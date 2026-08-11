"""Tests for tap_grid.grift.envelope — write-path envelope parse/split.

Covers spec-grift-envelope § Envelope Validation
(req-grift-envelope-validation):
- Required top-level spine fields present.
- `data` lane present and is a dict.
- Denormalized mirrors (entity_id, name) inside `data` equal their
  top-level values.
- `display` and unknown lanes are discarded on the write path.
- The function does not apply writes itself — it returns a SplitPayload
  the caller routes through the service layer.
"""

from __future__ import annotations

import pytest

from tap_grid.grift.envelope import (
    EnvelopeValidationError,
    SplitPayload,
    parse_envelope_for_write,
)


def _minimal_node_envelope(**overrides):
    """A minimal well-formed node envelope for happy-path tests."""
    envelope = {
        "entity_id": "00000000-0000-7000-8000-000000000001",
        "entity_type": "character",
        "name": "Frodo Baggins",
        "dimensions": {},
        "data": {
            "entity_id": "00000000-0000-7000-8000-000000000001",
            "name": "Frodo Baggins",
            "description": "A hobbit of the Shire.",
            "bio": "Carries the Ring.",
        },
    }
    envelope.update(overrides)
    return envelope


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_minimal_envelope_splits_cleanly(self):
        env = _minimal_node_envelope()
        split = parse_envelope_for_write(env)
        assert isinstance(split, SplitPayload)
        assert split.entity_payload["entity_id"] == "00000000-0000-7000-8000-000000000001"
        assert split.entity_payload["entity_type"] == "character"
        assert split.entity_payload["name"] == "Frodo Baggins"
        assert split.entity_payload["dimensions"] == {}

    def test_data_payload_excludes_mirrored_fields(self):
        env = _minimal_node_envelope()
        split = parse_envelope_for_write(env)
        # Mirrors are routed through entity_payload, not model_payload.
        assert "entity_id" not in split.model_payload
        assert "name" not in split.model_payload
        # Non-mirrored per-model fields survive.
        assert split.model_payload["description"] == "A hobbit of the Shire."
        assert split.model_payload["bio"] == "Carries the Ring."

    def test_no_discarded_lanes_when_minimal(self):
        env = _minimal_node_envelope()
        split = parse_envelope_for_write(env)
        assert split.discarded_lanes == ()

    def test_edge_envelope_shape(self):
        """Edges use the same envelope (req-grift-envelope-edge-uniformity)."""
        env = {
            "entity_id": "00000000-0000-7000-8000-000000000099",
            "entity_type": "edge",
            "name": "Frodo KNOWS Sam",
            "dimensions": {},
            "data": {
                "entity_id": "00000000-0000-7000-8000-000000000099",
                "name": "Frodo KNOWS Sam",
                "description": "",
                "from_entity_id": "00000000-0000-7000-8000-000000000001",
                "to_entity_id": "00000000-0000-7000-8000-000000000002",
                "edge_type": "KNOWS",
                "properties": {},
            },
        }
        split = parse_envelope_for_write(env)
        assert split.entity_payload["entity_type"] == "edge"
        assert split.model_payload["edge_type"] == "KNOWS"
        assert split.model_payload["from_entity_id"] == "00000000-0000-7000-8000-000000000001"
        assert "entity_id" not in split.model_payload


# ---------------------------------------------------------------------------
# Mirror equality (req-grift-envelope-denorm-3 / req-grift-envelope-validation-1)
# ---------------------------------------------------------------------------


