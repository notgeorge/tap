# TAP Agent Guide

This repository is TAP, The Analogy Platform: a Python/Django, PostgreSQL-backed graph system for modeling systems, operations, compliance, and security. Future agents should treat this file as the quick-start map, not the full architecture.

## Start Here

Before designing or implementing anything substantial:

1. Read `architecture.md`.
2. Read the active step in `plan/road-rampart.md` (the Rampart roadmap; governed by `specs/spec-roadmap.md`). Judge the work against that step's Objective / Done-Test / Non-Goals; the roadmap Doctrine is the standing strategic filter.
3. Read the relevant specs under `specs/`, `<app>/specs/`, and plugin `specs/`.
4. Inspect the existing code patterns for the app or plugin being changed.
5. Only then propose or edit code.

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
- Any new on-disk structured-data format (manifest, config shape, interchange payload) ships a JSON Schema authored in the same change, and its loader validates against that schema at load — fail loud on invalid, no ad hoc unvalidated formats. GRIFT, plugin manifests, and the boto3 collector resource manifest all follow this.
- Gryphon is the canonical graph read/query interface. Raw ORM querying of the graph, or a bespoke search module wired directly to the system, is **break-glass — last-ditch only, never a go-to**. These were reasonable pre-Gryphon; from 2026-05-19 on, the *urge* to reach for either is itself a demand signal to build out whatever Gryphon is missing, not a license to bypass it. (Distinct from the ORM-writes line above: direct ORM remains fine for migrations, intentional low-level/model tests, service-layer internals, and the Search `orm`-mode compiler — that is sanctioned low-level access, not graph querying.) Canonical source: `req-grid-search-canonical-read` in `tap_grid/specs/spec-grid-search.md` (principle in force now; code-level enforcement Proposed/designed there — bounded module-registration affordance + a static ORM lint/CI gate, not a runtime guard).
- Plugin code owns domain schemas and behavior; core apps provide shared platform capabilities.
- Do not introduce multi-tenancy.
- Do not introduce autonomous agent actions without an explicit spec change.
- Plugin-specific configuration must not live in `docker-compose.yml`, core settings, or other shared infrastructure. Plugins self-configure through plugin-owned mechanisms (v0: on-disk secrets under `TAP_SECRETS_ROOT`); a durable on-grid plugin-config model is future work. (A plugin-specific collector compose entry that once lived in shared infra was exactly this anti-pattern, and was removed.)
- Do not add third-party libraries or dependencies without explicit approval. TAP deliberately minimizes third-party dependence — prefer Django/stdlib batteries-included before reaching for a new package. A new dependency needs deliberate justification and the user's go-ahead. (Approved exception, decided 2026-05-17 with the user's go-ahead: `boto3` is the sanctioned AWS-collection dependency for `aws_core`. The earlier Steampipe-based AWS collector was excised — parked at git tag `park/steampipe-tooling` — and the from-scratch boto3 collector is built starting 2026-05-18. Do not re-introduce Steampipe or "prefer the already-present tool" reasoning for AWS collection.)
- v0 is a single-developer system with no other humans and no production data. Do not fear or hedge against dramatic changes to DB structure, data, or schemas — destructive migrations, dropped/renamed fields, and reshaped data are acceptable and usually preferable to compatibility shims or "defer for migration safety." Migrations are still used; they need not be non-destructive or data-preserving. The user will explicitly say when multi-developer / production constraints begin. (Orthogonal to the no-messy-specs push rule below: parallel automated sessions still exist, so specs pushed to `main` must stay internally consistent — freedom to break data, discipline to keep specs clean.)

## Logging Conventions

- `logger = logging.getLogger(__name__)` at module top — never hardcode a logger name. The logger name *is* the callsite path: derived, never authored.
- Every committed log call at **every** level (DEBUG through CRITICAL, plus `exception`) starts with a bare 4-hex site token `[<hex>]` — no slug, no prefix (Option A, `req-tap-logging-site-ids`). Mint it with `scripts/log-site-id` (see Developer Tooling); never hand-pick a hex. The hex only has to be unique *within its file* — the module path namespaces it.
- `# noqa: TAP-LOG-ID` on the same line is the narrow, review-visible escape hatch (e.g. tight high-volume diagnostic loops).
- Use `%s` placeholders, not f-strings, in log message arguments — the formatter needs structured args for future JSON output.
- `tap/logging.py` builds `settings.LOGGING` and runs the site-token scanner (format + within-file hex uniqueness, baseline-ratchet) enforced by `tap/tests/test_log_site_ids.py`; see [`specs/spec-tap-logging.md`](specs/spec-tap-logging.md) for the full convention.

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

