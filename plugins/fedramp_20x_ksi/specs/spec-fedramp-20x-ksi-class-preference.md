# FedRAMP 20x KSI Class Preference Specification

## Spec Status: Backlog

**Held 2026-05-05 pending the Dominant Class design.** This spec depends on [`spec-web-panel-client-state.md`](../../../tap_web/specs/spec-web-panel-client-state.md), which is itself Backlog for the same reason: a per-viewer browser preference is the wrong shape for the FedRAMP class problem. The breaking case is link-sharing — when one user shares a link to an indicator with another, the recipient opens at their own registered default class (or no class), not the sender's. Discussions about "look at indicator X under Class C" silently de-sync.

The right shape is a **dominant-class** object on the Grid (or per-system) that all KSI panels read from. The class isn't "what does this viewer prefer," it's "what class is this Rampart deployment / this system being audited under" — domain state, not UX state. A separate per-viewer preference layer may still be warranted later for non-shared-context preferences (UI density, color theme, timezone), but FedRAMP class is not one of them.

This spec is held until the Dominant Class spec lands. At that point this spec is revisited with one of three outcomes:

1. **Subsumed.** The dominant-class object covers all KSI-side needs; this spec is rewritten to align with it (or deprecated entirely).
2. **Re-scoped.** Per-viewer preferences are still useful for narrow values; this spec narrows to that scope or is dropped.
3. **Resurrected as-is.** The dominant-class layer covers shared-context values and a per-viewer preference layer covers UX values; this spec returns to `Approved for Development` after a re-review.

All requirements and ACIDs in this spec are status `Backlog`. The previously-drafted touch-ups to `spec-fedramp-20x-ksi-compliance-view.md`, `spec-fedramp-20x-ksi-indicator-profile.md`, and `spec-fedramp-20x-ksi-finding-profile.md` have been reverted; those existing specs will receive amendments only when this spec is unparked.

---

## Philosophy

FedRAMP 20x classifies systems into four certification classes — `a` (Pilot), `b` (Low), `c` (Moderate), `d` (High) — and the KSI catalog encodes per-class requirement variants on a substantial fraction of indicators. A user working through compliance for a Class C system shouldn't have to re-pick "C" on every indicator they open, every page they navigate to, every time the page reloads. The user's working class is a **persistent, browser-scoped preference** that the entire FedRAMP 20x KSI surface should respect uniformly.

Today this preference is partially implemented in an ad-hoc way: `spec-fedramp-20x-ksi-compliance-view.md` `req-ksi-compview-class-select` persists a user's class selection to `localStorage` under the key `tap-ksi-class-selection`. This works for the compliance view in isolation, but:

- The indicator profile (`spec-fedramp-20x-ksi-indicator-profile.md`) doesn't read it — every indicator page renders with a class chosen from a built-in fallback ladder (currently Class C via `_CLASS_PRECEDENCE` in the panel code).
- The finding profile doesn't read it (today findings don't carry class variants, but future class-scoped finding rollups will need to).
- Future system pages (when they land) would each need to invent their own way to read the same value.
- The platform now has a proper mechanism for this — the panel client-state system specified in `spec-web-panel-client-state.md`.

This spec **is the first concrete consumer** of the platform client-state mechanism. It:

1. Registers a single client-state preference: `fedramp.class`.
2. Rewires the compliance view from its ad-hoc `localStorage` storage to the platform mechanism (JS-only path; no server-side read for this panel).
3. Wires the indicator profile's hero / statement / class-badge logic to the preference so the page renders the user's preferred class on first paint, with the indicator profile opting in to the platform's server-side read API to avoid first-paint flicker.
4. Places a Preference Switcher panel above the existing compliance view on the `/fedramp-ksi` landing page, providing the explicit UI for setting the preference.
5. Calls out the future consumers (finding rollups, system pages) so the pattern is visible to the next person extending this surface.

### Why Greenfield (No localStorage Preservation)

