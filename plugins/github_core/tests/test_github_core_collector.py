"""Unit tests for the github_core collector building blocks.

Spec: plugins/github_core/specs/spec-github-core-v0.md
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from plugins.github_core.collectors.github_collector.identity import (
    account_id,
    edge_id,
    job_id,
    repository_id,
    run_id,
    runner_id,
    workflow_id,
)
from plugins.github_core.collectors.github_collector.manifest import (
    load_collection_manifest,
    load_link_manifest,
)
from plugins.github_core.collectors.github_collector.parser import parse_workflow_yaml
from plugins.github_core.collectors.github_collector.secret import (
    GITHUB_PAT_SCHEMA,
    api_base_url,
    initial_run_limit,
)


class TestManifests:
    def test_collection_manifest_loads(self) -> None:
        manifest = load_collection_manifest()
        assert manifest["manifest_version"] == "0"
        assert {s["name"] for s in manifest["sources"]} >= {
            "account",
            "repository",
            "workflows",
            "workflow_yaml",
            "runs",
            "jobs",
            "runners",
        }

    def test_link_manifest_loads(self) -> None:
        manifest = load_link_manifest()
        assert manifest["manifest_version"] == "0"
        edge_types = {r["edge_type"] for r in manifest["rules"]}
        assert edge_types == {"REFERENCES_RESOURCE"}

    def test_link_manifest_oneof_source_enforced(self) -> None:
        """Schema must reject rules with both source_field_path and source_constant."""
        import jsonschema

        from plugins.github_core.collectors.github_collector.manifest import (
            LINK_MANIFEST_SCHEMA_PATH,
        )

        schema = __import__("json").loads(LINK_MANIFEST_SCHEMA_PATH.read_text())
        bad = {
            "manifest_version": "0",
            "rules": [
                {
                    "name": "bad",
                    "source_entity_type": "github_repository",
                    "source_field_path": "x.y",
                    "source_constant": "z",
                    "target_entity_type": "aws_iam_oidc_provider",
                    "target_field": "url",
                    "edge_type": "REFERENCES_RESOURCE",
                    "match_mode": "exact",
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)

    def test_link_manifest_includes_oidc_rule(self) -> None:
        manifest = load_link_manifest()
        oidc = [
            r for r in manifest["rules"]
            if r.get("target_entity_type") == "aws_iam_oidc_provider"
        ]
        assert len(oidc) == 1
        rule = oidc[0]
        assert rule["source_constant"] == "token.actions.githubusercontent.com"
        assert rule["near_match_pattern"] == r"(?i)githubusercontent\.com"


class TestPATSchema:
    def test_minimal_valid_pat(self) -> None:
        jsonschema.validate(
            {"token": "ghp_x", "repos": ["notgeorge/samsite"]},
            GITHUB_PAT_SCHEMA,
        )

    def test_pat_with_optional_fields(self) -> None:
        jsonschema.validate(
            {
                "token": "ghp_x",
                "api_base_url": "https://github.enterprise.example/api/v3",
                "repos": ["notgeorge/samsite", "notgeorge/another"],
                "initial_run_limit": 25,
            },
            GITHUB_PAT_SCHEMA,
        )

    def test_pat_missing_token_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"repos": ["notgeorge/samsite"]}, GITHUB_PAT_SCHEMA)

    def test_pat_empty_repos_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"token": "ghp_x", "repos": []}, GITHUB_PAT_SCHEMA)

    def test_pat_malformed_repo_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"token": "ghp_x", "repos": ["just-a-name"]}, GITHUB_PAT_SCHEMA
            )

    def test_pat_extra_fields_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"token": "ghp_x", "repos": ["a/b"], "collect_variables": True},
                GITHUB_PAT_SCHEMA,
            )

    def test_helpers_apply_defaults(self) -> None:
        assert api_base_url({}) == "https://api.github.com"
        assert initial_run_limit({}) == 10
        assert api_base_url({"api_base_url": "https://custom/"}) == "https://custom/"
        assert initial_run_limit({"initial_run_limit": 50}) == 50


class TestIdentity:
    def test_uuids_are_deterministic(self) -> None:
        assert account_id("notgeorge") == account_id("notgeorge")
        assert repository_id("notgeorge/samsite") == repository_id("notgeorge/samsite")
        assert workflow_id("notgeorge/samsite", 12345) == workflow_id("notgeorge/samsite", 12345)
        assert run_id("notgeorge/samsite", 999) == run_id("notgeorge/samsite", 999)
        assert job_id("notgeorge/samsite", 8888) == job_id("notgeorge/samsite", 8888)
        assert runner_id("notgeorge/samsite", 7) == runner_id("notgeorge/samsite", 7)

    def test_different_inputs_yield_different_uuids(self) -> None:
        assert account_id("notgeorge") != account_id("someone-else")
        assert workflow_id("a/b", 1) != workflow_id("a/b", 2)
        assert workflow_id("a/b", 1) != workflow_id("c/d", 1)

    def test_edge_id_includes_endpoints(self) -> None:
        a = account_id("notgeorge")
        b = repository_id("notgeorge/samsite")
        c = repository_id("notgeorge/other")
        assert edge_id("OWNS_REPO", a, b) != edge_id("OWNS_REPO", a, c)
        assert edge_id("OWNS_REPO", a, b) != edge_id("DEFINES_WORKFLOW", a, b)


class TestParser:
    def test_minimal_workflow(self) -> None:
        yaml_text = """\
