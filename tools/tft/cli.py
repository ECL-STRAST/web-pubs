"""The command line. Knows about services, never about git or latexmk."""

import argparse
import sys
from pathlib import Path

from . import config
from .catalog import Catalog
from .entry import DEGREES, PUBLICATION, THESIS, TYPES
from .errors import TftError
from .ingest import Ingest, Overrides
from .site import SITE, Site

ROOT_MARKER = "pyproject.toml"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        return args.run(args)
    except (TftError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def find_root(start: Path) -> Path:
    """The repository root, found by walking up from start."""
    for folder in [start, *start.parents]:
        if (folder / ROOT_MARKER).is_file():
            return folder

    raise TftError(f"no {ROOT_MARKER} above {start}")


def _catalog() -> Catalog:
    return Catalog(config.load(find_root(Path.cwd())))


def _ingest() -> Ingest:
    cfg = config.load(find_root(Path.cwd()))

    return Ingest(cfg, Catalog(cfg))


def _add(args) -> int:
    if args.doi is not None:
        if args.type not in (None, PUBLICATION):
            raise TftError("a DOI is not a thesis; --doi implies --type publication")

        folder = _ingest().add_from_doi(doi=args.doi, name=args.name)
    else:
        overrides = Overrides(
            title=args.title, author=args.author, year=args.year, degree=args.degree,
        )
        folder = _ingest().add(
            project_id=args.overleaf, name=args.name,
            overrides=overrides, type=args.type or THESIS,
        )

    print(f"created {folder}; now replace the CHANGE-ME topic")

    return 0


def _sync(args) -> int:
    result = _ingest().sync(args.slug)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    print(f"{args.slug}: {'updated' if result.changed else 'unchanged'}")

    return 0


def _build(args) -> int:
    root = find_root(Path.cwd())
    cfg = config.load(root)
    out = Path(args.out) if args.out else root / SITE

    Site(cfg, Catalog(cfg)).build(out)
    print(f"built {out}")

    return 0


def _validate(args) -> int:
    problems = _catalog().problems()

    for problem in problems:
        print(problem)

    if problems:
        return 1

    print("ok")

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tft", description="Catalog tooling")
    subs = parser.add_subparsers(dest="command", required=True)

    add = subs.add_parser("add", help="add an entry from an Overleaf project or a DOI")
    src = add.add_mutually_exclusive_group(required=True)
    src.add_argument("--overleaf", metavar="ID", help="Overleaf project id")
    src.add_argument("--doi", metavar="DOI", help="create a publication from its DOI")
    add.add_argument("--name", required=True, help="slug without the year, e.g. surname-topic")
    add.add_argument("--title", default=None, help="override the extracted title")
    add.add_argument("--author", default=None, help="override the extracted author")
    add.add_argument("--year", default=None, type=int, help="override the extracted year")
    add.add_argument("--degree", default=None, choices=DEGREES,
                     help="override the extracted degree")
    add.add_argument("--type", default=None, choices=TYPES)
    add.set_defaults(run=_add)

    sync = subs.add_parser("sync", help="re-pull and recompile an entry")
    sync.add_argument("slug")
    sync.set_defaults(run=_sync)

    validate = subs.add_parser("validate", help="check every entry")
    validate.set_defaults(run=_validate)

    build = subs.add_parser("build", help="render the static site")
    build.add_argument("--out", default=None, help="output directory (default: site/)")
    build.set_defaults(run=_build)

    return parser
