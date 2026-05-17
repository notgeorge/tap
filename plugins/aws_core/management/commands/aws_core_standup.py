"""aws_core standup hook (proving ground): idempotently acquire Steampipe.

Implements `req-plugin-load-v0-standup-hook` for `aws_core` per
`plugins/aws_core/specs/spec-aws-steampipe-tooling.md`
(`req-aws-steampipe-tooling-standup`). Discovered by the generic
`manage.py plugin_standup` runner via the `<app_label>_standup` naming
convention; also runnable directly for debugging.

Idempotent: a fast pinned-state check (no network) on the hit path; on a
miss, fetch+sha256-verify the pinned linux/arm64 tarball via urllib,
extract the binary into the plugin-owned dir, `steampipe plugin install
aws` into a plugin-owned STEAMPIPE_INSTALL_DIR, and record state. Performs
no graph-state mutation. Everything lives under `plugins/aws_core/`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from plugins.aws_core.tooling import resolver

_PLUGIN_INSTALL_TIMEOUT = 900  # steampipe plugin install aws pulls a large plugin


class Command(BaseCommand):
    help = "aws_core standup: idempotently provision the plugin-owned Steampipe tool."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-provision even if the pinned state is already present.",
        )

    def handle(self, *args, **options) -> None:
        force: bool = options["force"]

        ok, expected, actual = resolver.platform_check()
        if not ok:
            raise CommandError(
                f"Platform mismatch: this build pins [{expected}] but the running platform is "
                f"{actual!r}. v0 ships a single pinned platform on purpose; multi-arch is a "
                f"recorded generalization seam (spec-aws-steampipe-tooling.md). Refusing to "
                f"install a wrong-arch binary."
            )

        if resolver.is_provisioned() and not force:
            state = resolver.read_state() or {}
            self.stdout.write(
                self.style.SUCCESS(
                    f"Steampipe already provisioned (steampipe {state.get('steampipe_version')}, "
                    f"aws plugin {state.get('aws_plugin_version')}). No action."
                )
            )
            return

        lock = resolver.load_lock()
        entry = lock["platforms"][actual]
        resolver.BIN_PATH.parent.mkdir(parents=True, exist_ok=True)
        resolver.INSTALL_DIR.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"Fetching steampipe {lock['steampipe_version']} ({actual}) …")
        with urllib.request.urlopen(entry["url"], timeout=180) as resp:
            blob = resp.read()

        if len(blob) != entry["size"]:
            raise CommandError(f"Size mismatch: got {len(blob)} bytes, lock expects {entry['size']}.")
        digest = hashlib.sha256(blob).hexdigest()
        if digest != entry["sha256"]:
            raise CommandError(f"sha256 mismatch: got {digest}, lock expects {entry['sha256']}. Aborting.")

        with tempfile.TemporaryDirectory() as td:
            tgz = Path(td) / "steampipe.tar.gz"
            tgz.write_bytes(blob)
            with tarfile.open(tgz, "r:gz") as tf:
                member = next((m for m in tf.getmembers() if m.name.rstrip("./") == "steampipe" or m.name.endswith("/steampipe")), None)
                if member is None:
                    names = [m.name for m in tf.getmembers()][:10]
                    raise CommandError(f"No 'steampipe' entry in tarball; members: {names}")
                extracted = tf.extractfile(member)
                if extracted is None:
                    raise CommandError("Could not read 'steampipe' from tarball.")
                resolver.BIN_PATH.write_bytes(extracted.read())
        resolver.BIN_PATH.chmod(0o755)
        self.stdout.write(self.style.SUCCESS(f"steampipe binary → {resolver.BIN_PATH}"))

        env = {
            **os.environ,
            "STEAMPIPE_INSTALL_DIR": str(resolver.INSTALL_DIR),
            "HOME": str(resolver.RUNTIME_DIR),
        }
        priv = resolver.subprocess_priv_kwargs()
        if priv:
            # The dropped uid must own everything it will read/write.
            resolver.chown_tree(resolver.RUNTIME_DIR)
        self.stdout.write("Installing the Steampipe AWS plugin (this can take a few minutes) …")
        proc = subprocess.run(  # noqa: S603
            [str(resolver.BIN_PATH), "plugin", "install", "aws"],
            env=env,
            capture_output=True,
            text=True,
            timeout=_PLUGIN_INSTALL_TIMEOUT,
            **priv,
        )
        if proc.returncode != 0:
            raise CommandError(
                f"`steampipe plugin install aws` failed (exit {proc.returncode}).\n"
                f"stdout: {proc.stdout[-1500:]}\nstderr: {proc.stderr[-1500:]}"
            )

        aws_version = self._resolve_aws_plugin_version(env, priv)

        resolver.STATE_PATH.write_text(
            json.dumps(
                {
                    "steampipe_version": lock["steampipe_version"],
                    "aws_plugin_version": aws_version,
                    "platform": actual,
                    "installed_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Steampipe provisioned: {lock['steampipe_version']}, aws plugin {aws_version}, "
                f"install dir {resolver.INSTALL_DIR}. State → {resolver.STATE_PATH}."
            )
        )

    def _resolve_aws_plugin_version(self, env: dict, priv: dict) -> str:
        """Best-effort resolved AWS-plugin version for the state file."""
        try:
            out = subprocess.run(  # noqa: S603
                [str(resolver.BIN_PATH), "plugin", "list", "--output", "json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                **priv,
            )
            data = json.loads(out.stdout or "{}")
            items = data.get("installed") or data.get("plugins") or data if isinstance(data, list) else data.get("installed", [])
            for item in items if isinstance(items, list) else []:
                name = str(item.get("name", ""))
                if "aws" in name:
                    return str(item.get("version") or "unknown")
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
        return "unknown"
