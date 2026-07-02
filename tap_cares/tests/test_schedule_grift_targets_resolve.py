"""Guard: schedule grift SCHEDULED_TARGET edges must resolve to a registered collector.

Mechanical backstop for req-tap-cares-collector-model-10. A collector's on-grid
entity id is derived: ``uuid5(NAMESPACE_COLLECTOR, "{scope}:{key}")``. Schedule
grift bundles hardcode that id as a ``SCHEDULED_TARGET`` edge target, so any drift
between the hardcoded id and the collector's actual derived id makes the edge
dangle. A dangling edge fails boot's population phase (`on_failure=abort`), which
fails a fresh `spawn-session` — exactly the class of breakage the package-mode
migration introduced when a collector's module path (its old identity input)
changed out from under a stale grift target.

This test makes that drift fail loudly at CI, at authoring time, instead of at a
developer's next spawn. It discovers plugins generically (`all_tap_plugins`), so
tap_cares carries no dependency on any specific plugin.
"""

import json
import uuid

from tap_cares.registry import NAMESPACE_COLLECTOR, collector_registry
from tap_plugins.seeding import all_tap_plugins

SCHEDULED_TARGET = "SCHEDULED_TARGET"


def _registered_collector_entity_ids() -> set[str]:
    """The derived on-grid entity id of every registered collector."""
    return {str(uuid.uuid5(NAMESPACE_COLLECTOR, qk)) for qk in collector_registry.keys()}


def _scheduled_target_edges() -> list[tuple[str, str, str, str]]:
    """Every SCHEDULED_TARGET edge across all shipped plugin grift bundles.

    Returns tuples of (plugin_slug, bundle_name, edge_json_path, to_entity_id).
    """
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
    return edges


def test_every_scheduled_target_resolves_to_a_registered_collector():
    registered = _registered_collector_entity_ids()
    edges = _scheduled_target_edges()

    # Fail closed on an empty sweep: a silent zero would let this guard pass while
    # covering nothing (e.g. if the discovery or edge-shape assumptions drifted).
    assert edges, "expected at least one SCHEDULED_TARGET edge across shipped plugins"

    dangling = [(slug, bundle, path, tid) for slug, bundle, path, tid in edges if tid not in registered]
    assert not dangling, (
        "SCHEDULED_TARGET edge(s) point at a collector entity id that no registered "
        "collector reconciles to — a stale hardcoded id or scope/key drift "
        "(req-tap-cares-collector-model-10):\n"
        + "\n".join(f"  {slug}/{bundle} {path} -> {tid}" for slug, bundle, path, tid in dangling)
        + f"\nRegistered collector ids: {sorted(registered)}"
    )
