"""Compiles a LaTeX source tree. The only module that runs latexmk."""

import subprocess
from pathlib import Path

from .errors import CompileError

LATEXMK = "latexmk"
LOG_NAME = "latexmk.log"
ROOT_MARKER = "\\documentclass"
# minted needs shell access to run Pygments; this lets a compiled
# document execute shell commands, so only compile trusted sources.
SHELL_ESCAPE = "-shell-escape"

# LaTeX (not latexmk) writes its own log per jobname; that's where "!"
# error lines reliably show up, unlike latexmk's captured stdout/stderr.
TEX_LOG_SUFFIX = ".log"
# TeX's own end-of-run summary line; not a distinct reported error.
FATAL_SUMMARY_MARKER = "==> Fatal error occurred"
ERROR_PREVIEW_LEN = 120


def find_main(src: Path) -> Path:
    """The root .tex at the top of the source tree."""
    roots = [p for p in sorted(src.glob("*.tex")) if ROOT_MARKER in p.read_text(errors="ignore")]

    if not roots:
        raise CompileError(f"no root .tex found in {src}")

    if len(roots) > 1:
        names = ", ".join(p.name for p in roots)
        raise CompileError(f"several root files ({names}); set overleaf.main")

    return roots[0]


def _first_error(log: Path) -> tuple[int, str | None]:
    """Count of "!" error lines in LaTeX's own log, and the first one."""
    if not log.is_file():
        return 0, None

    # errors="replace": TeX logs aren't guaranteed valid UTF-8 either.
    text = log.read_text(encoding="utf-8", errors="replace")
    errors = [
        ln for ln in text.splitlines()
        if ln.startswith("!") and FATAL_SUMMARY_MARKER not in ln
    ]

    if not errors:
        return 0, None

    first = errors[0]
    if len(first) > ERROR_PREVIEW_LEN:
        first = first[:ERROR_PREVIEW_LEN] + "…"

    return len(errors), first


def build(src: Path, main: Path, out: Path) -> Path:
    """Compile main into out. On failure the log is kept for the human."""
    out.mkdir(parents=True, exist_ok=True)
    args = [
        LATEXMK, "-pdf", "-interaction=nonstopmode", "-halt-on-error",
        SHELL_ESCAPE, f"-outdir={out}", main.name,
    ]

    try:
        # errors="replace": latexmk output isn't guaranteed valid UTF-8
        # (font/encoding messages); undecodable bytes must not crash the
        # subprocess call itself, only the CalledProcessError path below.
        subprocess.run(
            args, cwd=src, capture_output=True,
            encoding="utf-8", errors="replace", check=True,
        )
    except FileNotFoundError:
        raise CompileError(f"{LATEXMK} is not installed") from None
    except subprocess.CalledProcessError as exc:
        (out / LOG_NAME).write_text((exc.output or "") + (exc.stderr or ""), encoding="utf-8")

        # LaTeX's own log (not latexmk's) carries the "!" error lines.
        tex_log = out / f"{main.stem}{TEX_LOG_SUFFIX}"
        count, first = _first_error(tex_log)

        if count:
            plural = "" if count == 1 else "s"
            raise CompileError(
                f"{main.name} failed to compile ({count} error{plural}); "
                f"first: {first} — see {out / LOG_NAME}"
            ) from None

        raise CompileError(f"{main.name} failed to compile; see {out / LOG_NAME}") from None

    return out / f"{main.stem}.pdf"
