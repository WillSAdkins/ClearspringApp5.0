// Motion layer: page-load choreography + scroll-triggered reveals.
// Fully respects prefers-reduced-motion (falls back to instant visibility).
(function () {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function autoTag() {
    const auto = document.querySelectorAll(
      ".game-tile, .qa-card, .book-tile, .card, .placeholder-card, .verse-card, .day-group, " +
      ".bible-row, .lb-row, .devo-archive-row, .plan-card, .plan-item, .plan-day"
    );
    auto.forEach((el, i) => {
      if (!el.hasAttribute("data-reveal") && !el.hasAttribute("data-load")) {
        el.setAttribute("data-reveal", "");
        // Small stagger within a list so rows cascade in rather than
        // popping together — capped so long lists don't feel sluggish.
        el.style.transitionDelay = `${Math.min((i % 8) * 45, 315)}ms`;
      }
    });
  }

  function revealAll() {
    document.querySelectorAll("[data-reveal]").forEach((el) => el.classList.add("in"));
  }

  document.addEventListener("DOMContentLoaded", () => {
    autoTag();

    if (reduce) {
      revealAll();
      return;
    }

    const loadEls = [...document.querySelectorAll("[data-load]")];
    loadEls.forEach((el, i) => {
      el.style.transitionDelay = `${Math.min(i * 70, 500)}ms`;
      requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("in")));
    });

    const revealEls = document.querySelectorAll("[data-reveal]");
    if (!("IntersectionObserver" in window)) {
      revealAll();
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => io.observe(el));

    const hero = document.querySelector("[data-hero]");
    if (hero) {
      const onScroll = () => {
        const y = window.scrollY;
        hero.style.setProperty("--scroll", Math.min(y / 300, 1).toFixed(3));
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }
  });
})();
