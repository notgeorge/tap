# tap_viz Design

## Key Decisions

**cytoscape.js plus extensions.**  All graph visualizations will leverage cytoscape.js with the extensios for grid-guide, popper, clipboard, undo-redo 

**Layouts are Entities.**  Layouts should be self-contained entities with name, description being part of the db columns and layout-specific logic stored in cytoscape-ingestible json

**Use API for Edge & Entity Lookup.**  It's there, use it.  Do not rely on HTMX at this point.

**Default Landing Page Panel.**  Update the default landing page with a panel showing all the current entities in a cytoscape view using the grid layout.

## Important Features ##
**Zoomable Panels**  Plugins can create panels on pages that show a cytoscape grid with a specific layout applied that users can zoom, pan on.  These are READ ONLY.

**Layout Maker**  Page where users can create and save layout entities using cytoscape preset layout mode.  Editor includes standard buttons to add (from existing nodes & edges), create new nodes and edges (with appropriate modal or sidebar to set values), and position nodes in a specific format (align horizontal, vertical, distribute). Buttons exist for common cytoscape layouts like grid

**Edge Editing Mode**  On the layout page users can press a button to enter a mode that uses 

## Future Ideas - Do Not Implement Now ##
**Search to Add Nodes**  Once search / query entities have been defined, allow users to perform a search to gather all nodes and edges for use in the layout.

**Compound Nodes & Edges** Once parent-child relationships are defined on edge types layouts will automatically place child entities inside their parents with.  Edge drawing mode will support compound edges (a standard in-coming edge, node, out-going edge).

**Icon Support** Once Icon support is a first-class capability use icons displayed inside nodes, on edges, and in the corners of parent / compound nodes.


## What Lives Here vs Other Apps

- **tap_web**: Base templates, layout shell, home page, static assets
- **tap_core**: Models and services (no templates)
- **tap_api**: API endpoints (no templates)
- **tap_viz**: Visualization pages (extends base.html)
- **Plugins**: Domain-specific pages (extend base.html)
