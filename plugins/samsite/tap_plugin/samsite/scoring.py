"""KSI Scoreboard — joins the FedRAMP 20x KSI catalog against the OSCAL SSP
and POA&M to compute per-indicator pass/in-progress/accepted/gap status.

Pure-function math, no Django or ORM. Inputs are the KSI indicator catalog
(list of dicts), the parsed OSCAL SSP document, and the parsed OSCAL POA&M
document. Outputs a ScoreboardResult with per-indicator detail and a
top-level totals strip.

Spec: plugins/samsite/specs/spec-samsite-ksi-scoreboard-v0.md (to land).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Status taxonomy
# ---------------------------------------------------------------------------

# Per-control statuses (worst-case wins in aggregation).
CONTROL_PASS = "pass"
CONTROL_NA = "n/a"
CONTROL_PARTIAL = "partial"
CONTROL_OPEN = "open"
CONTROL_ACCEPTED = "accepted"
CONTROL_UNMAPPED = "unmapped"

# Per-indicator aggregated statuses.
INDICATOR_PASSING = "passing"
INDICATOR_IN_PROGRESS = "in-progress"
INDICATOR_ACCEPTED = "accepted"
INDICATOR_GAP = "gap"


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class ControlResult:
    control_id: str
    status: str  # one of CONTROL_*
    ssp_implementation_status: str  # raw OSCAL value, "" if missing
    poam_item_ids: list[str] = field(default_factory=list)


@dataclass
class IndicatorResult:
    code: str
    name: str
    description: str
    theme_code: str  # e.g. "KSI-CMT"
    classes: list[str]
    status: str  # one of INDICATOR_*
    controls: list[ControlResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.controls if c.status in (CONTROL_PASS, CONTROL_NA))

    @property
    def total_count(self) -> int:
        return len(self.controls)


@dataclass
class ScoreboardResult:
    system_class: str | None
    indicators: list[IndicatorResult] = field(default_factory=list)
    excluded_class_mismatch: int = 0  # indicators not applicable to system_class
    totals: dict[str, int] = field(default_factory=dict)  # indicator-status counts


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------


def _ssp_control_status_map(ssp_doc: dict | None) -> dict[str, str]:
    """Map control-id → SSP implementation-status (lowercase Rev-5 ids)."""
    if not ssp_doc:
        return {}
    root = ssp_doc.get("system-security-plan") or {}
    ci = root.get("control-implementation") or {}
    out: dict[str, str] = {}
    for req in ci.get("implemented-requirements") or []:
        if not isinstance(req, dict):
            continue
        cid = (req.get("control-id") or "").strip().lower()
        if not cid:
            continue
        status = ""
        for p in req.get("props") or []:
            if isinstance(p, dict) and p.get("name") == "implementation-status":
                status = p.get("value") or ""
                break
        # Last write wins if duplicates, which shouldn't happen.
        out[cid] = status
    return out


def _poam_control_coverage(poam_doc: dict | None) -> dict[str, list[tuple[str, str]]]:
    """Map control-id → list of (poam-id, status) covering that control.

    The FedRAMP convention puts referenced controls in a `controls` (plural)
    prop as a comma-separated string. Falls back to `control` (singular) for
    older docs that use that name.
    """
    if not poam_doc:
        return {}
    root = poam_doc.get("plan-of-action-and-milestones") or {}
    out: dict[str, list[tuple[str, str]]] = {}
    for it in root.get("poam-items") or []:
        if not isinstance(it, dict):
            continue
        props = {p.get("name"): p.get("value") for p in (it.get("props") or []) if isinstance(p, dict)}
        poam_id = props.get("poam-id") or it.get("uuid") or ""
        status = (props.get("status") or "").lower()
        controls_prop = props.get("controls") or props.get("control") or ""
        for raw in controls_prop.split(","):
            cid = raw.strip().lower()
            if not cid:
                continue
            out.setdefault(cid, []).append((poam_id, status))
    return out


def _system_class_from_ssp(ssp_doc: dict | None) -> str | None:
    """Read FedRAMP 20x class ('a'/'b'/'c'/'d') from the SSP metadata, lowercased.

    The convention is a metadata prop `fedramp-class` with the value `A/B/C/D`.
    Returns None if the SSP doesn't declare one.
    """
    if not ssp_doc:
        return None
    root = ssp_doc.get("system-security-plan") or {}
    md = root.get("metadata") or {}
    for p in md.get("props") or []:
        if isinstance(p, dict) and p.get("name") == "fedramp-class":
            v = (p.get("value") or "").strip().lower()
            if v in {"a", "b", "c", "d"}:
                return v
    return None


def _theme_from_code(code: str) -> str:
    """Extract theme prefix from an indicator code: 'KSI-CMT-LMC' -> 'KSI-CMT'."""
    parts = (code or "").split("-")
    if len(parts) >= 2:
        return "-".join(parts[:2])
    return code or ""


def _resolve_indicator_controls(indicator: dict, system_class: str | None) -> list[str]:
    """Return the control list for an indicator, honoring class_variants when set.

    If class_variants is a dict with the system's class as a key, its value
    (an object with a `controls` array) overrides the base controls list.
    Otherwise the indicator's base `controls` array applies.
    """
    base = list(indicator.get("controls") or [])
    variants = indicator.get("class_variants")
    if (
        system_class
        and isinstance(variants, dict)
        and system_class in variants
        and isinstance(variants[system_class], dict)
        and isinstance(variants[system_class].get("controls"), list)
    ):
        return [c for c in variants[system_class]["controls"] if isinstance(c, str)]
    return [c for c in base if isinstance(c, str)]


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


# Priority order for indicator-status aggregation (worst-case wins).
_INDICATOR_PRIORITY = {
    INDICATOR_GAP: 4,
    INDICATOR_IN_PROGRESS: 3,
    INDICATOR_ACCEPTED: 2,
    INDICATOR_PASSING: 1,
}


def _aggregate_indicator_status(controls: list[ControlResult]) -> str:
    if not controls:
        # No controls listed on the indicator at all → no signal to evaluate.
        # Treat as a gap so it surfaces; the indicator catalog itself is the bug.
        return INDICATOR_GAP

    worst = INDICATOR_PASSING
    for c in controls:
        if c.status == CONTROL_UNMAPPED:
            cand = INDICATOR_GAP
        elif c.status in (CONTROL_OPEN, CONTROL_PARTIAL):
            cand = INDICATOR_IN_PROGRESS
        elif c.status == CONTROL_ACCEPTED:
            cand = INDICATOR_ACCEPTED
        else:  # pass, n/a
            cand = INDICATOR_PASSING
        if _INDICATOR_PRIORITY[cand] > _INDICATOR_PRIORITY[worst]:
            worst = cand
    return worst


def _evaluate_control(
    control_id: str,
    ssp_status_map: dict[str, str],
    poam_coverage: dict[str, list[tuple[str, str]]],
) -> ControlResult:
    cid = control_id.strip().lower()
    poam_entries = poam_coverage.get(cid) or []
    poam_open = [pid for pid, st in poam_entries if st == "open"]
    poam_accepted = [pid for pid, st in poam_entries if st == "risk-accepted"]
    poam_ids = [pid for pid, _ in poam_entries]

    if cid not in ssp_status_map:
        return ControlResult(
            control_id=cid, status=CONTROL_UNMAPPED, ssp_implementation_status="", poam_item_ids=poam_ids
        )

    ssp_status = (ssp_status_map[cid] or "").lower()
    if poam_open:
        return ControlResult(
            control_id=cid, status=CONTROL_OPEN, ssp_implementation_status=ssp_status, poam_item_ids=poam_ids
        )
    if poam_accepted:
        return ControlResult(
            control_id=cid, status=CONTROL_ACCEPTED, ssp_implementation_status=ssp_status, poam_item_ids=poam_ids
        )
    if ssp_status == "not-applicable":
        return ControlResult(
            control_id=cid, status=CONTROL_NA, ssp_implementation_status=ssp_status, poam_item_ids=poam_ids
        )
    if ssp_status == "partial":
        return ControlResult(
            control_id=cid, status=CONTROL_PARTIAL, ssp_implementation_status=ssp_status, poam_item_ids=poam_ids
        )
    # implemented (or any other "looks implemented" value) → pass
    return ControlResult(
        control_id=cid, status=CONTROL_PASS, ssp_implementation_status=ssp_status, poam_item_ids=poam_ids
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def score(
    *,
    indicators: list[dict],
    ssp_doc: dict | None,
    poam_doc: dict | None,
    system_class: str | None = None,
) -> ScoreboardResult:
    """Compute the KSI scoreboard.

    `indicators` is a list of dicts shaped like the `ksi_indicator` model's
    JSON projection: must have `code`, `name`, `controls`, `classes`. Optional
    `description`, `class_variants`.

    If `system_class` is None, it's derived from the SSP's `fedramp-class`
    metadata prop. Indicators whose `classes` array doesn't contain the
    system class are excluded (and counted in `excluded_class_mismatch`).
    If the system class can't be determined, all indicators are scored
    regardless of class (no filtering).
    """
    ssp_map = _ssp_control_status_map(ssp_doc)
    poam_cov = _poam_control_coverage(poam_doc)
    resolved_class = system_class or _system_class_from_ssp(ssp_doc)

    results: list[IndicatorResult] = []
    excluded = 0

    for ind in indicators:
        if not isinstance(ind, dict):
            continue
        classes = [c.lower() for c in (ind.get("classes") or []) if isinstance(c, str)]
        if resolved_class and classes and resolved_class not in classes:
            excluded += 1
            continue

        controls_for_class = _resolve_indicator_controls(ind, resolved_class)
        control_results = [_evaluate_control(cid, ssp_map, poam_cov) for cid in controls_for_class]
        indicator_status = _aggregate_indicator_status(control_results)

        results.append(
            IndicatorResult(
                code=ind.get("code") or "",
                name=ind.get("name") or "",
                description=ind.get("description") or "",
                theme_code=_theme_from_code(ind.get("code") or ""),
                classes=classes,
                status=indicator_status,
                controls=control_results,
            )
        )

    # Sort by theme then code for stable display.
    results.sort(key=lambda r: (r.theme_code, r.code))

    totals = Counter(r.status for r in results)
    return ScoreboardResult(
        system_class=resolved_class,
        indicators=results,
        excluded_class_mismatch=excluded,
        totals=dict(totals),
    )


def group_by_theme(result: ScoreboardResult) -> list[dict[str, Any]]:
    """Group indicators by theme code, preserving sort order from `score()`."""
    out: list[dict[str, Any]] = []
    by_theme: dict[str, list[IndicatorResult]] = {}
    for ind in result.indicators:
        by_theme.setdefault(ind.theme_code, []).append(ind)
    for theme_code, inds in by_theme.items():
        theme_totals = Counter(i.status for i in inds)
        out.append(
            {
                "theme_code": theme_code,
                "indicators": inds,
                "totals": dict(theme_totals),
                "total_count": len(inds),
            }
        )
    return out
