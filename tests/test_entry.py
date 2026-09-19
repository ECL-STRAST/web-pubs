import pytest

from tft import entry
from tft.errors import BadValue, MissingField, UnknownField

MINIMAL = {
    "type": "thesis",
    "title": "A database for biomechanical data",
    "authors": ["Silvia Nieves Serrano"],
    "year": 2027,
    "degree": "bachelor",
    "topics": ["biomechanics"],
    "language": "en",
}


def test_minimal_entry_round_trips():
    parsed = entry.from_dict("2027-nieves-serrano-biomechanics-db", MINIMAL)

    assert parsed.slug == "2027-nieves-serrano-biomechanics-db"
    assert parsed.title == MINIMAL["title"]
    assert parsed.topics == ("biomechanics",)
    assert entry.to_dict(parsed) == MINIMAL


def test_optional_blocks_survive_the_round_trip():
    data = MINIMAL | {
        "supervisors": ["Rodrigo Garcia Carmona"],
        "overleaf": {"project_id": "698b41fa174f9aec00db94cb", "commit": "a3f19c2"},
        "repos": {"code": ["https://github.com/ECL-STRAST/libremotion-chloe"]},
        "slides": "slides.pdf",
    }

    parsed = entry.from_dict("2027-x", data)

    assert parsed.overleaf.project_id == "698b41fa174f9aec00db94cb"
    assert parsed.repos.code == ("https://github.com/ECL-STRAST/libremotion-chloe",)
    assert parsed.slides == "slides.pdf"
    assert entry.to_dict(parsed) == data


def test_unfinished_entry_is_valid():
    # No repos, no slides, no overleaf commit: the work is still in progress.
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.repos.code == ()
    assert parsed.slides is None
    assert parsed.overleaf is None


@pytest.mark.parametrize("field", ["type", "title", "authors", "year", "topics", "language"])
def test_missing_mandatory_field(field):
    data = {k: v for k, v in MINIMAL.items() if k != field}

    with pytest.raises(MissingField, match=field):
        entry.from_dict("2027-x", data)


def test_thesis_requires_a_degree():
    data = {k: v for k, v in MINIMAL.items() if k != "degree"}

    with pytest.raises(MissingField, match="degree"):
        entry.from_dict("2027-x", data)


def test_publication_does_not_require_a_degree():
    data = {k: v for k, v in MINIMAL.items() if k != "degree"} | {"type": "publication"}

    assert entry.from_dict("2027-x", data).degree is None


def test_publication_with_invalid_degree_is_rejected():
    data = {k: v for k, v in MINIMAL.items() if k != "type"} | {"type": "publication", "degree": "postdoc"}

    with pytest.raises(BadValue, match="degree"):
        entry.from_dict("2027-x", data)


def test_unknown_field_is_rejected():
    with pytest.raises(UnknownField, match="titel"):
        entry.from_dict("2027-x", MINIMAL | {"titel": "typo"})


def test_unknown_type_is_rejected():
    with pytest.raises(BadValue, match="type"):
        entry.from_dict("2027-x", MINIMAL | {"type": "poster"})


def test_unknown_degree_is_rejected():
    with pytest.raises(BadValue, match="degree"):
        entry.from_dict("2027-x", MINIMAL | {"degree": "postdoc"})


def test_year_must_be_an_integer():
    with pytest.raises(BadValue, match="year"):
        entry.from_dict("2027-x", MINIMAL | {"year": "2027"})


def test_topics_must_not_be_empty():
    with pytest.raises(BadValue, match="topics"):
        entry.from_dict("2027-x", MINIMAL | {"topics": []})


def test_doc_name_per_type():
    assert entry.DOC_NAME["thesis"] == "thesis.pdf"
    assert entry.DOC_NAME["publication"] == "paper.pdf"


def test_new_optional_fields_round_trip():
    data = MINIMAL | {
        "keywords": ["motion capture", "c3d"],
        "score": 10,
        "honours": True,
        "photo": "photo.jpg",
    }

    parsed = entry.from_dict("2027-x", data)

    assert parsed.keywords == ("motion capture", "c3d")
    assert parsed.score == 10
    assert parsed.honours is True
    assert parsed.photo == "photo.jpg"
    assert entry.to_dict(parsed) == data


def test_entry_without_the_new_fields_is_unchanged():
    # The catalog's existing entry predates them and must keep validating.
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.keywords == ()
    assert parsed.score is None
    assert parsed.honours is False
    assert parsed.photo is None
    assert entry.to_dict(parsed) == MINIMAL