The TAP demo deployment has exactly one user (the project author), so preserving any value previously set under the `tap-ksi-class-selection` localStorage key has no real cost-benefit case behind it. The migration ships clean: the dead key is removed unconditionally on first load and any prior class selection is dropped. Users land on the registered default (`"b"`) and re-select if they had a different working class. This keeps the spec focused on the new mechanism and removes a one-shot bridge that would otherwise carry weight across two release cycles.

The FedRAMP-side wiring is small in absolute lines of code — most of the mechanism lives in `tap_web` per the platform spec. What this spec primarily does is *commit to the contract*: every KSI panel that varies by class reads from the same place, writes to the same place, and the user's preference survives navigation, reload, and (within v0's per-browser scope) tab restarts.

### Cross-References

- Platform spec: [`spec-web-panel-client-state.md`](../../../tap_web/specs/spec-web-panel-client-state.md). The platform spec defines the registry, the cookie format, the server / client APIs, the Preference Switcher panel type, the per-key versioning mechanism, and the security boundary. This spec assumes that vocabulary throughout.
- Existing spec amendments tracked under platform `req-web-cstate-spec-touchups`:
  - `spec-fedramp-20x-ksi-compliance-view.md` — `req-ksi-compview-class-select` migrates from `localStorage` to the platform mechanism.
  - `spec-fedramp-20x-ksi-indicator-profile.md` — `req-ksi-profile-statement` and `req-ksi-profile-header` adopt the preference for their initial class.
  - `spec-fedramp-20x-ksi-finding-profile.md` — Future Work bullet noting class-scoped finding rollups will consume the same preference.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Single Source Of Truth | One registered preference (`fedramp.class`) drives every KSI panel that varies by class |
