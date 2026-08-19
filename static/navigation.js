// Makes navigation feel like an app rather than a website.
//
// Two things cause the "clunky" feeling in a server-rendered app:
//   1. A white flash between pages while the next one loads
//   2. No response to a tap until the server answers
//
// View Transitions fix the first where supported (Chrome, Android). The
// pressed state and progress bar fix the second everywhere.
(function () {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- Instant feedback on tap ---- */

  const TAPPABLE = [
    ".bible-row", ".book-row", ".chapter-cell", ".sermon-row", ".game-tile",
    ".plan-item", ".plan-card", ".home-event", ".campaign-card", ".devo-archive-row",
    ".sermon-feature", ".devo-feature", ".prayer-cta", ".give-primary",
    ".give-secondary", ".saved-item", ".v2-cell",
  ].join(",");

  document.addEventListener("pointerdown", (e) => {
    const el = e.target.closest && e.target.closest(TAPPABLE);
    if (el) el.classList.add("pressed");
  }, { passive: true });

  ["pointerup", "pointercancel", "pointerleave"].forEach((evt) => {
    document.addEventListener(evt, () => {
      document.querySelectorAll(".pressed").forEach((el) => el.classList.remove("pressed"));
    }, { passive: true });
  });

  /* ---- Thin progress bar while the next page loads ---- */

  let bar = null;
  let barTimer = null;

  function showBar() {
    if (reduce) return;
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "nav-progress";
      document.body.appendChild(bar);
    }
    bar.classList.remove("done");
    bar.classList.add("active");
  }

  function hideBar() {
    if (!bar) return;
    bar.classList.add("done");
    bar.classList.remove("active");
  }

  // Only show it if the page is actually taking a moment — avoids a flicker
  // on fast navigations, which would itself feel janky.
  document.addEventListener("click", (e) => {
    const link = e.target.closest && e.target.closest("a[href]");
    if (!link) return;
    const url = link.getAttribute("href") || "";
    if (
      link.target === "_blank" ||
      url.startsWith("#") ||
      url.startsWith("mailto:") ||
      url.startsWith("tel:") ||
      url.startsWith("http") && !url.startsWith(window.location.origin)
    ) return;
    clearTimeout(barTimer);
    barTimer = setTimeout(showBar, 150);
  });

  window.addEventListener("pageshow", () => {
    clearTimeout(barTimer);
    hideBar();
  });

  /* ---- Smooth cross-page transitions ---- */

  // Chrome and Android support this natively for multi-page apps via CSS;
  // this only handles the back/forward case where the browser restores
  // a cached page and the transition name needs resetting.
  if ("startViewTransition" in document && !reduce) {
    document.documentElement.classList.add("vt-enabled");
  }
})();
