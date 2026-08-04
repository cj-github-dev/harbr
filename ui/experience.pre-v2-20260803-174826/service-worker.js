const CACHE = "harbr-experience-v1";
const ASSETS = ["/","/styles.css","/app.js","/manifest.webmanifest","/data/experience.json",
"/assets/icons/harbr-mark.svg","/assets/icons/app-icon.svg",
"/assets/seasons/spring.svg","/assets/seasons/summer.svg","/assets/seasons/autumn.svg","/assets/seasons/winter.svg"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(fetch(e.request).then(r => {
    const copy = r.clone();
    caches.open(CACHE).then(c=>c.put(e.request,copy));
    return r;
  }).catch(()=>caches.match(e.request)));
});
