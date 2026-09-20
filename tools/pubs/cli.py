"""The command line. Knows about services, never about git or latexmk."""

import argparse
import sys
from pathlib import Path

from . import config
from .catalog import Catalog
from .entry import DEGREES, KINDS, PLACEHOLDER, THESIS
from .errors import PubsError
from .ingest import Ingest, Overrides
from .site import SITE, Site

ROOT_MARKER = "pyproject.toml"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        return args.run(args)
    except (PubsError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def find_root(start: Path) -> Path:
    """The repository root, found by walking up from start."""
    for folder in [start, *start.parents]:
        if (folder / ROOT_MARKER).is_file():
            return folder

    raise PubsError(f"no {ROOT_MARKER} above {start}")


def _catalog() -> Catalog:
    return Catalog(config.load(find_root(Path.cwd())))


def _ingest() -> Ingest:
    cfg = config.load(find_root(Path.cwd()))

    return Ingest(cfg, Catalog(cfg))


def _add_thesis(args) -> int:
    overrides = Overrides(
        title=args.title, author=args.author, year=args.year, degree=args.degree,
    )
    folder = _ingest().add(
        project_id=args.overleaf, name=args.name, overrides=overrides, type=THESIS,
    )
    print(f"created {folder}; now replace the {PLACEHOLDER} topic")

    return 0


def _add_paper(args) -> int:
    folder = _ingest().add_from_doi(doi=args.doi, name=args.name, kind=args.kind)
    print(f"created {folder}; now replace the {PLACEHOLDER} topic")

    if args.kind is None:
        print(f"and set the kind: {', '.join(KINDS)}")

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
    parser = argparse.ArgumentParser(prog="pubs", description="Catalog tooling")
    subs = parser.add_subparsers(dest="command", required=True)

    add = subs.add_parser("add", help="add an entry")
    added = add.add_subparsers(dest="what", required=True)

    thesis = added.add_parser("thesis", help="add a thesis from an Overleaf project")
    thesis.add_argument("--overleaf", required=True, metavar="ID", help="Overleaf project id")
    thesis.add_argument("--name", required=True, help="slug without the year, e.g. surname-topic")
    thesis.add_argument("--title", default=None, help="override the extracted title")
    thesis.add_argument("--author", default=None, help="override the extracted author")
    thesis.add_argument("--year", default=None, type=int, help="override the extracted year")
    thesis.add_argument("--degree", default=None, choices=DEGREES,
                        help="override the extracted degree")
    thesis.set_defaults(run=_add_thesis)

    paper = added.add_parser("paper", help="add a paper from its DOI")
    paper.add_argument("--doi", required=True, metavar="DOI", help="the paper's DOI")
    paper.add_argument("--name", required=True, help="slug without the year, e.g. surname-topic")
    paper.add_argument("--kind", default=None, choices=KINDS,
                       help=f"what the paper is; scaffolded as {PLACEHOLDER} otherwise")
    paper.set_defaults(run=_add_paper)

    sync = subs.add_parser("sync", help="re-pull and recompile an entry")
    sync.add_argument("slug")
    sync.set_defaults(run=_sync)

    validate = subs.add_parser("validate", help="check every entry")
    validate.set_defaults(run=_validate)

    build = subs.add_parser("build", help="render the static site")
    build.add_argument("--out", default=None, help="output directory (default: site/)")
    build.set_defaults(run=_build)

    return parser
