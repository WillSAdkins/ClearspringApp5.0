// Word-level highlights within a chapter.
//
// A highlight records the verse reference plus the exact phrase highlighted,
// so it can be re-applied when the chapter is opened again. Stored locally and,
// when the reader is signed in, synced to their account.
window.Highlights = (function () {
  const KEY = "cs_highlights";

  function load() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "[]");
    } catch (e) {
      return [];
    }
  }

  function persist(list) {
    localStorage.setItem(KEY, JSON.stringify(list));
  }

  function keyFor(h) {
    return `${h.ref}|${h.translation}|${h.text}`;
  }

  function forChapter(book, chapter, translation) {
    const prefix = `${book} ${chapter}:`;
    return load().filter(
      (h) => h.ref.startsWith(prefix) && h.translation === translation
    );
  }

  function exists(ref, text, translation) {
    return load().some(
      (h) => h.ref === ref && h.text === text && h.translation === translation
    );
  }

  function add(ref, text, translation) {
    if (!text || exists(ref, text, translation)) return false;
    const all = load();
    const item = { ref, text, translation, at: new Date().toISOString() };
    all.unshift(item);
    persist(all);
    syncUp(item, false);
    return true;
  }

  function remove(ref, text, translation) {
    const all = load().filter(
      (h) => !(h.ref === ref && h.text === text && h.translation === translation)
    );
    persist(all);
    syncUp({ ref, text, translation }, true);
  }

  function getAll() {
    return load();
  }

  // ---- Account sync (no-ops when signed out) ----

  async function syncUp(item, isDelete) {
    try {
      await fetch("/api/sync/highlight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: keyFor(item),
          value: item,
          delete: !!isDelete,
        }),
      });
    } catch (e) {
      /* offline or signed out — local copy still stands */
    }
  }

  async function pullFromAccount() {
    try {
      const res = await fetch("/api/sync/highlight");
      const data = await res.json();
      if (!data.ok || !data.signed_in) return false;

      const local = load();
      const seen = new Set(local.map(keyFor));
      let changed = false;
      data.items.forEach((row) => {
        const h = row.value;
        if (h && h.ref && !seen.has(keyFor(h))) {
          local.push(h);
          seen.add(keyFor(h));
          changed = true;
        }
      });
      if (changed) persist(local);
      return true;
    } catch (e) {
      return false;
    }
  }

  return { forChapter, exists, add, remove, getAll, pullFromAccount };
})();
