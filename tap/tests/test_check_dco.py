"""Behavioral tests for `scripts/check-dco` (req-cicd-dco-signoff).

The DCO check gates every road to `main`, so its verdicts are load-bearing: a
false GREEN publishes uncertified work, and a false RED blocks a promote. Each
test builds a THROWAWAY git repository and runs the real script against it —
never the session repo — so the assertions exercise the shipped artifact end to
end (exit code included) rather than a reimplementation of its logic.

Covers the four dispositions the policy defines: signed passes, unsigned fails,
bot-authored is exempt, and an individual remediation commit retroactively
certifies an earlier unsigned commit without rewriting history.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_DCO = REPO_ROOT / "scripts" / "check-dco"

AUTHOR_NAME = "Ada Lovelace"
AUTHOR_EMAIL = "ada@example.com"


def _git(repo: Path, *args: str, **env: str) -> str:
    """Run a git command in `repo`, returning stdout (raises on failure)."""
    environ = {
        "GIT_AUTHOR_NAME": AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
        # Never let the developer's own hooks (core.hooksPath=.githooks, which
        # auto-stamps a trailer) reach these fixtures — an "unsigned" commit must
        # actually be unsigned for the negative cases to mean anything.
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        **env,
    }
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(repo), **environ},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repo with one base commit; `base` tags the check's base ref."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", AUTHOR_NAME)
    _git(tmp_path, "config", "user.email", AUTHOR_EMAIL)
    (tmp_path / "f.txt").write_text("base\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base", "--no-verify")
    _git(tmp_path, "tag", "base")
    return tmp_path


def _commit(repo: Path, message: str, *, signed: bool, author: str | None = None) -> str:
    """Add a commit; returns its full sha. `author` overrides the author identity."""
    (repo / "f.txt").write_text(message)
    _git(repo, "add", "-A")
    args = ["commit", "-q", "-m", message, "--no-verify"]
    if signed:
        args.append("-s")
    env = {}
    if author is not None:
        name, _, email = author.partition(" <")
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email.rstrip(">")}
    _git(repo, *args, **env)
    return _git(repo, "rev-parse", "HEAD")


def _check(repo: Path) -> subprocess.CompletedProcess[str]:
    """Run the real scripts/check-dco against the throwaway repo, base ref `base`."""
    return subprocess.run(
        ["bash", str(CHECK_DCO), "base"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


@pytest.mark.spec("req-cicd-dco-signoff-2")
def test_signed_commit_passes(repo: Path) -> None:
    _commit(repo, "signed work", signed=True)
    assert _check(repo).returncode == 0


@pytest.mark.spec("req-cicd-dco-signoff-3")
def test_unsigned_commit_fails(repo: Path) -> None:
    _commit(repo, "unsigned work", signed=False)
    result = _check(repo)
    assert result.returncode == 1
    assert "missing Signed-off-by" in result.stderr


@pytest.mark.spec("req-cicd-dco-signoff-2")
def test_bot_authored_commit_is_exempt(repo: Path) -> None:
    """A bot must not certify the DCO, so its unsigned commits cannot be violations."""
    _commit(repo, "bot bump", signed=False, author="renovate[bot] <bot@users.noreply.github.com>")
    assert _check(repo).returncode == 0


@pytest.mark.spec("req-cicd-dco-signoff-4")
def test_remediation_commit_certifies_earlier_unsigned_commit(repo: Path) -> None:
    """History stays intact: a later signed declaration certifies the earlier commit."""
    target = _commit(repo, "unsigned work", signed=False)
    _commit(
        repo,
        f"I, {AUTHOR_NAME} <{AUTHOR_EMAIL}>, hereby add my Signed-off-by to this commit: {target}",
        signed=True,
    )
    result = _check(repo)
    assert result.returncode == 0, result.stderr
    assert "remediated" in result.stdout


@pytest.mark.spec("req-cicd-dco-signoff-4")
def test_remediation_by_a_different_identity_is_rejected(repo: Path) -> None:
    """Individual remediation certifies your OWN work — not somebody else's."""
    target = _commit(repo, "unsigned work", signed=False)
    _commit(
        repo,
        f"I, Someone Else <else@example.com>, hereby add my Signed-off-by to this commit: {target}",
        signed=True,
        author="Someone Else <else@example.com>",
    )
    result = _check(repo)
    assert result.returncode == 1
    assert "missing Signed-off-by" in result.stderr
