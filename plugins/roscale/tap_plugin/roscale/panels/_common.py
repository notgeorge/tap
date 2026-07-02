"""Helpers shared by ROSCALE's panel types.

Builds the provenance block and extracts sections + headline stats from
parsed OSCAL documents. Pure-Python — no Django/template imports — so
each helper is testable against a fixture dict without DB setup.

Entity resolution (URL deep link + fallback Gryphon query) is handled by
the canonical helper at `tap_web.panels.entity_resolution`; per-plugin
artifact-specific helpers no longer live here.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from tap_plugin.roscale.constants import control_family_label
from tap_plugin.roscale.parser import ParseResult, parse
from tap_plugin.roscale.validator import ValidationResult, validate


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

        # Short preview for the collapsed-control summary line. Strip
        # newlines (the narrative may span paragraphs) and truncate to a
        # readable one-line slice. Full text still lives in
        # statement_summary for the expanded view.
        preview = " ".join((statement_summary or "").split())
        if len(preview) > 110:
            preview = preview[:107].rstrip() + "…"

        # Search-text blob for the client-side type-to-filter. Includes
        # everything a user might plausibly grep for: control id, family
        # label, status, narrative, link text/URLs. Lowercased once
        # server-side so the client filter is a cheap substring check.
        search_parts = [
            control_id,
            control_family_label(control_id),
            impl_status,
            " ".join(origination_kinds),
            statement_summary or "",
            req.get("remarks") or "",
            " ".join(f"{lk['text']} {lk['href']}" for lk in evidence_links + reference_links + other_links),
        ]
        search_text = " ".join(part for part in search_parts if part).lower()

        out.append(
            {
                "control_id": control_id,
                "family_label": control_family_label(control_id),
                "implementation_status": impl_status,
                "origination_kinds": origination_kinds,
                "statement_summary": statement_summary,
                "statement_preview": preview,
                "remarks": req.get("remarks") or "",
                "evidence_links": evidence_links,
                "reference_links": reference_links,
                "other_links": other_links,
                "evidence_count": len(evidence_links),
                "reference_count": len(reference_links),
                "search_text": search_text,
            }
        )
    out.sort(key=lambda r: r["control_id"])
    return out


def ssp_implemented_requirements_by_family(impl_reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families: dict[str, list[dict[str, Any]]] = {}
    for r in impl_reqs:
        families.setdefault(r["family_label"], []).append(r)
    out: list[dict[str, Any]] = []
    for fam, reqs in sorted(families.items()):
        # Per-family aggregate of how many controls reached each
        # implementation status. Drives the family-header pill
        # ("X of Y implemented") so the user can see at a glance which
        # families have gaps without expanding every family.
        implemented = sum(1 for r in reqs if r["implementation_status"] == "implemented")
        out.append(
            {
                "family": fam,
                "count": len(reqs),
                "implemented_count": implemented,
                "requirements": reqs,
            }
        )
    return out


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
        title = it.get("title") or ""
        description = it.get("description") or ""
        status = _prop_value(props, "status")
        category = _prop_value(props, "category")
        original_risk = _prop_value(props, "original-risk-rating")
        adjusted_risk = _prop_value(props, "adjusted-risk-rating")
        asset_identifier = _prop_value(props, "asset-identifier")
        detector = _prop_value(props, "weakness-detector-source")
        scheduled_completion = _prop_value(props, "scheduled-completion-date")
        status_date = _prop_value(props, "status-date")
        original_detection = _prop_value(props, "original-detection-date")
        remediation = _prop_value(props, "remediation-plan-summary")
        poam_id = _prop_value(props, "poam-id")

        # One-line preview of the title for the collapsed-card summary;
        # description provides the body when the user expands.
        title_preview = " ".join((title or "").split())
        if len(title_preview) > 110:
            title_preview = title_preview[:107].rstrip() + "…"

        # Highest of (adjusted, original) drives the risk pill — the
        # "what's still on the table" reading. Stash both so the
        # expanded body can show the original-vs-adjusted comparison.
        effective_risk = adjusted_risk or original_risk

        # Search-text blob for the client-side type-to-filter. Lowercased
        # once server-side so the client just runs a cheap substring
        # check. Includes id, title, description, status/category/risk,
        # controls list, asset id, detector, remediation, dates.
        search_parts = [
            poam_id,
            it.get("uuid") or "",
            title,
            description,
            status,
            category,
            original_risk,
            adjusted_risk,
            " ".join(controls),
            asset_identifier,
            detector,
            remediation,
            scheduled_completion,
            status_date,
            original_detection,
        ]
        search_text = " ".join(part for part in search_parts if part).lower()

        out.append(
            {
                "uuid": it.get("uuid") or "",
                "title": title,
                "title_preview": title_preview,
                "description": description,
                "poam_id": poam_id,
                "status": status,
                "category": category,
                "controls": controls,
                "controls_count": len(controls),
                "original_risk": original_risk,
                "adjusted_risk": adjusted_risk,
                "effective_risk": effective_risk,
                "asset_identifier": asset_identifier,
                "weakness_detector_source": detector,
                "scheduled_completion_date": scheduled_completion,
                "status_date": status_date,
                "original_detection_date": original_detection,
                "remediation_plan_summary": remediation,
                "search_text": search_text,
            }
        )
    return out


def poam_items_by_status(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group POA&M items by status for progressive-disclosure rendering.

    Status is the question a POA&M-reader asks first: "what's still
    outstanding?" Open items lead, then risk-accepted (documented
    deferrals), then closed/anything else. Empty groups are dropped so
    the page doesn't show "Closed (0)" for a POA&M with nothing closed.
    """
    # Canonical status order for display. Anything outside this list
    # gets bucketed into "other" at the end with its original label.
    order = ["open", "risk-accepted", "ongoing", "closed", ""]
    label_overrides = {"": "(no status)"}

    buckets: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        s = (it.get("status") or "").strip().lower()
        buckets.setdefault(s, []).append(it)

    out: list[dict[str, Any]] = []
    for s in order:
        if s in buckets:
            out.append(
                {
                    "status": s,
                    "label": label_overrides.get(s, s).replace("-", " ").title() or "(no status)",
                    "count": len(buckets[s]),
                    "items": buckets[s],
                }
            )
            del buckets[s]
    # Leftover statuses we didn't anticipate.
    for s in sorted(buckets):
        out.append(
            {
                "status": s,
                "label": s.replace("-", " ").title() or "(no status)",
                "count": len(buckets[s]),
                "items": buckets[s],
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
