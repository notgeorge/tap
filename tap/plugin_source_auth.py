"""Settings-free git-source credential resolution for the pre-boot plugin install.

The private-repo half of the ``git`` source (`req-plugin-arch-sources-2`): a
profile's ``install`` entry may name a source-scoped credential, which pre-boot
resolves and hands to ``git`` **via ``GIT_ASKPASS``, never in the URL** — a token
in the URL leaks into the venv's ``direct_url.json`` (`req-plugin-arch-source-secret-4`).

Design constraints (why this lives in ``tap/`` next to ``runtime_secrets`` and
``preboot``, not in ``tap_plugins`` or ``tap_cares``):

- **Settings-free / no ``tap_*`` import** — pre-boot runs before Django is
  configured (`req-boot-preboot`). This module imports only stdlib +
  ``tap.runtime_secrets`` (the shared, app-neutral resolver) + ``tap.jsonfiles``.
- **Consumer-first scope ``tap_plugins/source``** (`req-plugin-arch-source-secret-2`):
  the credential belongs to the install *system*, never to a plugin — a plugin
  must never resolve the credential that installs its siblings.
- **Conditional necessity** (`req-plugin-arch-source-secret-5`): a credential is
  required only when a git source *declares* one — the ``credential`` key IS the
  declaration. An ``editable``/``path`` source, or a public git source with no
  ``credential``, needs none and resolves to ``None`` here. There is no implicit
  default key: a private repo names its credential explicitly, so the store never
  silently satisfies a source by file-presence.
- **Per-source selection** (`req-plugin-arch-source-secret-6`): a git entry's
  optional ``credential`` names *which* secret key (under scope
  ``tap_plugins/source``) to use, so plugins can be pulled from different private
  repos/orgs in one profile — a repo's PAT never sees another repo.

The token is returned in memory only and never logged: :class:`GitCredential`'s
``__repr__`` omits it, and :func:`git_askpass_env` passes it to the child process
through the environment (owner-only ``/proc/<pid>/environ``), not through the
argument list preboot logs.
"""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tap.jsonfiles import JsonFileError, validate_json
from tap.runtime_secrets import RuntimeSecretError, resolve_secret_envelope

# The install-system credential scope — owned by the install system, never a
# plugin (req-plugin-arch-source-secret-2). Every source credential lives here.
SOURCE_SECRET_SCOPE = "tap_plugins/source"

# The one kind a source credential may declare — shared type-axis with the
# github_core collector, but a different data_schema (req-plugin-arch-source-secret-1).
GITHUB_PAT_KIND = "github_pat"

DEFAULT_HOST = "github.com"
DEFAULT_USERNAME = "x-access-token"

_DATA_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "github_pat_source_secret.schema.json"


class SourceAuthError(Exception):
    """A declared git-source credential could not be resolved or is malformed.

    Raised only when a git source *declares* a ``credential`` that cannot be honored
    (absent store, missing secret, wrong kind, malformed data). A git source with no
    ``credential`` is public and never raises (`req-plugin-arch-source-secret-5`).
    """


@dataclass(frozen=True)
class GitCredential:
    """A resolved git HTTPS credential, fed to git via ``GIT_ASKPASS``.

    ``__repr__`` omits ``token`` so an instance interpolated into a log line or
    traceback cannot leak the secret.
    """

    token: str
    host: str
    username: str

    def __repr__(self) -> str:
        return f"GitCredential(host={self.host!r}, username={self.username!r}, token=<redacted>)"


def credential_ref_for_source(source: Mapping[str, Any]) -> str | None:
    """Return the credential KEY a git source declares, or ``None``.

    A git source with a ``credential`` key is private (that key is required). A git
    source without one is public (no auth); ``editable``/``path``/non-git sources
    never carry an install credential. There is no implicit default key — a private
    repo names its credential explicitly (`req-plugin-arch-source-secret-6`).
    """
    if not isinstance(source, Mapping) or source.get("type") != "git":
        return None
    declared = source.get("credential")
    return str(declared) if declared is not None else None


