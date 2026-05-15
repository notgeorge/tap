---
name: add-edge
description: Add a new TAP edge type to a plugin. Use when introducing a new relationship between entity types (e.g. HAS_EVIDENCE from finding to evidence).
allowed-tools: Read Write Edit Bash(scripts/dc *) Bash(grep *) Bash(find *) Bash(ls *) Glob Grep
argument-hint: <plugin_slug> <EDGE_SLUG>
---

# Add a New Edge Type

You are introducing a new edge type that connects two entity types in the TAP graph. The edge becomes a first-class type that GRIFT can seed, the service layer can create/replace/delete, and queries (gryphon, hotlink) can traverse.

## Authoritative Sources (read these first; do not guess from memory)

- **[`tap_grid/specs/spec-grid-edge.md`](../../specs/spec-grid-edge.md)** — Edge model, type system, source/target enforcement, dimensions on edges.
- **[`tap_grid/schemas/edge-definition.schema.json`](../../schemas/edge-definition.schema.json)** — JSON Schema for `.edge.json` files. Validate against this.
- **[`tap_plugins/specs/spec-plugin-manifest-v0.md`](../../../tap_plugins/specs/spec-plugin-manifest-v0.md)** — manifest registration of edge types.
- **[`tap_grid/specs/spec-grid-hotlink.md`](../../specs/spec-grid-hotlink.md)** — read this if the edge is the materialization of a JSON reference inside a hotlink-bearing field.
- **[`tap_grid/specs/spec-grid-service-write.md`](../../specs/spec-grid-service-write.md)** — `create_edge` / `replace_edge` semantics, idempotency, dimension defaults.

If a spec contradicts a pattern in code, flag it to the user — do not silently work around it.

## Step 1: Confirm the Shape With the User

Before authoring the edge file, gather:

1. **Plugin slug** the edge belongs to (e.g. `fedramp_20x_ksi`).
2. **Edge slug** (`SCREAMING_SNAKE_CASE`, e.g. `HAS_EVIDENCE`). The slug is the canonical edge type — used in service-layer calls, GRIFT, and gryphon queries. Edge slugs should be compact semantic predicates that help `source node + edge + target node` read like a coherent sentence.
3. **Human-readable name** and **description** (one or two sentences explaining what the edge represents and when to use it).
4. **`sources` and `targets`** — list the entity-type slugs allowed at each end. Wildcard (`omit`) is permitted but should be justified; explicit lists are strongly preferred for typed plugins.
5. **`property_schema`** (optional) — JSON Schema for structured edge properties. Use this when the edge carries semantically meaningful data (e.g. an enum that classifies the relationship). The user's case for adding a `support_kind` enum here is a textbook example.
6. **`default_dimensions`** — what dimensions does every new edge of this type carry? Edges should match the dimension convention of their participating entities. Dimension-less edges, like dimension-less nodes, are a design red flag.
7. **Hotlink integration** — is this edge the materialization of a JSON reference on a model? If yes, plan the `HOTLINKS` declaration on the model alongside the edge.

Write down the agreed shape before generating the file; it becomes the spec section in Step 5.

### Edge naming checklist

Default to compact, semantically rich predicate names. Avoid bare generic verbs like `USES`, `RUNS`, `HAS`, `ROUTES`, `STORES`, or `PULLS` when the relationship has an obvious missing object. Add the missing noun inside the predicate instead:

- Prefer `STORES_DATA_IN` over `STORES_IN`.
- Prefer `ROUTES_TRAFFIC_TO` over `ROUTES_TO`.
- Prefer `PULLS_IMAGE_FROM` over `PULLS_FROM`.
- Prefer `HAS_POLICY_ACCESS_TO` over `HAS_ACCESS_TO`.
- Prefer `ASSUMES_ROLE` over `ASSUMES`.

Do not overfit by repeating both endpoint type names unless the relation would otherwise be ambiguous. For example, `VPC_CONTAINS_SUBNET` may be warranted when distinguishing it from other containment semantics, but `CONTAINS` can still be acceptable for strict hierarchy when the endpoints already supply the needed nouns. The goal is for `source node + edge + target node` to be close to a useful sentence without turning every edge slug into a paragraph. Future semantic templates and predicate metadata may carry fuller natural-language phrasing; the slug should remain concise and meaningful.

### Property schema design checklist

When the edge carries an enum (e.g. `support_kind: passing | violation | informational`), confirm with the user:

