"""Decompose fetched compliance artifacts into GRIFT node + edge envelopes.

The decomposition is the heart of the samsite compliance collector: it turns
each fetched artifact (KSI signal JSON, VDR report JSON, OSCAL/IIW renderings)
into the grid-native ``fedramp_20x_ksi`` nodes and edges defined in
spec-fedramp-20x-ksi-compliance-artifacts-v0.md.

KSI signal -> ksi_signal + N ksi_component + N ksi_validation + M ksi_violation,
linked by DECLARES_COMPONENT / DECLARES_VALIDATION / EVALUATES_COMPONENT /
REPORTS_VIOLATION edges.

VDR report -> vdr_report + N vdr_finding, linked by REPORTS_FINDING. The
optional REFERENCES_SIGNAL edge (vdr_report -> ksi_signal) is emitted when
both artifacts come from the same ``system_id`` in this run. The
AFFECTS_RESOURCE edge is best-effort — emitted only where the finding's
``resource`` cleanly maps to an on-grid ksi_component.

OSCAL SSP / OSCAL POA&M / IIW -> one ``compliance_artifact`` blob node each,
no edges. They are renderings of the KSI inventory and are kept whole.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .identity import edge_entity_id, node_entity_id

_DIM_KSI_SIGNAL = {"compliance": "ksi-signal"}
_DIM_VDR = {"compliance": "vdr"}
_DIM_ARTIFACT = {"compliance": "compliance-artifact"}


@dataclass
class DecomposedArtifact:
    """The GRIFT envelopes produced from one artifact, plus a small index used
    to resolve cross-artifact edges within the same run."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    # system_id -> ksi_signal entity_id (str). Populated when this artifact is
    # a ksi_signal; consumed by VDR REFERENCES_SIGNAL resolution.
    ksi_signal_by_system: dict[str, str] = field(default_factory=dict)
    # component_id -> ksi_component entity_id (str). Populated by ksi_signal;
    # consumed by VDR AFFECTS_RESOURCE best-effort resolution.
    ksi_component_by_id: dict[str, str] = field(default_factory=dict)


def _node_envelope(
    entity_type: str,
    entity_id: str,
    name: str,
    dimensions: dict[str, str],
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entity": {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "name": name,
            "dimensions": dimensions,
        },
        "node": {"name": name, **fields},
    }


def _edge_envelope(
    edge_type: str,
    edge_id: str,
    from_entity_id: str,
    to_entity_id: str,
) -> dict[str, Any]:
    return {
        "entity": {
            "entity_id": edge_id,
            "entity_type": "edge",
            "name": edge_type,
            "dimensions": {},
        },
        "edge": {
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "edge_type": edge_type,
            "properties": {},
        },
    }


def _verification_fields(verification: dict[str, Any] | None) -> dict[str, Any]:
    """The collector-populated signature verification fields, or empty/null."""
    if not verification:
        return {
            "signature_verified": None,
            "signed_by": "",
            "rekor_log_index": "",
            "verified_at": "",
        }
    return {
        "signature_verified": verification.get("signature_verified"),
        "signed_by": verification.get("signed_by") or "",
        "rekor_log_index": str(verification.get("rekor_log_index") or ""),
        "verified_at": verification.get("verified_at") or "",
    }


