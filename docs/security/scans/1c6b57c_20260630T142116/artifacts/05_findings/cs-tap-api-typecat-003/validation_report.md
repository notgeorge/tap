# Validation: Entity type catalog API ignores grid.read for authenticated no-cap users

Disposition: valid.

Source evidence:

- tap_api/routers/entity_types.py:12 role=metadata_read_sink

Runtime evidence:

- See `artifacts/06_runtime/live_http_authz_matrix.json` for Docker-published-port capability permutations.
- See `artifacts/06_runtime/log_access_control_sample.txt` for protected-route authz-denial logs and the missing denial for the allowed panel read.

Validation notes:

Capless local-password session received 200 for /api/v1/entity-types/ and 403 for /api/v1/entities/.
