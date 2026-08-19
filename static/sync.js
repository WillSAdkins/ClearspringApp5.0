// Shared sync layer.
//
// Everything personal (saved verses, notes, journal, reading progress) is kept
// in this browser first, so the app works signed out and offline. When someone
// is signed in, each change is also sent to their account, and anything saved
// on another device is pulled in.
//
// Local storage stays the source of truth for reading; the server is the
// place things are kept safe. That means nothing breaks when offline.
window.Sync = (function () {
  let signedInCache = null;

  async function request(path, options) {
    try {
      const res = await fetch(path, options);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;      // offline, or signed out — local copy still stands
    }
  }

  /** Push one item up. Silently does nothing when signed out. */
  async function push(kind, key, value, isDelete) {
    if (signedInCache === false) return false;
    const data = await request(`/api/sync/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value, delete: !!isDelete }),
    });
    if (data) signedInCache = !!data.signed_in;
    return !!(data && data.signed_in);
  }

  /** Fetch everything of one kind. Returns [] when signed out. */
  async function pull(kind) {
    const data = await request(`/api/sync/${kind}`);
    if (!data) return [];
    signedInCache = !!data.signed_in;
    return data.signed_in ? data.items || [] : [];
  }

  /** Upload a whole local collection — used once, on first sign-in. */
  async function pushAll(kind, items) {
    if (!items.length) return false;
    const data = await request(`/api/sync/${kind}/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    return !!(data && data.ok);
  }

  /**
   * Merge the account's copy into local storage.
   *
   * Anything the server has that this device doesn't gets added. Anything this
   * device has that the server doesn't gets uploaded. Nothing is deleted by
   * merging — losing someone's notes would be far worse than a duplicate.
   */
  async function merge(kind, storageKey, keyOf) {
    const remote = await pull(kind);
    if (remote === null) return false;

    let local = [];
    try { local = JSON.parse(localStorage.getItem(storageKey) || "[]"); } catch (e) {}

    const localKeys = new Set(local.map(keyOf));
    const remoteKeys = new Set(remote.map((r) => r.key));

    // Bring down anything only the account has
    let changed = false;
    remote.forEach((r) => {
      if (r.value && !localKeys.has(r.key)) {
        local.push(r.value);
        changed = true;
      }
    });
    if (changed) {
      try { localStorage.setItem(storageKey, JSON.stringify(local)); } catch (e) {}
    }

    // Send up anything only this device has
    const missing = local
      .filter((item) => !remoteKeys.has(keyOf(item)))
      .map((item) => ({ key: keyOf(item), value: item }));
    if (missing.length) await pushAll(kind, missing);

    return true;
  }

  /** For single-value things like reading position or a sermon's notes. */
  async function pushSingle(kind, key, value) {
    return push(kind, key, value, false);
  }

  async function pullSingle(kind, key) {
    const items = await pull(kind);
    const found = items.find((i) => i.key === key);
    return found ? found.value : null;
  }

  return { push, pull, pushAll, merge, pushSingle, pullSingle };
})();
