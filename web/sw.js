/* Niat service worker — network-first app shell with offline fallback.
   API calls are never intercepted (always live). Bump CACHE to invalidate. */
const CACHE = "niat-v1";
const SHELL = [
  "/index.html",
  "/login.html",
  "/app.js",
  "/niat-logo.png",
  "/icon-192.png",
  "/icon-512.png",
  "/manifest.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // live data only, never cached
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok && !r.redirected) {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return r;
      })
      .catch(() =>
        caches.match(e.request).then((m) => m || caches.match("/index.html"))
      )
  );
});
