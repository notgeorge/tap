"""Source primitive for the boto3 collector: the ``aws_op`` driver + dispatch.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-source).

A manifest entry's ``source`` has two implementations that yield the *same*
thing — an iterable of raw resource items — so the engine never branches on
which was used downstream (``req-aws-collector-source-1``):

- ``aws_op``: a declared boto3 operation, driven generically — the engine
  resolves the client for the service, uses the botocore paginator when the
  operation has one, otherwise calls it once, and extracts items via the
  manifest ``items_path``. No per-resource pagination code
  (``req-aws-collector-source-2``).
- ``custom_fn``: a named callable resolved through a plugin-local registry,
  used only where AWS needs multiple calls to assemble one logical resource.
  Code is **never** loaded from manifest data — the manifest only names the
  callable (``req-aws-collector-source-3``).

``ResponseMetadata`` is stripped from every response before items are
extracted, so it never reaches an item / ``configuration``
(``req-aws-collector-field-projection-6``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from botocore import xform_name

from .envelope import without_response_metadata
from .paths import eval_path


class SourceError(Exception):
    """A manifest ``source`` could not be driven (unknown ``custom_fn``)."""


# A custom_fn yields raw items in the same shape an aws_op would. It receives
# a bound session/region context (built by the runtime integration, later).
CustomFn = Callable[[Any], Iterator[Any]]


class CustomFnRegistry:
    """Plugin-local registry of ``custom_fn`` callables.

    The manifest names a callable; the engine resolves it here. Code is never
    imported from manifest data (``req-aws-collector-source-3``), mirroring
    ``req-tap-cares-collector-registry-6``.
    """

    def __init__(self) -> None:
        self._fns: dict[str, CustomFn] = {}

    def register(self, name: str, fn: CustomFn) -> None:
        """Register ``fn`` under ``name`` (last registration wins)."""
        self._fns[name] = fn

    def get(self, name: str) -> CustomFn:
        """Resolve a registered callable or raise ``SourceError``."""
        try:
            return self._fns[name]
        except KeyError:
            known = ", ".join(sorted(self._fns)) or "<none>"
            raise SourceError(
                f"custom_fn {name!r} is not registered (known: {known})"
            ) from None


def iter_aws_op(client: Any, op_name: str, items_path: str) -> Iterator[Any]:
    """Yield raw items from a boto3 operation, generically.

    Uses the botocore paginator when the operation has one, else a single
    call (``req-aws-collector-source-2``). The boto3 client method is the
    ``xform_name`` of the manifest's API-cased operation (``ListFunctions``
    -> ``list_functions``).

    Args:
        client: A boto3 service client.
        op_name: The API-cased operation name from the manifest.
        items_path: The manifest path that flattens the response to items.
    """
    method = xform_name(op_name)
    if client.can_paginate(method):
        for page in client.get_paginator(method).paginate():
            yield from eval_path(without_response_metadata(page), items_path)
        return
    response = getattr(client, method)()
    yield from eval_path(without_response_metadata(response), items_path)


def iter_source(
    entry: dict[str, Any],
    *,
    client_for: Callable[[str], Any],
    custom_fns: CustomFnRegistry,
    fn_context: Any = None,
) -> Iterator[Any]:
    """Drive a manifest entry's ``source``, yielding raw items.

    The single place the engine resolves ``source``; everything downstream
    sees one uniform item iterable (``req-aws-collector-source-1``).

    Args:
        entry: A validated manifest entry.
        client_for: Builds a boto3 client for a service name (credential /
            region binding lives in the runtime integration, later).
        custom_fns: The plugin-local ``custom_fn`` registry.
        fn_context: Bound session/region context passed to a ``custom_fn``.
    """
    source = entry["source"]
    if "aws_op" in source:
        client = client_for(entry["service"])
        yield from iter_aws_op(client, source["aws_op"], entry["items_path"])
        return
    fn = custom_fns.get(source["custom_fn"])
    yield from fn(fn_context)
