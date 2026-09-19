# Papers from DOI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catalog scientific papers from their DOI: `tft add --doi <doi>` fills title, ordered authors, year, venue, keywords and abstract from CrossRef/DataCite, and papers without shareable PDFs are listed by citation alone.

**Architecture:** A new driver module `doi.py` (same layer as `tex.py`/`overleaf.py`) turns registry JSON into a flat `Record`; `ingest` maps it onto the existing `Catalog.create`; the schema gains `authors` (replacing `author` everywhere), `doi` and `published`. Publications no longer require `paper.pdf`: file presence, not a flag, is the clearance.

**Tech Stack:** Python 3.11 (stdlib `urllib` only, no new dependencies), PyYAML, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-papers-from-doi-design.md` — read it before starting; it carries every decision and the rationale.

## Global Constraints

- Python >= 3.11 (from `pyproject.toml`); no new third-party dependencies — network calls use stdlib `urllib`.
- Validation is syntax only; reachability is never checked (CI holds no secrets).
- Code and comments in English; user-facing prose minimal (repo `AGENTS.md`).
- Commit style: imperative mood, subject <= 50 chars, no trailing period (matches `git log`).
- Layering: `cli -> ingest -> (tex | overleaf | doi)`; `doi.py` knows registries and JSON only — no `Entry`, no `Catalog`, no YAML. It may import the `DOI` regex from `entry.py` (schema owner, no cycle).
- Run tests from the repo root with the venv: `.venv/bin/python -m pytest <file> -v`.

---

### Task 1: `author` becomes `authors` everywhere

One atomic rename: the schema, its consumers, the 2 existing entries. The old field is rejected outright (no migration shim) — an old-style `entry.yaml` fails `validate` loudly.

**Files:**
- Modify: `tools/tft/entry.py` (MANDATORY L38, TEXT_FIELDS L47, `Entry.author` L80, `from_dict` L133, `to_dict` L160)
- Modify: `tools/tft/catalog.py` (`create` L42-51)
- Modify: `tools/tft/ingest.py` (`add` L59-64, `sync` L89-93)
- Modify: `tools/tft/site.py` (`record` L49)
- Modify: `tools/tft/templates/entry.html` (L20, L25)
- Modify: `tools/tft/assets/app.js` (L27, L47)
- Modify: `tests/test_entry.py`, `tests/test_cli.py`, `tests/test_catalog.py`, `tests/test_site.py`, `tests/test_ingest.py` (fixtures + assertions)
- Modify: `content/theses/2026-duran-lopez-motion-capture-lib/entry.yaml`, `content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `Entry.authors: tuple[str, ...]`; `entry.yaml` key `authors: [str]` mandatory for both types; `catalog.create(slug, type, year, title, authors, degree=None, ...)`; `site.record` key `"authors": [str]` (key `"author"` is gone); app.js reads `e.authors`.

- [ ] **Step 1: Rewrite `tests/test_entry.py` for `authors` and add the new tests**

In the fixture at the top, replace `"author": "Silvia Nieves Serrano",` with:

```python
    "authors": ["Silvia Nieves Serrano"],
```

In the parametrized list of mandatory fields (L51), replace `"author"` with `"authors"`. Append at the end of the file:

```python
def test_authors_must_be_a_non_empty_list():
    data = {k: v for k, v in MINIMAL.items() if k != "authors"} | {"authors": []}

    with pytest.raises(BadValue, match="authors"):
        entry.from_dict("2027-x", data)


def test_authors_must_be_non_empty_strings():
    data = {k: v for k, v in MINIMAL.items() if k != "authors"} | {"authors": ["ok", " "]}

    with pytest.raises(BadValue, match="authors"):
        entry.from_dict("2027-x", data)


def test_authors_order_survives_the_round_trip():
    data = {k: v for k, v in MINIMAL.items() if k != "authors"} | {
        "authors": ["X. Garcia", "Y. Sanchez", "B. Gomez"]
    }
    parsed = entry.from_dict("2027-x", data)

    assert parsed.authors == ("X. Garcia", "Y. Sanchez", "B. Gomez")
    assert entry.to_dict(parsed) == data


def test_the_old_single_author_field_is_rejected():
    with pytest.raises(UnknownField, match="unknown field: author"):
        entry.from_dict("2027-x", MINIMAL | {"author": "Silvia Nieves Serrano"})
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_entry.py -v`
Expected: FAIL (`authors` rejected as unknown / mandatory missing).

- [ ] **Step 3: Rename in `entry.py`**

- `MANDATORY = ("type", "title", "authors", "year", "topics", "language")`
- `TEXT_FIELDS = ("title", "language")` (drop `"author"`)
- In `Entry`: replace `author: str` with `authors: tuple[str, ...]` (keep its position after `title`).
- In `from_dict`: replace `author=data["author"],` with `authors=tuple(data["authors"]),`; call `_check_authors(data)` next to `_check_types`.
- In `to_dict`: replace `"author": entry.author,` with `"authors": list(entry.authors),` (same position, after `"title"`).
- Add the check next to `_check_keywords`, same care as supervisors:

