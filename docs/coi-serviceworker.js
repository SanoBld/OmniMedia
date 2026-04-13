// coi-serviceworker.js
// adds Cross-Origin-Opener-Policy and Cross-Origin-Embedder-Policy headers
// to every response, which enables SharedArrayBuffer in the browser
// this is needed because GitHub Pages doesn't set these headers by default
// and ffmpeg.wasm needs SharedArrayBuffer to work
//
// how it works: this file works both as a normal page script AND as a service worker
// when included via <script src>, it registers itself as a SW, then reloads the page
// on reload, the SW intercepts all responses and adds the headers
// after that reload, crossOriginIsolated = true and ffmpeg.wasm works
//
// adapted from: https://github.com/gzuidhof/coi-serviceworker

(() => {
    // are we running as a service worker?
    const isSW = typeof window === 'undefined';

    if (isSW) {
        // --- SERVICE WORKER CONTEXT ---

        self.addEventListener('install', () => {
            // skip waiting so the SW activates immediately
            self.skipWaiting();
        });

        self.addEventListener('activate', e => {
            // claim all clients right away, don't wait for next nav
            e.waitUntil(self.clients.claim());
        });

        self.addEventListener('fetch', e => {
            // only intercept GET requests — don't touch POST etc
            if (e.request.method !== 'GET') return;

            // skip opaque requests (no-cors mode) — can't add headers to those
            if (e.request.cache === 'only-if-cached' && e.request.mode !== 'same-origin') {
                return;
            }

            e.respondWith(
                fetch(e.request).then(response => {
                    // don't touch opaque/errored responses
                    if (response.status === 0) return response;

                    // clone headers and add COOP/COEP
                    const newHeaders = new Headers(response.headers);
                    newHeaders.set('Cross-Origin-Opener-Policy', 'same-origin');
                    newHeaders.set('Cross-Origin-Embedder-Policy', 'require-corp');

                    return new Response(response.body, {
                        status: response.status,
                        statusText: response.statusText,
                        headers: newHeaders,
                    });
                }).catch(err => {
                    console.warn('[coi-sw] fetch failed:', err);
                    return fetch(e.request); // fallback without headers
                })
            );
        });

    } else {
        // --- PAGE CONTEXT ---
        // register this script as a service worker

        if (!('serviceWorker' in navigator)) {
            console.warn('[coi-sw] service workers not supported in this browser, ffmpeg.wasm might not work');
            return;
        }

        // if page is already cross-origin isolated, nothing to do
        if (window.crossOriginIsolated) {
            return;
        }

        const swURL = document.currentScript && document.currentScript.src;
        if (!swURL) {
            console.warn('[coi-sw] could not determine SW script URL');
            return;
        }

        navigator.serviceWorker.register(swURL, { scope: './' }).then(reg => {
            // if no controller yet, reload so the SW can take effect
            if (!navigator.serviceWorker.controller) {
                console.log('[coi-sw] registered, reloading page to activate...');
                window.location.reload();
            } else {
                console.log('[coi-sw] already active, crossOriginIsolated:', window.crossOriginIsolated);
            }
        }).catch(err => {
            console.warn('[coi-sw] registration failed:', err.message);
            console.warn('[coi-sw] ffmpeg.wasm may fail — if you see errors, try a different browser');
        });
    }
})();
