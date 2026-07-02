"""Generous-source OSCAL parser.

Accepts a Python dict, a JSON string, or an entity-like object with a
`content` attribute (e.g. a `compliance_artifact` node). Detects the OSCAL
root document type. Does not validate against schemas — see `validator`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .constants import OSCAL_ROOT_KEYS, document_type_for


@dataclass
class ParseError:
    phase: str
    message: str
    path: str | None = None


@dataclass
class ParseWarning:
    phase: str
    message: str
    path: str | None = None


@dataclass
class ParseResult:
    document: dict[str, Any] | None
    root_key: str | None
    document_type: str | None
    raw_content: str | None
    errors: list[ParseError] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.document is not None and self.root_key is not None and not self.errors


def _normalize_to_dict(source: Any) -> tuple[dict[str, Any] | None, str | None, list[ParseError], list[ParseWarning]]:
    errors: list[ParseError] = []
    warnings: list[ParseWarning] = []

    if isinstance(source, dict):
        return source, json.dumps(source, indent=2), errors, warnings

    if isinstance(source, str):
        try:
            return json.loads(source), source, errors, warnings
        except json.JSONDecodeError as exc:
            errors.append(ParseError(phase="json-parse", message=str(exc), path=None))
            return None, source, errors, warnings

    content = getattr(source, "content", None)
    if content is not None:
        entity_type = getattr(source, "entity_type", None)
        if entity_type and entity_type != "compliance_artifact":
            warnings.append(
                ParseWarning(
                    phase="source",
                    message=f"source entity_type is '{entity_type}'; preferred is 'compliance_artifact'",
                )
            )
        inner_doc, inner_raw, inner_errors, inner_warnings = _normalize_to_dict(content)
        return inner_doc, inner_raw, errors + inner_errors, warnings + inner_warnings

    errors.append(
        ParseError(
            phase="source",
            message=f"unsupported source type {type(source).__name__}; expected dict, str, or entity-like with .content",
        )
    )
    return None, None, errors, warnings


def detect_root(document: dict[str, Any]) -> str | None:
    matches = [k for k in document.keys() if k in OSCAL_ROOT_KEYS]
    if len(matches) == 1:
        return matches[0]
    return None


def parse(source: Any) -> ParseResult:
    document, raw_content, errors, warnings = _normalize_to_dict(source)

    if document is None:
        return ParseResult(
            document=None,
            root_key=None,
            document_type=None,
            raw_content=raw_content,
            errors=errors,
            warnings=warnings,
        )

    root_key = detect_root(document)
    if root_key is None:
        candidates = [k for k in document.keys() if k in OSCAL_ROOT_KEYS]
        if not candidates:
            errors.append(
                ParseError(
                    phase="root-detect",
                    message=(
                        "no recognized OSCAL root key found at top level; "
                        f"expected one of {sorted(OSCAL_ROOT_KEYS)}"
                    ),
                )
            )
        else:
            errors.append(
                ParseError(
                    phase="root-detect",
                    message=f"multiple OSCAL root keys at top level: {candidates}",
                )
            )

    return ParseResult(
        document=document,
        root_key=root_key,
        document_type=document_type_for(root_key) if root_key else None,
        raw_content=raw_content,
        errors=errors,
        warnings=warnings,
    )
