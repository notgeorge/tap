---
spec: ../../tap_web/specs/spec-web-tailwind-pipeline-BACKLOG.md
audience: [llm, developer]
covers:
  - ../../tap_web/specs/spec-web-tailwind-pipeline-BACKLOG.md
  - req-web-tailwind-pipeline-manual-fallback
update-triggers:
  - the Tailwind CLI invocation changes
  - the scanned content paths change
  - the compiled stylesheet path (`tap_web/static/tap_web/css/tailwind.css`) moves
  - an automated pipeline lands (then this doc is superseded by a build-step doc)
assumes:
  - macOS or Linux dev environment with network access for `npx`
  - the reader has just added a Tailwind utility class to a template and either sees the layout break or wants to head off the break before pushing
provides: |
  Reader knows when the manual Tailwind rebuild is required, how to run it,
  how to verify the output picked up the new class, and how to recognize the
  symptom that signals "you forgot to rebuild."
---

# Rebuilding the Tailwind CSS Stylesheet

## Status

The compiled stylesheet at `tap_web/static/tap_web/css/tailwind.css` is currently a hand-built artifact checked into the repo. There is no automated rebuild — adding a utility class to a template does not regenerate the CSS. This doc covers the manual rebuild flow until the automated pipeline lands (tracked in `tap_web/specs/spec-web-tailwind-pipeline-BACKLOG.md`).

## When to rebuild

Rebuild any time you add a utility class to a template that wasn't already present in another template. Common signals:

- New responsive-prefix class (`sm:`, `md:`, `lg:`) when no other template uses the same prefix-utility combination.
- New grid utilities (`grid-cols-3`, `gap-4`, `col-span-2`) — these are easy to miss because `.grid` alone is in the compiled output but the column / span / gap variants typically are not.
- New color shade not used elsewhere (e.g., `bg-amber-50` when the rest of the codebase only uses `amber-100` and `amber-200`).
- A new template directory under a path the Tailwind config doesn't scan. The current config only scans `tap_web/templates` and `tap_viz/templates` — plugin templates under `plugins/*/templates` are not covered, so utilities used only there will never be in the compiled output.

If unsure, grep first (see verify step below). It's faster to grep than to rebuild speculatively.

## The symptom of forgetting to rebuild

The HTML attribute is set correctly on the element — browser dev tools show `class="sm:grid sm:grid-cols-3 sm:gap-4 ..."` — but the computed style doesn't reflect the class. No `display: grid`. No grid template columns. The element renders as if the class weren't there.

This is *not* a CSS specificity problem, a media-query problem, or a Tailwind config problem. The rule simply doesn't exist in `tailwind.css`. Confirm by grepping the compiled file:

```
grep "sm\\\\:grid-cols-3" tap_web/static/tap_web/css/tailwind.css
```

If grep finds nothing, the rule is missing and the rebuild was skipped.

## Rebuild procedure

The repo's `tailwind.config.js` declares the content paths. The current canonical invocation is:

```
npx -y @tailwindcss/cli@3 \
    -c tailwind.config.js \
    -i tap_web/static/tap_web/css/tailwind-input.css \
    -o tap_web/static/tap_web/css/tailwind.css \
    --minify
```

Notes:

- The `@tailwindcss/cli@3` pin matches the v3 output format already in the repo. Bumping the major version produces a different output shape — diff carefully if you do.
- If `tailwind-input.css` doesn't exist yet, it's the standard three-line file with `@tailwind base; @tailwind components; @tailwind utilities;`. Create it on first run.
- The `--minify` flag matches the current artifact's shape. Drop it for human-readable output while iterating.
- The command runs from the repo root, not from inside the Docker container.

If you don't have `npx` available, the precompiled standalone binary from the Tailwind releases page is a no-Node alternative.

## Verifying the rebuild

After rebuilding:

1. Grep for the new utility:
   ```
   grep "sm\\\\:grid-cols-3" tap_web/static/tap_web/css/tailwind.css
   ```
   It should find at least one match. If not, the class is still missing — either the template path isn't scanned, or the class spelling doesn't exactly match what's in the template.

2. Reload the page in the browser with a hard refresh (Cmd-Shift-R) — the cached old stylesheet otherwise sticks.

3. Open dev tools, inspect the element, and confirm the computed style now reflects the class.

## Coverage gap: plugin templates

The current `tailwind.config.js` does not scan `plugins/*/templates`. Until that's fixed (see the BACKLOG spec's `req-web-tailwind-pipeline-content-paths`), utility classes used only inside plugin templates won't appear in `tailwind.css` no matter how many times you rebuild.

Workarounds:

- Use the same utility somewhere in `tap_web/templates` or `tap_viz/templates` so Tailwind's scanner sees it.
- Temporarily edit `tailwind.config.js` locally to add `./plugins/**/templates/**/*.html` to the content array. Don't commit the temp config — that's the BACKLOG spec's job to settle properly.
- Use inline styles for layout-critical classes that can't wait for the config change (e.g., `style="display: grid; grid-template-columns: 1fr 2fr;"`).

## Committing the rebuilt artifact

If your template change required a rebuild, commit `tailwind.css` in the same commit as the template change. Reviewers expect the artifact and the template to be consistent at every revision.
