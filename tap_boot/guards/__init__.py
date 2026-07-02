"""tap_boot-owned development guards.

Discovered by the harness (`tap.guards.discovery`) via the filesystem walk. These
protect boot invariants, so they live with tap_boot. They are also run by the boot
path itself — a guard is just an object with `check()`; the same class the harness
runs per-commit can be invoked directly by the pre-boot gate before startup.
"""
