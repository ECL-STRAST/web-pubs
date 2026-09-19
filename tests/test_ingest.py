import shutil

import pytest
import yaml

from tft import config
from tft.catalog import Catalog
from tft.entry import PUBLICATION
from tft.errors import CompileError, ExtractError
from tft.ingest import Ingest, Overrides

PROJECT = "698b41fa174f9aec00db94cb"
SHA = "a3f19c2000000000000000000000000000000000"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "public" / "taxonomy").mkdir(parents=True)
    (tmp_path / "public" / "taxonomy" / "topics.yaml").write_text(yaml.safe_dump(["vr"]))
    (tmp_path / "public" / "tft.toml").write_text(
        f'[paths]\nprivate = "{tmp_path / "private"}"\n'
    )

    return tmp_path / "public"


MAIN = r"""
\newcommand{\authorname}{Silvia Nieves Serrano}
\newcommand{\tfgtitle}{A database for biomechanical data}
\newcommand{\supervisor}{Rodrigo García Carmona, Ana Pérez Ruiz}
\newcommand{\fecha}{Junio 2027}
GRADO EN INGENIERÍA BIOMÉDICA
TRABAJO FIN DE GRADO
\documentclass{article}
\begin{document}x\end{document}
"""

ABSTRACT = r"""
\chapter*{Abstract}
\addcontentsline{toc}{chapter}{Abstract}
This thesis presents a \textbf{database} for biomechanical data.

\vfill
\textbf{Keywords:} biomechanics, Databases.
"""


def _ingest(repo, sha=SHA, fail=False, main=MAIN, abstract=ABSTRACT):
    """An Ingest whose drivers are stubbed: no network, no TeX."""
    def fetch(project_id, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "main.tex").write_text(main)
        (dest / "figure.png").write_bytes(b"png")

        if abstract is not None:
            (dest / "abstract.tex").write_text(abstract)

        return sha

    def build(src, main, out):
        if fail:
            raise CompileError("boom")
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / "main.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    cfg = config.load(repo)

    return Ingest(cfg, Catalog(cfg), fetch=fetch, build=build)


def _add(repo, ingest):
    return ingest.add(project_id=PROJECT, name="nieves-serrano-biomechanics-db")


def test_add_derives_the_slug_from_the_extracted_year(repo):
    folder = _add(repo, _ingest(repo))

    assert folder.name == "2027-nieves-serrano-biomechanics-db"


