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
