---
name: get-aws-icons
description: Source the official AWS Architecture icon for an aws_core service model's ENTITY_ICON key (or backfill every missing/placeholder icon) and install it normalized to the repo's icon convention. Use right after adding an AWS-service BaseModel to aws_core, or to replace hand-drawn placeholder icons.
allowed-tools: Read Write Edit WebFetch Bash(mktemp *) Bash(curl *) Bash(unzip *) Bash(ls *) Bash(find *) Glob Grep
argument-hint: "[<icon-key> | --all-missing]"
---

# Get AWS Icons

You are sourcing real AWS Architecture icons for `aws_core` service models so the
grid renders accurate, recognizable AWS iconography instead of hand-drawn
placeholders. This is the repeatable answer to "a new AWS service model needs an
icon" — never hand-author AWS service glyphs again.

## When this runs

- Automatically picked up by the `add-model` flow: after adding an AWS-service
  BaseModel to `aws_core`, run this for its `ENTITY_ICON` key.
- Manually, to backfill: `--all-missing` finds every `ENTITY_ICON` declared by
  an `aws_core` model that has no real icon yet (including placeholders).

This skill is the **focused icon-sourcing primitive**. The broader
`refresh-aws-catalog` skill (regions/AZs + bulk icon maintenance) remains; this
one is the sharp tool model-creation chains to.

## The icon pack (downloaded on demand to tmp — never git, never persisted)

The official **AWS Architecture Icons** pack is not committed and not kept
locally. This skill downloads it fresh to an ephemeral temp dir each run, uses
it, and lets it be discarded. Re-downloading on every new-model run is an
accepted cost (operator decision) — it keeps a licensed asset pack out of git
entirely and needs zero manual provisioning. Only the individual normalized
per-model SVGs are ever committed (the existing `static/aws_core/icons/*.svg`
pattern).

Resolve the pack for this run:

1. **Fast path (optional):** if `$AWS_ICONS_PACK` points at an already-unzipped
   pack root, use it. Never required; just saves a re-download for someone
   iterating on many models at once.
2. **Default — download to tmp:**
   - `WORK="$(mktemp -d)"` — ephemeral; everything below lives here and is
     **never** copied or moved under the repo, never `git add`-ed.
   - `WebFetch` `https://aws.amazon.com/architecture/icons/` to resolve the
     current **SVG Asset Package** zip URL. AWS re-releases periodically and
     the versioned URL changes — resolve it from the page each run; do not
     hardcode a URL that will rot.
   - `curl -L -o "$WORK/pack.zip" "<resolved zip url>"` then
     `unzip -q "$WORK/pack.zip" -d "$WORK/pack"`.
   - Use `$WORK/pack` as the pack root for Steps 2–3.

The dev environment has full internet. If the download fails, diagnose from the
actual `curl`/`WebFetch` error — do **not** assume a sandbox/no-network
condition. Do not hand-draw an icon as a fallback; a short-lived hand-drawn
placeholder is acceptable ONLY to keep plugin validation green while a genuine,
diagnosed network failure is resolved, and must be flagged as temporary.

## Step 1: Resolve the target icon keys

- Single key: the argument (e.g. `aws-cloudfront`).
- `--all-missing`: read every model under `plugins/aws_core/models/`, collect
  `ENTITY_ICON` values, and select those whose `static/aws_core/icons/<key>.svg`
  is absent **or** is a hand-drawn placeholder. Detect placeholders by absence
  of the official-pack `<title>` marker (real pack icons carry a title like
  `Icon-Architecture/64/Arch_AWS-Lambda_64`; placeholders do not).

Known placeholders to replace on first real run: `aws-cloudfront`,
`aws-cloudwatch`, `aws-eventbridge` (hand-drawn during the boto3 collector
model-gap work).

## Step 2: Map the icon key to the pack file

The pack organizes SVGs as `Arch_<Service>_<size>.svg` (e.g.
`Arch_Amazon-CloudFront_64.svg`, `Arch_AWS-Lambda_64.svg`,
`Arch_Amazon-CloudWatch_64.svg`, `Arch_Amazon-EventBridge_64.svg`) inside
category folders. From the kebab `aws-<service>` key, derive the service token
and locate the best `Arch_*_64.svg` (prefer 64; fall back to the largest
available). When ambiguous, list candidates and pick the one whose service name
matches the model's `ENTITY_NAME`; if still ambiguous, ask rather than guess.

## Step 3: Normalize to the repo convention

Match the **existing shipped icons exactly** — open `aws-lambda.svg` /
`aws-route53.svg` as the reference exemplars and conform:

- 80×80 `viewBox`, `width`/`height` 80px, the AWS category background
  `<rect>` in the service's official category color, white glyph.
- Preserve a `<title>` of the form `Icon-Architecture/64/Arch_<Service>_64`
  (this is also the placeholder-vs-real detector in Step 1).
- Strip pack cruft (extra metadata, ids that collide) but keep it a single
  clean self-contained SVG.