@pytest.mark.parametrize("score", [-1, 11, 10.5])
def test_score_outside_the_scale_is_rejected(score):
    with pytest.raises(BadValue, match="score"):
        entry.from_dict("2027-x", MINIMAL | {"score": score})


def test_score_must_be_a_number():
    with pytest.raises(BadValue, match="score"):
        entry.from_dict("2027-x", MINIMAL | {"score": "10"})


def test_score_must_not_be_a_boolean():
    # bool is a subclass of int in Python; True would otherwise pass as 1.
    with pytest.raises(BadValue, match="score"):
        entry.from_dict("2027-x", MINIMAL | {"score": True})


def test_score_accepts_the_bounds():
    assert entry.from_dict("2027-x", MINIMAL | {"score": 0}).score == 0
    assert entry.from_dict("2027-x", MINIMAL | {"score": 10}).score == 10
    assert entry.from_dict("2027-x", MINIMAL | {"score": 9.5}).score == 9.5


def test_honours_needs_a_score():
    with pytest.raises(BadValue, match="honours"):
        entry.from_dict("2027-x", MINIMAL | {"honours": True})


def test_keywords_must_not_be_empty():
    with pytest.raises(BadValue, match="keywords"):
        entry.from_dict("2027-x", MINIMAL | {"keywords": []})


def test_keywords_must_be_non_empty_strings():
    with pytest.raises(BadValue, match="keywords"):
        entry.from_dict("2027-x", MINIMAL | {"keywords": ["ok", " "]})


def test_keywords_are_not_checked_against_the_taxonomy():
    # Deliberate: keywords are the thesis's own words, topics are curated.
    parsed = entry.from_dict("2027-x", MINIMAL | {"keywords": ["plug-in gait"]})

    assert parsed.keywords == ("plug-in gait",)


def test_supervisors_must_be_a_list():
    with pytest.raises(BadValue, match="supervisors"):
        entry.from_dict("2027-x", MINIMAL | {"supervisors": "Rodrigo"})


def test_supervisors_must_be_non_empty_strings():
    with pytest.raises(BadValue, match="supervisors"):
        entry.from_dict("2027-x", MINIMAL | {"supervisors": ["ok", " "]})


def test_supervisors_may_be_an_empty_list():
    # Derived from \supervisor: a thesis with none is not a schema error.
    parsed = entry.from_dict("2027-x", MINIMAL | {"supervisors": []})

    assert parsed.supervisors == ()


def test_absent_supervisors_is_fine():
    assert entry.from_dict("2027-x", MINIMAL).supervisors == ()


def test_a_zero_score_survives_the_round_trip():
    data = MINIMAL | {"score": 0}

    assert entry.to_dict(entry.from_dict("2027-x", data)) == data


def test_photo_must_be_a_string():
    with pytest.raises(BadValue, match="photo"):
        entry.from_dict("2027-x", MINIMAL | {"photo": 123})


def test_photo_must_not_be_blank():
    with pytest.raises(BadValue, match="photo"):
        entry.from_dict("2027-x", MINIMAL | {"photo": "  "})


def test_photo_must_not_traverse_out_of_the_entry():
    with pytest.raises(BadValue, match="photo"):
        entry.from_dict("2027-x", MINIMAL | {"photo": "../../x.jpg"})


def test_slides_must_not_traverse_out_of_the_entry():
    with pytest.raises(BadValue, match="slides"):
        entry.from_dict("2027-x", MINIMAL | {"slides": "../secret.pdf"})


YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SHORT_URL = "https://youtu.be/dQw4w9WgXcQ"
VIMEO_URL = "https://vimeo.com/76979871"


def test_programme_round_trips():
    data = MINIMAL | {"programme": "GRADO EN INGENIERÍA BIOMÉDICA"}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.programme == "GRADO EN INGENIERÍA BIOMÉDICA"
    assert entry.to_dict(parsed) == data


def test_absent_programme_is_none():
    assert entry.from_dict("2027-x", MINIMAL).programme is None


def test_programme_must_be_a_non_empty_string():
    with pytest.raises(BadValue, match="programme"):
        entry.from_dict("2027-x", MINIMAL | {"programme": "  "})


def test_programme_must_be_a_string():
    with pytest.raises(BadValue, match="programme"):
        entry.from_dict("2027-x", MINIMAL | {"programme": 7})


def test_image_and_video_round_trip():
    data = MINIMAL | {"image": "cover.png", "video": YOUTUBE_URL}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.image == "cover.png"
    assert parsed.video == YOUTUBE_URL
    assert entry.to_dict(parsed) == data


