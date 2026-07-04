# TAP Boot Bootstrap Specification

## Philosophy

`spec-tap-boot-v0.md` took a TAP instance from a fresh database to a populated,
self-describing instance by applying **one boot profile in fixed phases**. It answered
*"given a profile, stand the instance up."* It did not answer the question that comes
*before* that one: **where does the profile itself come from, and how does a single
gesture pick which one?**

Today a profile is a file the operator already has on disk (`boot/<id>.boot.json`, or a
plugin-owned `--boot-file` path). That is **single-file boot**: you must already possess
the recipe. The chicken-and-egg is unmissable once plugins live in their own repos — if
`samsite.boot.json` ships *inside* the samsite plugin, and the boot profile is what says
*which plugins to install*, then the profile is trapped inside an artifact you have not
installed yet. You cannot read the recipe until you have the ingredient the recipe tells
you to fetch.

This spec closes that gap with **single-command boot**: one pointer, resolved through the
source machinery TAP already has, fetches the boot record out of a versioned plugin
artifact and stands the instance up from it.

> One pointer names a plugin artifact, a version, and a boot record inside it. The
> bootloader fetches the record, stages it as the active profile, and proceeds. The
> instance unrolls from a single line. Config-as-code, extended one level up: the
> *location of the config* is itself config.

