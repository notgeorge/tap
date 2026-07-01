// Workflow Catalog — click to expand/collapse one panel at a time.
// Spec: plugins/github_core/specs/spec-github-core-repo-landing-page-v0.md
// (req-github-core-repo-page-catalog-4).
(function () {
  "use strict";

  function init(root) {
    root.querySelectorAll(".ghc-catalog-summary").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var item = btn.closest(".ghc-catalog-item");
        if (!item) return;
        var wasOpen = item.classList.contains("is-open");
        // Collapse all siblings (single-expand-at-a-time per spec).
        var list = item.closest(".ghc-catalog-list");
        if (list) {
          list.querySelectorAll(".ghc-catalog-item.is-open").forEach(function (other) {
            other.classList.remove("is-open");
          });
        }
        if (!wasOpen) item.classList.add("is-open");
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { init(document); });
  } else {
    init(document);
  }
})();
