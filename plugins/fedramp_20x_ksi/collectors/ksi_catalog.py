"""KSICollector — runtime collector for the FedRAMP 20x KSI catalog.

Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-collector.md

Pipeline:
    1. fetch upstream JSON over HTTPS                 (req-...-collector-fetch)
    2. parse + validate against pinned schema         (req-...-collector-pin)
    3. run paranoid safety checks (all block-class)   (req-...-collector-safety)
    4. read prior catalog state from the local grid   (req-...-collector-diff)
    5. compute the new / modified / removed diff
    6. check mass-deletion threshold                  (req-...-collector-mass-deletion)
    7. assemble one GRIFT batch carrying only changes (req-...-collector-grift)
    8. submit via self.submit_grift

Each pipeline stage emits structured events into `self.results` via
`self.record_info` / `self.record_error`. The task body persists the full
accumulator to `CollectionJob.results` at terminal state. Block-class flags
raise `KSICollectorError` after recording the structured detail and setting
`self.error_summary`; the task body then writes the FAILED terminal patch.

The collector is HTTPS-only in v0; provenance posture is documented in the
spec's Runtime Safety Model section. A future `GitCollectorBase` will recover
the cryptographic provenance chain; the safety checks below carry the load
in the meantime.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5, uuid7

import jsonschema

from tap_cares.collectors import CollectorBase, CollectorConfig

# ---------------------------------------------------------------------------
# Pinned assets and constants
# ---------------------------------------------------------------------------

_COLLECTORS_DIR = Path(__file__).resolve().parent
_PINNED_SCHEMA_PATH = _COLLECTORS_DIR / "pinned" / "source_schema.json"
_PINNED_NAMESPACE_PATH = _COLLECTORS_DIR / "pinned" / "uuid_namespace.txt"
_PINNED_COLLECTION_SCHEMA_PATH = _COLLECTORS_DIR / "pinned" / "collection-v0.schema.json"
_DENYLIST_PATH = _COLLECTORS_DIR / "safety" / "denylist.json"

UPSTREAM_URL = "https://raw.githubusercontent.com/FedRAMP/rules/main/fedramp-consolidated-rules.json"
UPSTREAM_TIMEOUT_SECONDS = 30

MAX_SOURCE_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_THEMES = 20
MAX_INDICATORS_PER_THEME = 100
MAX_STRING_LEN = 100 * 1024  # 100 KiB
MAX_ARRAY_LEN = 200
MASS_DELETION_THRESHOLD = 0.10

# v0 paranoid posture: outlier means more than this multiple of the mean
# length for the same path across the catalog. Promoted from warn to block.
OUTLIER_LENGTH_MULTIPLIER = 5
OUTLIER_LENGTH_MIN_ABS = 4096  # only check fields that have at least one value over this

_BIDI_OVERRIDE_RE = re.compile(r"[‪-‮⁦-⁩]")
_BAD_CONTROL_RE = re.compile(r"[\x00-\x08\x0B-\x1F\x7F]")

COLLECTION_FORMAT = "tap.fedramp_20x_ksi.collection-v0"

# Site UUIDv7 per record_* callsite. Hardcoded; the repo-wide uniqueness
# test (tap_cares.tests.test_results_site_uniqueness) asserts no two callsites
# in the codebase share a UUID.
_SITE_RUN_STARTED = "019e1e15-a73d-7074-80e2-7128dc3c3004"
_SITE_UPSTREAM_FETCHED = "019e1e15-a7f6-731e-8579-97fc5afcbd61"
_SITE_DIFF_COMPUTED = "019e1e15-a8a1-7546-9cee-3efe48b7d071"
_SITE_DIFF_EMPTY = "019e1e15-a941-7360-8df4-5257ee28b826"
_SITE_GRIFT_SUBMITTED = "019e1e15-a9f7-72c4-8336-42ce158b8dd1"
_SITE_RUN_COMPLETED = "019e1e15-ab0e-7227-a35b-9313997dbecd"

_SITE_SCHEMA_DRIFT = "019e1e15-abc9-774e-b6b9-e12d255b86d8"
_SITE_UNKNOWN_FIELD = "019e1e15-ac73-767b-9fe2-4ea3bc1e53d5"
_SITE_STRUCTURAL_CAP = "019e1e15-ad2c-7135-b1a6-69993a6ae7ff"
_SITE_CHARACTER_CLASS = "019e1e15-adff-75ec-bb03-1af94fd63be4"
_SITE_DENYLIST_PHRASE = "019e1e15-aeb2-7540-ae30-fc7707f9e09e"
_SITE_OUTLIER_STRING_LENGTH = "019e1e15-af6d-765b-93ea-b348e6f82683"
_SITE_MASS_DELETION = "019e1e15-b010-76d5-9ed7-e2a1c6e56636"
_SITE_UPSTREAM_OVERSIZED = "019e1e15-b100-7461-b3a2-7dfd78b121c8"
_SITE_UPSTREAM_BAD_CONTENT_TYPE = "019e1e15-b223-73f1-a349-b44ddaac1f3e"
_SITE_UPSTREAM_FETCH_FAILED = "019e1e15-b32d-73d3-be2b-92cea597e807"


class KSICollectorError(Exception):
    """A block-class safety flag fired during collection.

    Raised from `_abort()` after structured error detail is recorded into
    `self.results["error"]` and `self.error_summary` is set. The `run_collector`
    task body catches the exception and writes the FAILED terminal patch to
    `CollectionJob` (status, finished_at, error_summary, results, grift_batches).
    """


# ---------------------------------------------------------------------------
# Cached pinned assets — loaded once per process
# ---------------------------------------------------------------------------


def _load_pinned_schema() -> dict[str, Any]:
    return json.loads(_PINNED_SCHEMA_PATH.read_text())


def _load_pinned_namespace() -> UUID:
    return UUID(_PINNED_NAMESPACE_PATH.read_text().strip())


def _load_collection_schema() -> dict[str, Any]:
    return json.loads(_PINNED_COLLECTION_SCHEMA_PATH.read_text())


def _load_denylist() -> dict[str, Any]:
    return json.loads(_DENYLIST_PATH.read_text())


# ---------------------------------------------------------------------------
# Walk helpers
# ---------------------------------------------------------------------------


def _walk_strings(obj: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    """Yield (JSONPath, string-value) for every string in the document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else k
            yield from _walk_strings(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def _walk_arrays(obj: Any, path: str = "$") -> Iterable[tuple[str, list]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else k
            yield from _walk_arrays(v, child)
    elif isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from _walk_arrays(v, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class KSICollector(CollectorBase):
    """KSI catalog collector. See module docstring for pipeline overview."""

    # Override points for tests. Subclasses (or test fixtures) can replace
    # _fetch_upstream_bytes to inject canned content without touching the
    # network.

    # -- Public entrypoint ---------------------------------------------------

    def run(self) -> None:
        self.record_info(_SITE_RUN_STARTED, "RUN_STARTED", "KSI catalog collection started.")
        body, content_sha256, byte_size = self._fetch_upstream_bytes()
        source = self._parse_and_validate(body, content_sha256, byte_size)
        self._check_safety(source)
        prior = self._read_grid_state()
        diff = self._compute_diff(source, prior)
        self._check_mass_deletion(diff, prior)

        if self._diff_is_empty(diff):
            self.record_info(
                _SITE_DIFF_EMPTY,
                "DIFF_EMPTY",
                "Upstream matches grid; nothing to import.",
                context={
                    "catalog_size": len(prior["indicators"]),
                },
            )
        else:
            document = self._assemble_batch(
                source=source,
                diff=diff,
                content_sha256=content_sha256,
                byte_size=byte_size,
                prior_indicator_count=len(prior["indicators"]),
            )
            result = self.submit_grift(document)
            self.record_info(
                _SITE_GRIFT_SUBMITTED,
                "GRIFT_SUBMITTED",
                f"GRIFT batch submitted ({result.counts.batches_imported} imported, "
                f"{result.counts.batches_skipped} skipped).",
                context={
                    "imported": [str(b.batch_entity_id) for b in result.imported_batches],
                    "skipped": [str(b.batch_entity_id) for b in result.skipped_batches],
                },
            )

        self.record_info(_SITE_RUN_COMPLETED, "RUN_COMPLETED", "KSI catalog collection complete.")
        # On exception: KSICollectorError propagates with self.error_summary already
        # set in _abort() and self.results["error"] populated; the run_collector
        # task body catches and persists the FAILED terminal patch.

    # -- Pipeline stages -----------------------------------------------------

    def _fetch_upstream_bytes(self) -> tuple[bytes, str, int]:
        """Fetch the upstream JSON over HTTPS. Returns (body, sha256_hex, byte_size).

        Test overrides should replace this method.
        """
        try:
            req = urllib.request.Request(UPSTREAM_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT_SECONDS) as resp:
                ctype = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                if ctype not in ("application/json", "text/plain", "text/json"):
                    self._abort(
                        _SITE_UPSTREAM_BAD_CONTENT_TYPE,
                        "UPSTREAM_BAD_CONTENT_TYPE",
                        f"Upstream returned Content-Type {ctype!r}; expected application/json.",
                        context={"content_type": ctype, "url": UPSTREAM_URL},
                    )
                # Read up to cap + 1 so we can detect oversize without exploding memory.
                body = resp.read(MAX_SOURCE_BYTES + 1)
        except urllib.error.URLError as exc:
            self._abort(
                _SITE_UPSTREAM_FETCH_FAILED,
                "UPSTREAM_FETCH_FAILED",
                f"Upstream fetch failed: {type(exc).__name__}: {exc}",
                context={"url": UPSTREAM_URL, "exception_type": type(exc).__name__},
            )

        if len(body) > MAX_SOURCE_BYTES:
            self._abort(
                _SITE_UPSTREAM_OVERSIZED,
                "UPSTREAM_OVERSIZED",
                f"Upstream body {len(body)} bytes exceeds cap {MAX_SOURCE_BYTES}.",
                context={"byte_size": len(body), "cap": MAX_SOURCE_BYTES},
            )

        sha256 = hashlib.sha256(body).hexdigest()
        self.record_info(
            _SITE_UPSTREAM_FETCHED,
            "UPSTREAM_FETCHED",
            f"Fetched {len(body)} bytes from upstream.",
            context={
                "url": UPSTREAM_URL,
                "byte_size": len(body),
                "content_sha256": sha256,
            },
        )
        return body, sha256, len(body)

    def _parse_and_validate(self, body: bytes, content_sha256: str, byte_size: int) -> dict[str, Any]:
        try:
            source = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._abort(
                _SITE_SCHEMA_DRIFT,
                "SCHEMA_DRIFT",
                f"Upstream is not valid JSON: {exc}",
                context={"exception_type": type(exc).__name__},
            )

        schema = _load_pinned_schema()
        # Accumulate every validation error rather than bailing on the first. The
        # upstream schema is actively evolving, so a single run frequently surfaces
        # multiple drift points; recording each gives the operator a complete
        # picture in one cycle instead of forcing iterative whack-a-mole.
        validator = jsonschema.Draft202012Validator(schema)
        schema_errors = list(validator.iter_errors(source))
        for exc in schema_errors:
            path = self._jsonpath(exc.absolute_path)
            self.record_error(
                _SITE_SCHEMA_DRIFT,
                "SCHEMA_DRIFT",
                f"Upstream failed pinned-schema validation at {path}: {exc.message}",
                context={
                    "path": path,
                    "validator": exc.validator,
                },
            )

        # The pinned schema's `additionalProperties: false` (where set) catches
        # most unknown-field cases. Belt-and-suspenders for the top-level keys.
        allowed_top = set(schema.get("properties", {}).keys())
        extras = set(source.keys()) - allowed_top
        if extras:
            self.record_error(
                _SITE_UNKNOWN_FIELD,
                "UNKNOWN_FIELD",
                f"Upstream contains unknown top-level keys: {sorted(extras)}",
                context={"unknown_keys": sorted(extras)},
            )

        # Raise once after the full sweep so the task body's terminal patch carries
        # every recorded error. The count-based error_summary is derived from
        # self.results["error"] at terminal write time.
        if self.results["error"]:
            raise KSICollectorError(
                f"Upstream failed pinned-schema validation with {len(self.results['error'])} error(s)."
            )

        return source

    def _check_safety(self, source: dict[str, Any]) -> None:
        self._check_structural_caps(source)
        self._check_character_classes(source)
        self._check_denylist(source)
        self._check_outliers(source)

    def _check_structural_caps(self, source: dict[str, Any]) -> None:
        ksi = source.get("KSI", {})
        if len(ksi) > MAX_THEMES:
            self._abort(
                _SITE_STRUCTURAL_CAP,
                "STRUCTURAL_CAP",
                f"Catalog has {len(ksi)} themes; cap is {MAX_THEMES}.",
                context={"observed": len(ksi), "cap": MAX_THEMES, "kind": "themes"},
            )
        for theme_key, theme in ksi.items():
            indicators = theme.get("indicators", {})
            if len(indicators) > MAX_INDICATORS_PER_THEME:
                self._abort(
                    _SITE_STRUCTURAL_CAP,
                    "STRUCTURAL_CAP",
                    f"Theme {theme_key} has {len(indicators)} indicators; cap is {MAX_INDICATORS_PER_THEME}.",
                    context={
                        "observed": len(indicators),
                        "cap": MAX_INDICATORS_PER_THEME,
                        "kind": "indicators_per_theme",
                        "theme_key": theme_key,
                    },
                )
        for path, arr in _walk_arrays(source):
            if len(arr) > MAX_ARRAY_LEN:
                self._abort(
                    _SITE_STRUCTURAL_CAP,
                    "STRUCTURAL_CAP",
                    f"{path}: array length {len(arr)} exceeds cap {MAX_ARRAY_LEN}.",
                    context={"observed": len(arr), "cap": MAX_ARRAY_LEN, "path": path},
                )
        for path, text in _walk_strings(source):
            if len(text) > MAX_STRING_LEN:
                self._abort(
                    _SITE_STRUCTURAL_CAP,
                    "STRUCTURAL_CAP",
                    f"{path}: string length {len(text)} exceeds cap {MAX_STRING_LEN}.",
                    context={"observed": len(text), "cap": MAX_STRING_LEN, "path": path},
                )

    def _check_character_classes(self, source: dict[str, Any]) -> None:
        for path, text in _walk_strings(source):
            if _BIDI_OVERRIDE_RE.search(text):
                self._abort(
                    _SITE_CHARACTER_CLASS,
                    "CHARACTER_CLASS",
                    f"{path}: contains Unicode BiDi override character.",
                    context={"path": path, "violation": "bidi_override"},
                )
            if _BAD_CONTROL_RE.search(text):
                self._abort(
                    _SITE_CHARACTER_CLASS,
                    "CHARACTER_CLASS",
                    f"{path}: contains control character outside \\t and \\n.",
                    context={"path": path, "violation": "bad_control"},
                )

    def _check_denylist(self, source: dict[str, Any]) -> None:
        denylist = _load_denylist()
        ksi = source.get("KSI", {})
        for rule_name, rule in denylist.items():
            if not isinstance(rule, dict):
                continue
            if rule_name == "low_quality_commit_message":
                continue  # applies to commit messages, not source content
            patterns = rule.get("patterns", [])
            if not patterns:
                continue
            for path, text in _walk_strings(ksi, path="$.KSI"):
                if rule_name == "url_scheme_warn" and path.endswith(".reference_url"):
                    continue
                for pat in patterns:
                    try:
                        if re.search(pat, text, re.IGNORECASE):
                            snippet = text[:80].replace("\n", "\\n")
                            self._abort(
                                _SITE_DENYLIST_PHRASE,
                                "DENYLIST_PHRASE",
                                f"{path}: matches denylist rule {rule_name!r}.",
                                context={
                                    "path": path,
                                    "rule": rule_name,
                                    "pattern": pat,
                                    "snippet": snippet,
                                },
                            )
                    except re.error:
                        continue

    def _check_outliers(self, source: dict[str, Any]) -> None:
        """Block when a single string field is dramatically longer than its peers.

        Computes, per path-prefix (everything except the trailing array index),
        the mean string length across siblings. Any string > OUTLIER_LENGTH_MULTIPLIER
        times the mean AND >= OUTLIER_LENGTH_MIN_ABS triggers a block.
        """
        groups: dict[str, list[tuple[str, str]]] = {}
        for path, text in _walk_strings(source):
            # group by stripping a trailing [N] (or the trailing dict-key when
            # array semantics aren't applicable).
            group_key = re.sub(r"\[\d+\]", "[*]", path)
            groups.setdefault(group_key, []).append((path, text))

        for group_key, items in groups.items():
            if len(items) < 2:
                continue
            lengths = [len(t) for _p, t in items]
            mean = sum(lengths) / len(lengths)
            if mean <= 0:
                continue
            for path, text in items:
                if (
                    len(text) >= OUTLIER_LENGTH_MIN_ABS
                    and len(text) > mean * OUTLIER_LENGTH_MULTIPLIER
                ):
                    self._abort(
                        _SITE_OUTLIER_STRING_LENGTH,
                        "OUTLIER_STRING_LENGTH",
                        f"{path}: length {len(text)} exceeds {OUTLIER_LENGTH_MULTIPLIER}× group mean "
                        f"{mean:.0f} (group {group_key}).",
                        context={
                            "path": path,
                            "observed": len(text),
                            "group_mean": int(mean),
                            "group": group_key,
                        },
                    )

    # -- Grid read + diff ----------------------------------------------------

    def _read_grid_state(self) -> dict[str, dict[str, dict[str, Any]]]:
        from plugins.fedramp_20x_ksi.models import KsiIndicator, KsiTheme

        themes: dict[str, dict[str, Any]] = {}
        for t in KsiTheme.objects.all():
            themes[t.code] = self._theme_state_from_orm(t)

        indicators: dict[str, dict[str, Any]] = {}
        for i in KsiIndicator.objects.all():
            indicators[i.code] = self._indicator_state_from_orm(i)

        return {"themes": themes, "indicators": indicators}

    def _theme_state_from_orm(self, theme: Any) -> dict[str, Any]:
        return {
            "code": theme.code,
            "name": theme.name,
            "short_name": theme.short_name,
            "web_name": theme.web_name,
            "description": theme.description,
        }

    def _indicator_state_from_orm(self, ind: Any) -> dict[str, Any]:
        return {
            "code": ind.code,
            "name": ind.name,
            "description": ind.description,
            "classes": list(ind.classes or []),
            "class_variants": ind.class_variants,
            "controls": list(ind.controls or []),
            "updated_log": list(ind.updated_log or []),
            "terms": list(ind.terms or []),
            "reference": ind.reference,
            "reference_url": ind.reference_url,
            "status": ind.status,
        }

    def _theme_state_from_source(self, theme: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": theme.get("id", ""),
            "name": theme.get("name", ""),
            "short_name": theme.get("short_name", ""),
            "web_name": theme.get("web_name", ""),
            "description": "",
        }

    def _indicator_state_from_source(self, code: str, indicator: dict[str, Any]) -> dict[str, Any]:
        varies = indicator.get("varies_by_class")
        class_variants = varies if isinstance(varies, dict) else None
        statement = indicator.get("statement", "") or ""
        classes = self._indicator_classes(indicator)
        return {
            "code": code,
            "name": indicator.get("name", ""),
            "description": statement if class_variants is None else "",
            "classes": classes,
            "class_variants": class_variants,
            "controls": indicator.get("controls", []) or [],
            "updated_log": indicator.get("updated", []) or [],
            "terms": indicator.get("terms", []) or [],
            "reference": indicator.get("reference", "") or "",
            "reference_url": indicator.get("reference_url", "") or "",
            "status": "published",
        }

    def _indicator_classes(self, indicator: dict[str, Any]) -> list[str]:
        varies = indicator.get("varies_by_class")
        if isinstance(varies, dict):
            return sorted(k for k in varies if k in ("a", "b", "c", "d"))
        return ["b", "c", "d"]

    def _compute_diff(
        self,
        source: dict[str, Any],
        prior: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        new_themes: dict[str, dict[str, Any]] = {}
        new_indicators: dict[str, dict[str, Any]] = {}
        theme_lookup: dict[str, str] = {}
        for theme_key, theme in source.get("KSI", {}).items():
            theme_code = theme.get("id") or theme_key
            new_themes[theme_code] = self._theme_state_from_source(theme)
            for ind_code, indicator in theme.get("indicators", {}).items():
                new_indicators[ind_code] = self._indicator_state_from_source(ind_code, indicator)
                theme_lookup[ind_code] = theme_code

        pt = prior["themes"]
        pi = prior["indicators"]
        diff = {
            "themes_added": {k: v for k, v in new_themes.items() if k not in pt},
            "themes_modified": {k: v for k, v in new_themes.items() if k in pt and pt[k] != v},
            "themes_removed": {k: pt[k] for k in pt if k not in new_themes},
            "indicators_added": {k: v for k, v in new_indicators.items() if k not in pi},
            "indicators_modified": {k: v for k, v in new_indicators.items() if k in pi and pi[k] != v},
            "indicators_removed": {k: pi[k] for k in pi if k not in new_indicators},
            "new_indicators_count": len(new_indicators),
            "new_themes_count": len(new_themes),
            "theme_lookup": theme_lookup,
        }
        self.record_info(
            _SITE_DIFF_COMPUTED,
            "DIFF_COMPUTED",
            (
                f"Diff: themes +{len(diff['themes_added'])}/~{len(diff['themes_modified'])}/-{len(diff['themes_removed'])}; "
                f"indicators +{len(diff['indicators_added'])}/~{len(diff['indicators_modified'])}/-{len(diff['indicators_removed'])}."
            ),
            context={
                "themes_new": len(diff["themes_added"]),
                "themes_modified": len(diff["themes_modified"]),
                "themes_deprecated": len(diff["themes_removed"]),
                "indicators_new": len(diff["indicators_added"]),
                "indicators_modified": len(diff["indicators_modified"]),
                "indicators_deprecated": len(diff["indicators_removed"]),
            },
        )
        return diff

    def _diff_is_empty(self, diff: dict[str, Any]) -> bool:
        return not any(
            (
                diff["themes_added"],
                diff["themes_modified"],
                diff["themes_removed"],
                diff["indicators_added"],
                diff["indicators_modified"],
                diff["indicators_removed"],
            )
        )

    def _check_mass_deletion(
        self,
        diff: dict[str, Any],
        prior: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        live = len(prior["indicators"])
        if live == 0:
            return  # fresh install — every indicator is `new`; ratio undefined.
        deprecated = len(diff["indicators_removed"])
        ratio = deprecated / live
        if ratio > MASS_DELETION_THRESHOLD:
            self._abort(
                _SITE_MASS_DELETION,
                "MASS_DELETION",
                f"Deprecation ratio {ratio:.1%} exceeds {MASS_DELETION_THRESHOLD:.0%} threshold "
                f"({deprecated} of {live} indicators).",
                context={
                    "ratio": ratio,
                    "deprecated": deprecated,
                    "live": live,
                    "threshold": MASS_DELETION_THRESHOLD,
                },
            )

    # -- Batch assembly ------------------------------------------------------

    def _ns_uuid(self, kind: str, key: str) -> str:
        namespace = _load_pinned_namespace()
        return str(uuid5(namespace, f"{kind}:{key}"))

    def _assemble_batch(
        self,
        *,
        source: dict[str, Any],
        diff: dict[str, Any],
        content_sha256: str,
        byte_size: int,
        prior_indicator_count: int,
    ) -> dict[str, Any]:
        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        deprecated = len(diff["indicators_removed"])
        new_count = diff["new_indicators_count"]
        ratio = deprecated / prior_indicator_count if prior_indicator_count > 0 else 0.0

        description_data = {
            "schema_version": "v0",
            "source": {
                "url": UPSTREAM_URL,
                "fetched_at": now_iso,
                "content_sha256": content_sha256,
                "byte_size": byte_size,
                "rules_version": source.get("version", "") or source.get("FRMR", {}).get("version", "") or "",
            },
            "changes": {
                "themes_new": len(diff["themes_added"]),
                "themes_modified": len(diff["themes_modified"]),
                "themes_deprecated": len(diff["themes_removed"]),
                "indicators_new": len(diff["indicators_added"]),
                "indicators_modified": len(diff["indicators_modified"]),
                "indicators_deprecated": deprecated,
                "catalog_size_before": prior_indicator_count,
                "catalog_size_after": new_count,
                "deletion_ratio": ratio,
            },
        }
        jsonschema.validate(instance=description_data, schema=_load_collection_schema())

        nodes: list[dict[str, Any]] = []
        for code, state in sorted(diff["themes_added"].items()):
            nodes.append(self._theme_node(code, state))
        for code, state in sorted(diff["themes_modified"].items()):
            nodes.append(self._theme_node(code, state))
        for code, state in sorted(diff["indicators_added"].items()):
            nodes.append(self._indicator_node(code, state))
        for code, state in sorted(diff["indicators_modified"].items()):
            nodes.append(self._indicator_node(code, state))
        for code, state in sorted(diff["indicators_removed"].items()):
            deprecated_state = dict(state)
            deprecated_state["status"] = "deprecated"
            nodes.append(self._indicator_node(code, deprecated_state))

        edges: list[dict[str, Any]] = []
        for ind_code in sorted(diff["indicators_added"]):
            theme_code = diff["theme_lookup"].get(ind_code)
            if not theme_code:
                continue
            edges.append(self._contains_indicator_edge(theme_code, ind_code))

        batch_entity_id = str(uuid7())
        batch = {
            "batch_entity": {
                "entity_id": batch_entity_id,
                "entity_type": "batch",
                "name": f"FedRAMP 20x KSI collection {now_iso}",
                "dimensions": {},
            },
            "batch_node": {
                "source": "plugins.fedramp_20x_ksi.collectors.ksi_catalog",
                "name": f"FedRAMP 20x KSI collection {now_iso}",
                "description": "Runtime catalog collection via tap_cares.",
                "description_json": {"format": COLLECTION_FORMAT, "data": description_data},
            },
            "nodes": nodes,
            "edges": edges,
        }
        return {"metadata": {"grift_version": "0"}, "_reserved": {}, "batches": [batch]}

    def _theme_node(self, code: str, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity": {
                "entity_id": self._ns_uuid("ksi_theme", code),
                "entity_type": "ksi_theme",
                "name": state.get("name") or code,
                "dimensions": {"compliance": "fedramp-20x"},
            },
            "node": state,
        }

    def _indicator_node(self, code: str, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity": {
                "entity_id": self._ns_uuid("ksi_indicator", code),
                "entity_type": "ksi_indicator",
                "name": state.get("name") or code,
                "dimensions": {"compliance": "fedramp-20x"},
            },
            "node": state,
        }

    def _contains_indicator_edge(self, theme_code: str, ind_code: str) -> dict[str, Any]:
        return {
            "entity": {
                "entity_id": self._ns_uuid("edge:CONTAINS_INDICATOR", f"{theme_code}->{ind_code}"),
                "entity_type": "edge",
                "dimensions": {"compliance": "fedramp-20x"},
            },
            "edge": {
                "from_entity_id": self._ns_uuid("ksi_theme", theme_code),
                "to_entity_id": self._ns_uuid("ksi_indicator", ind_code),
                "edge_type": "CONTAINS_INDICATOR",
                "properties": {},
            },
        }

    # -- Helpers -------------------------------------------------------------

    def _abort(self, site: str, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        """Record a block-class flag and raise KSICollectorError to halt the run.

        Follows the framework failure protocol (req-tap-cares-collector-failure-mode):
        record the structured error and raise. The task body's terminal patch
        derives `error_summary` from the count of recorded errors, so the
        collector does not set it directly.
        """
        self.record_error(site, code, message, context=context)
        raise KSICollectorError(message)

    @staticmethod
    def _jsonpath(absolute_path: Any) -> str:
        """Convert a jsonschema ValidationError's absolute_path to an RFC 9535 JSONPath."""
        parts = ["$"]
        for elem in absolute_path:
            if isinstance(elem, int):
                parts[-1] = parts[-1] + f"[{elem}]"
            else:
                parts.append(f".{elem}")
        return "".join(parts)
