# Monorepo test-collection marker (NOT the plugin package).
#
# The plugin's importable code is the installed PEP 420 namespace package
# tap_plugin.github_core (see tap_plugin/github_core/). This __init__.py exists only so that,
# during the monorepo transition, pytest names this project dir's tests
# fully-qualified as plugins.github_core.tests.* — avoiding the orphan-`tests`-package
# collision that occurs when two package-mode plugins both expose a bare top-level
# `tests` package. It ships in NO wheel (only tap_plugin/github_core/ is packaged) and is
# removed when the plugin extracts to its own repo. Deliberately empty otherwise.
