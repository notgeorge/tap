"""Unit tests for the workflow least-privilege scanner (req-cicd-runner-least-privilege).

Synthetic workflow fixtures exercise each predicate both ways. The live repo's
workflows are asserted clean by the harness itself (`test_guards.py` runs every
registered guard's `check()`), so these tests own the scanner logic, not the tree.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tap.guards.workflow_least_privilege import scan_workflow

_SHA = "0" * 40


def _scan(raw: str, name: str = "wf.yml") -> list[str]:
    return scan_workflow(Path(name), raw, yaml.safe_load(raw))


def _clean_workflow() -> str:
    return f"""
name: t
on: push
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{_SHA} # v7
"""


def test_clean_workflow_passes():
    assert _scan(_clean_workflow()) == []


def test_missing_toplevel_permissions_flagged():
    raw = f"""
name: t
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{_SHA} # v7
"""
    violations = _scan(raw)
    assert len(violations) == 1 and "no top-level `permissions:`" in violations[0]


def test_toplevel_write_flagged():
    raw = f"""
name: t
on: push
permissions:
  contents: write
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{_SHA} # v7
"""
    violations = _scan(raw)
    # top-level write + checkout-in-(now write-scoped)-job without persist-credentials
    assert any("top-level `permissions:` grants a write scope" in v for v in violations)


def test_tag_pinned_external_flagged():
    raw = """
name: t
on: push
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: some-org/some-action@v3
"""
    violations = _scan(raw)
    assert len(violations) == 1 and "not pinned to a 40-hex commit SHA" in violations[0]


def test_sha_without_version_comment_flagged():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: some-org/some-action@{_SHA}
"""
    violations = _scan(raw)
    assert len(violations) == 1 and "has no `# v<version>` comment" in violations[0]


def test_local_and_same_org_refs_exempt():
    raw = """
name: t
on: push
permissions:
  contents: read
jobs:
  local:
    uses: ./.github/workflows/reusable.yml
  org:
    uses: unified-systems-com/tap/.github/workflows/plugin-ci.yml@v1
"""
    assert _scan(raw) == []


def test_unannotated_third_party_in_write_job_flagged():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: some-org/pusher@{_SHA} # v1
"""
    violations = _scan(raw)
    assert len(violations) == 1 and "shares a job whose token carries a write scope" in violations[0]


def test_annotated_third_party_in_write_job_passes():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      # guard-allow: req-cicd-runner-least-privilege — this step IS the write.
      - uses: some-org/pusher@{_SHA} # v1
"""
    assert _scan(raw) == []


def test_third_party_in_readonly_job_needs_no_annotation():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: some-org/scanner@{_SHA} # v1
"""
    assert _scan(raw) == []


def test_checkout_persisting_credentials_in_write_job_flagged():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@{_SHA} # v7
"""
    violations = _scan(raw)
    assert len(violations) == 1 and "persist-credentials: false" in violations[0]


def test_checkout_nonpersisting_in_write_job_passes():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@{_SHA} # v7
        with:
          persist-credentials: false
"""
    assert _scan(raw) == []


def test_first_party_write_step_needs_no_annotation():
    raw = f"""
name: t
on: push
permissions:
  contents: read
jobs:
  attest:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - uses: actions/attest-build-provenance@{_SHA} # v4
"""
    assert _scan(raw) == []


def test_writeall_string_form_is_write():
    raw = f"""
name: t
on: push
permissions: read-all
jobs:
  danger:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - uses: some-org/tool@{_SHA} # v1
"""
    violations = _scan(raw)
    assert len(violations) == 1 and "write scope" in violations[0]
