# tap_web Design

## Purpose

tap_web provides the web interface for TAP. Templates, static assets, and views for dashboards and UIs that plugins can extend.

## Key Decisions

**Django templates + HTMX + Tailwind CSS.** Server-rendered with progressive enhancement. No JS build tooling. Fully offline-capable.

**Templates namespaced in app directory.** `tap_web/templates/tap_web/` avoids collisions. `APP_DIRS=True` finds them automatically.

**Static assets committed to repo.** `htmx.min.js` and `tailwind.css` are checked in. No CDN dependencies. Works offline.

**Tailwind CSS via standalone CLI.** No npm/node. Download the binary, scan templates, generate CSS. Regenerate when templates change.

**Base template provides shell.** Nav, content area, footer. Plugins extend `base.html` for consistent look.

**Plugin page registration deferred.** v0 just has the home page. Extensibility pattern comes with tap_viz or later.

## Important Features ##
**Navigation Bar** Supports plugins to register navigation links and sub-list / menus.

**Pages** Provides structure for plugins to create named pages and url paths and accept variables at the url using query parameters.  Pages can define variables that are accessible page-wide by panel on the page.

**Panel** Plugins can provide sub-page panels such as a bar chart or other component of a dashboard that can be included on pages.  The panels can access page state from query parameters and page-wide variables.

## Future Ideas ##
**Page Editor** Interactive builder for creating pages based on panels, variables, etc.

## Static Asset Workflow

**HTMX:** Download once, commit. `htmx.min.js` rarely changes.

**Tailwind CSS:** When templates change:
1. Download Tailwind standalone CLI for your platform
2. Run: `./tailwindcss -i input.css -o tap_web/static/tap_web/css/tailwind.css --content "tap_web/templates/**/*.html"`
3. Commit the generated CSS

## What Lives Here vs Other Apps

- **tap_web**: Base templates, layout shell, home page, static assets
- **tap_core**: Models and services (no templates)
- **tap_api**: API endpoints (no templates)
- **tap_viz**: Visualization pages (extends base.html)
- **Plugins**: Domain-specific pages (extend base.html)
