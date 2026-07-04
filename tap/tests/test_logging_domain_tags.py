"""Tests for the shared domain-tag vocabulary (tap/logging_domain_tags.py).

`req-tap-logging-domain-tags`: the single specialty-routing vocabulary both
`FLAW` (`flaw_tags`) and `CONCERN` (`tags`) inherit, so a tag means one thing
across every reserved signal.
"""

from __future__ import annotations

import pytest

from tap.logging_domain_tags import DOMAIN_TAGS, domain_tag_problems


def test_vocabulary_is_registered_and_described() -> None:
    assert set(DOMAIN_TAGS) == {"security", "operational", "data", "config", "integration"}
    # Every tag carries a human-readable description (routing reads these).
    assert all(isinstance(desc, str) and desc.strip() for desc in DOMAIN_TAGS.values())


def test_valid_tags_have_no_problems() -> None:
    assert domain_tag_problems(["security"]) == []
    assert domain_tag_problems(["security", "config"]) == []


def test_empty_is_a_problem() -> None:
    problems = domain_tag_problems([])
    assert problems and "at least one" in problems[0]


def test_unknown_tag_is_a_problem() -> None:
    problems = domain_tag_problems(["security", "not-a-real-tag"])
    assert problems and "unknown domain tag" in problems[0]
    assert "not-a-real-tag" in problems[0]


@pytest.mark.parametrize("tag", sorted(DOMAIN_TAGS))
def test_each_registered_tag_passes(tag: str) -> None:
    assert domain_tag_problems([tag]) == []
