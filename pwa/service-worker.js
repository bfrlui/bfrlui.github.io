const CACHE_NAME = 'pwa-cache-v1';
const urlsToCache = [
    '/pwa/',
    '/pwa/index.html',
    '/pwa/styles.css',
    '/pwa/app.js',
    '/pwa/manifest.json',
    '/pwa/images/icon-192x192.png',
    '/pwa/images/icon-512x512.png',
    '/pwa/images/apple-touch-icon.png'
];

// Install event - cache files
self.addEventListener('install', event => {
    console.log('Service Worker installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Cache opened');
                return cache.addAll(urlsToCache).catch(err => {
                    console.log('Some assets failed to cache, but continuing:', err);
                });
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    console.log('Service Worker activating...');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', event => {
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Return cached response if available
                if (response) {
                    return response;
                }

                // Clone the request
                const fetchRequest = event.request.clone();

                return fetch(fetchRequest).then(response => {
                    // Check if valid response
                    if (!response || response.status !== 200 || response.type === 'error') {
                        return response;
                    }

                    // Clone the response
                    const responseToCache = response.clone();

                    // Cache the new response
                    caches.open(CACHE_NAME)
                        .then(cache => {
                            cache.put(event.request, responseToCache);
                        });

                    return response;
                });
            })
            .catch(error => {
                // Return offline page or default response
                console.log('Fetch failed; returning offline page instead.', error);
                
                // Return a basic offline response
                return new Response(
                    '<html><body><h1>Offline</h1><p>The page you requested is not available offline.</p></body></html>',
                    {
                        headers: {
                            'Content-Type': 'text/html'
                        }
                    }
                );
            })
    );
});

// Background sync event
self.addEventListener('sync', event => {
    console.log('Background sync event:', event.tag);
    if (event.tag === 'sync-notes') {
        event.waitUntil(
            // Implement your sync logic here
            Promise.resolve()
        );
    }
});

// Push notification event
self.addEventListener('push', event => {
    console.log('Push notification received:', event);
    const options = {
        body: event.data ? event.data.text() : 'New notification',
        icon: '/images/icon-192x192.png',
        badge: '/images/icon-192x192.png',
        tag: 'pwa-notification',
        requireInteraction: false
    };

    event.waitUntil(
        self.registration.showNotification('PWA Notification', options)
    );
});

// Notification click event
self.addEventListener('notificationclick', event => {
    console.log('Notification clicked:', event);
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window' })
            .then(clientList => {
                // Check if window already open
                for (let client of clientList) {
                    if (client.url === '/' && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Open new window if not already open
                if (clients.openWindow) {
                    return clients.openWindow('/');
                }
            })
    );
});

// Message event - handle notifications from main app
self.addEventListener('message', event => {
    console.log('Service Worker received message:', event.data);
    
    if (event.data && event.data.type === 'SHOW_NOTIFICATION') {
        const { title, options } = event.data;
        self.registration.showNotification(title, options)
            .then(() => {
                console.log('Notification shown from Service Worker');
            })
            .catch(error => {
                console.error('Error showing notification:', error);
            });
    }
});
