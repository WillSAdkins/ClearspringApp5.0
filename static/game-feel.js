/*
 * game-feel.js
 *
 * The small things that make a game feel like a game rather than a form:
 * a tap you can feel, and something happening when you win.
 *
 * Written once and applied to all nine games, because every one of them
 * already marks its win panel with .mm-win — so there's a single hook to
 * watch rather than nine files to edit.
 *
 * Everything here degrades to nothing. No vibration API, no confetti, no
 * problem: the games work exactly as before.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------------ *
   * Haptics
   *
   * navigator.vibrate covers Android browsers. iOS Safari doesn't implement
   * it at all, but inside the native shell Capacitor's Haptics plugin does
   * the same job — so try that first when it's there.
   * ------------------------------------------------------------------ */
  var CapHaptics = window.Capacitor
    && window.Capacitor.Plugins
    && window.Capacitor.Plugins.Haptics;

  function buzz(kind) {
    if (reduced) return;
    try {
      if (CapHaptics) {
        if (kind === "win") CapHaptics.notification({ type: "SUCCESS" });
        else if (kind === "wrong") CapHaptics.notification({ type: "WARNING" });
        else CapHaptics.impact({ style: "Light" });
        return;
      }
      if (navigator.vibrate) {
        if (kind === "win") navigator.vibrate([18, 60, 18, 60, 40]);
        else if (kind === "wrong") navigator.vibrate([50, 40, 50]);
        else navigator.vibrate(12);
      }
    } catch (e) {
      /* Vibration can throw if the page isn't focused. Never worth failing for. */
    }
  }

  window.GameFeel = { buzz: buzz };

  /* ------------------------------------------------------------------ *
   * Tap feedback
   *
   * Delegated, so it covers buttons created after load — every game builds
   * its board dynamically.
   * ------------------------------------------------------------------ */
  document.addEventListener("click", function (e) {
    var t = e.target.closest(
      ".ls-cell, .bs-choice, .vb-word, .mm-cell, .game-tile, .btn-primary"
    );
    if (!t || t.disabled) return;
    // A wrong answer marks itself; let the game's own class decide the feel.
    if (t.classList.contains("wrong")) buzz("wrong");
    else buzz("tap");
  }, true);

  /* ------------------------------------------------------------------ *
   * Confetti
   *
   * Hand-rolled rather than a library: it's forty lines, it needs no
   * network request, and a kids' game shouldn't pull 30kB to celebrate.
   * ------------------------------------------------------------------ */
  var COLOURS = ["#E8845A", "#4FBF8B", "#5A9BE8", "#E8C34F", "#C77FE0", "#FFFFFF"];

  function celebrate() {
    if (reduced) return;

    var canvas = document.getElementById("gameConfetti");
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.id = "gameConfetti";
      document.body.appendChild(canvas);
    }
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";

    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    var W = window.innerWidth, H = window.innerHeight;
    var pieces = [];
    // Two bursts from the lower corners, meeting in the middle — reads as
    // celebration rather than as rain.
    [[0.12, 1], [0.88, -1]].forEach(function (origin) {
      for (var i = 0; i < 45; i++) {
        pieces.push({
          x: W * origin[0],
          y: H * 0.82,
          vx: (Math.random() * 5 + 2) * origin[1] + (Math.random() - 0.5) * 2,
          vy: -(Math.random() * 11 + 8),
          size: Math.random() * 6 + 4,
          rot: Math.random() * Math.PI,
          spin: (Math.random() - 0.5) * 0.3,
          colour: COLOURS[(Math.random() * COLOURS.length) | 0],
          life: 1,
        });
      }
    });

    var start = performance.now();
    var DURATION = 2400;

    function frame(now) {
      var elapsed = now - start;
      ctx.clearRect(0, 0, W, H);

      pieces.forEach(function (p) {
        p.vy += 0.32;            // gravity
        p.vx *= 0.992;           // drag
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.spin;
        p.life = Math.max(0, 1 - elapsed / DURATION);

        if (p.life <= 0) return;
        ctx.save();
        ctx.globalAlpha = p.life;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.colour;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      });

      if (elapsed < DURATION) {
        requestAnimationFrame(frame);
      } else {
        ctx.clearRect(0, 0, W, H);
        canvas.remove();
      }
    }
    requestAnimationFrame(frame);
  }

  window.GameFeel.celebrate = celebrate;

  /* ------------------------------------------------------------------ *
   * Watch for a win
   *
   * Every game reveals a .mm-win panel by clearing its `hidden` attribute.
   * Watching that attribute means no game file needs changing, and any game
   * added later gets this for free.
   * ------------------------------------------------------------------ */
  function watch(panel) {
    if (!panel || panel.dataset.feelWatched) return;
    panel.dataset.feelWatched = "1";

    var obs = new MutationObserver(function () {
      if (!panel.hidden) {
        buzz("win");
        celebrate();
      }
    });
    obs.observe(panel, { attributes: true, attributeFilter: ["hidden"] });

    // Already showing when the page loaded.
    if (!panel.hidden) { buzz("win"); celebrate(); }
  }

  function init() {
    document.querySelectorAll(".mm-win").forEach(watch);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
