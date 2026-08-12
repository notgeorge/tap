---
spec: ../../specs/spec-security-posture.md
audience: [llm, developer]
covers:
  - ../../tap_grid/specs/spec-grid-traversal-language.md
  - ../../tap_grid/specs/spec-grid-traversal-execution.md
  - ../../tap_grid/specs/spec-grid-search.md
  - ../../tap_grid/specs/spec-grid-security.md
  - ../../specs/spec-tap-boot-v0.md
  - ../../specs/spec-security-posture.md
assumes:
  - Reader knows Gryphon (a Cypher-subset language compiling to Django ORM → SQL, read-only) and that it is the canonical graph read path all graph-shaped queries route through.
  - Reader will open the cited spec requirements (every action below carries its RID + spec home) rather than trusting this summary — this doc is a map, the specs are the territory.
  - Reader understands the security posture doctrine (`specs/spec-security-posture.md`): take cheap foundational defensive edges while a surface is open; name the risks deliberately left open rather than implying completeness.
provides: |
  A resumption / handoff map for the NEXT Gryphon security-hardening pass. It records what
  the 2026-07-08 ROOT-1 / ROOT-2 remediation actually closed (with commit SHAs and the
  now-Implemented requirement RIDs), the full defense-in-depth model showing which layers
  are built vs deferred, and a rank-ordered inventory of every hardening action that was
  SPECCED in that session but deliberately left `Proposed` — each with its RID, spec home,
  what it does, why it was deferred, the demand signal that should pull it in, and a rough
  size. Read this first when picking the work back up; it exists so the deferrals are legible
  as deliberate choices, not forgotten gaps.
update-triggers:
  - Any deferred requirement in the "Remaining hardening actions" table moves Proposed → Implemented (move its row to "What shipped" and flip the status here).
  - A new Gryphon security finding is discovered (add it to the inventory with a RID once specced).
  - The opt-in searchability gate lands (the DB grant narrows from the full grid-table classification (`req-grid-table-classification.sec`) to the searchable subset — update the readonly-role scope caveat throughout).
  - The god-role decomposition or dimension-scoping RLS work begins (the two future-idea pointers below become active tracks).
  - spec-security-posture.md's ROOT-1 / ROOT-2 honest-risk register entries change.
---

# When It's Time to Come Back to Hardening Gryphon (Security)

> A resumption map, written 2026-07-08 at the close of the ROOT-1 / ROOT-2 security
> remediation on `session/gryphon-research`. The confirmed cross-table-read vulnerability is
> **closed** and the primary least-privilege backstops are **built and active**. This doc
> exists so that when the next security pass begins, the remaining actions — all of which were
> *specced* in that session but deliberately *not built* — are legible as scoped choices with
> triggers, not as an undocumented backlog. Nothing here is a surprise: every deferral is
> named in the `spec-security-posture.md` honest-risk register; this doc collects them in one
> place with the context needed to act.
>
> **How to use it:** skim "What this was" for the threat model, confirm "What shipped" against
> `git log` (trust the log over this doc if they disagree), then work the "Remaining hardening
> actions" table top-down — it is rank-ordered by leverage. Each action resolves to a spec
> requirement RID; open that requirement before building.

## What this was — the finding

A 2026-07-08 security sweep (a 24-agent parallel workflow over the live executor) confirmed
that Gryphon could **read non-grid tables** — including user PII and the password hash — from
a `grid.read`-only actor. Two root causes plus one load-bearing surprise:

- **ROOT-1 — un-allowlisted `data`-lane field paths.** All three Gryphon `data`-lane
  field-path resolvers (`_typescan_orm_path`, `_orm_path_for_envelope_path` node+edge,
  `_bare_spine_orm_path`) stripped the `data.` prefix and `__`-joined the remaining tokens
  straight into a Django ORM lookup **with no validation against the model's declared fields**.
  One root cause, four confirmed manifestations: (1) relation-crossing (`b.data.actor.password`
  → `INNER JOIN tap_user`, projecting the hash — `Batch.actor` is an FK to `AUTH_USER_MODEL`);
  (2) lookup/transform injection (`n.data.version.regex`/`.isnull`/`.year`); (3) undeclared
  field → uncaught Django `FieldError` → `500` (a field-name enumeration oracle); (4)
  `__`/bracket-key smuggling (`b.data.actor__password`, `b.data["actor__password"]`).
- **ROOT-2 — no query resource bounds.** A legitimate-in-scope but pathological-in-cost read
  (runaway time / memory / disk spill) was an availability risk with no cap.
