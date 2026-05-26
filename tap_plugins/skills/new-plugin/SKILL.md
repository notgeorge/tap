---
name: new-plugin
description: Scaffold a new TAP plugin with manifest, models, edges, tests, specs, icons, and docs. Supports both from-scratch authoring and spec-first graduation from a pre-authored planning doc.
disable-model-invocation: true
allowed-tools: Read Write Edit Bash(git *) Bash(gh *) Bash(mkdir *) Bash(mv *) Bash(ls *) Glob Grep
argument-hint: <slug> <display-name>  |  --from-spec <path>
---

# Scaffold a New TAP Plugin

> **Skill source-of-truth.** This SKILL.md's canonical location is `tap_plugins/skills/new-plugin/SKILL.md`. The `.claude/skills/new-plugin/` path is a directory-level symlink — edit the canonical, the symlink follows. Same pattern holds for the other plugin-tooling skills (`add-model`, `add-edge`, `add-page`, `add-panel`): canonical lives under the owning package's `skills/` directory.

You are creating a new TAP plugin. TAP plugins may be developed as standalone git repositories and later integrated into TAP as submodules, but the plugin's TAP contract should stay valid regardless of when that publishing shape is used.

## Operating Modes

This skill supports two entry modes; the work in Steps 1 and 3 differs based on which one applies. Every other step is identical.

**From-scratch mode.** No pre-authored spec exists. The skill collaborates with the user to draft the spec from zero (the original path).

**Spec-first mode.** A planning doc has already been authored — typically in another LLM session — at `docs/misc/preplugin-<slug>-v?.md`, or at a path the user passes via `--from-spec`. The skill reviews the doc, asks bounded clarifying questions, normalizes it into canonical spec shape, and graduates it (via `mv`) into `plugins/<slug>/specs/spec-<slug>-v0.md`.

### Detect the mode

Resolution order:

1. If `$ARGUMENTS` includes `--from-spec <path>`, that's spec-first mode with the named path.
2. Otherwise, once a slug is known (from `$ARGUMENTS` or just-asked), check `docs/misc/preplugin-<slug>-v?.md`. If exactly one match exists, that's spec-first mode. If multiple, ask which.
3. Otherwise, from-scratch mode.

Confirm the detected mode with the user in one sentence before proceeding.

## How TAP Specifications Work

TAP uses a spec-first development process. Specifications live in `specs/` directories throughout the codebase and are the authoritative source for how things work. Each spec contains requirements with RIDs (requirement IDs), acceptance criteria, and implementation details.

When you are unsure how something works — models, edges, manifests, icons, validation, GRIFT — read the relevant spec. Do not guess or rely on patterns you've seen elsewhere.

**Key specs to read before starting (plugin-scaffolding scope):**

- `tap_plugins/specs/spec-plugin-architecture.md` — plugin structure, repo conventions, skills, package layout
- `tap_plugins/specs/spec-plugin-manifest-v0.md` — manifest format and validation rules
- `tap_grid/specs/spec-grid-icon.md` — icon key format, SVG requirements, vendor brand colors
- `tap_grid/specs/spec-grift-v0.md` — GRIFT interchange format for seed data

**Key schemas:**

- `tap_grid/schemas/grift-document.schema.json` — machine-readable GRIFT document schema
- `tap_plugins/validate/plugin-validation-result.schema.json` — validation output schema

For per-model and per-edge work, the [`add-model`](../../../tap_grid/skills/add-model/SKILL.md) and [`add-edge`](../../../tap_grid/skills/add-edge/SKILL.md) skills carry the canonical spec pointers (BaseModel contract, edge-definition schema, hotlinks, history). Don't duplicate that material here — defer to those skills in Steps 5 and 6.

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