```python
def _check_authors(data: dict) -> None:
    if not isinstance(data["authors"], list) or not data["authors"]:
        raise BadValue("authors must be a non-empty list")

    for name in data["authors"]:
        if not isinstance(name, str) or not name.strip():
            raise BadValue("authors must be non-empty strings")
```

- [ ] **Step 4: Run `test_entry.py`, verify it passes**

Run: `.venv/bin/python -m pytest tests/test_entry.py -v`
Expected: PASS.

- [ ] **Step 5: Rename in the consumers**

`catalog.py` `create`: parameter `author` -> `authors`; in the data dict replace `"author": author` with `"authors": list(authors)`.

`ingest.py`: a thesis source declares one author (`tex.Meta.author` stays `str`); the ingest wraps it. In `add`, replace `author=meta.author,` with `authors=(meta.author,),`. In `sync`, replace `author=meta.author,` inside `dataclasses.replace` with `authors=(meta.author,),`.

`site.py` `record`: replace `"author": entry.author,` with `"authors": list(entry.authors),`.

`templates/entry.html`: both occurrences of `{{ entry.author }}` become `{{ entry.authors|join(", ") }}` (the portrait `alt` at L20 and the meta line at L25).

`assets/app.js`: haystack (L27) `e.author` -> `e.authors.join(" ")`; card meta (L47) `escape(e.author)` -> `escape(e.authors.join(", "))`.

- [ ] **Step 6: Update the remaining test fixtures and assertions**

- `tests/test_cli.py` MINIMAL (L9): `"author":` -> `"authors": ["Silvia Nieves Serrano"],`. The `Overrides.author` assertions (L128) do NOT change — `--author` remains a LaTeX-level flag.
- `tests/test_catalog.py` MINIMAL (L11): same replacement. `create` calls (L70-74, L84-87): `author="Unknown"` -> `authors=["Unknown"]`, `author="a"` -> `authors=["a"]`.
- `tests/test_site.py` MINIMAL (L14): same replacement. `test_accents_survive_round_trip`: `FULL | {"author": name}` -> `FULL | {"authors": [name]}`. The golden record (L73-93): replace `"author": "Silvia Nieves Serrano",` with `"authors": ["Silvia Nieves Serrano"],`.
- `tests/test_app_js.py` MINIMAL (L16): same replacement.
- `tests/test_ingest.py`: L88 `data["author"] == ...` -> `data["authors"] == ["Silvia Nieves Serrano"]`; L173 -> `data["authors"] == ["A"]`. `Overrides(... author=...)` calls do NOT change.

- [ ] **Step 7: Run the whole suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS everywhere except none — the rename is complete once the suite is green.

- [ ] **Step 8: Migrate the two live entries**

In `content/theses/2026-duran-lopez-motion-capture-lib/entry.yaml` and `content/theses/2026-gomez-martinez-biomechanics-viz/entry.yaml`, replace the line `author: <name>` with `authors:` newline `  - <name>` (same position, after `title`).

Run: `.venv/bin/python -m tft.cli validate` (or `.venv/bin/tft validate`)
Expected: `ok`.

- [ ] **Step 9: Commit**

```bash
git add tools tests content
git commit -m "Make authors a list on every entry"
```

---

### Task 2: `doi` and `published` fields

**Files:**
- Modify: `tools/tft/entry.py` (OPTIONAL L39-43, `Entry`, `from_dict`, `to_dict`)
- Test: `tests/test_entry.py`

**Interfaces:**
- Consumes: Task 1's schema.
- Produces: `Entry.doi: str | None`, `Entry.published: str | None`; module constants `entry.DOI` (compiled regex, full form), `entry.DOI_BASE = "https://doi.org/"`, `entry.PUBLISHED` (compiled regex); `entry.yaml` keys `doi`, `published` optional.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entry.py`:

```python
def test_doi_and_published_round_trip():
    data = MINIMAL | {"doi": "10.1109/TVCG.2026.1234567", "published": "2026-03-14"}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.doi == "10.1109/TVCG.2026.1234567"
    assert parsed.published == "2026-03-14"
    assert entry.to_dict(parsed) == data


def test_absent_doi_and_published_are_none():
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.doi is None
    assert parsed.published is None


@pytest.mark.parametrize("doi", [
    "https://doi.org/10.1109/TVCG.2026",
    "10.11/suffix",
    "DOI:10.1109/TVCG.2026",
    "10.1109/su ffix",
    "  ",
])
def test_doi_rejects_anything_but_the_bare_form(doi):
    with pytest.raises(BadValue, match="doi"):
        entry.from_dict("2027-x", MINIMAL | {"doi": doi})


@pytest.mark.parametrize("doi", ["10.1109/TVCG.2026.1234567", "10.12345/a"])
def test_doi_accepts_the_bare_form(doi):
    assert entry.from_dict("2027-x", MINIMAL | {"doi": doi}).doi == doi


@pytest.mark.parametrize("published", ["2026", "2026-03", "2026-03-14"])
def test_published_accepts_the_three_lengths(published):
    assert entry.from_dict("2027-x", MINIMAL | {"published": published}).published == published


