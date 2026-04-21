---
name: new-plugin
description: Scaffold a new TAP plugin with manifest, models, edges, tests, specs, icons, and README. Use when creating a new plugin from scratch.
disable-model-invocation: true
allowed-tools: Read Write Edit Bash(git *) Bash(gh *) Bash(mkdir *) Bash(ls *) Glob Grep
argument-hint: <slug> <display-name>
---

# Scaffold a New TAP Plugin

You are creating a new TAP plugin. TAP plugins may be developed as standalone git repositories and later integrated into TAP as submodules, but the plugin's TAP contract should stay valid regardless of when that publishing shape is used.

## How TAP Specifications Work

TAP uses a spec-first development process. Specifications live in `specs/` directories throughout the codebase and are the authoritative source for how things work. Each spec contains requirements with RIDs (requirement IDs), acceptance criteria, and implementation details.

When you are unsure how something works — models, edges, manifests, icons, validation, GRIFT — read the relevant spec. Do not guess or rely on patterns you've seen elsewhere.

**Key specs to read before starting:**

- `tap_plugins/specs/spec-plugin-architecture.md` — plugin structure, repo conventions, skills, package layout
- `tap_plugins/specs/spec-plugin-manifest-v0.md` — manifest format and validation rules
- `tap_grid/specs/spec-grid-entity.md` — BaseModel contract, dual schema requirement, field validation, known constraints
- `tap_grid/specs/spec-grid-icon.md` — icon key format, SVG requirements, vendor brand colors
- `tap_grid/specs/spec-grift-v0.md` — GRIFT interchange format for seed data

**Key schemas:**

- `tap_grid/schemas/grift-document.schema.json` — machine-readable GRIFT document schema
- `tap_grid/schemas/edge-definition.schema.json` — machine-readable edge definition schema
- `tap_plugins/validate/plugin-validation-result.schema.json` — validation output schema

If a spec seems incomplete or contradicts what you see in code, flag it to the user rather than silently working around it.

## Step 1: Establish Names And Defaults

Before drafting the full spec, collaborate with the user on the naming and dimension conventions for the plugin. This reduces churn later.

If $ARGUMENTS provides a slug and display name, use those. Otherwise ask.

Gather from the user:

1. **Plugin slug** — used as manifest `slug`, Django app label, directory name
2. **Display name** — human-readable name for the manifest `name` field
3. **Description** — one-line description
4. **Default dimensions convention** — what dimension key/value should all TAP-managed entities and edges use?
5. **Naming strategy** — proposed model/type slugs, edge slugs, icon keys, and GRIFT bundle names
6. **GitHub repo name and org** — where the repo will be created, if the standalone-repo/submodule shape will be used

Default dimensions are required for new plugin work unless the user explicitly changes that requirement. In general, dimension-less TAP-managed types should be treated as a design bug to justify rather than a default to accept silently.

## Step 2: Create GitHub Repo Early

Once the plugin slug, display name, description, and repo metadata are stable enough, create the GitHub repository early rather than waiting until the end. This lets the plugin author push partial specification work even if implementation is not finished yet.

If the standalone-repo/submodule shape is being used:

```bash
cd plugins/<slug>
git init
gh repo create <org>/<repo-name> --private --description "<description>"
git remote add origin <repo-url>
```

If the plugin directory does not exist yet, create it first with the minimal package skeleton or initialize the repository at the intended plugin root before continuing.

Do not wait for the full plugin scaffold to exist before creating the remote. Early publication of partial spec work is an intended workflow.

## Step 3: Write the Specification

Before writing any code, collaborate with the user to write the plugin specification. This is the most important step — the spec drives everything that follows.

Gather from the user:

1. **Domain** — what resource types, relationships, and reference data does this plugin model?
2. **Default dimensions** — confirm the convention from step 1
3. **Naming strategy** — confirm the naming set from step 1 before drafting the final spec
4. **GitHub repo name and org** — confirm whether the standalone-repo/submodule shape will be used now or later

Write `specs/spec-<slug>-v0.md` following TAP's spec format. Read existing specs in `tap_grid/specs/` and `tap_plugins/specs/` for the format, tone, and structure. The spec should cover:

- Philosophy — why this plugin exists, what domain it models
- Goals
- Requirements table with RIDs and statuses (initially Proposed)
- Model catalog — what models, organized by category, with rationale
- Edge types — what relationships, organized by category
- Reference data — what GRIFT seed data, if any
- Icons — what the icon approach will be
- Non-goals — what's explicitly deferred
- Future work

Bias toward durable primitives. If a proposed model or edge feels speculative, unstable, or too domain-specific for the plugin's stated scope, flag it and move it to non-goals or future work instead of forcing it into v0.

Go back and forth with the user until the spec is agreed. Update requirement statuses to Implemented as you build each piece.