**Convention note (known spec drift — do not silently fight it):**
`tap_grid/specs/spec-grid-icon.md` and `spec-aws-core-catalog`
(`req-aws-catalog-icons`) state 24×24 `currentColor`. Every shipped
`aws_core` icon is in fact 80×80 AWS-brand-colored (the official pack). For
AWS service recognizability and consistency with the existing 30+ icons, this
skill **deliberately targets the shipped 80×80 branded convention** — this is
the "vendor brand colors require explicit justification" case from the
`add-model` icon step, and the justification is: AWS icons must be instantly
recognizable in the demo and visually consistent with their peers. The
icon-spec-vs-reality contradiction is a separate, pre-existing reconcile (flag
it; out of scope here).

## Step 4: Install and validate

- Write to `plugins/aws_core/static/aws_core/icons/<key>.svg` (overwrite any
  placeholder).
- Run plugin validation at `loads` (icon existence/format is checked there):
  `scripts/dc exec web uv run python manage.py validate_plugin plugins/aws_core --level loads`
- Report: which keys were sourced, from which pack files, which placeholders
  were replaced, and any keys that still need a pack file (missing-pack case).

## Step 5: Set the node body + border to match the icon's brand color

The icon's first non-white `<rect fill>` is its AWS category color — the
purple of Networking & Content Delivery, the orange of Compute, the green
of Storage, the red of Security/IAM, the pink of Management & Governance,
etc. Every aws_core model's `DEFAULT_DISPLAY.tap_viz.colors` triple must
track that color so the *whole node cell* — body, border, label — reads
as the same AWS service from across the canvas, not just the icon glyph.
Without this the body falls back to indigo or a hand-picked color that
fights the icon; with it, the eye picks up the service category before
reading the label. Originating case (2026-05-26): 41 aws_core models all
rendering with mismatched bodies — `aws_ec2_instance` was blue while its
icon was Compute-orange, `aws_route53_zone` had purple-but-wrong-shade,
etc.

The triple is computed deterministically from the brand:

```python
DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
    "tap_viz": {
        "shape": "rectangle",   # or "round-rectangle" — preserve whatever the model already declares
        "colors": {
            "fill":   "<lightened brand>",   # body  — brand blended ~72% toward white
            "border": "<brand>",              # border — the icon's category color, verbatim
            "label":  "<darkened brand>",    # text  — brand blended ~72% toward black
        },
    },
}
```

Extract the brand and compute the triple:

```python
import re
from pathlib import Path

ICON = Path("plugins/aws_core/static/aws_core/icons/<key>.svg")
fills = re.findall(r'fill="(#[0-9A-Fa-f]{6})"', ICON.read_text())
brand = next(c for c in fills if c.upper() != "#FFFFFF").upper()

def _rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def _hex(r, g, b): return f"#{r:02X}{g:02X}{b:02X}"
def lighten(c, t=0.72):
    r, g, b = _rgb(c); return _hex(int(r+(255-r)*t), int(g+(255-g)*t), int(b+(255-b)*t))
def darken(c, t=0.72):
    r, g, b = _rgb(c); return _hex(int(r*(1-t)), int(g*(1-t)), int(b*(1-t)))

print(f'  brand={brand}  fill={lighten(brand)}  border={brand}  label={darken(brand)}')
```

Apply to the model's `DEFAULT_DISPLAY.tap_viz.colors`. The shape stays
whatever the model already declared (`rectangle` for most aws_core models;
`round-rectangle` for the container-ish ones — `aws_account`, `aws_region`,
`vpc`, `subnet`).

When this step is part of the new-model flow (right after icon install),
the model ships with the right colors from day one. To bulk-realign every
aws_core model's colors against its current icon (e.g. after the pack ships
new colors, or to fix accumulated drift), the same compute logic loops over
`plugins/aws_core/models/*.py`, reads each `ENTITY_ICON`, extracts the
brand from the corresponding icon SVG, and replaces the `"colors": {...}`
line in the model file. See the originating commit's bulk script for a
working version.

## Step 6: Leave it discoverable

This skill is referenced from `add-model` Step 7 and the `aws_core` README so
future AWS-service-model creation picks it up automatically. If you add a new
discoverability surface, keep those pointers in sync.

## Common mistakes (do not commit any of these)

- **Hand-drawing an AWS glyph.** That is exactly what this skill exists to end.
  A diagnosed network failure → fix the fetch, not a fresh placeholder.
- **Committing the pack or the zip.** Only the individual normalized per-model
  SVGs are committed; the downloaded pack lives only in the `mktemp` dir and is
  discarded.
- **Following the 24×24/`currentColor` spec literally.** It contradicts every
  shipped icon; match the 80×80 branded reality (see Step 3 note).
- **Guessing the pack file on an ambiguous service name.** List candidates and
  reconcile against `ENTITY_NAME`; ask if still unclear.
- **Stopping at the icon install and skipping the color triple (Step 5).** The
  body has to match the icon — half the visual story is the cell color, not
  just the glyph inside it. An icon-only install leaves the model rendering as
  an indigo box with a branded glyph that doesn't reinforce its AWS service.
