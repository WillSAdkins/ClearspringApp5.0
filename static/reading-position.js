// Remembers where someone is up to, so the app can offer to continue rather
// than making them navigate from scratch each time.
//
// Also keeps a gentle record of which days they read. Deliberately no
// "streak broken" messaging — missing a day shouldn't feel like failure.
window.ReadingPosition = (function () {
  const POS_KEY = "cs_reading_position";
  const DAYS_KEY = "cs_reading_days";
  const RECENT_KEY = "cs_recent_books";

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  /* ---- where they were reading ---- */

  function setPosition(book, bookSlug, chapter, translation) {
    const pos = { book, bookSlug, chapter, translation, at: new Date().toISOString() };
    try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch (e) {}
    noteToday();
    noteBook(book, bookSlug);
    // Keep the account's copy in step, so "continue reading" follows you
    // between devices.
    if (window.Sync) window.Sync.pushSingle("plan", "reading-position", pos);
    return pos;
  }

  /** Take the account's position if it is more recent than this device's. */
  async function syncWithAccount() {
    if (!window.Sync) return false;
    const remote = await window.Sync.pullSingle("plan", "reading-position");
    if (!remote || !remote.at) return false;
    const local = getPosition();
    if (!local || new Date(remote.at) > new Date(local.at)) {
      try { localStorage.setItem(POS_KEY, JSON.stringify(remote)); } catch (e) {}
      return true;
    }
    return false;
  }

  function getPosition() {
    return readJSON(POS_KEY, null);
  }

  /* ---- recently opened books ---- */

  function noteBook(book, slug) {
    const list = readJSON(RECENT_KEY, []).filter((b) => b.slug !== slug);
    list.unshift({ name: book, slug });
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 5))); } catch (e) {}
  }

  function recentBooks() {
    return readJSON(RECENT_KEY, []);
  }

  /* ---- days read, kept gently ---- */

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function noteToday() {
    const days = readJSON(DAYS_KEY, []);
    const t = today();
    if (!days.includes(t)) {
      days.push(t);
      try { localStorage.setItem(DAYS_KEY, JSON.stringify(days.slice(-365))); } catch (e) {}
    }
  }

  function daysThisWeek() {
    const days = readJSON(DAYS_KEY, []);
    const now = new Date();
    const monday = new Date(now);
    monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
    const start = monday.toISOString().slice(0, 10);
    return days.filter((d) => d >= start).length;
  }

  function readToday() {
    return readJSON(DAYS_KEY, []).includes(today());
  }

  function encouragement() {
    const n = daysThisWeek();
    if (n === 0) return null;
    if (n === 1) return "You've read once this week";
    if (n < 5) return `You've read ${n} days this week`;
    if (n < 7) return `${n} days this week — a good rhythm`;
    return "You've read every day this week";
  }

  return { setPosition, getPosition, recentBooks, daysThisWeek, readToday, encouragement, syncWithAccount };
})();
