"""Structured specification model + RID citation scanner.

The **one** parser of TAP's specification corpus (`req-docs-rid-integrity`). Two halves:

- **Definition side** — `load_corpus()` reads every spec into a `Requirement` per `RID:`
  heading, carrying its status, its acceptance-criteria ids (ACIDs), its normalized body,
  and a content hash over that body. `tap.guards.base.defined_requirement_rids()` delegates
  here rather than keeping a second regex pair, so "what RIDs exist" is derived once.
- **Reference side** — `collect_citations()` finds every `req-*` token cited in the living
  surfaces (first-party Python comments/docstrings, specs, non-archival docs, agent
  guides, scripts), and `collect_spec_markers()` finds every `@pytest.mark.spec(...)`
  argument. Both are what the integrity guards subtract the definition side from.

Design constraints, all inherited from the tree-scanner substrate (`spec-tap-tree-scanner.md`):
stdlib only, **no Django import**, safe to call pre-boot. The repo root arrives as a
parameter rather than a module global — `tap/` already derives that fact in five separate
places (`jsonfiles`, `boot_records`, `core_version`, `preboot`, `guards.base`) and this
module deliberately does not become the sixth.

Grammar note: a RID is `req-` plus kebab segments, optionally carrying a dotted facet
(`req-grid-table-classification.sec` — the security facet of a requirement). An ACID
appends `-<n>` to its parent (`req-grid-table-classification.sec-1`). The dot was absent
from the original resolver's character class, which silently truncated all 30 dotted RIDs
to their undotted stems and made every `.sec` citation look resolvable when it was not.

Illustrative RIDs in this module — and in any prose about the convention — use the
reserved `req-example-*` namespace, so documenting the scanner does not feed it phantom
citations. This file is its own first dogfood.
"""

from __future__ import annotations

import ast
import re
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tap.source_scan import first_party_source_roots, iter_parsed_sources, semantic_hash

# `req-` + kebab segments, plus zero or more dotted facets each itself kebab.
# Matches a RID (`req-example-a`, `req-example-a.sec`) and an ACID (`req-example-a-1`,
# `req-example-a.sec-1`) identically — the RID/ACID split is structural (see
# `load_corpus`), never lexical.
_RID_BODY = r"req-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)*"

_RID_HEADING = re.compile(rf"^RID:\s*`?({_RID_BODY})`?", re.MULTILINE)
_TABLE_CELL = re.compile(rf"^\|\s*({_RID_BODY})\s*\|", re.MULTILINE)
_STATUS_LINE = re.compile(r"^Status:\s*`?([A-Za-z ]+?)`?\s*$", re.MULTILINE)
# A requirement's section ends at the next heading of level 3 or shallower. Level-4+
# headings (`#### Acceptance Criteria`, `#### Implementation`) are *inside* the
# requirement — stopping at those would cut every ACID table out of its own parent.
_SECTION_BOUNDARY = re.compile(r"^#{1,3}\s", re.MULTILINE)
# Both guards on this pattern exist because prose is hostile to token scanning:
#   * the lookbehind — a bare `\b` also fires after a hyphen, so a filename of the shape
#     `spec-req-<name>.md` would yield a phantom citation for its trailing segment;
#   * the lookahead — prose wraps mid-token, and a citation broken across a line
#     (ending `… is req-example-auth-` and resuming `model …` on the next) would otherwise
#     be captured as its truncated stem. A genuine citation is never immediately followed
#     by a hyphen: the pattern would have consumed that segment if a valid one followed.
_CITATION = re.compile(rf"(?<![\w-])({_RID_BODY})\b(?!-)")

# Reserved namespace for illustrative RIDs in prose, examples and templates. Documentation
# *about* the RID convention has to name RIDs that do not exist; without a reserved prefix
# those become permanent baseline entries that can never be remediated — the stale-exemption
# smell. Authors write `req-example-…` and the scanner skips it.
_PLACEHOLDER_PREFIX = "req-example"

# Archival corpora describe the past; a retired RID cited there is a *record*, not drift
# (`req-docs-rid-integrity-3` — the scope decision, made explicitly rather than by accident).
_ARCHIVAL_DIR_PARTS = frozenset({"aar", "postmortems", "handoff", "handoffs"})

