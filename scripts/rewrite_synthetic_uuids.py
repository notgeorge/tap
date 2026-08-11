#!/usr/bin/env python3
"""One-shot rewrite of hand-shaped UUIDv7 seed IDs to organic uuid.uuid7().

See tap_grid/specs/spec-grift-seed-ids-real-uuid7.md (req-grift-seed-ids-rewrite).
Parented by tap_grid/specs/spec-grid-uuid-selection.md.

Two patterns are detected and rewritten:

1. Strict synthetic v7: ``xxxxxxxx-xxxx-7000-8000-xxxxxxxxxxxx`` (zeroed rand_a
   and zeroed high bits of rand_b).
2. Per-batch shared prefix v7: any group of >=2 v7-shaped UUIDs in a single
   grift file that share their first 18 hex characters (timestamp + version +
   rand_a + variant + high bits of rand_b).

Every distinct hand-shaped ID found is mapped to one freshly minted
uuid.uuid7(); the map is then applied verbatim everywhere it appears across
all grift files (entity_id, from/to_entity_id, in-payload references like
default_elevation_id, layouts, search_id, etc.) plus a small set of
non-grift docs that quote synthetic UUIDs.

Explicitly excluded from detection:

- The grandfathered KSI namespace UUID at
  plugins/fedramp_20x_ksi/skills/refresh-ksi-catalog/pinned/uuid_namespace.txt
  and any v5-derived UUIDs that descend from it (KSI grift entity IDs use
  version nibble != 7 and are filtered out by the v7-shape regex).

Run from the repo root::

    python3 scripts/rewrite_synthetic_uuids.py

Outputs scripts/uuid-rewrite-map.json containing the full old->new map.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRIFT_GLOB = "plugins/*/grift/*.grift.json"
EXTRA_TARGETS = [
    REPO_ROOT / "plugins/aws_core/skills/refresh-aws-catalog/SKILL.md",
]
SIDECAR = REPO_ROOT / "scripts/uuid-rewrite-map.json"

# Any version-7 UUID. Matches both organic and hand-shaped v7s; we filter
# afterwards to decide which to rewrite.
V7_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
STRICT_SYNTHETIC_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-7000-8000-[0-9a-f]{12}\b")


def shared_prefix_key(u: str) -> str:
    """First 18 hex chars (timestamp + version+rand_a + variant+high-rand_b)."""
    parts = u.split("-")
    return parts[0] + parts[1] + parts[2] + parts[3]


def collect_handshaped_ids(files: list[Path]) -> set[str]:
    """Find all hand-shaped v7 UUIDs across files.

    A v7 UUID is hand-shaped if it matches the strict synthetic pattern, OR if
    >=2 v7 UUIDs in the same file share the same 18-hex prefix (per-batch
    shared-prefix pattern).
    """
    handshaped: set[str] = set()
    for f in files:
        text = f.read_text()
        v7s = set(V7_RE.findall(text))

        # Strict synthetic.
        for u in v7s:
            if STRICT_SYNTHETIC_RE.fullmatch(u):
                handshaped.add(u)

        # Per-batch shared prefix: group v7s by 18-hex prefix; flag groups >=2.
        groups: dict[str, set[str]] = defaultdict(set)
        for u in v7s:
            groups[shared_prefix_key(u)].add(u)
        for group in groups.values():
            if len(group) >= 2:
                handshaped.update(group)
    return handshaped


def build_map(handshaped: set[str]) -> dict[str, str]:
    return {old: str(uuid.uuid7()) for old in sorted(handshaped)}


def apply_map(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    def sub(match: re.Match[str]) -> str:
        return mapping.get(match.group(0), match.group(0))

    new_text, count = V7_RE.subn(sub, text)
    return new_text, count


def main() -> int:
    grift_files = sorted(REPO_ROOT.glob(GRIFT_GLOB))
    extra_files = [p for p in EXTRA_TARGETS if p.exists()]
    all_files = grift_files + extra_files

    handshaped = collect_handshaped_ids(all_files)
    if not handshaped:
        print("No hand-shaped UUIDs found. Nothing to do.")
        return 0

    strict = sum(1 for u in handshaped if STRICT_SYNTHETIC_RE.fullmatch(u))
    print(
        f"Found {len(handshaped)} hand-shaped UUIDs "
        f"({strict} strict synthetic, {len(handshaped) - strict} per-batch shared prefix)."
    )

    mapping = build_map(handshaped)
    print(f"Minting {len(mapping)} fresh uuid7s.")

    total_replacements = 0
    touched = 0
    for f in all_files:
        before = f.read_text()
        after, count = apply_map(before, mapping)
        if count == 0:
            continue
        f.write_text(after)
        total_replacements += count
        touched += 1
        rel = f.relative_to(REPO_ROOT)
        print(f"  {rel}: {count} replacement(s)")

    SIDECAR.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n")
    print(
        f"\nDone. {total_replacements} replacement(s) across {touched} file(s)."
        f"\nMap written to {SIDECAR.relative_to(REPO_ROOT)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