This is **netboot** for TAP, and we build on that lineage deliberately (Prior Art below):
a machine with no operating system holds one pointer (PXE's `next-server`+`filename`,
Ignition's config URL, a Nix flake ref), fetches a recipe, and converges. The irreducible
stage-0 is *"know where to look"*; everything else is downloaded. TAP's irreducible
stage-0 is one pointer string.

Two forces make this worth building **now**, ahead of the lights-out deployment that will
eventually require it:

- **Dogfood-until-load-bearing.** The same command is the daily-driver spawn *and* the
  eventual zero-touch field standup. Building it now means it is exercised every day until
  the moment a customer's lights-out environment depends on it — battle-hardened before it
  is critical, not guessed at when it is.
- **It replaces a harder question.** The alternative — "where do we store boot profiles
  when we need them, and how do we version them" — is *more* machinery, not less. A pointer
  into a versioned artifact makes the storage-and-versioning question dissolve: the record
  lives in the plugin, versioned with it, fetched on demand.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | One Command | A single `tap boot --from <pointer>` stands an instance up from nothing but the pointer. |
| 2. | Records Ride The Artifact | Boot records ship *inside* the plugin package, so bootstrap is source-type-agnostic (git, index, wheelhouse all work identically). |
| 3. | Precise Selection | The pointer names package + version + record; a plugin may ship many records (instance flavors) and the pointer picks exactly one. |
| 4. | Versioned Honestly | A record carries its own version, decoupled from the plugin's code tag; content changes are guarded, never silent. |
| 5. | Fail Closed | Ambiguous or unverifiable selection is a loud error, never a silent default. |

## v0 Scope (spec-first, code deferred)

This spec is **authored ahead of its implementation** (the callsite-identity / SARIF-Phase-0
pattern): the design is locked here so the six standardization decisions do not drift while
the pieces land incrementally. The **content-hash integrity guard (`req-boot-bootstrap-record-version`)
is the near-term buildable floor** — cheap, foundational, worth laying while the surface is
being defined (`spec-security-posture.md` `req-sec-cheap-edges`). Signing
(`req-boot-bootstrap-signing`) is explicitly **backlog**, demand-gated on the first
non-George user (see the strategy note in `plan/road-rampart.md`).

The pilot is **`gryphon_playground`**: it already owns a plugin-local profile, it is
low-stakes, and it immediately exercises multi-record selection — a `playground` flavor
(muck around: seed the Gridkin corpus, no workers) and a `soak` flavor (same install, but
population drives the fuzz-campaign task loop). `samsite` (the demo) migrates to the
in-package `boot/` convention once the pilot proves the path.

## Prior Art

The pointer, the version model, and the fetch are each a well-trodden pattern; we assemble
them rather than invent.

- **Netboot family (PXE / iPXE / cloud-init / Ignition).** A machine with no OS holds one
  pointer and fetches its recipe: PXE's DHCP hands `next-server` + `filename`; Ignition
  takes a single config URL before PID 1 and converges on first boot. The irreducible
  stage-0 is *know where to look*; the rest is downloaded. TAP's single pointer is the same
  irreducible stage-0.
- **Nix flake reference + fragment.** `github:org/repo/v1.0#nixosConfigurations.foo` selects
  a **named output** from a **versioned** flake with a `#fragment`. This is the pointer
  grammar TAP adopts directly: `<source-ref>#<record>`. Nix also fails loud when no
  `default` output exists rather than guessing — the model for `req-boot-bootstrap-default-record`.
- **Lockfile integrity (npm `package-lock` SHA-512 SRI, Cargo.lock checksums, Nix narHash).**
  Every modern package manager splits a **human-facing version that floats** from a
  **content hash that pins and guards**: on install the artifact is re-hashed and compared,
  and a mismatch *halts the install*. A version bump produces a new hash, so a content change
  without a version bump is detectable. This is exactly the guard `req-boot-bootstrap-record-version`
  adopts — "content changed ⇒ version must move, or CI fails."
- **GitOps app-of-apps (`flux bootstrap`, `argocd-autopilot`).** The bootstrap config
  references the very repo/app that manages it — the self-reference that resolves the
  chicken-and-egg. TAP's boot record names its own plugin in its install list
  (`req-boot-bootstrap-stage0`).
- **Kustomize overlays / compose profiles / Spring profiles.** One artifact, many named
  instance shapes selected at launch. This is the "a plugin ships multiple boot records"
  model (`req-boot-bootstrap-records-in-package`): a record *is* an instance flavor.
- **Sigstore keyless signing / PyPI attestations (PEP 740).** OIDC workflow identity →
  short-lived Fulcio cert → sign → Rekor transparency log; no long-lived keys. The signing
  ladder (`req-boot-bootstrap-signing`) builds on this, not on GPG keyrings.

## Relationship To Other Specs

- **Extends `spec-tap-boot-v0.md`.** That spec owns the profile *shape* and the phase
  application (`req-boot-profile`, `req-boot-phases`, `req-boot-population`). This spec owns
  *resolving and fetching* the profile from a pointer, one level above. `--from` is a
  superset of `--boot-file` (`req-boot-bootstrap-command`): a local path still works; a
  remote `pkg@ver#record` is the new capability. The pre-boot stage (`req-boot-preboot`) is
  where stage-0 fetch runs — before Django, settings-free.
- **Consumes `spec-plugin-architecture.md`'s source machinery.** The pointer's `<source-ref>`
  resolves through the existing source-type strategies (`req-plugin-arch-sources`: git /
  index / wheelhouse); bootstrap is **another consumer of the source registry, not a new
  fetch path**. That is why records-ride-the-artifact matters: a record shipped as package
  data is reachable by *every* source type identically.
- **Supersedes the location half of `req-plugin-arch-layout-6`.** That requirement put a
  plugin's standalone-test profile at the plugin **root** (`plugins/<slug>/<slug>.boot.json`,
  outside the importable package). Correct for a monorepo; wrong for bootstrap, because a
  root-level file does **not** ship in the wheel and so cannot be fetched from an index or
  wheelhouse install. `req-boot-bootstrap-records-in-package` moves records *into* the
  package (`tap_plugin/<slug>/boot/`) so they ride the artifact.