def decompose_ksi_signal(
    signal: dict[str, Any],
    *,
    verification: dict[str, Any] | None = None,
) -> DecomposedArtifact:
    """Decompose a KSI signal document into nodes + edges."""
    out = DecomposedArtifact()

    signal_id = signal.get("signal_id") or ""
    system_id = signal.get("system_id") or ""
    if not signal_id:
        return out

    # ---- ksi_signal node -----------------------------------------------------
    provenance = signal.get("provenance") or {}
    builder = provenance.get("builder") or {}
    source = provenance.get("source") or {}
    ownership = signal.get("ownership") or {}
    disclosure = signal.get("disclosure") or {}

    signal_node_id = str(node_entity_id("ksi_signal", signal_id))
    out.ksi_signal_by_system[system_id] = signal_node_id
    signal_name = f"KSI signal {signal_id} @ {signal.get('emitted_at', '')}"
    out.nodes.append(
        _node_envelope(
            "ksi_signal",
            signal_node_id,
            signal_name,
            _DIM_KSI_SIGNAL,
            {
                "signal_version": signal.get("signal_version") or "",
                "signal_id": signal_id,
                "emitted_at": signal.get("emitted_at") or "",
                "emitter": signal.get("emitter") or "",
                "csp": signal.get("csp") or "",
                "system_id": system_id,
                "provenance_builder_id": builder.get("id") or "",
                "provenance_builder_run_id": builder.get("run_id") or "",
                "provenance_builder_version": builder.get("version") or "",
                "provenance_source_repository": source.get("repository") or "",
                "provenance_source_commit": source.get("commit") or "",
                "provenance_source_ref": source.get("ref") or "",
                "system_owner": ownership.get("system_owner") or "",
                "application_owner": ownership.get("application_owner") or "",
                "operator_contact": ownership.get("operator_contact") or "",
                "authorization_status": disclosure.get("authorization_status") or "",
                "fedramp_certified": disclosure.get("fedramp_certified"),
                "disclosure_remarks": disclosure.get("remarks") or "",
                "attestation": provenance.get("attestation") or {},
                **_verification_fields(verification),
            },
        )
    )

    # ---- ksi_component nodes + DECLARES_COMPONENT edges ----------------------
    for component in signal.get("components") or []:
        component_id = component.get("component_id") or ""
        if not component_id:
            continue
        comp_node_id = str(node_entity_id("ksi_component", component_id))
        out.ksi_component_by_id[component_id] = comp_node_id
        global_id = component.get("global_id") or {}
        security_category = component.get("security_category") or {}
        out.nodes.append(
            _node_envelope(
                "ksi_component",
                comp_node_id,
                component_id,
                _DIM_KSI_SIGNAL,
                {
                    "component_id": component_id,
                    "component_type": component.get("type") or "",
                    "native_id": component.get("native_id") or "",
                    "global_purl": global_id.get("purl") or "",
                    "global_sha256": global_id.get("sha256") or "",
                    "global_image_digest": global_id.get("image_digest") or "",
                    "security_confidentiality": security_category.get("confidentiality") or "",
                    "security_integrity": security_category.get("integrity") or "",
                    "security_availability": security_category.get("availability") or "",
                    "attributes": component.get("attributes") or {},
                    "information_flow": component.get("information_flow") or [],
                },
            )
        )
        out.edges.append(
            _edge_envelope(
                "DECLARES_COMPONENT",
                str(edge_entity_id("DECLARES_COMPONENT", signal_id, component_id)),
                signal_node_id,
                comp_node_id,
            )
        )

    # ---- ksi_validation nodes + DECLARES_VALIDATION + EVALUATES_COMPONENT + REPORTS_VIOLATION
    for validation in signal.get("validations") or []:
        validation_id = validation.get("validation_id") or ""
        if not validation_id:
            continue
        val_key = f"{signal_id}/{validation_id}"
        val_node_id = str(node_entity_id("ksi_validation", val_key))
        policy = validation.get("policy") or {}
        val_name = f"{validation_id} ({validation.get('result', '?')})"
        out.nodes.append(
            _node_envelope(
                "ksi_validation",
                val_node_id,
                val_name,
                _DIM_KSI_SIGNAL,
                {
                    "validation_id": validation_id,
                    "policy_id": policy.get("id") or "",
                    "policy_version": policy.get("version") or "",
                    "result": validation.get("result") or "",
                },
            )
        )
        out.edges.append(
            _edge_envelope(
                "DECLARES_VALIDATION",
                str(edge_entity_id("DECLARES_VALIDATION", signal_id, val_key)),
                signal_node_id,
                val_node_id,
            )
        )

        # EVALUATES_COMPONENT — the component_refs join.
        for component_ref in validation.get("component_refs") or []:
            comp_node_id = out.ksi_component_by_id.get(component_ref)
            if not comp_node_id:
                continue  # validation referenced a component the signal didn't declare; skip
            out.edges.append(
                _edge_envelope(
                    "EVALUATES_COMPONENT",
                    str(edge_entity_id("EVALUATES_COMPONENT", val_key, component_ref)),
                    val_node_id,
                    comp_node_id,
                )
            )

        # REPORTS_VIOLATION — each violation becomes its own ksi_violation node.
        for index, violation in enumerate(validation.get("violations") or []):
            violation_key = f"{val_key}/{index}"
            violation_node_id = str(node_entity_id("ksi_violation", violation_key))
            violation_type = violation.get("type") or ""
            violation_name = f"{violation_type or 'violation'} @ {validation_id}#{index}"
            out.nodes.append(
                _node_envelope(
                    "ksi_violation",
                    violation_node_id,
                    violation_name,
                    _DIM_KSI_SIGNAL,
                    {
                        "violation_type": violation_type,
                        "message": violation.get("message") or "",
                        "severity": violation.get("severity") or "",
                        "resource": violation.get("resource") or "",
                    },
                )
            )
            out.edges.append(
                _edge_envelope(
                    "REPORTS_VIOLATION",
                    str(edge_entity_id("REPORTS_VIOLATION", val_key, violation_key)),
                    val_node_id,
                    violation_node_id,
                )
            )

    return out


