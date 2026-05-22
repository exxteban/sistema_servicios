(function () {
    if (window.__dashboardEventBusInitialized) {
        return;
    }
    window.__dashboardEventBusInitialized = true;

    const STORAGE_KEY = 'dashboard-sync-v1';
    const CHANNEL_NAME = 'dashboard-sync';
    const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
    const POST_COMMIT_DELAYS = [0, 250, 1000];
    const FORM_SUBMIT_DELAYS = [800, 1600, 3000];
    let lastPayloadId = '';
    let channel = null;

    function uniqueId() {
        return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    }

    function isSameOrigin(url) {
        try {
            return new URL(url, window.location.origin).origin === window.location.origin;
        } catch (e) {
            return false;
        }
    }

    function parseUrl(input) {
        try {
            if (typeof input === 'string' || input instanceof URL) {
                return new URL(input, window.location.origin);
            }
            if (input && input.url) {
                return new URL(input.url, window.location.origin);
            }
        } catch (e) {
        }
        return null;
    }

    function methodFrom(input, init) {
        const raw = (init && init.method) || (input && input.method) || 'GET';
        return String(raw || 'GET').toUpperCase();
    }

    function mutationReasonFor(url, method) {
        if (!url || SAFE_METHODS.has(method) || !isSameOrigin(url.toString())) {
            return '';
        }

        const path = url.pathname || '';
        const rules = [
            [/^\/clientes\/\d+\/servicios\/(?:asignar|\d+\/actualizar)$/, 'clientes-servicios'],
            [/^\/agenda\/turnos\/peluqueria\/crear$/, 'agenda-turno'],
            [/^\/agenda\/actividades(?:\/nueva|\/\d+\/(?:editar|iniciar|completar|cancelar|eliminar|reprogramar))$/, 'agenda'],
            [/^\/ventas\/(?:procesar|enviar-a-caja)$/, 'ventas'],
            [/^\/caja\/api\/cola-cobro\/\d+\/(?:tomar|liberar|cancelar|cobrar)$/, 'caja-cola-cobro'],
            [/^\/pedidos\/.*(?:estado|reabrir|items|pagos|entregar|enviar-a-caja|cola-cobro).*$/, 'pedidos'],
            [/^\/cobranzas\/.*(?:cobros|enviar-a-caja|cola-cobro).*$/, 'cobranzas'],
            [/^\/reparaciones\/\d+\/(?:estado|costos|vincular_venta|generar_venta|enviar_a_caja|items).*$/, 'reparaciones'],
        ];

        const match = rules.find(([pattern]) => pattern.test(path));
        return match ? match[1] : '';
    }

    function dispatchDashboardRefresh(payload) {
        const detail = payload || {};
        window.dispatchEvent(new CustomEvent('dashboard:sync', { detail }));
        window.dispatchEvent(new CustomEvent('dashboard:refresh-totals', { detail }));
        window.dispatchEvent(new CustomEvent('dashboard:cobros-pendientes-changed', { detail }));
    }

    function replayPayload(payload) {
        if (!payload || payload.id === lastPayloadId) {
            return;
        }
        lastPayloadId = payload.id;
        const delays = Array.isArray(payload.delays) && payload.delays.length
            ? payload.delays
            : POST_COMMIT_DELAYS;

        delays.forEach((delay) => {
            window.setTimeout(() => dispatchDashboardRefresh(payload), Number(delay || 0));
        });
    }

    function broadcastPayload(payload) {
        try {
            if (channel) {
                channel.postMessage(payload);
            }
        } catch (e) {
        }
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
        } catch (e) {
        }
    }

    function emitDashboardSync(reason, detail, options) {
        const payload = {
            id: uniqueId(),
            reason: String(reason || 'dashboard-data-changed'),
            at: Date.now(),
            detail: detail || {},
            delays: (options && Array.isArray(options.delays)) ? options.delays : POST_COMMIT_DELAYS,
        };

        replayPayload(payload);
        if (!options || options.broadcast !== false) {
            broadcastPayload(payload);
        }
        return payload;
    }

    window.appDashboardSync = {
        storageKey: STORAGE_KEY,
        emit: emitDashboardSync,
        refreshNow(detail) {
            return emitDashboardSync('manual-refresh', detail || {}, { delays: [0] });
        },
        reasonFor(input, method) {
            return mutationReasonFor(parseUrl(input), String(method || 'GET').toUpperCase());
        },
    };

    if (typeof BroadcastChannel === 'function') {
        try {
            channel = new BroadcastChannel(CHANNEL_NAME);
            channel.addEventListener('message', (event) => {
                replayPayload(event && event.data ? event.data : null);
            });
        } catch (e) {
            channel = null;
        }
    }

    window.addEventListener('storage', (event) => {
        if (!event || event.key !== STORAGE_KEY || !event.newValue) {
            return;
        }
        try {
            replayPayload(JSON.parse(event.newValue));
        } catch (e) {
        }
    });

    if (window.fetch) {
        const originalFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            const method = methodFrom(input, init);
            const url = parseUrl(input);
            const reason = mutationReasonFor(url, method);
            return originalFetch(input, init).then((response) => {
                if (reason && response && response.ok) {
                    emitDashboardSync(reason, {
                        method,
                        path: url ? url.pathname : '',
                        status: response.status,
                        source: 'fetch',
                    }, { delays: POST_COMMIT_DELAYS });
                }
                return response;
            });
        };
    }

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.hasAttribute('data-dashboard-sync-skip')) {
            return;
        }
        const method = String(form.getAttribute('method') || form.method || 'GET').toUpperCase();
        const url = parseUrl(form.getAttribute('action') || form.action || window.location.href);
        const reason = mutationReasonFor(url, method);
        if (!reason) {
            return;
        }
        emitDashboardSync(reason, {
            method,
            path: url ? url.pathname : '',
            source: 'form-submit',
        }, { delays: FORM_SUBMIT_DELAYS });
    }, true);
})();
