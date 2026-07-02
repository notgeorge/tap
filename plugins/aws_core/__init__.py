# Monorepo test-collection marker (NOT the plugin package). The plugin's importable
# code is the installed PEP 420 namespace package tap_plugin.aws_core (tap_plugin/aws_core/).
# This exists only so pytest names this project dir's tests fully-qualified as
# plugins.aws_core.tests.* during the monorepo transition, avoiding the orphan-tests
# collision when two package-mode plugins both expose a bare top-level tests package.
# Ships in NO wheel; removed on repo extraction. Deliberately empty otherwise.
