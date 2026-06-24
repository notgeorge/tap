"""tap_boot — the TAP bootloader.

All boot logic lives here: the ``manage.py boot`` command, profile handling,
the boot context (``tap_bootloader`` actor resolution + per-run state), phase
sequencing, and action logging. ``tap_boot`` sits first in ``INSTALLED_APPS``
and depends on the capability apps, calling their reusable, boot-agnostic ops
(``tap_auth.sync_auth`` / ``ensure_initial_admin``, the ``tap_grid`` service
layer, ``tap_cares`` collector firing / reconcile, the plugin GRIFT import
path). No boot logic lives in ``tap_grid``/``tap_auth``/``tap_cares``/
``tap_plugins`` — the dependency direction is one-way (``tap_boot → everything``).

Spec: specs/spec-tap-boot-v0.md (req-boot-app).
"""
