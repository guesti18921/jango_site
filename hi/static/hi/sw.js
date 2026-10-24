// Only cache versioned static assets. Never cache account pages, locale catalogs or API data.
const CACHE_NAME='veyra-static-v26';
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('media-app-')||(key.startsWith('mysite-static-')||key.startsWith('veyra-static-'))&&key!==CACHE_NAME).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
    const url=new URL(event.request.url);
    if(event.request.method!=='GET'||url.origin!==self.location.origin||!url.pathname.startsWith('/static/hi/'))return;
    event.respondWith(fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.put(event.request,copy)));}return response;}).catch(()=>caches.match(event.request)));
});
