/**
 * Command palette per req-web-nav-command-palette.
 *
 * Cmd-K / Ctrl-K (or the chrome affordance button) opens a centered modal
 * with a fuzzy-search input. Results stream from /__nav-index.json on
 * first open and cache for the session. Clicking a result (or pressing
 * Enter on the highlighted row) navigates. Esc / click-outside closes.
 *
 * v0 scope: registered Pages only. Entities, recent visits, and platform
 * commands are spec'd as later additions; this MVP just answers the
 * "what pages exist?" question that drove the rollout.
 */
(function () {
  "use strict";

  let navIndex = null;       // Cached nav-index data; populated on first open.
  let modal = null;          // The palette modal element.
  let input = null;          // The search input.
  let resultsList = null;    // The results list element.
  let selectedIndex = 0;     // Currently highlighted result.
  let currentResults = [];   // Most recent result set.

  // -------------------------------------------------------------------------
  // Fuzzy match scoring.
  // -------------------------------------------------------------------------
  // For an empty query: return all pages, sorted alphabetically by URL.
  // For a non-empty query: tiered scoring — exact > prefix > substring >
  // subsequence > URL substring > description substring. Top 10 returned.

  function isSubsequence(needle, haystack) {
    let i = 0;
    for (const c of haystack) {
      if (c === needle[i]) i++;
      if (i === needle.length) return true;
    }
    return false;
  }

  function scorePage(page, q) {
    const name = (page.name || "").toLowerCase();
    const url = (page.url || "").toLowerCase();
    const desc = (page.description || "").toLowerCase();
    if (name === q) return 1000;
    if (name.startsWith(q)) return 800;
    if (name.includes(q)) return 600;
    if (isSubsequence(q, name)) return 400;
    if (url.includes(q)) return 300;
    if (desc.includes(q)) return 100;
    return 0;
  }

  function rankPages(query) {
    if (!navIndex) return [];
    if (!query) {
      // Empty query — show every page, alphabetically by URL.
      return navIndex.pages
        .slice()
        .sort((a, b) => a.url.localeCompare(b.url));
    }
    const q = query.toLowerCase();
    const scored = navIndex.pages
      .map((page) => ({ score: scorePage(page, q), page }))
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score);
    return scored.slice(0, 10).map((entry) => entry.page);
  }

  // -------------------------------------------------------------------------
  // Modal DOM.
  // -------------------------------------------------------------------------

  function createModal() {
    const overlay = document.createElement("div");
    overlay.className = "tap-palette-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Command palette");

    const box = document.createElement("div");
    box.className = "tap-palette-box";

    input = document.createElement("input");
    input.type = "text";
    input.className = "tap-palette-input";
    input.setAttribute("placeholder", "Search pages…");
    input.setAttribute("aria-label", "Search pages");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("autocorrect", "off");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("spellcheck", "false");

    resultsList = document.createElement("ul");
    resultsList.className = "tap-palette-results";
    resultsList.setAttribute("role", "listbox");

    box.appendChild(input);
    box.appendChild(resultsList);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    // Click-outside dismisses.
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closePalette();
    });
    input.addEventListener("input", () => renderResults());
    input.addEventListener("keydown", handleKeyNav);

    return overlay;
  }

  function renderResults() {
    const query = input.value;
    currentResults = rankPages(query);
    resultsList.innerHTML = "";
    selectedIndex = 0;

    if (currentResults.length === 0) {
      const li = document.createElement("li");
      li.className = "tap-palette-empty";
      li.textContent = navIndex ? "No pages match" : "Loading pages…";
      resultsList.appendChild(li);
      return;
    }

    currentResults.forEach((page, i) => {
      const li = document.createElement("li");
      li.className = "tap-palette-result" + (i === 0 ? " is-selected" : "");
      li.setAttribute("role", "option");
      li.setAttribute("data-url", page.url);

      const name = document.createElement("span");
      name.className = "tap-palette-result-name";
      name.textContent = page.name || page.url;

      const url = document.createElement("span");
      url.className = "tap-palette-result-url";
      url.textContent = page.url;

      li.appendChild(name);
      li.appendChild(url);

      li.addEventListener("click", () => navigate(page.url));
      li.addEventListener("mouseenter", () => {
        selectedIndex = i;
        updateSelection();
      });

      resultsList.appendChild(li);
    });
  }

  function updateSelection() {
    const items = resultsList.querySelectorAll(".tap-palette-result");
    items.forEach((item, i) => {
      if (i === selectedIndex) item.classList.add("is-selected");
      else item.classList.remove("is-selected");
    });
    if (items[selectedIndex]) {
      items[selectedIndex].scrollIntoView({ block: "nearest" });
    }
  }

  function handleKeyNav(e) {
    if (e.key === "Escape") {
      closePalette();
      e.preventDefault();
    } else if (e.key === "ArrowDown") {
      selectedIndex = Math.min(selectedIndex + 1, currentResults.length - 1);
      updateSelection();
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      selectedIndex = Math.max(selectedIndex - 1, 0);
      updateSelection();
      e.preventDefault();
    } else if (e.key === "Enter") {
      const page = currentResults[selectedIndex];
      if (page) navigate(page.url);
      e.preventDefault();
    }
  }

  function navigate(url) {
    window.location.href = url;
  }

  async function loadNavIndex() {
    if (navIndex) return;
    try {
      const response = await fetch("/__nav-index.json");
      navIndex = await response.json();
    } catch (e) {
      console.error("Failed to load nav index:", e);
      navIndex = { pages: [] };
    }
  }

  async function openPalette() {
    if (!modal) modal = createModal();
    modal.classList.add("is-open");
    input.value = "";
    // Initial render gives the loading-state message until fetch resolves.
    renderResults();
    input.focus();
    if (!navIndex) await loadNavIndex();
    renderResults();
  }

  function closePalette() {
    if (modal) modal.classList.remove("is-open");
  }

  // -------------------------------------------------------------------------
  // Wire Cmd-K / Ctrl-K and the chrome affordance.
  // -------------------------------------------------------------------------

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      openPalette();
      e.preventDefault();
    }
  });

  function wireAffordance() {
    const btn = document.querySelector("[data-tap-palette-affordance]");
    if (btn) {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        openPalette();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireAffordance);
  } else {
    wireAffordance();
  }
})();
