# Scientific papers catalogued from their DOI

Date: 2026-09-19
Status: approved, pending implementation plan

## Purpose

The catalog holds theses only in practice: `tft add` ingests from
Overleaf, and `type: publication` is scaffolded (`content/publications/`,
`venue`, `paper.pdf`) but has never carried an entry. Papers are cited by
DOI, and a DOI identifies everything the catalog needs: title, the full
ordered author list, year, venue, the authors' own keywords, sometimes an
abstract.

This design adds `tft add --doi <doi>`, which builds a publication entry
from public registry metadata, and adjusts what "public" means for a
paper: a citation is never confidential, a PDF can be.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Paywalled papers | Listed without their PDF | Metadata is public knowledge; only hosting the file needs clearance. No flag: `paper.pdf` present or absent is the state |
| Authors | One `authors` list for every entry | A thesis has exactly one; two fields for one concept would tax every consumer forever |
| PDF acquisition | Human drops it in | Rights are a human call; the tool never downloads publisher files |
| Extraction depth | Curated fields only | Volume/ISSN/funders/refs live behind the DOI, which is authoritative and permanent |
| Source mirroring | DOI-only for now | Combining `--doi` with an Overleaf mirror is additive later; nothing here blocks it |
| Registry | CrossRef first, DataCite fallback | CrossRef covers most journal and conference papers; DataCite covers the rest (Zenodo, arXiv) |
| Slug | `--name` still required | The slug becomes a URL others will cite; it stays human-chosen |

### Why not keep the strict presence-is-clearance rule

A paywalled paper cannot legally sit in the public repo under the current
rule, so the catalog would list only fully open papers — and the group's
own IEEE/TVCG work is mostly not. Splitting the rule in two keeps its
teeth: the citation is listed, the file appears only if someone put it
there with the rights to. The bug class it protects against (a file
leaking) is unchanged.

### Why not extract paper metadata from LaTeX

Publisher and venue templates are unbounded, and most papers will not
come from a group Overleaf project. The existing
`add --overleaf --type publication` path stays for papers that do; this
design does not touch it.

## Data model

`entry.py` changes:

| Change | Shape | Validation |
|---|---|---|
| `author` -> `authors` | list of str, mandatory, ordered | non-empty list of non-empty strings |
| `doi` | str, optional | bare form `10.\d{4,}/\S+`; syntax only, reachability never checked |
| `published` | str, optional | `YYYY`, `YYYY-MM` or `YYYY-MM-DD` |

`catalog.create`'s `author` parameter becomes `authors` likewise; its
two callers (the Overleaf path and the new DOI path) each pass one.
`venue` exists already and is unchanged. `year` remains the sort key and
the folder prefix. `supervisors`, `score`, `honours` keep their thesis
meaning and stay unused for papers.

File requirements become per-type in `catalog._required_files`:

- thesis: `summary.md` + `thesis.pdf`, as today;
- publication: `summary.md`, and `paper.pdf` joins the existing
  "declared or present files must exist" rule — present in the folder,
  it is copied by the build; absent, the entry is valid and the page
  links the DOI instead.

### Migration

`author: X` becomes `authors: [X]` in the two existing `entry.yaml`
files, by hand, in the same commit as the schema change. `tex.Meta`
keeps its single `author: str` and `ingest` wraps it: a thesis source
declares one author, and the extractor stays simple.

## The DOI driver

New module `tools/tft/doi.py`, same layer as `tex.py` and `overleaf.py`:
it knows registries and nothing else — no `Entry`, no `Catalog`, no YAML.

```python
@dataclass(frozen=True)
class Record:
    title: str
    authors: tuple[str, ...]
    year: int | None
    published: str | None        # YYYY, YYYY-MM or YYYY-MM-DD
    venue: str | None
    keywords: tuple[str, ...]
    abstract: str | None
    language: str | None

def fetch(doi: str) -> Record: ...
```

`fetch` tries `https://api.crossref.org/works/<doi>`; a 404 there falls
back to `https://api.datacite.org/dois/<doi>`. Stdlib `urllib` only. A
DOI unknown to both, a network failure, or an unparseable reply raise
`TftError` subclasses whose message names the remedy.

### Mapping

