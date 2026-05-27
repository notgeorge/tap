"""Deterministic UUIDv5 entity IDs for github_core nodes.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-models-4 Deterministic Identity). The natural-key table in
the spec is the source of truth for each entity type's identity inputs.
"""

from __future__ import annotations

from uuid import NAMESPACE_DNS, UUID, uuid5

# A stable, github_core-specific namespace derived from the canonical DNS
# namespace. Using a fixed UUID here keeps entity IDs reproducible across
# environments without depending on a runtime random seed.
GITHUB_CORE_NAMESPACE: UUID = uuid5(NAMESPACE_DNS, "github_core.tap")


def _id(entity_type: str, natural_key: str) -> UUID:
    return uuid5(GITHUB_CORE_NAMESPACE, f"{entity_type}:{natural_key}")


def account_id(login: str) -> UUID:
    return _id("github_account", login)


def repository_id(full_name: str) -> UUID:
    return _id("github_repository", full_name)


def workflow_id(full_name: str, workflow_id_int: int | str) -> UUID:
    return _id("github_workflow", f"{full_name}#{workflow_id_int}")


def run_id(full_name: str, run_id_int: int | str) -> UUID:
    # v0 natural key is owner/repo + run_id (run_attempt deferred — see
    # req-github-core-backlog-run-attempts).
    return _id("github_actions_run", f"{full_name}#{run_id_int}")


def job_id(full_name: str, job_id_int: int | str) -> UUID:
    return _id("github_actions_job", f"{full_name}#{job_id_int}")


def runner_id(full_name: str, runner_id_int: int | str) -> UUID:
    return _id("github_runner", f"{full_name}#{runner_id_int}")


def edge_id(edge_type: str, source: UUID, target: UUID) -> UUID:
    """Deterministic UUIDv5 for an edge by (type, source, target)."""
    return uuid5(GITHUB_CORE_NAMESPACE, f"edge:{edge_type}:{source}:{target}")
