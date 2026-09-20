"""Where the tool reads and writes, resolved once per run."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import BadValue, ConfigError

CONFIG_FILE = "pubs.toml"
DEFAULT_PRIVATE = "../web-pubs-private"
DEFAULT_MIRROR_BASE = "https://github.com/ECL-STRAST/web-pubs-private/tree/main/sources"
WORK_DIR = ".work"


@dataclass(frozen=True)
class Config:
    root: Path          # the public repo
    private: Path       # the private repo checkout holding LaTeX sources
    work: Path          # scratch clones, gitignored
    mirror_base: str    # public URL prefix for a mirrored source folder


def load(root: Path) -> Config:
    """Read pubs.toml if present, otherwise fall back to the sibling repo."""
    toml = _read_toml(root)
    private = _private_path(root, toml)
    mirror_base = _mirror_base(toml)

    return Config(root=root, private=private, work=root / WORK_DIR, mirror_base=mirror_base)


def _private_path(root: Path, toml: dict) -> Path:
    raw = toml.get("paths", {}).get("private", DEFAULT_PRIVATE)

    if not isinstance(raw, str):
        raise BadValue(f"paths.private must be a string, got {type(raw).__name__}")

    # An absolute override is taken as given; anything else hangs off the repo.
    path = Path(raw)

    return path if path.is_absolute() else (root / path).resolve()


def _mirror_base(toml: dict) -> str:
    raw = toml.get("paths", {}).get("mirror_base", DEFAULT_MIRROR_BASE)

    if not isinstance(raw, str):
        raise BadValue(f"paths.mirror_base must be a string, got {type(raw).__name__}")

    return raw


def _read_toml(root: Path) -> dict:
    path = root / CONFIG_FILE

    if not path.exists():
        return {}

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
