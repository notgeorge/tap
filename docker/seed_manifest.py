"""Wheel-cache seed manifest — generate and verify (req-cicd-supply-chain-provenance-2).

The web image ships a pre-compiled uv wheel cache (/opt/uv-cache-seed, Dockerfile
deps-warm stage). Build-time inputs are verified by uv.lock hashes and the build is
attested — but the boot-time seed copy was a bare `cp`, and a warm-cache `uv sync`
does NOT re-verify hashes on cache hits. This module closes that gap:

* `generate` runs INSIDE the attested image build (deps-warm) and writes a per-file
  sha256 manifest of the seed tree, keyed by RELATIVE POSIX path — the seed is
  generated under /root/.cache/uv and verified under /opt/uv-cache-seed, so absolute
  paths would never match. The manifest is written OUTSIDE the tree (enforced), so it
  never lists itself.
* `verify` runs in docker/entrypoint.sh BEFORE seeding an empty uv-cache volume, as a
  FULL BIDIRECTIONAL reconciliation: hash mismatches, files missing from the seed,
  and extra unmanifested files are all failures — a partial or padded seed must not
  pass as "mostly fine". On success it emits one machine-legible boot-evidence line.

Semantics split by presence (spec): an ABSENT seed may degrade cleanly (uv falls back
to lock-hash-verified downloads/compiles); a PRESENT-but-invalid seed is a fail-closed
boot abort — inside an immutable image that means corruption or tamper, never
staleness. The abort itself is the entrypoint's job (emit_abort); this module only
reports.

Runs under bare in-container python3 BEFORE `uv sync` creates the venv, so it MUST
stay stdlib-only (guarded by tap/tests/test_boot_pointer.py's import-graph walk).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MANIFEST_FORMAT = "tap-seed-manifest/1"
_CHUNK = 1 << 20


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_files(tree: Path) -> dict[str, str]:
    """Hash every regular file under tree, keyed by relative POSIX path."""
    files: dict[str, str] = {}
    for path in sorted(tree.rglob("*")):
        if path.is_file():
            files[path.relative_to(tree).as_posix()] = _sha256_file(path)
    return files


def generate(tree: Path, out: Path) -> dict[str, object]:
    """Write the manifest for tree to out (which MUST lie outside tree)."""
    tree = tree.resolve()
    out = out.resolve()
    if not tree.is_dir():
        raise ValueError(f"seed tree does not exist or is not a directory: {tree}")
    if out.is_relative_to(tree):
        raise ValueError(f"manifest path {out} is inside the tree it describes — it would list itself")
    manifest: dict[str, object] = {
        "format": MANIFEST_FORMAT,
        "_description": (
            "Per-file sha256 manifest of the image's uv wheel-cache seed, generated inside "
            "the attested image build and verified by the entrypoint before seeding an empty "
            "cache volume (req-cicd-supply-chain-provenance-2). Keys are POSIX paths relative "
            "to the seed root; the manifest lives outside the tree and never lists itself."
        ),
        "files": _walk_files(tree),
    }
    out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify(tree: Path, manifest_path: Path) -> list[str]:
    """Full bidirectional reconciliation; returns failures (empty = valid)."""
    if not manifest_path.is_file():
        return [f"manifest missing: {manifest_path} (a seed without its manifest is invalid, not stale)"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest["files"]
        fmt = manifest["format"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"manifest unreadable: {exc}"]
    if fmt != MANIFEST_FORMAT:
        return [f"manifest format {fmt!r} != expected {MANIFEST_FORMAT!r}"]
    if not tree.is_dir():
        return [f"seed tree missing: {tree}"]

    actual = _walk_files(tree)
    failures: list[str] = []
    for rel in sorted(set(declared) - set(actual)):
        failures.append(f"MISSING from seed: {rel}")
    for rel in sorted(set(actual) - set(declared)):
        failures.append(f"EXTRA unmanifested file: {rel}")
    for rel in sorted(set(declared) & set(actual)):
        if declared[rel] != actual[rel]:
            failures.append(f"HASH MISMATCH: {rel}")
    return failures


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "generate":
        generate(Path(argv[2]), Path(argv[3]))
        return 0
    if len(argv) == 4 and argv[1] == "verify":
        failures = verify(Path(argv[2]), Path(argv[3]))
        if failures:
            for line in failures:
                print(f"seed-verify: {line}", file=sys.stderr)
            print(f"seed-verify: FAILED ({len(failures)} problem(s))", file=sys.stderr)
            return 1
        count = len(json.loads(Path(argv[3]).read_text(encoding="utf-8"))["files"])
        # Machine-legible boot evidence (req-cicd-supply-chain-provenance-2): emitted
        # here, pre-tap.preboot; the boot-record surface absorbs it when available.
        print(json.dumps({"tap_boot_evidence": "seed-verify", "result": "ok", "files": count}))
        return 0
    print("usage: seed_manifest.py generate <tree> <out-manifest> | verify <tree> <manifest>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
