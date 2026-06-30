"""Observation-aware write semantics — explicit-null preservation + FLIP-touch scope.

Covers req-grid-service-write-observation (realizing the field-observation convention's
write-path dependency, spec-grid-node.md req-grid-node-observation). These drive the
full service write pipeline, not update_flip_map in isolation.
"""

import uuid

import pytest

from plugins.computing_core.models.network_interface import NetworkInterface
from tap_grid.caller_context import CallerContext
from tap_grid.services import create_node, patch_node


def _ctx() -> CallerContext:
    return CallerContext(batch_id=str(uuid.uuid7()))


@pytest.mark.django_db
class TestObservationWrites:
    def _create(self, payload: dict, ctx: CallerContext | None = None) -> tuple[NetworkInterface, str]:
        ctx = ctx or _ctx()
        result = create_node("network_interface", payload, caller_context=ctx)
        assert result.success, result.errors
        return NetworkInterface.objects.get(entity_id=result.entity_id), ctx.batch_id

    def test_explicit_null_clears_and_stamps_flip(self):
        # observation-1: explicit null on a nullable field clears it...
        ni, _ = self._create({"interface_name": "eth0", "mac_address": "00:11:22:33:44:55"})
        ctx_b = _ctx()
        patch_node(ni.entity_id, {"mac_address": None}, caller_context=ctx_b)
        ni.refresh_from_db()
        assert ni.mac_address is None
        # ...and earns a FLIP entry — a known unknown (a batch asserted the absence).
        assert ni.flip_map.get("mac_address") == ctx_b.batch_id

    def test_omitted_field_leaves_flip_alone(self):
        # observation-3/5: an omitted field is neither applied nor re-stamped.
        ni, batch_a = self._create({"interface_name": "eth0", "mac_address": "00:11:22:33:44:55"})
        ctx_b = _ctx()
        patch_node(ni.entity_id, {"interface_name": "eth1"}, caller_context=ctx_b)
        ni.refresh_from_db()
        assert ni.flip_map.get("interface_name") == ctx_b.batch_id
        assert ni.flip_map.get("mac_address") == batch_a  # untouched

    def test_create_stamps_only_provided_fields(self):
        # observation-6: omitted fields get no FLIP entry (unknown unknown), not a default stamp.
        ni, batch_a = self._create({"interface_name": "eth0"})
        assert ni.flip_map.get("interface_name") == batch_a
        assert "mac_address" not in ni.flip_map

    def test_flip_scoped_to_touched_on_patch(self):
        # observation-5: a patch stamps only the touched field, not the full surface.
        ni, batch_a = self._create({"interface_name": "eth0", "mac_address": "00:11:22:33:44:55", "state": "up"})
        ctx_b = _ctx()
        patch_node(ni.entity_id, {"state": "down"}, caller_context=ctx_b)
        ni.refresh_from_db()
        assert ni.flip_map.get("state") == ctx_b.batch_id
        assert ni.flip_map.get("interface_name") == batch_a
        assert ni.flip_map.get("mac_address") == batch_a

    def test_null_on_non_null_field_dropped(self):
        # observation-2: a null on a non-null field is dropped (treated as absent), not an error.
        ni, _ = self._create({"interface_name": "eth0", "state": "up"})
        result = patch_node(ni.entity_id, {"state": None}, caller_context=_ctx())
        assert result.success, result.errors
        ni.refresh_from_db()
        assert ni.state == "up"  # unchanged — null dropped, not applied
