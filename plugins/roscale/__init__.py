# Monorepo test-collection marker (NOT the plugin package). The plugin's importable
# code is the installed PEP 420 namespace package tap_plugin.roscale (tap_plugin/roscale/).
# This exists only so pytest names this project dir's tests fully-qualified as
# plugins.roscale.tests.* during the monorepo transition, avoiding the orphan-tests
# collision when two package-mode plugins both expose a bare top-level tests package.
# Ships in NO wheel; removed on repo extraction. Deliberately empty otherwise.
