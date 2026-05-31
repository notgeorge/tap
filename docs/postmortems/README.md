# TAP Post-Mortems

A growing corpus of incident write-ups for things that broke, drifted, or
behaved surprisingly while running, maintaining, and fixing a TAP instance.

> **Sibling corpus:** [`docs/aar/`](../aar/) holds **After-Action Reports** —
> retrospectives on the *development process* (how we worked). This tree holds
> incidents in the *running instance's state* (how the system behaved). Same
> neighborhood, different question. Cross-link when one caused the other.

## Why this exists — the Paladin foundation

These are not just operational hygiene. They are the **training foundation for
the Paladin system**: a forthcoming LLM-based healer for the *internal state* of
a TAP instance. Every post-mortem here is a worked example of the shape
"something was wrong with a live instance → here is how we noticed → here is the
root cause → here is the safe fix." That is exactly the knowledge a self-healing
capability needs: how to *detect* an unhealthy instance from observable signals,
and how to *remediate* it without guessing.

Each post-mortem therefore ends with a **"What Paladin would need"** section:
the machine-observable signal that would let an automated healer detect this
class of problem, and the safe remediation it could apply (or escalate).

## Taxonomy (provisional — evolving as we go)

Tags are deliberately not frozen yet. We accrete the vocabulary from real
incidents and will formalize it once the corpus is large enough to see the
natural cut-points. Today's starter tags (use `tags:` in frontmatter; add new
ones freely and note them here):

- `application-bug` — wrong behavior in committed code/data (logic, schema, seed).
- `runtime-issue` — environment/orchestration/timing/ordering; the code is right
  but the conditions it ran under were not.
- `frontend-ux` — rendering, layout, projection, or user-experience nits.
- `seed-data-integrity` — GRIFT seed bundles self-contradicting or drifting.
- `collector-dependency` — a collector's output depends on another collector or
  on grid state that must exist first.
- `silent-failure` — a missing input produced an incomplete result with no
  error, indistinguishable from a correct one. (Recurring failure *shape*, not a
  component.)
- `dev-tooling` — spawn/despawn/promote/validation harness behavior.

A single incident usually carries several tags. The `failure_class` frontmatter
field names the underlying *shape* (often shared across otherwise-unrelated
incidents) — that cross-cutting view is what Paladin will generalize from.

## Naming

`docs/postmortems/YYYY-MM-DD-<short-slug>.md`. One incident (or one tightly
coupled cluster) per file.