- **Required vs. optional?** If the edge has no useful default, list it under `required`.
- **`additionalProperties: false`?** Default to true (yes, forbid extras). New properties should be explicit additions, not silent expansions.
- **Vocabulary alignment** with sibling enums elsewhere in the plugin (e.g. don't use `passing` here if the rest of the plugin uses `compliant`).

## Step 2: Author the `.edge.json` File

Create `<plugin>/edges/<EDGE_SLUG>.edge.json` matching `edge-definition.schema.json`:

```json
{
  "slug": "<EDGE_SLUG>",
  "name": "<Human Name>",
  "description": "<Sentence explaining what the edge represents.>",
  "sources": ["<source_entity_type>"],
  "targets": ["<target_entity_type>"],
  "property_schema": {
    "type": "object",
    "required": ["<key>"],
    "additionalProperties": false,
    "properties": {
      "<key>": {"type": "string", "enum": ["<v1>", "<v2>"]}
    }
  },
  "default_dimensions": {
    "<dim_key>": "<dim_value>"
  }
}
```

### Field rules (per `edge-definition.schema.json`)

- `slug`, `name`, `description` are required and must be non-empty.
- `slug` **must** equal both the filename (minus `.edge.json`) and the manifest key.
- `sources` and `targets` are arrays of entity-type slugs; omit either to allow wildcard at that end.
- `property_schema` is a JSON Schema object; the service layer validates edge properties against it on create/update.
- `default_dimensions` is a flat string-to-string map applied at edge creation when the caller doesn't specify dimensions.

## Step 3: Register in the Plugin Manifest

Edit `<plugin>/tap-plugin.toml`. Under `[edges]`, add the edge:

```toml
[edges]
<EDGE_SLUG> = "edges/<EDGE_SLUG>.edge.json"
```

The manifest key on the left **must** equal the edge file's `slug`. Any mismatch surfaces as a manifest validation error.

## Step 4: Validate and Smoke-Test

Validate the manifest and edge files:

```bash
scripts/dc exec web uv run python manage.py validate_plugin <plugin> --level structure
```

Then smoke-test creating an edge of the new type via the service layer (Django shell or a test):

```python
from tap_grid.services import create_edge
from tap_grid.caller_context import CallerContext

ctx = CallerContext()
edge = create_edge(
    from_target="<source_entity_id>",
    to_target="<target_entity_id>",
    edge_type="<EDGE_SLUG>",
    payload={"properties": {"<key>": "<value>"}},
    caller_context=ctx,
)
```

Confirm:

- Sources / targets that violate the type's declared `sources`/`targets` are rejected with a clear error.
- Properties outside the `property_schema` are rejected.
- `default_dimensions` are applied when the caller omits dimensions.

## Step 5: Update or Add the Spec

Edges, like models, must be spec-driven. Either:

- Add a new requirement to an existing plugin spec, OR
- Add an "Edge Types" subsection that documents the new edge alongside its peers.

The requirement should cover:

- Sources / targets the edge accepts.
- Property schema (especially any enums that drive validation logic).
- Default dimensions.
- Whether the edge is hotlink-bearing (and which model owns the hotlink).
- Status: `In Development` → `Implemented` after Step 7 passes.

If the edge replaces or supersedes an existing edge type, update the deprecated edge's requirement and add a migration note.

## Step 6: Author GRIFT Seed Data (if applicable)

If the plugin needs reference data using this edge type, add edges in a GRIFT bundle. Read [`tap_grid/specs/spec-grift-v0.md`](../../specs/spec-grift-v0.md) for format and idempotency rules.

GRIFT envelope shape for an edge:

```json
{
  "entity": {
    "entity_id": "<uuidv7>",
    "entity_type": "edge",
    "name": "<source label> <EDGE_SLUG> <target label>",
    "dimensions": {"<dim>": "<value>"}
  },
  "edge": {
    "from_entity_id": "<source-uuid>",
    "to_entity_id": "<target-uuid>",
    "edge_type": "<EDGE_SLUG>",
    "properties": {"<key>": "<value>"}
  }
}
```

UUIDv7 batch / entity / edge ids should come from `scripts/uuid7`. Iteration follows the canonical paths in [`tap_plugins/specs/spec-plugin-architecture.md`](../../../tap_plugins/specs/spec-plugin-architecture.md) (`req-plugin-arch-iterative-dev`): version-bump for shipping, `--force-batches` for dev iteration only.

## Step 7: Tests

Add tests that exercise the edge through the service layer:

- **Type acceptance**: edges with allowed source/target types are created successfully.
- **Type rejection**: edges with disallowed source/target types are rejected with a clear error.
- **Property schema**: required properties are enforced; unknown properties are rejected.
- **Default dimensions**: applied when caller doesn't override.
- **Idempotency**: GRIFT re-import of an edge with the same `entity_id` is a no-op (per the importer contract).

Place tests in `<plugin>/tests/test_<edge_slug>.py` or a more general edge-suite test file when adding many at once.

## Step 8: Verify and Sync

```bash
# Run the edge tests.
scripts/dc exec web uv run pytest <plugin>/tests/test_<edge_slug>.py -v

# Run the plugin manifest test.
scripts/dc exec web uv run pytest <plugin>/tests/test_<plugin>_manifest.py -v

# Re-import GRIFT if you added seed data.
scripts/dc exec web uv run python manage.py import_plugin_grift <plugin>
```

Once green:

- Flip the spec requirement Status from `In Development` → `Implemented`.
- Update the spec's requirement-status table.
- If docs reference any RIDs you changed, follow the doc-spec sync rules in [`specs/spec-docs.md`](../../../specs/spec-docs.md).

## Common Mistakes (do not commit any of these)

- **Slug case mismatch.** The edge slug, filename, and manifest key must match exactly. `Has_Evidence` ≠ `HAS_EVIDENCE`.
- **`additionalProperties: true` (or omitted) on `property_schema`.** Default to `false`. Silent property growth makes the edge type's contract unstable.
- **Bare generic edge slugs.** Names like `USES`, `RUNS`, `HAS`, `ROUTES`, `STORES`, or `PULLS` usually need a semantic noun in the predicate (`USES_SEARCH`, `ROUTES_TRAFFIC_TO`, `STORES_DATA_IN`, `PULLS_IMAGE_FROM`) so graph triples read coherently.
- **Wildcard sources/targets without justification.** Typed plugins should constrain edge endpoints. Wildcards are appropriate for cross-plugin edges (e.g. `HAS_FINDING` from any asset to a finding), but they should be a deliberate choice, not the default.
- **Forgetting `default_dimensions`.** Edges should carry the same dimension convention as their endpoints; missing dimensions cause silent scoping bugs later.
- **Authoring GRIFT edges without a UUIDv7.** Use `scripts/uuid7`; never hand-shape edge entity_ids.
- **Skipping the hotlink declaration** when the edge is the materialization of a JSON reference. Without it, the JSON and the edge set will drift.