class TestMirrorEquality:
    def test_entity_id_mismatch_rejected(self):
        env = _minimal_node_envelope()
        env["data"]["entity_id"] = "00000000-0000-7000-8000-deadbeef0000"
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write(env)
        assert exc_info.value.code == "mirror_mismatch"
        assert "entity_id" in str(exc_info.value)

    def test_name_mismatch_rejected(self):
        env = _minimal_node_envelope()
        env["data"]["name"] = "Not Frodo"
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write(env)
        assert exc_info.value.code == "mirror_mismatch"
        assert "name" in str(exc_info.value)

    def test_mirror_absent_in_data_is_allowed(self):
        """Mirror MAY be absent in data; only mismatch is a violation.

        (Note: req-grift-envelope-denorm-4 says serializers always include
        the mirror; this test is about the parser's strictness, not the
        serializer's behavior.)
        """
        env = _minimal_node_envelope()
        del env["data"]["entity_id"]
        del env["data"]["name"]
        split = parse_envelope_for_write(env)
        # Top-level still flows to entity_payload.
        assert split.entity_payload["entity_id"] == "00000000-0000-7000-8000-000000000001"
        assert split.entity_payload["name"] == "Frodo Baggins"


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


class TestStructuralValidation:
    def test_non_dict_envelope_rejected(self):
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write("not an envelope")  # type: ignore[arg-type]
        assert exc_info.value.code == "envelope_not_dict"

    def test_missing_entity_id_rejected(self):
        env = _minimal_node_envelope()
        del env["entity_id"]
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write(env)
        assert exc_info.value.code == "spine_field_missing"
        assert "entity_id" in str(exc_info.value)

    def test_missing_entity_type_rejected(self):
        env = _minimal_node_envelope()
        del env["entity_type"]
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write(env)
        assert exc_info.value.code == "spine_field_missing"
        assert "entity_type" in str(exc_info.value)

    def test_missing_data_lane_rejected(self):
        env = _minimal_node_envelope()
        del env["data"]
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write(env)
        assert exc_info.value.code == "data_lane_missing"

    def test_data_not_dict_rejected(self):
        env = _minimal_node_envelope()
        env["data"] = ["not", "a", "dict"]
        with pytest.raises(EnvelopeValidationError) as exc_info:
            parse_envelope_for_write(env)
        assert exc_info.value.code == "data_lane_not_dict"


# ---------------------------------------------------------------------------
# Discarded lanes (display + unknown future lanes)
# ---------------------------------------------------------------------------


class TestDiscardedLanes:
    def test_display_lane_recorded_and_discarded(self):
        env = _minimal_node_envelope(display={"tap_viz": {"shape": "ellipse"}})
        split = parse_envelope_for_write(env)
        assert "display" in split.discarded_lanes
        # Nothing from display surfaces into either write payload.
        assert "display" not in split.entity_payload
        assert "display" not in split.model_payload

    def test_future_provenance_lane_discarded(self):
        """req-grift-envelope-shape: future lanes are named-not-built, and
        discarded on write until a spec promotes them."""
        env = _minimal_node_envelope(provenance={"batch_id": "ignored"})
        split = parse_envelope_for_write(env)
        assert "provenance" in split.discarded_lanes
        assert "provenance" not in split.entity_payload
        assert "provenance" not in split.model_payload

    def test_framework_managed_timestamps_excluded_from_entity_payload(self):
        """req-grift-envelope-validation: created_at / updated_at / version
        live at the top of the envelope on read but are framework-managed;
        callers can't set them via the write path."""
        env = _minimal_node_envelope(
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
            deleted_at=None,
            version=42,
        )
        split = parse_envelope_for_write(env)
        for key in ("created_at", "updated_at", "deleted_at", "version"):
            assert key not in split.entity_payload, f"framework-managed field {key} leaked into entity_payload"


# ---------------------------------------------------------------------------
# Package-level re-exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_parse_function_exported_at_grift_package(self):
        from tap_grid.grift import parse_envelope_for_write as pe

        assert pe is parse_envelope_for_write

    def test_split_payload_exported_at_grift_package(self):
        from tap_grid.grift import SplitPayload as SP

        assert SP is SplitPayload

    def test_error_class_exported_at_grift_package(self):
        from tap_grid.grift import EnvelopeValidationError as EVE

        assert EVE is EnvelopeValidationError
