"""aws_core-internal Steampipe tool resolver (proving ground).

Resolves the plugin-owned Steampipe binary + writable install dir from
`plugins/aws_core/tooling/`, never system PATH. The collector and the
collector self-test use this; nothing here provisions (provisioning is the
`aws_core_standup` management command). See
`plugins/aws_core/specs/spec-aws-steampipe-tooling.md`
(`req-aws-steampipe-tooling-resolution`, `-platform`).

Deliberately aws_core-local: promoting this to a shared `tap_plugins`
tool-resolver is a recorded generalization seam, not built here.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

# Steampipe refuses to run as root (hard guard). The dev container runs as
# root, so steampipe subprocesses are dropped to an unprivileged uid and the
# plugin-owned runtime dir is chowned to it. Single source of truth for both
# `aws_core_standup` (install) and the collector runner (query). Recorded
# generalization seam: "tool refuses root -> standup/runner drop privileges
# and own their dirs as that uid" (req-aws-steampipe-tooling-seams).
DROP_UID = 65534  # nobody
DROP_GID = 65534  # nogroup (Debian)

TOOLING_DIR = Path(__file__).resolve().parent
LOCK_PATH = TOOLING_DIR / "steampipe.lock.json"
RUNTIME_DIR = TOOLING_DIR / "_runtime"
BIN_PATH = RUNTIME_DIR / "bin" / "steampipe"
INSTALL_DIR = RUNTIME_DIR / "install"
STATE_PATH = RUNTIME_DIR / "state.json"


def load_lock() -> dict:
    return json.loads(LOCK_PATH.read_text())


def current_platform() -> str:
    """Return TAP's `<os>/<arch>` key, mapping uname arch to release arch."""
    system = platform.system().lower()  # "linux"
    machine = platform.machine().lower()  # "aarch64" | "x86_64" | ...
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(machine, machine)
    return f"{system}/{arch}"


def platform_check() -> tuple[bool, str, str]:
    """(_matches_, expected_pinned_platform, actual_platform).

    v0 pins exactly one platform; any mismatch is a loud failure, never a
    silently wrong binary (`req-aws-steampipe-tooling-platform-2`).
    """
    pinned = list(load_lock()["platforms"].keys())
    actual = current_platform()
    return (actual in pinned, ", ".join(pinned), actual)


def read_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text())
    except (ValueError, OSError):
        return None


def is_provisioned() -> bool:
    """Fast, exact hit-path check — no binary exec, no network.

    Source of truth is the state file `aws_core_standup` writes only after a
    verified install, so this stays cheap enough to run on every stand-up
    and inside the (pure) self-test.
    """
    lock = load_lock()
    state = read_state()
    if state is None:
        return False
    if not (BIN_PATH.exists() and BIN_PATH.is_file()):
        return False
    if state.get("steampipe_version") != lock.get("steampipe_version"):
        return False
    if not state.get("aws_plugin_version"):
        return False
    return state.get("platform") == current_platform()


def steampipe_binary() -> Path | None:
    """Plugin-owned binary path, or None if not provisioned at the pinned state."""
    return BIN_PATH if is_provisioned() else None


def runtime_env() -> dict[str, str]:
    """Env that points Steampipe at the plugin-owned writable dirs."""
    return {
        "STEAMPIPE_INSTALL_DIR": str(INSTALL_DIR),
        "HOME": str(RUNTIME_DIR),
    }


def subprocess_priv_kwargs() -> dict:
    """`subprocess.run` kwargs to drop to an unprivileged uid when running as root."""
    if os.geteuid() == 0:
        return {"user": DROP_UID, "group": DROP_GID}
    return {}


def chown_tree(root: Path, uid: int = DROP_UID, gid: int = DROP_GID) -> None:
    """Recursively chown a tree (best-effort) so the dropped uid owns it."""
    try:
        os.chown(root, uid, gid)
    except OSError:
        pass
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            try:
                os.chown(os.path.join(dirpath, name), uid, gid)
            except OSError:
                pass
