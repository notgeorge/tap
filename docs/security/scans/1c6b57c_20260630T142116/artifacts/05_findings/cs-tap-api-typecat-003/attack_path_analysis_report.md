# Attack Path Analysis: Entity type catalog API ignores grid.read for authenticated no-cap users

Severity: low
Confidence: high

Attack path:

1. Attacker logs in as a capless user.
2. Attacker requests /api/v1/entity-types/.
3. Response enumerates registered entity types and plugin names despite missing grid.read.

Why the existing controls did not stop it:

Read-only type metadata was treated as harmless API catalog data and missed the auth spec requirement that every graph read, including API read endpoints, requires grid.read.

Recommended fix:

Authorize grid.read in list_entity_types before querying EntityType, or route the catalog through a gated read service. Add no-cap tests for /api/v1/entity-types/ mirroring the existing /api/v1/entities/ denial tests.
