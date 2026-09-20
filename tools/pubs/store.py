"""Reads and writes entry folders. The only module that knows about YAML."""

import dataclasses
from pathlib import Path

import yaml

from . import entry as model
from .entry import Entry
from .errors import ConfigError, SchemaError

ENTRY_FILE = "entry.yaml"
SUMMARY_FILE = "summary.md"


def read_list(path: Path) -> list:
    """Parse a YAML file expected to hold a list, e.g. the topic vocabulary."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def read(dir: Path) -> Entry:
    """Load one entry folder. The directory name is the slug."""
    path = dir / ENTRY_FILE

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    try:
        parsed = model.from_dict(dir.name, data)
    except SchemaError as exc:
        # Re-raise the same class so callers can still discriminate the cause.
        raise type(exc)(f"{path}: {exc}") from exc

    return dataclasses.replace(parsed, summary=_summary(dir))


def write(dir: Path, entry: Entry) -> None:
    """Write entry.yaml. summary.md is written separately, by write_summary."""
    dir.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(model.to_dict(entry), sort_keys=False, allow_unicode=True)
    (dir / ENTRY_FILE).write_text(text, encoding="utf-8")


def write_summary(dir: Path, text: str) -> None:
    """Write summary.md. Derived from the thesis abstract and rewritten on
    every sync, so hand edits do not survive; the diff is the review."""
    dir.mkdir(parents=True, exist_ok=True)
    (dir / SUMMARY_FILE).write_text(text, encoding="utf-8")


def exists(path: Path) -> bool:
    """Whether a file is present in an entry folder."""
    return path.is_file()


def dir_exists(path: Path) -> bool:
    """Whether an entry folder exists."""
    return path.is_dir()


def dirs(parent: Path) -> list[Path]:
    """Entry folders under parent, sorted by slug."""
    if not parent.is_dir():
        return []

    return sorted(d for d in parent.iterdir() if (d / ENTRY_FILE).is_file())


def _summary(dir: Path) -> str:
    path = dir / SUMMARY_FILE

    return path.read_text(encoding="utf-8") if path.is_file() else ""
