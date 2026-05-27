"""Helpers shared by ROSCALE's panel types.

Resolves a compliance_artifact node from a panel's page variable, builds
the provenance block, and extracts sections + headline stats from parsed
OSCAL documents. Pure-Python — no Django/template imports — so each helper
is testable against a fixture dict without DB setup.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any

from plugins.roscale.constants import control_family_label
from plugins.roscale.parser import ParseResult, parse
from plugins.roscale.validator import ValidationResult, validate

logger = logging.getLogger(__name__)


@dataclass
class ArtifactResolution:
    """Outcome of resolving a compliance_artifact entity from a page variable."""

    entity_id: str
    var_name: str
    node: dict[str, Any] | None
    error: str | None
    used_fallback: bool = False
    fallback_kind: str | None = None

    @property
    def ok(self) -> bool:
        return self.node is not None and self.error is None


def _lookup_by_entity_id(entity_id: str) -> dict[str, Any] | None:
    """Run the Gryphon search for a compliance_artifact with the given entity_id."""
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="roscale-oscal-artifact-lookup",
        input_schema={
            "type": "object",
            "properties": {"entity_id": {"type": "string", "format": "uuid"}},
            "required": ["entity_id"],
        },
        definition={
            "query": [
                "MATCH (a:compliance_artifact) WHERE a.entity_id = $entity_id",
            ],
        },
        default_limit=1,
        max_limit=1,
    )
    result = execute_search(search, inputs={"entity_id": entity_id}, layer="extended")
    envelope = result.get("results", result)
    for n in envelope.get("nodes", []) or []:
        # Gryphon's "extended" envelope returns flat dicts: spine fields
        # (entity_id, entity_type, name, dimensions, created_at, ...) at the
        # top level, and per-model fields nested under `data`.
        if n.get("entity_id") == entity_id:
            return n
    return None


def _lookup_latest_by_kind(kind: str) -> dict[str, Any] | None:
    """Return the compliance_artifact node with the given kind whose `fetched_at` is highest.

    Pulls all matching nodes via Gryphon then sorts in Python by `fetched_at`
    (ISO 8601 string, lexically equivalent to chronological order when the
    format is consistent). Used by the panel-config-driven fallback path
    (`config.fallback.kind`) when no explicit entity_id is supplied in the URL.
    """
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="roscale-oscal-latest-by-kind",
        input_schema={
            "type": "object",
            "properties": {"kind": {"type": "string"}},
            "required": ["kind"],
        },
        definition={
            # `kind` is a model-specific field on compliance_artifact (not a
            # spine field like entity_id), so Gryphon requires the `.data.` prefix
            # per spec-grift-envelope.
            "query": ["MATCH (a:compliance_artifact) WHERE a.data.kind = $kind"],
        },
        default_limit=500,
        max_limit=2000,
    )
    result = execute_search(search, inputs={"kind": kind}, layer="extended")
    envelope = result.get("results", result)
    nodes = envelope.get("nodes", []) or []
    if not nodes:
        return None
    # ISO 8601 `fetched_at` sorts lexically as chronological order; empties last.
    # Per-model fields (including `fetched_at`) live under the envelope's `data`.
    nodes_sorted = sorted(
        nodes,
        key=lambda n: (n.get("data") or {}).get("fetched_at") or "",
        reverse=True,
    )
    return nodes_sorted[0]


def resolve_artifact(panel: Any, request: Any, default_var_name: str) -> ArtifactResolution:
    """Look up the compliance_artifact node named by the panel's page variable.

    The panel config may set `artifact_entity_id_var` to override the default
    variable name; the variable's value comes from `request.GET[<var_name>]`
    per `req-roscale-input-3` (URL-backed).

    When `request.GET[var_name]` is empty and the panel config supplies a
    `fallback.kind`, the resolver falls back to the most-recently-fetched
    `compliance_artifact` matching that kind. The result's `used_fallback`
    flag is set so consumers can surface the carve-out (e.g. a banner like
    "showing latest emission"). Explicit URL entity_id always wins.

    Returns an ArtifactResolution with the node on success or a populated
    `error` on failure.
    """
    config = getattr(panel, "config", None) or {}
    var_name = config.get("artifact_entity_id_var", default_var_name)
    fallback = config.get("fallback") or {}
    fallback_kind = fallback.get("kind") if isinstance(fallback, dict) else None
    entity_id = (request.GET.get(var_name) or "").strip()

    if entity_id:
        try:
            node = _lookup_by_entity_id(entity_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[ros1] Compliance artifact lookup failed for %s", entity_id)
            return ArtifactResolution(
                entity_id=entity_id,
                var_name=var_name,
                node=None,
                error=f"Artifact lookup failed: {exc}",
            )
        if node is not None:
            return ArtifactResolution(entity_id=entity_id, var_name=var_name, node=node, error=None)
        return ArtifactResolution(
            entity_id=entity_id,
            var_name=var_name,
            node=None,
            error=f"Compliance artifact not found for entity_id '{entity_id}'.",
        )

    if fallback_kind:
        try:
            node = _lookup_latest_by_kind(fallback_kind)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[ros2] Compliance artifact fallback lookup failed for kind=%s", fallback_kind)
            return ArtifactResolution(
                entity_id="",
                var_name=var_name,
                node=None,
                error=f"Artifact fallback lookup failed: {exc}",
                fallback_kind=fallback_kind,
            )
        if node is not None:
            resolved_id = node.get("entity_id") or ""
            return ArtifactResolution(
                entity_id=resolved_id,
                var_name=var_name,
                node=node,
                error=None,
                used_fallback=True,
                fallback_kind=fallback_kind,
            )
        return ArtifactResolution(
            entity_id="",
            var_name=var_name,
            node=None,
            error=f"No compliance_artifact of kind '{fallback_kind}' found on the grid yet. Run the collector at least once, then reload.",
            fallback_kind=fallback_kind,
        )

    return ArtifactResolution(
        entity_id="",
        var_name=var_name,
        node=None,
        error=f"No artifact specified. Expected page variable '{var_name}' in the URL.",
    )


def build_provenance(node: dict[str, Any]) -> dict[str, Any]:
    """Extract artifact-node provenance fields per req-roscale-rendering.

    Envelope shape: spine fields (entity_id, name, ...) live at the top
    level of `node`; per-model fields live under `node["data"]`.
    """
    data = node.get("data") or {}
    return {
        "name": node.get("name") or data.get("name") or "",
        "kind": data.get("kind") or "",
        "source_url": data.get("source_url") or "",
        "fetched_at": data.get("fetched_at") or "",
        "content_type": data.get("content_type") or "",
        "size_bytes": data.get("size_bytes"),
        "signature_verified": data.get("signature_verified"),
        "signed_by": data.get("signed_by") or "",
        "rekor_log_index": data.get("rekor_log_index") or "",
        "verified_at": data.get("verified_at") or "",
    }


def parse_and_validate(content: Any) -> tuple[ParseResult, ValidationResult]:
    parsed = parse(content)
    result = validate(parsed)
    return parsed, result


def pretty_json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False)
    except (TypeError, ValueError):
        return str(obj)


# ---------------------------------------------------------------------------
# SSP section extractors
# ---------------------------------------------------------------------------


def ssp_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    root = doc.get("system-security-plan", {}) or {}
    md = root.get("metadata", {}) or {}
    return {
        "title": md.get("title") or "",
        "oscal_version": md.get("oscal-version") or "",
        "last_modified": md.get("last-modified") or "",
        "document_version": md.get("version") or "",
        "remarks": md.get("remarks") or "",
        "published": md.get("published") or "",
    }


def ssp_system_overview(doc: dict[str, Any]) -> dict[str, Any]:
    root = doc.get("system-security-plan", {}) or {}
    sysc = root.get("system-characteristics", {}) or {}
    sysid_list = sysc.get("system-ids") or []
    sysid = sysid_list[0].get("id") if sysid_list and isinstance(sysid_list[0], dict) else ""
    sec_imp = sysc.get("security-impact-level", {}) or {}
    return {
        "system_name": sysc.get("system-name") or "",
        "system_name_short": sysc.get("system-name-short") or "",
        "system_id": sysid,
        "description": sysc.get("description") or "",
        "authorization_boundary": (sysc.get("authorization-boundary") or {}).get("description") or "",
        "security_sensitivity_level": sysc.get("security-sensitivity-level") or "",
        "confidentiality": sec_imp.get("security-objective-confidentiality") or "",
        "integrity": sec_imp.get("security-objective-integrity") or "",
        "availability": sec_imp.get("security-objective-availability") or "",
        "status": (sysc.get("status") or {}).get("state") or "",
    }


def ssp_implemented_requirements(doc: dict[str, Any]) -> list[dict[str, Any]]:
    root = doc.get("system-security-plan", {}) or {}
    ci = root.get("control-implementation", {}) or {}
    reqs = ci.get("implemented-requirements") or []
    out: list[dict[str, Any]] = []
    for req in reqs:
        if not isinstance(req, dict):
            continue
        control_id = req.get("control-id") or ""
        # Implementation status and origination are encoded as "props" with
        # specific names; pull the most-commonly-named ones.
        impl_status = ""
        origination_kinds: list[str] = []
        for prop in req.get("props") or []:
            if not isinstance(prop, dict):
                continue
            name = prop.get("name") or ""
            value = prop.get("value") or ""
            if name == "implementation-status":
                impl_status = value
            elif name == "control-origination":
                origination_kinds.append(value)
        # OSCAL allows the implementation narrative in several places:
        # statements[*].description, statements[*].remarks, or
        # statements[*].by-components[*].description. Walk all three in
        # priority order; Sam's SSP puts the narrative in statements[*].remarks
        # which the prior single-source-of-truth lookup missed entirely.
        statements = req.get("statements") or []
        statement_summary = ""
        for stmt in statements:
            if not isinstance(stmt, dict):
                continue
            text = (stmt.get("description") or "").strip() or (stmt.get("remarks") or "").strip()
            if not text:
                for by in stmt.get("by-components") or []:
                    if isinstance(by, dict):
                        text = (by.get("description") or "").strip()
                        if text:
                            break
            if text:
                statement_summary = text
                break

        # Evidence and reference URLs grouped by `rel`. OSCAL convention:
        # rel="evidence" is a machine-verifiable artifact (live signal,
        # signed bundle); rel="reference" is human-readable supporting
        # material (architecture decisions, Terraform source). Anything
        # else is bucketed as "other" so a future renderer can decide.
        evidence_links: list[dict[str, str]] = []
        reference_links: list[dict[str, str]] = []
        other_links: list[dict[str, str]] = []
        for link in req.get("links") or []:
            if not isinstance(link, dict):
                continue
            href = (link.get("href") or "").strip()
            if not href:
                continue
            entry = {
                "href": href,
                "text": (link.get("text") or "").strip(),
                "rel": (link.get("rel") or "").strip(),
                "media_type": (link.get("media-type") or "").strip(),
            }
            if entry["rel"] == "evidence":
                evidence_links.append(entry)
            elif entry["rel"] == "reference":
                reference_links.append(entry)
            else:
                other_links.append(entry)

        out.append(
            {
                "control_id": control_id,
                "family_label": control_family_label(control_id),
                "implementation_status": impl_status,
                "origination_kinds": origination_kinds,
                "statement_summary": statement_summary,
                "remarks": req.get("remarks") or "",
                "evidence_links": evidence_links,
                "reference_links": reference_links,
                "other_links": other_links,
            }
        )
    out.sort(key=lambda r: r["control_id"])
    return out


def ssp_implemented_requirements_by_family(impl_reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families: dict[str, list[dict[str, Any]]] = {}
    for r in impl_reqs:
        families.setdefault(r["family_label"], []).append(r)
    return [
        {"family": fam, "count": len(reqs), "requirements": reqs}
        for fam, reqs in sorted(families.items())
    ]


def ssp_components(doc: dict[str, Any]) -> list[dict[str, Any]]:
    root = doc.get("system-security-plan", {}) or {}
    si = root.get("system-implementation", {}) or {}
    out: list[dict[str, Any]] = []
    for c in si.get("components") or []:
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "uuid": c.get("uuid") or "",
                "type": c.get("type") or "",
                "title": c.get("title") or "",
                "description": c.get("description") or "",
                "status": (c.get("status") or {}).get("state") or "",
            }
        )
    return out


def ssp_users(doc: dict[str, Any]) -> list[dict[str, Any]]:
    root = doc.get("system-security-plan", {}) or {}
    si = root.get("system-implementation", {}) or {}
    out: list[dict[str, Any]] = []
    for u in si.get("users") or []:
        if not isinstance(u, dict):
            continue
        out.append(
            {
                "uuid": u.get("uuid") or "",
                "title": u.get("title") or "",
                "role_ids": u.get("role-ids") or [],
            }
        )
    return out


def ssp_back_matter(doc: dict[str, Any]) -> list[dict[str, Any]]:
    root = doc.get("system-security-plan", {}) or {}
    bm = root.get("back-matter", {}) or {}
    out: list[dict[str, Any]] = []
    for r in bm.get("resources") or []:
        if not isinstance(r, dict):
            continue
        links = []
        for link in r.get("rlinks") or []:
            if isinstance(link, dict) and link.get("href"):
                links.append(link["href"])
        out.append(
            {
                "uuid": r.get("uuid") or "",
                "title": r.get("title") or "",
                "description": r.get("description") or "",
                "links": links,
            }
        )
    return out


def ssp_headline_stats(doc: dict[str, Any], impl_reqs: list[dict[str, Any]]) -> dict[str, Any]:
    root = doc.get("system-security-plan", {}) or {}
    family_counts = Counter(r["family_label"] for r in impl_reqs)
    impl_status_counts = Counter(r["implementation_status"] or "(unset)" for r in impl_reqs)
    origination_counts: Counter[str] = Counter()
    for r in impl_reqs:
        for kind in r["origination_kinds"]:
            origination_counts[kind] += 1
    si = root.get("system-implementation", {}) or {}
    bm = root.get("back-matter", {}) or {}
    md = root.get("metadata", {}) or {}
    return {
        "total_controls": len(impl_reqs),
        "family_counts": dict(family_counts.most_common()),
        "implementation_status_counts": dict(impl_status_counts.most_common()),
        "origination_counts": dict(origination_counts.most_common()),
        "component_count": len(si.get("components") or []),
        "back_matter_count": len(bm.get("resources") or []),
        "party_count": len(md.get("parties") or []),
    }


def ssp_self_attestation_signal(doc: dict[str, Any]) -> dict[str, Any]:
    """Look for self-attested / not-authorized language in metadata/sysc.

    OSCAL doesn't have a single 'self-attested' field, but conventional places
    include metadata.remarks, system-characteristics.remarks, and a 'self-attest'
    or 'not-authorized' prop. Best-effort: surface flags + the matching text.
    """
    root = doc.get("system-security-plan", {}) or {}
    md = root.get("metadata", {}) or {}
    sysc = root.get("system-characteristics", {}) or {}
    indicators: list[str] = []
    matches: list[str] = []
    for haystack_name, haystack in (
        ("metadata.remarks", md.get("remarks") or ""),
        ("system-characteristics.remarks", sysc.get("remarks") or ""),
        ("metadata.title", md.get("title") or ""),
    ):
        if not isinstance(haystack, str):
            continue
        low = haystack.lower()
        if "self-attest" in low or "self attest" in low:
            indicators.append("self-attested")
            matches.append(f"{haystack_name}: {haystack[:200]}")
        if "not authorized" in low or "not-authorized" in low or "not yet authorized" in low:
            indicators.append("not-authorized")
            matches.append(f"{haystack_name}: {haystack[:200]}")
    # De-dupe indicators preserving order.
    seen = set()
    unique = []
    for ind in indicators:
        if ind not in seen:
            seen.add(ind)
            unique.append(ind)
    return {"indicators": unique, "matches": matches}


# ---------------------------------------------------------------------------
# POA&M section extractors
# ---------------------------------------------------------------------------


def poam_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    root = doc.get("plan-of-action-and-milestones", {}) or {}
    md = root.get("metadata", {}) or {}
    return {
        "title": md.get("title") or "",
        "oscal_version": md.get("oscal-version") or "",
        "last_modified": md.get("last-modified") or "",
        "document_version": md.get("version") or "",
        "published": md.get("published") or "",
    }


def _prop_value(props: list[Any], name: str) -> str:
    for p in props or []:
        if isinstance(p, dict) and p.get("name") == name:
            return p.get("value") or ""
    return ""


def poam_items(doc: dict[str, Any]) -> list[dict[str, Any]]:
    root = doc.get("plan-of-action-and-milestones", {}) or {}
    items = root.get("poam-items") or []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        props = it.get("props") or []
        # FedRAMP POA&M convention puts referenced Rev-5 control IDs in a
        # `controls` (plural) prop as a comma-separated string, e.g.
        # "ia-2, ia-5, ac-2". Verified against Samsite's live POA&M.
        controls_prop = _prop_value(props, "controls") or _prop_value(props, "control")
        controls = [c.strip() for c in controls_prop.split(",")] if controls_prop else []
        controls = [c for c in controls if c]
        out.append(
            {
                "uuid": it.get("uuid") or "",
                "title": it.get("title") or "",
                "description": it.get("description") or "",
                "poam_id": _prop_value(props, "poam-id"),
                "status": _prop_value(props, "status"),
                "category": _prop_value(props, "category"),
                "controls": controls,
                "original_risk": _prop_value(props, "original-risk-rating"),
                "adjusted_risk": _prop_value(props, "adjusted-risk-rating"),
                "asset_identifier": _prop_value(props, "asset-identifier"),
                "weakness_detector_source": _prop_value(props, "weakness-detector-source"),
                "scheduled_completion_date": _prop_value(props, "scheduled-completion-date"),
                "status_date": _prop_value(props, "status-date"),
                "original_detection_date": _prop_value(props, "original-detection-date"),
                "remediation_plan_summary": _prop_value(props, "remediation-plan-summary"),
            }
        )
    return out


def poam_headline_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    status_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    detector_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    open_count = 0
    risk_accepted_count = 0
    for it in items:
        status = it["status"] or "(unset)"
        status_counts[status] += 1
        if status == "open":
            open_count += 1
        elif status == "risk-accepted":
            risk_accepted_count += 1
        risk_counts[it["adjusted_risk"] or it["original_risk"] or "(unset)"] += 1
        category_counts[it["category"] or "(unset)"] += 1
        detector_counts[it["weakness_detector_source"] or "(unset)"] += 1
        for c in it["controls"]:
            family_counts[control_family_label(c)] += 1
    return {
        "total": total,
        "open_count": open_count,
        "risk_accepted_count": risk_accepted_count,
        "status_counts": dict(status_counts.most_common()),
        "risk_counts": dict(risk_counts.most_common()),
        "category_counts": dict(category_counts.most_common()),
        "detector_counts": dict(detector_counts.most_common()),
        "family_counts": dict(family_counts.most_common()),
    }