def test_add_fills_entry_yaml_from_the_source(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["title"] == "A database for biomechanical data"
    assert data["authors"] == ["Silvia Nieves Serrano"]
    assert data["year"] == 2027
    assert data["degree"] == "bachelor"
    assert data["keywords"] == ["biomechanics", "databases"]


def test_add_writes_the_abstract_as_the_summary(repo):
    folder = _add(repo, _ingest(repo))

    assert (folder / "summary.md").read_text().startswith(
        "This thesis presents a database for biomechanical data."
    )


def test_missing_metadata_names_the_field(repo):
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"

    with pytest.raises(ExtractError, match="title"):
        _add(repo, _ingest(repo, main=bare, abstract=None))


def test_override_supplies_a_missing_field(repo):
    main = MAIN.replace(r"\newcommand{\tfgtitle}{A database for biomechanical data}", "")
    ingest = _ingest(repo, main=main)

    folder = ingest.add(
        project_id=PROJECT, name="nieves-serrano-biomechanics-db",
        overrides=Overrides(title="Supplied by hand"),
    )
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["title"] == "Supplied by hand"


def test_override_beats_the_source(repo):
    folder = _ingest(repo).add(
        project_id=PROJECT, name="x", overrides=Overrides(year=2030),
    )

    assert folder.name == "2030-x"


def test_add_publication_needs_only_flags(repo):
    # A conference paper has no cover phrase, no abstract chapter: none of
    # the thesis landmarks apply, and none should be required.
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"
    ingest = _ingest(repo, main=bare, abstract=None)

    folder = ingest.add(
        project_id=PROJECT, name="garcia-paper",
        overrides=Overrides(title="A Paper", author="X. Garcia", year=2027),
        type=PUBLICATION,
    )
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["title"] == "A Paper"
    assert "degree" not in data


def test_add_without_main_tex_succeeds_with_full_overrides(repo):
    """The spec promises this: a different template, still ingestable."""
    def fetch(project_id, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "root.tex").write_text(
            "\\documentclass{article}\\begin{document}x\\end{document}"
        )
        (dest / "abstract.tex").write_text(ABSTRACT)
        return SHA

    def build(src, main, out):
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / "main.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    cfg = config.load(repo)
    ingest = Ingest(cfg, Catalog(cfg), fetch=fetch, build=build)

    folder = ingest.add(
        project_id=PROJECT, name="x",
        overrides=Overrides(title="T", author="A", year=2027, degree="bachelor"),
    )
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["title"] == "T"
    assert data["authors"] == ["A"]
    assert data["year"] == 2027
    assert data["degree"] == "bachelor"
    assert data["keywords"] == ["biomechanics", "databases"]


def test_extraction_failure_leaves_no_entry(repo):
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"

    with pytest.raises(ExtractError):
        _add(repo, _ingest(repo, main=bare, abstract=None))

    assert not (repo / "content" / "theses").exists() or \
        list((repo / "content" / "theses").iterdir()) == []


def test_add_installs_pdf_and_stubs(repo):
    folder = _add(repo, _ingest(repo))

    assert (folder / "thesis.pdf").read_bytes().startswith(b"%PDF")
    assert (folder / "summary.md").is_file()


def test_add_records_project_and_commit(repo):
    folder = _add(repo, _ingest(repo))

    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["overleaf"]["project_id"] == PROJECT
    assert data["overleaf"]["commit"] == SHA


def test_add_mirrors_sources_without_git(repo):
    _add(repo, _ingest(repo))

    mirror = repo.parent / "private" / "sources" / "theses" / "2027-nieves-serrano-biomechanics-db"

    assert (mirror / "main.tex").is_file()
    assert (mirror / "figure.png").is_file()
    assert not (mirror / ".git").exists()


def test_recorded_mirror_is_a_url_not_a_local_path(repo):
    folder = _add(repo, _ingest(repo))

    data = yaml.safe_load((folder / "entry.yaml").read_text())
    expected = (
        f"{config.DEFAULT_MIRROR_BASE}/theses/2027-nieves-serrano-biomechanics-db"
    )

    assert data["overleaf"]["mirror"] == expected


def test_mirror_base_override_is_honoured(repo):
    (repo / "tft.toml").write_text(
        (repo / "tft.toml").read_text() + 'mirror_base = "https://example.org/sources"\n'
    )

    folder = _add(repo, _ingest(repo))

    data = yaml.safe_load((folder / "entry.yaml").read_text())
    assert data["overleaf"]["mirror"] == (
        "https://example.org/sources/theses/2027-nieves-serrano-biomechanics-db"
    )

    # The actual files still land at the local private-repo path.
    mirror_dir = repo.parent / "private" / "sources" / "theses" / "2027-nieves-serrano-biomechanics-db"
    assert (mirror_dir / "main.tex").is_file()


def test_add_leaves_nothing_behind_when_the_compile_fails(repo):
    with pytest.raises(CompileError):
        _add(repo, _ingest(repo, fail=True))

    assert not (repo / "content" / "theses" / "2027-nieves-serrano-biomechanics-db").exists()


def test_sync_refreshes_pdf_and_sha(repo):
    folder = _add(repo, _ingest(repo))
    later = "b" * 40

    assert _ingest(repo, sha=later).sync("2027-nieves-serrano-biomechanics-db").changed is True

    data = yaml.safe_load((folder / "entry.yaml").read_text())
    assert data["overleaf"]["commit"] == later


def test_failed_sync_keeps_the_previous_pdf(repo):
    folder = _add(repo, _ingest(repo))
    (folder / "thesis.pdf").write_bytes(b"%PDF-original\n")

    with pytest.raises(CompileError):
        _ingest(repo, sha="c" * 40, fail=True).sync("2027-nieves-serrano-biomechanics-db")

    assert (folder / "thesis.pdf").read_bytes() == b"%PDF-original\n"


def test_failed_mirror_keeps_the_pdf_and_yaml(repo):
    """A mirror failure must not leave folder/entry.yaml disagreeing."""
    folder = _add(repo, _ingest(repo))
    (folder / "thesis.pdf").write_bytes(b"%PDF-original\n")

    # Replace the private checkout with a file: _mirror's mkdir then
    # fails, before either the PDF or entry.yaml can be touched.
    private = repo.parent / "private"
    shutil.rmtree(private)
    private.write_text("blocker")

    with pytest.raises(NotADirectoryError):
        _ingest(repo, sha="d" * 40).sync("2027-nieves-serrano-biomechanics-db")

    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert (folder / "thesis.pdf").read_bytes() == b"%PDF-original\n"
    assert data["overleaf"]["commit"] == SHA


def test_failed_sync_keeps_the_previous_summary(repo):
    """A failed install must not leave summary.md re-derived early."""
    folder = _add(repo, _ingest(repo))
    (folder / "summary.md").write_text("Original summary.\n")

    # Same mirror-blocking trick as test_failed_mirror_keeps_the_pdf_and_yaml:
    # _install fails before summary.md is touched.
    private = repo.parent / "private"
    shutil.rmtree(private)
    private.write_text("blocker")

    with pytest.raises(NotADirectoryError):
        _ingest(repo, sha="d" * 40).sync("2027-nieves-serrano-biomechanics-db")

    assert (folder / "summary.md").read_text() == "Original summary.\n"


def test_failed_copy_leaves_no_tmp_residue(repo, monkeypatch):
    """A copy failure must not leave the .tmp sibling behind."""
    folder = _add(repo, _ingest(repo))
    (folder / "thesis.pdf").write_bytes(b"%PDF-original\n")

    real_copyfile = shutil.copyfile

    def broken_copy(src, dst, *args, **kwargs):
        # Only the final PDF copy must fail; the source mirror (which also
        # uses copyfile, via copytree) must proceed normally.
        if str(dst).endswith(".tmp"):
            raise OSError("disk full")
        return real_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", broken_copy)

    with pytest.raises(OSError):
        _ingest(repo, sha="e" * 40).sync("2027-nieves-serrano-biomechanics-db")

    assert (folder / "thesis.pdf").read_bytes() == b"%PDF-original\n"
    assert not any(folder.glob("*.tmp"))


NEXT_SHA = "b7c379a000000000000000000000000000000000"


def _synced(repo, folder, **stub):
    """Re-sync the entry in folder with a moved Overleaf commit."""
    return _ingest(repo, sha=NEXT_SHA, **stub).sync(folder.name)


def test_sync_is_a_noop_when_overleaf_has_not_moved(repo):
    folder = _add(repo, _ingest(repo))

    assert _ingest(repo).sync(folder.name).changed is False


def test_sync_refreshes_the_summary_from_the_abstract(repo):
    folder = _add(repo, _ingest(repo))
    (folder / "summary.md").write_text("Hand-written text.\n")
    moved = ABSTRACT.replace("a \\textbf{database}", "an \\textbf{archive}")

    result = _synced(repo, folder, abstract=moved)

    assert result.changed is True
    assert "archive" in (folder / "summary.md").read_text()


def test_sync_refreshes_keywords(repo):
    folder = _add(repo, _ingest(repo))
    moved = ABSTRACT.replace("biomechanics, Databases.", "gait, Kinematics.")

    _synced(repo, folder, abstract=moved)
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["keywords"] == ["gait", "kinematics"]


def test_sync_preserves_human_owned_fields(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())
    data["topics"] = ["biomechanics"]
    data["score"] = 10
    data["honours"] = True
    data["slides"] = "slides.pdf"
    data["image"] = "cover.png"
    data["video"] = "https://vimeo.com/76979871"
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    _synced(repo, folder)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["topics"] == ["biomechanics"]
    assert after["score"] == 10
    assert after["honours"] is True
    assert after["slides"] == "slides.pdf"
    assert after["image"] == "cover.png"
    assert after["video"] == "https://vimeo.com/76979871"


def test_add_records_the_programme_and_supervisors(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["programme"] == "GRADO EN INGENIERÍA BIOMÉDICA"
    assert data["supervisors"] == ["Rodrigo García Carmona", "Ana Pérez Ruiz"]


def test_add_without_a_programme_omits_the_field(repo):
    main = MAIN.replace("GRADO EN INGENIERÍA BIOMÉDICA\n", "")
    folder = _add(repo, _ingest(repo, main=main))
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert "programme" not in data


def test_sync_backfills_the_programme_and_supervisors(repo):
    folder = _add(repo, _ingest(repo))
    data = yaml.safe_load((folder / "entry.yaml").read_text())
    del data["programme"]
    del data["supervisors"]
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    _synced(repo, folder)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["programme"] == "GRADO EN INGENIERÍA BIOMÉDICA"
    assert after["supervisors"] == ["Rodrigo García Carmona", "Ana Pérez Ruiz"]


def test_sync_overwrites_hand_entered_supervisors(repo):
    # supervisors is derived now: the \supervisor macro is the whole list,
    # so a re-sync replacing it cannot lose a co-supervisor.
    folder = _add(repo, _ingest(repo))
    moved = MAIN.replace(
        "Rodrigo García Carmona, Ana Pérez Ruiz", "Rodrigo García Carmona",
    )

    _synced(repo, folder, main=moved)
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert after["supervisors"] == ["Rodrigo García Carmona"]


def test_a_publication_gets_no_programme(repo):
    bare = "\\documentclass{article}\\begin{document}x\\end{document}"
    ingest = _ingest(repo, main=bare, abstract=None)

    folder = ingest.add(
        project_id=PROJECT, name="garcia-paper",
        overrides=Overrides(title="A Paper", author="X. Garcia", year=2027),
        type=PUBLICATION,
    )
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert "programme" not in data


def test_sync_warns_but_does_not_rename_on_a_year_change(repo):
    folder = _add(repo, _ingest(repo))
    moved = MAIN.replace("Junio 2027", "Junio 2028")

    result = _synced(repo, folder, main=moved)
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["year"] == 2028
    assert folder.name == "2027-nieves-serrano-biomechanics-db"
    assert folder.is_dir()
    assert any("2028" in w for w in result.warnings)
