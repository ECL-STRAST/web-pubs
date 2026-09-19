import pytest
import yaml

from tft import cli

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
def repo(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'tft'\n")
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["biomechanics"]))
    monkeypatch.chdir(tmp_path)

    return tmp_path


def _entry(repo, slug, data=None, doc=True):
    folder = repo / "content" / "theses" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data or MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")

    if doc:
        (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    return folder


def test_find_root_walks_up(repo):
    nested = repo / "content" / "theses"
    nested.mkdir(parents=True)

    assert cli.find_root(nested) == repo


def test_validate_succeeds_on_a_sound_catalog(repo, capsys):
    _entry(repo, "2027-x")

    assert cli.main(["validate"]) == 0
    assert "ok" in capsys.readouterr().out


def test_validate_fails_and_lists_problems(repo, capsys):
    _entry(repo, "2027-x", doc=False)

    assert cli.main(["validate"]) == 1
    assert "thesis.pdf" in capsys.readouterr().out


def test_add_reports_a_missing_token(repo, monkeypatch, capsys):
    monkeypatch.delenv("OVERLEAF_GIT_TOKEN", raising=False)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "nieves-serrano-biomechanics-db",
    ])

    assert code == 1
    assert "OVERLEAF_GIT_TOKEN" in capsys.readouterr().err


def test_add_builds_the_slug_from_the_name(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        seen["name"] = name
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main(["add", "--overleaf", "abc", "--name", "nieves-serrano-biomechanics-db"])

    assert code == 0
    assert seen["name"] == "nieves-serrano-biomechanics-db"


def test_sync_reports_no_change(repo, monkeypatch, capsys):
    from tft.ingest import SyncResult

    _entry(repo, "2027-x")
    monkeypatch.setattr(
        "tft.ingest.Ingest.sync", lambda self, slug: SyncResult(changed=False),
    )

    assert cli.main(["sync", "2027-x"]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_sync_prints_warnings(repo, monkeypatch, capsys):
    from tft.ingest import SyncResult

    _entry(repo, "2027-x")
    monkeypatch.setattr(
        "tft.ingest.Ingest.sync",
        lambda self, slug: SyncResult(changed=True, warnings=("year is now 2028",)),
    )

    assert cli.main(["sync", "2027-x"]) == 0
    assert "year is now 2028" in capsys.readouterr().err


def test_add_passes_the_overrides_through(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        seen["overrides"] = overrides
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "x",
        "--title", "T", "--year", "2027",
    ])

    assert code == 0
    assert seen["overrides"].title == "T"
    assert seen["overrides"].year == 2027
    assert seen["overrides"].author is None


def test_add_publication_passes_the_type(repo, monkeypatch):
    seen = {}

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        seen["type"] = type
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main([
        "add", "--overleaf", "abc", "--name", "x", "--type", "publication",
    ])

    assert code == 0
    assert seen["type"] == "publication"


def test_add_reports_an_unreadable_field(repo, monkeypatch, capsys):
    from tft.errors import ExtractError

    def fake_add(self, project_id, name, overrides=None, type="thesis"):
        raise ExtractError("could not read title; pass --title")

    monkeypatch.setattr("tft.ingest.Ingest.add", fake_add)

    code = cli.main(["add", "--overleaf", "abc", "--name", "x"])

    assert code == 1
    assert "--title" in capsys.readouterr().err


def test_add_doi_implies_publication(repo, monkeypatch):
    seen = {}

    def fake_add_from_doi(self, doi, name):
        seen["doi"] = doi
        seen["name"] = name
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add_from_doi", fake_add_from_doi)

    code = cli.main(["add", "--doi", "10.1109/x", "--name", "autor-paper"])

    assert code == 0
    assert seen == {"doi": "10.1109/x", "name": "autor-paper"}


def test_add_doi_with_type_thesis_is_refused(repo, capsys):
    code = cli.main(["add", "--doi", "10.1109/x", "--name", "x", "--type", "thesis"])

    assert code == 1
    assert "thesis" in capsys.readouterr().err


def test_add_doi_with_type_publication_is_allowed(repo, monkeypatch):
    def fake_add_from_doi(self, doi, name):
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add_from_doi", fake_add_from_doi)

    assert cli.main(["add", "--doi", "10.1109/x", "--name", "x",
                     "--type", "publication"]) == 0


@pytest.mark.parametrize("flag,value", [
    ("--title", "T"), ("--author", "A"), ("--year", "2025"), ("--degree", "bachelor"),
])
def test_add_doi_refuses_the_overleaf_overrides(repo, capsys, flag, value):
    # The registry supplies them; silently dropping the flag would lie.
    code = cli.main(["add", "--doi", "10.1109/x", "--name", "x", flag, value])

    assert code == 1
    assert flag in capsys.readouterr().err


def test_add_refuses_overleaf_and_doi_together(repo):
    with pytest.raises(SystemExit):
        cli.main(["add", "--overleaf", "abc", "--doi", "10.1109/x", "--name", "x"])


def test_add_requires_one_source(repo):
    with pytest.raises(SystemExit):
        cli.main(["add", "--name", "x"])


def test_add_doi_reports_registry_error(repo, monkeypatch, capsys):
    from tft.errors import RegistryError

    def fake(self, doi, name):
        raise RegistryError("no registry knows 10.1109/x; check the spelling")

    monkeypatch.setattr("tft.ingest.Ingest.add_from_doi", fake)

    assert cli.main(["add", "--doi", "10.1109/x", "--name", "x"]) == 1
    assert "check the spelling" in capsys.readouterr().err


def test_add_empty_doi_reaches_the_registry_check(repo, capsys):
    # "" must not fall through to the Overleaf branch: fetch's regex rejects
    # it as a non-DOI, rather than add() crashing on a None project id.
    assert cli.main(["add", "--doi", "", "--name", "x"]) == 1
    assert "is not a DOI" in capsys.readouterr().err
