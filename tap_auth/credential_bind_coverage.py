"""Static credential-bind coverage scanner (`req-tap-auth-credential-bind-provenance`).

`WebAuthnCredential` (a public key that authenticates as its user) and
`WebAuthnUserHandle` (the opaque per-user id discoverable login resolves by) are the
identity-binding writes of the auth system. They sit **off the Entity spine**, so the
direct-write lint (`req-tap-auth-policy-9`) correctly ignores them — yet a credential
bind is the most privileged write in the codebase: whoever controls it controls which
public key authenticates as whom, with no graph, capability, or ceremony in the way.

So the surface carries its own guard. Every class-level write to either model must sit
under an inline ``# TAP-CRED-BIND: <provenance>`` tag naming WHY it is a sanctioned
identity bind, from a **per-model** vocabulary:

    WebAuthnCredential (public key):  pop-ceremony | dev-profile-gate | assertion-counter
    WebAuthnUserHandle (handle):      pre-registration-handle | dev-profile-gate

The vocabulary is per-model on purpose: a public-key credential may be *bound* **only** by a
proof-of-possession ceremony or the dev-profile-gated import — never under a weaker handle
provenance (`assertion-counter` is not a bind: it is a post-verified-assertion sign_count
update on an already-bound credential, tagged so a queryset `.update()` cannot touch the key
untracked). Naming the positive reason (not "why the rule doesn't apply") is the finding-#8
lesson made structural: an untagged bind, an unknown provenance, or a handle provenance on a
credential fails the build.

This proves **containment + local verifiability**, not proof-of-possession itself — whether a
challenge was verified upstream is an interprocedural property (see the `spec-dev-validation.md`
Prior Art section). The tag asserts the site was reviewed to establish its named provenance
(each site's provenance IS locally verifiable: `pop-ceremony` calls `verify_registration_response`
in the same function; `dev-profile-gate` calls `assert_dev_import_allowed`); the guard keeps the
set of binding sites small, closed, and self-documenting.

DIY AST + tokenize, stdlib-only, Django-free, pre-boot — same shape as the other tree-scanners.
Hard lint: no baseline (every existing bind is legitimately taggable).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field, replace
from pathlib import Path

from tap.source_scan import CallSite, ScopeStackVisitor, iter_parsed_sources

_CREDENTIAL_MODEL = "WebAuthnCredential"
_HANDLE_MODEL = "WebAuthnUserHandle"
_BIND_MODELS = frozenset({_CREDENTIAL_MODEL, _HANDLE_MODEL})

_TAG = "TAP-CRED-BIND"
#: Per-model provenance vocabulary — a public-key credential may NEVER be bound under a
#: handle-only provenance. `dev-profile-gate` covers both models (the dev replay writes both).
#: `assertion-counter` is credential-only: a post-verified-assertion sign_count/last_used
#: update on an ALREADY-bound credential — accounted for (a queryset `.update()` could
#: otherwise touch `public_key`), but distinguished from a new bind.
_PROVENANCE_BY_MODEL: dict[str, frozenset[str]] = {
    _CREDENTIAL_MODEL: frozenset({"pop-ceremony", "dev-profile-gate", "assertion-counter"}),
    _HANDLE_MODEL: frozenset({"pre-registration-handle", "dev-profile-gate"}),
}
#: A tag is the *well-formed* `# TAP-CRED-BIND: <provenance>` only. A comment that merely
#: mentions the token in prose (this module's own docs) is not a tag and is ignored.
_TAG_RE = re.compile(rf"{_TAG}:\s*([a-z0-9-]+)")

# Class-level write shapes: `<Model>.objects.<method>(...)` and terminal queryset writes.
_MANAGER_WRITES = frozenset(
    {"create", "get_or_create", "update_or_create", "bulk_create", "bulk_update", "update", "acreate", "aget_or_create"}
)
_TERMINAL_WRITES = frozenset({"delete", "update", "adelete", "aupdate"})


def _model_name(node: ast.expr) -> str | None:
    """The bind-model name from `Model` (Name) or `pkg.Model` (Attribute), else None."""
    if isinstance(node, ast.Name) and node.id in _BIND_MODELS:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in _BIND_MODELS:
        return node.attr
    return None


def _manager_model(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr in ("objects", "all_objects"):
        return _model_name(node.value)
    return None


def _chain_model(node: ast.expr) -> str | None:
    """The bind model if an attr/call chain roots at `<Model>.objects` — so a terminal
    `.delete()`/`.update()` on it is a queryset write to that model."""
    while True:
        model = _manager_model(node)
        if model is not None:
            return model
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return None


def _bind_target(call: ast.Call) -> tuple[str, str] | None:
    """`(model, op)` if `call` is a class-level write to a bind model, else None."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr
    if method in _MANAGER_WRITES:
        model = _manager_model(func.value)
        if model is not None:
            return (model, method)
    if method in _TERMINAL_WRITES:
        model = _chain_model(func.value)
        if model is not None:
            return (model, method)
    if method in ("save", "asave") and isinstance(func.value, ast.Call):
        model = _model_name(func.value.func)
        if model is not None:
            return (model, method)
    return None


