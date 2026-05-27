"""Workflow YAML parser.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-workflow-parse). v0 extracts triggers, permissions, job
metadata (`runs-on`, `needs`, `uses`), and categorized refs for the link
manifest's enrichment phase. Secret/variable references are deferred per
req-github-core-backlog-references and deliberately NOT extracted here.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

# Categorization patterns for the grid-link enrichment phase. Conservative —
# false positives produce zero-candidate warnings (no edge), not bad data.
_AWS_REGION_RE = re.compile(r"^(us|eu|ap|sa|ca|me|af|cn|us-gov)(-[a-z]+)+-\d+$")
_CLOUDFRONT_DISTRIBUTION_ID_RE = re.compile(r"^E[0-9A-Z]{12,16}$")
# Loose domain pattern: at least one dot, no slashes, no spaces, valid TLD.
_DOMAIN_NAME_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", re.IGNORECASE)


def parse_workflow_yaml(raw_yaml: str) -> dict[str, Any]:
    """Parse workflow YAML into the configuration shape declared in the spec.

    Returns a dict suitable for assignment to `github_workflow.configuration`.
    Keys: triggers, permissions, jobs (list), refs (categorized), raw_yaml.
    """
    parsed = yaml.safe_load(raw_yaml) or {}
    if not isinstance(parsed, dict):
        return {"raw_yaml": raw_yaml, "triggers": [], "permissions": {}, "jobs": [], "refs": _empty_refs()}

    # YAML 1.1 gotcha: `on:` parses as boolean `True`. Check both keys.
    triggers = _extract_triggers(parsed.get("on", parsed.get(True)))
    permissions = _normalize_permissions(parsed.get("permissions"))
    jobs = [_extract_job(job_id, job_def) for job_id, job_def in (parsed.get("jobs") or {}).items()]
    refs = _categorize_refs(parsed)

    return {
        "raw_yaml": raw_yaml,
        "triggers": triggers,
        "permissions": permissions,
        "jobs": jobs,
        "refs": refs,
    }


def _extract_triggers(on_block: Any) -> list[str]:
    if on_block is None:
        return []
    if isinstance(on_block, str):
        return [on_block]
    if isinstance(on_block, list):
        return [str(x) for x in on_block]
    if isinstance(on_block, dict):
        return sorted(on_block.keys())
    return []


def _normalize_permissions(perms: Any) -> dict[str, str] | str:
    # GitHub allows `permissions: read-all`/`write-all`/None, or a dict of
    # scope -> level. Preserve the shape for inspection.
    if perms is None:
        return {}
    if isinstance(perms, str):
        return perms
    if isinstance(perms, dict):
        return {k: str(v) for k, v in perms.items()}
    return {}


def _extract_job(job_id: str, job_def: Any) -> dict[str, Any]:
    if not isinstance(job_def, dict):
        return {"id": job_id, "name": job_id, "runs_on": "", "needs": [], "uses": "", "steps": []}
    needs = job_def.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    return {
        "id": job_id,
        "name": str(job_def.get("name") or job_id),
        "runs_on": str(job_def.get("runs-on") or ""),
        "needs": [str(n) for n in needs],
        "uses": str(job_def.get("uses") or ""),
        "steps": job_def.get("steps") or [],
    }


def _categorize_refs(parsed: dict[str, Any]) -> dict[str, list[str]]:
    """Walk the YAML for string values and categorize them for link rules.

    Used by the enrichment phase. Conservative pattern matching; false hits
    just fail to find a grid candidate and produce no edge.
    """
    refs = _empty_refs()
    for value in _string_values(parsed):
        if _AWS_REGION_RE.match(value):
            _append_unique(refs["aws_regions"], value)
        elif _CLOUDFRONT_DISTRIBUTION_ID_RE.match(value):
            _append_unique(refs["cloudfront_distribution_ids"], value)
        elif _DOMAIN_NAME_RE.match(value):
            _append_unique(refs["domain_names"], value.lower())
    return refs


def _empty_refs() -> dict[str, list[str]]:
    return {
        "domain_names": [],
        "aws_regions": [],
        "cloudfront_distribution_ids": [],
    }


def _append_unique(lst: list[str], value: str) -> None:
    if value not in lst:
        lst.append(value)


def _string_values(obj: Any) -> list[str]:
    out: list[str] = []
    stack: list[Any] = [obj]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out