| Field | CrossRef | DataCite |
|---|---|---|
| title | `message.title[0]` | `attributes.titles[0]` |
| authors | `message.author[]` in given order; ORCID and affiliations dropped | `attributes.creators[]` |
| year + published | `issued` date-parts, else `published-print`, `published-online`, then `accepted` | `publicationYear`, `published` when present |
| venue | `container-title[0]` | `attributes.container` |
| keywords | `subject[]` | `attributes.subjects[]` |
| abstract | JATS-tagged, stripped of tags | `attributes.descriptions` entries of type Abstract, else absent |
| language | `message.language` when present | not offered |

`venue` absent is valid: preprints have none. `language` defaults to `en`
when the registry does not say. `keywords` seed the existing own-words
field — never the curated `topics`, same rule as thesis keywords.

A registry year that is not a four-digit Gregorian year is a registry
bug: raise, naming the DOI and the value, never file it.

### Abstract into summary.md

A registry abstract seeds `summary.md` at add time, with JATS/emphasis
markup stripped to plain paragraphs. From then on the human owns the
file: publications keep the current sync rule that their summary is
never overwritten. No abstract in the registry, no seed: the stub
sentence is written, as for any new entry.

## CLI and ingest

- `tft add --doi <doi>` implies `--type publication`. `--overleaf` and
  `--doi` are mutually exclusive, and `--doi --type thesis` is refused:
  a DOI is not a thesis. `--name` stays required.
- `ingest.add_from_doi(doi, name)` calls `doi.fetch`, maps the
  `Record` onto `Catalog.create` (slug `f"{year}-{name}"`), writes the
  summary seed, and does nothing else: no compile, no mirror, no PDF.
  A missing `year` in the registry aborts — the slug needs it.
- `tft sync <slug>` on a DOI entry (entry has `doi`, no
  `overleaf.project_id`) re-fetches and refreshes title, authors, year,
  venue, keywords and published. It never touches summary, topics, or
  any human field. Year drift warns without renaming, exactly as the
  Overleaf sync does.
- `tft sync` on a publication with neither `doi` nor `overleaf` fails
  naming what is missing, as today.

## Site

`site.record()` gains `authors` (joined for display, list for search),
`venue`, `doi` (as `https://doi.org/<doi>`, built from validated parts
never interpolated raw — same care as video embeds) and `published`.

Index page:

- a **type filter** (`All types / Theses / Publications`) beside the
  existing selects; `type` is already in the record,
- the haystack gains `venue` and every author,
- card meta shows joined authors, ` · year · ` then venue for papers
  where a thesis shows degree,
- publications get no score badge; score keeps its thesis meaning.

Entry page: authors line; venue and `published` when set; a permalink
`https://doi.org/<doi>`; the PDF button becomes a DOI button when
`paper.pdf` is absent. Papers get no portrait logic — `photo` stays a
thesis field in practice but needs no schema change for that.

## Testing

`tests/test_doi.py`, fixtures per case against a fake fetchable
(CrossRef JSON, DataCite JSON — never the network):

- every field recovered from each registry's shape,
- CrossRef 404 falls through to DataCite,
- DOI unknown to both: error names the remedy,
- JATS abstract stripped to plain paragraphs,
- date-parts pick: issued over print over online over accepted,
- author list order preserved, ORCID and affiliations dropped,
- registry without venue, without keywords, without abstract.

Existing suites extended:

- `test_entry.py`: `authors` mandatory for both types, `doi` and
  `published` validation, old `author` rejected as unknown.
- `test_catalog.py`: publication without `paper.pdf` is valid; present
  but missing file is caught.
- `test_ingest.py`: `add_from_doi` end-to-end against fake fetch;
  summary seeded then never rewritten; sync refresh fields, warns on
  year drift.
- `test_cli.py`: `--doi` implies publication; `--doi` with `--overleaf`
  is refused.
- `test_site.py`, `test_app_js.py`: new record fields, type filter,
  DOI-as-PDF fallback link.

## Out of scope

- `tft add --doi --overleaf` (mirror sources while citing the DOI):
  additive later, no decision here forecloses it.
- ORCID, affiliations, funders, ISSN, volumes, pages, reference lists:
  behind the DOI by choice, not by omission.
- Pulling the full text: the tool never downloads a paper.
- A public/private visibility flag: file presence remains the state.

## Note for the README

A new "Adding a paper" section: `tft add --doi ...`, human fills topics,
drop `paper.pdf` only if the rights allow it, paywalled papers are
listed without it. The clearance rule restated for the new shape: the
citation is always public; the file appears only if it was put there
with the rights to.
