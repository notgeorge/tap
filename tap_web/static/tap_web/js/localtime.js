/**
 * localtime.js — TAP local-time rendering (spec-web-time-display).
 *
 * The single source of truth for turning a UTC instant into the text a human
 * reads. TAP stores and transmits time as absolute UTC (req-web-time-utc-canonical);
 * localization to the viewer's browser zone happens here, at the last hop
 * (req-web-time-local-display, D1: viewer's browser zone).
 *
 * Two consumers share this one code path (req-web-time-single-helper):
 *   1. Server-rendered <time data-tap-localtime datetime="...Z"> elements
 *      (emitted by the `tap_localtime` template filter) are localized in place
 *      by the DOM pass below.
 *   2. Client-rendered panels (panel-table.js) call TapLocalTime.formatEl()
 *      directly so Tabulator cells match the server-rendered surfaces exactly.
 *
 * Zone disclosure (req-web-time-zone-disclosure, D2): the visible text carries
 * the zone abbreviation (e.g. "2026-07-02 10:30 EDT") and the element's title=
 * tooltip carries the exact UTC instant (e.g. "2026-07-02 14:30:00 UTC"), so a
 * displayed local time is never evidentiarily ambiguous.
 */

(function () {
  "use strict";

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  // The viewer's zone abbreviation for the given instant (e.g. "EDT", "GMT+2").
  // Uses the browser's own zone; empty string if the platform can't report one.
  function zoneAbbrev(d) {
    try {
      var parts = new Intl.DateTimeFormat(undefined, {
        timeZoneName: "short",
      }).formatToParts(d);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === "timeZoneName") return parts[i].value;
      }
    } catch (e) {
      /* Intl unavailable — fall through to no abbreviation. */
    }
    return "";
  }

  /**
   * Format a UTC instant for human display.
   *
   * @param {string|Date} isoUtc  A UTC ISO-8601 string (…Z or +00:00) or Date.
   * @returns {{text: string, title: string}}  Local text (with zone abbrev) and
   *   the UTC tooltip. On an unparseable value, both fall back to the raw input.
   */
  function format(isoUtc) {
    var d = isoUtc instanceof Date ? isoUtc : new Date(isoUtc);
    if (isNaN(d.getTime())) {
      var raw = String(isoUtc);
      return { text: raw, title: raw };
    }
    // Local components (viewer's browser zone).
    var local =
      d.getFullYear() +
      "-" +
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      " " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes());
    var abbrev = zoneAbbrev(d);
    var text = abbrev ? local + " " + abbrev : local;
    // UTC tooltip — the absolute instant, always recoverable.
    var title =
      d.getUTCFullYear() +
      "-" +
      pad(d.getUTCMonth() + 1) +
      "-" +
      pad(d.getUTCDate()) +
      " " +
      pad(d.getUTCHours()) +
      ":" +
      pad(d.getUTCMinutes()) +
      ":" +
      pad(d.getUTCSeconds()) +
      " UTC";
    return { text: text, title: title };
  }

  /**
   * A localized <time> element for a UTC instant — for consumers that render
   * DOM nodes (e.g. Tabulator cell formatters). The `datetime` attribute keeps
   * the canonical machine value; the body is local text; the title is UTC.
   *
   * @param {string|Date} isoUtc
   * @returns {HTMLTimeElement}
   */
  function formatEl(isoUtc) {
    var f = format(isoUtc);
    var el = document.createElement("time");
    el.setAttribute("datetime", String(isoUtc));
    el.setAttribute("title", f.title);
    el.textContent = f.text;
    return el;
  }

  // Localize every server-rendered <time data-tap-localtime> under `root`.
  // Idempotent: re-running never changes the (immutable) datetime attribute, so
  // it is safe to call again after HTMX swaps bring in fresh fragments.
  function localizeAll(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll("time[data-tap-localtime]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var iso = el.getAttribute("datetime");
      if (!iso) continue;
      var f = format(iso);
      el.textContent = f.text;
      el.setAttribute("title", f.title);
    }
  }

  window.TapLocalTime = {
    format: format,
    formatEl: formatEl,
    localizeAll: localizeAll,
  };

  // Localize on initial load and after HTMX swaps bring in new content.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      localizeAll(document);
    });
  } else {
    localizeAll(document);
  }
  document.body &&
    document.body.addEventListener("htmx:afterSwap", function (evt) {
      localizeAll(evt.target || document);
    });
})();
