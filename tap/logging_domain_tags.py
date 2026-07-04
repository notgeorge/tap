"""Domain-tag vocabulary — the shared specialty-routing axis for structured signals.

`req-tap-logging-domain-tags` (spec-tap-logging.md).

A **domain tag** names *which specialty concern* a structured signal belongs to,
so a router (eventually an AI on-call) dispatches to the right specialty without
reading code. It is orthogonal to *who fixes it* (a FLAW's `flaw_class`) and to
*how urgent* (severity/level).

The vocabulary lives here — one home at the logging layer both reserved
cross-cutting signals inherit — rather than inside any one signal's module:

- `FLAW` (`tap/flaws.py`) draws its `flaw_tags` from this set.
- `CONCERN` (`tap/logging.py`) draws its `tags` from this set.

So `security` means one thing across every signal, and a future third consumer
gets the vocabulary (and any new tag added here) for free. It is deliberately a
small, **registered, described** set: an ad hoc tag string would defeat code-free
routing, so an unregistered tag is a producer defect (`domain_tag_problems`).

This module is intentionally tiny and dependency-free (stdlib only) so both the
logging helpers and `tap/flaws.py` can import it without pulling in the logging
config builder or the Flaw hierarchy.
"""

from __future__ import annotations

# Registered, described domain-tag vocabulary. Extend by adding a registered,
# described entry here — never by emitting an ad hoc string at a callsite.
DOMAIN_TAGS: dict[str, str] = {
    "security": "Authentication, authorization, secrets, isolation.",
    "operational": "Runtime, availability, jobs, the platform's own machinery.",
    "data": "Grid / content integrity and consistency.",
    "config": "Instance / boot configuration.",
    "integration": "Collectors, plugins, and upstream systems.",
}


def domain_tag_problems(tags: list[str]) -> list[str]:
    """Return human-readable problems with a domain-tag list (empty list = fine).

    A tagged signal must carry at least one tag, and every tag must be registered
    in :data:`DOMAIN_TAGS`. The reaction to a problem is the caller's — a FLAW
    reports `flaw_api_misuse` (a `code` Flaw), the `concern()` helper falls back to
    a safe default — but the validation itself is shared so the vocabulary is
    enforced identically wherever it is used.
    """
    if not tags:
        return ["a tagged signal must carry at least one domain tag"]
    unknown = [t for t in tags if t not in DOMAIN_TAGS]
    if unknown:
        return [f"unknown domain tag(s) {unknown}; registered: {sorted(DOMAIN_TAGS)}"]
    return []


__all__ = ["DOMAIN_TAGS", "domain_tag_problems"]
