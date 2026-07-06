---
title: Gryphon Commandments - Codex Draft (RETIRED / merged)
audience:
  - llm
  - developer
status: archived
superseded-by: doc-gryphon-commandments.md
covers:
  - ../tap_grid/specs/spec-grid-traversal-language.md
update-triggers:
  - Do not update — this draft is retired. Edit doc-gryphon-commandments.md instead.
assumes:
  - Reader arrived here from a link or a grep and needs the canonical doc
provides: |
  Tombstone. This was Codex's independent draft in the commandments bake-off.
  It has been merged into the canonical doc-gryphon-commandments.md; nothing
  here is live guidance. The original text is preserved in git history.
---

# Gryphon Commandments — Codex Draft (RETIRED)

> **This document is retired.** The canonical Gryphon commandments live in
> **[`doc-gryphon-commandments.md`](doc-gryphon-commandments.md)**. Do not cite `GRY-CMD-*` /
> `FUT-GRY-CMD-*` IDs from this draft — cite the canonical `GRY-<AREA>-<n>` / `GRY-F-<n>` IDs instead.

## What happened

This was Codex's independent draft, written in parallel with Claude's for a deliberate bake-off
(2026-07-05). The two were compared on 2026-07-06. Claude's draft was chosen as the canonical base —
it won on LLM-fidelity (RFC-2119 keyword gradation), per-commandment **Enforcement** anchoring, and
scar-based **Reason** lines. This draft's genuinely-distinct contributions were then **merged into the
canonical doc**:

| This draft | Merged into canonical as |
| --- | --- |
| `GRY-CMD-11` — Variable Scope Must Be Local and Auditable | **`GRY-SEM-6`** — variable scope is local, explicit, read from the AST |
| `GRY-CMD-19` — Preserve Canonical Result Shapes | **`GRY-ARCH-11`** — canonical result shapes only; no caller-specific views |
| Agent Checklist (8 pre-flight questions) | **§ Agent pre-flight checklist** |
| Baseline Facts section | **§ Baseline facts** grounding block |
| Kubernetes API conventions prior-art | **§ Prior art & lineage** (k8s bullet) |

Everything else in this draft was already covered by the canonical doc (usually with tighter RFC-2119
wording, an Enforcement anchor, and a cited scar). The full original text remains in git history for
provenance.

## Where to go

- **The doctrine:** [`doc-gryphon-commandments.md`](doc-gryphon-commandments.md)
- **The bake-off reasoning:** session notes / commit history (2026-07-06 merge commit).
