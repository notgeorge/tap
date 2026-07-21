"""Tests for the crypto Bill-of-Materials gate (req-fips-crypto-bom).

Two layers:
  * unit tests for the fingerprinter + classifier over synthetic inputs (run anywhere);
  * the GATE — a real scan of the installed environment (the `test_all` plugin union), asserting no
    unclassified or non-validated crypto provider leaks. Anti-fail-open: the gate also asserts the
    scan actually read binaries and saw the known providers, so an empty scan cannot pass silently.
"""

from __future__ import annotations

import pytest

from tap import crypto_bom
from tap.crypto_bom import Finding, core_report, fingerprint
from tap.crypto_providers import Boundary, Waiver


# ---------------------------------------------------------------------------- fingerprinter
def test_go_requires_both_needles_not_a_stray_crypto_tls() -> None:
    """The Go/Rust disambiguation: `crypto/tls` alone (as in the Rust `uv` binary) is NOT Go — Go
    needs the build-info magic too, or every Rust TLS binary would be misread as Go crypto."""
    assert fingerprint(b"...crypto/tls...") == set()
    assert fingerprint(b"...Go buildinf: ...crypto/tls...") == {"go-crypto"}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"blob ring_core_0_17 blob", {"rust-ring"}),
        (b"blob aws_lc_0_1 blob", {"rust-aws-lc-rs"}),
        (b"blob sodium_init blob", {"libsodium"}),
        (b"needs libcrypto.so.3 here", {"openssl-system"}),
        (b"needs libpq.so.5 here", {"openssl-system"}),
        (b"needs libcurl.so.4 here", {"openssl-system"}),
        (b"org/bouncycastle/crypto/", {"bouncycastle"}),
        (b"nothing cryptographic at all", set()),
    ],
)
def test_fingerprint_signatures(data: bytes, expected: set[str]) -> None:
    assert fingerprint(data) == expected


# ---------------------------------------------------------------------------- classifier / dispositions
def test_unclassified_nonopenssl_provider_is_a_failure(tmp_path) -> None:
    findings = crypto_bom._classify_artifact(tmp_path / "evil.so", {"libsodium"})
    assert len(findings) == 1
    assert findings[0].boundary is None and findings[0].is_failure


def test_dispositioned_providers_resolve(tmp_path) -> None:
    # uv → out-of-boundary; a gosu-named binary's Go crypto → unreached; system OpenSSL → validated.
    uv = crypto_bom._classify_artifact(tmp_path / "uv", {"rust-aws-lc-rs"})[0]
    gosu = crypto_bom._classify_artifact(tmp_path / "gosu", {"go-crypto"})[0]
    ossl = crypto_bom._classify_artifact(tmp_path / "libfoo.so", {"openssl-system"})[0]
    assert uv.boundary is Boundary.OUT_OF_BOUNDARY and not uv.is_failure
    assert gosu.boundary is Boundary.UNREACHED and not gosu.is_failure
    assert ossl.boundary is Boundary.VALIDATED and not ossl.is_failure


def test_known_nonfips_distribution_is_flagged() -> None:
    findings = crypto_bom._distribution_findings(["PyNaCl"])  # case/underscore-insensitive
    assert len(findings) == 1 and findings[0].is_failure


def test_jvm_arrival_is_a_tripwire(tmp_path) -> None:
    """Java is out of scope, but its ARRIVAL must fail the gate loudly (jars/classes are not ELF, so
    the fingerprinter is blind to JVM crypto — this is the only thing that catches it)."""
    (tmp_path / "libjvm.so").write_bytes(b"x")
    (tmp_path / "java").write_bytes(b"x")
    (tmp_path / "app.jar").write_bytes(b"x")
    (tmp_path / "Main.class").write_bytes(b"x")
    findings = crypto_bom._jvm_findings([tmp_path], dist_names=[])
    assert len(findings) == 4
    assert all(f.provider == "jvm-detected" and f.boundary is Boundary.MUST_FIX for f in findings)


def test_jvm_bridge_distribution_is_a_tripwire() -> None:
    findings = crypto_bom._jvm_findings([], dist_names=["JPype1"])
    assert len(findings) == 1 and findings[0].is_failure and findings[0].provider == "jvm-detected"


def test_no_jvm_no_tripwire(tmp_path) -> None:
    (tmp_path / "regular.so").write_bytes(b"x")
    assert crypto_bom._jvm_findings([tmp_path], dist_names=["django"]) == []


def test_bundled_libcrypto_file_outside_system_dir_is_flagged(tmp_path) -> None:
    site = tmp_path / "site-packages"
    site.mkdir()
    (site / "libcrypto-abcd1234.so.3").write_bytes(b"bundled")  # a wheel's hashed private libcrypto
    findings = crypto_bom._libcrypto_findings([tmp_path])
    assert len(findings) == 1
    assert findings[0].provider == "openssl-bundled-file" and findings[0].boundary is Boundary.MUST_FIX


