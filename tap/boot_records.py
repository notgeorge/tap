"""Referrer-held integrity digests for in-package boot records (spec-tap-boot-bootstrap).

A shippable boot record lives *inside* its plugin package at
``tap_plugin/<slug>/boot/<name>.boot.json`` (``req-boot-bootstrap-records-in-package``)
and rides the wheel/git artifact. Its integrity is a content ``sha256`` declared **one
layer up** — in the package ``tap-plugin.toml``'s ``[[boot.records]]`` table
(``req-boot-bootstrap-record-version``) — never inside the record itself (a thing never
contains its own hash; the wheel-``RECORD`` / OCI-manifest pattern). A content hash is a
fixed point, so this is non-circular: editing a record changes only *its* digest, and the
digest is regenerated through this derivation, never hand-typed
(the derived-vs-declared lesson from the uuid5 seed-id drift).

This module is settings-free and stdlib-only (``tomllib``/``json``/``hashlib``), so it runs
on the host (``scripts/boot-record-hash``) and in the ``tap/tests/test_boot_records.py``
guard, which fails closed on digest drift or a manifest<->files mismatch (both directions).
It lives in ``tap/`` — infrastructure beneath any plugin, no ``tap_*`` app dependency.

CLI (``python -m tap.boot_records``):
    (default)     print discovered records + computed digests
    --check       verify declared == computed + manifest<->files bijection; exit 1 on drift
    --refresh     rewrite the ``sha256`` values in each package ``tap-plugin.toml``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tap.boot_naming import RECORD_SUFFIX

__all__ = [
    "REPO_ROOT",
    "RECORD_SUFFIX",
    "canonical_digest_bytes",
    "canonical_digest",
    "discover",
    "check",
    "refresh",
    "main",
]

# tap/boot_records.py -> repo root is two parents up (holds plugins/, tap/).
REPO_ROOT = Path(__file__).resolve().parent.parent

# RECORD_SUFFIX is imported above from its home, the stdlib-only naming leaf
# (tap/boot_naming.py), and re-exported here for existing consumers.

# Globs for a plugin package's in-package boot dir, one per supported layout:
#   plugins/<dir>/tap_plugin/<slug>/boot/       — monorepo-era in-tree plugins
#   _dev-plugins/<dir>/tap_plugin/<slug>/boot/  — plugin-workspace dev checkouts
#     (spec-dev-plugin-workspace.md). Without this sweep, a fork author editing
#     their checkout's in-package record (the external-adopter cutover flow)
#     could not run the MANDATORY digest derivation the toml points them at —
#     `scripts/boot-record-hash --refresh` simply couldn't see the file.
#     CI never has _dev-plugins, so its behavior is unchanged; a worktree WITH
#     dev checkouts now also gets their digests coherence-checked (desirable:
#     a stale digest in a checkout should be loudly visible).
_BOOT_DIR_GLOBS = (
    "plugins/*/tap_plugin/*/boot",
    "_dev-plugins/*/tap_plugin/*/boot",
)


@dataclass(frozen=True)
class RecordFile:
    """A boot record on the filesystem plus its computed canonical digest."""

    slug: str
    name: str  # record selector: filename with RECORD_SUFFIX stripped
    path: Path
    digest: str


@dataclass(frozen=True)
class PluginBootManifest:
    """One plugin's in-package boot records (filesystem) vs its declared digests (toml)."""

    slug: str
    toml_path: Path
    boot_dir: Path
    files: dict[str, RecordFile]  # name -> RecordFile (source of truth)
    declared: dict[str, str]  # name -> declared sha256 (from [[boot.records]])


def canonical_digest_bytes(raw: bytes) -> str:
    """SHA-256 over the canonicalized record bytes (sorted keys, tight separators).

    Canonicalization means cosmetic reformatting (indent, key order) does not move the
    digest; only real content changes do. The record never contains its own hash, so there
    is no self-reference to exclude. Bytes-first so a record fetched out of an artifact
    (``tap.boot_pointer`` stage-0) hashes identically to one read off disk.
    """
    data = json.loads(raw.decode("utf-8"))
    canon = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def canonical_digest(path: Path) -> str:
    """SHA-256 over the canonicalized record at ``path`` (see :func:`canonical_digest_bytes`)."""
    return canonical_digest_bytes(path.read_bytes())


def _declared_records(toml_path: Path) -> dict[str, str]:
    """Read ``{name: sha256}`` from a package toml's ``[[boot.records]]`` table."""
    if not toml_path.is_file():
        return {}
    with open(toml_path, "rb") as fh:
        loaded = tomllib.load(fh)
    records = (loaded.get("boot") or {}).get("records") or []
    out: dict[str, str] = {}
    for rec in records:
        name = rec.get("name")
        if isinstance(name, str):
            out[name] = rec.get("sha256", "") if isinstance(rec.get("sha256", ""), str) else ""
    return out