Default dimensions are required **when the plugin contributes TAP-managed entities** (models or edges). If the plugin's Plugin Scope explicitly excludes TAP-managed entities — e.g., a panel-only, presentation-only, or pure-helper plugin — default dimensions are N/A; note the carve-out once and do not require a value. Otherwise, dimension-less TAP-managed types should be treated as a design bug to justify rather than a default to accept silently.

**In spec-first mode**, slug + display name come from the spec's `## Plugin Identity` section (see Step 3). Default dimensions, naming strategy, and GitHub repo metadata may or may not be answered in the spec — the Step 3 review pass identifies the gaps and asks for them in one bounded batch rather than re-eliciting answers the spec already contains.

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

## Step 3: Write or Graduate the Specification

Before writing any code, ensure a settled plugin specification exists at `plugins/<slug>/specs/spec-<slug>-v0.md`. The spec drives everything that follows — this is the most important step.

### Canonical Spec Shape

The required sections of a graduated TAP plugin spec:

- `## Plugin Identity` — slug, display name, and key initial entry points (e.g. initial page route, initial panel type slug, initial page variables). This is the "what is this plugin called and where does it land" header that anyone graduating the spec wants to read first. Required on every plugin spec; do not invent ad-hoc top metadata blocks in lieu of this section.
- `## Philosophy` — why this plugin exists, what domain it models, what's deliberately in vs. out of scope
- `## Goals` — numbered table: `| # | Name | Description |`
- `## Requirements` — top-level table: `| RID | Name | Status | Notes |`
- Per-requirement section: `### <Name>` heading, `----` divider, `RID: \`req-<slug>-<noun>\``, `Status: \`<Proposed|Implemented|Backlog>\``, descriptive body, optional `#### Implementation` body, and an `#### Acceptance Criteria` table (`| ACID | Title | Status | Description | Notes |`)
- Model catalog (if applicable) — what models, organized by category, with rationale
- Edge types (if applicable) — what relationships, organized by category
- Reference data (if applicable) — what GRIFT seed data
- Icons (if applicable) — what the icon approach will be
- Non-goals — encoded either as a tail `### v0 Non-Goals` requirement (e.g. `req-<slug>-nongoals`) or as `Backlog`-status requirements; pick one and apply consistently within the spec

Read existing graduated specs for format/tone — strong references: `plugins/aws_core/specs/spec-aws-core-v0.md`, `plugins/samsite/specs/spec-samsite-compliance-collector-v0.md`, `plugins/gryphon_playground/specs/spec-gridkin-v0.md`.

### From-Scratch Variant

Collaborate with the user to draft the spec from zero. Gather:

1. **Domain** — what resource types, relationships, and reference data does this plugin model?
2. **Default dimensions** — confirm the convention from Step 1 (skip if the plugin contributes no TAP-managed entities)
3. **Naming strategy** — confirm the naming set from Step 1 before drafting
4. **GitHub repo name and org** — confirm whether the standalone-repo/submodule shape will be used now or later

Bias toward durable primitives. If a proposed model or edge feels speculative, unstable, or too domain-specific for the plugin's stated scope, flag it and move it to non-goals or future work instead of forcing it into v0.

Go back and forth with the user until the spec is agreed.

### Spec-First Variant

A pre-authored planning doc exists at `docs/misc/preplugin-<slug>-v?.md` (or the `--from-spec` path). Treat it as the source of truth and do not re-draft from scratch. The work here is **review → clarify → normalize → graduate**, in that order.

#### Review Checklist

Run every item; report findings in one summary before asking anything.