# ---------------------------------------------------------------------------- the gate (real scan)
def test_crypto_bom_gate_no_leaks() -> None:
    """No unclassified or non-validated crypto provider anywhere in the installed environment.

    Under `test_all` the venv is the full plugin union, so this catches a plugin that leaks a
    non-FIPS provider — making core FIPS-capable is worthless if a plugin ships `pynacl` or a Go
    collector (req-fips-crypto-bom)."""
    report = core_report()

    # Anti-fail-open (doc L2/L12): prove the scan actually read binaries and saw the known providers,
    # so an empty scan (wrong root / unreadable files) fails loudly instead of a false all-clear.
    assert report.scanned_files > 20, "crypto-BOM scanned too few ELF artifacts — did it run in the image?"
    assert "openssl-system" in report.detected_providers, "expected to detect the system OpenSSL provider"

    assert report.failures == [], "unclassified / non-validated crypto providers:\n" + crypto_bom.format_report(report)


def test_finding_failure_semantics() -> None:
    assert Finding("a", "p", None, "d", None).is_failure  # unclassified
    assert Finding("a", "p", Boundary.MUST_FIX, "d", "r").is_failure
    assert not Finding("a", "p", Boundary.VALIDATED, "d", "r").is_failure
    assert not Finding("a", "p", Boundary.OUT_OF_BOUNDARY, "d", "r").is_failure
    assert not Finding("a", "p", Boundary.UNREACHED, "d", "r").is_failure
    assert not Finding("a", "p", None, "d", None, waived=True, waiver_reason="ok").is_failure  # waived


# ---------------------------------------------------------------------------- operator waivers (deployment)
def test_load_waivers_requires_a_nonempty_reason() -> None:
    with pytest.raises(crypto_bom.WaiverError, match="reason"):
        crypto_bom.load_waivers([{"plugin": "evil_plugin", "provider": "libsodium", "reason": "   "}])
    with pytest.raises(crypto_bom.WaiverError, match="reason"):
        crypto_bom.load_waivers([{"plugin": "evil_plugin"}])  # no reason at all
    [w] = crypto_bom.load_waivers(
        [{"plugin": "evil_plugin", "reason": "reviewed: only used for a non-security checksum"}]
    )
    assert w.artifact == "evil_plugin" and w.provider == "*" and w.reason.startswith("reviewed")


def test_load_waivers_rejects_non_dict() -> None:
    with pytest.raises(crypto_bom.WaiverError):
        crypto_bom.load_waivers(["evil_plugin"])


def test_apply_waivers_excuses_a_matching_failure_and_records_the_reason() -> None:
    report = crypto_bom.Report(findings=[Finding("/x/tap_plugin/evil/thing.so", "libsodium", None, "d", None)])
    assert report.failures  # unwaived → a failure
    waived = crypto_bom.apply_waivers(
        report, crypto_bom.load_waivers([{"plugin": "evil", "reason": "accepted by 3PAO"}])
    )
    assert waived.failures == []
    assert waived.findings[0].waived and waived.findings[0].waiver_reason == "accepted by 3PAO"


def test_waiver_provider_must_match() -> None:
    report = crypto_bom.Report(findings=[Finding("/x/evil/thing.so", "libsodium", None, "d", None)])
    # A waiver for a DIFFERENT provider does not excuse it.
    waived = crypto_bom.apply_waivers(report, [Waiver("*", "rust-ring", "unrelated")])
    assert waived.failures  # still failing


# ---------------------------------------------------------------------------- per-plugin scan + system gate
def test_scan_plugin_flags_a_bundled_nonfips_so(tmp_path) -> None:
    (tmp_path / "vendored.so").write_bytes(b"\x7fELF stuff sodium_init more")
    report = crypto_bom.scan_plugin(tmp_path)
    assert any(f.provider == "libsodium" and f.is_failure for f in report.findings)


def test_system_fips_gate_is_noop_when_fips_off(monkeypatch) -> None:
    monkeypatch.setenv("TAP_FIPS_MODE", "0")
    called = False

    def _boom():
        nonlocal called
        called = True
        raise AssertionError("core_report should not run when FIPS is off")

    monkeypatch.setattr(crypto_bom, "core_report", _boom)
    code, report = crypto_bom.system_fips_gate("core_dev")
    assert code == 0 and not called and report.findings == []


def test_system_fips_gate_fails_on_unwaived_leak(monkeypatch) -> None:
    monkeypatch.setenv("TAP_FIPS_MODE", "1")
    monkeypatch.setattr(
        crypto_bom,
        "core_report",
        lambda: crypto_bom.Report(findings=[Finding("/x/evil/z.so", "libsodium", None, "d", None)]),
    )
    monkeypatch.setattr(crypto_bom, "_profile_waivers", lambda profile_id: [])
    code, report = crypto_bom.system_fips_gate("core_dev")
    assert code == 1 and report.failures


def test_system_fips_gate_passes_with_operator_waiver(monkeypatch) -> None:
    monkeypatch.setenv("TAP_FIPS_MODE", "1")
    monkeypatch.setattr(
        crypto_bom,
        "core_report",
        lambda: crypto_bom.Report(findings=[Finding("/x/evil/z.so", "libsodium", None, "d", None)]),
    )
    monkeypatch.setattr(
        crypto_bom, "_profile_waivers", lambda profile_id: [Waiver("evil", "*", "reviewed non-security use")]
    )
    code, report = crypto_bom.system_fips_gate("core_dev")
    assert code == 0 and report.failures == [] and report.findings[0].waived
