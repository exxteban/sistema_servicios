// Utilidades puras y persistencia IndexedDB de la cola offline del POS.
// Extraído de pos_offline_resilience.js para respetar el límite de líneas por archivo.
(function () {
    const PENDING_DB_NAME = 'pos_offline_queue_v1';
    const PENDING_STORE = 'ventas';
    // Tiempo máximo para registrar una venta o enviarla a caja. Generoso a propósito:
    // cortar antes de que el servidor termine deja la venta en duda. Si igual se
    // corta, el client_request_id se conserva y el servidor deduplica.
    const PROCESAR_TIMEOUT_MS = 20000;
    const ENVIAR_CAJA_TIMEOUT_MS = 15000;

    function now() {
        return Date.now();
    }

    // Errores transitorios del servidor: la venta sigue pendiente y se reintenta
    // sola, sin marcarla como "requiere revisión".
    // 0 = sin respuesta; 408 timeout; 429 rate limit; 5xx errores del servidor.
    function esErrorTemporalServidor(status) {
        const code = Number(status || 0);
        return code === 0 || code === 408 || code === 429 || code >= 500;
    }

    function normalizedText(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    function itemKey(item) {
        return `${item && item.tipo ? item.tipo : 'producto'}-${item && item.id ? item.id : ''}`;
    }

    function safeJsonParse(raw, fallback) {
        try {
            return JSON.parse(raw);
        } catch (e) {
            return fallback;
        }
    }

    function openPendingDb() {
        return new Promise((resolve, reject) => {
            if (!window.indexedDB) {
                reject(new Error('indexedDB unavailable'));
                return;
            }
            const request = indexedDB.open(PENDING_DB_NAME, 1);
            request.onupgradeneeded = () => {
                const db = request.result;
                if (!db.objectStoreNames.contains(PENDING_STORE)) {
                    db.createObjectStore(PENDING_STORE, { keyPath: 'client_request_id' });
                }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error || new Error('indexedDB open failed'));
        });
    }

    async function readPendingIdb() {
        const db = await openPendingDb();
        return await new Promise((resolve, reject) => {
            const tx = db.transaction(PENDING_STORE, 'readonly');
            const request = tx.objectStore(PENDING_STORE).getAll();
            request.onsuccess = () => resolve(Array.isArray(request.result) ? request.result : []);
            request.onerror = () => reject(request.error || new Error('indexedDB read failed'));
            tx.oncomplete = () => db.close();
            tx.onerror = () => db.close();
        });
    }

    async function replacePendingIdb(items) {
        const db = await openPendingDb();
        await new Promise((resolve, reject) => {
            const tx = db.transaction(PENDING_STORE, 'readwrite');
            const store = tx.objectStore(PENDING_STORE);
            store.clear();
            for (const item of items || []) {
                if (item && item.client_request_id) store.put(item);
            }
            tx.oncomplete = () => {
                db.close();
                resolve();
            };
            tx.onerror = () => {
                db.close();
                reject(tx.error || new Error('indexedDB write failed'));
            };
        });
    }

    window.POSOfflineColaDB = {
        PROCESAR_TIMEOUT_MS,
        ENVIAR_CAJA_TIMEOUT_MS,
        now,
        esErrorTemporalServidor,
        normalizedText,
        itemKey,
        safeJsonParse,
        readPendingIdb,
        replacePendingIdb,
    };
})();