| # | Check | What "fail" looks like |
| :---: | --- | --- |
| a | **Required sections present.** All sections in the Canonical Spec Shape above. Specifically check whether a `## Plugin Identity` section exists, or whether the doc has an ad-hoc top metadata block to convert. | Missing Philosophy, Goals, Requirements table, or per-req sections; ad-hoc top metadata block in lieu of `## Plugin Identity` |
| b | **RIDs well-formed.** Unique within the spec, kebab-case, prefixed `req-<slug>-`. | Duplicates, missing prefix, non-kebab-case |
| c | **ACIDs well-formed.** Unique under each RID, kebab-case, prefixed with the RID (e.g. `req-roscale-v0-scope-1`). | Duplicates within a requirement, missing or wrong prefix |
| d | **Statuses valid.** Every Status ∈ `{Proposed, Implemented, Backlog}`. | Non-canonical statuses like `Pre-Plugin Planning`, `Draft`, etc. |
| e | **Step 1 + Step 3 questions answered.** Slug, display name, description, scope, naming strategy, default dimensions (only if Step 1's conditional applies), GitHub repo metadata. | Any of these missing or vague enough to need user input |
| f | **Known Codex-shaped artifacts flagged for normalization.** | See list below |
| g | **Spec quality smell-tests.** Are requirements concrete? ACs testable? Contradictions, undefined terms, ambiguous scope language? | Any "we'll figure it out" hand-waving in normative sections |

Known Codex-shaped artifacts (item f) and their normalizations:

- `# <Name> v0 Pre-Plugin Plan`-style title → rename to `# <Name> Plugin Specification` (or domain-appropriate canonical title)
- Top-level `Status: Pre-Plugin Planning` line under the title → drop. Status lives per-requirement, not at the document level.
- Top metadata block (slug / display name / initial page / initial panel / initial variable laid out as key/value pairs at the top) → convert to a proper `## Plugin Identity` section.
- `## Strategic Check` section (path alignment, scope risk, defer list, recommendation) → drop. Pure planning artifact; not part of a settled spec. Optionally archive separately under `docs/misc/decision-*.md` if the rationale is worth keeping.
- `## Initial Implementation Outline` section (numbered list of "first slice" steps) → drop. This skill IS the implementation outline; Steps 4–13 below cover it.
- `## Open Questions For Implementation` tail bucket → fold each open question into the relevant requirement's `Notes` column on the Requirements table, or into a per-requirement note inside the requirement body. Open questions belong adjacent to the requirement they affect, not in a tail bucket.
- `## Prior Art And Source Boundaries` as a top-level section → consider folding into the most-relevant requirement (e.g., a Vendored Assets requirement). Keep the substance; lose the top-level slot if the content only justifies a single requirement.

#### Clarifying-Question Protocol

Where the checklist finds genuine gaps, ask in **one bounded batch** via `AskUserQuestion` — at most 4 questions per batch. Only open a second batch if the first batch's answers reveal new gaps that weren't visible before. Avoid 20-question chains; if many gaps exist, surface that as "this spec needs more work before graduation" and stop, rather than power through with a long elicitation.

#### Normalize

Apply the checklist findings to the doc in place. Then show the normalized result to the user and get one round of approval before graduation. Do not graduate on assumed approval.

#### Graduate

```bash
mkdir -p plugins/<slug>/specs
mv docs/misc/preplugin-<slug>-v0.md plugins/<slug>/specs/spec-<slug>-v0.md
```

`mv` clean — the planning doc is replaced; history lives in git. Do not leave a redirect stub at the old path; stubs rot.

Confirm the file is in its new location before proceeding to Step 4.

---

After either variant, update requirement statuses to `Implemented` as you build each piece. Spec drift is a bug — keep statuses in sync with code as the work proceeds.

## Step 4: Create Plugin Directory and Core Files

Create the directory at `plugins/<slug>/`. Read `tap_plugins/specs/spec-plugin-architecture.md` for the full package layout requirements — do not hardcode the directory list here.

The core files every plugin needs:

- `__init__.py` — package marker, docstring only
- `apps.py` — single `TapPluginConfig` subclass, body is `pass`, no explicit `name`/`label`/`verbose_name`
- `tap-plugin.toml` — manifest per `spec-plugin-manifest-v0.md`
- `README.md` — plugin-local developer and AI-agent orientation notes that travel with the plugin
- `docs/` — setup guides, runbooks, inventories, and deeper operational/design notes
- `migrations/__init__.py` — empty
- `tests/__init__.py` — empty
- `.gitignore` — if the plugin will be its own git repo (the standalone-repo/submodule shape from Step 2), create one to keep Python bytecode and tooling caches out of the index. Plugin repos do not inherit the TAP repo's top-level `.gitignore`. Skip this step only if `.gitignore` is already tracked. Minimum recommended contents:

  ```gitignore
  __pycache__/
  *.pyc
  *.pyo
  .pytest_cache/
  .mypy_cache/
  .ruff_cache/
  ```

  Without this, the first `git add -A` after running tests or migrations will quietly pull dozens of `.pyc` files into a commit.

Create root `README.md` as soon as the plugin directory exists. This file is not marketing copy. It is the durable context page for future developers and AI agents working inside the plugin, especially after the plugin is split into its own repository or submodule. At minimum include:

- what this plugin owns
- what nearby TAP apps or plugins own instead
- important specs and docs to read first
- current model, edge, collector, and GRIFT scope
- local validation and operational notes

Keep it short at scaffold time, then maintain it as decisions accumulate. Do not leave it as a stale placeholder once the plugin has real behavior.

Periodically revisit root `README.md` and any plugin-local docs during plugin work, especially after adding models, edges, collectors, GRIFT seed data, validation behavior, or operational assumptions. Treat stale plugin documentation as spec drift: update it in the same change set when the implementation or architecture moves. Use `docs/` for setup guides, operator runbooks, inventories, and longer design notes that would make the root README hard to scan.

## If Your Plugin Ships Templates

If the plugin will render its own panels or pages, those land under `plugins/<slug>/templates/<slug>/...` and the actual authoring follows the [`add-panel`](../../../tap_web/skills/add-panel/SKILL.md) and [`add-page`](../../../tap_web/skills/add-page/SKILL.md) skills. Two scaffold-time things worth knowing up front:

- **Tailwind utilities require a manual stylesheet rebuild.** The compiled `tap_web/static/tap_web/css/tailwind.css` does not auto-rebuild when you add new utility classes. Procedure documented in [`docs/misc/doc-dev-tailwind-rebuild.md`](../../../docs/misc/doc-dev-tailwind-rebuild.md). The symptom of forgetting: the `class=` attribute is set, the computed style ignores it.
- **Plugin templates aren't yet scanned by the Tailwind config.** Until the BACKLOG fix lands (see [`tap_web/specs/spec-web-tailwind-pipeline-BACKLOG.md`](../../../tap_web/specs/spec-web-tailwind-pipeline-BACKLOG.md) — `req-web-tailwind-pipeline-content-paths`), utilities used only inside `plugins/<slug>/templates/` won't end up in the compiled output no matter how many times you rebuild. The add-panel skill enumerates workarounds.

## Plugin Configuration And Dependencies (hard rules)

Two anti-patterns that have bitten this codebase — do not repeat them:

- **No plugin config in core infrastructure.** A plugin's configuration must not live in `docker-compose.yml`, core settings, or other shared infra (`req-plugin-arch-runtime-4`). Plugins self-configure through plugin-owned mechanisms — in v0, on-disk secrets discovered under `TAP_SECRETS_ROOT` (e.g. resolve a well-known `SecretRef`). A durable on-grid plugin-config model is future work. The removed `AWS_CORE_STEAMPIPE_COLLECTOR` compose entry was this mistake.
- **No new third-party dependencies without explicit approval.** TAP deliberately minimizes third-party dependence: prefer Django/stdlib and capabilities already present before reaching for a package. Adding a library requires deliberate justification and the user's go-ahead — never slip one in. (boto3 was pulled in for an AWS identity check and removed; the check uses the already-present Steampipe instead.)

## Step 5: Create Models

For each model the plugin needs, follow the **[`add-model`](../../../tap_grid/skills/add-model/SKILL.md) skill**. It is the canonical procedure for adding a TAP-managed BaseModel — file layout, required class variables, dual-schema contract, manifest registration, migrations, spec sync, and tests are all covered there.

Within plugin scaffolding, complete the skill's Step 1 (shape) and Step 2 (model file) for every model before moving on. Step 4 (manifest registration), Step 5 (migrations), and Step 8 (tests) typically run once at the end of plugin scaffolding rather than once per model.

Re-export every model from `models/__init__.py` so `from <plugin>.models import <Model>` works.

## Step 6: Create Edge Definitions

For each edge type the plugin needs, follow the **[`add-edge`](../../../tap_grid/skills/add-edge/SKILL.md) skill**. It is the canonical procedure for adding an edge type — `.edge.json` file shape, source/target rules, property schema design (especially enums), manifest registration, default dimensions, and tests are all covered there.

Within plugin scaffolding, complete the skill's Step 1 (shape) and Step 2 (edge file) for every edge before moving on. Step 3 (manifest registration) and Step 7 (tests) typically run once at the end of plugin scaffolding rather than once per edge.

## Step 7: Create GRIFT Seed Data (if applicable)

If the plugin includes reference data that should be pre-loaded, create GRIFT files in `grift/`.

Read `tap_grid/specs/spec-grift-v0.md` for the format. Validate against `tap_grid/schemas/grift-document.schema.json`.

Use deterministic entity IDs where repeated imports should upsert cleanly. If the repo does not yet have an approved pattern for the plugin, flag that gap rather than inventing an unstable ID scheme silently.

### Iterating on GRIFT content

GRIFT batches are idempotent by `batch_entity.entity_id` — editing a file in place and re-running the importer does nothing. When you need to revise content, pick one of two canonical paths:

- **Version bump (always valid, required for release).** Create a new batch with a fresh `batch_entity.entity_id` and a bumped name (`v0.1.0` → `v0.2.0`). Node and edge entity_ids inside the batch stay stable so upsert applies. This is the path whenever the change ships, whenever you're outside `DEBUG=True`, and whenever you want the batch history to read as a coherent progression.
- **Force re-import (dev iteration only, DEBUG-gated).** Use `import_plugin_grift <plugin> --force-batches=<batch_id>` to re-apply the same batch without changing its id. Add `--purge` to hard-delete ephemeral orphans. Add `--sweep-strict` to abort if any orphan can't be cleanly swept. All permitted if and only if `DEBUG=True`.

Canonical guidance lives in [`tap_plugins/specs/spec-plugin-architecture.md`](../../tap_plugins/specs/spec-plugin-architecture.md) under *Iterative Development* (`req-plugin-arch-iterative-dev`). The underlying requirements — force re-import, batch-scoped sweep, sweep purge — are defined in [`tap_grid/specs/spec-grid-import-grift.md`](../../tap_grid/specs/spec-grid-import-grift.md).

Do not silently edit grift content and re-run the importer without picking one of the two paths above; the edit will be ignored and you'll waste time debugging an absence of change.

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

## Step 11: Update Plugin Documentation

Update root `README.md` so it is useful to a future developer or AI agent landing directly in the plugin. Cover:

- What the plugin does (1-2 sentences)
- What this plugin owns versus what remains in TAP core or sibling plugins
- Resource types modeled (organized by category)
- Edge types
- Collector, receiver, emitter, or schedule behavior, if any
- GRIFT seed data and import expectations, if any
- Important specs and source files to read before editing
- How to install (`git submodule add`, `INSTALLED_APPS`, `migrate`)
- How to validate (`python manage.py validate_plugin plugins/<slug> --level runs`)
- Pointer to `specs/` for detailed documentation

Create or update `docs/` files for operational setup, runbooks, generated inventories, and longer implementation notes. The root README should point into those docs rather than absorbing all details.

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
