import json

import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.errors import BadValue, UnsafeOutputDir
from tft.site import Site, titlecase

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "authors": ["Silvia Nieves Serrano"],
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}

FULL = MINIMAL | {
    "programme": "GRADO EN INGENIERÍA BIOMÉDICA",
    "supervisors": ["Rodrigo Garcia Carmona"],
    "topics": ["biomechanics", "rehabilitation"],
    "keywords": ["motion capture", "c3d"],
    "score": 10,
    "honours": True,
    "repos": {
        "code": ["https://github.com/ECL-STRAST/libremotion-chloe"],
        "docs": "https://github.com/ECL-STRAST/libremotion-chloe-docs",
    },
    "slides": "slides.pdf",
}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(
        yaml.safe_dump(["biomechanics", "rehabilitation"])
    )

    return tmp_path


def _entry(repo, slug, data, summary="Stores **gait** data.\n"):
    folder = repo / "content" / "theses" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    (folder / "summary.md").write_text(summary)
    (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    if data.get("slides"):
        (folder / data["slides"]).write_bytes(b"%PDF-slides\n")

    return folder


def _build(repo):
    cfg = config.load(repo)
    out = repo / "site"
    Site(cfg, Catalog(cfg)).build(out)

    return out


def test_index_json_matches_the_golden_record(repo):
    _entry(repo, "2027-nieves-serrano-biomechanics-db", FULL)

    out = _build(repo)
    records = json.loads((out / "index.json").read_text())

    assert records == [{
        "slug": "2027-nieves-serrano-biomechanics-db",
        "type": "thesis",
        "title": "A database for biomechanical data",
        "authors": ["Silvia Nieves Serrano"],
        "year": 2027,
        "degree": "bachelor",
        "kind": None,
        "programme": "GRADO EN INGENIERÍA BIOMÉDICA",
        "venue": None,
        "doi": None,
        "published": None,
        "language": "en",
        "topics": ["biomechanics", "rehabilitation"],
        "supervisors": ["Rodrigo Garcia Carmona"],
        "keywords": ["motion capture", "c3d"],
        "score": 10,
        "honours": True,
        "url": "entries/2027-nieves-serrano-biomechanics-db/",
        "doc": "entries/2027-nieves-serrano-biomechanics-db/thesis.pdf",
        "slides": "entries/2027-nieves-serrano-biomechanics-db/slides.pdf",
        "has_code": True,
        "has_slides": True,
        "summary": "Stores gait data.",
    }]


def test_unfinished_entry_has_false_flags(repo):
    _entry(repo, "2027-x", MINIMAL)

    records = json.loads((_build(repo) / "index.json").read_text())

    assert records[0]["has_code"] is False
    assert records[0]["has_slides"] is False
    assert records[0]["slides"] is None
    assert records[0]["programme"] is None


def test_documents_are_copied_next_to_the_page(repo):
    _entry(repo, "2027-x", FULL)

    out = _build(repo)

    assert (out / "entries" / "2027-x" / "thesis.pdf").read_bytes().startswith(b"%PDF")
    assert (out / "entries" / "2027-x" / "slides.pdf").is_file()


def test_entry_page_renders_summary_markdown(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "<strong>gait</strong>" in page
    assert "libremotion-chloe" in page


def test_index_page_ships_the_assets(repo):
    _entry(repo, "2027-x", MINIMAL)

    out = _build(repo)

    assert (out / "index.html").is_file()
    assert (out / "assets" / "style.css").is_file()


def test_build_replaces_a_previous_run(repo):
    _entry(repo, "2027-x", MINIMAL)
    out = _build(repo)
    (out / "stale.html").write_text("old")

    _build(repo)

    assert not (out / "stale.html").exists()


def test_missing_slides_aborts_before_deleting_output(repo):
    _entry(repo, "2027-x", FULL)
    out = _build(repo)
    (out / "sentinel.html").write_text("kept")

    # The metadata still declares slides, but the file behind it is gone.
    (repo / "content" / "theses" / "2027-x" / "slides.pdf").unlink()

    with pytest.raises(BadValue, match="2027-x.*slides.pdf"):
        _build(repo)

    assert (out / "sentinel.html").read_text() == "kept"


def test_missing_document_names_the_slug(repo):
    folder = _entry(repo, "2027-x", MINIMAL)
    (folder / "thesis.pdf").unlink()

    with pytest.raises(BadValue, match="2027-x"):
        _build(repo)


def test_build_into_a_fresh_path_works(repo):
    _entry(repo, "2027-x", MINIMAL)

    out = _build(repo)

    assert (out / "index.html").is_file()


def test_accents_survive_round_trip(repo):
    """entry.yaml and index.json must stay UTF-8, regardless of locale."""
    name = "Rodrigo García Carmona"
    _entry(repo, "2027-x", FULL | {"authors": [name]})
    cfg = config.load(repo)
    cat = Catalog(cfg)
    cat.save(cat.find("2027-x"))  # round-trip through store.write

    out = _build(repo)

    entry_yaml = (repo / "content" / "theses" / "2027-x" / "entry.yaml").read_text(encoding="utf-8")
    assert name in entry_yaml

    index = (out / "index.json").read_text(encoding="utf-8")
    assert name in index


def test_build_refuses_a_foreign_directory(repo):
    """A directory without index.json is not a previous build; it survives."""
    _entry(repo, "2027-x", MINIMAL)
    cfg = config.load(repo)
    out = repo / "not-a-build"
    out.mkdir()
    (out / "important.txt").write_text("do not delete me")

    with pytest.raises(UnsafeOutputDir, match=str(out)):
        Site(cfg, Catalog(cfg)).build(out)

    assert (out / "important.txt").read_text() == "do not delete me"


def test_entry_without_a_score_has_nulls(repo):
    _entry(repo, "2027-x", MINIMAL)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["score"] is None
    assert record["honours"] is False
    assert record["keywords"] == []


def test_entry_page_shows_the_score(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "10 / 10" in page
    assert "Matrícula de Honor" in page


def test_entry_page_lists_keywords(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "motion capture" in page


def test_entry_page_shows_the_portrait_when_present(repo):
    folder = _entry(repo, "2027-x", FULL | {"photo": "photo.jpg"})
    (folder / "photo.jpg").write_bytes(b"\xff\xd8\xff")

    out = _build(repo)
    page = (out / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="photo.jpg"' in page
    assert (out / "entries" / "2027-x" / "photo.jpg").is_file()


def test_entry_page_omits_the_portrait_block_when_absent(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "portrait" not in page


GITHUB_URL = "https://github.com/snieves"
LINKEDIN_URL = "https://www.linkedin.com/in/snieves"


def test_entry_page_shows_author_links_when_present(repo):
    _entry(repo, "2027-x", FULL | {"author_github": GITHUB_URL, "author_linkedin": LINKEDIN_URL})

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert f'href="{GITHUB_URL}"' in page
    assert f'href="{LINKEDIN_URL}"' in page


def test_entry_page_omits_author_links_when_absent(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "social" not in page


def test_a_declared_photo_missing_from_disk_fails_the_build(repo):
    _entry(repo, "2027-x", FULL | {"photo": "photo.jpg"})

    with pytest.raises(BadValue, match="2027-x.*photo.jpg"):
        _build(repo)


def test_logo_and_favicon_ship_with_the_site(repo):
    _entry(repo, "2027-x", MINIMAL)

    out = _build(repo)

    assert (out / "assets" / "ecl-logo.png").is_file()
    assert 'rel="icon"' in (out / "index.html").read_text()
    assert 'rel="icon"' in (out / "entries" / "2027-x" / "index.html").read_text()


def test_stylesheet_defines_the_ecl_palette(repo):
    _entry(repo, "2027-x", MINIMAL)

    css = (_build(repo) / "assets" / "style.css").read_text()

    for token in ["--ecl-blue: #046ba5", "--ecl-navy: #093d76",
                  "--ecl-teal: #218880", "--ecl-green: #1a6c46"]:
        assert token in css


def test_image_is_copied_next_to_the_page(repo):
    folder = _entry(repo, "2027-x", FULL | {"image": "cover.png"})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")

    out = _build(repo)

    assert (out / "entries" / "2027-x" / "cover.png").is_file()


def test_a_declared_image_missing_from_disk_fails_the_build(repo):
    folder = _entry(repo, "2027-x", FULL | {"image": "cover.png"})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")
    out = _build(repo)
    (out / "sentinel.html").write_text("kept")

    # The metadata still declares the image, but the file behind it is gone.
    (folder / "cover.png").unlink()

    with pytest.raises(BadValue, match="2027-x.*cover.png"):
        _build(repo)

    assert (out / "sentinel.html").read_text() == "kept"


def test_entry_page_carries_the_site_header(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="../../assets/ecl-logo.png"' in page
    assert 'class="rule"' in page
    assert 'href="../../"' in page
    # The header's home link replaces the old back link; it is not duplicated.
    assert "All entries" not in page


def test_entry_page_shows_the_programme_title_cased(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "Grado en Ingeniería Biomédica" in page
    assert "GRADO EN INGENIERÍA BIOMÉDICA" not in page


def test_entry_page_omits_the_programme_when_absent(repo):
    _entry(repo, "2027-x", MINIMAL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "Grado en" not in page


def test_the_card_meta_line_keeps_showing_the_degree_not_the_programme(repo):
    # The card's meta line is author · year · degree; a full programme
    # name would wrap it on a phone. The programme stays searchable only.
    _entry(repo, "2027-x", FULL)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["degree"] == "bachelor"
    assert record["programme"] == "GRADO EN INGENIERÍA BIOMÉDICA"


@pytest.mark.parametrize("raw,shown", [
    ("GRADO EN INGENIERÍA BIOMÉDICA", "Grado en Ingeniería Biomédica"),
    ("MÁSTER EN INGENIERÍA DE TELECOMUNICACIÓN", "Máster en Ingeniería de Telecomunicación"),
    ("EN", "En"),
    ("", ""),
])
def test_titlecase_lowercases_spanish_connectives(raw, shown):
    assert titlecase(raw) == shown


VIMEO_URL = "https://vimeo.com/76979871"
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _with_media(repo, slug="2027-x", video=YOUTUBE_URL):
    folder = _entry(repo, slug, FULL | {"image": "cover.png", "video": video})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")

    return folder


def test_image_and_video_render_before_the_abstract(repo):
    _with_media(repo)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert page.index("thesis-image") < page.index('class="summary"')
    assert page.index("<iframe") < page.index('class="summary"')


def test_video_src_is_built_from_the_id_not_the_stored_url(repo):
    _with_media(repo)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in page
    assert YOUTUBE_URL not in page


def test_a_vimeo_video_uses_the_vimeo_player(repo):
    _with_media(repo, video=VIMEO_URL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert 'src="https://player.vimeo.com/video/76979871"' in page


def test_media_never_enters_the_index(repo):
    _with_media(repo)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert "image" not in record
    assert "video" not in record


def test_entry_page_omits_the_media_blocks_when_absent(repo):
    _entry(repo, "2027-x", FULL)

    page = (_build(repo) / "entries" / "2027-x" / "index.html").read_text()

    assert "thesis-image" not in page
    assert "<iframe" not in page


PAPER = {
    "type": "publication",
    "title": "Motion capture in the wild",
    "authors": ["A. Autor", "B. Autor"],
    "year": 2026,
    "kind": "journal",
    "topics": ["biomechanics"],
    "language": "en",
    "venue": "IEEE TVCG",
    "doi": "10.1109/TVCG.2026.1234567",
    "published": "2026-03-14",
}


def _publication(repo, slug="2026-x", pdf=False, kind=None):
    data = PAPER if kind is None else PAPER | {"kind": kind}

    folder = repo / "content" / "publications" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")

    if pdf:
        (folder / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    return folder


def test_publication_without_a_pdf_builds_and_has_no_doc(repo):
    _publication(repo)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["doc"] is None


def test_publication_with_a_pdf_copies_it(repo):
    _publication(repo, pdf=True)

    out = _build(repo)

    assert (out / "entries" / "2026-x" / "paper.pdf").read_bytes().startswith(b"%PDF")
    assert json.loads((out / "index.json").read_text())[0]["doc"] == "entries/2026-x/paper.pdf"


def test_index_page_offers_the_group_buttons(repo):
    _entry(repo, "2027-x", MINIMAL)
    _publication(repo)

    page = (_build(repo) / "index.html").read_text()

    assert 'id="group-thesis"' in page
    assert 'id="group-publication"' in page
    assert "Theses (1)" in page
    assert "Publications (1)" in page


def test_index_page_has_no_type_select(repo):
    _entry(repo, "2027-x", MINIMAL)
    _publication(repo)

    assert 'id="type"' not in (_build(repo) / "index.html").read_text()


def test_index_page_offers_the_kind_filter(repo):
    _publication(repo)

    page = (_build(repo) / "index.html").read_text()

    assert 'id="kind"' in page
    assert "<option>journal</option>" in page


def test_placeholder_kind_is_not_a_filter_option(repo):
    _publication(repo, kind="CHANGE-ME")

    assert "<option>CHANGE-ME</option>" not in (_build(repo) / "index.html").read_text()


def test_publication_record_carries_the_kind(repo):
    _publication(repo)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["kind"] == "journal"


def test_publication_page_links_the_doi_and_has_no_pdf_item(repo):
    _publication(repo)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert 'href="https://doi.org/10.1109/TVCG.2026.1234567"' in page
    assert "Document (PDF)" not in page


def test_publication_page_with_a_pdf_offers_both(repo):
    _publication(repo, pdf=True)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert "Document (PDF)" in page
    assert 'href="https://doi.org/10.1109/TVCG.2026.1234567"' in page


def test_publication_page_shows_authors_venue_and_date(repo):
    _publication(repo)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert "A. Autor, B. Autor" in page
    assert "IEEE TVCG" in page
    assert "2026-03-14" in page


def test_publication_page_shows_the_kind(repo):
    _publication(repo)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert "(journal)" in page


def test_entry_page_topic_link_carries_the_group(repo):
    # A topic click from a paper must land on Publications, not Theses.
    _publication(repo)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert "?group=publication&topic=biomechanics" in page