def discover(repo_root: Path = REPO_ROOT) -> list[PluginBootManifest]:
    """Find every plugin package that ships in-package boot records."""
    manifests: list[PluginBootManifest] = []
    boot_dirs = sorted({p for pattern in _BOOT_DIR_GLOBS for p in repo_root.glob(pattern)})
    for boot_dir in boot_dirs:
        if not boot_dir.is_dir():
            continue
        slug = boot_dir.parent.name  # tap_plugin/<slug>/boot -> <slug>
        toml_path = boot_dir.parent / "tap-plugin.toml"
        files: dict[str, RecordFile] = {}
        for record_path in sorted(boot_dir.glob(f"*{RECORD_SUFFIX}")):
            name = record_path.name[: -len(RECORD_SUFFIX)]
            files[name] = RecordFile(slug=slug, name=name, path=record_path, digest=canonical_digest(record_path))
        manifests.append(
            PluginBootManifest(
                slug=slug,
                toml_path=toml_path,
                boot_dir=boot_dir,
                files=files,
                declared=_declared_records(toml_path),
            )
        )
    return manifests


def check(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return a list of problems; empty means every declared digest matches + is coherent.

    Fails closed both directions: a record file with no ``[[boot.records]]`` entry, an
    entry with no file, an empty/placeholder digest, or a digest that no longer matches the
    record's content.
    """
    problems: list[str] = []
    for man in discover(repo_root):
        file_names = set(man.files)
        declared_names = set(man.declared)

        for name in sorted(file_names - declared_names):
            problems.append(
                f"{man.slug}: record 'boot/{name}{RECORD_SUFFIX}' has no [[boot.records]] entry in "
                f"{man.toml_path.name} (add name + description, then `scripts/boot-record-hash --refresh`)."
            )
        for name in sorted(declared_names - file_names):
            problems.append(
                f"{man.slug}: [[boot.records]] declares '{name}' but no 'boot/{name}{RECORD_SUFFIX}' exists "
                f"(remove the entry or add the record file)."
            )
        for name in sorted(file_names & declared_names):
            computed = man.files[name].digest
            declared = man.declared[name]
            if not declared:
                problems.append(
                    f"{man.slug}: record '{name}' has an empty sha256 in {man.toml_path.name} — "
                    f"run `scripts/boot-record-hash --refresh` (expected {computed})."
                )
            elif declared != computed:
                problems.append(
                    f"{man.slug}: record '{name}' content changed — declared sha256 {declared} != computed "
                    f"{computed}. Rerun `scripts/boot-record-hash --refresh` (never hand-edit the digest)."
                )
    return problems


_NAME_RE = re.compile(r'^\s*name\s*=\s*"(?P<name>[^"]*)"\s*$')
_SHA_RE = re.compile(r'^(?P<pre>\s*sha256\s*=\s*")(?P<val>[^"]*)(?P<post>".*)$')
_TABLE_RE = re.compile(r"^\s*\[")


def _rewrite_toml_digests(text: str, digests: dict[str, str]) -> str:
    """Replace the ``sha256`` value in each ``[[boot.records]]`` block by its record ``name``.

    Assumes the controlled authored format (``name`` precedes ``sha256`` within a block).
    Any table header line ends the current record block's context.
    """
    lines = text.splitlines(keepends=True)
    in_records = False
    current: str | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[[boot.records]]":
            in_records = True
            current = None
            continue
        if _TABLE_RE.match(line) and stripped != "[[boot.records]]":
            in_records = False
            current = None
            continue
        if not in_records:
            continue
        m_name = _NAME_RE.match(line)
        if m_name:
            current = m_name.group("name")
            continue
        m_sha = _SHA_RE.match(line)
        if m_sha and current is not None and current in digests:
            lines[i] = (
                f"{m_sha.group('pre')}{digests[current]}{m_sha.group('post')}\n"
                if line.endswith("\n")
                else (f"{m_sha.group('pre')}{digests[current]}{m_sha.group('post')}")
            )
    return "".join(lines)


def refresh(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Rewrite each package toml's ``[[boot.records]]`` ``sha256`` to the computed digests.

    Returns the list of toml paths actually changed.
    """
    changed: list[Path] = []
    for man in discover(repo_root):
        if not man.toml_path.is_file():
            continue
        digests = {name: rf.digest for name, rf in man.files.items()}
        text = man.toml_path.read_text(encoding="utf-8")
        new_text = _rewrite_toml_digests(text, digests)
        if new_text != text:
            man.toml_path.write_text(new_text, encoding="utf-8")
            changed.append(man.toml_path)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tap.boot_records", description="Boot-record integrity digests.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="verify declared == computed (exit 1 on drift)")
    group.add_argument("--refresh", action="store_true", help="rewrite sha256 digests in each package toml")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="discovery root holding plugins/ and/or _dev-plugins/ (default: this repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    if args.refresh:
        changed = refresh(root)
        for path in changed:
            try:
                shown = path.relative_to(root)
            except ValueError:
                shown = path
            print(f"refreshed {shown}")
        if not changed:
            print("no digest changes")
        return 0

    if args.check:
        problems = check(root)
        for p in problems:
            print(p, file=sys.stderr)
        if problems:
            print(f"{len(problems)} boot-record integrity problem(s)", file=sys.stderr)
            return 1
        print("boot records: all digests match, manifests coherent")
        return 0

    # Default: list discovered records + computed digests.
    for man in discover(root):
        for name, rf in man.files.items():
            print(f"{man.slug}#{name}\t{rf.digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
