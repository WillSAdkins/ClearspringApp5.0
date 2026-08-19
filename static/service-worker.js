const CACHE_NAME = "clearspring-v6";
const OFFLINE_URLS = ["/static/style.css", "/static/loading-screen.mp4"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(OFFLINE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== "cs-sermon-audio")
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Never cache API calls or feeds — they must always be fresh.
  if (url.pathname.startsWith("/api/") || url.pathname.endsWith(".xml")) return;

  // Never touch the Unity game.
  //
  // Two reasons, either of which is enough:
  //
  //  1. Its files are served with Content-Encoding: br. Putting such a
  //     response in the Cache API stores the already-decoded body but keeps
  //     the encoding header, so replaying it makes the browser try to
  //     brotli-decode plain bytes. It fails, and Unity reports the file as
  //     missing — which is misleading, because it is there.
  //
  //  2. It is 11 MB. Caching that alongside everything else risks blowing
  //     the storage quota and evicting things that genuinely benefit.
  if (url.pathname.startsWith("/static/games/rockslinger/")) return;

  // HTML pages are NOT cached. They vary by who is signed in, so a cached
  // copy can show one person's state to another, or show a signed-in person
  // as signed out. Only static assets are worth caching.
  const isPage = event.request.mode === "navigate" ||
    (event.request.headers.get("accept") || "").includes("text/html");

  if (isPage) {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match("/offline") || caches.match("/")
      )
    );
    return;
  }

  // Static assets: serve from cache, refresh in the background.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});

/* ---- Push notifications ---- */

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: "Clearspring", body: event.data ? event.data.text() : "" };
  }

  const title = data.title || "Clearspring";
  const options = {
    body: data.body || "",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    // A unique tag per message. Reusing a tag makes a new notification
    // silently replace the previous one, which looks like nothing happened.
    tag: (data.tag || "clearspring") + "-" + Date.now(),
    data: { url: data.url || "/" },
    renotify: true,
    requireInteraction: false,
    vibrate: [100, 50, 100],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      // Focus an existing tab if the app is already open.
      for (const client of list) {
        if ("focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
