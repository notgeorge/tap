# Gryphon Feature Request: Regex Match Operator `=~`

**Requesting plugin:** `github_core`
**Filed:** 2026-05-28
**Status:** Filed — awaiting review by gryphon_playground session

## Demand signal

`github_core`'s link-manifest resolver supports a `near_match_pattern` on each
link rule — when an exact match yields zero candidates AND a target row's
field matches the pattern, the resolver emits a `LINK_NEAR_MATCH` warning so
an operator can investigate rather than silently miss a cross-grid link.

The OIDC link rule's `near_match_pattern` is `githubusercontent\.com`, used
to catch URL variants like `https://Token.Actions.GitHubUserContent.com`
(scheme prefix, mixed case, GHES tenants). The resolver currently reaches
into Django ORM with `__iregex` because Gryphon has no regex operator. That
ORM reach is exactly the kind of break-glass the `feedback_gryphon_over_orm`
memory flags as a demand signal to extend Gryphon.

**Blocking AC on the github_core side:** `req-github-core-grid-links-1` in
`plugins/github_core/specs/spec-github-core-v0.md` is stuck on this Gryphon
gap.

**Implementation file the resolver reaches for ORM from:**
`plugins/github_core/collectors/github_collector/enrichment.py` — search for
`__iregex` in `resolve_links()`. That one query is the entire migration
target on the consumer side.

## Existing spec anchor

`tap_grid/specs/spec-grid-traversal-language.md` → `req-grid-traversal-lang-string-match`
already lists this as Future:

> - Wildcard / regex-like pattern matching — a single `LIKE`- or
>   `MATCHES`-style operator generalizing these three. **Deliberately
>   deferred: the three explicit operators cover the detected demand and
>   avoid the needle-escaping and case-sensitivity surface a pattern
>   language drags in. Promote when a real query needs a shape the three
>   fixed operators cannot express.**

That promotion moment is here.

## Prior art — Cypher-family conventions

| System | Operator | Flavor | Case-insensitive |
| --- | --- | --- | --- |
| Neo4j Cypher (canonical) | `=~` | `java.util.regex` | `(?i)` inline flag |
| openCypher 9 (spec) | `=~` | impl-defined | inline flags |
| Apache AGE (Cypher on Postgres) | `=~` | POSIX (Postgres) | `(?i)` inline flag |
| Memgraph | (no regex op) | n/a | `toLower()` normalize |

Three of four standardize on `=~` with inline-flag case-insensitivity.
Memgraph is the outlier and reaches for `toLower()` precisely because they
omitted regex — exactly the workaround we're trying to escape. Following
Neo4j/openCypher gives query authors a familiar shape and avoids inventing
TAP-specific spelling.

### Alternative considered: `_CI` operator variants

An earlier draft of this request proposed `STARTS_WITH_CI` / `ENDS_WITH_CI`
/ `CONTAINS_CI` as a smaller-scope ask. Dropped because:

- No surveyed Cypher-family system uses that shape. Inventing it would
  diverge from the convention Gryphon is otherwise following.
- Inline `(?i)` in `=~` covers case-insensitive needs without duplicating
  the existing operator surface.
- Future regex-shaped needs (anchored prefix with wildcard middle, alternation,
  character classes) would still drive `=~` later — better to land once.

The user explicitly chose the broader-scope ask: "i'm willing to land regex,
it's going to be needed more and more, may as well tackle it now."

## Proposed shape

Add `=~` to the `Comparison` operator family, alongside `=`, `<>`, `<`, `>`,
`STARTS_WITH`, `ENDS_WITH`, `CONTAINS`.

```text
field_path =~ value
```

Where `value` is a string literal or `$param` reference holding a regex
pattern.

### Semantics

- **Full-string match (anchored).** Following Neo4j/openCypher: `=~` matches
  the *entire* field value against the pattern (implicit `^...$`). Substring
  matching is expressed explicitly as `=~ ".*needle.*"`. This is the
  long-standing Cypher convention; deviating would surprise anyone coming
  from Neo4j and openCypher.
