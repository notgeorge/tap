# Validation: Generic panel endpoint lets no-cap users read panel content and request-selected entity fields

Disposition: valid.

Source evidence:

- tap_web/views.py:75 role=root_control_and_render_sink
- tap_web/panels/viewer_panel/__init__.py:108 role=request_selected_object_read_sink
- tap_web/templates/tap_web/panels/text_panel.html:1 role=panel_content_render_sink

Runtime evidence:

- See `artifacts/06_runtime/live_http_authz_matrix.json` for Docker-published-port capability permutations.
- See `artifacts/06_runtime/log_access_control_sample.txt` for protected-route authz-denial logs and the missing denial for the allowed panel read.

Validation notes:

Capless local-password session over host-published Docker port received 200 for /panel/... and 200 for a ViewerPanel with entity_id/entity_type query parameters, while /object/page/... returned 403.
