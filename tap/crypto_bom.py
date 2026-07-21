"""Crypto Bill-of-Materials scanner (req-cicd-crypto-bom) — the build-time FIPS-provider gate.

Enumerates every cryptographic *provider* actually present in an environment (core's venv + image
binaries, or a single plugin's closure) and classifies each against the curated registry in
`tap.crypto_providers`. A provider with no disposition, or a `MUST_FIX` disposition, fails the gate.

Why a scanner and not just the boot self-check: `tap.fips` proves the *OpenSSL-backed Python* layer
is enforced, but it is blind to a Go binary, a Rust crate on `ring`/`aws-lc-rs`, or a `libsodium`
wheel — those carry their own crypto, ignore `OPENSSL_CONF`, and would silently run non-FIPS crypto
with no error (doc-fips-assessment-record.md L17). This detects them by fingerprinting the real ELF
artifacts, so a dependency or binary that leaks a non-validated provider is caught at build time.

Positioned for plugins: `scan()` takes explicit roots, so per-plugin conformance can scan a single
plugin's isolated closure — plugins run in the same image/process, so a plugin leak defeats a
FIPS-capable core. The core gate (`core_report()`) scans the installed union, which under the
`test_all` profile already contains every plugin's dependency closure.

Anti-fail-open (doc L2/L12): the scan is only trustworthy if it actually read binaries. `core_report()`
records what it detected, and the gate test asserts the known-present validated providers were seen —
so an empty scan (wrong root, unreadable files) fails loudly instead of reporting a false all-clear.
"""

from __future__ import annotations

import fnmatch
import importlib.metadata as importlib_metadata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from tap.crypto_providers import (
    DISPOSITIONS,
    JVM_ARTIFACT_SUFFIXES,
    JVM_EXECUTABLES,
    JVM_RUNTIME_FILES,
    KNOWN_JVM_DISTRIBUTIONS,
    KNOWN_NONFIPS_DISTRIBUTIONS,
    SIGNATURES,
    Boundary,
    Disposition,
)

ELF_MAGIC = b"\x7fELF"
#: Skip reading any single file larger than this (crypto libs are a few MB; a huge blob is not one).
_MAX_READ_BYTES = 96 * 1024 * 1024

# Core-environment defaults (inside the web container). `/bin`→`/usr/bin` (L4), so `/usr/bin` covers both.
_VENV_ROOT = Path("/app/.venv")
_BINARY_ROOTS = (Path("/usr/bin"),)
#: Where a bundled libcrypto/libssl FILE (the psycopg[binary] class) would hide.
_LIBCRYPTO_ROOTS = (Path("/usr/lib"), Path("/app/.venv"))
#: Real (symlink-resolved) directories where the one legitimate system OpenSSL lives (`/lib`→`/usr/lib`).
_SYSTEM_LIB_DIRS = frozenset({"/usr/lib"})


@dataclass(frozen=True)
class Finding:
    """One (artifact, provider) pair and its resolved disposition. `boundary is None` = unclassified."""

    artifact: str
    provider: str
    boundary: Boundary | None
    detail: str
    rid: str | None

    @property
    def is_failure(self) -> bool:
        # Unclassified (no disposition) or an in-boundary non-validated provider fails the gate.
        return self.boundary is None or self.boundary is Boundary.MUST_FIX


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    scanned_files: int = 0
    unreadable: list[str] = field(default_factory=list)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.is_failure]

    @property
    def detected_providers(self) -> set[str]:
        return {f.provider for f in self.findings}


def fingerprint(data: bytes) -> set[str]:
    """Return the set of provider names whose signature (ALL needles) is present in `data`."""
    providers: set[str] = set()
    for sig in SIGNATURES:
        if all(needle in data for needle in sig.needles):
            providers.add(sig.provider)
    return providers


