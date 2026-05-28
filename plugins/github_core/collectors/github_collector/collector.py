"""GitHubCollector — CollectorBase subclass driving the v0 collection.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-collector). Two-phase run: collection + enrichment, both
through `CollectorBase.submit_grift`.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from tap_cares.collectors.base import CollectorBase
from tap_cares.exceptions import SecretError

from .api_client import GithubAPIError, GithubClient
from .batch import (
    assemble_batch,
    edge_envelope,
    node_envelope,
)
from .enrichment import resolve_links
from .identity import (
    account_id,
    edge_id,
    job_id,
    repository_id,
    run_id,
    runner_id,
    workflow_id,
)
from .manifest import load_collection_manifest, load_link_manifest
from .parser import parse_workflow_yaml
from .secret import (
    GITHUB_SECRET_REF,
    api_base_url,
    initial_run_limit,
    resolve_github_secret,
)

logger = logging.getLogger(__name__)

# Log site tokens for the recorder. Minted via scripts/log-site-id.
_SITE_RUN_STARTED = "8fb5"
_SITE_ABORT_SECRET = "64be"
_SITE_ABORT_API = "54ce"
_SITE_REPO_DONE = "d98c"
_SITE_RUNNER_DEGRADED = "b969"
_SITE_WORKFLOW_YAML_MISSING = "9573"
_SITE_BATCH_SUBMITTED = "d66b"
_SITE_ENRICHMENT_SUMMARY = "fd9e"


class GithubCollectorError(Exception):
    """Unrecoverable error during the github_core collection run."""


class GithubCollector(CollectorBase):
    """GitHub Actions collector — single PAT, configured repos, two-phase run."""

    def _abort(self, site: str, code: str, message: str) -> None:
        self.record_error(site, code, message)
        raise GithubCollectorError(message)

    def run(self) -> None:
        self.record_info(_SITE_RUN_STARTED, "RUN_STARTED", "GitHub Core collection started.")

        # --- secret resolution (unrecoverable on failure) ---
        try:
            secret = resolve_github_secret(GITHUB_SECRET_REF)
        except SecretError as exc:
            self._abort(_SITE_ABORT_SECRET, "SECRET_UNUSABLE", f"github_pat secret unusable: {exc}")
        data = dict(secret.data)
        repos: list[str] = list(data["repos"])
        run_limit = initial_run_limit(data)

        client = GithubClient(token=data["token"], api_base_url=api_base_url(data))

        # --- manifests (load-time JSON Schema validation; errors abort) ---
        load_collection_manifest()  # validates; engine is procedural in v0
        link_manifest = load_link_manifest()

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        # --- collection phase: per-repo walk ---
        for full_name in repos:
            try:
                self._collect_repo(client, full_name, run_limit, nodes, edges)
            except GithubAPIError as exc:
                self._abort(_SITE_ABORT_API, f"GITHUB_API_{exc.status}", str(exc))
            self.record_info(_SITE_REPO_DONE, "REPO_DONE", f"Collected {full_name}")

        # --- submission phase ---
        github_batch = assemble_batch(
            batch_name=f"github_core collection: {', '.join(repos)}",
            description=f"GitHub Actions plumbing for {len(repos)} repo(s).",
            nodes=nodes,
            edges=edges,
        )
        self.submit_grift(github_batch)
        self.record_info(
            _SITE_BATCH_SUBMITTED,
            "COLLECTION_BATCH_SUBMITTED",
            f"Submitted collection batch with {len(nodes)} node(s) + {len(edges)} edge(s).",
        )

        # --- enrichment phase (link resolution against landed nodes) ---
        enrichment_dims = {"github.platform": "github.com"}
        enrichment = resolve_links(
            link_manifest=link_manifest,
            repos=repos,
            edge_default_dimensions=enrichment_dims,
        )
        if enrichment.edge_envelopes:
            enrichment_batch = assemble_batch(
                batch_name=f"github_core enrichment: {', '.join(repos)}",
                description="REFERENCES_RESOURCE edges resolved from the grid-link manifest.",
                nodes=[],
                edges=enrichment.edge_envelopes,
            )
            self.submit_grift(enrichment_batch)
        self._record_enrichment_summary(enrichment)

        self.summary = (
            f"Collected {len(repos)} repo(s): {len(nodes)} node(s), "
            f"{len(edges)} spine edge(s), "
            f"{len(enrichment.edge_envelopes)} link edge(s)."
        )

    # ---------- per-repo collection ----------

    def _collect_repo(
        self,
        client: GithubClient,
        full_name: str,
        run_limit: int,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        owner, _, repo = full_name.partition("/")
        repo_dims = {
            "github.platform": "github.com",
            "github.owner": owner,
            "github.repo": repo,
        }
        actions_dims = {**repo_dims, "github.surface": "actions"}
        observation_dims = {**actions_dims, "github.observation": "execution"}

        # account
        account_payload = self._fetch_account(client, owner)
        account_uuid = account_id(account_payload["login"])
        nodes.append(
            node_envelope(
                entity_id=account_uuid,
                entity_type="github_account",
                name=account_payload["login"],
                dimensions={**repo_dims},  # owner+repo carried even on account
                fields={
                    "login": account_payload["login"],
                    "github_id": account_payload.get("id"),
                    "account_type": account_payload.get("type", ""),
                    "html_url": account_payload.get("html_url", ""),
                    "configuration": {},
                    "tags": {},
                },
            )
        )

        # repository (envelope name == payload name == full_name for display)
        repo_payload = client.get(f"/repos/{full_name}")
        repo_uuid = repository_id(full_name)
        nodes.append(
            node_envelope(
                entity_id=repo_uuid,
                entity_type="github_repository",
                name=full_name,
                dimensions=repo_dims,
                fields={
                    "full_name": full_name,
                    "owner_login": owner,
                    "name": full_name,
                    "github_id": repo_payload.get("id"),
                    "default_branch": repo_payload.get("default_branch", ""),
                    "visibility": repo_payload.get("visibility", ""),
                    "html_url": repo_payload.get("html_url", ""),
                    "configuration": {},
                    "tags": {},
                },
            )
        )
        edges.append(self._edge("OWNS_REPO", account_uuid, repo_uuid, repo_dims))

        # workflows + workflow YAML
        workflows = client.get_paginated(
            f"/repos/{full_name}/actions/workflows", item_path="workflows"
        )
        for wf in workflows:
            wf_uuid = workflow_id(full_name, wf["id"])
            raw_yaml, parsed_config = self._fetch_workflow_config(client, full_name, wf.get("path", ""))
            wf_display_name = wf.get("name") or wf.get("path") or str(wf["id"])
            nodes.append(
                node_envelope(
                    entity_id=wf_uuid,
                    entity_type="github_workflow",
                    name=wf_display_name,
                    dimensions=actions_dims,
                    fields={
                        "full_name": full_name,
                        "workflow_id": wf["id"],
                        "path": wf.get("path", ""),
                        "name": wf_display_name,
                        "state": wf.get("state", ""),
                        "html_url": wf.get("html_url", ""),
                        "configuration": parsed_config,
                        "tags": {},
                    },
                )
            )
            edges.append(self._edge("DEFINES_WORKFLOW", repo_uuid, wf_uuid, actions_dims))

        # runs (latest run_limit)
        run_payloads = client.get_paginated(
            f"/repos/{full_name}/actions/runs",
            params={"per_page": str(min(run_limit, 100))},
            item_path="workflow_runs",
            max_pages=1,
        )[:run_limit]
        for r in run_payloads:
            run_uuid = run_id(full_name, r["id"])
            wf_ref_uuid = workflow_id(full_name, r["workflow_id"]) if r.get("workflow_id") else None
            nodes.append(
                node_envelope(
                    entity_id=run_uuid,
                    entity_type="github_actions_run",
                    name=f"Run #{r.get('run_number', r['id'])}",
                    dimensions=observation_dims,
                    fields={
                        "full_name": full_name,
                        "run_id": r["id"],
                        "run_number": r.get("run_number"),
                        "event": r.get("event", ""),
                        "status": r.get("status", ""),
                        "conclusion": r.get("conclusion") or "",
                        "head_sha": r.get("head_sha", ""),
                        "head_branch": r.get("head_branch", ""),
                        "run_started_at": r.get("run_started_at"),
                        "completed_at": r.get("updated_at"),
                        "html_url": r.get("html_url", ""),
                        "configuration": {
                            "workflow_id": r.get("workflow_id"),
                            "raw_payload_keys": sorted(r.keys()),
                        },
                        "tags": {},
                    },
                )
            )
            if wf_ref_uuid is not None:
                edges.append(self._edge("EXECUTES_WORKFLOW", run_uuid, wf_ref_uuid, observation_dims))

            # jobs for this run (latest-attempt endpoint per req-github-core-collector-8)
            jobs = client.get_paginated(
                f"/repos/{full_name}/actions/runs/{r['id']}/jobs", item_path="jobs"
            )
            for j in jobs:
                j_uuid = job_id(full_name, j["id"])
                j_display_name = j.get("name") or str(j["id"])
                nodes.append(
                    node_envelope(
                        entity_id=j_uuid,
                        entity_type="github_actions_job",
                        name=j_display_name,
                        dimensions=observation_dims,
                        fields={
                            "full_name": full_name,
                            "job_id": j["id"],
                            "name": j_display_name,
                            "status": j.get("status", ""),
                            "conclusion": j.get("conclusion") or "",
                            "started_at": j.get("started_at"),
                            "completed_at": j.get("completed_at"),
                            "html_url": j.get("html_url", ""),
                            "configuration": {
                                "runner_id": j.get("runner_id"),
                                "runner_name": j.get("runner_name"),
                                "runner_group_id": j.get("runner_group_id"),
                                "labels": j.get("labels") or [],
                                "steps": j.get("steps") or [],
                            },
                            "tags": {},
                        },
                    )
                )
                edges.append(self._edge("HAS_JOB", run_uuid, j_uuid, observation_dims))

        # runners (graceful-degrade on 403 per req-github-core-collector-5)
        try:
            runners = client.get_paginated(
                f"/repos/{full_name}/actions/runners", item_path="runners"
            )
        except GithubAPIError as exc:
            if exc.status == 403:
                self.record_warn(
                    _SITE_RUNNER_DEGRADED,
                    "RUNNER_CONFIG_FORBIDDEN",
                    f"Runner config inaccessible for {full_name}: {exc.body[:120]}",
                )
                runners = []
            else:
                raise
        runner_uuid_by_id: dict[int, Any] = {}
        for rn in runners:
            rn_uuid = runner_id(full_name, rn["id"])
            runner_uuid_by_id[rn["id"]] = rn_uuid
            rn_display_name = rn.get("name") or str(rn["id"])
            nodes.append(
                node_envelope(
                    entity_id=rn_uuid,
                    entity_type="github_runner",
                    name=rn_display_name,
                    dimensions=actions_dims,
                    fields={
                        "full_name": full_name,
                        "runner_id": rn["id"],
                        "name": rn_display_name,
                        "os": rn.get("os", ""),
                        "status": rn.get("status", ""),
                        "busy": bool(rn.get("busy", False)),
                        "labels": [lab.get("name") if isinstance(lab, dict) else lab for lab in rn.get("labels", [])],
                        "configuration": {},
                        "tags": {},
                    },
                )
            )

        # EXECUTED_ON edges (only when an observed job runner_id matches a durable runner node)
        for r in run_payloads:
            run_jobs = client.get_paginated(
                f"/repos/{full_name}/actions/runs/{r['id']}/jobs", item_path="jobs"
            )
            for j in run_jobs:
                if j.get("runner_id") and j["runner_id"] in runner_uuid_by_id:
                    j_uuid = job_id(full_name, j["id"])
                    rn_uuid = runner_uuid_by_id[j["runner_id"]]
                    edges.append(self._edge("EXECUTED_ON", j_uuid, rn_uuid, observation_dims))

    # ---------- helpers ----------

    def _edge(
        self,
        edge_type: str,
        source_uuid: Any,
        target_uuid: Any,
        dimensions: dict[str, str],
    ) -> dict[str, Any]:
        return edge_envelope(
            entity_id=edge_id(edge_type, source_uuid, target_uuid),
            edge_type=edge_type,
            source_id=source_uuid,
            target_id=target_uuid,
            dimensions=dimensions,
        )

    def _fetch_account(self, client: GithubClient, owner: str) -> dict[str, Any]:
        try:
            return client.get(f"/users/{owner}")
        except GithubAPIError as exc:
            if exc.status == 404:
                # Maybe it's an org; let /orgs handle it (rare for user-owned repos).
                return client.get(f"/orgs/{owner}")
            raise

    def _fetch_workflow_config(
        self, client: GithubClient, full_name: str, path: str
    ) -> tuple[str, dict[str, Any]]:
        """Fetch workflow YAML via Contents API; return (raw, parsed configuration)."""
        if not path:
            return "", parse_workflow_yaml("")
        try:
            payload = client.get(f"/repos/{full_name}/contents/{path}")
        except GithubAPIError as exc:
            if exc.status == 404:
                self.record_warn(
                    _SITE_WORKFLOW_YAML_MISSING,
                    "WORKFLOW_YAML_MISSING",
                    f"{full_name} workflow file not found: {path}",
                )
                return "", parse_workflow_yaml("")
            raise
        encoded = payload.get("content", "")
        raw_yaml = base64.b64decode(encoded).decode("utf-8") if encoded else ""
        return raw_yaml, parse_workflow_yaml(raw_yaml)

    def _record_enrichment_summary(self, enrichment: Any) -> None:
        emitted = sum(1 for r in enrichment.resolutions if r.emitted_edge)
        zero = sum(1 for r in enrichment.resolutions if r.candidate_count == 0)
        multi = sum(1 for r in enrichment.resolutions if r.candidate_count > 1)
        near = len(enrichment.near_matches)
        self.record_info(
            _SITE_ENRICHMENT_SUMMARY,
            "ENRICHMENT_SUMMARY",
            f"Link resolution: {emitted} edge(s) emitted, "
            f"{zero} zero-candidate, {multi} multi-candidate, "
            f"{near} near-match warning(s).",
        )
        # Multi-candidate failures are warnings per req-github-core-grid-links-3.
        for res in enrichment.resolutions:
            if res.candidate_count > 1:
                self.record_warn(
                    "3812",
                    "LINK_AMBIGUOUS",
                    f"Rule {res.rule_name} on {res.source_entity_type}: value "
                    f"{res.source_value!r} matched {res.candidate_count} candidates; no edge emitted.",
                )
        # Near-match warnings surface "almost looks right but not quite" rows
        # (GHES tenant URLs, typos, alternate audiences) so the operator can
        # investigate instead of silently missing the link.
        for nm in enrichment.near_matches:
            self.record_warn(
                "db00",
                "LINK_NEAR_MATCH",
                f"Rule {nm.rule_name}: no exact match for {nm.expected_value!r} on "
                f"{nm.target_entity_type}.{nm.expected_value}, but a near-match exists: "
                f"{nm.target_value!r}. Not linking — investigate whether the rule should "
                f"be extended or the target is misconfigured.",
            )
