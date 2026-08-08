"""Tests for the canonical scoped-registry token grammar (tap/registry.py).

`validate_scoped_token` is the single home the secret registry, collector
registry, and pre-boot secret resolver all defer to, so the grammar cannot
drift across read paths. These pin the flat, opaque-label contract — notably
that `/` is rejected (a scope is a namespace key, not a path).
"""

from __future__ import annotations

import pytest

from tap.registry import SCOPED_TOKEN_PATTERN, validate_scoped_token


class _DummyError(Exception):
    pass


@pytest.mark.parametrize(
    "value",
    [
        "auth",
        "github_core",
        "aws_core",
        "tap_plugins.source",  # the realigned install-system scope (dot, flat)
        "example-google",
        "a",
        "A0._-",
    ],
)
def test_accepts_flat_tokens(value: str) -> None:
    validate_scoped_token(value, error_cls=_DummyError, label="thing")  # does not raise


@pytest.mark.parametrize(
    "value",
    [
        "tap_plugins/source",  # the outlier that started this — no slash
        "a/b",
        "",  # empty
        "_leading",  # must start alphanumeric
        ".leading",
        "-leading",
        "has space",
        "emoji😀",
    ],
)
def test_rejects_malformed_tokens(value: str) -> None:
    with pytest.raises(_DummyError, match="Invalid thing token"):
        validate_scoped_token(value, error_cls=_DummyError, label="thing")


def test_non_string_rejected() -> None:
    with pytest.raises(_DummyError):
        validate_scoped_token(123, error_cls=_DummyError, label="thing")  # type: ignore[arg-type]


def test_message_carries_label_and_pattern() -> None:
    with pytest.raises(_DummyError) as exc:
        validate_scoped_token("bad/tok", error_cls=_DummyError, label="secret scope")
    msg = str(exc.value)
    assert "Invalid secret scope token 'bad/tok'" in msg
    assert SCOPED_TOKEN_PATTERN.pattern in msg


def test_pattern_forbids_slash() -> None:
    assert SCOPED_TOKEN_PATTERN.fullmatch("a.b") is not None
    assert SCOPED_TOKEN_PATTERN.fullmatch("a/b") is None