def _read(path: Path) -> bytes | None:
    """Read a file's bytes, or None if it cannot be read (recorded by the caller, never silently
    dropped — an error-suppressing discovery step is the L2 fail-open trap)."""
    try:
        if path.stat().st_size > _MAX_READ_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _iter_native_files(roots: Iterable[Path]) -> Iterator[Path]:
    """Yield each distinct ELF file under the given roots as its resolved (real) path.

    Dedups by real path, so the Wolfi `/bin`→`/usr/bin` and `/lib`→`/usr/lib` symlinks (L4) do not
    double-count a file, and the canonical path is what dispositions match against."""
    seen: set[Path] = set()
    for root in roots:
        if root.is_file():
            candidates: Iterable[Path] = (root,)
        elif root.is_dir():
            candidates = (p for p in root.rglob("*") if p.is_file())
        else:
            continue
        for path in candidates:
            try:
                real = path.resolve()
                if real in seen:
                    continue
                with real.open("rb") as fh:
                    if fh.read(4) == ELF_MAGIC:
                        seen.add(real)
                        yield real
            except OSError:
                continue


def _disposition_for(artifact: str, provider: str) -> Disposition | None:
    """Resolve the disposition for a finding: an fnmatch on the artifact path/name, provider exact
    or '*'. First match wins (registry order)."""
    for d in DISPOSITIONS:
        if (d.provider in (provider, "*")) and fnmatch.fnmatch(artifact, d.artifact):
            return d
    return None


def _classify_artifact(path: Path, providers: set[str]) -> list[Finding]:
    """Turn one artifact's detected providers into findings.

    - `openssl-system` → a VALIDATED finding (routes through the #4282 provider);
    - a non-OpenSSL provider (go/ring/aws-lc/libsodium/…) → a finding that must be dispositioned;
      an undispositioned one is unclassified (boundary None) and fails the gate.
    """
    artifact = str(path)
    findings: list[Finding] = []
    for provider in sorted(providers):
        if provider == "openssl-system":
            findings.append(
                Finding(artifact, provider, Boundary.VALIDATED, "links system OpenSSL", "req-cicd-crypto-bom")
            )
            continue
        disp = _disposition_for(artifact, provider)
        if disp is None:
            findings.append(Finding(artifact, provider, None, "no disposition — an unclassified crypto provider", None))
        else:
            findings.append(Finding(artifact, provider, disp.boundary, disp.rationale, disp.rid))
    return findings


def _libcrypto_findings(roots: Iterable[Path]) -> list[Finding]:
    """A libcrypto/libssl FILE whose real path is outside the system lib dir is a bundled OpenSSL
    (e.g. a wheel shipping its own `libcrypto-<hash>.so.3`) — the psycopg[binary] class, separate-file
    form. Dedups by real path so the `/lib`→`/usr/lib` symlink (L4) is not mistaken for a second copy."""
    findings: list[Finding] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not (path.name.startswith(("libcrypto", "libssl")) and (".so" in path.name)):
                continue
            try:
                real = path.resolve()
            except OSError:
                continue
            if real in seen or not real.is_file():
                continue
            seen.add(real)
            if str(real.parent) not in _SYSTEM_LIB_DIRS:
                findings.append(
                    Finding(
                        str(real),
                        "openssl-bundled-file",
                        Boundary.MUST_FIX,
                        "a bundled libcrypto/libssl outside the system dir — build the dependency against "
                        "the system OpenSSL instead (L17)",
                        "req-cicd-crypto-bom",
                    )
                )
    return findings


def _distribution_findings(dist_names: Iterable[str]) -> list[Finding]:
    """Name-based findings for Python distributions whose crypto byte-fingerprinting cannot reach
    (pure-Python, or an indirect link) — the belt to the fingerprinter's braces."""
    findings: list[Finding] = []
    for raw in dist_names:
        name = raw.lower().replace("_", "-")
        if name in KNOWN_NONFIPS_DISTRIBUTIONS:
            disp = _disposition_for(name, "*")
            if disp is None:
                findings.append(
                    Finding(
                        f"dist:{name}",
                        "python-nonfips-crypto",
                        None,
                        "known non-FIPS crypto distribution, no disposition",
                        None,
                    )
                )
            else:
                findings.append(
                    Finding(f"dist:{name}", "python-nonfips-crypto", disp.boundary, disp.rationale, disp.rid)
                )
    return findings


