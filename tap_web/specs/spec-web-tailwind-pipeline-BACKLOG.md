# Web Tailwind Build Pipeline Specification

## Philosophy

TAP's web layer uses Tailwind CSS for layout, typography, and color, with the compiled stylesheet shipped as `tap_web/static/tap_web/css/tailwind.css`. Tailwind's JIT compiler generates only the utility class rules it observes in scanned source files. Any class string that appears in a template but isn't present at compile time becomes a no-op in the browser: the HTML attribute is set, but there is no matching CSS rule, so the layout silently fails to apply.

Today the compiled stylesheet is a hand-built artifact checked into the repo. There is no `Makefile`, no `package.json`, no Docker build stage, no spawn-session hook, and no pre-commit/pre-push step that re-runs the Tailwind CLI. Whoever last built the stylesheet did so on their own machine and committed the output. New utility classes added to a template after that build silently miss the compiled CSS, often without anyone noticing until a layout is visibly broken.

This specification proposes a standing Tailwind build pipeline that keeps the compiled stylesheet in lockstep with the templates that scan into it, so adding a new utility class is the only edit a contributor has to make.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | No Silent Failures | A new utility class in a template should never silently lack its CSS rule. |
| 2. | Dev-Loop Speed | The rebuild should happen automatically during template iteration, not on demand. |
| 3. | Scoped Surface | The build should scan every template directory that ships utility classes — `tap_web/templates`, `tap_viz/templates`, and any plugin templates under `plugins/*/templates`. |
| 4. | Reproducible | The build should produce identical output on any contributor's machine, in CI, and in the dev Docker stack. |
| 5. | No Hidden Dependencies | Whatever build mechanism is chosen should declare its tool versions explicitly so the artifact is deterministic. |
| 6. | Spawn-Session Friendly | New session worktrees should pick up the pipeline automatically without manual setup. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-tailwind-pipeline-rebuild | [Automated Rebuild](#automated-rebuild) | Proposed | The compiled `tailwind.css` should rebuild automatically when a watched template changes |
| req-web-tailwind-pipeline-content-paths | [Content Path Coverage](#content-path-coverage) | Proposed | Plugin template directories should be scanned alongside `tap_web` and `tap_viz` |
| req-web-tailwind-pipeline-determinism | [Deterministic Output](#deterministic-output) | Proposed | The build should pin the Tailwind CLI version so output is reproducible |
| req-web-tailwind-pipeline-spawn-integration | [Spawn-Session Integration](#spawn-session-integration) | Proposed | New session worktrees should inherit the pipeline without per-session setup |
| req-web-tailwind-pipeline-manual-fallback | [Documented Manual Path](#documented-manual-path) | Implemented | Until the pipeline lands, `docs/misc/doc-dev-tailwind-rebuild.md` documents the manual rebuild |

## Requirements

### Automated Rebuild
----
RID: `req-web-tailwind-pipeline-rebuild`
Status: `Proposed`

The compiled `tap_web/static/tap_web/css/tailwind.css` should rebuild automatically whenever a template in a scanned directory changes.

#### Implementation

The build mechanism is implementation-defined. Candidates worth weighing:

- **Docker sidecar**: a small Node container running `tailwindcss --watch` in the dev compose stack, sharing the templates volume. Same shape as how Django auto-reloads — fits the existing dev-loop.
- **`django-tailwind` package**: a Django app that integrates the CLI with `collectstatic` and dev-server reload. Cleanest Django-native integration but adds a third-party dependency (which requires the standing no-new-deps approval gate).
- **Standalone tailwindcss binary**: the precompiled standalone CLI ships without Node; can be invoked from a `scripts/tailwind-watch` wrapper. Smallest surface, no JS toolchain in the dev environment.

Whichever path lands, the contract is: editing a template never produces a no-op utility class; the next page load shows the new CSS rule applied.

#### Development

The current pattern — hand-built artifact checked into the repo — is the root cause of layout failures that are hard to diagnose. The HTML attribute is set, the browser dev tools show the class, but no rule matches the selector. A new contributor can spend significant time debugging "why doesn't my `sm:grid` apply" before the gap surfaces.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-tailwind-pipeline-rebuild-1 | Rebuild On Template Change | Proposed | Adding a new utility class to a watched template produces a matching CSS rule in `tailwind.css` without manual intervention. | |
| req-web-tailwind-pipeline-rebuild-2 | Dev-Loop Speed | Proposed | The rebuild completes fast enough that the next browser reload sees the new CSS — sub-2-second target. | |

#### Future

Decide whether to keep the compiled artifact in git after the pipeline lands, or move it to a build-time output that isn't committed.


### Content Path Coverage
----
RID: `req-web-tailwind-pipeline-content-paths`
Status: `Proposed`

The Tailwind content-path configuration should cover every template directory that ships utility classes.

#### Implementation

The v0 `tailwind.config.js` lists only `./tap_web/templates/**/*.html` and `./tap_viz/templates/**/*.html`. Plugin templates under `plugins/*/templates/**/*.html` are not scanned. Any utility class introduced in a plugin template will silently miss the compiled CSS.

The fix is a glob expansion in `content` to include `./plugins/**/templates/**/*.html` (or the equivalent per-plugin enumeration). The pattern should not depend on plugin discovery happening at Python import time — it should be a static glob the Tailwind CLI can resolve directly.

#### Development

Plugins increasingly own their own templates and panels. The roscale workbench, samsite KSI scoreboard, samsite nav-links, and any future plugin all sit outside the current scan path. Without coverage, their layout depends on whatever subset of utilities `tap_web`/`tap_viz` happen to use.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-tailwind-pipeline-content-paths-1 | Plugin Templates Scanned | Proposed | The Tailwind content config includes `plugins/*/templates/**/*.html`. | |
| req-web-tailwind-pipeline-content-paths-2 | Static Glob Resolution | Proposed | The scan path resolves without depending on Python plugin discovery. | |


### Deterministic Output
----
RID: `req-web-tailwind-pipeline-determinism`
Status: `Proposed`

The build should pin the Tailwind CLI version so the compiled output is reproducible.

#### Implementation

Whichever build mechanism is chosen, the Tailwind CLI version must be pinned — via a `package.json` `devDependencies` entry, a Docker image tag, or a checked-in standalone binary version stamp. Two contributors building the stylesheet from the same git revision should produce byte-identical output.

#### Development

Tailwind output diffs between CLI versions are real — utility class ordering, vendor prefix sets, and CSS variable patterns can shift. An unpinned build means "rebuild the stylesheet" turns into a noisy diff that obscures the actual class additions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-tailwind-pipeline-determinism-1 | CLI Version Pinned | Proposed | The Tailwind CLI version used by the build is explicitly pinned in repo configuration. | |
| req-web-tailwind-pipeline-determinism-2 | Reproducible Across Machines | Proposed | Rebuilding from a clean checkout produces a byte-identical `tailwind.css` to a teammate's rebuild. | |


### Spawn-Session Integration
----
RID: `req-web-tailwind-pipeline-spawn-integration`
Status: `Proposed`

New session worktrees (per `spec-dev-multisession`) should inherit the Tailwind pipeline without per-session setup.

#### Implementation

`scripts/spawn-session.sh` already wires per-session Compose stacks, port allocation, and grift seeding. Once the pipeline lands, spawning a session should activate the rebuild path automatically — no manual `npm install`, no per-session container build, no surprise on the first template edit.

#### Development

Session worktrees are how the project is actually developed. If the pipeline requires per-session setup, the friction will push contributors back to the "ship a hand-built stylesheet" pattern and the gap re-opens.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-tailwind-pipeline-spawn-integration-1 | Spawn Picks Up Pipeline | Proposed | A freshly spawned session worktree has the rebuild active without extra setup. | |


### Documented Manual Path
----
RID: `req-web-tailwind-pipeline-manual-fallback`
Status: `Implemented`

Until the automated pipeline lands, the manual rebuild process is documented so contributors can keep `tailwind.css` in step with template edits without guessing.

#### Implementation

`docs/misc/doc-dev-tailwind-rebuild.md` covers: when to rebuild (after adding any utility class not already present in the compiled output), how to rebuild (CLI invocation + content paths), how to verify (grep the compiled output for the new class), and the symptom-to-recognize when the rebuild was skipped ("the class appears on the element but the computed style doesn't match").

#### Development

A documented manual path is the bridge between "we know the gap exists" and "the pipeline closes the gap automatically." Without the doc, every contributor independently rediscovers the build mechanism, the content paths, and the symptom of forgetting to rebuild.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-tailwind-pipeline-manual-fallback-1 | Doc Exists | Implemented | `docs/misc/doc-dev-tailwind-rebuild.md` documents the manual rebuild flow. | |
| req-web-tailwind-pipeline-manual-fallback-2 | Symptom Documented | Implemented | The doc describes the "class present, no rule" symptom so contributors recognize it on sight. | |
