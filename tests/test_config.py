import pytest
from pathlib import Path

from pubs import config
from pubs.errors import BadValue


def test_defaults_to_sibling_private_repo(tmp_path):
    cfg = config.load(tmp_path)

    assert cfg.root == tmp_path
    assert cfg.private == (tmp_path / ".." / "web-pubs-private").resolve()
    assert cfg.work == tmp_path / ".work"


def test_toml_overrides_private_path(tmp_path):
    (tmp_path / "pubs.toml").write_text('[paths]\nprivate = "/srv/private"\n')

    cfg = config.load(tmp_path)

    assert cfg.private == Path("/srv/private")


def test_relative_override_resolves_against_root(tmp_path):
    (tmp_path / "pubs.toml").write_text('[paths]\nprivate = "sibling"\n')

    cfg = config.load(tmp_path)

    assert cfg.private == (tmp_path / "sibling").resolve()


def test_non_string_private_path_is_rejected(tmp_path):
    (tmp_path / "pubs.toml").write_text("[paths]\nprivate = 7\n")

    with pytest.raises(BadValue):
        config.load(tmp_path)


def test_defaults_to_the_public_mirror_url(tmp_path):
    cfg = config.load(tmp_path)

    assert cfg.mirror_base == config.DEFAULT_MIRROR_BASE


def test_toml_overrides_mirror_base(tmp_path):
    (tmp_path / "pubs.toml").write_text('[paths]\nmirror_base = "https://example.org/x"\n')

    cfg = config.load(tmp_path)

    assert cfg.mirror_base == "https://example.org/x"


def test_non_string_mirror_base_is_rejected(tmp_path):
    (tmp_path / "pubs.toml").write_text("[paths]\nmirror_base = 7\n")

    with pytest.raises(BadValue):
        config.load(tmp_path)