def resolve_git_credential(secrets_root: Path | None, source: Mapping[str, Any]) -> GitCredential | None:
    """Resolve the credential for one install ``source``, honoring conditional necessity.

    Returns ``None`` when no auth applies — a non-git source, or a git source with no
    ``credential`` key (public repo). Raises :class:`SourceAuthError` when a declared
    credential cannot be honored: the store is absent, the secret is missing, or it is
    of the wrong kind / malformed data. The ``credential`` key IS the declaration that
    makes it required (`req-plugin-arch-source-secret-5`).

    Args:
        secrets_root: The ``TAP_SECRETS_ROOT`` directory, or ``None`` when unset.
        source: One profile ``install`` entry's ``source`` mapping.
    """
    key = credential_ref_for_source(source)
    if key is None:
        return None

    if secrets_root is None:
        raise SourceAuthError(
            f"git source declares credential '{key}' but TAP_SECRETS_ROOT is not set; "
            f"mount the secrets store or remove the 'credential' field for a public repo"
        )

    try:
        envelope = resolve_secret_envelope(secrets_root, SOURCE_SECRET_SCOPE, key)
    except RuntimeSecretError as exc:
        raise SourceAuthError(
            f"git source declares credential '{key}' but it could not be resolved "
            f"(scope '{SOURCE_SECRET_SCOPE}'): {exc}"
        ) from exc

    if envelope.kind != GITHUB_PAT_KIND:
        raise SourceAuthError(
            f"source credential '{SOURCE_SECRET_SCOPE}:{key}' has kind '{envelope.kind}', "
            f"expected '{GITHUB_PAT_KIND}'"
        )

    try:
        validate_json(dict(envelope.data), _DATA_SCHEMA_PATH, source=envelope.source_path)
    except JsonFileError as exc:
        raise SourceAuthError(
            f"source credential '{SOURCE_SECRET_SCOPE}:{key}' has a malformed data block: {exc}"
        ) from exc

    data = envelope.data
    return GitCredential(
        token=str(data["token"]),
        host=str(data.get("host", DEFAULT_HOST)),
        username=str(data.get("username", DEFAULT_USERNAME)),
    )


# The GIT_ASKPASS helper git invokes. git calls it with a single argument — the
# prompt string ("Username for '...': " / "Password for '...': ") — and reads the
# answer from stdout. The script carries NO secret; it echoes the username/token
# the env overlay supplies, so the token never touches the filesystem.
_ASKPASS_SCRIPT = (
    "#!/bin/sh\n"
    'case "$1" in\n'
    '  Username*) printf "%s" "$TAP_GIT_USERNAME" ;;\n'
    '  *)         printf "%s" "$TAP_GIT_PASSWORD" ;;\n'
    "esac\n"
)


@contextmanager
def git_askpass_env(cred: GitCredential) -> Iterator[dict[str, str]]:
    """Yield an env overlay that feeds ``cred`` to git via ``GIT_ASKPASS``.

    Writes a short-lived, owner-only (``0700``) askpass script that reads the
    username/token from the environment, and yields the env keys to merge into the
    install subprocess. The token rides in ``TAP_GIT_PASSWORD`` (child env only),
    never in the URL or the script body. ``GIT_TERMINAL_PROMPT=0`` forbids an
    interactive fallback so a bad/absent credential fails fast instead of hanging.
    The script is deleted on exit.
    """
    fd, path = tempfile.mkstemp(prefix="tap-askpass-", suffix=".sh")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(_ASKPASS_SCRIPT)
        os.chmod(path, stat.S_IRWXU)  # rwx------ : only this user runs it
        yield {
            "GIT_ASKPASS": path,
            "GIT_TERMINAL_PROMPT": "0",
            "TAP_GIT_USERNAME": cred.username,
            "TAP_GIT_PASSWORD": cred.token,
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


__all__ = [
    "SOURCE_SECRET_SCOPE",
    "GITHUB_PAT_KIND",
    "DEFAULT_HOST",
    "DEFAULT_USERNAME",
    "SourceAuthError",
    "GitCredential",
    "credential_ref_for_source",
    "resolve_git_credential",
    "git_askpass_env",
]