| 2. | First-Paint Correct    | Server-rendered KSI panels emit the user's preferred class on initial render — no JS toggle round-trip |
| 3. | Drop-In Switcher       | The Preference Switcher panel from `tap_web` is the v0 UI; no plugin-side selector code |
| 4. | Migration Without Loss | A user with an existing `tap-ksi-class-selection` localStorage value carries that selection forward into the new mechanism on first load |
| 5. | Forward-Compatible     | Future class-scoped consumers (system pages, finding rollups) plug in by calling the platform API; no plugin-side coordination is required |
| 6. | Documented Default     | The default value (`c`) and its rationale are recorded so reviewers don't have to reconstruct the choice |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-ksi-classpref-register | [Preference Registration](#preference-registration) | Backlog | `fedramp.class` registered with `allowed_values=("a","b","c","d")`, `default="c"`, `version=1` |
| req-ksi-classpref-switcher-placement | [Preference Switcher Placement](#preference-switcher-placement) | Backlog | Switcher panel above the compliance view on the `/fedramp-ksi` page |
| req-ksi-classpref-compliance-view | [Compliance View Adoption](#compliance-view-adoption) | Backlog | Compliance view reads/writes via platform client state (JS-only path) |
| req-ksi-classpref-indicator-profile | [Indicator Profile Initial Class](#indicator-profile-initial-class) | Backlog | Indicator profile picks initial active class from the preference |
| req-ksi-classpref-helpers | [Class Resolution Helpers](#class-resolution-helpers) | Backlog | `_ksi_description()` / `_CLASS_PRECEDENCE` accept a preferred class as primary lookup |
| req-ksi-classpref-finding-future | [Finding Profile Forward Hook](#finding-profile-forward-hook) | Backlog | Future class-scoped finding rollups consume the same preference |
| req-ksi-classpref-system-future | [System Page Forward Hook](#system-page-forward-hook) | Backlog | Future KSI system pages consume the same preference |

---

### Preference Registration
----
RID: `req-ksi-classpref-register`
Status: `Backlog`

The FedRAMP 20x KSI plugin registers exactly one client-state preference at startup.

#### Implementation
- Registration call lives in `Fedramp20xKsiConfig.ready()` in `plugins/fedramp_20x_ksi/apps.py`.
- Pref shape:
  ```python
  ClientStatePref(
      namespace="fedramp",
      key="class",
      allowed_values=("a", "b", "c", "d"),
      default="b",
      version=1,
      js_readable=True,
      description="Preferred FedRAMP 20x certification class for catalog displays.",
  )
  ```
- Default rationale: Class B (Low) is the v0 demo's primary working baseline. The `_CLASS_PRECEDENCE` fallback ladder in the panel module remains `("c", "b", "a", "d")` — that's the *internal* statement-resolution fallback when the user's preferred class has no variant on a given indicator, separate from the user-facing default. Changing the user-facing default is independent of the internal precedence.
- Namespace `fedramp` reserves the namespace for the FedRAMP-specific preference family. Future FedRAMP-scoped preferences (e.g. preferred control crosswalk, baseline display mode) extend this namespace under additional keys.
- Registration is idempotent in practice: the platform registry rejects duplicate registrations (per `req-web-cstate-registry-4`), so an accidental double-import surfaces immediately rather than silently overwriting.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-register-1 | Registered At Startup | Backlog | `fedramp.class` is registered via `tap_web.client_state.register_pref()` in the KSI plugin's `AppConfig.ready()`. | |
| req-ksi-classpref-register-2 | Allowed Values | Backlog | Allowed values are exactly `("a", "b", "c", "d")`. | |
| req-ksi-classpref-register-3 | Default `b` | Backlog | The registered default is `"b"`. | |
| req-ksi-classpref-register-5 | JS-Readable | Backlog | The preference is registered as `js_readable=True` so the client API can read and write it. | Cross-references [`spec-web-panel-client-state.md`](../../../tap_web/specs/spec-web-panel-client-state.md) `req-web-cstate-cookie`. |
| req-ksi-classpref-register-4 | Version 1 | Backlog | The registered version is `1`. | |

---

### Preference Switcher Placement
----
RID: `req-ksi-classpref-switcher-placement`
Status: `Backlog`

The Preference Switcher panel (specified by `req-web-cstate-switcher-panel`) is placed at the top of the `/fedramp-ksi` landing page so users can pick their working class before drilling into any specific indicator.

#### Implementation
- The `/fedramp-ksi` page layout (defined by the existing `ksi-compliance-page.grift.json` bundle) is extended to add a new `panel-id` slot above the existing compliance-view slot.
- A new `panel` entity is added to the same bundle (or a new sibling bundle, at the implementer's discretion):
  - `slug`: `fedramp-class-switcher`
  - Panel type: `client-state-switcher` (the standard `tap_web` type from `req-web-cstate-switcher-panel`)
  - `config`:
    ```json
    {
      "namespace": "fedramp",
      "key": "class",
      "label": "Working Class",
      "style": "pills",
      "value_labels": {
        "a": "Class A — Pilot",
        "b": "Class B — Low",
        "c": "Class C — Moderate",
        "d": "Class D — High"
      }
    }
    ```
- Layout shape: a single-row, single-column slot above the existing single-row, single-column compliance-view slot. Heights are content-driven; the switcher row stays compact (~48px of pills + label + padding).
- A small plugin-side CSS overlay (`static/fedramp_20x_ksi/css/page-class-switcher.css`) is permitted for visual identity (matching the FedRAMP color tokens already in use in the hero gradients), but the panel functions correctly without it.
- The switcher is **only** placed on the `/fedramp-ksi` page in v0. The indicator profile, finding profile, and future system pages do not embed the switcher themselves — they read the active value but defer the explicit-set UI to the landing page. This keeps the surface focused: users come to `/fedramp-ksi` to pick their working context, then navigate down into specific indicators / findings / systems with that context applied.

#### Development
- A future iteration may want a topbar-resident switcher visible from any page; that's a separate decision that should be motivated by a real user behavior, not a default. v0 keeps the switcher on the entry page.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-switcher-placement-1 | Switcher On Landing Page | Backlog | A `client-state-switcher` panel instance bound to `fedramp.class` is rendered on the `/fedramp-ksi` page above the compliance view. | |
| req-ksi-classpref-switcher-placement-2 | Configured For Class Pref | Backlog | The panel is configured with `namespace="fedramp"`, `key="class"`, `style="pills"`, with full class-label overrides. | |
| req-ksi-classpref-switcher-placement-3 | Click Persists | Backlog | Clicking a class pill calls `TAP.clientState.set("fedramp", "class", value)` and the value persists across page reloads. | |

---

### Compliance View Adoption
----
RID: `req-ksi-classpref-compliance-view`
Status: `Backlog`

The KSI compliance view's class selector — currently backed by an ad-hoc `localStorage` key per `req-ksi-compview-class-select` — is rewired to read/write through the platform client-state mechanism. The legacy `tap-ksi-class-selection` localStorage key is removed entirely; existing values in any browser are not preserved (greenfield rollout — see Philosophy "Why Greenfield" note below).

#### Implementation
- **Client side, JS-only.** The compliance view doesn't need server-side reads — every class variant is already in the panel's embedded JSON payload, and switching classes is a pure DOM filter / text-swap that already runs on the client. Migrating storage doesn't change that.
  - The compliance-view JS replaces direct `localStorage.getItem("tap-ksi-class-selection")` / `setItem(...)` calls with `TAP.clientState.get("fedramp", "class")` / `TAP.clientState.set("fedramp", "class", value)`.
  - Initial class on first load: read from `TAP.clientState.get("fedramp", "class")`; if `null` (no cookie), use the registered default (`"b"`). The platform JS module exposes the registered default via the discovery bridge so the panel doesn't hardcode it.
  - "All Classes" remains a transient view-only filter on this panel — it does NOT call `TAP.clientState.set()` and is not persisted. (The platform pref's allowed values are `a/b/c/d`, deliberately excluding "all".) When a user picks "All Classes" then later picks `c`, only the `c` selection writes through to the preference.
- **Refresh path:** `TAP.clientState.subscribe("fedramp", "class", callback)` per platform `req-web-cstate-refresh-subscribe`. Class changes drive in-place DOM updates; no HTMX refresh is needed.
- **Server side: no change.** The compliance view's `get_view_context()` does NOT read `request.client_state` — the panel is opting out of server-side reads per the platform's `req-web-cstate-when-server-side` rule (the data needed to render every class is already in the embedded payload, so first-paint correctness is a no-op for this panel).
- **Legacy localStorage cleanup:** the JS does `localStorage.removeItem("tap-ksi-class-selection")` unconditionally on first load after the new build ships. This removes the dead key from any browser where it was set, without preserving its value.

#### Development
- The compliance-view tests are updated to assert:
  - First load with no cookie → renders with default class (`b`).
  - First load with cookie set → renders with cookie's class.
  - Selecting a class pill writes the cookie via `TAP.clientState.set()`.
  - "All Classes" does NOT write the cookie.
  - Legacy localStorage key is removed on first load.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-compliance-view-1 | Client Reads / Writes Platform API | Backlog | The compliance-view JS uses `TAP.clientState` instead of direct `localStorage` access. | |
| req-ksi-classpref-compliance-view-2 | Subscribe-Based Refresh | Backlog | Class changes drive in-place DOM updates via `TAP.clientState.subscribe()`. | |
| req-ksi-classpref-compliance-view-3 | "All Classes" Stays Transient | Backlog | Selecting "All Classes" does not call `TAP.clientState.set()` and is not persisted. | |
| req-ksi-classpref-compliance-view-4 | No Server-Side Read | Backlog | The panel's `get_view_context()` does not read `request.client_state` — JS-only path per `req-web-cstate-when-server-side`. | |
| req-ksi-classpref-compliance-view-5 | Legacy Key Removed | Backlog | The dead `tap-ksi-class-selection` localStorage key is removed from any browser on first load after the new build ships; its prior value is not preserved. | |

---

### Indicator Profile Initial Class
----
RID: `req-ksi-classpref-indicator-profile`
Status: `Backlog`

The indicator profile page renders with the user's preferred class active on first paint — no JS toggle round-trip required for the common case.

#### Implementation
- The indicator profile is the v0 consumer that **opts in** to the platform's server-side read path per `req-web-cstate-when-server-side`. The justification: the page renders one specific class-variant statement as its primary content, and a "wrong-class statement paints, then JS swaps it" flicker would be visible on the most prominent UI element on the page. The rule's first criterion ("first-paint correctness matters") applies cleanly.
- `KsiIndicatorProfilePanelType.get_view_context()` calls `tap_web.client_state.get(request, "fedramp", "class")` to resolve the active class server-side, then uses it to pick the initial display statement and the initially-active class badge.
- Specifically:
  - `display_statement` resolution becomes:
    1. If the indicator has a direct `description` (Shape A), use it (the preference does not apply — Shape A indicators don't vary by class).
    2. Otherwise (Shape B), use `class_variants[<preferred_class>].statement` if present.
    3. Otherwise (preferred class has no variant), fall back to the existing `_CLASS_PRECEDENCE` ladder.
  - The hero's class badge row marks `<preferred_class>` as `--active` instead of always marking the first class. If the indicator does not include the preferred class in its `classes` list, fall back to the first class (the existing default), so indicators that don't apply to the user's working class still render meaningfully.
- The existing per-row JS toggle continues to work unchanged: clicking a different class badge swaps the statement with the existing fade transition. The toggle does NOT write to the client-state preference — it's a transient inspection of an alternate class, not a preference change. The user explicitly sets their preference via the Preference Switcher on `/fedramp-ksi` (or via the compliance view's class selector, which does write).
- The indicator profile panel does NOT register a `data-tap-cstate-bind` for HTMX refresh: the user's preference is applied at navigation time (i.e. when they click into an indicator), not while they're viewing it. Changing the class while sitting on an indicator profile page is an edge case that doesn't justify the additional refresh path; users who want to switch classes do so on the landing page.

#### Development
- The toggle-vs-preference distinction is documented in the panel-side code comments. It's a narrow but easy-to-confuse UX point.
- Test coverage extension:
  - Profile renders with hero's preferred class marked active on first load.
  - Profile renders with the correct class-variant statement on first load.
  - Toggling a class badge does not modify the cookie.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-indicator-profile-1 | Initial Statement Follows Preference | Backlog | The hero statement renders with the preferred class's variant on first paint when available. | |
| req-ksi-classpref-indicator-profile-2 | Initial Active Badge Follows Preference | Backlog | The hero class-badge row marks the preferred class as `--active` on first paint when applicable. | |
| req-ksi-classpref-indicator-profile-3 | Per-Row Toggle Preserved | Backlog | The existing per-row class toggle continues to work without writing to the preference. | |
| req-ksi-classpref-indicator-profile-4 | Graceful Fallback | Backlog | When the preferred class is not in the indicator's `classes` list, the panel falls back to its existing first-class default. | |

---

### Class Resolution Helpers
----
RID: `req-ksi-classpref-helpers`
Status: `Backlog`

The internal helpers that pick a class-variant statement when the indicator has multiple variants accept a preferred class as their primary input.

#### Implementation
- `_ksi_description(ksi_body, preferred_class=None)` is extended to take an optional preferred-class argument:
  - When `preferred_class` is supplied and matches a populated variant, return that variant's statement.
  - When `preferred_class` is supplied but the indicator has no variant for that class, fall through to the existing `_CLASS_PRECEDENCE` ladder.
  - When `preferred_class` is `None` (caller doesn't have a preference context), the existing precedence behavior is preserved unchanged.
- The constant `_CLASS_PRECEDENCE = ("c", "b", "a", "d")` is preserved as the fallback ladder. Its rationale (Class C as the strictest moderate baseline) was already documented in the panel module; this spec simply formalizes that the precedence is a *fallback*, not the primary selection mechanism.
- Callers in this plugin update to thread the preferred class through:
  - Indicator profile panel: passes `request.client_state["fedramp"]["class"]`.
  - Compliance view panel: passes `request.client_state["fedramp"]["class"]`.
  - Future consumers: same pattern.
- The helper signature change is backward-compatible (`preferred_class` is optional with a default of `None`), so any not-yet-updated caller continues to work with the existing precedence behavior.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-helpers-1 | Optional Preferred Class | Backlog | `_ksi_description()` accepts an optional `preferred_class` parameter without breaking existing callers. | |
| req-ksi-classpref-helpers-2 | Preferred Class Wins | Backlog | When supplied and matched, the preferred class's variant takes precedence over the `_CLASS_PRECEDENCE` ladder. | |
| req-ksi-classpref-helpers-3 | Ladder Fallback Preserved | Backlog | When the preferred class has no matching variant (or is `None`), the existing precedence behavior is preserved. | |

---

### Finding Profile Forward Hook
----
RID: `req-ksi-classpref-finding-future`
Status: `Backlog`

Today the finding model does not vary by class — findings carry a `CONCERNS_COMPLIANCE_CONTROL` edge with a `relationship_type` property, but no class-scoped fields. The finding profile (`spec-fedramp-20x-ksi-finding-profile.md`) therefore does not consume the preference today.

When (and only when) class-scoped finding rollups, severity adjustments, or class-aware rollup tables are added — under follow-on iterations of `spec-fedramp-20x-ksi-finding.md` or its descendants — the consumer reads `request.client_state["fedramp"]["class"]` via the same pattern used by the indicator profile and compliance view.

This requirement exists as a forward hook so the next person extending the finding model has a clear pointer to the platform mechanism rather than re-inventing class-aware filtering.

#### Status Details
Proposed. Will move to Approved when the relevant follow-on iteration is scoped.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-finding-future-1 | Forward-Hook Documented | Backlog | The finding profile spec carries a Future Work bullet pointing at this requirement. | |

---

### System Page Forward Hook
----
RID: `req-ksi-classpref-system-future`
Status: `Backlog`

Future KSI system pages (the asset-side view of compliance state — currently unscoped) will surface class-scoped expectations / variants for the systems they describe. Those pages are first-class consumers of `fedramp.class` from day one.

#### Status Details
Proposed. Will move to Approved when the system-page spec is drafted. The intent is captured here so the system-page spec author has a built-in pointer.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-classpref-system-future-1 | Forward-Hook Documented | Backlog | When the system-page spec lands, it cross-references this requirement and the platform spec. | |

---

## Future Work

- **Class-aware finding rollups.** When findings gain class-scoped attributes (severity adjusted by class, applicability gated by class, etc.), `req-ksi-classpref-finding-future` flips to Approved, the finding profile reads the preference, and any rollup tables filter by it.
- **Per-page override.** A future "compare classes side-by-side" view that intentionally ignores `fedramp.class` and shows all four columns simultaneously. Hooks into the platform's `req-web-cstate-spec-touchups`-tracked future per-page-override mechanism if/when that lands.
- **Topbar switcher.** Move the switcher from the `/fedramp-ksi` page header to the topbar so it's visible from anywhere in the app. Held — v0 keeps the switcher on the landing page until there's evidence users want to change classes mid-deep-dive.
- **Per-grid default override.** Allow a Grid's installation to declare a different default class (e.g. a Class D-only deployment defaults to `d`). Hooks into a future Grid-level configuration mechanism.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Backlog |  |
| Backlog | Requirement is accepted and ready to be implemented |
| Backlog |  |
| Backlog |  |
| Backlog |  |
| Backlog |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>[.sec]`

## Requirements Format

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