@pytest.mark.parametrize("published", ["2026/03", "2026-13", "2026-03-14T00:00", "March 2026", "  "])
def test_published_rejects_anything_else(published):
    with pytest.raises(BadValue, match="published"):
        entry.from_dict("2027-x", MINIMAL | {"published": published})
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_entry.py -v`
Expected: FAIL — `unknown field: doi`.

- [ ] **Step 3: Implement in `entry.py`**

Constants next to the other patterns (near `GITHUB_URL`):

```python
# The bare registrant form only; the resolved URL is built at render time.
DOI = re.compile(r"10\.\d{4,}/\S+")
DOI_BASE = "https://doi.org/"

PUBLISHED = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
```

`OPTIONAL` gains `"doi", "published"` (append to the tuple; `venue` is already there). `Entry` gains, after `venue`:

```python
    doi: str | None = None
    published: str | None = None
```

`from_dict`: add `doi=data.get("doi"), published=data.get("published"),` next to `venue=...`, and call `_check_doi(data)` and `_check_published(data)` next to `_check_text(data, "programme")`. `to_dict`: `_put(out, "doi", entry.doi)` and `_put(out, "published", entry.published)` right after `venue`.

```python
def _check_doi(data: dict) -> None:
    _check_text(data, "doi")

    if data.get("doi") is not None and not DOI.fullmatch(data["doi"]):
        raise BadValue(f"doi must look like 10.NNNN/suffix, got {data['doi']!r}")


def _check_published(data: dict) -> None:
    _check_text(data, "published")

    if data.get("published") is not None and not PUBLISHED.fullmatch(data["published"]):
        raise BadValue(f"published must be YYYY, YYYY-MM or YYYY-MM-DD, got {data['published']!r}")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_entry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/tft/entry.py tests/test_entry.py
git commit -m "Add doi and published fields"
```

---

### Task 3: A publication without `paper.pdf` is valid

**Files:**
- Modify: `tools/tft/catalog.py` (`_required_files` L113-126, import `THESIS`)
- Modify: `tools/tft/site.py` (`record` signature, `_verify_files`, `_write_index`, `_write_entry`)
- Test: `tests/test_catalog.py`, `tests/test_site.py`

**Interfaces:**
- Consumes: Tasks 1-2 (`authors`, `DOI_BASE`).
- Produces: `catalog._required_files` requires the doc only for theses; `site.record(entry, has_doc: bool)` where `record["doc"]` is `None` when the PDF is absent; `Site.build` copies `paper.pdf` only when present.

- [ ] **Step 1: Write the failing catalog tests**

Append to `tests/test_catalog.py` (its `MINIMAL` is thesis-shaped; a publication fixture drops `degree`):

```python
PAPER = {
    "type": "publication",
    "title": "Motion capture in the wild",
    "authors": ["A. Autor", "B. Autor"],
    "year": 2026,
    "topics": ["vr"],
    "language": "en",
    "venue": "IEEE TVCG",
    "doi": "10.1109/TVCG.2026.1234567",
}


