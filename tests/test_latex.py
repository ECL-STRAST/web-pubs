import shutil

import pytest

from pubs import latex
from pubs.errors import CompileError

DOC = "\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n"


def test_find_main_picks_the_root_document(tmp_path):
    (tmp_path / "main.tex").write_text(DOC)
    (tmp_path / "chapter.tex").write_text("Just a fragment.\n")

    assert latex.find_main(tmp_path) == tmp_path / "main.tex"


def test_find_main_without_any_document(tmp_path):
    (tmp_path / "chapter.tex").write_text("Just a fragment.\n")

    with pytest.raises(CompileError, match="no root"):
        latex.find_main(tmp_path)


def test_find_main_with_several_documents(tmp_path):
    (tmp_path / "main.tex").write_text(DOC)
    (tmp_path / "poster.tex").write_text(DOC)

    with pytest.raises(CompileError, match="overleaf.main"):
        latex.find_main(tmp_path)


def test_build_failure_writes_the_log(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"

    def fail(args, **kwargs):
        raise _fake_failure("! Undefined control sequence.\n")

    monkeypatch.setattr(latex.subprocess, "run", fail)

    with pytest.raises(CompileError):
        latex.build(src, src / "main.tex", out)

    assert "Undefined control sequence" in (out / latex.LOG_NAME).read_text()


def test_build_failure_names_error_count_and_first(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (out / "main.log").write_text(
        "! Undefined control sequence.\nl.25 \\end{itemize}\n\n"
        "! Extra }, or forgotten \\endgroup.\nl.40 }\n"
    )

    def fail(args, **kwargs):
        raise _fake_failure("latexmk output, no ! lines here\n")

    monkeypatch.setattr(latex.subprocess, "run", fail)

    with pytest.raises(CompileError, match=r"2 errors.*Undefined control sequence"):
        latex.build(src, src / "main.tex", out)


def test_build_failure_without_tex_log(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"

    def fail(args, **kwargs):
        raise _fake_failure("! Undefined control sequence.\n")

    monkeypatch.setattr(latex.subprocess, "run", fail)

    with pytest.raises(CompileError, match="failed to compile; see"):
        latex.build(src, src / "main.tex", out)


def test_build_failure_tex_log_without_errors(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (out / "main.log").write_text("nothing alarming here\n")

    def fail(args, **kwargs):
        raise _fake_failure("! Undefined control sequence.\n")

    monkeypatch.setattr(latex.subprocess, "run", fail)

    with pytest.raises(CompileError, match="failed to compile; see"):
        latex.build(src, src / "main.tex", out)


def test_build_passes_shell_escape(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return _fake_success()

    monkeypatch.setattr(latex.subprocess, "run", fake_run)

    latex.build(src, src / "main.tex", out)

    assert latex.SHELL_ESCAPE in seen["args"]


def _fake_success():
    import subprocess

    return subprocess.CompletedProcess("latexmk", 0)


def _fake_failure(output):
    import subprocess

    return subprocess.CalledProcessError(1, "latexmk", output=output, stderr="")


def test_build_survives_undecodable_output(tmp_path, monkeypatch):
    """latexmk output that isn't valid UTF-8 (font/encoding messages are
    common offenders) must not crash subprocess.run; the normal
    CalledProcessError path should still run and write the log."""
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"

    # Stand-in for latexmk: writes an invalid UTF-8 byte (0xe1, the byte
    # from the real failure this fixes) to stderr and exits non-zero.
    fake = tmp_path / "fake-latexmk"
    fake.write_text("#!/bin/sh\nprintf 'bad byte: \\341 end\\n' >&2\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setattr(latex, "LATEXMK", str(fake))

    with pytest.raises(CompileError, match="failed to compile"):
        latex.build(src, src / "main.tex", out)

    assert (out / latex.LOG_NAME).is_file()


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="latexmk not installed")
def test_build_produces_a_pdf(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.tex").write_text(DOC)
    out = tmp_path / "out"

    pdf = latex.build(src, src / "main.tex", out)

    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
