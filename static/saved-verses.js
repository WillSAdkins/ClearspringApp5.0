// Saved verses.
//
// Kept in this browser so the app works signed out and offline. When someone
// is signed in they also sync to their account, so verses saved on a phone
// appear on a laptop.
window.SavedVerses = (function () {
  const KEY = "cs_saved_verses";

  function keyOf(v) {
    return `${v.ref}|${v.translation}`;
  }

  function getAll() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function persist(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {}
  }

  function isSaved(ref, translation) {
    return getAll().some((v) => v.ref === ref && v.translation === translation);
  }

  function save(ref, text, translation) {
    const all = getAll();
    if (!all.some((v) => v.ref === ref && v.translation === translation)) {
      const item = { ref, text, translation, savedAt: new Date().toISOString() };
      all.unshift(item);
      persist(all);
      if (window.Sync) window.Sync.push("verse", keyOf(item), item, false);
    }
  }

  function remove(ref, translation) {
    persist(getAll().filter((v) => !(v.ref === ref && v.translation === translation)));
    if (window.Sync) {
      window.Sync.push("verse", `${ref}|${translation}`, null, true);
    }
  }

  function toggle(ref, text, translation) {
    if (isSaved(ref, translation)) {
      remove(ref, translation);
      return false;
    }
    save(ref, text, translation);
    return true;
  }

  /** Merge with the account. Safe to call on every page load. */
  async function syncWithAccount() {
    if (!window.Sync) return false;
    return window.Sync.merge("verse", KEY, keyOf);
  }

  return { getAll, isSaved, save, remove, toggle, syncWithAccount };
})();
