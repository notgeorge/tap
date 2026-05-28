/**
 * Breadcrumb interactions per req-web-nav-segment-interactions.
 *
 * Three behaviors on top of the static breadcrumb chrome:
 *
 *   1. Click the chevron between two segments → sibling popover for the
 *      segment AFTER the chevron. Lists pages at that hierarchy level.
 *   2. Alt-click a segment (or its preceding chevron) → column-view
 *      explorer showing siblings at every breadcrumb level from root
 *      to the current page.
 *   3. Window-width overflow → middle of the breadcrumb collapses to
 *      an interactive ellipsis (`…`); clicking the ellipsis reveals
 *      the hidden segments in a popover.
 *
 * Data source: /__nav-index.json, fetched once and cached for the
 * page lifetime. Same cache shape as palette.js but fetched
 * independently (browser HTTP cache makes the second request cheap).
 */
(function () {
  "use strict";

  let navIndex = null;
  let activePopover = null;

  // -------------------------------------------------------------------------
  // Nav-index + tree derivation.
  // -------------------------------------------------------------------------

  async function loadNavIndex() {
    if (navIndex) return navIndex;
    try {
      const response = await fetch("/__nav-index.json");
      navIndex = await response.json();
    } catch (e) {
      console.error("Failed to load nav index:", e);
      navIndex = { pages: [] };
    }
    return navIndex;
  }

  /** Return pages at `depth` whose breadcrumb[depth-1].url === parentUrl. */
  function pagesAtDepth(parentUrl, depth) {
    if (!navIndex) return [];
    const seen = new Set();
    const out = [];
    navIndex.pages.forEach((p) => {
      if (p.breadcrumb.length <= depth) return;
      if (p.breadcrumb[depth - 1].url !== parentUrl) return;
      const seg = p.breadcrumb[depth];
      if (seen.has(seg.url)) return;
      seen.add(seg.url);
      out.push(seg);
    });
    return out.sort((a, b) => (a.label || a.url).localeCompare(b.label || b.url));
  }

  /** For URL X, return X's siblings — pages at X's depth with same parent. */
  function siblingsOf(url) {
    if (!navIndex) return [];
    const me = navIndex.pages.find((p) => p.url === url);
    if (!me) return [];
    const depth = me.breadcrumb.length - 1;
    if (depth === 0) return [];
    const parentUrl = me.breadcrumb[depth - 1].url;
    return pagesAtDepth(parentUrl, depth);
  }

  /** For URL X, return columns — one per breadcrumb level, each listing siblings. */
  function columnsFor(url) {
    if (!navIndex) return [];
    const me = navIndex.pages.find((p) => p.url === url);
    if (!me) return [];
    const cols = [];
    for (let depth = 1; depth < me.breadcrumb.length; depth++) {
      const parentUrl = me.breadcrumb[depth - 1].url;
      cols.push({
        currentUrl: me.breadcrumb[depth].url,
        items: pagesAtDepth(parentUrl, depth),
      });
    }
    return cols;
  }

  // -------------------------------------------------------------------------
  // Popover infrastructure.
  // -------------------------------------------------------------------------

  function dismissPopover() {
    if (!activePopover) return;
    activePopover.remove();
    activePopover = null;
    document.removeEventListener("click", outsideClickHandler);
    document.removeEventListener("keydown", escHandler);
  }

  function outsideClickHandler(e) {
    if (activePopover && !activePopover.contains(e.target)) dismissPopover();
  }

  function escHandler(e) {
    if (e.key === "Escape") dismissPopover();
  }

  function armOutsideClick() {
    // Defer to next tick so the same click that opened the popover doesn't
    // immediately dismiss it.
    setTimeout(() => {
      document.addEventListener("click", outsideClickHandler);
      document.addEventListener("keydown", escHandler);
    }, 0);
  }

  // -------------------------------------------------------------------------
  // Chevron sibling popover.
  // -------------------------------------------------------------------------

  function showSiblingPopover(anchor, url) {
    dismissPopover();
    const siblings = siblingsOf(url);
    if (siblings.length === 0) return;

    const popover = document.createElement("ul");
    popover.className = "tap-bc-popover";
    popover.setAttribute("role", "menu");

    siblings.forEach((s) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.className = "tap-bc-popover-item" + (s.url === url ? " is-current" : "");
      a.href = s.url;
      a.textContent = s.label || s.url;
      a.setAttribute("role", "menuitem");
      li.appendChild(a);
      popover.appendChild(li);
    });

    const rect = anchor.getBoundingClientRect();
    popover.style.position = "fixed";
    popover.style.top = `${rect.bottom + 6}px`;
    popover.style.left = `${rect.left}px`;
    document.body.appendChild(popover);
    activePopover = popover;
    armOutsideClick();
  }

  // -------------------------------------------------------------------------
  // Column-view explorer (alt-click).
  // -------------------------------------------------------------------------

  function showColumnView(_anchor, url) {
    dismissPopover();
    const cols = columnsFor(url);
    if (cols.length === 0) return;

    const wrap = document.createElement("div");
    wrap.className = "tap-bc-columns";
    wrap.setAttribute("role", "navigation");
    wrap.setAttribute("aria-label", "Page hierarchy");

    cols.forEach((col) => {
      const ul = document.createElement("ul");
      ul.className = "tap-bc-column";
      col.items.forEach((it) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        const isOnPath = it.url === col.currentUrl;
        a.className = "tap-bc-column-item" + (isOnPath ? " is-on-path" : "");
        a.href = it.url;
        a.textContent = it.label || it.url;
        li.appendChild(a);
        ul.appendChild(li);
      });
      wrap.appendChild(ul);
    });

    wrap.style.position = "fixed";
    wrap.style.top = "44px";
    wrap.style.left = "1rem";
    wrap.style.right = "1rem";
    document.body.appendChild(wrap);
    activePopover = wrap;
    armOutsideClick();
  }

  // -------------------------------------------------------------------------
  // Overflow truncation (Phase 7 — req-web-nav-breadcrumb-header-4).
  // -------------------------------------------------------------------------

  function applyOverflowTruncation() {
    const ol = document.querySelector('nav[aria-label="Breadcrumb"] ol');
    if (!ol) return;

    // Reset prior truncation state so re-evaluation sees real widths.
    ol.querySelectorAll(".tap-bc-collapsed").forEach((el) => el.remove());
    ol.querySelectorAll("li[data-tap-collapsible]").forEach((li) => {
      li.style.display = "";
    });

    if (ol.scrollWidth <= ol.clientWidth) return;

    // Identify collapsible segments — every li except the first (home),
    // its trailing chevron, and the last two (parent + current) with
    // their leading chevrons.
    const lis = Array.from(ol.children);
    if (lis.length <= 5) return; // Nothing meaningful to collapse.

    // Layout convention from the template: segment li, chevron li,
    // segment li, chevron li, ... so to keep [home, ..., parent, current]
    // we keep lis[0..1] (home + first chevron) and the last 4 (parent
    // chevron + parent + current chevron + current).
    const keepHead = 2;
    const keepTail = 4;
    const collapsibleLis = lis.slice(keepHead, lis.length - keepTail);
    if (collapsibleLis.length === 0) return;

    // Mark + hide collapsibles; remember the URLs they covered for the
    // ellipsis popover.
    const collapsedUrls = [];
    collapsibleLis.forEach((li) => {
      li.style.display = "none";
      li.setAttribute("data-tap-collapsible", "");
      const link = li.querySelector("a[href], span");
      const url = li.querySelector("a[href]")?.getAttribute("href");
      const label = link?.textContent?.trim();
      if (url && label) collapsedUrls.push({ url, label });
    });

    // Insert an interactive ellipsis at the gap.
    const ell = document.createElement("li");
    ell.className = "tap-bc-collapsed";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tap-bc-ellipsis";
    btn.setAttribute("aria-label", "Show collapsed breadcrumb segments");
    btn.textContent = "…";
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      showCollapsedPopover(btn, collapsedUrls);
    });
    ell.appendChild(btn);
    ol.insertBefore(ell, lis[keepHead]);
  }

  function showCollapsedPopover(anchor, items) {
    dismissPopover();
    if (items.length === 0) return;

    const popover = document.createElement("ul");
    popover.className = "tap-bc-popover";
    popover.setAttribute("role", "menu");

    items.forEach((it) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.className = "tap-bc-popover-item";
      a.href = it.url;
      a.textContent = it.label;
      li.appendChild(a);
      popover.appendChild(li);
    });

    const rect = anchor.getBoundingClientRect();
    popover.style.position = "fixed";
    popover.style.top = `${rect.bottom + 6}px`;
    popover.style.left = `${rect.left}px`;
    document.body.appendChild(popover);
    activePopover = popover;
    armOutsideClick();
  }

  // -------------------------------------------------------------------------
  // Wire interactions.
  // -------------------------------------------------------------------------

  async function init() {
    await loadNavIndex();

    document.querySelectorAll("[data-tap-chevron]").forEach((chev) => {
      chev.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const url = chev.getAttribute("data-tap-sibling-url");
        if (e.altKey) showColumnView(chev, url);
        else showSiblingPopover(chev, url);
      });
    });

    document.querySelectorAll("[data-tap-segment-url]").forEach((seg) => {
      seg.addEventListener("click", (e) => {
        if (!e.altKey) return;
        e.preventDefault();
        e.stopPropagation();
        const url = seg.getAttribute("data-tap-segment-url");
        showColumnView(seg, url);
      });
    });

    // Phase 7: truncate the middle on overflow.
    applyOverflowTruncation();
    if (window.ResizeObserver) {
      const ol = document.querySelector('nav[aria-label="Breadcrumb"] ol');
      if (ol) new ResizeObserver(() => applyOverflowTruncation()).observe(ol.parentElement);
    } else {
      window.addEventListener("resize", applyOverflowTruncation);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
