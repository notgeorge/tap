"""Open-alerts dataset invariants for the Genericom demo.

Asserts the no-orphan invariant from req-genericom-alerts-no-orphans:
every open Finding in the seeded Genericom + findings dataset must have at
least one HAS_FINDING parent edge. The Genericom Open Alerts panel relies
on this as a precondition rather than handling missing parents in code.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from tap_grid.grift import grift_import

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
GRIFT_DIR = PLUGIN_ROOT / "grift"
AWS_CORE_GRIFT_DIR = PLUGIN_ROOT.parent / "aws_core" / "grift"
KSI_GRIFT_DIR = PLUGIN_ROOT.parent / "fedramp_20x_ksi" / "grift"


def _import(doc_path: Path) -> None:
    doc = json.loads(doc_path.read_text())
    result = grift_import(doc, dangling_edge_mode="error", actor=None)
    assert result.success, f"GRIFT import failed for {doc_path}: {result.errors}"


def _genericom_bundles_in_manifest_order() -> list[str]:
    toml = tomllib.loads((PLUGIN_ROOT / "tap-plugin.toml").read_text())
    return list(toml["grift"].keys())


@pytest.mark.django_db(transaction=True)
def test_no_orphan_open_findings() -> None:
    """Every open Finding in the seeded dataset must have a HAS_FINDING parent."""
    for name in ("dimension", "regions"):
        _import(AWS_CORE_GRIFT_DIR / f"{name}.grift.json")
    for name in _genericom_bundles_in_manifest_order():
        _import(GRIFT_DIR / f"{name}.grift.json")
    for name in ("dimension", "findings-genericom"):
        _import(KSI_GRIFT_DIR / f"{name}.grift.json")

    from tap_plugin.fedramp_20x_ksi.models.finding import Finding
    from tap_grid.models import Edge

    open_findings = list(Finding.objects.filter(status="open"))
    assert open_findings, "Expected at least one open finding in the seeded dataset"

    orphans = [
        f
        for f in open_findings
        if not Edge.objects.filter(
            to_entity_id=f.entity_id, edge_type="HAS_FINDING"
        ).exists()
    ]

    assert not orphans, (
        f"{len(orphans)} open finding(s) have no HAS_FINDING parent edge. "
        f"Genericom Open Alerts panel requires every open finding to have a "
        f"parent system. Orphan entity_ids: "
        f"{[str(f.entity_id) for f in orphans]}"
    )
