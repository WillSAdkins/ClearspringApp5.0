/*
 * keep-place.js
 *
 * Two related annoyances this fixes:
 *
 *   1. You scroll halfway down a long chapter, tap through to something else,
 *      come back, and you're at the top again.
 *   2. You switch to another app. iOS reclaims the memory, and when you come
 *      back the webview has quietly reloaded — losing your position even
 *      though it looks like the same page.
 *
 * Browsers restore scroll on back/forward, but not on a fresh navigation to a
 * page you've seen before, and not after a background reload. So positions are
 * remembered per URL for the session.
 *
 * sessionStorage, not localStorage: this should last as long as the app is
 * open and no longer. Nobody wants to return next week to exactly where they
 * were in Leviticus.
 */
(function () {
  "use strict";

  var KEY = "cs:scroll";
  var MAX_ENTRIES = 40;

  function storage() {
    try {
      // Private browsing on some platforms throws on access rather than
      // returning null, so this has to be inside the try.
      var s = window.sessionStorage;
      s.getItem(KEY);
      return s;
    } catch (e) {
      return null;
    }
  }

  var store = storage();
  if (!store) return;

  function here() {
    return window.location.pathname + window.location.search;
  }

  function readAll() {
    try {
      return JSON.parse(store.getItem(KEY)) || {};
    } catch (e) {
      return {};
    }
  }

  function save() {
    var y = window.scrollY || document.documentElement.scrollTop || 0;
    var all = readAll();

    if (y < 40) {
      // Near the top isn't worth remembering, and clearing it means a genuine
      // scroll-to-top is respected next time rather than being overridden.
      delete all[here()];
    } else {
      all[here()] = { y: Math.round(y), t: Date.now() };
    }

    // Keep the newest few so this can't grow without limit.
    var keys = Object.keys(all);
    if (keys.length > MAX_ENTRIES) {
      keys.sort(function (a, b) { return (all[b].t || 0) - (all[a].t || 0); });
      keys.slice(MAX_ENTRIES).forEach(function (k) { delete all[k]; });
    }

    try {
      store.setItem(KEY, JSON.stringify(all));
    } catch (e) {
      // Quota full — drop everything rather than fail on every scroll.
      try { store.removeItem(KEY); } catch (e2) { /* nothing more to do */ }
    }
  }

  function restore() {
    var entry = readAll()[here()];
    if (!entry || !entry.y) return;

    // Content can arrive after first paint — scripture is fetched, images
    // reflow — so re-apply a few times over the first second rather than
    // once, and stop early if the reader has already scrolled themselves.
    var target = entry.y;
    var attempts = 0;
    var userMoved = false;

    function onUserScroll() { userMoved = true; }
    window.addEventListener("wheel", onUserScroll, { passive: true, once: true });
    window.addEventListener("touchstart", onUserScroll, { passive: true, once: true });

    function attempt() {
      if (userMoved) return cleanup();
      var max = Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight
      ) - window.innerHeight;
      if (max > 0) {
        window.scrollTo(0, Math.min(target, max));
      }
      attempts += 1;
      if (attempts < 6) {
        setTimeout(attempt, attempts * 90);
      } else {
        cleanup();
      }
    }

    function cleanup() {
      window.removeEventListener("wheel", onUserScroll);
      window.removeEventListener("touchstart", onUserScroll);
    }

    // Stop the browser fighting us on back/forward.
    if ("scrollRestoration" in history) {
      history.scrollRestoration = "manual";
    }
    attempt();
  }

  /* ---------------------------------------------------------------- *
   * Saving
   * ---------------------------------------------------------------- */

  // Throttled, so a long scroll doesn't write on every frame.
  var pending = null;
  window.addEventListener("scroll", function () {
    if (pending) return;
    pending = setTimeout(function () {
      pending = null;
      save();
    }, 250);
  }, { passive: true });

  // The reliable moments to persist: leaving the page, and being backgrounded.
  // pagehide fires where unload doesn't on mobile Safari.
  window.addEventListener("pagehide", save);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) save();
  });

  // Following a link is the most common way to leave.
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("a[href]");
    if (link) save();
  }, true);

  /* ---------------------------------------------------------------- *
   * Restoring
   * ---------------------------------------------------------------- */

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restore);
  } else {
    restore();
  }

  // Returning from the back/forward cache, or after the OS reloaded the
  // webview behind our back.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) restore();
  });
})();