def _publication(repo, slug, data=None, summary="Text.\n", pdf=False):
    folder = repo / "content" / "publications" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(data or PAPER, sort_keys=False))
    (folder / "summary.md").write_text(summary)

    if pdf:
        (folder / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    return folder


def test_publication_without_a_pdf_is_no_problem(repo):
    _publication(repo, "2026-x")

    assert _catalog(repo).problems() == []


def test_publication_with_a_pdf_on_disk_is_no_problem(repo):
    _publication(repo, "2026-x", pdf=True)

    assert _catalog(repo).problems() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `missing paper.pdf`.

- [ ] **Step 3: Implement `catalog._required_files`**

`from .entry import DOC_NAME, THESIS, Entry, from_dict`. Replace the first line of `_required_files`:

```python
    def _required_files(self, entry: Entry) -> list[str]:
        names = [store.SUMMARY_FILE]

        # Only the thesis needs its document: a paper's citation is the
        # entry, its PDF may not be shareable.
        if entry.type == THESIS:
            names.append(DOC_NAME[entry.type])
```

(the slides/photo/image block stays exactly as it was).

- [ ] **Step 4: Run catalog tests, verify pass**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing site tests**

Append to `tests/test_site.py` (reuses its `repo` fixture; the publication helper below writes into the publications collection):

```python
PAPER = {
    "type": "publication",
    "title": "Motion capture in the wild",
    "authors": ["A. Autor", "B. Autor"],
    "year": 2026,
    "topics": ["biomechanics"],
    "language": "en",
    "venue": "IEEE TVCG",
    "doi": "10.1109/TVCG.2026.1234567",
}


def _publication(repo, slug="2026-x", pdf=False):
    folder = repo / "content" / "publications" / slug
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump(PAPER, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")

    if pdf:
        (folder / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    return folder


def test_publication_without_a_pdf_builds_and_has_no_doc(repo):
    _publication(repo)

    record = json.loads((_build(repo) / "index.json").read_text())[0]

    assert record["doc"] is None


def test_publication_with_a_pdf_copies_it(repo):
    _publication(repo, pdf=True)

    out = _build(repo)

    assert (out / "entries" / "2026-x" / "paper.pdf").read_bytes().startswith(b"%PDF")
    assert json.loads((out / "index.json").read_text())[0]["doc"] == "entries/2026-x/paper.pdf"
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_site.py -v`
Expected: FAIL (`record` still has `"author"`, missing keys; build raises `BadValue: missing paper.pdf`).

- [ ] **Step 7: Implement in `site.py`**

`from .entry import DOI_BASE, DOC_NAME, Entry, parse_video` and add `from .entry import THESIS` is NOT needed — presence drives it. Replace `record` and the three touched methods:

```python
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
```

Note: this is also where the golden record test from Task 1 (`test_index_json_matches_the_golden_record`) gains `venue`, `doi`, `published` keys — update it now, expected keys for the thesis become: slug, type, title, authors, year, degree, programme, venue (None), doi (None), published (None), language, topics, supervisors, keywords, score, honours, url, doc, slides, has_code, has_slides, summary.

`_verify_files`: add `THESIS` to the `.entry` import; replace the doc requirement line with

```python
        for entry in entries:
            source = self._catalog.dir_for(entry)
            doc = DOC_NAME[entry.type]

            # A thesis must carry its document; a paper may omit the PDF.
            if entry.type == THESIS or store.exists(source / doc):
                self._require(source, doc, entry.slug)
```

(import `THESIS` from `.entry` in the import line above.)

`_write_index` first line becomes:

```python
        records = [
            record(e, store.exists(self._catalog.dir_for(e) / DOC_NAME[e.type]))
            for e in entries
        ]
```

`_write_entry` doc handling becomes:

```python
        doc = DOC_NAME[entry.type]
        has_doc = store.exists(source / doc)

        if has_doc:
            shutil.copyfile(source / doc, folder / doc)
```

and the render call passes `doc=doc if has_doc else None`.

- [ ] **Step 8: Run the full suite, verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS (thesis behaviour unchanged everywhere).

- [ ] **Step 9: Commit**

```bash
git add tools/tft/catalog.py tools/tft/site.py tests
git commit -m "Let publications omit paper.pdf"
```

---

### Task 4: The DOI driver `doi.py`

**Files:**
- Create: `tools/tft/doi.py`
- Modify: `tools/tft/errors.py` (append one class)
- Create: `tests/test_doi.py`

**Interfaces:**
- Consumes: `entry.DOI` (regex) from Task 2.
- Produces: `doi.Record` — frozen dataclass `(title: str | None, authors: tuple[str, ...], year: int | None, published: str | None, venue: str | None, keywords: tuple[str, ...], abstract: str | None, language: str | None)`; `doi.fetch(doi: str, get=doi.get_json) -> Record`; `doi.get_json(url) -> dict | None` (`None` = 404); `errors.RegistryError(TftError)`.

- [ ] **Step 1: Add the error class**

Append to `tools/tft/errors.py`:

```python
class RegistryError(TftError):
    """A DOI lookup failed: malformed DOI, unknown to both registries, or the network."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_doi.py`:

```python
import pytest

from tft.doi import CROSSREF, DATACITE, fetch
from tft.errors import RegistryError

CROSSREF_URL = CROSSREF + "10.1109/TVCG.2026.1234567"
DATACITE_URL = DATACITE + "10.1109/TVCG.2026.1234567"

CROSSREF_REPLY = {"message": {
    "title": ["Motion capture in the wild"],
    "author": [
        {"given": "Ana", "family": "Pérez", "sequence": "first",
         "orcid": "0000-0002-1825-0097"},
        {"given": "Bea", "family": "Gómez"},
    ],
    "issued": {"date-parts": [[2026, 3, 14]]},
    "container-title": ["IEEE TVCG"],
    "subject": ["motion capture", "vr"],
    "abstract": ("<jats:abstract><jats:p>Two para.</jats:p>"
                 "<jats:p>Second &amp; final.</jats:p></jats:abstract>"),
    "language": "en",
}}

DATACITE_REPLY = {"data": {"attributes": {
    "titles": [{"title": "A preprint"}],
    "creators": [{"name": "Pérez, Ana"}, {"name": "Consortium"}],
    "publicationYear": 2026,
    "published": "2026-03-14T00:00:00Z",
    "subjects": [{"subject": "biomechanics"}, {"subject": ""}],
    "descriptions": [
        {"descriptionType": "Other", "description": "ignore me"},
        {"descriptionType": "Abstract", "description": "The abstract."},
    ],
    "language": "en",
}}}


def _get(replies):
    """A fake network: url -> payload, missing key answers 404 (None)."""
    def get(url):
        return replies.get(url)

    return get


def test_crossref_reply_maps_every_field():
    rec = fetch("10.1109/TVCG.2026.1234567", get=_get({CROSSREF_URL: CROSSREF_REPLY}))

    assert rec.title == "Motion capture in the wild"
    assert rec.authors == ("Ana Pérez", "Bea Gómez")
    assert rec.year == 2026
    assert rec.published == "2026-03-14"
    assert rec.venue == "IEEE TVCG"
    assert rec.keywords == ("motion capture", "vr")
    assert rec.abstract == "Two para.\n\nSecond & final."
    assert rec.language == "en"


def test_datacite_reply_maps_every_field():
    rec = fetch("10.1109/TVCG.2026.1234567", get=_get({DATACITE_URL: DATACITE_REPLY}))

    assert rec.title == "A preprint"
    assert rec.authors == ("Ana Pérez", "Consortium")
    assert rec.year == 2026
    assert rec.published == "2026-03-14"
    assert rec.keywords == ("biomechanics",)
    assert rec.abstract == "The abstract."


def test_crossref_404_falls_back_to_datacite():
    rec = fetch("10.1109/TVCG.2026.1234567", get=_get({DATACITE_URL: DATACITE_REPLY}))

    assert rec.title == "A preprint"


def test_unknown_doi_names_the_remedy():
    with pytest.raises(RegistryError, match="check the spelling"):
        fetch("10.1109/TVCG.2026.1234567", get=_get({}))


@pytest.mark.parametrize("doi", ["not a doi", "https://doi.org/10.1109/x", ""])
def test_malformed_doi_never_reaches_the_network(doi):
    def get(url):
        raise AssertionError("network must not be reached")

    with pytest.raises(RegistryError, match="is not a DOI"):
        fetch(doi, get=get)


def test_issued_beats_print_beats_online_beats_accepted():
    msg = {"message": {
        "issued": {},
        "published-print": {"date-parts": [[2025]]},
        "published-online": {"date-parts": [[2026, 3]]},
        "accepted": {"date-parts": [[2024]]},
    }}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert (rec.year, rec.published) == (2025, "2025")


def test_absurd_year_is_skipped():
    msg = {"message": {"issued": {"date-parts": [[1900, 2, 3]]}}}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert rec.year is None and rec.published is None


def test_record_without_venue_keywords_or_abstract():
    msg = {"message": {"title": ["Bare"], "author": [{"family": "Solo"}],
                       "issued": {"date-parts": [[2026]]}}}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert rec.authors == ("Solo",)
    assert rec.venue is None and rec.keywords == () and rec.abstract is None
    assert rec.published == "2026"
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_doi.py -v`
Expected: FAIL — `No module named 'tft.doi'`.

- [ ] **Step 4: Implement `doi.py`**

```python
"""The DOI registries: CrossRef first, DataCite as fallback.

Knows registries and JSON, nothing else: no Entry, no Catalog, no YAML.
The DOI shape comes from entry.py, which owns the schema.
"""

import html
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
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None

        raise RegistryError(f"{url}: HTTP {exc.code}; try again later") from exc
    except (URLError, TimeoutError) as exc:
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

        year = int(parts[0])

        if not MIN_YEAR <= year <= MAX_YEAR:
            continue

        date = str(year)

        if len(parts) > 1:
            date += f"-{int(parts[1]):02d}"

        if len(parts) > 2:
            date += f"-{int(parts[2]):02d}"

        return year, date

    return None, None


def _name(given: str | None, family: str | None) -> str:
    return " ".join(part for part in (given, family) if part).strip()


def _strip_markup(text: str | None) -> str | None:
    """JATS abstracts to plain markdown-ready paragraphs."""
    if not text:
        return None

    body = PARAGRAPH_END.sub("\n\n", text)
    body = TAG.sub("", body)
    paragraphs = [" ".join(line.split()) for line in body.split("\n\n")]
    out = "\n\n".join(p for p in paragraphs if p)

    return html.unescape(out) or None


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
        keywords=tuple(message.get("subject", [])),
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
        venue=attributes.get("container") or None,
        keywords=tuple(
            s["subject"] for s in attributes.get("subjects", []) if s.get("subject")
        ),
        abstract=_strip_markup(_datacite_abstract(attributes)),
        language=attributes.get("language"),
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_doi.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/tft/doi.py tools/tft/errors.py tests/test_doi.py
git commit -m "Add the DOI registry driver"
```

---

### Task 5: `Ingest.add_from_doi` and DOI-aware `sync`

**Files:**
- Modify: `tools/tft/ingest.py` (imports, `__init__`, `add` -> `_sync_overleaf` split, new `add_from_doi` + `_sync_doi`)
- Modify: `tools/tft/catalog.py` (`create` gains `venue/doi/published/language` optional params)
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `doi.fetch`/`doi.Record` (Task 4), `catalog.create(authors=...)` (Task 1).
- Produces: `Ingest(cfg, catalog, fetch=..., build=..., fetch_doi=doi.fetch)`; `Ingest.add_from_doi(doi: str, name: str) -> Path`; `Ingest.sync(slug)` dispatches: overleaf entry -> old path, entry with `doi` -> `_sync_doi`, neither -> `FileNotFoundError`. `catalog.create(slug, type, year, title, authors, degree=None, programme=None, supervisors=(), keywords=(), summary=..., venue=None, doi=None, published=None, language="en")`.

- [ ] **Step 1: Write the failing ingest tests**

Append to `tests/test_ingest.py`:

```python
from tft.doi import Record

DOI_STR = "10.1109/TVCG.2026.1234567"


def _paper_record(**over):
    base = dict(
        title="Motion capture in the wild", authors=("A. Autor", "B. Autor"),
        year=2026, published="2026-03-14", venue="IEEE TVCG",
        keywords=("mocap",), abstract="A registry abstract.", language="en",
    ) | over

    return Record(**base)


def _ingest_doi(repo, record):
    """An Ingest whose DOI driver is stubbed; the Overleaf ones stay real."""
    cfg = config.load(repo)

    return Ingest(cfg, Catalog(cfg), fetch_doi=lambda doi: record)


def _add_doi(repo, record=None):
    return _ingest_doi(repo, record or _paper_record()).add_from_doi(DOI_STR, "autor-mocap")


def test_add_from_doi_creates_the_publication(repo):
    folder = _add_doi(repo)

    assert folder == repo / "content" / "publications" / "2026-autor-mocap"
    data = yaml.safe_load((folder / "entry.yaml").read_text())

    assert data["type"] == "publication"
    assert data["authors"] == ["A. Autor", "B. Autor"]
    assert data["venue"] == "IEEE TVCG"
    assert data["doi"] == DOI_STR
    assert data["published"] == "2026-03-14"
    assert data["keywords"] == ["mocap"]
    assert "paper.pdf" not in data


def test_add_from_doi_seeds_the_summary_from_the_abstract(repo):
    folder = _add_doi(repo)

    assert (folder / "summary.md").read_text() == "A registry abstract."


def test_add_from_doi_without_abstract_writes_the_stub(repo):
    folder = _add_doi(repo, _paper_record(abstract=None))

    assert "Replace this line" in (folder / "summary.md").read_text()


def test_add_from_doi_without_a_year_aborts(repo):
    with pytest.raises(ExtractError, match="year"):
        _add_doi(repo, _paper_record(year=None))


def test_sync_doi_refreshes_the_registry_fields(repo):
    _add_doi(repo)
    moved = _paper_record(title="Motion capture in rooms", venue="IEEE VCJR",
                          year=2027, published="2027-01", keywords=("vr",))

    result = _ingest_doi(repo, moved).sync("2026-autor-mocap")
    data = yaml.safe_load((repo / "content" / "publications" / "2026-autor-mocap" / "entry.yaml").read_text())

    assert result.changed is True
    assert data["title"] == "Motion capture in rooms"
    assert data["venue"] == "IEEE VCJR"
    assert data["year"] == 2027
    assert data["keywords"] == ["vr"]


def test_sync_doi_warns_without_renaming_on_year_drift(repo):
    _add_doi(repo)
    result = _ingest_doi(repo, _paper_record(year=2027)).sync("2026-autor-mocap")

    assert any("2027" in w for w in result.warnings)
    assert (repo / "content" / "publications" / "2026-autor-mocap").is_dir()


def test_sync_doi_keeps_the_summary_and_human_fields(repo):
    folder = _add_doi(repo)
    (folder / "summary.md").write_text("Hand-written.\n")
    data = yaml.safe_load((folder / "entry.yaml").read_text())
    data["topics"] = ["vr"]
    (folder / "entry.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    _ingest_doi(repo, _paper_record(title="Changed")).sync("2026-autor-mocap")
    after = yaml.safe_load((folder / "entry.yaml").read_text())

    assert (folder / "summary.md").read_text() == "Hand-written.\n"
    assert after["topics"] == ["vr"]


def test_sync_doi_reports_no_change_when_the_registry_is_still(repo):
    _add_doi(repo)

    assert _ingest_doi(repo, _paper_record()).sync("2026-autor-mocap").changed is False


def test_sync_of_an_entry_with_neither_source_names_what_is_missing(repo):
    folder = repo / "content" / "publications" / "2026-orphan"
    folder.mkdir(parents=True)
    (folder / "entry.yaml").write_text(yaml.safe_dump({
        "type": "publication", "title": "t", "authors": ["a"], "year": 2026,
        "topics": ["vr"], "language": "en",
    }, sort_keys=False))
    (folder / "summary.md").write_text("Text.\n")

    with pytest.raises(FileNotFoundError, match="neither overleaf.project_id nor doi"):
        _ingest(repo).sync("2026-orphan")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `add_from_doi` / `fetch_doi` unknown.

- [ ] **Step 3: Extend `catalog.create`**

```python
    def create(self, slug, type, year, title, authors, degree=None,
               programme=None, supervisors=(), keywords=(), summary=STUB_SUMMARY,
               venue=None, doi=None, published=None, language="en") -> Path:
```

In the data dict: replace `"language": "en"` with `"language": language`, then after the dict literal add, before `store.write`:

```python
        for name, value in (("venue", venue), ("doi", doi), ("published", published)):
            if value is not None:
                data[name] = value
```

- [ ] **Step 4: Implement `ingest.py`**

Imports: `from . import latex, overleaf, store, tex` stays; add `from .doi import fetch as fetch_registry`. In `__init__`:

```python
    def __init__(self, cfg: Config, catalog: Catalog, fetch=overleaf.fetch,
                 build=latex.build, fetch_doi=fetch_registry):
```

with `self._fetch_doi = fetch_doi` added. Replace `sync`'s body: keep `find` + the dispatch, move the existing Overleaf body verbatim into `_sync_overleaf(self, entry)`:

```python
    def sync(self, slug: str) -> SyncResult:
        entry = self._catalog.find(slug)

        if entry.overleaf is not None:
            return self._sync_overleaf(entry)

        if entry.doi is not None:
            return self._sync_doi(entry)

        raise FileNotFoundError(f"{slug} has neither overleaf.project_id nor doi to sync")
```

Add:

```python
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
```

And append at module level at the bottom of `ingest.py`, next to `OVERRIDABLE`:

```python
# A registry that loses a field must not blank the entry: only what it
# reports wins.
REGISTRY_FIELDS = ("title", "authors", "year", "venue", "keywords", "published")
```

- [ ] **Step 5: Run the full suite, verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS (the old sync tests for Overleaf entries pass unchanged through `_sync_overleaf`).

- [ ] **Step 6: Commit**

```bash
git add tools/tft/ingest.py tools/tft/catalog.py tests/test_ingest.py
git commit -m "Ingest publications from a DOI"
```

---

### Task 6: `tft add --doi`

**Files:**
- Modify: `tools/tft/cli.py` (`_parser` add subparser, `_add`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Ingest.add_from_doi` (Task 5).
- Produces: `tft add --doi <doi> --name <name>` (implies publication); `--overleaf`/`--doi` mutually exclusive, one required; `--doi --type thesis` refused. `--type` default becomes `None` (resolved in `_add`).

- [ ] **Step 1: Write the failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_add_doi_implies_publication(repo, monkeypatch):
    seen = {}

    def fake_add_from_doi(self, doi, name):
        seen["doi"] = doi
        seen["name"] = name
        return repo

    monkeypatch.setattr("tft.ingest.Ingest.add_from_doi", fake_add_from_doi)

    code = cli.main(["add", "--doi", "10.1109/x", "--name", "autor-paper"])

    assert code == 0
    assert seen == {"doi": "10.1109/x", "name": "autor-paper"}


def test_add_doi_with_type_thesis_is_refused(repo, capsys):
    code = cli.main(["add", "--doi", "10.1109/x", "--name", "x", "--type", "thesis"])

    assert code == 1
    assert "thesis" in capsys.readouterr().err


def test_add_refuses_overleaf_and_doi_together(repo):
    with pytest.raises(SystemExit):
        cli.main(["add", "--overleaf", "abc", "--doi", "10.1109/x", "--name", "x"])


def test_add_requires_one_source(repo):
    with pytest.raises(SystemExit):
        cli.main(["add", "--name", "x"])


def test_add_doi_reports_registry_error(repo, monkeypatch, capsys):
    from tft.errors import RegistryError

    def fake(self, doi, name):
        raise RegistryError("no registry knows 10.1109/x; check the spelling")

    monkeypatch.setattr("tft.ingest.Ingest.add_from_doi", fake)

    assert cli.main(["add", "--doi", "10.1109/x", "--name", "x"]) == 1
    assert "check the spelling" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL — unrecognized `--doi`.

- [ ] **Step 3: Implement in `cli.py`**

`from .entry import DEGREES, PUBLICATION, THESIS` (add `PUBLICATION`). Replace the `--overleaf` line of the `add` subparser with:

```python
    src = add.add_mutually_exclusive_group(required=True)
    src.add_argument("--overleaf", metavar="ID", help="Overleaf project id")
    src.add_argument("--doi", metavar="DOI", help="create a publication from its DOI")
```

`add.add_argument("--type", default=None, choices=TYPES)`. `_add` becomes:

```python
def _add(args) -> int:
    if args.doi:
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
```

- [ ] **Step 4: Run the full suite, verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/tft/cli.py tests/test_cli.py
git commit -m "Add tft add --doi"
```

---

### Task 7: The site shows authors, venue and the DOI

**Files:**
- Modify: `tools/tft/templates/index.html` (type select)
- Modify: `tools/tft/templates/entry.html` (meta line, Files list)
- Modify: `tools/tft/assets/app.js` (CONTROLS, matches, haystack, card)
- Modify: `tools/tft/site.py` (pass `types` to the template)
- Test: `tests/test_site.py`, `tests/test_app_js.py`

**Interfaces:**
- Consumes: record keys from Task 3 (`authors`, `venue`, `doi`, `published`, `doc` possibly None).
- Produces: index page `<select id="type">`; app.js CONTROLS gains `"type"`; entry page renders joined authors, venue, `published or year`, and a DOI item in the Files list when `doi_url` is set; the PDF item only when `doc` is not None.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_site.py` (reuses the Task 3 `_publication` helper):

```python
def test_index_page_offers_the_type_filter(repo):
    _publication(repo)

    page = (_build(repo) / "index.html").read_text()

    assert 'id="type"' in page
    assert "<option>publication</option>" in page


def test_publication_page_links_the_doi_and_has_no_pdf_item(repo):
    _publication(repo)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert 'href="https://doi.org/10.1109/TVCG.2026.1234567"' in page
    assert "Document (PDF)" not in page


def test_publication_page_with_a_pdf_offers_both(repo):
    _publication(repo, pdf=True)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert "Document (PDF)" in page
    assert 'href="https://doi.org/10.1109/TVCG.2026.1234567"' in page


def test_publication_page_shows_authors_venue_and_date(repo):
    _publication(repo)

    page = (_build(repo) / "entries" / "2026-x" / "index.html").read_text()

    assert "A. Autor, B. Autor" in page
    assert "IEEE TVCG" in page
    assert "2026-03-14" in page
```

Append to `tests/test_app_js.py`:

```python
def test_app_binds_the_type_control():
    source = APP_JS.read_text()

    assert '"type"' in source or "'type'" in source


def test_app_searches_authors_and_venue():
    source = APP_JS.read_text()

    assert "e.authors" in source
    assert "e.venue" in source
```

Update the existing `test_app_binds_every_filter_control` control list to `["q", "year", "type", "degree", "topic", "code", "slides"]`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_site.py tests/test_app_js.py -v`
Expected: FAIL.

- [ ] **Step 3: `site.py` passes the facet**

In `_write_index`'s template render, add:

```python
            types=sorted({e.type for e in entries}),
```

- [ ] **Step 4: `index.html` gains the select**

After the `year` select:

```html
  <select id="type"><option value="">Any type</option>
    {% for type in types %}<option>{{ type }}</option>{% endfor %}
  </select>
```

- [ ] **Step 5: `entry.html` meta line and Files list**

Replace the meta line block (L24-35) with:

```html
  <p class="meta">
    {{ entry.authors|join(", ") }}
    {%- if entry.author_github %}
    <a class="social" href="{{ entry.author_github }}" aria-label="GitHub">{% include "icons/github.svg" %}</a>
    {%- endif %}
    {%- if entry.author_linkedin %}
    <a class="social" href="{{ entry.author_linkedin }}" aria-label="LinkedIn">{% include "icons/linkedin.svg" %}</a>
    {%- endif %}
    &middot; {{ entry.published or entry.year }} &middot; {{ entry.type }}
    {%- if entry.degree %} ({{ entry.degree }}){% endif %}
    {%- if entry.venue %} &middot; {{ entry.venue }}{% endif %}
    {%- if entry.programme %} &middot; {{ entry.programme|titlecase }}{% endif %}
  </p>
```

Replace the Files list (L69-73) with:

```html
  <h2>Files</h2>
  <ul>
    {% if doc %}<li><a href="{{ doc }}">Document (PDF)</a></li>{% endif %}
    {% if entry.slides %}<li><a href="{{ entry.slides }}">Presentation</a></li>{% endif %}
    {# Built from the validated bare DOI, never from free text. #}
    {% if doi_url %}<li><a href="{{ doi_url }}">Published version (DOI)</a></li>{% endif %}
  </ul>
```

and in `site.py._write_entry`'s render call add `doi_url=f"{DOI_BASE}{entry.doi}" if entry.doi else None`.

- [ ] **Step 6: `app.js`**

```js
const CONTROLS = ["q", "year", "type", "degree", "topic", "code", "slides"];
```

In `matches`, after the year line:

```js
  if (f.type && e.type !== f.type) return false;
```

In `matches`, the haystack becomes:

```js
  const haystack = [e.title, e.authors.join(" "), e.summary, e.programme, e.venue,
                    e.topics.join(" "), e.keywords.join(" ")]
```

In `card`, the degree bit becomes the kind bit (a thesis shows its degree, a paper its venue):

```js
  const kind = e.degree || e.venue;
  const kindBit = kind ? ` &middot; ${escape(kind)}` : "";
```

and the meta line of the card becomes:

```js
    <p class="meta">${escape(e.authors.join(", "))} &middot; ${escape(e.year)}${kindBit}</p>
```

- [ ] **Step 7: Run the full suite, verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tools/tft/templates tools/tft/assets/app.js tools/tft/site.py tests
git commit -m "Show authors, venue and DOI on the site"
```

---

### Task 8: README and final verification

**Files:**
- Modify: `README.md` (Layout block, new "Adding a paper" section, clearance rule restated)

- [ ] **Step 1: Update the Layout block**

In the indented layout block (`content/theses/<year>-<slug>/ ...`), add after the theses line:

```
    content/publications/<year>-<slug>/ same shape; paper.pdf only if shareable
```

- [ ] **Step 2: Add the "Adding a paper" section**

After the "Adding an entry" section's "Keeping an entry current" line and before "Changing one field", insert:

```markdown
### Adding a paper

    tft add --doi 10.1109/TVCG.2026.1234567 --name autor-mocap

Title, authors in order, year, venue, keywords and the abstract (when
the registry carries one) come from CrossRef, falling back to DataCite.
The slug still needs `--name`: it is a URL others will cite. A DOI the
registries do not know aborts; so does one without a year.

Then replace the `CHANGE-ME` topic as with a thesis. `tft sync <slug>`
re-reads the registries and refreshes title, authors, year, venue and
keywords; your own fields and `summary.md` are never touched.

Drop `paper.pdf` in the folder only if the rights allow it — publisher
PDFs usually may not be hosted, accepted manuscripts often may. A
paywalled paper is listed by its citation alone: the page links the
DOI. Presence in this repo remains the clearance for the file; the
citation itself is public knowledge and is not withheld.
```

- [ ] **Step 3: Verify the whole toolchain end to end**

Run: `.venv/bin/python -m pytest -v && .venv/bin/tft validate && .venv/bin/tft build`
Expected: suite green, `ok`, `built site/`. Then open `site/index.html`, confirm the two real theses render unchanged and the type filter offers `publication`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document adding a paper"
```

---

## Out of this plan (from the spec)

- `tft add --doi --overleaf` (mirror sources while citing): additive later.
- ORCID, affiliations, funders, ISSN, volumes, pages, reference lists: behind the DOI by choice.
- Any visibility flag: file presence remains the state.