name: Deploy
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        config = parse_workflow_yaml(yaml_text)
        assert config["triggers"] == ["push"]
        assert config["jobs"][0]["id"] == "build"
        assert config["jobs"][0]["runs_on"] == "ubuntu-latest"
        assert config["raw_yaml"] == yaml_text

    def test_triggers_normalized(self) -> None:
        yaml_text = "on:\n  push:\n  pull_request:\njobs: {}\n"
        config = parse_workflow_yaml(yaml_text)
        assert config["triggers"] == ["pull_request", "push"]

    def test_refs_categorized(self) -> None:
        yaml_text = """\
on: push
env:
  AWS_REGION: us-east-1
  DOMAIN_NAME: samaydlette.com
  CF_DIST: E2QWERTYUIOPAS
  IGNORED: just-some-string
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo done
"""
        config = parse_workflow_yaml(yaml_text)
        refs = config["refs"]
        assert "us-east-1" in refs["aws_regions"]
        assert "samaydlette.com" in refs["domain_names"]
        assert "E2QWERTYUIOPAS" in refs["cloudfront_distribution_ids"]
        assert "just-some-string" not in refs["domain_names"]

    def test_empty_yaml_safe(self) -> None:
        config = parse_workflow_yaml("")
        assert config["triggers"] == []
        assert config["jobs"] == []
        assert config["refs"] == {"domain_names": [], "aws_regions": [], "cloudfront_distribution_ids": []}
        assert config["local_action_refs"] == []

    def test_local_action_refs_detected(self) -> None:
        """Local composite-action `uses: ./...` references are flagged for the
        collector to warn on (req-github-core-workflow-parse-3)."""
        yaml_text = """\
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-foo
      - uses: ./local-helper
      - run: echo "hello"
  release:
    uses: ./.github/workflows/release.yml
"""
        config = parse_workflow_yaml(yaml_text)
        refs = config["local_action_refs"]
        # Two local-action refs in the `build` job; the `release` job's
        # `./.github/workflows/release.yml` is a reusable workflow call,
        # NOT a local action — must NOT be flagged.
        uses_strings = sorted(r["uses"] for r in refs)
        assert uses_strings == sorted(["./.github/actions/setup-foo", "./local-helper"])
        job_ids = {r["job_id"] for r in refs}
        assert job_ids == {"build"}

    def test_reusable_workflow_call_not_flagged_as_local_action(self) -> None:
        """`uses: ./.github/workflows/x.yml` is a reusable workflow call, not
        a local action — explicitly NOT flagged so an operator isn't told to
        investigate something that's a different category entirely."""
        yaml_text = """\
on: push
jobs:
  call:
    uses: ./.github/workflows/build.yaml
"""
        config = parse_workflow_yaml(yaml_text)
        assert config["local_action_refs"] == []


class TestCollectorRegistration:
    def test_collector_registered_in_tap_cares(self) -> None:
        from tap_cares.registry import get_collector

        cls = get_collector("github_core")
        assert cls.__name__ == "GithubCollector"