def _jvm_findings(roots: Iterable[Path], dist_names: Iterable[str]) -> list[Finding]:
    """Fail-closed tripwire: a JVM/Java runtime, executable, artifact, or bridge distribution has
    arrived. Java crypto uses JCA providers (BouncyCastle → BC-FIPS), not OpenSSL, and is invisible to
    the ELF fingerprinter (jars/classes are not ELF), so its arrival must fail the gate loudly rather
    than ship a silent non-FIPS JVM (req-cicd-crypto-bom residual (a))."""

    def _tripwire(artifact: str, what: str) -> Finding:
        return Finding(
            artifact,
            "jvm-detected",
            Boundary.MUST_FIX,
            f"a JVM/Java {what} arrived — the crypto-BOM does not yet reason about JVM crypto (JCA "
            "providers / BouncyCastle vs BC-FIPS). Now is the time to build the Java crypto layer, or "
            "remove it.",
            "req-cicd-crypto-bom",
        )

    findings: list[Finding] = []
    seen: set[str] = set()
    for root in roots:
        candidates: Iterable[Path] = (root,) if root.is_file() else (root.rglob("*") if root.is_dir() else ())
        for path in candidates:
            name = path.name
            what = None
            if name in JVM_RUNTIME_FILES:
                what = "runtime (libjvm.so)"
            elif name in JVM_EXECUTABLES:
                what = f"executable ({name})"
            elif name.endswith(JVM_ARTIFACT_SUFFIXES):
                what = f"artifact ({name})"
            if what is not None and str(path) not in seen:
                seen.add(str(path))
                findings.append(_tripwire(str(path), what))
    for raw in dist_names:
        dist = raw.lower().replace("_", "-")
        if dist in KNOWN_JVM_DISTRIBUTIONS:
            findings.append(_tripwire(f"dist:{dist}", f"bridge distribution ({dist})"))
    return findings


def scan(
    native_roots: Iterable[Path],
    dist_names: Iterable[str] = (),
    libcrypto_roots: Iterable[Path] = (),
    jvm_roots: Iterable[Path] = (),
) -> Report:
    """Scan the given roots and distributions, returning a Report. This is the reusable core — the
    same call scans core's environment or a single plugin's closure, only the roots differ."""
    dist_names = list(dist_names)
    report = Report()
    for path in _iter_native_files(native_roots):
        report.scanned_files += 1
        data = _read(path)
        if data is None:
            report.unreadable.append(str(path))
            continue
        providers = fingerprint(data)
        if providers:
            report.findings.extend(_classify_artifact(path, providers))
    report.findings.extend(_libcrypto_findings(libcrypto_roots))
    report.findings.extend(_distribution_findings(dist_names))
    report.findings.extend(_jvm_findings(jvm_roots, dist_names))
    return report


def core_report() -> Report:
    """Scan the core web-container environment: the venv's native extensions, the image binaries TAP
    ships/execs, and the libcrypto search paths. Under `test_all` the venv is the full plugin union."""
    dist_names = [d.metadata["Name"] for d in importlib_metadata.distributions() if d.metadata["Name"]]
    return scan(
        native_roots=(_VENV_ROOT, *_BINARY_ROOTS),
        dist_names=dist_names,
        libcrypto_roots=_LIBCRYPTO_ROOTS,
        jvm_roots=(_VENV_ROOT, *_BINARY_ROOTS, *_LIBCRYPTO_ROOTS),
    )


def format_report(report: Report) -> str:
    """Human/AI-legible one-line-per-finding rendering, worst-first."""
    order = {None: 0, Boundary.MUST_FIX: 1, Boundary.UNREACHED: 2, Boundary.OUT_OF_BOUNDARY: 3, Boundary.VALIDATED: 4}
    lines = [f"crypto-BOM: {report.scanned_files} ELF artifacts scanned, {len(report.findings)} finding(s)"]
    for f in sorted(report.findings, key=lambda f: order.get(f.boundary, 0)):
        label = f.boundary.value if f.boundary else "UNCLASSIFIED"
        lines.append(f"  [{label}] {f.provider} @ {f.artifact} — {f.detail}")
    if report.unreadable:
        lines.append(f"  ({len(report.unreadable)} unreadable file(s) skipped)")
    return "\n".join(lines)