# --- implementation claims (`req-tap-traceability-claim`) ----------------------------

#: The closed role vocabulary (`req-tap-traceability-roles`). A requirement is often
#: realized at several layers, all legitimately; uniqueness is scoped per (rid, role).
CLAIM_ROLES = frozenset({"derivation", "enforcement", "surface"})

# Assembled by concatenation so this module — and anything quoting the grammar — never
# matches its own source. Same idiom as `tap/guards/known_dupes.py`.
_CLAIM_TOKEN = "TAP-" + "IMPLEMENTS"
_CLAIM_RE = re.compile(rf"{_CLAIM_TOKEN}:\s*({_RID_BODY})@([0-9a-f]{{12}})\s*\(([a-z]+)\)")
# Anything that *looks* like an attempt. A near-miss must fail loudly rather than be
# skipped: a misspelled tag otherwise reports "no claim here" and the typo goes unnoticed
# — the documented failure mode of clippy's `SAFTEY:` hole (`req-tap-traceability-claim-3`).
_CLAIM_NEAR_MISS_RE = re.compile(r"TAP[-_ ]?IMPLEMENT(?:S|ED|ATION)?\b", re.IGNORECASE)

# The modules that *implement* the convention necessarily spell the token out in prose.
# Excluding them is the same self-reference dodge `known_dupes.py` and `record_site.py`
# make; without it the scanner reports its own documentation as malformed claims.
_CONVENTION_MODULES = frozenset(
    {
        "tap/spec_trace.py",
        "tap/guards/implements_shape.py",
        "tap/guards/implements_integrity.py",
        "tap/guards/implements_uniqueness.py",
        "tap/guards/implements_staleness.py",
        "tap/tests/test_spec_trace.py",
        "tap/tests/test_implements_claims.py",
    }
)


@dataclass(frozen=True)
class Claim:
    """A declaration that this code is the authoritative implementation of a requirement."""

    rid: str
    recorded_hash: str
    role: str
    qualname: str
    path: Path
    lineno: int

    def where(self, repo_root: Path) -> str:
        rel = self.path.relative_to(repo_root).as_posix()
        return f"{rel}:{self.lineno} ({self.qualname})"

    def key(self, repo_root: Path) -> str:
        """Uniqueness key — module, requirement, role. Never a line number.

        Keyed per *module* rather than per function so that a conditional definition
        (`if sys.version_info >= …:`) does not manufacture a false duplicate.
        """
        return f"{self.path.relative_to(repo_root).as_posix()}::{self.rid}::{self.role}"


@dataclass(frozen=True)
class MalformedClaim:
    """A line that attempted the claim grammar and missed."""

    text: str
    path: Path
    lineno: int

    def where(self, repo_root: Path) -> str:
        return f"{self.path.relative_to(repo_root).as_posix()}:{self.lineno}"


