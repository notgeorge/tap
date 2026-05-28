"""GitHubCollector — CollectorBase subclass driving the v0 collection.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-collector). Two-phase run: collection + enrichment, both
through `CollectorBase.submit_grift`.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from tap_cares.collectors import (
    CollectorDocRef,
    CollectorReadinessStatus,
    CollectorSelfTestResult,
    check_fail,
    check_pass,
)
from tap_cares.collectors.base import CollectorBase
from tap_cares.exceptions import (
    SecretError,
    SecretNotFoundError,
    SecretValidationError,
)

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
    platform_id,
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
_SITE_RUN_JOBS_MISSING = "bcff"
_SITE_INCREMENTAL_WINDOW = "c2ca"
_SITE_NON_TERMINAL_REFRESH = "6558"
_SITE_RUN_NOT_FOUND = "f938"
_SITE_LOCAL_ACTION_DEFERRED = "b148"

_DOCS = (
    CollectorDocRef(
        plugin="github_core",
        doc="collector",
        section="self-test",
        label="GitHub Core collector self-test",
    ),
)

# GitHub Actions `status` values that are non-terminal — runs in any of these
# states are re-fetched on every collection until they reach `completed`
# (`req-github-core-collector-4`). Enumerating terminal-vs-not is more robust
# than enumerating "the non-terminal ones": GitHub may add new in-flight
# states (`waiting`, `pending`, `requested`, `action_required`, etc.) and
# anything we don't recognize is safer treated as "keep watching."
_TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"completed"})

# The platform instance every collected account/repo/workflow hangs under.
# v0 is github.com only; a GHES host would key on its own hostname.
_PLATFORM_HOST = "github.com"
_PLATFORM_DIMENSIONS = {"github.platform": "github.com"}


class GithubCollectorError(Exception):
    """Unrecoverable error during the github_core collection run."""


class GithubCollector(CollectorBase):
    """GitHub Actions collector — single PAT, configured repos, two-phase run."""

    @classmethod
    def self_test(cls) -> CollectorSelfTestResult:
        """Operator-facing readiness check for the github_core collector.

        Four checks in order; each short-circuits the rest on failure with an
        actionable readiness status:
          1. GITHUB_SECRET_PRESENT — `github_pat` secret file exists
          2. GITHUB_SECRET_VALID   — secret schema validates (token, repos, ...)
          3. GITHUB_API_REACHABLE  — `GET /rate_limit` succeeds within budget
          4. GITHUB_REPO_ACCESS    — per-configured-repo `GET /repos/{owner}/{repo}`
                                     succeeds; surfaces which repo(s) fail

        The empty-body-404 retry in `api_client` is deliberately disabled for
        self-test paths: a real auth/access 404 should surface immediately,
        not after the full backoff budget (which won't change the outcome).
        """
        checks: list = []

        # 1. Secret present.
        try:
            secret = resolve_github_secret(GITHUB_SECRET_REF)
        except SecretNotFoundError as exc:
            checks.append(
                check_fail(
                    "GITHUB_SECRET_PRESENT",
                    f"github_pat secret is not configured: {exc}",
                    readiness_status=CollectorReadinessStatus.UNCONFIGURED,
                    docs=_DOCS,
                )
            )
            return CollectorSelfTestResult.from_checks(
                checks,
                summary="github_pat secret is not configured.",
                docs=_DOCS,
            )
        except (SecretValidationError, SecretError) as exc:
            # 2. Secret malformed (schema failed).
            checks.append(
                check_fail(
                    "GITHUB_SECRET_VALID",
                    f"github_pat secret is malformed: {exc}",
                    readiness_status=CollectorReadinessStatus.MISCONFIGURED,
                    docs=_DOCS,
                )
            )
            return CollectorSelfTestResult.from_checks(
                checks,
                summary="github_pat secret is malformed.",
                docs=_DOCS,
            )
        checks.append(
            check_pass(
                "GITHUB_SECRET_VALID",
                "github_pat secret resolves and is the expected kind.",
                docs=_DOCS,
            )
        )

        data = dict(secret.data)
        repos: list[str] = list(data["repos"])

        # 3. API reachable + PAT authenticates — GET /rate_limit.
        # No-retry client so a real 401/403 surfaces immediately.
        client = GithubClient(
            token=data["token"],
            api_base_url=api_base_url(data),
            retry_empty_404=False,
        )
        try:
            rate = client.get("/rate_limit")
        except GithubAPIError as exc:
            checks.append(
                check_fail(
                    "GITHUB_API_REACHABLE",
                    f"GitHub /rate_limit failed: status={exc.status} "
                    f"body={exc.body[:200] or '(empty)'}",
                    readiness_status=CollectorReadinessStatus.ERROR,
                    docs=_DOCS,
                )
            )
            return CollectorSelfTestResult.from_checks(
                checks,
                summary="GitHub API unreachable or PAT auth failed.",
                docs=_DOCS,
            )
        core = rate.get("rate") or rate.get("resources", {}).get("core", {})
        checks.append(
            check_pass(
                "GITHUB_API_REACHABLE",
                f"GitHub API reachable; PAT rate-limit "
                f"{core.get('used', '?')}/{core.get('limit', '?')} used.",
                context={"rate": core},
                docs=_DOCS,
            )
        )

        # 4. Per-repo access. Each failure is recorded but doesn't short-
        # circuit the rest — operator wants to see ALL the broken repos in
        # one run, not just the first.
        repo_access_ok = True
        for repo in repos:
            try:
                client.get(f"/repos/{repo}")
            except GithubAPIError as exc:
                repo_access_ok = False
                checks.append(
                    check_fail(
                        f"GITHUB_REPO_ACCESS:{repo}",
                        f"PAT cannot access {repo}: status={exc.status} "
                        f"body={exc.body[:200] or '(empty)'}",
                        readiness_status=CollectorReadinessStatus.ERROR,
                        docs=_DOCS,
                    )
                )
            else:
                checks.append(
                    check_pass(
                        f"GITHUB_REPO_ACCESS:{repo}",
                        f"PAT has access to {repo}.",
                        context={"repo": repo},
                        docs=_DOCS,
                    )
                )

        return CollectorSelfTestResult.from_checks(
            checks,
            summary=(
                f"GitHub Core collector is ready; {len(repos)} repo(s) accessible."
                if repo_access_ok
                else "GitHub Core collector PAT cannot access one or more configured repos."
            ),
            docs=_DOCS,
        )

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

        # --- platform singleton: one github.com node per run, the top of the
        # account → repo → workflow tree. Synthesized (no API enumerates "the
        # platform"); deterministic id so re-runs upsert in place and a
        # hand-written GRIFT node with the same host upserts cleanly onto it.
        platform_uuid = platform_id(_PLATFORM_HOST)
        nodes.append(
            node_envelope(
                entity_id=platform_uuid,
                entity_type="github_platform",
                name=_PLATFORM_HOST,
                dimensions=dict(_PLATFORM_DIMENSIONS),
                fields={
                    "host": _PLATFORM_HOST,
                    "html_url": f"https://{_PLATFORM_HOST}",
                    "configuration": {},
                    "tags": {},
                },
            )
        )

        # --- collection phase: per-repo walk ---
        for full_name in repos:
            try:
                self._collect_repo(client, full_name, run_limit, nodes, edges, platform_uuid)
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
                description="Cross-grid link edges (REFERENCES_RESOURCE, FEDERATES_VIA) resolved from the grid-link manifest.",
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
        platform_uuid: Any,
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
        # platform hosts this account — top-of-tree containment. Deterministic
        # edge id dedupes across repos that share an owner.
        edges.append(
            self._edge("HOSTS_ACCOUNT", platform_uuid, account_uuid, dict(_PLATFORM_DIMENSIONS))
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
            # Local-action surfacing per req-github-core-workflow-parse-3.
            for ref in parsed_config.get("local_action_refs") or []:
                self.record_warn(
                    _SITE_LOCAL_ACTION_DEFERRED,
                    "LOCAL_ACTION_DEFERRED",
                    f"{full_name} workflow {wf.get('path', '')}: local/composite "
                    f"action reference {ref.get('uses')!r} at {ref.get('path')} "
                    f"(job {ref.get('job_id')!r}); v0 does not parse action.yml bodies.",
                )

        # runs — incremental fetch per req-github-core-collector-3:
        #   - First population (no on-grid runs): latest `run_limit` runs.
        #   - Later populations: runs created since the latest on-grid
        #     `run_started_at` for this repo, using GitHub's `created` filter.
        run_payloads = self._fetch_run_window(client, full_name, run_limit)

        # Non-terminal refresh per req-github-core-collector-4: pull every
        # on-grid run for this repo whose status is not in
        # _TERMINAL_RUN_STATUSES and re-fetch it singly. Skips any run_id
        # already in this batch's run_payloads (the incremental fetch may
        # already have re-fetched it).
        refreshed = self._fetch_non_terminal_refresh(
            client, full_name, already_fetched_run_ids={r["id"] for r in run_payloads}
        )
        run_payloads.extend(refreshed)
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
            jobs = self._fetch_run_jobs(client, full_name, r["id"])
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
            run_jobs = self._fetch_run_jobs(client, full_name, r["id"])
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

    def _fetch_run_window(
        self, client: GithubClient, full_name: str, run_limit: int
    ) -> list[dict[str, Any]]:
        """Run-list fetch per req-github-core-collector-3.

        First population (no on-grid runs): the latest `run_limit` runs.
        Later populations: every run created since the latest on-grid
        `run_started_at` for this repo, scoped via GitHub's `?created=>=ISO`
        filter. The first-fetch cap is `run_limit`; later fetches are
        unbounded but typically small (only new runs since last collection).
        """
        from django.db.models import Max

        from plugins.github_core.models import GithubActionsRun

        max_ts = (
            GithubActionsRun.objects.filter(full_name=full_name)
            .aggregate(Max("run_started_at"))["run_started_at__max"]
        )
        if max_ts is None:
            # First population — cap at run_limit, one page is enough.
            return client.get_paginated(
                f"/repos/{full_name}/actions/runs",
                params={"per_page": str(min(run_limit, 100))},
                item_path="workflow_runs",
                max_pages=1,
            )[:run_limit]

        # Incremental — fetch everything strictly newer. GitHub's `created`
        # filter accepts ISO 8601 with comparison operators. We use `>` not
        # `>=` to avoid re-fetching the boundary run we already have.
        iso = max_ts.astimezone().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.record_info(
            _SITE_INCREMENTAL_WINDOW,
            "INCREMENTAL_WINDOW",
            f"{full_name}: incremental run fetch since {iso}.",
        )
        return client.get_paginated(
            f"/repos/{full_name}/actions/runs",
            params={"created": f">{iso}", "per_page": "100"},
            item_path="workflow_runs",
        )

    def _fetch_non_terminal_refresh(
        self,
        client: GithubClient,
        full_name: str,
        already_fetched_run_ids: set[int],
    ) -> list[dict[str, Any]]:
        """Re-fetch on-grid runs whose status is non-terminal per
        req-github-core-collector-4.

        Each run is fetched via the single-run endpoint
        `/repos/{owner}/{repo}/actions/runs/{run_id}`. A 404 on that endpoint
        (real, body-bearing — the empty-body retry in api_client already
        absorbed the intermittent ones) records a structured warn and the
        run is skipped from this refresh; mirrors the per-run /jobs degrade
        in `_fetch_run_jobs`.
        """
        from plugins.github_core.models import GithubActionsRun

        non_terminal_ids = list(
            GithubActionsRun.objects.filter(full_name=full_name)
            .exclude(status__in=list(_TERMINAL_RUN_STATUSES))
            .exclude(run_id__in=list(already_fetched_run_ids))
            .values_list("run_id", flat=True)
        )
        if not non_terminal_ids:
            return []
        self.record_info(
            _SITE_NON_TERMINAL_REFRESH,
            "NON_TERMINAL_REFRESH",
            f"{full_name}: refreshing {len(non_terminal_ids)} non-terminal run(s).",
        )
        refreshed: list[dict[str, Any]] = []
        for rid in non_terminal_ids:
            try:
                payload = client.get(f"/repos/{full_name}/actions/runs/{rid}")
            except GithubAPIError as exc:
                if exc.status == 404:
                    self.record_warn(
                        _SITE_RUN_NOT_FOUND,
                        "RUN_NOT_FOUND",
                        f"{full_name} run {rid}: single-run endpoint 404 "
                        f"({exc.body[:120] or '(empty)'}). "
                        f"Skipping refresh for this run.",
                    )
                    continue
                raise
            refreshed.append(payload)
        return refreshed

    def _fetch_run_jobs(
        self, client: GithubClient, full_name: str, run_id_int: int
    ) -> list[dict[str, Any]]:
        """Fetch the jobs list for a specific run.

        Per GitHub docs the endpoint documents only `200 - OK`; no 404
        condition is documented. The HTTP client retries empty-body 404s
        (undocumented intermittent quirk; see api_client module docstring).
        Real 404s — a JSON body with `{"message": "..."}` — still propagate
        and we graceful-degrade per-run to avoid aborting the whole collection
        on a single quirky run (`req-github-core-collector-5` discipline).
        """
        try:
            return client.get_paginated(
                f"/repos/{full_name}/actions/runs/{run_id_int}/jobs", item_path="jobs"
            )
        except GithubAPIError as exc:
            if exc.status == 404:
                self.record_warn(
                    _SITE_RUN_JOBS_MISSING,
                    "RUN_JOBS_MISSING",
                    f"{full_name} run {run_id_int} jobs endpoint returned 404 "
                    f"with body: {exc.body[:120] or '(empty)'}. "
                    f"Skipping job collection for this run.",
                )
                return []
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
