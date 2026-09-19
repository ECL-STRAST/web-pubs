import socket
from urllib.error import URLError

import pytest

from tft.doi import CROSSREF, DATACITE, TIMEOUT_SECONDS, fetch, get_json
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
    # DataCite names languages in its own vocabulary ("eng" for "en"), so
    # its language is dropped rather than mixed into the entry's.
    assert rec.language is None


def test_datacite_container_mapping_is_not_a_venue():
    # The live API answers container as a mapping, not a string: 10.5281/
    # zenodo.3710157 says {'type': 'Series', 'identifier': '10.1590/...'}.
    attrs = dict(DATACITE_REPLY["data"]["attributes"])
    attrs["container"] = {"type": "Series", "identifier": "10.1590/1982-0224-20170162",
                          "identifierType": "DOI"}
    rec = fetch("10.1109/x", get=_get({DATACITE + "10.1109/x": {"data": {"attributes": attrs}}}))

    assert rec.venue is None


def test_datacite_container_title_is_the_venue():
    attrs = dict(DATACITE_REPLY["data"]["attributes"])
    attrs["container"] = {"containerTitle": "IEEE TVCG", "containerType": "series"}
    rec = fetch("10.1109/x", get=_get({DATACITE + "10.1109/x": {"data": {"attributes": attrs}}}))

    assert rec.venue == "IEEE TVCG"


def test_entity_encoded_tags_do_not_survive_the_strip():
    # A registry abstract may hide its markup behind entities: stripping
    # before unescaping would hand the decoded tags straight to |safe.
    msg = {"message": {
        "title": ["Bare"], "issued": {"date-parts": [[2026]]},
        "abstract": "<jats:p>&lt;script&gt;alert(1)&lt;/script&gt; plain.</jats:p>",
    }}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert "<" not in rec.abstract
    assert rec.abstract == "alert(1) plain."


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
    msg = {"message": {"issued": {"date-parts": [[9999, 2, 3]]}}}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert rec.year is None and rec.published is None


def test_old_but_real_year_survives_the_sanity_floor():
    # Retro-registered classics carry DOIs: 10.1002/andp.19050910702 is 1905.
    msg = {"message": {"issued": {"date-parts": [[1905, 6, 30]]}}}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert (rec.year, rec.published) == (1905, "1905-06-30")


def test_record_without_venue_keywords_or_abstract():
    msg = {"message": {"title": ["Bare"], "author": [{"family": "Solo"}],
                       "issued": {"date-parts": [[2026]]}}}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert rec.authors == ("Solo",)
    assert rec.venue is None and rec.keywords == () and rec.abstract is None
    assert rec.published == "2026"


def test_non_numeric_date_part_is_skipped():
    # A registry handing us "oops" where a year belongs must not crash the tool.
    msg = {"message": {"issued": {"date-parts": [["oops"]]}}}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert rec.year is None and rec.published is None


def test_blank_crossref_subjects_are_dropped():
    msg = {"message": {
        "title": ["Bare"], "issued": {"date-parts": [[2026]]},
        "subject": ["", "ok", "  "],
    }}
    rec = fetch("10.1109/x", get=_get({CROSSREF + "10.1109/x": msg}))

    assert rec.keywords == ("ok",)


def _stalling_urlopen(monkeypatch, error):
    """urlopen replaced by a stub that notes its kwargs, then stalls."""
    seen = {}

    def urlopen(request, *args, **kwargs):
        seen.update(kwargs)
        raise error

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    return seen


def test_stalled_registry_becomes_a_registry_error(monkeypatch):
    seen = _stalling_urlopen(monkeypatch, TimeoutError("read operation timed out"))

    with pytest.raises(RegistryError, match="check your connection"):
        get_json(CROSSREF_URL)

    assert seen["timeout"] == TIMEOUT_SECONDS


def test_connect_timeout_maps_to_the_same_remedy(monkeypatch):
    stall = socket.timeout("timed out")
    _stalling_urlopen(monkeypatch, URLError(stall))

    with pytest.raises(RegistryError, match="check your connection"):
        get_json(CROSSREF_URL)