- **Case-insensitive via inline flag.** `n.url =~ "(?i)github"` — no separate
  `=~i` operator, no separate `CONTAINS_CI` sibling. Inline flags `(?i)`,
  `(?s)`, `(?m)`, `(?x)` work as supported by the backing engine.
- **Regex flavor: PostgreSQL POSIX extended regex** (the Postgres `~`/`~*`
  engine, surfaced via Django's `__regex` / `__iregex` lookups). This is the
  natural backing for our stack and supports the embedded-options syntax
  `(?ismx)`. The flavor is documented; query authors who need PCRE-specific
  features (named groups beyond `(?P<name>...)`, lookbehinds with variable
  width, etc.) hit a known boundary.
- **Compiles to Django regex lookup.** When no `(?i)` flag is present in the
  pattern, compile to `<field>__regex=<pattern>`. When `(?i)` is present at
  the start, two valid paths (see Open Questions below):
  - **(a)** Strip the `(?i)` prefix and compile to `__iregex` so Postgres's
    `~*` operator handles case-insensitivity at the engine level.
  - **(b)** Always compile to `__regex` and let Postgres's regex engine
    consume the inline flag.
- **NULL handling:** `null =~ pattern` returns `null` (three-valued logic,
  standard Cypher). `value =~ null` is also `null`.
- **Composes with combinators.** A regex `Comparison` joins `AND` / `OR` /
  `NOT` like any comparison.
- **Parameterizable needle.** `WHERE n.url =~ $pattern` — `$pattern` resolves
  at execution time. No whole-pattern parameterization issues — patterns are
  scalar strings.

### What this looks like in practice

```text
# github_core's near-match query becomes:
MATCH (n:aws_iam_oidc_provider)
WHERE n.data.url =~ "(?i).*githubusercontent\\.com.*"
  AND NOT n.data.url = $exact
RETURN n
```

```text
# Substring match (case-sensitive):
MATCH (n:finding) WHERE n.data.title =~ ".*timeout.*" RETURN n

# Anchored prefix (long-form of STARTS_WITH):
MATCH (n) WHERE n.entity_type =~ "aws_.*" RETURN n
```

### What this deliberately doesn't add

- **`_CI` variants of `STARTS_WITH` / `ENDS_WITH` / `CONTAINS`.** Inline
  `(?i)` in `=~` covers case-insensitive needs. Adding `_CI` siblings would
  duplicate functionality and diverge from Cypher convention.
- **A `MATCHES` keyword alternative spelling.** `=~` is the canonical Cypher
  symbol. One spelling.
- **PCRE-specific features.** Postgres POSIX is the documented flavor. Future
  move to PCRE (via `pg_pcre` extension or similar) is a separate spec
  change.
- **Pattern compilation caching.** Postgres caches its own regex compilation
  per backend session; we don't need to layer additional caching at the
  Gryphon level for v0.

### Security / DoS surface

- **Catastrophic backtracking.** POSIX extended regex on Postgres is less
  prone to catastrophic backtracking than PCRE in some shapes, but pathological
  patterns can still cause CPU exhaustion. **Document this risk in the spec
  body**; do not silently swallow it.
- **Needle escaping.** Unlike `STARTS_WITH` / `CONTAINS` (which escape `%`
  and `_` literally), `=~` does NOT escape special regex metacharacters in
  the needle. This is the explicit deal: query authors writing `=~` are
  opting into regex syntax. `$param` substitution treats the param value as
  a regex string, not as escaped literal — so `$param = "."` is "any
  character," not the literal dot. Document this prominently; it's the
  Cypher norm but worth pinning.
- **No catastrophic-pattern detection.** v0 does not analyze patterns for
  known-bad shapes (nested quantifiers like `(a+)+`). Operator beware.
  Future work could add a pattern validator if a real incident motivates it.
- **Statement-level timeout** (existing Postgres/Django machinery) is the
  catch-all defense.

## Acceptance criteria (suggested)

| ACID | Title | Description |
| --- | --- | --- |
| `req-grid-traversal-lang-regex-1` | Operator Accepted | The parser accepts `field_path =~ value` as a `WHERE` `Comparison`. |
| `req-grid-traversal-lang-regex-2` | Full-String Match Semantics | `=~` matches the entire field value (implicit `^...$`). Substring matching is expressed as `=~ ".*needle.*"`. Documented prominently. |
| `req-grid-traversal-lang-regex-3` | POSIX Flavor | The regex flavor is PostgreSQL POSIX extended regex. Documented; PCRE-specific features fail or behave differently. |
| `req-grid-traversal-lang-regex-4` | Inline Flags Supported | `(?i)`, `(?s)`, `(?m)`, `(?x)` work per Postgres regex semantics. |
| `req-grid-traversal-lang-regex-5` | Compiles To Django Regex Lookup | Compiles to `__regex` (or `__iregex` when `(?i)` is present at pattern start; pick one path consistently — see Open Questions). |
| `req-grid-traversal-lang-regex-6` | NULL Three-Valued | `null =~ pattern` and `value =~ null` both return `null`. |
| `req-grid-traversal-lang-regex-7` | Needle Is Regex Text | The needle is NOT escaped — metacharacters carry regex meaning. Documented as the explicit deal. |
| `req-grid-traversal-lang-regex-8` | Needle May Be A Param | `WHERE n.url =~ $pattern` accepts a `$param` reference resolved at execution time. |
| `req-grid-traversal-lang-regex-9` | Composes With Combinators | A regex `Comparison` combines with `AND` / `OR` / `NOT` like any comparison. |
| `req-grid-traversal-lang-regex-10` | Gridkin Scenario | A new scenario in `plugins/gryphon_playground/scenarios/` exercises: case-sensitive full-match, case-insensitive via `(?i)`, substring via `.*needle.*`, needle with `\.` escape, parameterized pattern, NULL field value, and one composed `AND` expression. |
| `req-grid-traversal-lang-regex-11` | Documented DoS Surface | The spec body explicitly warns about catastrophic backtracking risk and notes that statement-level timeout is the defense. |

## Open questions for the implementing session

1. **Compile target when `(?i)` is in the pattern.** Two valid paths:
   - **(a)** Detect leading `(?i)`, strip, and route to Django's `__iregex`
     lookup.
   - **(b)** Always route to `__regex` and let Postgres's regex engine
     consume the inline flag.

   Both work. (a) produces a slightly cleaner SQL plan (Postgres has `~*`
   as a distinct operator with potentially different index optimization).
   (b) is simpler code with no flag-stripping. No strong preference from
   the consumer side; pick whichever produces the better EXPLAIN output on
   real queries.

2. **Spine vs data-lane field access.** The bare-labelless-MATCH spec talks
   about spine vs data-lane predicate placement; confirm `=~` works in both
   paths (it should be just another `Comparison` leaf compiled into the
   same `Q`-tree).

3. **Index-use docs.** Postgres can use trigram indexes for some regex
   patterns (anchored prefix). Worth a one-line note in the spec body that
   the query planner may or may not use indexes depending on pattern shape,
   with a pointer to Postgres's `pg_trgm` extension as future tuning.

## What this unblocks downstream

- `req-github-core-grid-links-1` (Search/Gryphon Read Path) in
  `plugins/github_core/specs/spec-github-core-v0.md` flips
  `Proposed → Implemented` once github_core's resolver migrates to use the
  new operator.
- The ORM `__iregex` query in
  `plugins/github_core/collectors/github_collector/enrichment.py` becomes a
  Gryphon Search, completing the github_core resolver's migration off raw
  ORM.
- The link-manifest `near_match_pattern` shape (`source_constant` +
  `near_match_pattern`) becomes a first-class precedent any future plugin
  can adopt without an ORM carve-out.
- The "promote when a real query needs a shape the three fixed operators
  cannot express" gate in the existing string-match spec gets discharged —
  both with a documented consumer (this) and a documented operator (`=~`).

## Coordination

When this lands, ping the github_core session (or update this document with
the merged spec RID + Gridkin scenario path) so the consumer-side migration
can pick up cleanly. The consumer-side change is small — one Gryphon Search
replacing one ORM filter call in `enrichment.py` — and shouldn't need any
back-and-forth once the operator is available.
