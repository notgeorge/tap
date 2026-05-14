# TAP Agent Guide

This repository is TAP, The Analogy Platform: a Python/Django, PostgreSQL-backed graph system for modeling systems, operations, compliance, and security. Future agents should treat this file as the quick-start map, not the full architecture.

## Start Here

Before designing or implementing anything substantial:

1. Read `architecture.md`.
2. Read the relevant specs under `specs/`, `<app>/specs/`, and plugin `specs/`.
3. Inspect the existing code patterns for the app or plugin being changed.
4. Only then propose or edit code.

Specifications are the canonical source of truth. If this guide conflicts with a spec, follow the spec and update this guide later.

## Documentation Lookup

Use the OpenAI developer documentation MCP server for current OpenAI API, ChatGPT Apps SDK, Codex, and related OpenAI product documentation. The server is configured as `openaiDeveloperDocs` and points to `https://developers.openai.com/mcp`.

For non-OpenAI frameworks and libraries, prefer official upstream documentation and current installed package behavior when the answer may depend on version.

## Core TAP Rules

- `Entity` is the canonical graph spine for TAP-managed nodes and edges.
- Nodes are concrete `BaseModel` subclasses with a one-to-one backing `Entity`.
- Edges are first-class graph objects with their own backing `Entity`.
- Dimensions live on `Entity` as flat JSON metadata used for scoping and interpretation.
- TAP-managed node and edge mutations go through the service layer.
- Direct ORM writes are reserved for migrations, low-level tests, and explicitly specified subsystem internals.
- GRIFT is TAP's canonical graph interchange format. Batch-oriented imports and portable graph updates should use GRIFT-shaped documents/batches.
- Rich graph reads should use Search/Gryphon rather than ad hoc traversal helpers.
- Plugin code owns domain schemas and behavior; core apps provide shared platform capabilities.
- Do not introduce multi-tenancy.
- Do not introduce autonomous agent actions without an explicit spec change.

## Important Grid Specs

When working on graph data model behavior, read these first:

- `tap_grid/specs/spec-grid-entity.md`
- `tap_grid/specs/spec-grid-node.md`
- `tap_grid/specs/spec-grid-edge.md`
- `tap_grid/specs/spec-grid-dimension.md`
- `tap_grid/specs/spec-grid-service-write.md`
- `tap_grid/specs/spec-grid-service-read.md`
- `tap_grid/specs/spec-grid-service-batch.md`
- `tap_grid/specs/spec-grift-v0.md`
- `tap_grid/specs/spec-grid-import-grift.md`
- `tap_grid/specs/spec-grid-search.md`

## App Map

- `tap_grid` — entity spine, nodes, edges, dimensions, service layer, search, GRIFT, batches.
- `tap_plugins` — plugin loading, validation, manifests, plugin GRIFT import.
- `tap_api` — Django Ninja API layer and plugin API mounting.
- `tap_web` — web UI primitives, pages, panels, editor/viewer surfaces.
- `tap_viz` — graph visualization.
- `tap_cares` — Collect, Act, Receive, Emit, Schedule; on-grid automation plumbing for collectors, receivers, emitters, actions, schedules, run records, and GRIFT-batch-based grid updates.
- `tap_ai` — future read-only RAG/LLM surfaces.

## tap-cares Context

tap-cares capabilities should be on-grid. Collectors, collection jobs, job status, actions, schedules, and related execution records are expected to be modeled as TAP graph objects where practical, not hidden backend-only machinery.

Collector outputs that mutate the grid should become GRIFT batches. The collector/job execution path should not bypass the grid service layer.

The current tap-cares spec lives at:

- `tap_cares/specs/spec-tap-cares-v0.md`

## Collaboration Norms

- If the user says they are framing, spitballing, or discussing, do not start implementing.
- Ask clarifying questions when the architectural choice is genuinely open. Prefer batches of five questions, ordered with the most important questions first.
- Keep edits scoped to the requested app/spec/feature.
- Do not overwrite unrelated user changes in the worktree.
- Prefer small, inspectable changes over broad refactors.
- When adding new capabilities, update specs first or alongside implementation.

## Git Workflow

When advancing `origin/main` from a session branch, follow `req-dev-multisession-push-workflow` in [`specs/spec-dev-multisession.md`](specs/spec-dev-multisession.md). The four-step pattern is:

1. **Never edit on `main`** — all work happens on `session/<name>`.
2. **Pre-push merge** — `git fetch origin main && git merge origin/main` into the session branch so the push is a fast-forward.
3. **Push** — `git push origin session/<name>:main`.
4. **Post-push sync** — `git -C /Users/george/tap-sessions/main pull --ff-only` to advance the local `main` ref. This is required because `scripts/spawn-session.sh` branches new sessions off local `main`, so a stale ref means stale spawns.

Do **not** use `git fetch origin main:main` from a session worktree — Git refuses to fast-forward a branch checked out in another worktree (`fatal: refusing to fetch into branch 'refs/heads/main' checked out at ...`). The `git -C <path> pull --ff-only` form does the equivalent work *inside* the main worktree, which is the path Git permits.

See the spec section for the full rationale and acceptance criteria.
