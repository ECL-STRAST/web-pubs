import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.errors import MissingField

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "authors": ["Silvia Nieves Serrano"],
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(
        yaml.safe_dump(["biomechanics", "rehabilitation", "vr"])
    )
    (tmp_path / "content" / "theses").mkdir(parents=True)

    return tmp_path


def _add(repo, slug, data=None, summary="Text.\n", doc="thesis.pdf"):
    folder = repo / "content" / "theses" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data or MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text(summary)

    if doc:
        (folder / doc).write_bytes(b"%PDF-1.4\n")

    return folder


def _catalog(repo):
    return Catalog(config.load(repo))


def test_entries_sort_newest_first(repo):
    _add(repo, "2025-old", data=MINIMAL | {"year": 2025})
    _add(repo, "2027-new", data=MINIMAL | {"year": 2027})
    _add(repo, "2025-older", data=MINIMAL | {"year": 2025})

    slugs = [e.slug for e in _catalog(repo).entries()]

    assert slugs == ["2027-new", "2025-old", "2025-older"]


def test_find_returns_the_entry(repo):
    _add(repo, "2027-x")

    assert _catalog(repo).find("2027-x").title == MINIMAL["title"]


def test_find_missing_slug_raises(repo):
    with pytest.raises(MissingField, match="2027-nope"):
        _catalog(repo).find("2027-nope")


def test_create_scaffolds_a_usable_folder(repo):
    cat = _catalog(repo)

    folder = cat.create(
        slug="2027-x", type="thesis", year=2027,
        title="Untitled", authors=["Unknown"], degree="bachelor",
    )

    assert folder == repo / "content" / "theses" / "2027-x"
    assert (folder / "summary.md").is_file()
    assert cat.find("2027-x").year == 2027


def test_create_refuses_an_existing_slug(repo):
    _add(repo, "2027-x")

    with pytest.raises(FileExistsError):
        _catalog(repo).create(
            slug="2027-x", type="thesis", year=2027,
            title="t", authors=["a"], degree="bachelor",
        )


def test_sound_catalog_has_no_problems(repo):
    _add(repo, "2027-x")

    assert _catalog(repo).problems() == []


def test_unknown_topic_is_a_problem(repo):
    _add(repo, "2027-x", data=MINIMAL | {"topics": ["byomechanics"]})

    problems = _catalog(repo).problems()

    assert len(problems) == 1
    assert "byomechanics" in problems[0]


def test_missing_document_is_a_problem(repo):
    _add(repo, "2027-x", doc=None)

    assert any("thesis.pdf" in p for p in _catalog(repo).problems())


def test_missing_summary_is_a_problem(repo):
    folder = _add(repo, "2027-x")
    (folder / "summary.md").unlink()

    assert any("summary.md" in p for p in _catalog(repo).problems())


def test_declared_slides_must_exist(repo):
    _add(repo, "2027-x", data=MINIMAL | {"slides": "slides.pdf"})

    assert any("slides.pdf" in p for p in _catalog(repo).problems())


def test_malformed_repo_url_is_a_problem(repo):
    _add(repo, "2027-x", data=MINIMAL | {"repos": {"code": ["not-a-url"]}})

    problems = _catalog(repo).problems()

    assert any("2027-x" in p and "not-a-url" in p for p in problems)


def test_wellformed_repo_url_is_not_a_problem(repo):
    _add(repo, "2027-x", data=MINIMAL | {
        "repos": {
            "code": ["https://github.com/ECL-STRAST/example"],
            "docs": "https://github.com/ECL-STRAST/example-docs",
        },
    })

    assert _catalog(repo).problems() == []


def test_entry_without_repos_is_not_a_problem(repo):
    _add(repo, "2027-x")

    assert _catalog(repo).problems() == []


def test_schema_error_is_reported_not_raised(repo):
    _add(repo, "2027-x", data={"type": "thesis"})

    assert any("missing field" in p for p in _catalog(repo).problems())


def test_broken_yaml_does_not_abort_scan(repo):
    # Add one entry with broken YAML syntax, sorts first alphabetically.
    broken_folder = repo / "content" / "theses" / "2027-broken"
    broken_folder.mkdir(parents=True)
    (broken_folder / "entry.yaml").write_text("type: thesis\n  bad: [indent")
    (broken_folder / "summary.md").write_text("Text.\n")

    # Add one entry sorting after the broken one, with its own problem.
    _add(repo, "2027-sound", data=MINIMAL | {"topics": ["not-in-vocabulary"]})

    # problems() should complete without raising and collect all issues.
    problems = _catalog(repo).problems()

    # If the scan aborted at the broken entry, this would fail.
    assert any("2027-broken" in p for p in problems)
    assert any("2027-sound" in p for p in problems)


def test_declared_photo_must_exist(repo):
    _add(repo, "2027-x", data=MINIMAL | {"photo": "photo.jpg"})

    assert any("photo.jpg" in p for p in _catalog(repo).problems())


def test_present_photo_is_no_problem(repo):
    folder = _add(repo, "2027-x", data=MINIMAL | {"photo": "photo.jpg"})
    (folder / "photo.jpg").write_bytes(b"\xff\xd8\xff")

    assert _catalog(repo).problems() == []


def test_declared_image_must_exist(repo):
    _add(repo, "2027-x", data=MINIMAL | {"image": "cover.png"})

    assert any("cover.png" in p for p in _catalog(repo).problems())


def test_present_image_is_no_problem(repo):
    folder = _add(repo, "2027-x", data=MINIMAL | {"image": "cover.png"})
    (folder / "cover.png").write_bytes(b"\x89PNG\r\n")

    assert _catalog(repo).problems() == []