- Open every session with an explicit stated goal / definition-of-done (the user states it, or the agent asks for it and reflects it back). It resolves to the strategy doc's critical path when one exists. Restate it on mid-session scope changes. An agent working without a clear stated goal should stop and ask for one. (AAR root causes #1/#2 — `aar/2026-05-16-aws-collector-sprint-sprawl.md`.)
- If the user says they are framing, spitballing, or discussing, do not start implementing.
- Ask clarifying questions when the architectural choice is genuinely open. Prefer batches of five questions, ordered with the most important questions first.
- Keep edits scoped to the requested app/spec/feature.
- Do not overwrite unrelated user changes in the worktree.
- Prefer small, inspectable changes over broad refactors.
- When adding new capabilities, update specs first or alongside implementation.
- When designing or discussing any new feature or capability, search popular open-source projects for how they solved the same problem and bring that prior art into the design **early** — first design pass, before a shape is chosen, not as a late sanity check. Present it specifically: project → concrete module/pattern → how they shaped it → which patterns/approaches are worth adapting for TAP vs. which don't fit and why. Prior art is an input, still judged against the active roadmap step's fence. **Hard line: inspiration only — NEVER copy open-source code (verbatim or lightly adapted) into TAP core or any plugin, ever.** Studying OSS for shapes/structure/approach is encouraged; pulling in its source would bind TAP to that project's license, a commitment we are deliberately not ready to make. Extract the idea, discard the code, write our own clean-room implementation in our own words — never paste upstream source into specs, plans, or the codebase. This is a licensing boundary, not a style preference. If a real search found nothing comparable, say so explicitly rather than skipping silently.
- When asked to record a durable rule/fact ("add to memory", "add to AGENTS.md", "remember this", or just stating a standing rule), put it in **both** the agent memory and `AGENTS.md` (and the `MEMORY.md` index) by default — do not make the user ask twice or say "both". Applies to every agent (Claude has file memory; Codex reads `AGENTS.md`).

## Git Workflow

Never promote in-flight, incomplete, or known-messy specs to `origin/main` if it can be avoided. Specs are canonical truth and `scripts/spawn-session.sh` branches new sessions off `main`, so a drifted spec on `main` makes every parallel session build on bad truth. Treat spec reconciliation (implementation drift, plugin specs, cross-referencing specs) as a pre-push gate, not a follow-up; if a spec must stay in-flight, keep it on the session branch and exclude it from the promote.

When advancing `origin/main` from a session branch, follow `req-dev-multisession-push-workflow` in [`specs/spec-dev-multisession.md`](specs/spec-dev-multisession.md). The four-step pattern is:

1. **Never edit on `main`** — all work happens on `session/<name>`.
2. **Pre-push merge** — `git fetch origin main && git merge origin/main` into the session branch so the push is a fast-forward.
3. **Push (atomic combined refspec)** — `git push --atomic origin session/<name>:main session/<name>:session/<name>`. Two refspecs in one push, with `--atomic` so `origin/main` and `origin/session/<name>` advance all-or-nothing. WITHOUT `--atomic` the server may apply the two refspecs independently. A single `:main` refspec advances only `origin/main` and does NOT preserve the session branch on origin.
4. **Post-push sync** — `git -C /Users/george/tap-sessions/main pull --ff-only` to advance the local `main` ref. Required because `scripts/spawn-session.sh` branches new sessions off local `main` (via `git worktree add ... main`), so a stale ref means stale spawns.

Do **not** use `git fetch origin main:main` from a session worktree — Git refuses to fast-forward a branch checked out in another worktree (`fatal: refusing to fetch into branch 'refs/heads/main' checked out at ...`). The `git -C <path> pull --ff-only` form does the equivalent work *inside* the main worktree, which is the path Git permits.

The canonical implementation of the four-step pattern is `scripts/promote-to-main.sh`, invoked from inside the session worktree. For "consolidate every session at once", `scripts/promote-all-sessions.sh` iterates `$HOME/tap-sessions/.registry` and runs the per-session script in each worktree sequentially. Both support `--dry-run`. When the user expresses intent to advance `origin/main` from session branches (phrases like "consolidate sessions", "ship the sessions", "sync to main"), prefer the script over retyping the four git commands — the script is the contract.

See the spec section for the full rationale and acceptance criteria (`req-dev-multisession-promote-script`, `req-dev-multisession-promote-all-script`).

Advancing `origin/main` is gated on validation, not just a clean merge. Per `req-dev-multisession-promote-gate` (in `spec-dev-multisession.md`) and its reciprocal `req-dev-validation-promote-hook` (in [`specs/spec-dev-validation.md`](specs/spec-dev-validation.md)), the development validation gate runs *after* the pre-push merge and *before* the atomic push; a red gate aborts the promote and `origin/main` is not advanced. This is the mechanical form of the "no messy state to main" discipline above. `spec-dev-validation.md` is the **center of gravity for validation tracking**: its Validation Map is the authoritative inventory of every validation surface (spawn-env smoke, teardown, the log-site scanner, the task-backend async tiers, the cold-boot gate, the canary tier) with each surface's honest guard status. Adding any validation surface anywhere REQUIRES adding its Map row in the same change. The gate itself is `Proposed` (not yet built), so today this is the contract a session is working toward, not a script it can call.

## Developer Tooling

Mint identifiers with the provided scripts rather than hand-rolling them — both are agent-runnable and collision-safe:

- `scripts/uuid7 [N]` — UUIDv7(s) for `record_*` call-site IDs, entity IDs, etc.
- `scripts/log-site-id [N]` — collision-checked `[<hex>]` log site token(s). Run this whenever you add a `logger.*` call; every committed log call at every level needs one (`req-tap-logging-site-ids` in `specs/spec-tap-logging.md`). Do not guess a hex by hand — the script greps the tree so the token is never a collision.
