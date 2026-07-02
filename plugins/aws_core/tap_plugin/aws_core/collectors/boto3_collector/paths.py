"""Restricted path evaluator for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-field-projection, req-aws-collector-manifest).

A deliberately small path mini-language — NOT full JSONPath. It supports
exactly what the manifest needs:

- dotted key access:        ``LoggingConfig.LogGroup``
- list flatten:             ``Functions[]``, ``DistributionList.Items[]``
- nested flatten + project: ``Origins.Items[].DomainName`` (-> list)
- whole value is the list:  ``[]`` (custom_fn yielding a top-level list)
- scalars:                  ``FunctionArn``

Graceful-missing is the contract: a path that does not resolve yields
``None`` (scalar context) or ``[]`` (list context) — never an exception.
A `[]` segment over a missing/non-list value yields ``[]``. This mirrors
the existing aws_core hybrid nullable-field pattern; conditional/optional
AWS fields absent on a given instance are normal, not errors.
"""

from __future__ import annotations

from typing import Any

_Segment = tuple[str, bool]  # (key, is_list); key "" means a bare "[]"


def _parse(expr: str) -> list[_Segment]:
    segments: list[_Segment] = []
    for part in expr.split("."):
        if part.endswith("[]"):
            segments.append((part[:-2], True))
        else:
            segments.append((part, False))
    return segments


def _walk(value: Any, segments: list[_Segment]) -> Any:
    if not segments:
        return value

    name, is_list = segments[0]
    rest = segments[1:]

    if name:
        value = value.get(name) if isinstance(value, dict) else None

    if not is_list:
        return _walk(value, rest) if rest else value

    if not isinstance(value, list):
        return []  # graceful: missing or wrong-typed list

    if not rest:
        return list(value)

    out: list[Any] = []
    for element in value:
        projected = _walk(element, rest)
        if isinstance(projected, list):
            out.extend(item for item in projected if item is not None)
        elif projected is not None:
            out.append(projected)
    return out


def eval_path(data: Any, expr: str) -> Any:
    """Evaluate a manifest path expression against ``data``.

    Returns a list when the expression ends in (or passes through) a ``[]``
    flatten, otherwise the scalar at the path or ``None`` if absent.

    Args:
        data: The object to resolve against (a response dict or one item).
        expr: A manifest path expression (see module docstring).
    """
    return _walk(data, _parse(expr))
