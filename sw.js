/* Offline shell for the tide viewer.
 *
 * Every prediction is computed locally from tide-data.js, so once these files
 * are cached the page works with no signal at all. Bump CACHE when any of them
 * changes so the new copy replaces the old one. */
var PREFIX = "gm-tides-";
var CACHE = PREFIX + "v3";
var ASSETS = [
  "./",
  "./index.html",
  "./app.css",
  "./app.js",
  "./tide-data.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./apple-touch-icon.png",
  "./icon-192.png",
  "./icon-512.png"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE)
      .then(function (c) { return c.addAll(ASSETS); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (keys) {
        // Only our own buckets: github.io puts every project on one origin, so
        // deleting everything here would wipe a neighbouring site's cache.
        return Promise.all(keys.map(function (k) {
          return (k !== CACHE && k.indexOf(PREFIX) === 0) ? caches.delete(k) : null;
        }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;

  // Cache first: the payload is static and being fast offline matters more
  // than picking up a redeploy the same minute it lands.
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      if (hit) {
        // Refresh in the background so the next visit gets any update. This has
        // to be kept alive with waitUntil, or the worker can be shut down before
        // the revalidation lands and the stale copy sticks forever.
        e.waitUntil(
          fetch(e.request).then(function (res) {
            if (res && res.ok) return caches.open(CACHE).then(function (c) { return c.put(e.request, res); });
          }).catch(function () { /* offline: keep the cached copy */ })
        );
        return hit;
      }
      return fetch(e.request).then(function (res) {
        if (res && res.ok && e.request.url.startsWith(self.location.origin)) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return res;
      }).catch(function () {
        return caches.match("./index.html");
      });
    })
  );
});