@dataclass(frozen=True)
class CredentialBindSite:
    """One class-level identity-bind write, with the provenance tag found on its span (or None)."""

    path: Path
    lineno: int
    end_lineno: int
    qualname: str
    model: str
    op: str
    provenance: str | None


@dataclass
class CredentialBindScanResult:
    """Identity-bind write sites, partitioned by their tag state."""

    ok: list[CredentialBindSite] = field(default_factory=list)
    #: Bind with no `# TAP-CRED-BIND` tag on its span — the regression shape.
    untagged: list[CredentialBindSite] = field(default_factory=list)
    #: Tagged, but the provenance is unknown or not valid for this model (e.g. a
    #: handle provenance on a public-key credential).
    invalid_provenance: list[CredentialBindSite] = field(default_factory=list)
    #: A `# TAP-CRED-BIND` tag sitting on no bind write — a stale claim.
    orphan_tags: list[CallSite] = field(default_factory=list)


def _tag_lines(source: str) -> dict[int, str]:
    """`{line: provenance}` for **well-formed** `# TAP-CRED-BIND: <provenance>` COMMENT tokens.

    Tokenize-precise (the marker in a string literal is not a tag) *and* form-precise: only
    a comment matching `TAP-CRED-BIND: <[a-z0-9-]+>` is a tag. A comment that merely mentions
    the token in prose — this module's and the guard's own documentation — is ignored, not
    recorded. A malformed/empty tag (`# TAP-CRED-BIND:` with no value) is likewise not a tag,
    so its bind falls through to `untagged` — still a failure, just reported as "no tag"."""
    tags: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                match = _TAG_RE.search(tok.string)
                if match:
                    tags[tok.start[0]] = match.group(1)
    except tokenize.TokenError, IndentationError, SyntaxError, ValueError:
        pass
    return tags


def _is_out_of_scope(path: Path) -> bool:
    """Tests (factories bind credentials directly) and migrations are not production
    identity-bind paths, so they are out of scope — mirrors the authz scanner."""
    return (
        "tests" in path.parts
        or path.name.startswith("test_")
        or path.name == "conftest.py"
        or "migrations" in path.parts
    )


class _BindVisitor(ScopeStackVisitor):
    """Collect every class-level identity-bind write, carrying its enclosing qualname."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.sites: list[CredentialBindSite] = []

    def visit_Call(self, node: ast.Call) -> None:
        target = _bind_target(node)
        if target is not None:
            model, op = target
            end = node.end_lineno or node.lineno
            self.sites.append(CredentialBindSite(self.path, node.lineno, end, self.current_qualname(), model, op, None))
        self.generic_visit(node)


def scan_credential_binds(roots: list[Path]) -> CredentialBindScanResult:
    """Flag identity-bind writes across `roots` by their `# TAP-CRED-BIND` provenance tag.

    Every `WebAuthnCredential`/`WebAuthnUserHandle` class-level write must carry a tag whose
    provenance is valid for that model; the scan partitions sites into ok / untagged /
    invalid, and surfaces orphaned tags. Use `tap.source_scan.first_party_source_roots()`.
    """
    result = CredentialBindScanResult()
    for parsed in iter_parsed_sources(roots, skip=_is_out_of_scope):
        visitor = _BindVisitor(parsed.path)
        visitor.visit(parsed.tree)
        tags = _tag_lines(parsed.source)
        consumed: set[int] = set()
        for site in visitor.sites:
            on_span = [line for line in range(site.lineno, site.end_lineno + 1) if line in tags]
            provenance = tags[on_span[0]] if on_span else None
            consumed.update(on_span)
            site = replace(site, provenance=provenance)
            if provenance is None:
                result.untagged.append(site)
            elif provenance in _PROVENANCE_BY_MODEL[site.model]:
                result.ok.append(site)
            else:
                result.invalid_provenance.append(site)
        for line in sorted(set(tags) - consumed):
            result.orphan_tags.append(CallSite(parsed.path, line))
    return result
