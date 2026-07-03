"""tap_cares-owned development guards.

Discovered by the harness (`tap.guards.discovery`) via the filesystem walk; each
concrete guard is one file in this package. These protect tap_cares invariants
(collector scheduling, record-site tokens, the single recurring task), so they live
with the code they guard rather than centrally in `tap/guards/`.
"""
