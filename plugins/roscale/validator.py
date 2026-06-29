"""Best-effort OSCAL validation.

Two layers, reported separately:

1. Schema validation against the vendored official OSCAL 1.1.2 JSON Schemas.
2. TAP-authored semantic checks for display-critical structure (SSP and POA&M).

Schema errors and semantic warnings are surfaced as distinct lists so the
panel can render them differently. Only the absence of a recognized OSCAL
root document is treated as a hard validation failure — everything else is
best-effort and does not block rendering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from jsonschema import Draft7Validator, validators

from .constants import schema_path_for
from .parser import ParseResult


# OSCAL 1.1.2 schemas declare $schema = http://json-schema.org/draft-07/schema#.
# Using a Draft 2020-12 validator breaks internal $id anchor resolution.
#
# OSCAL also uses ECMA-262 regex patterns (e.g. \p{L}\p{N}) for some fields.
# Python's stdlib `re` does not support \p{...} Unicode property escapes and
# raises re.PatternError. Rather than pull in the third-party `regex` library
# (a new dep) or crash, the validator skips the `pattern` keyword entirely.
# This is surfaced in ValidationResult.unsupported_keywords so consumers and
# the panel can show the limitation explicitly. Semantic checks compensate for
# the most display-critical structure that `pattern` would have caught.
def _skip_pattern(_validator, _patrn, _instance, _schema):
    return
    yield  # noqa: B901 — marker to ensure this is treated as a generator


_SchemaValidator = validators.extend(Draft7Validator, validators={"pattern": _skip_pattern})
UNSUPPORTED_KEYWORDS: tuple[str, ...] = ("pattern",)


@dataclass
class SchemaError:
    message: str
    path: str
    schema_path: str


@dataclass
class SemanticWarning:
    check: str
    message: str
    path: str | None = None


@dataclass
class ValidationResult:
    root_recognized: bool
    schema_ok: bool
    schema_errors: list[SchemaError] = field(default_factory=list)
    semantic_warnings: list[SemanticWarning] = field(default_factory=list)
    schema_skipped_reason: str | None = None
    unsupported_keywords: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.root_recognized and self.schema_ok and not self.semantic_warnings


@cache
def _load_validator(schema_file: str):
    with open(schema_file, "rb") as fh:
        schema = json.load(fh)
    return _SchemaValidator(schema)


def _path_str(deque) -> str:
    parts = []
    for p in deque:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(f".{p}" if parts else str(p))
    return "".join(parts) if parts else "(root)"


def _schema_validate(parsed: ParseResult) -> tuple[bool, list[SchemaError], str | None]:
    if parsed.root_key is None or parsed.document is None:
        return False, [], "no recognized OSCAL root; schema validation not attempted"

    schema_file = schema_path_for(parsed.root_key)
    if schema_file is None or not schema_file.exists():
        return False, [], f"no vendored schema for root '{parsed.root_key}'"

    validator = _load_validator(str(schema_file))
    errors: list[SchemaError] = []
    for err in validator.iter_errors(parsed.document):
        errors.append(
            SchemaError(
                message=err.message,
                path=_path_str(err.absolute_path),
                schema_path=_path_str(err.absolute_schema_path),
            )
        )
    return len(errors) == 0, errors, None


def _semantic_ssp(doc: dict[str, Any]) -> list[SemanticWarning]:
    warnings: list[SemanticWarning] = []
    root = doc.get("system-security-plan", {})

    metadata = root.get("metadata")
    if metadata is None:
        warnings.append(
            SemanticWarning(
                check="ssp-metadata-present", message="metadata block is missing", path="system-security-plan.metadata"
            )
        )
    else:
        if "title" not in metadata:
            warnings.append(
                SemanticWarning(
                    check="ssp-metadata-title",
                    message="metadata.title is missing",
                    path="system-security-plan.metadata.title",
                )
            )
        if "oscal-version" not in metadata:
            warnings.append(
                SemanticWarning(
                    check="ssp-oscal-version",
                    message="metadata.oscal-version is missing",
                    path="system-security-plan.metadata.oscal-version",
                )
            )

    if "system-characteristics" not in root:
        warnings.append(
            SemanticWarning(
                check="ssp-system-characteristics",
                message="system-characteristics block is missing",
                path="system-security-plan.system-characteristics",
            )
        )

    control_impl = root.get("control-implementation", {})
    impl_reqs = control_impl.get("implemented-requirements")
    if impl_reqs is not None:
        if not isinstance(impl_reqs, list):
            warnings.append(
                SemanticWarning(
                    check="ssp-implemented-requirements-list",
                    message="control-implementation.implemented-requirements should be a list",
                    path="system-security-plan.control-implementation.implemented-requirements",
                )
            )
        else:
            for i, req in enumerate(impl_reqs):
                if not isinstance(req, dict):
                    continue
                if not req.get("control-id"):
                    warnings.append(
                        SemanticWarning(
                            check="ssp-implemented-requirement-control-id",
                            message="implemented requirement missing control-id",
                            path=f"system-security-plan.control-implementation.implemented-requirements[{i}].control-id",
                        )
                    )

    return warnings


def _semantic_poam(doc: dict[str, Any]) -> list[SemanticWarning]:
    warnings: list[SemanticWarning] = []
    root = doc.get("plan-of-action-and-milestones", {})

    if root.get("metadata") is None:
        warnings.append(
            SemanticWarning(
                check="poam-metadata-present",
                message="metadata block is missing",
                path="plan-of-action-and-milestones.metadata",
            )
        )

    poam_items = root.get("poam-items")
    if poam_items is not None:
        if not isinstance(poam_items, list):
            warnings.append(
                SemanticWarning(
                    check="poam-items-list",
                    message="poam-items should be a list",
                    path="plan-of-action-and-milestones.poam-items",
                )
            )
        else:
            for i, item in enumerate(poam_items):
                if not isinstance(item, dict):
                    continue
                if not (item.get("title") or item.get("description")):
                    warnings.append(
                        SemanticWarning(
                            check="poam-item-title-or-description",
                            message="poam-item has neither title nor description",
                            path=f"plan-of-action-and-milestones.poam-items[{i}]",
                        )
                    )

    return warnings


_SEMANTIC_CHECKS: dict[str, Any] = {
    "system-security-plan": _semantic_ssp,
    "plan-of-action-and-milestones": _semantic_poam,
}


def validate(parsed: ParseResult) -> ValidationResult:
    if parsed.root_key is None or parsed.document is None:
        return ValidationResult(
            root_recognized=False,
            schema_ok=False,
            schema_skipped_reason="no recognized OSCAL root",
        )

    schema_ok, schema_errors, skipped_reason = _schema_validate(parsed)

    semantic_check = _SEMANTIC_CHECKS.get(parsed.root_key)
    semantic_warnings = semantic_check(parsed.document) if semantic_check else []

    return ValidationResult(
        root_recognized=True,
        schema_ok=schema_ok,
        schema_errors=schema_errors,
        semantic_warnings=semantic_warnings,
        schema_skipped_reason=skipped_reason,
        unsupported_keywords=UNSUPPORTED_KEYWORDS,
    )
