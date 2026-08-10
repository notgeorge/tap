"""Request-parsing hardening for the TAP API (the parse chokepoint).

NUL (U+0000) is representable in JSON strings and URL-encodable in query
strings, but PostgreSQL text fields cannot store it — so any NUL that rides a
request into an ORM write or filter detonates as a psycopg DataError 500 deep
in the stack (found by the authenticated api-fuzz pass, 2026-08-10). No TAP
input legitimately contains NUL, so it is rejected wholesale at the one place
every API input passes through: django-ninja routes JSON bodies, query params,
form data, and file-field names through the configured parser
(``ninja/params/models.py``), for core and plugin routers alike. Rejecting here
is the cheap foundational edge (spec-security-posture): one chokepoint instead
of per-field validators that every future schema would have to remember.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.utils.datastructures import MultiValueDict
from ninja.errors import HttpError
from ninja.parser import Parser
from ninja.types import DictStrAny


def _reject_nul(value: Any) -> None:
    """Recursively refuse NUL characters in strings, container keys included.

    400, not 422: ninja wraps any ``parse_body`` exception into
    ``HttpError(400, "Cannot parse request body")`` (``BodyModel.get_request_data``),
    so the body path can only ever surface as 400 — the query path raises the
    same status deliberately so rejection is uniform across carriers.
    """
    if isinstance(value, str):
        if "\x00" in value:
            raise HttpError(400, "NUL (U+0000) characters are not accepted in API input.")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_nul(key)
            _reject_nul(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_nul(item)


class NulForbiddingParser(Parser):
    """The default JSON parser plus wholesale NUL rejection (400, never a 500)."""

    def parse_body(self, request: HttpRequest) -> DictStrAny:
        data = super().parse_body(request)
        _reject_nul(data)
        return data

    def parse_querydict(
        self, data: MultiValueDict[str, Any], list_fields: list[str], request: HttpRequest
    ) -> DictStrAny:
        result = super().parse_querydict(data, list_fields, request)
        _reject_nul(result)
        return result