- **Load-bearing surprise.** The production raw endpoint (`tap_api/routers/gryphon.py`)
  executed on the *writable* `default` connection, not `search_readonly` — so the read-only
  backstop the whole design assumed (write-block, resource GUCs, DB grant) was **not engaged**
  on the live raw path. Harmless only because the ORM emitted SELECT-only; a real gap.

The vulnerability class is named prior art: OWASP GraphQL "nested-relationship traversal
bypassing entry-point authz" (BOLA-via-traversal); the published mitigation is authorization
at every hop — which, for Gryphon, is the field-path allowlist. Codex's framing during spec
review: the real danger is the **Django `__` lookup-compiler boundary**, not "Cypher is scary."

## What shipped this session (closed + Implemented)

All on `session/gryphon-research`, **not yet promoted to `main`.** Confirmed by a live
end-to-end smoke test (the role authenticates over TCP as a non-superuser, reads a grid table,
is denied `tap_user` with SQLSTATE 42501, and the Flaw fires) plus targeted regression tests.

| Layer | What was built | Requirement (now `Implemented`) | Commit |
| --- | --- | --- | --- |
| **Can't-express** (the primary fix) | Data-lane field-path allowlist: every post-`data` token must resolve to a concrete declared field (or a key inside a declared JSONField); relation walks, lookups/transforms, undeclared fields, and `__`/bracket smuggling are all rejected at compile time, at all three resolvers, in `WHERE` + `RETURN`. `_validate_data_lane_steps` in `executor.py`; `model_cls` is now a required (fail-closed) param. Closes all four ROOT-1 manifestations. | `req-grid-traversal-lang-relation-guard.sec` (+ sec-1..9) | `66edbb35` |
| **Every entrypoint bound** | All raw Gryphon entrypoints default to the read-only alias (`READONLY_DB_ALIAS`), closing the writable-`default`-connection surprise so the backstops actually bind on the live path. | `req-grid-traversal-exec-scope.sec-5` | `f401614b` |
| **DB-denies** (defense in depth) | Least-privilege `tap_gryphon_ro` DB role: `SELECT` on exactly the model-layer-derived grid tables + spine, nothing else. `search_readonly` authenticates as it. A read reaching a non-grid table is denied by PostgreSQL regardless of any in-code guard. Provisioned idempotently in a boot grid-infra phase; grant set derived from the model layer (`tap_grid/grid_tables.py`, shared with the ORM read backstop) so it cannot drift. | `req-grid-search-readonly-role.sec` (+ sec-1/2/3/4/6), `req-boot-search-role` (+ sec-1..6) | `23e63897` |
| **Resource bounds** | Native PostgreSQL caps: `statement_timeout` / `lock_timeout` / `work_mem` on the connection (USERSET), `temp_file_limit` role-pinned via `ALTER ROLE` (SUSET — see gotcha below). | `req-grid-traversal-exec-resource-bounds.sec-1/2/3/7` | `27bc87f4` + `23e63897` |
| **Detection** | Broad 42501 Flaw: any `permission denied` (SQLSTATE 42501) on **any** Django connection emits a `security` Flaw at a single `connection_created` chokepoint, before the error propagates. Forward-proofs every future least-privilege role with no new wiring. | `req-grid-db-permission-flaw.sec` (+ sec-1..5) | `31079ed0` |

Spec status was reconciled Proposed → Implemented in `8aa597e9`, which also corrected two
honest-risk overclaims in `spec-security-posture.md` (it had asserted `REVOKE TEMP` was done
and that ROOT-1 was still live — neither was true).

### The gotcha worth remembering

