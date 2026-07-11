(function () {
    const originalPosApp = window.posApp;
    if (typeof originalPosApp !== 'function') return;

    const CATALOG_CACHE_KEY = 'pos_catalogo_cache_v1';
    const CATALOG_MAX_AGE_MS = 24 * 60 * 60 * 1000;
    const REQUEST_TIMEOUT_MS = 8000;
    const SLOW_REQUEST_MS = 1800;
    const HEALTH_CHECK_URL = '/api/health';
    const HEALTH_TIMEOUT_MS = 2500;
    const HEALTH_GOOD_MS = 1400;
    const SYNC_RETRY_MS = 10000;
    const SYNC_RETRY_MAX_MS = 60000;
    const PENDING_DB_NAME = 'pos_offline_queue_v1';
    const PENDING_STORE = 'ventas';
    // Si una venta quedó marcada como "sincronizando" hace más de este tiempo,
    // fue un envío interrumpido: la volvemos a dejar pendiente para reintentar.
    const SENDING_STALE_MS = 2 * 60 * 1000;

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

    window.posApp = function posAppOfflineResilience() {
        const app = originalPosApp();
        if (!app || typeof app !== 'object') return app;

        app.connectionStatus = navigator.onLine ? 'online' : 'offline';
        app.connectionMessage = '';
        app.catalogoOffline = [];
        app.catalogoOfflineLoadedAt = null;
        app.catalogoOfflineNoticeAt = 0;
        app.sincronizandoPendientes = false;
        app.ultimaSincronizacionError = '';
        app.posSyncRetryTimeoutId = null;
        app.posSyncRetryDelayMs = SYNC_RETRY_MS;
        app.medicionConexionMs = null;
        app.colaPersistencia = window.indexedDB ? 'indexedDB' : 'localStorage';
        app.pendingIdbSavePromise = Promise.resolve();

        app.estadoConexionTexto = function estadoConexionTexto() {
            if (this.connectionStatus === 'slow') return this.connectionMessage || 'Conexion lenta';
            if (this.connectionStatus === 'syncing') return 'Sincronizando';
            if (this.connectionStatus === 'offline') return 'Offline';
            return 'Online';
        };

        app.estadoConexionClase = function estadoConexionClase() {
            if (this.connectionStatus === 'slow') return 'bg-amber-100 text-amber-800';
            if (this.connectionStatus === 'syncing') return 'bg-blue-100 text-blue-700';
            if (this.connectionStatus === 'offline') return 'bg-red-100 text-red-700';
            return 'bg-green-100 text-green-700';
        };

        app.marcarConexionOnline = function marcarConexionOnline() {
            this.isOnline = true;
            this.connectionStatus = 'online';
            this.connectionMessage = '';
            this.posSyncRetryDelayMs = SYNC_RETRY_MS;
        };

        app.marcarConexionLenta = function marcarConexionLenta(message) {
            this.isOnline = true;
            this.connectionStatus = 'slow';
            this.connectionMessage = message || 'Conexion lenta';
        };

        app.marcarConexionOffline = function marcarConexionOffline(message) {
            this.isOnline = false;
            this.connectionStatus = 'offline';
            this.connectionMessage = message || 'Sin conexion';
        };

        app.chequearConexionSaludable = async function chequearConexionSaludable() {
            if (!navigator.onLine) {
                this.marcarConexionOffline();
                return false;
            }

            const startedAt = (window.performance && typeof window.performance.now === 'function')
                ? window.performance.now()
                : now();
            try {
                const response = await this.fetchResponseConTimeout(`${HEALTH_CHECK_URL}?_=${now()}`, {
                    headers: { Accept: 'application/json' },
                    cache: 'no-store',
                }, {
                    timeoutMs: HEALTH_TIMEOUT_MS,
                    slowMs: HEALTH_GOOD_MS,
                    markSlow: false,
                });
                const finishedAt = (window.performance && typeof window.performance.now === 'function')
                    ? window.performance.now()
                    : now();
                const elapsedMs = Math.round(finishedAt - startedAt);
                this.medicionConexionMs = elapsedMs;
                if (!response.ok) {
                    this.marcarConexionLenta('Servidor no disponible');
                    return false;
                }
                if (elapsedMs > HEALTH_GOOD_MS) {
                    this.marcarConexionLenta(`Conexion lenta (${elapsedMs} ms)`);
                    return false;
                }
                this.marcarConexionOnline();
                return true;
            } catch (e) {
                this.medicionConexionMs = null;
                if (e && e.posTimeout) this.marcarConexionLenta('Conexion demasiado lenta');
                else if (!navigator.onLine) this.marcarConexionOffline();
                else this.marcarConexionLenta('Conexion inestable');
                return false;
            }
        };

        app.programarSincronizacionPendientes = function programarSincronizacionPendientes(delayMs = null) {
            if (!this.ventasPendientes || this.ventasPendientes.length === 0) return;
            if (this.posSyncRetryTimeoutId) return;
            const delay = delayMs === null ? this.posSyncRetryDelayMs : Number(delayMs || 0);
            this.posSyncRetryTimeoutId = setTimeout(() => {
                this.posSyncRetryTimeoutId = null;
                this.sincronizarVentasPendientes({ automatico: true });
            }, Math.max(1000, delay));
        };

        app.aumentarEsperaSincronizacion = function aumentarEsperaSincronizacion() {
            const actual = Number(this.posSyncRetryDelayMs || SYNC_RETRY_MS);
            this.posSyncRetryDelayMs = Math.min(SYNC_RETRY_MAX_MS, Math.max(SYNC_RETRY_MS, actual * 2));
        };

        app.resumenColaLocalTexto = function resumenColaLocalTexto() {
            const total = Array.isArray(this.ventasPendientes) ? this.ventasPendientes.length : 0;
            if (total <= 0) return '';
            const conError = this.ventasPendientes.filter(v => (v.estado_sync || '') === 'error').length;
            if (conError > 0) return `${total} venta(s) en cola local. ${conError} requiere(n) revision.`;
            if (this.sincronizandoPendientes) return `${total} venta(s) en cola local, enviando al servidor...`;
            return `${total} venta(s) guardada(s) en este equipo para enviar al servidor cuando la conexion este estable.`;
        };

        app.estadoVentaPendienteTexto = function estadoVentaPendienteTexto(venta) {
            const estado = String((venta && venta.estado_sync) || 'pendiente');
            if (estado === 'sincronizando') return 'Enviando';
            if (estado === 'error') return 'Revisar';
            return 'En cola';
        };

        app.fechaVentaPendienteTexto = function fechaVentaPendienteTexto(venta) {
            const ts = Number(venta && venta.created_at ? venta.created_at : 0);
            if (!ts) return '';
            try {
                return new Date(ts).toLocaleString('es-PY');
            } catch (e) {
                return '';
            }
        };

        app.totalVentaPendiente = function totalVentaPendiente(venta) {
            const payload = (venta && venta.payload) || {};
            const items = Array.isArray(payload.items) ? payload.items : [];
            const subtotal = items.reduce((sum, item) => sum + app.subtotalItemPromocion.call(app, item), 0);
            return Math.max(0, subtotal - (parseFloat(payload.descuento) || 0));
        };

        const originalGuardarVentasPendientes = app.guardarVentasPendientes;
        if (typeof originalGuardarVentasPendientes === 'function') {
            app.guardarVentasPendientes = function guardarVentasPendientesPersistente() {
                originalGuardarVentasPendientes.call(this);
                const snapshot = Array.isArray(this.ventasPendientes) ? this.ventasPendientes : [];
                this.pendingIdbSavePromise = this.pendingIdbSavePromise
                    .catch(() => {})
                    .then(() => replacePendingIdb(snapshot));
                this.pendingIdbSavePromise
                    .then(() => { this.colaPersistencia = 'indexedDB'; })
                    .catch(() => { this.colaPersistencia = 'localStorage'; });
            };
        }

        const originalCargarVentasPendientes = app.cargarVentasPendientes;
        if (typeof originalCargarVentasPendientes === 'function') {
            app.cargarVentasPendientes = function cargarVentasPendientesPersistente() {
                originalCargarVentasPendientes.call(this);
                readPendingIdb()
                    .then((itemsDb) => {
                        const merged = new Map();
                        for (const item of itemsDb || []) {
                            if (item && item.client_request_id) merged.set(item.client_request_id, item);
                        }
                        for (const item of this.ventasPendientes || []) {
                            if (item && item.client_request_id) merged.set(item.client_request_id, item);
                        }
                        this.ventasPendientes = [...merged.values()]
                            .map((venta) => {
                                if ((venta.estado_sync || '') === 'sincronizando'
                                    && now() - Number(venta.updated_at || venta.created_at || 0) > SENDING_STALE_MS) {
                                    venta.estado_sync = 'pendiente';
                                    venta.ultimo_error = venta.ultimo_error || 'Envio anterior interrumpido; pendiente de reintento';
                                }
                                return venta;
                            })
                            .sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));
                        this.colaPersistencia = 'indexedDB';
                        this.guardarVentasPendientes();
                        this.programarSincronizacionPendientes(1500);
                    })
                    .catch(() => { this.colaPersistencia = 'localStorage'; });
            };
        }

        app.fetchResponseConTimeout = async function fetchResponseConTimeout(input, init = {}, options = {}, fetchImpl = window.fetch) {
            const timeoutMs = Number(options.timeoutMs || REQUEST_TIMEOUT_MS);
            const slowMs = Number(options.slowMs || SLOW_REQUEST_MS);
            const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
            const requestInit = { ...(init || {}) };
            let timeoutId = null;
            let slowId = null;
            let slowTriggered = false;

            if (controller) requestInit.signal = controller.signal;
            if (slowMs > 0) {
                slowId = setTimeout(() => {
                    slowTriggered = true;
                    if (options.markSlow !== false) this.marcarConexionLenta('Conexion lenta');
                }, slowMs);
            }
            if (controller && timeoutMs > 0) {
                timeoutId = setTimeout(() => controller.abort(), timeoutMs);
            }

            try {
                const response = await fetchImpl(input, requestInit);
                if (timeoutId) clearTimeout(timeoutId);
                if (slowId) clearTimeout(slowId);
                if (slowTriggered) this.marcarConexionLenta('Conexion recuperada, pero lenta');
                else this.marcarConexionOnline();
                return response;
            } catch (error) {
                if (timeoutId) clearTimeout(timeoutId);
                if (slowId) clearTimeout(slowId);
                if (error && error.name === 'AbortError') {
                    error.posTimeout = true;
                    this.marcarConexionLenta('Servidor sin respuesta');
                } else if (!navigator.onLine) {
                    this.marcarConexionOffline();
                } else {
                    this.marcarConexionLenta('Conexion inestable');
                }
                throw error;
            }
        };

        app.fetchJsonConTimeout = async function fetchJsonConTimeout(input, init = {}, options = {}) {
            const response = await this.fetchResponseConTimeout(input, init, options);
            const data = await response.json().catch(() => ({}));
            return { response, data };
        };

        app.cargarCatalogoOfflineCache = function cargarCatalogoOfflineCache() {
            const raw = localStorage.getItem(CATALOG_CACHE_KEY);
            const parsed = raw ? safeJsonParse(raw, null) : null;
            const items = parsed && Array.isArray(parsed.items) ? parsed.items : [];
            this.catalogoOffline = items;
            this.catalogoOfflineLoadedAt = parsed && parsed.saved_at ? Number(parsed.saved_at) : null;
        };

        app.guardarCatalogoOfflineCache = function guardarCatalogoOfflineCache(items) {
            const data = { saved_at: now(), items: Array.isArray(items) ? items : [] };
            try {
                localStorage.setItem(CATALOG_CACHE_KEY, JSON.stringify(data));
                this.catalogoOffline = data.items;
                this.catalogoOfflineLoadedAt = data.saved_at;
            } catch (e) {
            }
        };

        app.fusionarCatalogoOffline = function fusionarCatalogoOffline(items) {
            if (!Array.isArray(items) || items.length === 0) return;
            const merged = new Map((this.catalogoOffline || []).map(item => [itemKey(item), item]));
            for (const item of items) {
                if (item && item.id) merged.set(itemKey(item), item);
            }
            this.guardarCatalogoOfflineCache([...merged.values()]);
        };

        app.actualizarCatalogoOffline = async function actualizarCatalogoOffline(options = {}) {
            if (!this.isOnline) return;
            try {
                const { response, data } = await this.fetchJsonConTimeout('/ventas/catalogo/bootstrap', {}, {
                    timeoutMs: 10000,
                    slowMs: 2500,
                    markSlow: options.markSlow !== false,
                });
                if (!response.ok || !data || !Array.isArray(data.items)) return;
                this.guardarCatalogoOfflineCache(data.items);
                if (!options.silent) mostrarNotificacion('Catalogo offline actualizado', 'success');
            } catch (e) {
            }
        };

        app.catalogoOfflineVigente = function catalogoOfflineVigente() {
            if (!this.catalogoOfflineLoadedAt) return false;
            return now() - Number(this.catalogoOfflineLoadedAt) <= CATALOG_MAX_AGE_MS;
        };

        app.notificarCatalogoOffline = function notificarCatalogoOffline() {
            const ultimo = Number(this.catalogoOfflineNoticeAt || 0);
            if (now() - ultimo < 6000) return;
            this.catalogoOfflineNoticeAt = now();
            mostrarNotificacion('Mostrando catalogo guardado por conexion inestable', 'warning');
        };

        app.buscarCatalogoOffline = function buscarCatalogoOffline(query, exact = false) {
            const q = normalizedText(query);
            if (!q) return exact ? null : [];
            const items = Array.isArray(this.catalogoOffline) ? this.catalogoOffline : [];
            if (exact) {
                return items.find(item => {
                    return [item.codigo, item.codigo_barras, item.codigo_proveedor]
                        .some(value => normalizedText(value) === q);
                }) || null;
            }
            return items.filter(item => {
                const texto = normalizedText([
                    item.codigo,
                    item.nombre,
                    item.marca,
                    item.modelo,
                ].join(' '));
                return texto.includes(q);
            }).slice(0, 20);
        };

        const originalInit = app.init;
        if (typeof originalInit === 'function') {
            app.init = function initOfflineResilience(...args) {
                this.cargarCatalogoOfflineCache();
                this.connectionStatus = navigator.onLine ? 'online' : 'offline';
                const result = originalInit.apply(this, args);
                window.addEventListener('online', () => {
                    this.marcarConexionOnline();
                    this.actualizarCatalogoOffline({ silent: true, markSlow: false });
                    this.programarSincronizacionPendientes(1500);
                });
                window.addEventListener('offline', () => this.marcarConexionOffline());
                if (this.isOnline) {
                    setTimeout(() => this.actualizarCatalogoOffline({ silent: true, markSlow: false }), 500);
                    this.programarSincronizacionPendientes(2500);
                }
                return result;
            };
        }

        app.buscarProductos = async function buscarProductosOfflineAware() {
            const q = (this.busqueda || '').trim();
            if (q.length < 2) {
                this.resultados = [];
                return;
            }
            try {
                const { response, data } = await this.fetchJsonConTimeout(`/ventas/catalogo/buscar?q=${encodeURIComponent(q)}`, {}, {
                    timeoutMs: 5000,
                    slowMs: 1200,
                });
                if (response.ok && Array.isArray(data)) {
                    this.resultados = data;
                    this.fusionarCatalogoOffline(data);
                    return;
                }
            } catch (e) {
            }
            const fallback = this.buscarCatalogoOffline(q, false);
            this.resultados = fallback;
            if (fallback.length > 0) this.notificarCatalogoOffline();
        };

        app.agregarPorEnter = async function agregarPorEnterOfflineAware() {
            const q = (this.busqueda || '').trim();
            if (!q) return;
            try {
                const { response, data } = await this.fetchJsonConTimeout(`/ventas/catalogo/buscar_exacto?q=${encodeURIComponent(q)}`, {}, {
                    timeoutMs: 3500,
                    slowMs: 1000,
                });
                if (response.ok && data && data.id) {
                    this.fusionarCatalogoOffline([data]);
                    this.agregarProducto(data);
                    return;
                }
            } catch (e) {
            }

            const exactoOffline = this.buscarCatalogoOffline(q, true);
            if (exactoOffline) {
                this.notificarCatalogoOffline();
                this.agregarProducto(exactoOffline);
                return;
            }

            await this.buscarProductos();
            this.agregarPrimero();
        };

        const originalGuardarVentaPendiente = app.guardarVentaPendiente;
        if (typeof originalGuardarVentaPendiente === 'function') {
            app.guardarVentaPendiente = function guardarVentaPendienteConEstado(payload, clientRequestId) {
                const before = Array.isArray(this.ventasPendientes) ? this.ventasPendientes.length : 0;
                originalGuardarVentaPendiente.call(this, payload, clientRequestId);
                if ((this.ventasPendientes || []).length > before && this.ventasPendientes[0]) {
                    this.ventasPendientes[0].estado_sync = 'pendiente';
                    this.ventasPendientes[0].ultimo_error = '';
                    this.guardarVentasPendientes();
                    this.programarSincronizacionPendientes(5000);
                }
            };
        }

        app.sincronizarVentasPendientes = async function sincronizarVentasPendientesRobusto(options = {}) {
            if (!this.isOnline || this.sincronizandoPendientes) return;
            if (!this.ventasPendientes || this.ventasPendientes.length === 0) return;

            this.sincronizandoPendientes = true;
            this.connectionStatus = 'syncing';
            this.ultimaSincronizacionError = '';

            const conexionSaludable = await this.chequearConexionSaludable();
            if (!conexionSaludable) {
                this.sincronizandoPendientes = false;
                this.aumentarEsperaSincronizacion();
                this.programarSincronizacionPendientes();
                if (!options.automatico) {
                    mostrarNotificacion('La venta queda guardada. Se enviara cuando la conexion responda bien.', 'warning');
                }
                return;
            }

            this.connectionStatus = 'syncing';
            // Solo reintentamos automáticamente las que no quedaron detenidas por
            // un error permanente (esas esperan una acción manual: reintentar o descartar).
            const pendientes = [...this.ventasPendientes].filter(v => (v.estado_sync || '') !== 'error');

            for (const venta of pendientes) {
                const payload = { ...(venta.payload || {}), client_request_id: venta.client_request_id };
                venta.estado_sync = 'sincronizando';
                venta.updated_at = now();
                venta.ultimo_error = '';
                this.guardarVentasPendientes();
                try {
                    // Antes de reenviar, preguntamos al servidor si esta venta ya quedó
                    // resuelta (registrada, aún pendiente de cobro o descartada). Así una
                    // venta que se procesó pero cuya respuesta se perdió por timeout, o
                    // cuyo pendiente ya fue cobrado/cancelado, sale de la cola sin quedar
                    // trabada como "requiere revisión".
                    const yaResuelta = await this.consultarVentaYaRegistrada(venta.client_request_id);
                    if (yaResuelta) {
                        this.ventasPendientes = (this.ventasPendientes || []).filter(v => v.client_request_id !== venta.client_request_id);
                        this.guardarVentasPendientes();
                        if (yaResuelta.source === 'descartada') {
                            mostrarNotificacion('Una venta en cola ya no correspondia y se quito de la cola', 'info');
                        } else {
                            mostrarNotificacion(yaResuelta.id_venta ? `Venta ya sincronizada: #${yaResuelta.id_venta}` : 'Venta ya sincronizada', 'success');
                        }
                        continue;
                    }

                    const { response, data } = await this.fetchJsonConTimeout('/ventas/procesar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    }, { timeoutMs: 9000, slowMs: 1800 });
                    if (response.ok && data && data.success) {
                        this.ventasPendientes = (this.ventasPendientes || []).filter(v => v.client_request_id !== venta.client_request_id);
                        this.guardarVentasPendientes();
                        mostrarNotificacion(data.id_venta ? `Venta sincronizada: #${data.id_venta}` : 'Venta sincronizada', 'success');
                        try {
                            window.dispatchEvent(new CustomEvent('dashboard:refresh-totals'));
                            if (window.dashboardRefreshTotals) window.dashboardRefreshTotals();
                        } catch (e) {
                        }
                        continue;
                    }

                    const mensaje = (data && data.error) ? data.error : `No se pudo sincronizar (HTTP ${response.status})`;
                    venta.ultimo_error = mensaje;
                    this.ultimaSincronizacionError = mensaje;
                    if (esErrorTemporalServidor(response.status)) {
                        // Transitorio: la venta sigue pendiente y se reintenta sola.
                        venta.estado_sync = 'pendiente';
                        venta.updated_at = now();
                        this.guardarVentasPendientes();
                        this.aumentarEsperaSincronizacion();
                        this.programarSincronizacionPendientes();
                        break;
                    }
                    // Permanente (payload/estado inválido, sin permisos, etc.): queda
                    // detenida esperando revisión manual, pero no bloquea a las demás.
                    venta.estado_sync = 'error';
                    venta.updated_at = now();
                    this.guardarVentasPendientes();
                    mostrarNotificacion(`Una venta en cola necesita revision: ${mensaje}`, 'error');
                    continue;
                } catch (e) {
                    venta.estado_sync = 'pendiente';
                    venta.updated_at = now();
                    venta.ultimo_error = e && e.posTimeout ? 'Servidor sin respuesta' : 'Conexion inestable';
                    this.ultimaSincronizacionError = venta.ultimo_error;
                    this.guardarVentasPendientes();
                    this.aumentarEsperaSincronizacion();
                    this.programarSincronizacionPendientes();
                    break;
                }
            }

            this.sincronizandoPendientes = false;
            const quedanPendientes = Array.isArray(this.ventasPendientes)
                && this.ventasPendientes.some(v => (v.estado_sync || '') !== 'error');
            if (!this.ventasPendientes || this.ventasPendientes.length === 0) {
                this.posSyncRetryDelayMs = SYNC_RETRY_MS;
                this.ultimaSincronizacionError = '';
            } else if (!quedanPendientes) {
                // Solo quedan ventas detenidas por error permanente: no hay nada que
                // reintentar solo, así que no dejamos el aviso de "último intento".
                this.ultimaSincronizacionError = '';
            }
            if (this.isOnline && this.connectionStatus === 'syncing') this.marcarConexionOnline();
        };

        app.consultarVentaYaRegistrada = async function consultarVentaYaRegistrada(clientRequestId) {
            const id = String(clientRequestId || '').trim();
            if (!id) return null;
            try {
                const { response, data } = await this.fetchJsonConTimeout(`/ventas/sync-status/${encodeURIComponent(id)}`, {}, {
                    timeoutMs: 5000,
                    slowMs: 1500,
                    markSlow: false,
                });
                if (response.ok && data && data.success && data.exists) return data;
            } catch (e) {
            }
            return null;
        };

        app.ventaPendienteEsDescartable = function ventaPendienteEsDescartable(venta) {
            // Solo se puede descartar manualmente una venta detenida por error permanente,
            // nunca una que todavia se va a reintentar sola (asi no se pierde nada por error).
            return String((venta && venta.estado_sync) || 'pendiente') === 'error';
        };

        app.reintentarVentaPendiente = function reintentarVentaPendiente(clientRequestId) {
            const id = String(clientRequestId || '').trim();
            const venta = (this.ventasPendientes || []).find(v => v.client_request_id === id);
            if (venta) {
                venta.estado_sync = 'pendiente';
                venta.ultimo_error = '';
                venta.updated_at = now();
                this.guardarVentasPendientes();
            }
            return this.sincronizarVentasPendientes();
        };

        app.descartarVentaPendiente = function descartarVentaPendiente(clientRequestId) {
            const id = String(clientRequestId || '').trim();
            if (!id) return;
            const venta = (this.ventasPendientes || []).find(v => v.client_request_id === id);
            if (!venta) return;
            if (!this.ventaPendienteEsDescartable(venta)) {
                mostrarNotificacion('Solo se pueden descartar ventas detenidas por error. Esta se reintentara sola.', 'warning');
                return;
            }
            const total = (typeof this.formatNumber === 'function') ? this.formatNumber(this.totalVentaPendiente(venta)) : this.totalVentaPendiente(venta);
            const confirmar = window.confirm(
                '¿Descartar definitivamente esta venta en cola?\n\n' +
                `Total: ₲ ${total}\n` +
                `Motivo del error: ${venta.ultimo_error || 'desconocido'}\n\n` +
                'Esta accion NO se puede deshacer. Solo hacelo si confirmaste que la venta no debe registrarse.'
            );
            if (!confirmar) return;
            this.ventasPendientes = (this.ventasPendientes || []).filter(v => v.client_request_id !== id);
            this.guardarVentasPendientes();
            if (!this.ventasPendientes.some(v => (v.estado_sync || '') === 'error')) {
                this.ultimaSincronizacionError = '';
            }
            mostrarNotificacion('Venta descartada de la cola local', 'info');
        };

        const originalEjecutarVenta = app.ejecutarVenta;
        if (typeof originalEjecutarVenta === 'function') {
            app.ejecutarVenta = async function ejecutarVentaConTimeout(...args) {
                const originalFetch = window.fetch;
                const self = this;
                window.fetch = function fetchPosConTimeout(input, init) {
                    if (String(input || '').includes('/ventas/procesar')) {
                        return self.fetchResponseConTimeout(input, init, { timeoutMs: 9000, slowMs: 1800 }, originalFetch.bind(this));
                    }
                    return originalFetch.call(this, input, init);
                };
                try {
                    return await originalEjecutarVenta.apply(this, args);
                } finally {
                    window.fetch = originalFetch;
                }
            };
        }

        const originalEnviarVentaACaja = app.enviarVentaACaja;
        if (typeof originalEnviarVentaACaja === 'function') {
            app.enviarVentaACaja = async function enviarVentaACajaConTimeout(...args) {
                const originalFetch = window.fetch;
                const self = this;
                window.fetch = function fetchCajaConTimeout(input, init) {
                    if (String(input || '').includes('/ventas/enviar-a-caja')) {
                        return self.fetchResponseConTimeout(input, init, { timeoutMs: 7000, slowMs: 1500 }, originalFetch.bind(this));
                    }
                    return originalFetch.call(this, input, init);
                };
                try {
                    return await originalEnviarVentaACaja.apply(this, args);
                } finally {
                    window.fetch = originalFetch;
                }
            };
        }

        return app;
    };
})();
