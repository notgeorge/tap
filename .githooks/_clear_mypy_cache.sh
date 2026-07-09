# Shared helper (sourced by the post-merge / post-checkout / post-rewrite hooks).
#
# Drop mypy's incremental cache when the working tree's module structure may have
# changed underneath it — merge, pull, branch checkout, rebase, amend. mypy's
# content-hash invalidation does NOT catch a moved/deleted module (a tree-structure
# change, not an edit), so a stale .mypy_cache emits false `import-untyped` /
# missing-module errors in the mypy guard (tap/tests/test_guards.py). This bit the
# github_core extraction on tip a94bc98c; clearing on the actual triggers keeps
# mypy's incremental speed on ordinary edits while never trusting a stale graph.
#
# The promote gate (scripts/promote-to-main.sh) clears the cache too, as a
# hook-independent fail-safe on the branch that advances origin/main.
#
# Sourced, so it only defines a function — no `exit`.
clear_mypy_cache() {
    root="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0
    [ -n "$root" ] && [ -d "$root/.mypy_cache" ] && rm -rf "$root/.mypy_cache"
    return 0
}
