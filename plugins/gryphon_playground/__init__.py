# Monorepo test-collection marker (NOT the plugin package). The plugin's importable
# code is the installed PEP 420 namespace package tap_plugin.gryphon_playground
# (tap_plugin/gryphon_playground/). The test-harness subpackages that STAY at this
# project-dir level — gridkin/, tests/, fixtures/, scenarios/, expected/ — resolve
# their `plugins.gryphon_playground.gridkin.*` imports through this marker; they do
# NOT ship in the wheel. This also names this dir's tests fully-qualified as
# plugins.gryphon_playground.tests.* during the monorepo transition, avoiding the
# orphan-tests collision when two package-mode plugins expose a bare top-level tests
# package. Ships in NO wheel; removed on repo extraction. Deliberately empty otherwise.