`temp_file_limit` is a **superuser-only (SUSET)** GUC. A non-superuser role **cannot** set it
via connection startup `OPTIONS`; the live login failed `FATAL: permission denied to set
parameter "temp_file_limit"` even though provisioning succeeded. It must be **role-pinned via
`ALTER ROLE … SET`** (issued by the superuser at provision, applied at the role's login). The
other three GUCs are USERSET and ride the connection.

**The deeper lesson:** the pytest suite runs `search_readonly` *as superuser* (a deliberate
test-env risk gate — `tap/test_settings.py` overrides the role back to the app role so the
whole corpus is not gambled onto the restricted role). A superuser-bypass test environment
**cannot** catch a non-superuser connection-parameter failure. The live SET-ROLE / actual-login
**smoke test is load-bearing** — it caught what 400+ tests structurally could not. When picking
up the remaining role work, re-run the live smoke test; do not trust green pytest alone.

## The defense-in-depth model (built vs deferred)

The design is a layered net; a query must clear every layer. This is the map of which layers
exist today:

```
query text
   │
   ▼
[1] CAN'T-EXPRESS   data-lane field-path allowlist ............... BUILT ✓
   │               (illegal path rejected at compile time)
   ▼
[2] BLOCKED-BEFORE  compiled-query table-scope guard .............. DEFERRED  (exec-table-guard.sec)
    -EXEC          (alias_map ⊆ allowlist, else block + Flaw)
   │
   ▼
[3] SCOPE-NARROW    opt-in searchability gate ..................... DEFERRED  (exec-searchable.sec)
   │               (grant = FULL classification until this lands)
   ▼
[4] DB-DENIES       least-privilege tap_gryphon_ro role ........... BUILT ✓
   │               (PostgreSQL rejects non-grid table)
   ▼
[5] BOUNDED         resource caps (time/mem/disk) ................. BUILT ✓  (row-cap DEFERRED)
   │
   ▼
[6] DETECTED        broad 42501 security Flaw ..................... BUILT ✓
```

Layers 1, 4, 5 (partial), and 6 are built — that is the primary fix plus its DB backstop and
detection. Layers 2 and 3 are the *belts* that were consciously deferred (they harden an
already-closed hole); the row-cap half of layer 5 was deferred with them.

## Remaining hardening actions (specced, not built)

Rank-ordered by leverage. Every row resolves to a `Proposed` requirement — open it before
building. Size: **S** ≈ one focused session, **M** ≈ a couple, **L** ≈ a multi-session sprint
with a spec decision inside it.

| # | Action | RID / spec home | Why deferred | Trigger to build | Size |
| --- | --- | --- | --- | --- | --- |
| 1 | **Compiled-query table-scope guard.** Shape-agnostic belt: before any queryset executes, enumerate the tables it references (`query.alias_map`) and block + `security` Flaw if any is outside the searchable + spine allowlist. Plus a CI cross-check (sec-6) parsing tables from the *captured final SQL* of every Gridkin snapshot (annotations, subqueries) and asserting they're a subset of what the guard enumerated — closing the `alias_map`-is-pre-execution blind spot. | `req-grid-traversal-exec-table-guard.sec` (+ sec-1..6) — `spec-grid-traversal-execution.md` | The allowlist (layer 1) already makes ROOT-1 un-expressible; this is a second net for an *unfound* injection instance in a different dispatch shape. Real value, but not urgent once layer 1 is closed. | A new field-path/injection finding that layer 1 misses; or before exposing Gryphon to lower-trust callers. | M |
| 2 | **Opt-in searchability gate + classification ledger.** A `BaseModel` type is Gryphon-searchable only if it sets `GRYPHON_SEARCHABLE = True` (default-deny); non-opted types rejected at Validate; bare `MATCH (n)` unions only searchable types; the flag is discoverable through the registry-backed type surface. A classification ledger (searchable / intentionally-not / internal-only + rationale) reconciles with the flag so no future "set True everywhere" sweep is possible. | `req-grid-traversal-exec-searchable.sec` (+ sec-1..6) — `spec-grid-traversal-execution.md` | Inverts fail-open → fail-closed for *which types* are queryable. Until it lands, the DB grant (layer 4) is derived from the **full grid-table classification** (`req-grid-table-classification.sec`), not a narrower searchable subset — broader than the eventual target, but still strictly grid-only, so the fail-safe direction holds. | Demand to expose only a curated subset of types; or a new type added that should not be queryable by default. **Note:** this narrows the DB grant when built — update the readonly-role scope caveat everywhere it appears. | M |
| 3 | **Default result-row cap** (+ loud capped-result metadata). The executor injects a default row limit for a query naming no `LIMIT`, applied once in the row-materialization backend so every shape inherits it (larger explicit `LIMIT` clamped, smaller honored); a capped result is marked capped in envelope metadata — never a silent truncation. | `req-grid-traversal-exec-resource-bounds.sec-4` (+ sec-5/6; parent stays `Proposed`) — `spec-grid-traversal-execution.md` | The native caps (time/mem/disk) already bound the *damage* of a runaway query; the row cap is the application-level complement, cheaper to add later. | A query returning a pathologically large row set that the native caps don't catch (they bound cost, not row count); or a client OOM. | S |
| 4 | **`REVOKE TEMP` / `TEMPORARY` on the database.** A read-only transaction still permits writes to *temporary* tables (per PostgreSQL's `READ ONLY` definition). Deny temp-table creation at the privilege layer so the residue is closed outright, not merely bounded. | `req-boot-search-role-7` — `spec-tap-boot-v0.md` | The residue is already **bounded** by the role-pinned `temp_file_limit` (a 1 GB hard cap on spill). Revoking `TEMP` interacts with the default `PUBLIC` grant — it must be revoked from `PUBLIC`, which touches the app role too, so it needs a reviewed change, not a blind add. | Time to do the god-role decomposition (below), where the `PUBLIC`/app-role interaction is being reasoned about anyway. | S |
| 5 | **Structural `KeyTransform` JSON-key lowering.** A key inside a declared JSONField should lower through `KeyTransform` / `->` (structured path data), never a `__`-joined lookup string, so a JSON key named like a Django lookup/transform (`year`, `isnull`, `regex`) or containing `__` resolves unambiguously as a *key*, not a transform. | `req-grid-traversal-lang-relation-guard.sec-10` — `spec-grid-traversal-language.md` | **Residual accepted risk today:** JSON sub-keys inside a declared JSONField still lower through a `__`-joined lookup. Bounded because the *first* token is allowlist-validated as a declared field and embedded `__` is rejected — so no relation or undeclared field is reachable through the JSON tail; the residue is name-collision ambiguity on JSON keys, not a cross-table read. | A JSON key legitimately named `year`/`isnull`/`regex` producing a wrong result; or a fuzzer surfacing a JSON-tail ambiguity. | M |
| 6 | **CI touched-tables ⊆ grant guard.** A CI check asserts the set of tables Gryphon's SQL touches (from Gridkin snapshots) is a subset of the role's granted set, catching an under-grant before production rather than as a runtime 42501. | `req-grid-search-readonly-role.sec-5` — `spec-grid-search.md` | The authentic SET-ROLE test proves the grants directly today; this is the drift-prevention automation on top. Overlaps with action #1's sec-6 cross-check — build them together. | Building action #1 (share the SQL-snapshot table-extraction machinery). | S |

## Adjacent tracks (bigger, named here so they're not lost)

These are broader than Gryphon but were surfaced in the same discussion and have future-idea
docs / spec `Future` notes already written (committed in `d50efd14`):

- **Least-privilege DB-role decomposition (the "god role").** Today one database role owns the
  tables and is used for boot, migrations, grants, *and* the runtime writable connection — a
  full owner by convenience, not design. The decomposition: a bootstrap/migration role (DDL +
  grant authority, boot-time only), a runtime application role (DML only, non-owner), and the
  already-built read-only search role. The non-owner runtime role also makes RLS apply without
  `FORCE`. Home: `spec-tap-boot-v0.md` `req-boot-search-role` Future; risk register in
  `spec-security-posture.md`. **This is the natural home for action #4** (the `PUBLIC`/TEMP
  reasoning belongs here).
- **Row-Level Security for dimension / entity scoping.** `grid.read` intentionally reads the
  *entire* grid today; per-dimension / per-entity down-scoping is accepted-deferred (a ruling,
  not a finding). The future first pass: implement it at the PostgreSQL layer with RLS, as both
  a read and a write backstop, once the runtime role is a non-owner (so RLS applies without
  `FORCE ROW LEVEL SECURITY`). Home: `spec-security-posture.md` + `spec-grid-search.md` Future.

## Accepted risks / out-of-scope (named, not fixed)

Deliberately left open — recorded so they read as choices, not oversights:

- **Error-catalog leak.** `tap_grid/registry.py` (~line 86) echoes the full type catalog in an
  error message — a low-severity enumeration aid. Deferred; LOW severity.
- **42501 Flaw covers only Django-ORM connections.** Direct `psql` / psycopg / external tooling
  bypasses the `connection_created` chokepoint — that is pgaudit / DB-log territory, a later
  backstop. Named in `req-grid-db-permission-flaw.sec`.
- **Unauthenticated API schema.** `/api/v1/openapi.json` and `/docs` are served unauthenticated
  — out of Gryphon scope, part of the general API-hardening backlog.

## Pointers

- **Threat model + sweep detail:** `spec-security-posture.md` (the ROOT-1 / ROOT-2 honest-risk
  register entries — the canonical decision home for every deferral above).
- **The specs (authoritative):** `spec-grid-traversal-language.md` (allowlist), `spec-grid-traversal-execution.md`
  (searchable gate, table-guard, resource bounds, entrypoint scope), `spec-grid-search.md`
  (read-only role), `spec-grid-security.md` (42501 Flaw), `spec-tap-boot-v0.md` (role provisioning).
- **Wishlist Known Issues:** `doc-dev-gryphon-wishlist.md`.
- **Correctness (not security) hardening:** `doc-gryphon-hardening-roadmap.md` (comparative-study
  reliability backlog) and `doc-gryphon-battle-hardening.md` (per-query on-instance validation) —
  a different axis of "hardening"; this doc is the *security* axis.
