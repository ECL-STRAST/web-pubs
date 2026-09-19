"""The catalog as a whole: locating, listing, creating and checking entries."""

from pathlib import Path
from urllib.parse import urlparse

from . import store
from .config import Config
from .entry import DOC_NAME, KINDS, PLACEHOLDER, PUBLICATION, THESIS, Entry, from_dict
from .errors import ConfigError, MissingField, SchemaError

CONTENT = "content"
TAXONOMY = "taxonomy/topics.yaml"
COLLECTIONS = {"thesis": "theses", "publication": "publications"}
HTTPS = "https"

STUB_SUMMARY = "Replace this line with one or two paragraphs in English.\n"


class Catalog:
    def __init__(self, cfg: Config):
        self._cfg = cfg

    def entries(self) -> list[Entry]:
        """Every entry in the catalog, newest first."""
        found = []

        for collection in COLLECTIONS.values():
            found += [store.read(d) for d in store.dirs(self._content(collection))]

        return sorted(found, key=lambda e: (-e.year, e.slug))

    def find(self, slug: str) -> Entry:
        for entry in self.entries():
            if entry.slug == slug:
                return entry

        raise MissingField(f"no entry with slug {slug}")

    def dir_for(self, entry: Entry) -> Path:
        return self._content(COLLECTIONS[entry.type]) / entry.slug

    def create(self, slug, type, year, title, authors, degree=None, kind=None,
               programme=None, supervisors=(), keywords=(), summary=STUB_SUMMARY,
               venue=None, doi=None, published=None, language="en") -> Path:
        """Scaffold a new entry folder with stubs for the human to fill in."""
        folder = self._content(COLLECTIONS[type]) / slug

        if store.dir_exists(folder):
            raise FileExistsError(f"{folder} already exists")

        data = {
            "type": type, "title": title, "authors": list(authors), "year": year,
            "topics": [PLACEHOLDER], "language": language,
        }

        for name, value in (("venue", venue), ("doi", doi), ("published", published)):
            if value is not None:
                data[name] = value

        if degree is not None:
            data["degree"] = degree

        # kind is as essential to a paper as degree is to a thesis: scaffold
        # a placeholder validate will report until the human fixes it.
        if type == PUBLICATION:
            data["kind"] = kind or PLACEHOLDER

        if programme is not None:
            data["programme"] = programme

        if supervisors:
            data["supervisors"] = list(supervisors)

        if keywords:
            data["keywords"] = list(keywords)

        store.write(folder, from_dict(slug, data))
        store.write_summary(folder, summary)

        return folder

    def save(self, entry: Entry) -> None:
        store.write(self.dir_for(entry), entry)

    def topics(self) -> set[str]:
        path = self._cfg.root / TAXONOMY

        return set(store.read_list(path))

    def problems(self) -> list[str]:
        """Every reason the catalog would not publish cleanly."""
        vocabulary = self.topics()
        found = []

        for collection in COLLECTIONS.values():
            for folder in store.dirs(self._content(collection)):
                found += self._check(folder, vocabulary)

        return found

    def _check(self, folder: Path, vocabulary: set[str]) -> list[str]:
        try:
            entry = store.read(folder)
        except (SchemaError, ConfigError) as exc:
            return [str(exc)]

        found = [
            f"{folder.name}: topic not in the vocabulary: {topic}"
            for topic in entry.topics
            if topic not in vocabulary
        ]

        if entry.kind == PLACEHOLDER:
            found.append(f"{folder.name}: kind is still {PLACEHOLDER}; pick one of {', '.join(KINDS)}")

        for name in self._required_files(entry):
            if not store.exists(folder / name):
                found.append(f"{folder.name}: missing {name}")

        for url in (*entry.repos.code, entry.repos.docs):
            if url and not _is_https_url(url):
                found.append(f"{folder.name}: malformed repo URL: {url}")

        return found

    def _required_files(self, entry: Entry) -> list[str]:
        names = [store.SUMMARY_FILE]

        # Only the thesis needs its document: a paper's citation is the
        # entry, its PDF may not be shareable.
        if entry.type == THESIS:
            names.append(DOC_NAME[entry.type])

        # Slides are optional, but a declared file must be there.
        if entry.slides:
            names.append(entry.slides)

        if entry.photo:
            names.append(entry.photo)

        if entry.image:
            names.append(entry.image)

        return names

    def _content(self, collection: str) -> Path:
        return self._cfg.root / CONTENT / collection


def _is_https_url(value: str) -> bool:
    """Well-formed absolute https:// URL. Syntax only, never reachability."""
    parsed = urlparse(value)

    return parsed.scheme == HTTPS and bool(parsed.netloc)
