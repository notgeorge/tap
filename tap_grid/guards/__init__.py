"""tap_grid-owned development guards.

Discovered by the harness (`tap.guards.discovery`) via the filesystem walk; each
concrete guard is one file. These protect tap_grid invariants (the service-layer
capability gateway, the Gryphon executor coverage floor), so they live with the
code they guard rather than centrally in `tap/guards/`.
"""
