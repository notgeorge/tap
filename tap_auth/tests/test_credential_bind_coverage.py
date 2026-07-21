"""Unit tests for the credential-bind provenance scanner (`req-tap-auth-credential-bind-provenance`).

Hermetic and Django-free: `scan_credential_binds` takes source roots, so these drive it
over synthetic source. Every class-level write to `WebAuthnCredential` /
`WebAuthnUserHandle` must carry a `# TAP-CRED-BIND: <provenance>` tag valid for that model;
the scan partitions sites into ok / untagged / invalid, and surfaces orphaned tags.
"""

from __future__ import annotations

from pathlib import Path

from tap_auth.credential_bind_coverage import scan_credential_binds


def _scan(tmp_path: Path, source: str) -> object:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    return scan_credential_binds([tmp_path])


# --------------------------------------------------------------------------- #
# Well-tagged binds pass
# --------------------------------------------------------------------------- #


def test_credential_create_with_pop_ceremony_is_ok(tmp_path: Path) -> None:
    src = "def f():\n    WebAuthnCredential.objects.create(\n        # TAP-CRED-BIND: pop-ceremony\n        user=u,\n    )\n"
    result = _scan(tmp_path, src)
    assert [(s.model, s.op, s.provenance) for s in result.ok] == [("WebAuthnCredential", "create", "pop-ceremony")]  # type: ignore[attr-defined]
    assert result.untagged == [] and result.invalid_provenance == []  # type: ignore[attr-defined]


def test_credential_dev_profile_gate_is_ok(tmp_path: Path) -> None:
    src = "def f():\n    WebAuthnCredential.objects.update_or_create(\n        # TAP-CRED-BIND: dev-profile-gate\n        credential_id=c,\n    )\n"
    assert len(_scan(tmp_path, src).ok) == 1  # type: ignore[attr-defined]


def test_credential_assertion_counter_update_is_ok(tmp_path: Path) -> None:
    """A queryset `.update()` for the sign_count is a credential write, tagged as a non-bind counter update."""
    src = "def f():\n    WebAuthnCredential.objects.filter(pk=p).update(\n        # TAP-CRED-BIND: assertion-counter\n        sign_count=n,\n    )\n"
    result = _scan(tmp_path, src)
    assert [(s.op, s.provenance) for s in result.ok] == [("update", "assertion-counter")]  # type: ignore[attr-defined]


def test_handle_pre_registration_is_ok(tmp_path: Path) -> None:
    src = "def f():\n    WebAuthnUserHandle.objects.get_or_create(\n        # TAP-CRED-BIND: pre-registration-handle\n        user=u,\n    )\n"
    assert len(_scan(tmp_path, src).ok) == 1  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Violations
# --------------------------------------------------------------------------- #


def test_untagged_credential_bind_is_flagged(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    WebAuthnCredential.objects.create(user=u)\n")
    assert [(s.model, s.op) for s in result.untagged] == [("WebAuthnCredential", "create")]  # type: ignore[attr-defined]


def test_construct_then_save_untagged_is_flagged(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    WebAuthnCredential(user=u).save()\n")
    assert [(s.model, s.op) for s in result.untagged] == [("WebAuthnCredential", "save")]  # type: ignore[attr-defined]


def test_credential_under_handle_provenance_is_invalid(tmp_path: Path) -> None:
    """The load-bearing per-model rule: a public-key credential may NOT be bound under a handle provenance."""
    src = "def f():\n    WebAuthnCredential.objects.create(\n        # TAP-CRED-BIND: pre-registration-handle\n        user=u,\n    )\n"
    result = _scan(tmp_path, src)
    assert [(s.model, s.provenance) for s in result.invalid_provenance] == [("WebAuthnCredential", "pre-registration-handle")]  # type: ignore[attr-defined]
    assert result.ok == []  # type: ignore[attr-defined]


def test_handle_under_credential_provenance_is_invalid(tmp_path: Path) -> None:
    src = "def f():\n    WebAuthnUserHandle.objects.create(\n        # TAP-CRED-BIND: pop-ceremony\n        user=u,\n    )\n"
    assert len(_scan(tmp_path, src).invalid_provenance) == 1  # type: ignore[attr-defined]


def test_unknown_provenance_is_invalid(tmp_path: Path) -> None:
    src = "def f():\n    WebAuthnCredential.objects.create(\n        # TAP-CRED-BIND: made-up\n        user=u,\n    )\n"
    assert [s.provenance for s in _scan(tmp_path, src).invalid_provenance] == ["made-up"]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Tag precision — the regressions found while building this
# --------------------------------------------------------------------------- #


def test_prose_mention_of_the_token_is_not_a_tag(tmp_path: Path) -> None:
    """A comment naming the marker without the `: <provenance>` form (docs) is not a tag."""
    src = "def f():\n    x = 1  # the TAP-CRED-BIND convention names why a bind is safe\n"
    result = _scan(tmp_path, src)
    assert result.orphan_tags == [] and result.untagged == []  # type: ignore[attr-defined]


def test_tag_in_a_string_literal_is_not_a_tag(tmp_path: Path) -> None:
    result = _scan(tmp_path, 'HINT = "annotate a bind with # TAP-CRED-BIND: pop-ceremony"\n')
    assert result.orphan_tags == []  # type: ignore[attr-defined]


def test_wellformed_tag_on_no_bind_is_an_orphan(tmp_path: Path) -> None:
    result = _scan(tmp_path, "x = 1  # TAP-CRED-BIND: pop-ceremony\n")
    assert [c.lineno for c in result.orphan_tags] == [1]  # type: ignore[attr-defined]


def test_write_to_a_non_bind_model_is_ignored(tmp_path: Path) -> None:
    result = _scan(tmp_path, "def f():\n    SomeOtherModel.objects.create(x=1)\n")
    assert result.ok == [] and result.untagged == [] and result.orphan_tags == []  # type: ignore[attr-defined]
