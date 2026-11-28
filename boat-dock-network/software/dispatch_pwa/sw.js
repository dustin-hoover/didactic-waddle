/* DockOS Crew service worker — offline app shell + last run sheet (doc 23).
   Shell and lake chart: cache-first. Run sheet: network-first, cached fallback.
   Field actions are never cached: the page's outbox replays them when back online. */
const SHELL = "dockos-crew-v1";
const ASSETS = ["./", "./index.html", "./app.js", "./manifest.webmanifest", "./icon.svg", "/lake.geojson"];
self.addEventListener("install", e => e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL && k !== "dockos-data").map(k => caches.delete(k))))
    .then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET") return;                        // POST /field/actions -> network only
  if (u.pathname.startsWith("/dispatch/runsheet/")) {               // network-first
    e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open("dockos-data").then(c => c.put(e.request, cp)); return r; })
      .catch(() => caches.match(e.request)));
    return;
  }
  if (u.origin === location.origin || u.host.endsWith("gstatic.com") || u.host.endsWith("googleapis.com")) {
    e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {
      if (r.ok || r.type === "opaque") { const cp = r.clone(); caches.open(SHELL).then(c => c.put(e.request, cp)); }
      return r;
    })));
  }
});