class _DocstringVisitor(ast.NodeVisitor):
    """Collects (qualname, docstring, lineno) for every module, class and function."""

    def __init__(self) -> None:
        self.scope: list[str] = []
        self.found: list[tuple[str, str, int]] = []

    def _record(self, node: ast.AST, qualname: str) -> None:
        doc = ast.get_docstring(node, clean=False)  # type: ignore[arg-type]
        if not doc:
            return
        body = getattr(node, "body", None)
        lineno = getattr(body[0], "lineno", 1) if body else 1
        self.found.append((qualname, doc, lineno))

    def visit_Module(self, node: ast.Module) -> None:
        self._record(node, "<module>")
        self.generic_visit(node)

    def _visit_scoped(self, node: ast.AST, name: str) -> None:
        self.scope.append(name)
        self._record(node, ".".join(self.scope))
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scoped(node, node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scoped(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scoped(node, node.name)


def collect_claims(repo_root: Path, source_roots: list[Path]) -> tuple[list[Claim], list[MalformedClaim]]:
    """Every well-formed claim, and every line that tried to be one and failed.

    Read from source via `ast.get_docstring`, never from `__doc__`: `python -OO` discards
    docstrings, and `functools.wraps` copies them, so a wrapper would silently inherit the
    claim of the function it wraps (`req-tap-traceability-claim-2`).
    """
    claims: list[Claim] = []
    malformed: list[MalformedClaim] = []

    for parsed in iter_parsed_sources(source_roots):
        if parsed.path.relative_to(repo_root).as_posix() in _CONVENTION_MODULES:
            continue
        visitor = _DocstringVisitor()
        visitor.visit(parsed.tree)
        for qualname, doc, doc_lineno in visitor.found:
            for offset, line in enumerate(doc.splitlines()):
                lineno = doc_lineno + offset
                match = _CLAIM_RE.search(line)
                if match is not None:
                    claims.append(
                        Claim(
                            rid=match.group(1),
                            recorded_hash=match.group(2),
                            role=match.group(3),
                            qualname=qualname,
                            path=parsed.path,
                            lineno=lineno,
                        )
                    )
                elif _CLAIM_NEAR_MISS_RE.search(line):
                    malformed.append(MalformedClaim(text=line.strip(), path=parsed.path, lineno=lineno))
    return claims, malformed


@dataclass(frozen=True)
class Requirement:
    """One requirement, as defined by an `RID:` heading in a spec."""

    rid: str
    spec_path: Path
    status: str | None
    acids: tuple[str, ...]
    body: str
    content_hash: str


@dataclass(frozen=True)
class SpecCorpus:
    """Every requirement, ACID, and bare table-row id defined across the specs."""

    requirements: dict[str, Requirement]
    acids: frozenset[str]
    other_ids: frozenset[str]

    @property
    def defined(self) -> frozenset[str]:
        """The flat union — what a citation must resolve against."""
        return frozenset(self.requirements) | self.acids | self.other_ids

    def parent_of(self, acid: str) -> str | None:
        """The requirement an ACID belongs to, or None if it is not an ACID."""
        for rid, req in self.requirements.items():
            if acid in req.acids:
                return rid
        return None


@dataclass(frozen=True)
class Citation:
    """One `req-*` token cited somewhere outside a spec's own definition."""

    token: str
    path: Path
    lineno: int

    def where(self, repo_root: Path) -> str:
        return f"{self.path.relative_to(repo_root).as_posix()}:{self.lineno}"


def spec_files(repo_root: Path) -> list[Path]:
    """Every spec Markdown file: top-level `specs/`, each app's, each in-repo plugin's."""
    files = sorted((repo_root / "specs").glob("*.md"))
    files += sorted(repo_root.glob("*/specs/*.md"))
    files += sorted(repo_root.glob("plugins/*/specs/*.md"))
    return files


def _normalize(body: str) -> str:
    """Whitespace-collapsed requirement text, with the `Status:` line removed.

    Status is excluded deliberately: it is metadata *about* the requirement, it moves on
    its own lifecycle, and the derived-status work computes it from evidence — so hashing
    it would make every claim self-churn the moment a status advanced.
    """
    return " ".join(_STATUS_LINE.sub("", body).split())


def load_corpus(repo_root: Path) -> SpecCorpus:
    """Parse every spec into the structured requirement model."""
    requirements: dict[str, Requirement] = {}
    all_cells: set[str] = set()
    claimed_acids: set[str] = set()

    for path in spec_files(repo_root):
        text = path.read_text(encoding="utf-8")
        all_cells.update(_TABLE_CELL.findall(text))

        headings = list(_RID_HEADING.finditer(text))
        for index, match in enumerate(headings):
            rid = match.group(1)
            # The requirement's section runs to the next markdown heading, or to the next
            # `RID:` heading if one arrives first (some specs stack requirements densely).
            start = match.end()
            limit = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            next_section = _SECTION_BOUNDARY.search(text, start)
            if next_section is not None:
                limit = min(limit, next_section.start())
            body = text[start:limit]

            status_match = _STATUS_LINE.search(body)
            # An ACID is a table row *inside this requirement's section* whose id extends
            # the RID with `-<n>`. That co-location is what gives the parent/child relation.
            acids = tuple(
                sorted(
                    cell
                    for cell in _TABLE_CELL.findall(body)
                    if cell.startswith(f"{rid}-") and cell[len(rid) + 1 :].isdigit()
                )
            )
            claimed_acids.update(acids)
            requirements[rid] = Requirement(
                rid=rid,
                spec_path=path,
                status=status_match.group(1).strip() if status_match else None,
                acids=acids,
                body=body,
                content_hash=semantic_hash(_normalize(body)),
            )

    other_ids = all_cells - set(requirements) - claimed_acids
    return SpecCorpus(
        requirements=requirements,
        acids=frozenset(claimed_acids),
        other_ids=frozenset(other_ids),
    )


def _is_archival(path: Path, repo_root: Path) -> bool:
    parts = path.relative_to(repo_root).parts
    return any(part in _ARCHIVAL_DIR_PARTS for part in parts)


def python_scan_roots(repo_root: Path) -> list[Path]:
    """First-party Python roots for citation scanning.

    `first_party_source_roots` returns the *apps* (a directory with `apps.py`), which
    deliberately excludes `tap/` — the project package. `tap/` is where the boot, secrets,
    guard and scanner machinery lives, and therefore where a large share of RID citations
    sit, so this scanner adds it back explicitly rather than silently under-covering.
    """
    roots = list(first_party_source_roots(repo_root))
    project_package = repo_root / "tap"
    if project_package.is_dir():
        roots.append(project_package)
    return roots


def living_markdown(repo_root: Path) -> list[Path]:
    """Docs and agent guides whose citations must resolve — archival corpora excluded."""
    docs_dir = repo_root / "docs"
    files = [p for p in sorted(docs_dir.rglob("*.md")) if not _is_archival(p, repo_root)] if docs_dir.is_dir() else []
    files += [p for p in (repo_root / "CLAUDE.md", repo_root / "AGENTS.md") if p.exists()]
    return files


def _iter_python_citations(repo_root: Path, roots: list[Path]) -> Iterator[Citation]:
    """Citations in first-party Python — docstrings via `ast`, comments via `tokenize`.

    Deliberately *not* every string literal: a RID inside an arbitrary string is data (a
    guard's own `rid` field, an error message, a test fixture), not a cross-reference.
    """
    for parsed in iter_parsed_sources(roots):
        for node in ast.walk(parsed.tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node, clean=False)
            if not doc:
                continue
            doc_start = getattr(node.body[0], "lineno", 1) if node.body else 1
            for offset, line in enumerate(doc.splitlines()):
                for token in _CITATION.findall(line):
                    yield Citation(token=token, path=parsed.path, lineno=doc_start + offset)
        try:
            with parsed.path.open("rb") as handle:
                for tok in tokenize.tokenize(handle.readline):
                    if tok.type != tokenize.COMMENT:
                        continue
                    for token in _CITATION.findall(tok.string):
                        yield Citation(token=token, path=parsed.path, lineno=tok.start[0])
        except tokenize.TokenError, SyntaxError, UnicodeDecodeError, OSError:
            continue


def _iter_text_citations(paths: list[Path]) -> Iterator[Citation]:
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in _CITATION.findall(line):
                yield Citation(token=token, path=path, lineno=lineno)


def collect_citations(repo_root: Path, source_roots: list[Path]) -> list[Citation]:
    """Every `req-*` citation across the living surfaces."""
    citations = list(_iter_python_citations(repo_root, source_roots))
    citations += list(_iter_text_citations(spec_files(repo_root)))
    citations += list(_iter_text_citations(living_markdown(repo_root)))
    return citations


def citation_key(citation: Citation, repo_root: Path) -> str:
    """Baseline key for a citation: file + token, deliberately **without** a line number.

    A dangling citation is remediated per (file, token) — you fix every occurrence in the
    file together — and a line-keyed baseline would churn on every unrelated edit above it
    (`spec-tap-callsite-identity.md`: the location is navigation, never the key).
    """
    return f"{citation.path.relative_to(repo_root).as_posix()}::{citation.token}"


def dangling_citations(repo_root: Path) -> list[Citation]:
    """Every citation whose `req-*` token resolves to no defined requirement or ACID."""
    corpus = load_corpus(repo_root)
    citations = collect_citations(repo_root, python_scan_roots(repo_root))
    return [c for c in citations if c.token not in corpus.defined and not c.token.startswith(_PLACEHOLDER_PREFIX)]


def malformed_claims(repo_root: Path) -> list[MalformedClaim]:
    """Lines that attempted the claim grammar and missed (`req-tap-traceability-claim-3`)."""
    return collect_claims(repo_root, python_scan_roots(repo_root))[1]


def invalid_claims(repo_root: Path) -> list[tuple[Claim, str]]:
    """Claims naming a requirement that does not exist, or a role outside the vocabulary."""
    corpus = load_corpus(repo_root)
    claims, _ = collect_claims(repo_root, python_scan_roots(repo_root))
    problems: list[tuple[Claim, str]] = []
    for claim in claims:
        requirement = corpus.requirements.get(claim.rid)
        if claim.rid not in corpus.defined:
            problems.append((claim, "names a requirement that does not exist"))
        elif claim.role not in CLAIM_ROLES:
            problems.append((claim, f"role {claim.role!r} is not one of {sorted(CLAIM_ROLES)}"))
        elif requirement is not None and requirement.status in DOCTRINE_STATUSES:
            # `Unwanted` coverage: the requirement never asked to be implemented.
            problems.append(
                (
                    claim,
                    "is standing doctrine (In Force) — doctrine is conformed to, not implemented. "
                    "Either the requirement is mis-labelled, or the checkable part of it should be "
                    "split out as its own requirement and claimed there",
                )
            )
    return problems


def stale_claims(repo_root: Path) -> list[tuple[Claim, str]]:
    """Claims whose recorded hash no longer matches their requirement (`Outdated`).

    Returns `(claim, expected_hash)`. A claim on a requirement that does not resolve is
    *not* reported here — that is `invalid_claims`' finding, and reporting it twice would
    make one defect look like two.
    """
    corpus = load_corpus(repo_root)
    claims, _ = collect_claims(repo_root, python_scan_roots(repo_root))
    stale: list[tuple[Claim, str]] = []
    for claim in claims:
        requirement = corpus.requirements.get(claim.rid)
        if requirement is None:
            continue
        if claim.recorded_hash != requirement.content_hash:
            stale.append((claim, requirement.content_hash))
    return stale


def duplicate_claim_groups(repo_root: Path) -> dict[tuple[str, str], list[Claim]]:
    """`(rid, role)` -> claims, for every pair claimed by more than one module.

    Within-module repeats collapse first: a conditional definition legitimately declares
    the same claim twice in one file (`req-tap-traceability-uniqueness-3`).
    """
    claims, _ = collect_claims(repo_root, python_scan_roots(repo_root))
    by_pair: dict[tuple[str, str], dict[str, Claim]] = {}
    for claim in claims:
        module = claim.path.relative_to(repo_root).as_posix()
        by_pair.setdefault((claim.rid, claim.role), {}).setdefault(module, claim)
    return {pair: list(mods.values()) for pair, mods in by_pair.items() if len(mods) > 1}


# --- evidence and derived status (`req-tap-traceability-status`) ----------------------

#: Declared statuses that assert the requirement is built. A claim of `Verified` is the
#: only one this module gates on, because it is the only one that asserts *verification*.
_BUILT_STATUSES = frozenset({"Implemented", "Verified"})
#: Statuses that assert the requirement is NOT yet built — evidence contradicts them.
_UNBUILT_STATUSES = frozenset({"Proposed", "Backlog"})
#: Standing doctrine — in effect now, never "completed", and expecting *conformance* from
#: other work rather than an implementation of its own. The convention is Python's, whose
#: PEP 1 gives Informational and Process PEPs a status of `Active` precisely because they
#: "are never meant to be completed"; Ethereum calls the same state `Living`, and IETF's
#: BCP series has no maturity ladder at all because doctrine is in force or it is not.
#:
#: A doctrine requirement is neither built nor unbuilt, so it belongs in **neither**
#: coverage bucket. Counting it as built-without-evidence was the miscount that made the
#: unevidenced number unreadable.
DOCTRINE_STATUSES = frozenset({"In Force"})


@dataclass(frozen=True)
class Evidence:
    """What the tree can actually show about a requirement."""

    rid: str
    declared: str | None
    implemented_by: tuple[Claim, ...]
    verified_acids: tuple[str, ...]

    @property
    def classes(self) -> int:
        """How many *independent* evidence classes exist — implementation, verification.

        Two is the bar for `Verified`. A requirement evidenced only by its own
        implementation is not verified: the implementation asserting it works is the claim
        under test, not a check on it. SQLite renders a requirement green only at 2+
        independent evidence classes for exactly this reason.
        """
        return bool(self.implemented_by) + bool(self.verified_acids)

    @property
    def derived(self) -> str:
        """The status the evidence supports, independent of what the spec declares."""
        if self.implemented_by and self.verified_acids:
            return "Verified"
        if self.implemented_by:
            return "Implemented"
        if self.verified_acids:
            return "Tested"
        return "Unevidenced"


def collect_evidence(repo_root: Path) -> dict[str, Evidence]:
    """Per-requirement evidence: implementation claims and verified acceptance criteria."""
    corpus = load_corpus(repo_root)
    roots = python_scan_roots(repo_root)
    claims, _ = collect_claims(repo_root, roots)
    marked = {m.token for m in collect_spec_markers(roots)}

    by_rid: dict[str, list[Claim]] = {}
    for claim in claims:
        by_rid.setdefault(claim.rid, []).append(claim)

    evidence: dict[str, Evidence] = {}
    for rid, requirement in corpus.requirements.items():
        evidence[rid] = Evidence(
            rid=rid,
            declared=requirement.status,
            implemented_by=tuple(by_rid.get(rid, ())),
            verified_acids=tuple(sorted(acid for acid in requirement.acids if acid in marked)),
        )
    return evidence


def _evidence_or_scan(repo_root: Path, evidence: dict[str, Evidence] | None) -> dict[str, Evidence]:
    """Reuse a caller's scan when it has one — each `collect_evidence` walks the whole tree."""
    return collect_evidence(repo_root) if evidence is None else evidence


def unearned_verified(repo_root: Path, evidence: dict[str, Evidence] | None = None) -> list[Evidence]:
    """Requirements declaring `Verified` without two independent evidence classes.

    The one hard gate in the status work. It deliberately does **not** fault a requirement
    for lacking a claim — claims are opt-in and scarce by design
    (`req-tap-traceability-scope-1`), so faulting their absence would contradict the
    convention. What it faults is the strongest possible assertion — "this is verified" —
    made without the evidence that would justify it.
    """
    return [e for e in _evidence_or_scan(repo_root, evidence).values() if e.declared == "Verified" and e.classes < 2]


def under_declared(repo_root: Path, evidence: dict[str, Evidence] | None = None) -> list[Evidence]:
    """Requirements carrying evidence while still declared unbuilt.

    Reported, never failed: a requirement can legitimately be `Proposed` while part of it
    is built, and a doctrine requirement is cited as guidance rather than implemented.
    """
    return [e for e in _evidence_or_scan(repo_root, evidence).values() if e.declared in _UNBUILT_STATUSES and e.classes]


def doctrine(repo_root: Path, evidence: dict[str, Evidence] | None = None) -> list[Evidence]:
    """Requirements in force as standing doctrine — outside the coverage question entirely."""
    return [e for e in _evidence_or_scan(repo_root, evidence).values() if e.declared in DOCTRINE_STATUSES]


def claimed_doctrine(repo_root: Path, evidence: dict[str, Evidence] | None = None) -> list[Evidence]:
    """Doctrine requirements carrying an implementation claim — `Unwanted` coverage.

    The inverse check, and the thing that keeps the doctrine label from decaying into
    decoration. OpenFastTrace fires `Unwanted` when an item covers something that *did not
    ask* for coverage; Doorstop warns when a non-normative item has links; NIST's published
    catalogue has zero of 3,707 assessment objectives pointing at a guidance part. The
    lesson those three share: **a flag that only ever removes a check is a flag nobody
    maintains.** Marking a requirement as doctrine has to cost something, and what it costs
    is the ability to claim it.

    A doctrine requirement is conformed to, not implemented. If something genuinely *is*
    the one derivation of a doctrine requirement's fact, that is a signal the requirement
    was mis-labelled — or that a checkable part of it should be split out as its own
    requirement, which is what PCI does with Applicability Notes and NIST with ODPs.
    """
    return [e for e in doctrine(repo_root, evidence) if e.implemented_by]


def unevidenced_built(repo_root: Path, evidence: dict[str, Evidence] | None = None) -> list[Evidence]:
    """Requirements declared built with no evidence at all.

    The honest headline number, and deliberately **not** a failure: with claims opt-in,
    this measures how much of the corpus has been *targeted*, not how much is wrong.
    """
    return [
        e for e in _evidence_or_scan(repo_root, evidence).values() if e.declared in _BUILT_STATUSES and not e.classes
    ]


EVIDENCE_BEGIN = "<!-- BEGIN GENERATED EVIDENCE — manage.py guards --sync-evidence -->"
EVIDENCE_END = "<!-- END GENERATED EVIDENCE -->"


def render_evidence_markdown(repo_root: Path) -> str:
    """The generated evidence report — declared status against what the tree can show.

    Deliberately compact: it lists only requirements that *have* evidence, plus the
    contradictions, rather than all ~1,100 rows. A report nobody can read is a report
    nobody reads, and the tag's whole value depends on this being looked at.
    """
    evidence = collect_evidence(repo_root)  # one tree walk; every helper below reuses it
    evidenced = sorted((e for e in evidence.values() if e.classes), key=lambda e: e.rid)
    built_without = unevidenced_built(repo_root, evidence)
    under = sorted(under_declared(repo_root, evidence), key=lambda e: e.rid)
    unearned = sorted(unearned_verified(repo_root, evidence), key=lambda e: e.rid)

    doctrinal = doctrine(repo_root, evidence)
    lines = [
        EVIDENCE_BEGIN,
        "",
        f"**{len(evidence)}** requirements · **{len(doctrinal)}** standing doctrine · "
        f"**{len(evidenced)}** carry evidence · "
        f"**{sum(1 for e in evidenced if e.classes == 2)}** carry both classes · "
        f"**{len(built_without)}** declared built with none.",
        "",
        "Four separate facts, deliberately not blended into one percentage. **Doctrine** is "
        'outside the coverage question — in force now, never "completed", expecting '
        "conformance rather than an implementation. **Declared built with none** is context, "
        "not a defect list: claims are opt-in and scarce by design "
        "(`req-tap-traceability-scope`), so it measures how much of the corpus has been "
        "deliberately targeted, not how much is wrong. Collapsing these into a single "
        "coverage score is what makes such a score meaningless.",
        "",
        "| Requirement | Declared | Derived | Implementation | Verified by |",
        "| --- | --- | --- | --- | --- |",
    ]
    for e in evidenced:
        impl = ", ".join(f"`{c.qualname}`" for c in e.implemented_by) or "—"
        acids = ", ".join(f"`{a}`" for a in e.verified_acids) or "—"
        lines.append(f"| `{e.rid}` | {e.declared or '—'} | {e.derived} | {impl} | {acids} |")

    lines += [
        "",
        "**Declared unbuilt, but evidence exists** — reported, never failed; a "
        "requirement can be partly built, and a doctrine requirement is cited as guidance:",
    ]
    if under:
        lines += ["", "| Requirement | Declared | Derived |", "| --- | --- | --- |"]
        lines += [f"| `{e.rid}` | {e.declared} | {e.derived} |" for e in under]
    else:
        lines += ["", "None."]

    lines += [
        "",
        "**Declared `Verified` without two evidence classes** — this one fails " "(`req-tap-traceability-status`):",
    ]
    lines += ["", "None." if not unearned else ""]
    lines += [f"- `{e.rid}` (evidence classes: {e.classes})" for e in unearned]
    lines += ["", EVIDENCE_END]
    return "\n".join(lines)


def unresolvable_markers(repo_root: Path) -> list[Citation]:
    """Every `@pytest.mark.spec(...)` argument that resolves to nothing defined."""
    corpus = load_corpus(repo_root)
    markers = collect_spec_markers(python_scan_roots(repo_root))
    return [m for m in markers if m.token not in corpus.defined]


def collect_spec_markers(source_roots: list[Path]) -> list[Citation]:
    """Every `@pytest.mark.spec("<acid>")` argument, read from the AST.

    Test modules are parsed, never imported — the scanner runs pre-boot and must not
    trigger Django setup or fixture collection as a side effect.
    """
    markers: list[Citation] = []
    for parsed in iter_parsed_sources(source_roots):
        for node in ast.walk(parsed.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "spec":
                continue
            owner = func.value
            if not (isinstance(owner, ast.Attribute) and owner.attr == "mark"):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    markers.append(Citation(token=arg.value, path=parsed.path, lineno=node.lineno))
    return markers
