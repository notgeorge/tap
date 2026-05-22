"""The samsite compliance collector.

A ``CollectorBase`` subclass that fetches samsite's signed ``/.well-known/``
compliance artifacts over HTTPS. Unlike the boto3 collector it needs no cloud
credentials — it reads public URLs.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md.

Build state: ``run()`` fetches every manifest artifact (document + Sigstore
bundle) and records the result. Signature verification and decomposition into
the ``fedramp_20x_ksi`` compliance-artifact models are subsequent additive
phases of the same ``run()``.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from tap_cares.collectors.base import CollectorBase

from .manifest import ArtifactManifestError, load_manifest

_SITE_RUN_STARTED = "be33"
_SITE_MANIFEST_LOADED = "3a92"
_SITE_RUN_FINISHED = "c94a"
_SITE_ARTIFACT_FETCHED = "c7ac"
_SITE_ARTIFACT_FETCH_FAILED = "147c"
_SITE_BUNDLE_FETCH_FAILED = "f159"
_SITE_MANIFEST_INVALID = "8c42"

_FETCH_TIMEOUT_SECONDS = 30
_USER_AGENT = "tap-samsite-compliance-collector"


class SamsiteComplianceCollectorError(Exception):
    """Unrecoverable samsite compliance collector failure."""


def _fetch(url: str) -> bytes:
    """HTTP GET — return the response body, or raise.

    HTTPS-only: a non-HTTPS URL is refused before the request is made (the
    artifacts are public TLS-served documents; there is no reason to fetch
    one over plaintext).
    """
    if not url.startswith("https://"):
        raise ValueError(f"Refusing to fetch non-HTTPS URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310 — HTTPS-guarded above
        return response.read()


class SamsiteComplianceCollector(CollectorBase):
    """Fetches samsite's signed ``/.well-known/`` compliance artifacts."""

    def _abort(self, site: str, code: str, message: str) -> None:
        """Record a structured error and raise to halt the run."""
        self.record_error(site, code, message)
        raise SamsiteComplianceCollectorError(message)

    def run(self) -> None:
        self.record_info(_SITE_RUN_STARTED, "RUN_STARTED", "Samsite compliance collection started.")

        try:
            manifest = load_manifest()
        except ArtifactManifestError as exc:
            self._abort(_SITE_MANIFEST_INVALID, "MANIFEST_INVALID", str(exc))

        base_url = manifest["site_base_url"]
        artifacts = manifest["artifacts"]
        self.record_info(
            _SITE_MANIFEST_LOADED,
            "MANIFEST_LOADED",
            f"Artifact manifest loaded — {len(artifacts)} artifact(s) from {base_url}.",
            message_data={"site_base_url": base_url, "artifact_count": len(artifacts)},
        )

        # Fetched artifacts, content in hand — the input to the verification
        # and decomposition phases (which extend this run()).
        fetched: list[dict[str, Any]] = []
        for artifact in artifacts:
            name = artifact["name"]
            doc_url = base_url + artifact["path"]
            try:
                body = _fetch(doc_url)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.record_warn(
                    _SITE_ARTIFACT_FETCH_FAILED,
                    "ARTIFACT_FETCH_FAILED",
                    f"Could not fetch {name} from {doc_url}: {exc}",
                    message_data={"artifact": name, "url": doc_url},
                )
                continue

            bundle_bytes: bytes | None = None
            bundle_path = artifact.get("bundle_path")
            if bundle_path:
                try:
                    bundle_bytes = _fetch(base_url + bundle_path)
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    self.record_warn(
                        _SITE_BUNDLE_FETCH_FAILED,
                        "BUNDLE_FETCH_FAILED",
                        f"Fetched {name} but its signature bundle is unavailable: {exc}",
                        message_data={"artifact": name},
                    )

            fetched.append({"artifact": artifact, "body": body, "bundle": bundle_bytes})
            self.record_info(
                _SITE_ARTIFACT_FETCHED,
                "ARTIFACT_FETCHED",
                f"Fetched {name} ({len(body)} bytes)"
                + ("" if bundle_bytes is None else f" + signature bundle ({len(bundle_bytes)} bytes)"),
                message_data={
                    "artifact": name,
                    "size_bytes": len(body),
                    "bundle_available": bundle_bytes is not None,
                },
            )

        self.summary = f"Fetched {len(fetched)}/{len(artifacts)} compliance artifacts."
        self.record_info(_SITE_RUN_FINISHED, "RUN_FINISHED", self.summary)