def decompose_vdr_report(
    report: dict[str, Any],
    *,
    ksi_signal_by_system: dict[str, str] | None = None,
    ksi_component_by_id: dict[str, str] | None = None,
    verification: dict[str, Any] | None = None,
) -> DecomposedArtifact:
    """Decompose a VDR report document into nodes + edges."""
    out = DecomposedArtifact()
    ksi_signal_by_system = ksi_signal_by_system or {}
    ksi_component_by_id = ksi_component_by_id or {}

    report_id = report.get("report_id") or ""
    system_id = report.get("system_id") or ""
    if not report_id:
        return out

    report_node_id = str(node_entity_id("vdr_report", report_id))
    report_name = f"VDR report {report_id[:8]} @ {report.get('emitted_at', '')}"
    out.nodes.append(
        _node_envelope(
            "vdr_report",
            report_node_id,
            report_name,
            _DIM_VDR,
            {
                "report_version": report.get("report_version") or "",
                "report_id": report_id,
                "emitted_at": report.get("emitted_at") or "",
                "system_id": system_id,
                "vdr_class": report.get("class") or "",
                "ksi_signal_ref": report.get("ksi_signal_ref") or "",
                "poam_ref": report.get("poam_ref") or "",
                "summary": report.get("summary") or {},
            },
        )
    )

    # REFERENCES_SIGNAL — pair the VDR report to the KSI signal for the same system.
    sibling_signal_id = ksi_signal_by_system.get(system_id)
    if sibling_signal_id:
        out.edges.append(
            _edge_envelope(
                "REFERENCES_SIGNAL",
                str(edge_entity_id("REFERENCES_SIGNAL", report_id, sibling_signal_id)),
                report_node_id,
                sibling_signal_id,
            )
        )

    # Findings (disposition: open) and risk_accepted (disposition: risk-accepted)
    # are both vdr_finding nodes — one model, disposition discriminator.
    def _finding_node(record: dict[str, Any], default_disposition: str) -> None:
        tracking_id = record.get("tracking_id") or ""
        if not tracking_id:
            return
        finding_key = f"{report_id}/{tracking_id}"
        finding_node_id = str(node_entity_id("vdr_finding", finding_key))
        finding_name = (record.get("title") or tracking_id)[:200]
        disposition = record.get("current_disposition") or default_disposition
        out.nodes.append(
            _node_envelope(
                "vdr_finding",
                finding_node_id,
                finding_name,
                _DIM_VDR,
                {
                    "tracking_id": tracking_id,
                    "source": record.get("source") or "",
                    "tool_id": record.get("tool_id") or "",
                    "title": record.get("title") or "",
                    "description": record.get("description") or "",
                    "resource": record.get("resource") or "",
                    "cve": record.get("cve") or "",
                    "first_detected": record.get("first_detected") or "",
                    "days_since_first_detected": record.get("days_since_first_detected"),
                    "pain": record.get("pain") or "",
                    "internet_reachable": bool(record.get("internet_reachable")),
                    "likely_exploitable": bool(record.get("likely_exploitable")),
                    "is_kev": bool(record.get("is_kev")),
                    "current_disposition": disposition,
                    "remediation_sla_days": record.get("remediation_sla_days"),
                    "remediation_due_at": record.get("remediation_due_at") or "",
                    "is_blocking": bool(record.get("is_blocking")),
                    "block_reason": record.get("block_reason") or "",
                    "explanation": record.get("explanation") or "",
                    "poam_ref": record.get("poam_ref") or "",
                },
            )
        )
        out.edges.append(
            _edge_envelope(
                "REPORTS_FINDING",
                str(edge_entity_id("REPORTS_FINDING", report_id, tracking_id)),
                report_node_id,
                finding_node_id,
            )
        )

        # AFFECTS_RESOURCE — best-effort. resource strings are heterogeneous
        # (ecosystem:package, tf addresses, ARNs); v0 emits the edge only if
        # the resource cleanly matches a known ksi_component_id, else skips.
        resource = record.get("resource") or ""
        component_node_id = ksi_component_by_id.get(resource)
        if component_node_id:
            out.edges.append(
                _edge_envelope(
                    "AFFECTS_RESOURCE",
                    str(edge_entity_id("AFFECTS_RESOURCE", finding_key, resource)),
                    finding_node_id,
                    component_node_id,
                )
            )

    for finding in report.get("findings") or []:
        _finding_node(finding, "open")
    for accepted in report.get("risk_accepted") or []:
        _finding_node(accepted, "risk-accepted")

    return out


def decompose_compliance_artifact(
    *,
    body: bytes,
    artifact_kind: str,
    source_url: str,
    fetched_at: str,
    content_format: str,
    verification: dict[str, Any] | None = None,
) -> DecomposedArtifact:
    """A rendering artifact (OSCAL SSP/POA&M, IIW) kept whole — one node, no edges."""
    out = DecomposedArtifact()

    # Identity: kind + a per-emission discriminator. The fetched_at is the
    # per-run discriminator; the same kind re-fetched at a different time
    # produces a different node (per-emission, per the spec).
    natural_key = f"{artifact_kind}/{fetched_at}"
    artifact_node_id = str(node_entity_id("compliance_artifact", natural_key))

    if content_format == "json":
        import json

        try:
            content: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            content = body.decode("utf-8", errors="replace")
    else:
        # IIW is CSV — stored as text (JSONField can hold a string).
        content = body.decode("utf-8", errors="replace")

    artifact_name = f"{artifact_kind} @ {fetched_at}"
    out.nodes.append(
        _node_envelope(
            "compliance_artifact",
            artifact_node_id,
            artifact_name,
            _DIM_ARTIFACT,
            {
                "kind": artifact_kind,
                "source_url": source_url,
                "content_type": content_format,
                "fetched_at": fetched_at,
                "size_bytes": len(body),
                "content": content,
                **_verification_fields(verification),
            },
        )
    )
    return out
