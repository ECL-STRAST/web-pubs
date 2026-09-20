import pytest
import yaml

from pubs import entry, store
from pubs.errors import SchemaError

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "authors": ["Silvia Nieves Serrano"],
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def _make(tmp_path, slug, data=None, summary=None):
    folder = tmp_path / slug
    folder.mkdir(parents=True)
    (folder / store.ENTRY_FILE).write_text(yaml.safe_dump(data or MINIMAL, sort_keys=False))

    if summary is not None:
        (folder / store.SUMMARY_FILE).write_text(summary)

    return folder


def test_reads_slug_from_the_directory_name(tmp_path):
    folder = _make(tmp_path, "2027-nieves-serrano-biomechanics-db")

    assert store.read(folder).slug == "2027-nieves-serrano-biomechanics-db"


def test_reads_summary_into_the_entry(tmp_path):
    folder = _make(tmp_path, "2027-x", summary="Stores gait data.\n")

    assert store.read(folder).summary == "Stores gait data.\n"


def test_missing_summary_is_empty_not_an_error(tmp_path):
    folder = _make(tmp_path, "2027-x")

    assert store.read(folder).summary == ""


def test_write_then_read_round_trips(tmp_path):
    folder = tmp_path / "2027-x"
    folder.mkdir()
    original = entry.from_dict("2027-x", MINIMAL | {"slides": "slides.pdf"})

    store.write(folder, original)

    assert store.read(folder) == original


def test_write_does_not_touch_the_summary(tmp_path):
    folder = _make(tmp_path, "2027-x", summary="Hand written.\n")
    parsed = store.read(folder)

    store.write(folder, parsed)

    assert (folder / store.SUMMARY_FILE).read_text() == "Hand written.\n"


def test_invalid_entry_reports_the_file(tmp_path):
    folder = _make(tmp_path, "2027-x", data={"type": "thesis"})

    with pytest.raises(SchemaError, match="2027-x"):
        store.read(folder)


def test_dirs_lists_only_entry_folders(tmp_path):
    _make(tmp_path, "2027-b")
    _make(tmp_path, "2025-a")
    (tmp_path / "not-an-entry").mkdir()

    assert [d.name for d in store.dirs(tmp_path)] == ["2025-a", "2027-b"]


def test_dirs_on_a_missing_parent_is_empty(tmp_path):
    assert store.dirs(tmp_path / "nope") == []
