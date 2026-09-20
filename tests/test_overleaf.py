import os
import subprocess

import pytest

from pubs import overleaf
from pubs.errors import OverleafError

TOKEN = "olp_secret123"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _commit(repo, text):
    (repo / "main.tex").write_text(text)
    _git("add", "-A", cwd=repo)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x", cwd=repo)


@pytest.fixture
def remote(tmp_path):
    """A local git repo standing in for an Overleaf project."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", "-b", "main", cwd=origin)
    _commit(origin, "\\documentclass{article}\n\\begin{document}x\\end{document}\n")

    return origin


def test_url_is_tokenless():
    assert overleaf.url("abc123") == f"https://{overleaf.GIT_HOST}/abc123"


def test_scrub_removes_every_occurrence():
    text = f"fatal: https://git:{TOKEN}@git.overleaf.com/abc failed, token {TOKEN}"

    scrubbed = overleaf.scrub(text, TOKEN)

    assert TOKEN not in scrubbed
    assert scrubbed.count("***") == 2


def test_token_missing_from_environment(monkeypatch):
    monkeypatch.delenv(overleaf.TOKEN_ENV, raising=False)

    with pytest.raises(OverleafError, match=overleaf.TOKEN_ENV):
        overleaf.token()


def test_fetch_clones_then_pulls(tmp_path, remote, monkeypatch):
    monkeypatch.setattr(overleaf, "url", lambda project_id: str(remote))
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    dest = tmp_path / "work" / "2027-x"

    first = overleaf.fetch("abc123", dest)

    assert (dest / "main.tex").is_file()
    assert len(first) == 40

    # A second call must update in place, not fail on the existing directory.
    assert overleaf.fetch("abc123", dest) == first


def test_fetch_scrubs_the_token_from_failures(tmp_path, monkeypatch):
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    # A local path that does not exist makes git fail without any network,
    # and carries the token into the error message git prints back.
    monkeypatch.setattr(
        overleaf, "url",
        lambda project_id: f"{tmp_path}/missing-{TOKEN}",
    )

    with pytest.raises(OverleafError) as caught:
        overleaf.fetch("does-not-exist", tmp_path / "dest")

    assert TOKEN not in str(caught.value)
    assert "***" in str(caught.value)


def test_scrub_fallback_on_empty_stderr(tmp_path, monkeypatch):
    """When git writes no stderr, str(CalledProcessError) must be scrubbed."""
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)

    def stub_run(*args, **kwargs):
        # Simulate git failure with empty stderr (e.g., permission denied).
        exc = subprocess.CalledProcessError(1, ["git", "clone", f"https://git:{TOKEN}@git.overleaf.com/xyz"])
        exc.stderr = ""
        raise exc

    monkeypatch.setattr(subprocess, "run", stub_run)

    with pytest.raises(OverleafError) as caught:
        overleaf.fetch("xyz", tmp_path / "dest")

    assert TOKEN not in str(caught.value)
    assert "***" in str(caught.value)


def test_fetch_survives_undecodable_stderr(tmp_path, monkeypatch):
    """git stderr that isn't valid UTF-8 must not crash subprocess.run;
    the normal CalledProcessError path should still run and scrub the
    token from the message."""
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)

    # A fake "git" on PATH: writes the token plus an invalid UTF-8 byte
    # (0xe1) to stderr and exits non-zero. No real git or network involved.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_git = bin_dir / "git"
    fake_git.write_text(f"#!/bin/sh\nprintf 'token {TOKEN} bad byte \\341 end\\n' >&2\nexit 1\n")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    with pytest.raises(OverleafError) as caught:
        overleaf.fetch("abc123", tmp_path / "dest")

    assert TOKEN not in str(caught.value)
    assert "***" in str(caught.value)


def test_fetch_keeps_token_out_of_argv_and_env(tmp_path, monkeypatch):
    """The token must reach git only via OVERLEAF_GIT_TOKEN, never argv or another env var."""
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(overleaf, "url", lambda project_id: "https://example.invalid/abc")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs["env"]))
        return subprocess.CompletedProcess(args, 0, stdout="deadbeef\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    overleaf.fetch("abc123", tmp_path / "dest")

    assert calls  # fetch made at least one git call

    for args, env in calls:
        assert all(TOKEN not in arg for arg in args)

        for key, value in env.items():
            if key == overleaf.TOKEN_ENV:
                continue
            assert TOKEN not in value

        assert env["GIT_TERMINAL_PROMPT"] == "0"
        count = int(env["GIT_CONFIG_COUNT"])
        values = [env[f"GIT_CONFIG_VALUE_{i}"] for i in range(count)]

        # Reset entry ("") must precede the real helper, so it discards
        # any credential.helper inherited from the caller's own git config.
        assert values.index("") < values.index(overleaf.CREDENTIAL_HELPER)


def test_fetch_preserves_callers_git_config_entries(tmp_path, monkeypatch):
    """A caller's own GIT_CONFIG_* entries must survive alongside ours."""
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(overleaf, "url", lambda project_id: "https://example.invalid/abc")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "caller.setting")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "keep-me")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(kwargs["env"])
        return subprocess.CompletedProcess(args, 0, stdout="deadbeef\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    overleaf.fetch("abc123", tmp_path / "dest")

    for env in calls:
        assert env["GIT_CONFIG_KEY_0"] == "caller.setting"
        assert env["GIT_CONFIG_VALUE_0"] == "keep-me"
        assert int(env["GIT_CONFIG_COUNT"]) == 3

        keys = [env[f"GIT_CONFIG_KEY_{i}"] for i in range(1, 3)]
        values = [env[f"GIT_CONFIG_VALUE_{i}"] for i in range(1, 3)]

        assert keys == ["credential.helper", "credential.helper"]
        assert values == ["", overleaf.CREDENTIAL_HELPER]


def test_fetch_pull_reflects_a_pushed_commit_without_leaking_token(tmp_path, monkeypatch):
    """End to end against a real local remote: pull fast-forwards, token stays out of .git."""
    monkeypatch.setenv(overleaf.TOKEN_ENV, TOKEN)

    bare = tmp_path / "origin.git"
    _git("init", "-q", "--bare", "-b", "main", str(bare), cwd=tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-q", "-b", "main", cwd=seed)
    _commit(seed, "\\documentclass{article}\n\\begin{document}x\\end{document}\n")
    _git("push", "-q", str(bare), "main", cwd=seed)

    monkeypatch.setattr(overleaf, "url", lambda project_id: str(bare))
    dest = tmp_path / "work" / "2027-x"
    first = overleaf.fetch("abc123", dest)

    # Push a second commit to the remote, as an Overleaf edit would produce.
    _commit(seed, "\\documentclass{article}\n\\begin{document}y\\end{document}\n")
    _git("push", "-q", str(bare), "main", cwd=seed)
    pushed = subprocess.run(
        ["git", "rev-parse", "main"], cwd=seed, capture_output=True, text=True, check=True,
    ).stdout.strip()

    second = overleaf.fetch("abc123", dest)

    assert second == pushed
    assert second != first

    for path in (dest / ".git").rglob("*"):
        if path.is_file():
            assert TOKEN.encode() not in path.read_bytes()
