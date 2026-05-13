---
name: refresh-aws-catalog
description: Refresh the AWS Core plugin's catalog data (regions, AZs, icons) by searching current AWS documentation, updating GRIFT seed data and icon assets, and validating the result. Use when AWS infrastructure data needs updating.
disable-model-invocation: true
allowed-tools: WebSearch WebFetch Read Write Edit Bash(docker *) Bash(python *) Glob Grep
argument-hint: [--dry-run]
---

# Refresh AWS Catalog

You are updating the TAP AWS Core plugin's reference data by gathering current information from AWS and writing it into the plugin's GRIFT seed files.

The plugin lives in its own directory (currently at `plugins/aws_core/` during development, eventually its own git repo). All paths in this skill are relative to the plugin root.

## Current Scope

**In scope:** AWS regions, availability zones, and entity type icons.
**Deferred:** Service/resource type catalog, live account queries.

## Incremental Update Strategy

This skill runs periodically (nightly in CI). It must detect changes since the last run rather than blindly regenerating everything.

1. **Check file modification dates** on the existing GRIFT file to understand when it was last updated.
2. **Search for changes** — focus web searches on what's new/changed since the last update date. Look for newly launched regions, new AZs, or deprecated/removed regions.
3. **Preserve existing data** — never remove a region or AZ unless you find an authoritative AWS source (official AWS documentation or announcement) explicitly declaring it deprecated or removed. Missing it from a search result is NOT sufficient evidence for removal.
4. **Add new entries** — new regions and AZs get new deterministic entity IDs following the existing convention.

### Deprecation Policy

**DO NOT remove any region, AZ, service, or model** unless:
- An official AWS page or announcement explicitly declares it deprecated/removed
- You can cite the source URL

If you cannot find a resource in current docs but have no deprecation notice, keep it and add a warning comment to your summary.

## Step 1: Read Current Plugin State

Read the existing GRIFT file at `grift/regions.grift.json` (relative to plugin root) to understand:
- What regions and AZs already exist (match by `region_code` / zone name)
- The entity ID convention being used
- When the file was last modified

## Step 2: Gather Current AWS Data

Search the web for the current list of AWS regions and their availability zones.

For each **region**, collect:
- Region code (e.g. `us-east-1`)
- Display name (e.g. `US East (N. Virginia)`)
- Geographic area (e.g. `North America`, `Europe`, `Asia Pacific`, `South America`, `Middle East`, `Africa`)

For each **availability zone**, collect:
- Zone name (e.g. `us-east-1a`)
- Zone ID if available (e.g. `use1-az1`)
- Parent region

Exclude GovCloud and China partition regions unless they appear in standard commercial AWS documentation.

## Step 3: Update GRIFT Seed Data

Update `grift/regions.grift.json` with the complete set of regions, AZs, and CONTAINS edges.

### Format Reference

The GRIFT document format is defined by the JSON Schema at `tap_grid/schemas/grift-document.schema.json` and specified in `tap_grid/specs/spec-grift-v0.md`. Read those files for the authoritative format — do not rely on format knowledge embedded in this skill.

### Entity ID Convention

Use deterministic UUIDs so that repeated runs produce the same IDs (enabling GRIFT upsert):
- Batch: `019dd143-3e8f-73e4-b0fa-e52ee20fda3d`
- Regions: `01965b00-1000-7000-8000-` followed by 12-char hex (increment from `000000000001`)
- AZs: `01965b00-2000-7000-8000-` followed by 12-char hex (increment)
- Edges (region CONTAINS AZ): `01965b00-3000-7000-8000-` followed by 12-char hex (increment)

**Preserve existing entity IDs** for regions/AZs that already exist. Only assign new IDs for newly discovered items. Assign new IDs by continuing the incrementing sequence from the highest existing ID in each range.

### Ordering

- Sort regions by `region_code`
- Group AZs under their parent region, sorted by zone name
- Edges follow node order

## Step 4: Update Icons

Each entity type in the plugin declares an `ENTITY_ICON` kebab-case key. Icons are SVG files stored at:

```
static/aws_core/icons/<icon-key>.svg
```

The icon specification is at `tap_grid/specs/spec-grid-icon.md` and the resolver is at `tap_grid/icon.py`. Read those for the authoritative contract.

### Icon Requirements

- Format: SVG only
- Use official AWS Architecture Icons with their native brand colors — do NOT convert to `currentColor`
- Only rename files to match the kebab-case icon key convention
- The rendering pipeline treats SVGs as image assets so multi-color icons work correctly

### Icon Sources

Icons must come from the official AWS Architecture Icons asset pack published at `https://aws.amazon.com/architecture/icons/`. Do not use third-party mirrors or recreations.

1. Download the official AWS Architecture Icons pack
2. Locate the SVG for each service (typically under the service category folders)
3. Rename to match the kebab-case icon key (e.g. `Arch_Amazon-EC2_64.svg` becomes `aws-ec2.svg`)
4. For infrastructure concepts (region, AZ, account) that don't have a dedicated service icon, use the closest match from the AWS icon set (e.g. AWS Global Infrastructure category)

### Icon Inventory

1. Read all `ENTITY_ICON` values from the model files in `models/`
2. Check which SVGs already exist in `static/aws_core/icons/`
3. Create or update any missing icons
4. Multiple models may share an icon key (e.g. `aws-iam` for user, role, and policy)

### Deduplication

Several models share icon keys:
- `aws-ecs` → EcsCluster, EcsService, EcsTask
- `aws-iam` → IamUser, IamRole, IamPolicy
- `aws-vpc` → Vpc, Subnet

Only one SVG file per unique icon key is needed.

## Step 5: Validate

Validate the GRIFT file against the JSON Schema:

```bash
docker compose exec web uv run python -c "
import json, jsonschema
from pathlib import Path
schema = json.loads(Path('tap_grid/schemas/grift-document.schema.json').read_text())
doc = json.loads(Path('plugins/aws_core/grift/regions.grift.json').read_text())
jsonschema.validate(doc, schema)
print('Schema validation passed')
"
```

Then run the plugin validator:

```bash
docker compose exec web uv run python manage.py validate_plugin plugins/aws_core --level runs
```

Both must pass. If either fails, diagnose and fix before completing.

## Step 6: Report

Summarize what changed:
- Regions added / removed / unchanged (with count)
- AZs added / removed / unchanged (with count)
- Total entity counts
- Any items that could not be confirmed (kept but flagged)
- Source URLs consulted

If `--dry-run` was passed as an argument ($ARGUMENTS contains "--dry-run"), report what would change without writing any files.
