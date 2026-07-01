# Monorepo test-collection marker (NOT the plugin package).
#
# The plugin's importable code is the installed PEP 420 namespace package
# tap_plugin.fedramp_20x_ksi (see tap_plugin/fedramp_20x_ksi/). This __init__.py exists only so that,
# during the monorepo transition, pytest names this project dir's tests
# fully-qualified as plugins.fedramp_20x_ksi.tests.* — avoiding the orphan-`tests`-package
# collision that occurs when two package-mode plugins both expose a bare top-level
# `tests` package. It ships in NO wheel (only tap_plugin/fedramp_20x_ksi/ is packaged) and is
# removed when the plugin extracts to its own repo. Deliberately empty otherwise.