## Step 4: Create Plugin Directory and Core Files

Create the directory at `plugins/<slug>/`. Read `tap_plugins/specs/spec-plugin-architecture.md` for the full package layout requirements — do not hardcode the directory list here.

The core files every plugin needs:

- `__init__.py` — package marker, docstring only
- `apps.py` — single `TapPluginConfig` subclass, body is `pass`, no explicit `name`/`label`/`verbose_name`
- `tap-plugin.toml` — manifest per `spec-plugin-manifest-v0.md`
- `migrations/__init__.py` — empty
- `tests/__init__.py` — empty

## Step 5: Create Models

Read `tap_grid/specs/spec-grid-entity.md` for the full BaseModel contract. It covers:

- Required class variables (`ENTITY_TYPE`, `ENTITY_NAME`, `ENTITY_DESCRIPTION`, `ENTITY_ICON`, `DEFAULT_DIMENSIONS`, `FIELD_CRUD_SCHEMA`, `FIELD_VALIDATION_SCHEMA`, `CREATE_REQUIRED`)
- The dual schema requirement and the difference between `FIELD_CRUD_SCHEMA` and `FIELD_VALIDATION_SCHEMA`
- Nullable field handling
- Known field name collisions (e.g. `instance_type` is reserved by django-simple-history)

Create one file per model in `models/` and a `models/__init__.py` that re-exports all classes.

## Step 6: Create Edge Definitions

Read `tap_plugins/specs/spec-plugin-manifest-v0.md` for the edge file format. Validate edge files against `tap_grid/schemas/edge-definition.schema.json`.

Create one `.edge.json` file per edge type in `edges/`. Include `default_dimensions` matching the convention agreed in step 1.

## Step 7: Create GRIFT Seed Data (if applicable)

If the plugin includes reference data that should be pre-loaded, create GRIFT files in `grift/`.

Read `tap_grid/specs/spec-grift-v0.md` for the format. Validate against `tap_grid/schemas/grift-document.schema.json`.

Use deterministic entity IDs where repeated imports should upsert cleanly. If the repo does not yet have an approved pattern for the plugin, flag that gap rather than inventing an unstable ID scheme silently.

## Step 8: Create Icons

Read `tap_grid/specs/spec-grid-icon.md` for the full icon contract.

Icons are optional but strongly encouraged. If the user hasn't specified icon requirements, ask them:

- Should icons use vendor brand colors (e.g. official AWS/GCP icons) or TAP's `currentColor` convention?
- Are there official icon assets available for this domain?
- Which models should share icon keys?

Every model that declares `ENTITY_ICON` must have a corresponding SVG at `static/<slug>/icons/<icon-key>.svg`. Icon keys must be kebab-case.

## Step 9: Create Tests

Create `tests/test_<slug>_manifest.py` for plugin validation system tests:

```python
from pathlib import Path
import pytest
from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

class TestStructure:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()
```

Note: `loads` and `runs` level tests require the plugin to be in `INSTALLED_APPS`. Structure-level tests work standalone.

Create additional test files for domain-specific behavior. Name test files after what they test — `test_<slug>_edges.py`, `test_<slug>_defaults.py`, etc. — not always `_models.py`.

Do not re-implement structural or smoke tests that the centralized plugin validation system already covers.

## Step 10: Validate

Run structural validation to confirm the scaffold is correct:

```bash
python -m tap_plugins.validate_plugin plugins/<slug>
```

This runs without Django and confirms manifest, paths, edge files, and directory structure. Fix any failures before proceeding.

Before making the plugin public, strongly recommend that the author also run the future `loads` and `runs` validation levels once those capabilities are available and the plugin is integrated into a real TAP installation.

Remember that structure-level validation confirms manifest, import, and path correctness, but it does not yet prove that plugin-backed database tables or migration state are present.

## Step 11: Create README.md

Write a concise README for the plugin repo covering:

- What the plugin does (1-2 sentences)
- Resource types modeled (organized by category)
- Edge types
- How to install (`git submodule add`, `INSTALLED_APPS`, `migrate`)
- How to validate (`python manage.py validate_plugin plugins/<slug> --level runs`)
- Pointer to `specs/` for detailed documentation

## Step 12: Commit And Push Progress

```bash
cd plugins/<slug>
git add .
git commit -m "Initial <Display Name> plugin"
git push -u origin main
```

Then add as submodule from the TAP repo root:

```bash
git submodule add <repo-url> plugins/<slug>
```

Do NOT add the plugin to `INSTALLED_APPS`. The plugin author does that when they're ready to integrate, and the validation system confirms correctness.

This step is intentionally late in the workflow, but the author may commit and push partial progress earlier, especially once the initial spec exists.

## Step 13: Update Specification

Go back to the spec and update all requirement statuses to reflect what was implemented. The spec must stay in sync with the code — spec drift is a bug.
