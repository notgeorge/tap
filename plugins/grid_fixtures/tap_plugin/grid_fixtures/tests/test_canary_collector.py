"""The cold-boot canary lands its fixed batch — offline and deterministically.

Per-commit guard for the collector the dev-validation cold-boot gate drives every
promote (`spec-dev-validation.md` `req-dev-validation-real-backend`). The gate
exercises it end-to-end against the real backend; this is the cheap early catch:
if the `grid_fixtures__*` vocabulary the canary emits ever drifts (a renamed node
type or edge slug), the canary stops importing and this reds at commit time rather
than only at the gate.

Runs through the service layer (`run_collection`) under the test backend — the
canary's own logic (inline data, no network) is what's under test here; the
real-backend delivery path is the gate's job.
"""

from __future__ import annotations

import pytest

from tap_cares.models import CollectionJobStatus, Collector
from tap_cares.registry import reconcile_collector_nodes
from tap_cares.services import run_collection
from tap_grid.batch import produced_batches

_CANARY_KEY = "grid_fixtures:canary"


@pytest.mark.django_db(transaction=True)
def test_canary_lands_two_leaves_and_one_edge():
    from tap_plugin.grid_fixtures.models.pg_leaf import PgLeaf

    # The canary is registered by grid_fixtures.ready(); materialize its on-grid node.
    reconcile_collector_nodes()
    collector = Collector.objects.get(collector_registry=_CANARY_KEY)

    job = run_collection(collector)
    job.refresh_from_db()

    assert job.status == CollectionJobStatus.SUCCESSFUL, job.summary
    assert len(produced_batches(job.entity_id)["imported"]) == 1
    assert PgLeaf.objects.filter(kind="cold_boot_canary").count() == 2


@pytest.mark.django_db(transaction=True)
def test_canary_is_idempotent():
    """Fixed uuid5 ids ⇒ re-running lands no new nodes (a valid no-op)."""
    from tap_plugin.grid_fixtures.models.pg_leaf import PgLeaf

    reconcile_collector_nodes()
    collector = Collector.objects.get(collector_registry=_CANARY_KEY)

    run_collection(collector)
    after_first = PgLeaf.objects.filter(kind="cold_boot_canary").count()
    run_collection(collector)
    assert PgLeaf.objects.filter(kind="cold_boot_canary").count() == after_first == 2
