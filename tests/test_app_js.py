import json
import re
from pathlib import Path

import yaml

from pubs import config
from pubs.catalog import Catalog
from pubs.site import Site

APP_JS = Path(__file__).parent.parent / "tools" / "pubs" / "assets" / "app.js"

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "authors": ["Silvia Nieves Serrano"],
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def _fields_read_by(source: str) -> set[str]:
    return set(re.findall(r"\be\.([a-z_]+)", source))


def test_app_reads_only_fields_the_record_provides(tmp_path):
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["biomechanics"]))
    folder = tmp_path / "content" / "theses" / "2027-x"
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")
    (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    cfg = config.load(tmp_path)
    Site(cfg, Catalog(cfg)).build(tmp_path / "site")
    record = json.loads((tmp_path / "site" / "index.json").read_text())[0]

    assert _fields_read_by(APP_JS.read_text()) <= set(record)


def test_app_binds_every_filter_control():
    source = APP_JS.read_text()

    for control in ["q", "year", "degree", "kind", "topic", "code", "slides"]:
        assert f'"{control}"' in source or f"'{control}'" in source


def test_app_escapes_interpolated_text():
    # Titles and summaries are authored content; they must never be raw HTML.
    assert "escape" in APP_JS.read_text()


def test_app_escapes_quotes_in_attributes():
    # URL in href attribute must escape quotes to prevent attribute injection.
    source = APP_JS.read_text()
    assert "&quot;" in source


def test_app_reads_the_score_and_keywords():
    source = APP_JS.read_text()

    assert "e.score" in source
    assert "e.keywords" in source


def test_app_searches_the_programme():
    # "biomédica" must find the thesis even though the card never shows it.
    assert "e.programme" in APP_JS.read_text()


def test_app_binds_the_group_buttons():
    source = APP_JS.read_text()

    assert 'const GROUPS = ["thesis", "publication"]' in source
    assert "group-${g}" in source


def test_app_keeps_the_group_in_the_url():
    # Shared links and topic clicks must land on the same group.
    source = APP_JS.read_text()

    assert "group=" in source


def test_app_honours_a_legacy_type_param():
    # ?type=publication predates the group buttons: it names a group.
    assert 'params.get("type")' in APP_JS.read_text()


def test_app_ignores_a_hidden_facet():
    # A hidden degree/kind select belongs to the other group and
    # filtering by it would empty the list invisibly.
    assert "node.hidden" in APP_JS.read_text()


def test_app_searches_authors_and_venue():
    source = APP_JS.read_text()

    assert "e.authors" in source
    assert "e.venue" in source
