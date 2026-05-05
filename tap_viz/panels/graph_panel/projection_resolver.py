"""Server-side resolver: walks a v1 Projection's graph chain into the shape the
client runtime expects.

The client-side projection runtime in `tap_viz/static/tap_viz/js/runtime/projection.js`
expects an inline definition shape — `elevations[].tap_layouts[].js_file` and
`default_elevation` (by name) — that predates the v1 entity reshape. To keep
the runtime contract stable while moving to entity-based composition, this
resolver walks the v1 graph chain (Projection → Elevation → Layout → Arrangement)
and emits a flattened structure with the same keys the runtime already reads.

The reshape happens here, server-side, once per panel render. Client runtime is
unchanged.

Input  (v1 Projection.definition):
    {
      "elevations": ["<el-uuid-1>", "<el-uuid-2>"],
      "default_elevation_id": "<el-uuid-1>",
      "node_style": ..., "status_badges": ..., "min_zoom": ..., "lock_nodes": ...
    }

Output (runtime-shaped):
    {
      "default_elevation": "<el-uuid-1>",        # the runtime keys by name
      "elevations": [
        {
          "name": "<el-uuid-1>",                  # entity_id used as the stable name
          "description": "...",
          "zoom": 0.6,
          "tap_layouts": [
            {
              "name": "<l-uuid-1>",
              "description": "...",
              "js_file": "plugins/.../foo.js",    # null when layout is arrangements-only
              "arrangements": [                    # zero or more inline arrangement defs
                {"anchor": ..., "members": ..., "positioning": ..., "distribution": ...},
                ...
              ]
            }
          ],
          "double_tap_targets": [
            {"entity_type": "...", "target_elevation": "<el-uuid-other>"}
          ]
        }
      ],
      "node_style": ..., "status_badges": ..., "min_zoom": ..., "lock_nodes": ...
    }

Names use entity_ids so the runtime's name-keyed lookup keeps working without
needing string slugs that could collide.
"""

from __future__ import annotations

from typing import Any

from tap_grid.models import Edge


def resolve_projection_definition(projection_definition: dict[str, Any]) -> dict[str, Any]:
    """Walk the v1 entity chain referenced by a Projection.definition and return
    a runtime-shaped dict. Pure read; no mutation."""
    from tap_viz.models import Arrangement, Elevation, Layout

    elevation_ids: list[str] = projection_definition.get("elevations") or []
    default_id: str | None = projection_definition.get("default_elevation_id")

    elevations_out: list[dict[str, Any]] = []

    for el_id in elevation_ids:
        elevation = Elevation.objects.filter(entity__id=el_id).first()
        if elevation is None:
            # Skip dangling references; hotlink validation should prevent this in practice.
            continue
        el_def = elevation.definition or {}

        layout_ids: list[str] = el_def.get("layouts") or []
        layouts_out: list[dict[str, Any]] = []
        for l_id in layout_ids:
            layout = Layout.objects.filter(entity__id=l_id).first()
            if layout is None:
                continue
            l_def = layout.definition or {}

            arrangement_ids: list[str] = l_def.get("arrangements") or []
            control = l_def.get("arrangement_control") or {}
            mode = control.get("mode", "all") if isinstance(control, dict) else "all"
            arrangements_out: list[dict[str, Any]] = []
            if mode != "none":
                for a_id in arrangement_ids:
                    arrangement = Arrangement.objects.filter(entity__id=a_id).first()
                    if arrangement is None:
                        continue
                    arrangements_out.append(arrangement.definition or {})

            layouts_out.append(
                {
                    "name": str(layout.entity_id),
                    "description": layout.description or "",
                    "js_file": l_def.get("js_file"),
                    "arrangements": arrangements_out,
                }
            )

        # double_tap_targets stays close to its v0 shape but rewrites
        # `target_elevation_id` (UUID) to `target_elevation` (the runtime's name key).
        dtt_out: list[dict[str, Any]] = []
        for dtt in el_def.get("double_tap_targets") or []:
            target_id = dtt.get("target_elevation_id")
            entity_type = dtt.get("entity_type")
            if isinstance(target_id, str) and isinstance(entity_type, str):
                dtt_out.append({"entity_type": entity_type, "target_elevation": target_id})

        elevations_out.append(
            {
                "name": str(elevation.entity_id),
                "description": elevation.description or el_def.get("description", ""),
                "zoom": el_def.get("zoom", 1.0),
                "tap_layouts": layouts_out,
                "double_tap_targets": dtt_out,
            }
        )

    resolved: dict[str, Any] = {
        "default_elevation": default_id or "",
        "elevations": elevations_out,
    }
    # Pass chrome through unchanged.
    for chrome_key in ("node_style", "status_badges", "min_zoom", "lock_nodes"):
        if chrome_key in projection_definition:
            resolved[chrome_key] = projection_definition[chrome_key]

    return resolved
