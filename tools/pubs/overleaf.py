"""Talks to the Overleaf git connector. The only module that runs git."""

import os
import subprocess
from pathlib import Path

from .errors import OverleafError

TOKEN_ENV = "OVERLEAF_GIT_TOKEN"
GIT_HOST = "git.overleaf.com"
REDACTED = "***"

# A credential helper that reads the token from the environment at git's
# request, instead of it ever appearing in a URL, argv, or .git/config.
CREDENTIAL_HELPER = f'!f(){{ echo username=git; echo "password=${TOKEN_ENV}"; }};f'

# An empty credential.helper value resets the (possibly inherited, e.g. a
# user's global `credential.helper = store`) helper list before ours is
# added. Without it, git would also consult those helpers, and one that
# persists credentials (like `store`) would write the token to disk after
# a successful auth.
_GIT_CONFIG_ENTRIES = [
    ("credential.helper", ""),
    ("credential.helper", CREDENTIAL_HELPER),
]


def token() -> str:
    """The Overleaf git token, from the environment and nowhere else."""
    value = os.environ.get(TOKEN_ENV)

    if not value:
        raise OverleafError(f"{TOKEN_ENV} is not set")

    return value


def url(project_id: str) -> str:
    return f"https://{GIT_HOST}/{project_id}"


def scrub(text: str, token: str) -> str:
    return text.replace(token, REDACTED)


def fetch(project_id: str, dest: Path) -> str:
    """Clone or update the project into dest. Returns the HEAD SHA."""
    secret = token()
    remote = url(project_id)

    if (dest / ".git").is_dir():
        _run(["git", "pull", "--ff-only", remote], secret, cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", remote, str(dest)], secret, cwd=dest.parent)

    return _run(["git", "rev-parse", "HEAD"], secret, cwd=dest).strip()


def _run(args: list[str], secret: str, cwd: Path) -> str:
    env = _build_git_env()

    try:
        # errors="replace": git's stderr isn't guaranteed valid UTF-8;
        # undecodable bytes must not crash the subprocess call itself,
        # only the CalledProcessError path below.
        done = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True,
            encoding="utf-8", errors="replace", check=True,
        )
    except subprocess.CalledProcessError as exc:
        # Omit the chain: git's stderr and str(CalledProcessError) can carry
        # remote URLs and other diagnostic detail. Only the scrubbed message
        # (kept as a guard, though no production path taints it now) should
        # reach the user.
        raise OverleafError(scrub(exc.stderr or str(exc), secret)) from None

    return done.stdout


def _build_git_env() -> dict[str, str]:
    """The caller's environment, plus our GIT_CONFIG_* entries appended
    after any the caller already set, so neither side's entries are lost."""
    env = dict(os.environ)
    index = _config_count(env)

    for key, value in _GIT_CONFIG_ENTRIES:
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
        index += 1

    env["GIT_CONFIG_COUNT"] = str(index)
    env["GIT_TERMINAL_PROMPT"] = "0"

    return env


def _config_count(env: dict[str, str]) -> int:
    """Entries already reserved via GIT_CONFIG_COUNT; 0 if absent or bad."""
    try:
        return max(int(env.get("GIT_CONFIG_COUNT", 0)), 0)
    except ValueError:
        return 0
