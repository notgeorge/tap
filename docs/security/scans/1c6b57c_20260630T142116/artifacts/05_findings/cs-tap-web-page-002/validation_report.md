# Validation: Dynamic page and nav-index routes enumerate page metadata and panel URLs without grid.read

Disposition: valid.

Source evidence:

- tap_web/views.py:43 role=page_route_root_control
- tap_web/views.py:520 role=page_render_sink
- tap_web/views.py:716 role=nav_index_metadata_sink
- tap_web/page.py:14 role=direct_page_panel_read

Runtime evidence:

- See `artifacts/06_runtime/live_http_authz_matrix.json` for Docker-published-port capability permutations.
- See `artifacts/06_runtime/log_access_control_sample.txt` for protected-route authz-denial logs and the missing denial for the allowed panel read.

Validation notes:

Capless local-password session over host-published Docker port received 200 for page and nav-index routes; anonymous users were redirected to login and guarded graph APIs returned 403.
