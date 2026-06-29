"""tap_health — the instance's health domain.

Owns the first-party probe registry, the structured `HealthReport`, the
`run_health()` service entrypoint, the `manage.py health` command, and the
boot-time provisioning system check. See `specs/spec-tap-health-v0.md`.
"""
