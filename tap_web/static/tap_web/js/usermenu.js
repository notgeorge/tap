// Header user-menu + flash-message UX (no framework, no dependencies).
//   - Close the <details data-tap-usermenu> dropdown on any outside click or Esc
//     (native <details> only toggles on the summary itself).
//   - Flash messages: dismiss on × click, and auto-dismiss after a timeout.
(function () {
  "use strict";

  function closeMenus(except) {
    document.querySelectorAll("details[data-tap-usermenu][open]").forEach(function (d) {
      if (d !== except && (!except || !d.contains(except))) {
        d.removeAttribute("open");
      }
    });
  }

  // Outside-click closes any open user menu. A click on the summary is "inside",
  // so the native toggle still works; a click anywhere else closes it.
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details[data-tap-usermenu][open]").forEach(function (d) {
      if (!d.contains(e.target)) {
        d.removeAttribute("open");
      }
    });
  });

  // Esc closes the menu.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeMenus(null);
    }
  });

  // Flash messages.
  var AUTO_DISMISS_MS = 6000;

  function dismissFlash(el) {
    if (!el) return;
    el.classList.add("tap-flash--leaving");
    setTimeout(function () {
      el.remove();
    }, 250);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-tap-flash-close]");
    if (btn) {
      dismissFlash(btn.closest("[data-tap-flash]"));
    }
  });

  document.querySelectorAll("[data-tap-flash]").forEach(function (el) {
    setTimeout(function () {
      dismissFlash(el);
    }, AUTO_DISMISS_MS);
  });
})();