- **Sits under `spec-security-posture.md`.** The pointer is a **supply-chain root of trust** —
  the whole instance unrolls from it. The hash-floor / sigstore / TUF ladder
  (`req-boot-bootstrap-signing`) is the honest-risk register for that surface: cheap edge
  now, expensive edges named and demand-gated.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-boot-bootstrap-command | [Single-Command Boot](#single-command-boot) | Proposed | `tap boot --from <pointer>` fetches + stages + boots; `--from` subsumes `--boot-file` (local path, or remote `pkg@ver#record`) |
| req-boot-bootstrap-records-in-package | [Records Ride The Artifact](#records-ride-the-artifact) | Proposed | Boot records live at `tap_plugin/<slug>/boot/<name>.boot.json` as package data; shippable records in-package, harness profiles stay repo-local; supersedes the location of `req-plugin-arch-layout-6` |
| req-boot-bootstrap-pointer-grammar | [Pointer Grammar](#pointer-grammar) | Proposed | `<source-ref>#<record>` (Nix-flake fragment); source-ref resolves via `req-plugin-arch-sources`; `#<record>` selects `boot/<record>.boot.json` |
| req-boot-bootstrap-default-record | [Default Record Is Explicit](#default-record-is-explicit) | Proposed | No `#` → `boot/default.boot.json` if present, else loud error naming available records; never "first"/"latest" |
| req-boot-bootstrap-record-version | [Record Version + Integrity Guard](#record-version--integrity-guard) | Proposed | **Hash floor is the near-term build.** Record carries its own `version`, decoupled from the code tag; a content hash guards it (content change ⇒ version bump, else CI fails); install entries pin *or* float per plugin |
| req-boot-bootstrap-stage0 | [Stage-0 Fetch Without Import](#stage-0-fetch-without-import) | Proposed | Extract only `boot/<record>.boot.json` from the artifact without installing/importing the package; the record self-references its own plugin (app-of-apps) |
| req-boot-bootstrap-discovery | [Record Discovery](#record-discovery) | Proposed | `tap-plugin.toml` enumerates records (name + description); `tap boot --list <pointer>` and spawn tab-completion read it; a CI guard reconciles the toml against `boot/*.boot.json` |
| req-boot-bootstrap-signing | [Supply-Chain Integrity Ladder](#supply-chain-integrity-ladder) | Proposed | **Backlog, surfaced sooner-than-usual.** Hash (near-term) → Sigstore keyless attestation → TUF channel security; verify primitives are a `tap/`-level helper (`sigstore` uv-installed), NOT the `sigstore_core` plugin; trigger = first non-George user |

---

### Single-Command Boot
----
RID: `req-boot-bootstrap-command`
Status: `Proposed`

One command stands an instance up from nothing but a pointer.

#### Implementation

- The bootloader gains `--from <pointer>`, a **superset** of `--boot-file`. `--from` accepts:
  - a **local path** (today's `--boot-file` behavior — a file already on disk, including a
    repo-local harness profile like `boot/core_dev.boot.json`);
  - a **remote pointer** (`req-boot-bootstrap-pointer-grammar`) resolved through the source
    machinery — the new capability.
  The single flag dispatches on the shape of its argument, matching the mainstream polymorphic
  form (`nix run <installable>`, `pip install <arg>` — path, URL, or name). `--boot-file` is
  retained as a deprecated alias, not a second mechanism.
- The pointer may be supplied as `--from`, or as the `TAP_BOOT_FROM` boot-variable
  (`req-boot-variable-resolution` ladder: flag > env > default). One env var is the entire
  lights-out stage-0 configuration — the DHCP-option / cloud-init-user-data equivalent.
- Remote resolution runs in the **pre-boot stage** (`req-boot-preboot`), before `migrate` and
  before Django reads settings: stage-0 fetch (`req-boot-bootstrap-stage0`) produces the boot
  record on disk, which the rest of pre-boot and `manage.py boot` then consume exactly as a
  local profile. Nothing downstream of staging knows the profile came from a pointer.
- The command is the canonical standup for **both** dev (spawn) and customer field deployment —
  the one-path doctrine (`req-boot-app`) extended to the profile's origin.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-command-1 | From Flag | Proposed | `--from <pointer>` resolves a local path or a remote pointer; dispatch is on argument shape. | |
| req-boot-bootstrap-command-2 | Boot-File Subsumed | Proposed | `--boot-file` becomes a deprecated alias of `--from`; one code path. | |
| req-boot-bootstrap-command-3 | Env Stage-0 | Proposed | `TAP_BOOT_FROM` supplies the pointer via the boot-variable ladder; one env var is the whole lights-out stage-0 config. | |
| req-boot-bootstrap-command-4 | Resolves In Pre-Boot | Proposed | Remote resolution runs in the settings-free pre-boot stage; downstream boot treats the staged record as a local profile. | |

---

### Records Ride The Artifact
----
RID: `req-boot-bootstrap-records-in-package`
Status: `Proposed`

Boot records ship **inside** the importable plugin package, as package data, so bootstrap is
source-type-agnostic.

#### Implementation

- A plugin's boot records live at **`tap_plugin/<slug>/boot/<name>.boot.json`** — inside the
  importable package, declared as package data (the same treatment `grift/` and
  `tap-plugin.toml` already get). They therefore **ship in the wheel** and travel with the
  versioned artifact.
- **This is the load-bearing reason for the location.** A record must be reachable by *every*
  source type — git, the future index, and the wheelhouse. A record at the plugin **root**
  (the old `req-plugin-arch-layout-6` location) is outside `tap_plugin/<slug>/` and does **not**
  ship in the wheel, so it can only be fetched over git — breaking bootstrap from an index or an
  airgapped wheelhouse. In-package placement makes the fetch identical across all source types
  (`req-plugin-arch-sources`).
- **Version coherence for free.** The record you get is exactly the one that shipped in that
  package version — the recipe and the code it installs are pinned together by construction
  (see `req-boot-bootstrap-record-version` for the record's *own* version axis).
- **A record is an instance flavor.** A plugin MAY ship several records in its `boot/` dir, each
  a full instance recipe (install + population + behavior). The pilot: `gryphon_playground`'s
  `boot/playground.boot.json` (seed the Gridkin corpus, no workers — muck around) and
  `boot/soak.boot.json` (same install, population drives the fuzz-campaign task loop). Same
  package, same version, different flavor — the Kustomize-overlay / compose-profile shape.
- **Two record classes, two homes:**
  - **Shippable / solution-set records** (samsite demo, gryphon flavors) live **in-package**,
    per this requirement — they travel to deployments.
  - **Harness / dev records** (`core`, `core_dev`, `test_all`) stay **repo-local** under `boot/`
    — they are monorepo-dev/test infrastructure, install-everything-editable, and never shipped.
    `--from` still resolves them by local path.
- **Migration.** `req-plugin-arch-layout-6`'s `plugins/<slug>/<slug>.boot.json` moves to
  `plugins/<slug>/tap_plugin/<slug>/boot/<name>.boot.json`. The gryphon pilot moves
  `gryphon_playground.boot.json` → `tap_plugin/gryphon_playground/boot/playground.boot.json`
  and adds `boot/soak.boot.json`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-records-in-package-1 | In-Package Location | Proposed | Boot records live at `tap_plugin/<slug>/boot/<name>.boot.json`, declared as package data, shipping in the wheel. | |
| req-boot-bootstrap-records-in-package-2 | Source-Type-Agnostic | Proposed | Because records ride the wheel, the same pointer resolves identically over git, index, and wheelhouse. | Supersedes the plugin-root location of `req-plugin-arch-layout-6` |
| req-boot-bootstrap-records-in-package-3 | Multiple Records Per Plugin | Proposed | A plugin may ship several records (instance flavors) in one `boot/` dir; selection is per `req-boot-bootstrap-pointer-grammar`. | Pilot: gryphon `playground` vs `soak` |
| req-boot-bootstrap-records-in-package-4 | Shippable vs Harness | Proposed | Shippable records are in-package; harness profiles (`core`/`core_dev`/`test_all`) stay repo-local under `boot/` and resolve by local path. | |

---

### Pointer Grammar
----
RID: `req-boot-bootstrap-pointer-grammar`
Status: `Proposed`

A single-line pointer names package + version + record.

#### Implementation

- The grammar is the **Nix-flake fragment**: `<source-ref>#<record>`.
  - `<source-ref>` is resolved by the **existing** source machinery (`req-plugin-arch-sources`)
    to a **versioned artifact**. It carries the source type + locator + version exactly as an
    `install` entry's `source` already does — e.g.
    `git+https://github.com/notgeorge/tap-plugin-gryphon-playground@v0.1.0`, or an index/wheelhouse
    locator. Credentials resolve from `TAP_SECRETS_ROOT`, never in the pointer
    (`req-plugin-arch-sources-4`).
  - `#<record>` selects `boot/<record>.boot.json` from inside that artifact.
- Example: `git+https://github.com/notgeorge/tap-plugin-gryphon-playground@v0.1.0#soak`
  → the `soak` record from the v0.1.0 gryphon artifact.
- **Three independent, individually-pinnable version axes** — do not conflate them:
  1. the **package artifact** version (which wheel carries the record) — in `<source-ref>`;
  2. the **record contract** version (`req-boot-bootstrap-record-version`) — inside the record;
  3. the **per-plugin install** versions — inside the record's `install` entries.
- The pointer is a **locator, not a full profile**: it identifies the record; the record itself
  declares the install set and population. This keeps the pointer to a single line and puts the
  reproducibility surface (pinned plugin versions) in the record where it is reviewable.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-pointer-grammar-1 | Fragment Selects Record | Proposed | `#<record>` selects `boot/<record>.boot.json` from the resolved artifact. | |
| req-boot-bootstrap-pointer-grammar-2 | Source-Ref Reuses Machinery | Proposed | `<source-ref>` resolves through `req-plugin-arch-sources` (git/index/wheelhouse); bootstrap adds no new fetch path. | |
| req-boot-bootstrap-pointer-grammar-3 | No Secrets In Pointer | Proposed | The pointer carries only a locator + version + record name; credentials resolve from `TAP_SECRETS_ROOT`. | Mirrors `req-plugin-arch-sources-4` |
| req-boot-bootstrap-pointer-grammar-4 | Three Version Axes | Proposed | Artifact version, record-contract version, and per-plugin install versions are independent and separately pinnable. | |

---

### Default Record Is Explicit
----
RID: `req-boot-bootstrap-default-record`
Status: `Proposed`

Selecting a record without a `#` resolves to a named default or fails loud — never a guess.

#### Implementation

- A pointer with no `#<record>` resolves to **`boot/default.boot.json`** if it exists.
- If there is no `default.boot.json`, resolution **fails loud**, naming the records that *are*
  available (`req-boot-bootstrap-discovery` supplies the list). It does **not** pick "the first
  one" or "the only one."
- **Prior art dictates this.** Nix flakes look for an explicitly-named `default` output and
  error if absent — the careful pattern. Docker's implicit `:latest` default is the
  widely-regretted counterexample: it drifts silently and reads as "the newest" when it means
  "whatever was tagged latest." Fail-closed-on-ambiguity is also the security posture
  (`req-sec-cheap-edges`: over-restriction relaxes cheaply; a silent wrong-flavor boot is
  expensive).
- The single-record convenience case is served by *naming* the default record `default.boot.json`,
  not by inferring it — an explicit authoring choice, visible in the `boot/` dir.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-default-record-1 | Named Default | Proposed | No `#` resolves to `boot/default.boot.json` when present. | |
| req-boot-bootstrap-default-record-2 | Fail Closed On Ambiguity | Proposed | Absent a `default.boot.json`, resolution errors and names the available records; never "first"/"latest". | |

---

### Record Version + Integrity Guard
----
RID: `req-boot-bootstrap-record-version`
Status: `Proposed`

A boot record carries its **own** version, decoupled from the plugin's code tag, and a content
hash guards it. **The hash guard is the near-term buildable floor of this spec.**

#### Implementation

- **The problem this solves.** If the record's identity were tied to the plugin's git tag alone,
  a bugfix that bumps `gryphon@v0.1.0 → v0.1.1` would "move" the record even though its content
  did not change — and anyone pinned to `@v0.1.0` would be frozen on stale code with no way to
  express "same recipe, newer code." A record needs a version axis of its own.
- **Two-layer versioning, per universal lockfile practice** (npm SRI, Cargo.lock, Nix narHash):
  1. a **human-facing `version`** inside the record (SemVer), which the author bumps when the
     record's content changes; and
  2. a **content hash** (`sha256` over the canonicalized record) that pins the bytes and *guards*
     the version.
- **The guard (this is the cheap edge to build now).** A CI check re-hashes each record and
  compares against its declared hash/version: **content changed ⇒ the hash changed ⇒ the declared
  `version` must have moved, or the build fails.** This is exactly the npm `EINTEGRITY` /
  lockfile-mismatch discipline, and it is the same derived-vs-declared drift lesson that bit the
  uuid5 seed ids — a value derived from content must be regenerated through its derivation, not
  hand-edited. Cheap now, foundational, worth laying while the surface is being defined.
- **The honest tension — named, not hidden.** No system can give both "old pointers auto-receive
  fixes" *and* "old pointers are byte-reproducible"; those contradict. What every package manager
  ships instead is: *float a ref, pin via a lock, make re-pinning a deliberate, guarded act*
  (`nix flake update`, `npm update`). TAP's version of that lives in the record's **install
  entries**, each of which may:
  - **pin** (`rev: v0.1.0`) → byte-reproducible, for lights-out / customer records; or
  - **float** (`rev: main`, or a range) → auto-receives fixes, for daily-driver records.
  The record's own `version` + content-hash guard makes every *recipe* change deliberate,
  independent of whether the *code* it installs floats.
- **Content hash is also the artifact `req-boot-bootstrap-signing` signs over** — the hash is the
  floor of the integrity ladder; a signature binds identity on top of the same bytes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-record-version-1 | Record Owns Its Version | Proposed | A record carries a SemVer `version` decoupled from the plugin's code tag; bumping code does not move it unless the record content changed. | |
| req-boot-bootstrap-record-version-2 | Content Hash Guard | Proposed | A CI check re-hashes each record; a content change without a `version` bump fails the build (derived-vs-declared drift). | **Near-term buildable floor** |
| req-boot-bootstrap-record-version-3 | Per-Entry Pin Or Float | Proposed | Each install entry pins (`rev: v0.1.0`, reproducible) or floats (`rev: main`/range, auto-fix); the reproducible-vs-fresh tension is resolved per entry, deliberately. | |

---

### Stage-0 Fetch Without Import
----
RID: `req-boot-bootstrap-stage0`
Status: `Proposed`

Stage-0 extracts only the boot record from the artifact, without installing or importing the
package.

#### Implementation

- Stage-0 resolves `<source-ref>` to the artifact and **extracts only `boot/<record>.boot.json`** —
  it does **not** `pip install` or import the bootstrap plugin at this point. Concretely: download
  the wheel (or sparse-fetch the path) and read the file out of it, rather than installing a
  package whose sibling-imports are not yet satisfiable (the bootstrap plugin may `import
  tap_plugin.<sibling>` at module load, and those siblings are exactly what the record has not
  installed yet). Reading bytes out of an artifact triggers none of that.
- This keeps stage-0 the **minimal, settings-free, Django-free** fetcher that pre-boot already is
  (`req-boot-preboot-1`), and preserves the "abort before any mutation" guarantee: a bad pointer
  fails before `migrate`, DB untouched.
- **Self-reference resolves the chicken-and-egg (app-of-apps).** The staged record names its own
  plugin in its `install` list, so the bootstrap plugin is then installed *properly* (pinned,
  registered, migrated) as part of the normal install stage — not left as a stage-0 peek. This is
  the GitOps `flux bootstrap` / `argocd-autopilot` shape: the config that manages the instance
  includes itself.
- The extracted record is written to the pre-boot working area and consumed as an ordinary local
  profile from that point on; `req-boot-preboot` / `req-boot-install-section` / `req-boot-population`
  are unchanged downstream.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-stage0-1 | Extract Not Install | Proposed | Stage-0 reads `boot/<record>.boot.json` out of the artifact without installing/importing the package. | |
| req-boot-bootstrap-stage0-2 | Settings-Free + Abort-Safe | Proposed | Stage-0 stays Django-free and runs before `migrate`; a bad pointer aborts with the DB untouched. | Extends `req-boot-preboot-4` |
| req-boot-bootstrap-stage0-3 | Self-Reference | Proposed | The staged record names its own plugin in `install`, so the bootstrap plugin is properly installed in the normal stage (app-of-apps). | |

---

### Record Discovery
----
RID: `req-boot-bootstrap-discovery`
Status: `Proposed`

A plugin's available boot records are enumerable cheaply, without a full artifact fetch.

#### Implementation

- **`tap-plugin.toml` enumerates the records** the plugin ships: for each, its `name` (the
  `#<record>` selector) and a one-line `description` of the flavor. The `boot/*.boot.json` files
  remain the runtime source of truth; the manifest is the **index** of them (the entry-points /
  flake-`show` / compose-`--profiles` shape). Each record's own `description` field
  (`json-structures-require-descriptions`) is the long form; the manifest carries the short label
  so listing does not require reading every record.
- **`tap boot --list <source-ref>`** fetches only the manifest (one small file, source-type-agnostic)
  and prints the available records + descriptions — the netboot menu.
- **Tab completion falls out of the grammar.** Because the pointer is enumerable at each coordinate
  — package → version → record — `spawn-session` (and `tap boot`) can complete each `<TAB>`:
  package names from the known plugin set, versions from the source's tags/index, and record names
  from the manifest (with descriptions shown inline). Completing a record requires only the manifest
  read, not a wheel download. This is a concrete near-term payoff of standardizing the grammar, not
  a hypothetical.
- **A CI guard reconciles the manifest against the filesystem:** every record enumerated in
  `tap-plugin.toml` has a matching `boot/<name>.boot.json`, and every `boot/*.boot.json` is
  enumerated (fail closed both directions). This is the same cheap coherence-guard shape as the
  existing plugin conformance checks — it keeps the listing honest.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-discovery-1 | Manifest Enumerates Records | Proposed | `tap-plugin.toml` lists each shipped record's name + description; `boot/*.boot.json` stays the runtime truth. | |
| req-boot-bootstrap-discovery-2 | List Command | Proposed | `tap boot --list <source-ref>` fetches only the manifest and prints available records + descriptions. | |
| req-boot-bootstrap-discovery-3 | Tab Completion | Proposed | Package / version / record complete from known sets + the manifest; record completion needs no wheel download. | `spawn-session` + `tap boot` |
| req-boot-bootstrap-discovery-4 | Manifest ↔ Files Guard | Proposed | A CI check fails closed if the manifest's record list and `boot/*.boot.json` disagree in either direction. | |

---

### Supply-Chain Integrity Ladder
----
RID: `req-boot-bootstrap-signing`
Status: `Proposed`

The pointer is a supply-chain root of trust; the instance unrolls from it. Integrity is a
**ladder** — a cheap floor now, expensive rungs named and demand-gated.

#### Implementation

> **Backlog — but surfaced sooner than the usual demand-gate.** The **trigger is the first
> non-George user** playing with the system: at that point we want to offer the most secure
> plugin/boot experience possible, to set the bar high from the start. See the strategy note in
> `plan/road-rampart.md`. Named here so the surface is designed for it, not retrofitted.

- **What signing buys, and what it does not.** A signature gives **integrity** (not tampered) +
  **authenticity** (who built it) — and **nothing else**. Not confidentiality, and crucially **not
  a judgment of intent**: a correctly-signed malicious plugin verifies perfectly. Signing binds an
  artifact to an identity; trusting the identity is a separate decision. This bounds the whole
  ladder honestly.
- **The three rungs:**

  | Rung | Cost | When |
  | --- | --- | --- |
  | **Content hash** in the record / a wheelhouse `sha256` manifest | ~free | **now** — this is `req-boot-bootstrap-record-version`'s guard; catches accidental drift + naive tampering |
  | **Sigstore keyless attestation** (wheel + boot record) | low — reuses the `gh` OIDC identity + a small `tap/` helper | **first non-George user** |
  | **TUF-style channel security** (rollback / freshness / threshold keys) | high | only when an untrusted mirror/index is in the path |

- **Sigstore keyless, specifically.** No long-lived keys. The GitHub Actions release workflow gets
  an OIDC token ("I am the release job of `notgeorge/tap-plugin-<slug>`"), sends an ephemeral public
  key + that token to Fulcio (Sigstore's CA), and receives a ~10-minute cert **binding the workflow
  identity to the key**. It signs the artifact's digest, producing a PEP-740-style in-toto
  attestation that ties *this artifact's name + hash* to *that identity*, logged in the Rekor
  transparency log; the ephemeral key is discarded. Verification checks: signature valid, cert
  identity == the expected release workflow, present in Rekor. Key custody: none, ever. This fits
  TAP because plugins are already published via `gh` — the same OIDC identity the release path
  already has.
- **Layering — the verifier is `tap/`-level, NOT the `sigstore_core` plugin.** Plugin-install/boot
  verification runs **before and beneath** any plugin exists; making the verifier depend on a
  plugin being installed to verify plugins is a chicken-and-egg layering violation and cuts against
  the no-sideways-`tap_*`-dependency rule (`avoid-tap-app-interdependencies`). The verify primitives
  therefore live at **`tap/` level** — a `tap/plugin_verify.py`-shaped helper next to
  `plugin_source_auth.py` and `runtime_secrets` — with the `sigstore` library **uv-installed as a
  boot dependency**, not by reusing `sigstore_core`'s code (that plugin is *domain data on the grid*;
  this is *infrastructure*). Same shape as the source-auth helper: settings-free, app-neutral,
  import-safe.
- **Highest-value target is the record, not only the wheel.** Because the pointer is the root, the
  **boot record** (the recipe) is as worth signing as the plugin code (the ingredients). Sign both.
- **Where it matters most.** The git+PAT install already trusts the *transport* (TLS to GitHub + the
  token) — authenticity of the *channel*, not the *artifact*. Signing is transport-independent, so
  it matters exactly where the channel guarantee disappears: **wheelhouse / airgapped / third-party
  index** installs, where a wheel arrives with no trusted-host TLS behind it. This shares the
  deferred-signing edge already named in `req-plugin-arch-sources-6` / `req-plugin-arch-versioning-5`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-bootstrap-signing-1 | Hash Floor Now | Proposed | The content hash of `req-boot-bootstrap-record-version` is the near-term integrity floor; wheelhouse `sha256` manifest shares it. | |
| req-boot-bootstrap-signing-2 | Sigstore Keyless | Proposed | Wheel + boot record signed via Sigstore keyless (OIDC → Fulcio → Rekor); no long-lived keys; verify checks identity + inclusion. | Trigger: first non-George user |
| req-boot-bootstrap-signing-3 | Verifier Is tap/-Level | Proposed | Verify primitives live in `tap/` (e.g. `tap/plugin_verify.py`) with `sigstore` uv-installed; NOT the `sigstore_core` plugin (layering: infra below plugins). | |
| req-boot-bootstrap-signing-4 | Sign The Record Too | Proposed | The boot record (the recipe / supply-chain root) is signed alongside the plugin code (the ingredients). | |
| req-boot-bootstrap-signing-5 | TUF Named Not Built | Proposed | TUF-style channel security (rollback/freshness/threshold) is the far rung, built only when an untrusted mirror is in the path. | |
