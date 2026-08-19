// Reading plan progress. Kept in this browser so it works offline and signed
// out; also synced to the member's account when they're signed in, so ticking
// a day on a phone shows up on a laptop.
(function () {
  const root = document.querySelector(".plan-progress");
  if (!root) return;

  const slug = root.dataset.plan;
  const total = parseInt(root.dataset.total, 10);
  const KEY = "cs_plan_" + slug;

  function getDone() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch (e) {
      return new Set();
    }
  }

  function save(done) {
    const list = [...done];
    try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {}
    if (window.Sync) {
      window.Sync.pushSingle("plan", "plan-" + slug, list);
    }
  }

  const fill = document.getElementById("planFill");
  const count = document.getElementById("planCount");

  function refresh() {
    const done = getDone();
    document.querySelectorAll(".plan-day").forEach((li) => {
      const day = parseInt(li.dataset.day, 10);
      li.classList.toggle("done", done.has(day));
    });
    const pct = total ? Math.round((done.size / total) * 100) : 0;
    fill.style.width = pct + "%";
    count.textContent = `${done.size} of ${total} days`;
  }

  document.querySelectorAll(".plan-check").forEach((btn) => {
    btn.addEventListener("click", () => {
      const day = parseInt(btn.dataset.day, 10);
      const done = getDone();
      if (done.has(day)) {
        done.delete(day);
      } else {
        done.add(day);
      }
      save(done);
      refresh();
    });
  });

  document.getElementById("planReset").addEventListener("click", () => {
    if (confirm("Reset your progress on this plan?")) {
      localStorage.removeItem(KEY);
      refresh();
    }
  });

  refresh();

  // Bring in progress from the account. If both exist, keep whichever has more
  // days ticked — losing someone's progress is worse than an extra tick.
  if (window.Sync) {
    window.Sync.pullSingle("plan", "plan-" + slug).then((remote) => {
      if (!Array.isArray(remote)) return;
      const local = getDone();
      if (remote.length > local.size) {
        try { localStorage.setItem(KEY, JSON.stringify(remote)); } catch (e) {}
        refresh();
      } else if (local.size > remote.length) {
        window.Sync.pushSingle("plan", "plan-" + slug, [...local]);
      }
    });
  }
})();