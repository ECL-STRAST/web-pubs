"""The DOI registries: CrossRef first, DataCite as fallback.

Knows registries and JSON, nothing else: no Entry, no Catalog, no YAML.
The DOI shape comes from entry.py, which owns the schema.
"""

import html
import http.client
import json
import re
import urllib.request
from dataclasses import dataclass
from urllib.error import HTTPError, URLError

from .entry import DOI
from .errors import RegistryError

CROSSREF = "https://api.crossref.org/works/"
DATACITE = "https://api.datacite.org/dois/"
USER_AGENT = "tft-catalog/0.1"

# How long a registry may take to connect and to answer each read: a stalled
# registry is a broken connection, not a slow one, and must not hang the tool.
TIMEOUT_SECONDS = 10

# Sanity floor and ceiling, not a date filter: a registry year outside
# is its bug, not data to file.
MIN_YEAR, MAX_YEAR = 1000, 2100

PARAGRAPH_END = re.compile(r"</(?:p|jats:p)>\s*")
TAG = re.compile(r"<[^>]+>")
DATE_PREFIX = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


@dataclass(frozen=True)
class Record:
    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    published: str | None = None
    venue: str | None = None
    keywords: tuple[str, ...] = ()
    abstract: str | None = None
    language: str | None = None


def get_json(url: str) -> dict | None:
    """The registry's reply as parsed JSON; None for 'not found'."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None

        raise RegistryError(f"{url}: HTTP {exc.code}; try again later") from exc
    # RemoteDisconnected and friends escape urlopen unwrapped.
    except (URLError, TimeoutError, http.client.HTTPException) as exc:
        raise RegistryError(f"{url}: {exc}; check your connection") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{url}: the registry replied with malformed JSON") from exc


def fetch(doi: str, get=get_json) -> Record:
    """Everything the registries usefully say about a DOI."""
    if not DOI.fullmatch(doi):
        raise RegistryError(f"{doi!r} is not a DOI; copy it from the paper")

    found = get(CROSSREF + doi)

    if found is not None:
        return _from_crossref(found.get("message") or {})

    found = get(DATACITE + doi)

    if found is not None:
        return _from_datacite((found.get("data") or {}).get("attributes") or {})

    raise RegistryError(f"no registry knows {doi}; check the spelling")


def _pick_date(candidates: list) -> tuple[int | None, str | None]:
    """Year and precise date from the first candidate holding a sane one."""
    for candidate in candidates:
        parts = ((candidate or {}).get("date-parts") or [[]])[0]

        if not parts:
            continue

        try:
            year = int(parts[0])

            if not MIN_YEAR <= year <= MAX_YEAR:
                continue

            date = str(year)

            if len(parts) > 1:
                date += f"-{int(parts[1]):02d}"

            if len(parts) > 2:
                date += f"-{int(parts[2]):02d}"
        except (TypeError, ValueError):
            # A date-part the registry cannot name as a number is its bug, not
            # data to file: skip the candidate, as we would a year out of
            # range, rather than crash past the CLI's handler.
            continue

        return year, date

    return None, None


def _name(given: str | None, family: str | None) -> str:
    return " ".join(part for part in (given, family) if part).strip()


def _strip_markup(text: str | None) -> str | None:
    """JATS abstracts to plain markdown-ready paragraphs."""
    if not text:
        return None

    # Unescape first: an entity-encoded <script> decodes to a real tag,
    # which the strip then removes; the reverse order would smuggle it in.
    body = html.unescape(text)
    body = PARAGRAPH_END.sub("\n\n", body)
    body = TAG.sub("", body)
    paragraphs = [" ".join(line.split()) for line in body.split("\n\n")]
    out = "\n\n".join(p for p in paragraphs if p)

    return out or None


def _from_crossref(message: dict) -> Record:
    year, published = _pick_date([
        message.get("issued"),
        message.get("published-print"),
        message.get("published-online"),
        message.get("accepted"),
    ])

    authors = tuple(
        name for name in (
            _name(a.get("given"), a.get("family")) for a in message.get("author", [])
        ) if name
    )

    return Record(
        title=(message.get("title") or [None])[0],
        authors=authors,
        year=year,
        published=published,
        venue=(message.get("container-title") or [None])[0] or None,
        keywords=tuple(s for s in message.get("subject", []) if s and s.strip()),
        abstract=_strip_markup(message.get("abstract")),
        language=message.get("language"),
    )


def _datacite_name(creator: dict) -> str:
    # DataCite keeps "Family, Given"; display order is the other way round.
    family, comma, given = creator.get("name", "").partition(", ")

    if not comma:
        return family.strip()

    return f"{given.strip()} {family.strip()}".strip()


def _datacite_abstract(attributes: dict) -> str | None:
    for description in attributes.get("descriptions", []):
        if description.get("descriptionType") == "Abstract":
            return description.get("description")

    return None


def _datacite_venue(attributes: dict) -> str | None:
    # The live API answers container as a mapping, not a string; only its
    # title, if it has one, is a venue a human could read.
    container = attributes.get("container")

    if isinstance(container, str):
        return container or None

    if isinstance(container, dict):
        return container.get("containerTitle") or container.get("title") or None

    return None


def _from_datacite(attributes: dict) -> Record:
    year = attributes.get("publicationYear")
    published = None

    if isinstance(year, int) and MIN_YEAR <= year <= MAX_YEAR:
        match = DATE_PREFIX.match(attributes.get("published") or "")
        published = match.group(0) if match else str(year)
    else:
        year = None

    return Record(
        title=(attributes.get("titles") or [{}])[0].get("title"),
        authors=tuple(
            name for name in
            (_datacite_name(c) for c in attributes.get("creators", [])) if name
        ),
        year=year,
        published=published,
        venue=_datacite_venue(attributes),
        keywords=tuple(
            s["subject"] for s in attributes.get("subjects", []) if s.get("subject")
        ),
        abstract=_strip_markup(_datacite_abstract(attributes)),
        # DataCite reports "eng" where CrossRef reports "en": two vocabularies
        # in one field is worse than the add_from_doi default.
    )