def test_absent_image_and_video_are_none():
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.image is None
    assert parsed.video is None


def test_image_must_be_a_string():
    with pytest.raises(BadValue, match="image"):
        entry.from_dict("2027-x", MINIMAL | {"image": 123})


def test_image_must_not_be_blank():
    with pytest.raises(BadValue, match="image"):
        entry.from_dict("2027-x", MINIMAL | {"image": "  "})


def test_image_must_not_traverse_out_of_the_entry():
    with pytest.raises(BadValue, match="image"):
        entry.from_dict("2027-x", MINIMAL | {"image": "../../secret.png"})


@pytest.mark.parametrize("url,host,id", [
    (YOUTUBE_URL, entry.YOUTUBE, "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ", entry.YOUTUBE, "dQw4w9WgXcQ"),
    (SHORT_URL, entry.YOUTUBE, "dQw4w9WgXcQ"),
    (VIMEO_URL, entry.VIMEO, "76979871"),
])
def test_video_accepts_each_allowed_form(url, host, id):
    parsed = entry.from_dict("2027-x", MINIMAL | {"video": url})

    assert parsed.video == url
    assert entry.parse_video(url) == entry.Video(host=host, id=id)


@pytest.mark.parametrize("url", [
    "https://evil.example.com/watch?v=dQw4w9WgXcQ",
    "javascript:alert(1)",
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30",
    "https://vimeo.com/not-a-number",
    "https://www.youtube.com/watch?v=",
    "dQw4w9WgXcQ",
    SHORT_URL + "\n",
])
def test_video_rejects_anything_else(url):
    with pytest.raises(BadValue, match="video"):
        entry.from_dict("2027-x", MINIMAL | {"video": url})


def test_video_must_be_a_string():
    with pytest.raises(BadValue, match="video"):
        entry.from_dict("2027-x", MINIMAL | {"video": 42})


def test_embed_url_is_built_from_the_id_alone():
    assert entry.parse_video(YOUTUBE_URL).embed == "https://www.youtube.com/embed/dQw4w9WgXcQ"
    assert entry.parse_video(VIMEO_URL).embed == "https://player.vimeo.com/video/76979871"


def test_parse_video_of_nothing_is_none():
    assert entry.parse_video(None) is None
    assert entry.parse_video("javascript:alert(1)") is None


GITHUB_URL = "https://github.com/bgomezm"
LINKEDIN_URL = "https://www.linkedin.com/in/bgomezm"


def test_author_links_round_trip():
    data = MINIMAL | {"author_github": GITHUB_URL, "author_linkedin": LINKEDIN_URL}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.author_github == GITHUB_URL
    assert parsed.author_linkedin == LINKEDIN_URL
    assert entry.to_dict(parsed) == data


def test_absent_author_links_are_none():
    parsed = entry.from_dict("2027-x", MINIMAL)

    assert parsed.author_github is None
    assert parsed.author_linkedin is None


def test_author_links_accept_a_trailing_slash():
    # What a browser's address bar actually shows when you copy a profile URL.
    data = MINIMAL | {"author_github": GITHUB_URL + "/", "author_linkedin": LINKEDIN_URL + "/"}

    parsed = entry.from_dict("2027-x", data)

    assert parsed.author_github == GITHUB_URL + "/"
    assert parsed.author_linkedin == LINKEDIN_URL + "/"


@pytest.mark.parametrize("url", [
    "https://gitlab.com/bgomezm",
    "http://github.com/bgomezm",
    "https://github.com/bgomezm/some-repo",
    "javascript:alert(1)",
    GITHUB_URL + "\n",
])
def test_author_github_rejects_anything_else(url):
    with pytest.raises(BadValue, match="author_github"):
        entry.from_dict("2027-x", MINIMAL | {"author_github": url})


@pytest.mark.parametrize("url", [
    "https://linkedin.com/company/ecl-strast",
    "http://www.linkedin.com/in/bgomezm",
    "https://facebook.com/bgomezm",
    LINKEDIN_URL + "\n",
])
def test_author_linkedin_rejects_anything_else(url):
    with pytest.raises(BadValue, match="author_linkedin"):
        entry.from_dict("2027-x", MINIMAL | {"author_linkedin": url})


def test_author_github_must_be_a_string():
    with pytest.raises(BadValue, match="author_github"):
        entry.from_dict("2027-x", MINIMAL | {"author_github": 42})


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
