"""Renders the catalog into a static site."""

import json
import shutil
from importlib import resources
from pathlib import Path

import markdown
from jinja2 import Environment, PackageLoader, select_autoescape

from . import store
from .catalog import Catalog
from .config import Config
from .entry import DOI_BASE, DOC_NAME, PLACEHOLDER, PUBLICATION, THESIS, Entry, parse_video
from .errors import BadValue, UnsafeOutputDir

SITE = "site"
INDEX_JSON = "index.json"
ENTRIES = "entries"
ASSETS = "assets"

SUMMARY_LIMIT = 300

# Spanish connectives stay lowercase inside a programme name, except
# when the name starts with one.
MINOR_WORDS = ("en", "de", "del", "la", "el", "los", "las", "y", "e")


def titlecase(text: str) -> str:
    """'GRADO EN INGENIERÍA BIOMÉDICA' -> 'Grado en Ingeniería Biomédica'."""
    words = [word.lower() for word in text.split()]

    if not words:
        return ""

    rest = [word if word in MINOR_WORDS else word.capitalize() for word in words[1:]]

    return " ".join([words[0].capitalize(), *rest])


def record(entry: Entry, has_doc: bool) -> dict:
    """The flat shape the client-side filter works with."""
    base = f"{ENTRIES}/{entry.slug}"

    return {
        "slug": entry.slug,
        "type": entry.type,
        "title": entry.title,
        "authors": list(entry.authors),
        "year": entry.year,
        "degree": entry.degree,
        "kind": entry.kind,
        "programme": entry.programme,
        "venue": entry.venue,
        "doi": f"{DOI_BASE}{entry.doi}" if entry.doi else None,
        "published": entry.published,
        "language": entry.language,
        "topics": list(entry.topics),
        "supervisors": list(entry.supervisors),
        "keywords": list(entry.keywords),
        "score": entry.score,
        "honours": entry.honours,
        "url": f"{base}/",
        "doc": f"{base}/{DOC_NAME[entry.type]}" if has_doc else None,
        "slides": f"{base}/{entry.slides}" if entry.slides else None,
        "has_code": bool(entry.repos.code),
        "has_slides": bool(entry.slides),
        "summary": _teaser(entry.summary),
    }


class Site:
    def __init__(self, cfg: Config, catalog: Catalog):
        self._cfg = cfg
        self._catalog = catalog
        self._jinja = Environment(
            loader=PackageLoader("pubs", "templates"),
            autoescape=select_autoescape(["html"]),
        )
        self._jinja.filters["titlecase"] = titlecase

    def build(self, out: Path) -> None:
        """Render everything. The output directory is rebuilt from scratch."""
        entries = self._catalog.entries()
        self._verify_files(entries)

        if out.exists():
            self._require_previous_build(out)
            shutil.rmtree(out)

        out.mkdir(parents=True)

        self._write_index(out, entries)
        self._write_assets(out)

        for entry in entries:
            self._write_entry(out, entry)

    def _require_previous_build(self, out: Path) -> None:
        """Refuse to wipe a directory unless it looks like a prior build."""
        if not (out / INDEX_JSON).is_file():
            raise UnsafeOutputDir(f"{out} exists and is not a previous build; remove it yourself")

    def _verify_files(self, entries: list[Entry]) -> None:
        """Confirm every file a build would copy exists, before out is wiped."""
        for entry in entries:
            source = self._catalog.dir_for(entry)
            doc = DOC_NAME[entry.type]

            # A thesis must carry its document; a paper may omit the PDF.
            if entry.type == THESIS or store.exists(source / doc):
                self._require(source, doc, entry.slug)

            if entry.slides:
                self._require(source, entry.slides, entry.slug)

            if entry.photo:
                self._require(source, entry.photo, entry.slug)

            if entry.image:
                self._require(source, entry.image, entry.slug)

    def _require(self, source: Path, name: str, slug: str) -> None:
        if not store.exists(source / name):
            raise BadValue(f"{slug}: missing {name}")

    def _write_index(self, out: Path, entries: list[Entry]) -> None:
        records = [
            record(e, store.exists(self._catalog.dir_for(e) / DOC_NAME[e.type]))
            for e in entries
        ]
        (out / INDEX_JSON).write_text(
            json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8",
        )

        page = self._jinja.get_template("index.html").render(
            entries=entries,
            years=sorted({e.year for e in entries}, reverse=True),
            degrees=sorted({e.degree for e in entries if e.degree}),
            # The placeholder is a to-do, not a facet: never a filter option.
            kinds=sorted({e.kind for e in entries if e.kind and e.kind != PLACEHOLDER}),
            topics=sorted({t for e in entries for t in e.topics}),
            n_theses=sum(e.type == THESIS for e in entries),
            n_publications=sum(e.type == PUBLICATION for e in entries),
        )
        (out / "index.html").write_text(page, encoding="utf-8")

    def _write_entry(self, out: Path, entry: Entry) -> None:
        folder = out / ENTRIES / entry.slug
        folder.mkdir(parents=True)

        source = self._catalog.dir_for(entry)
        doc = DOC_NAME[entry.type]
        has_doc = store.exists(source / doc)

        if has_doc:
            shutil.copyfile(source / doc, folder / doc)

        if entry.slides:
            shutil.copyfile(source / entry.slides, folder / entry.slides)

        if entry.photo:
            shutil.copyfile(source / entry.photo, folder / entry.photo)

        if entry.image:
            shutil.copyfile(source / entry.image, folder / entry.image)

        page = self._jinja.get_template("entry.html").render(
            entry=entry, doc=doc if has_doc else None, video=parse_video(entry.video),
            doi_url=f"{DOI_BASE}{entry.doi}" if entry.doi else None,
            summary=markdown.markdown(entry.summary),
        )
        (folder / "index.html").write_text(page, encoding="utf-8")

    def _write_assets(self, out: Path) -> None:
        """Copied verbatim: assets are not templates and must not be rendered."""
        source = resources.files("pubs") / ASSETS
        dest = out / ASSETS
        dest.mkdir()

        for asset in source.iterdir():
            shutil.copyfile(asset, dest / asset.name)


def _teaser(summary: str) -> str:
    """The summary's first paragraph as plain text, for the index."""
    first = summary.strip().split("\n\n")[0]
    plain = first.replace("*", "").replace("`", "").replace("\n", " ").strip()

    return plain if len(plain) <= SUMMARY_LIMIT else plain[:SUMMARY_LIMIT].rstrip() + "..."
