import pytest
import yaml

from pubs import cli

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
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'pubs'\n")
    (tmp_path / "taxonomy").mkdir()
    (tmp_path / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["biomechanics"]))

    folder = tmp_path / "content" / "theses" / "2027-x"
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(MINIMAL, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")
    (folder / "thesis.pdf").write_bytes(b"%PDF-1.4\n")

    monkeypatch.chdir(tmp_path)

    return tmp_path


def test_build_writes_the_default_site_dir(repo):
    assert cli.main(["build"]) == 0
    assert (repo / "site" / "index.html").is_file()
    assert (repo / "site" / "index.json").is_file()


def test_build_honours_an_explicit_out(repo, tmp_path):
    out = tmp_path / "elsewhere"

    assert cli.main(["build", "--out", str(out)]) == 0
    assert (out / "index.html").is_file()
