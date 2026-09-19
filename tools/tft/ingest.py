"""Brings an Overleaf project into the catalog: fetch, compile, mirror."""

import dataclasses
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import latex, overleaf, store, tex
from .catalog import COLLECTIONS, STUB_SUMMARY, Catalog
from .doi import fetch as fetch_registry
from .config import Config
from .entry import DOC_NAME, PUBLICATION, THESIS, Entry, Overleaf
from .errors import ExtractError

SOURCES = "sources"

# Everything an entry cannot be created without, per type. A publication
# has no cover phrase, no abstract chapter: only the CLI flags apply.
REQUIRED_BY_TYPE = {
    THESIS: ("title", "author", "year", "degree", "abstract", "keywords"),
    PUBLICATION: ("title", "author", "year"),
}


@dataclass(frozen=True)
class Overrides:
    """What the human supplies when the source does not declare it."""
    title: str | None = None
    author: str | None = None
    year: int | None = None
    degree: str | None = None


@dataclass(frozen=True)
class SyncResult:
    """What a sync did, and anything the human should look at."""
    changed: bool
    warnings: tuple[str, ...] = ()


class Ingest:
    def __init__(self, cfg: Config, catalog: Catalog, fetch=overleaf.fetch,
                 build=latex.build, fetch_doi=fetch_registry):
        self._cfg = cfg
        self._catalog = catalog
        self._fetch = fetch
        self._build = build
        self._fetch_doi = fetch_doi

    def add(self, project_id, name, overrides=Overrides(), type=THESIS) -> Path:
        """Create a new entry from an Overleaf project."""
        work = self._cfg.work / project_id
        sha = self._fetch(project_id, work)

        # Read metadata before compiling: a missing field costs seconds,
        # a LaTeX run costs a minute.
        meta = self._meta(work, overrides, type)
        pdf = self._compile(work, main=None)

        slug = f"{meta.year}-{name}"
        folder = self._catalog.create(
            slug=slug, type=type, year=meta.year, title=meta.title,
            authors=(meta.author,), degree=_degree_for(type, meta),
            programme=meta.programme, supervisors=meta.supervisors,
            keywords=meta.keywords, summary=meta.abstract or STUB_SUMMARY,
        )
        entry = self._catalog.find(slug)

        self._install(entry, folder, pdf, work, sha, project_id)

        return folder

    def sync(self, slug: str) -> SyncResult:
        """Refresh an entry from its source, Overleaf or the DOI registries."""
        entry = self._catalog.find(slug)

        if entry.overleaf is not None:
            return self._sync_overleaf(entry)

        if entry.doi is not None:
            return self._sync_doi(entry)

        raise FileNotFoundError(f"{slug} has neither overleaf.project_id nor doi to sync")

    def _sync_overleaf(self, entry: Entry) -> SyncResult:
        project_id = entry.overleaf.project_id
        work = self._cfg.work / project_id
        sha = self._fetch(project_id, work)

        if sha == entry.overleaf.commit:
            return SyncResult(changed=False)

        meta = self._meta(work, Overrides(), entry.type)
        pdf = self._compile(work, entry.overleaf.main)
        folder = self._catalog.dir_for(entry)

        refreshed = dataclasses.replace(
            entry, title=meta.title, authors=(meta.author,), year=meta.year,
            degree=_degree_for(entry.type, meta), programme=meta.programme,
            supervisors=meta.supervisors, keywords=meta.keywords,
        )
        self._install(refreshed, folder, pdf, work, sha, project_id)

        # summary.md is derived from the abstract; a publication has none,
        # so its hand-written summary is left alone. Rewritten only once
        # _install succeeds, so a failure leaves it untouched.
        if meta.abstract:
            store.write_summary(folder, meta.abstract)

        return SyncResult(changed=True, warnings=_year_drift(entry.year, meta.year, entry.slug))

    def add_from_doi(self, doi: str, name: str) -> Path:
        """Create a publication entry from the registries alone: no compile,
        no mirror, no PDF. What is shareable is a human call."""
        record = self._fetch_doi(doi)

        if record.year is None:
            raise ExtractError(f"{doi}: the registry reports no year; the slug needs one")

        return self._catalog.create(
            slug=f"{record.year}-{name}", type=PUBLICATION, year=record.year,
            title=record.title, authors=record.authors, venue=record.venue,
            doi=doi, published=record.published, keywords=record.keywords,
            language=record.language or "en",
            summary=record.abstract or STUB_SUMMARY,
        )

    def _sync_doi(self, entry: Entry) -> SyncResult:
        record = self._fetch_doi(entry.doi)
        refreshed = dataclasses.replace(
            entry,
            title=record.title or entry.title,
            authors=record.authors or entry.authors,
            year=record.year or entry.year,
            venue=record.venue or entry.venue,
            keywords=record.keywords or entry.keywords,
            published=record.published or entry.published,
        )
        changed = any(
            getattr(refreshed, name) != getattr(entry, name)
            for name in REGISTRY_FIELDS
        )

        if changed:
            self._catalog.save(refreshed)

        return SyncResult(
            changed=changed,
            warnings=_year_drift(entry.year, refreshed.year, entry.slug),
        )

    def _compile(self, work: Path, main: str | None) -> Path:
        root = work / main if main else latex.find_main(work)

        return self._build(work, root, self._cfg.work / "out")

    def _meta(self, work: Path, overrides: Overrides, type: str) -> tex.Meta:
        """Source metadata with the human's overrides laid on top."""
        found = tex.read(work)
        supplied = {
            name: value
            for name, value in dataclasses.asdict(overrides).items()
            if value is not None
        }
        meta = dataclasses.replace(found, **supplied)
        missing = [name for name in REQUIRED_BY_TYPE[type] if not getattr(meta, name)]

        if missing:
            raise ExtractError(f"could not read {', '.join(missing)}; {_remedy(missing)}")

        return meta

    def _install(self, entry: Entry, folder: Path, pdf: Path, work: Path, sha, project_id) -> None:
        """Everything that must only happen once the compile has succeeded."""
        # Mirror first: it is the likeliest step to fail (missing private
        # repo, rmtree of the old mirror). Failing here must not leave the
        # public PDF and entry.yaml disagreeing about which commit built it.
        mirror = self._mirror(entry, work)

        target = folder / DOC_NAME[entry.type]
        tmp = target.with_name(target.name + ".tmp")

        # Remove the partial temp file on a failed copy (disk full,
        # interrupted): the live PDF must stay untouched either way.
        try:
            shutil.copyfile(pdf, tmp)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        os.replace(tmp, target)
        updated = dataclasses.replace(
            entry,
            overleaf=Overleaf(
                project_id=project_id,
                commit=sha,
                main=entry.overleaf.main if entry.overleaf else None,
                mirror=mirror,
            ),
        )

        self._catalog.save(updated)

    def _mirror(self, entry: Entry, work: Path) -> str:
        """Copy the sources into the private repo, minus git's bookkeeping."""
        collection = COLLECTIONS[entry.type]
        dest = self._cfg.private / SOURCES / collection / entry.slug

        if dest.exists():
            shutil.rmtree(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, dest, ignore=shutil.ignore_patterns(".git"))

        return f"{self._cfg.mirror_base}/{collection}/{entry.slug}"


# Fields the CLI can supply; the rest must be fixed in the LaTeX itself.
OVERRIDABLE = ("title", "author", "year", "degree")


# A registry that loses a field must not blank the entry: only what it
# reports wins.
REGISTRY_FIELDS = ("title", "authors", "year", "venue", "keywords", "published")


def _degree_for(type: str, meta: tex.Meta) -> str | None:
    """A publication never has a degree, even if a cover phrase leaked in."""
    return meta.degree if type == THESIS else None


def _year_drift(was: int, now: int, slug: str) -> tuple[str, ...]:
    """The slug embeds the year, but renaming would break shared URLs."""
    if was == now:
        return ()

    return (f"{slug}: year is now {now}; the folder name still says {was}",)


def _remedy(missing: list[str]) -> str:
    """What the human can do about each field that could not be read."""
    flags = [f"--{name}" for name in missing if name in OVERRIDABLE]

    if not flags:
        return "fix the thesis source"

    return f"pass {' '.join(flags)}"
