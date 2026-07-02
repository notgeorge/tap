"""tap_cares scheduling/collector invariants — three guards, one per invariant.

- **schedule-grift-targets** (`req-tap-cares-collector-model-10`) — every
  `SCHEDULED_TARGET` grift edge must resolve to a registered collector's derived
  entity id. A stale hardcoded id dangles → boot population aborts → fresh spawn
  fails. This is the guard the package-mode collector-identity rename motivated.
- **record-site-uniqueness** (`req-tap-cares-collector-job-model-15`) — no file
  reuses a `record_*` site hex within itself (cross-file reuse is namespaced-safe).
- **recurring-uniqueness** (`req-tap-cares-task-backend-recurring-scope-4`) —
  exactly one `@recurring` decoration exists (the scheduler tick); all other
  scheduling routes through on-grid `Schedule` entities.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from pathlib import Path

from tap.guards.base import REPO_ROOT, Guard

# ── schedule-grift-targets ────────────────────────────────────────────────────

SCHEDULED_TARGET = "SCHEDULED_TARGET"


class ScheduleGriftTargetsGuard(Guard):
    slug = "schedule-grift-targets"
    map_row = "Schedule grift target integrity"
    description = (
        "A collector's on-grid id is derived from its scope:key; schedule grift bundles hardcode that id "
        "as a SCHEDULED_TARGET edge. If the two drift (the failure the package-mode rename introduced), the "
        "edge dangles, boot population aborts, and every fresh spawn breaks. This fails that drift at "
        "authoring time instead of at a developer's next spawn."
    )

    def check(self) -> None:
        import json

        from tap_cares.registry import NAMESPACE_COLLECTOR, collector_registry
        from tap_plugins.seeding import all_tap_plugins

        registered = {str(uuid.uuid5(NAMESPACE_COLLECTOR, qk)) for qk in collector_registry.keys()}

        edges: list[tuple[str, str, str, str]] = []
        for config in all_tap_plugins():
            manifest = config.manifest
            if manifest is None:
                continue
            for bundle in manifest.grift:
                doc = json.loads((manifest.plugin_root / bundle.path).read_text())
                for batch_idx, batch in enumerate(doc.get("batches", [])):
                    for edge_idx, edge in enumerate(batch.get("edges", [])):
                        body = edge.get("edge", {})
                        if body.get("edge_type") == SCHEDULED_TARGET:
                            edges.append(
                                (
                                    manifest.slug,
                                    bundle.name,
                                    f"$.batches[{batch_idx}].edges[{edge_idx}]",
                                    body["to_entity_id"],
                                )
                            )

        # Fail closed on an empty sweep: a silent zero would pass while covering nothing.
        assert edges, "expected at least one SCHEDULED_TARGET edge across shipped plugins"

        dangling = [(slug, bundle, path, tid) for slug, bundle, path, tid in edges if tid not in registered]
        assert not dangling, (
            "SCHEDULED_TARGET edge(s) point at a collector entity id that no registered collector "
            "reconciles to — a stale hardcoded id or scope/key drift (req-tap-cares-collector-model-10):\n"
            + "\n".join(f"  {slug}/{bundle} {path} -> {tid}" for slug, bundle, path, tid in dangling)
            + f"\nRegistered collector ids: {sorted(registered)}"
        )


# ── record-site-uniqueness ────────────────────────────────────────────────────

_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "static",
    "build",
    "dist",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

_HEX = r"[0-9a-f]{4}"
# A `_SITE_<NAME> = "<hex>"` module/class constant assignment.
_SITE_CONST = re.compile(r"^\s*_SITE_[A-Z0-9_]+\s*=\s*[\"'](" + _HEX + r")[\"']\s*$", re.MULTILINE)
# An inline first-positional string literal to a record_* call.
_RECORD_INLINE = re.compile(r"record_(?:info|warn|error)\s*\(\s*[\"'](" + _HEX + r")[\"']", re.DOTALL)


def _iter_repo_python_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    return files


class RecordSiteUniquenessGuard(Guard):
    slug = "record-site-uniqueness"
    map_row = "`record_*` site tokens"
    description = (
        "Collectors tag observations with a 4-hex record_* site token whose callsite path is the module, so "
        "the hex only has to be unique within its file. Reusing one within a file (copy-paste without "
        "bumping it) collapses two callsites into one indistinguishable token. This flags any such reuse."
    )

    def check(self) -> None:
        self_rel = Path("tap/guards/cares.py")
        offenders: list[str] = []
        for path in _iter_repo_python_files():
            rel = path.relative_to(REPO_ROOT)
            if rel == self_rel:  # this scanner defines the regexes it looks for
                continue
            try:
                text = path.read_text()
            except OSError, UnicodeDecodeError:
                continue

            seen: dict[str, list[int]] = defaultdict(list)
            for match in _SITE_CONST.finditer(text):
                seen[match.group(1)].append(text.count("\n", 0, match.start()) + 1)
            for match in _RECORD_INLINE.finditer(text):
                seen[match.group(1)].append(text.count("\n", 0, match.start()) + 1)

            for hex_tok, lines in sorted(seen.items()):
                if len(lines) > 1:
                    offenders.append(f"  {rel}: '{hex_tok}' at lines {sorted(lines)}")

        assert not offenders, (
            "Duplicate record_* site hex within a file:\n"
            + "\n".join(offenders)
            + "\n\nEach site token must be unique within its file (cross-file reuse is namespaced-safe). "
            "Mint fresh ones with `scripts/log-site-id`."
        )


# ── recurring-uniqueness ──────────────────────────────────────────────────────

_RECURRING_SCAN_ROOTS = (
    "tap_cares",
    "tap_grid",
    "tap_plugins",
    "tap_api",
    "tap_web",
    "tap_viz",
    "plugins",
)


class RecurringUniquenessGuard(Guard):
    slug = "recurring-uniqueness"
    map_row = "Recurring-task uniqueness"
    description = (
        "Steady Queue's @recurring decorator is permitted for exactly one task — the TAP scheduler tick. "
        "Every other scheduling need must route through an on-grid Schedule entity (auditable, FLIP-able), "
        "not a new code-level recurring task. This asserts there is exactly one @recurring callsite."
    )

    def check(self) -> None:
        self_rel = "tap/guards/cares.py"
        callsites: list[str] = []
        for root in _RECURRING_SCAN_ROOTS:
            root_path = REPO_ROOT / root
            if not root_path.is_dir():
                continue
            for path in root_path.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                rel = str(path.relative_to(REPO_ROOT))
                if rel == self_rel:
                    continue
                for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if line.lstrip().startswith("@recurring("):
                        callsites.append(f"{rel}:{lineno}: {line.lstrip()}")

        assert len(callsites) == 1, (
            f"Expected exactly one @recurring callsite (the TAP scheduler tick in "
            f"tap_cares/task_backend.py), found {len(callsites)}:\n  "
            + "\n  ".join(callsites)
            + "\n\nAdditional recurring tasks belong on the TAP grid as Schedule entities, not as "
            "@recurring decorators (req-tap-cares-task-backend-recurring-scope-4)."
        )
        assert (
            "tap_cares/task_backend.py" in callsites[0]
        ), f"Expected the @recurring callsite to live in tap_cares/task_backend.py; got {callsites[0]}"
