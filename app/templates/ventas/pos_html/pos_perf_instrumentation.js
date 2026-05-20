(function () {
    const STORAGE_KEY = 'pos_perf_nav_start_v1';
    const PERF_WINDOW_MS = 15000;
    const state = {
        startedAt: performance.now(),
        summaryPrinted: false,
        marks: {
            script_loaded_ms: 0
        },
        requests: {},
        navigation: null
    };

    function nowMs() {
        return performance.now();
    }

    function mark(name, value) {
        state.marks[name] = value;
    }

    function readNavigationStart() {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || !parsed.started_at_ms) return null;
            if ((Date.now() - parsed.started_at_ms) > PERF_WINDOW_MS) return null;
            return parsed;
        } catch (e) {
            return null;
        }
    }

    function clearNavigationStart() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch (e) {
        }
    }

    function extractUrl(input) {
        if (!input) return '';
        if (typeof input === 'string') return input;
        if (typeof input.url === 'string') return input.url;
        return String(input);
    }

    function trackFetch(url, startedAt, finishedAt, ok, status) {
        const normalized = extractUrl(url);
        if (!normalized) return;

        if (
            normalized.includes('/clientes/buscar_json')
            && normalized.includes('?q=')
            && !state.requests.clientes_default
        ) {
            state.requests.clientes_default = {
                duration_ms: finishedAt - startedAt,
                ok: !!ok,
                status: status ?? null
            };
        }

        if (normalized.includes('/ventas/validar-carrito') && !state.requests.validar_carrito) {
            state.requests.validar_carrito = {
                duration_ms: finishedAt - startedAt,
                ok: !!ok,
                status: status ?? null
            };
        }
    }

    function printSummary(reason) {
        if (state.summaryPrinted) return;
        state.summaryPrinted = true;
        const tabLoad = window.__posPerfTabLoadTiming || null;
        const rel = (nameA, nameB) => {
            if (!tabLoad) return null;
            const a = tabLoad[nameA];
            const b = tabLoad[nameB];
            if (typeof a !== 'number' || typeof b !== 'number') return null;
            return b - a;
        };

        const summary = {
            reason,
            route: window.location.pathname,
            nav_to_script_ms: state.navigation ? (state.navigation.script_started_at_ms - state.navigation.started_at_ms) : null,
            tab_fetch_ms: rel('fetch_start_perf', 'fetch_response_perf'),
            tab_response_text_ms: rel('fetch_response_perf', 'response_text_end_perf'),
            tab_extract_ms: rel('extract_start_perf', 'extract_end_perf'),
            tab_apply_payload_ms: rel('apply_payload_start_perf', 'apply_payload_end_perf'),
            tab_script_replace_ms: rel('script_replace_start_perf', 'script_replace_end_perf'),
            alpine_init_ms: (state.marks.alpine_init_start_ms !== undefined && state.marks.alpine_init_end_ms !== undefined)
                ? (state.marks.alpine_init_end_ms - state.marks.alpine_init_start_ms)
                : null,
            input_found_ms: state.marks.input_found_ms ?? null,
            input_focused_ms: state.marks.input_focused_ms ?? null,
            clientes_default_fetch_ms: state.requests.clientes_default ? state.requests.clientes_default.duration_ms : null,
            validar_carrito_fetch_ms: state.requests.validar_carrito ? state.requests.validar_carrito.duration_ms : null
        };

        console.groupCollapsed('[POS PERF]');
        console.table(summary);
        console.log('detail', {
            navigation: state.navigation,
            tabLoad,
            marks: state.marks,
            requests: state.requests
        });
        console.groupEnd();

        window.dispatchEvent(new CustomEvent('pos:perf-summary', { detail: summary }));
        clearNavigationStart();
    }

    function waitForInput(activeState) {
        const startedAt = nowMs();
        const maxWaitMs = 5000;

        function check() {
            const input = document.querySelector('[x-ref="inputBusqueda"]');
            const elapsed = nowMs() - startedAt;

            if (input && activeState.marks.input_found_ms === undefined) {
                activeState.marks.input_found_ms = nowMs() - activeState.startedAt;
            }

            if (input && document.activeElement === input) {
                activeState.marks.input_focused_ms = nowMs() - activeState.startedAt;
                if (activeState.printSummary) {
                    activeState.printSummary('input-focused');
                }
                return;
            }

            if (elapsed >= maxWaitMs) {
                if (activeState.printSummary) {
                    activeState.printSummary(input ? 'input-found-timeout-focus' : 'input-not-found');
                }
                return;
            }

            requestAnimationFrame(check);
        }

        requestAnimationFrame(check);
    }

    state.navigation = readNavigationStart();
    if (state.navigation) {
        state.navigation.script_started_at_ms = Date.now();
    }

    window.__posPerfDebugState = state;
    window.__posPerfWaitForInput = waitForInput;
    state.printSummary = printSummary;

    if (!window.__posPerfFetchPatched && typeof window.fetch === 'function') {
        const originalFetch = window.fetch.bind(window);
        window.fetch = async function (...args) {
            const startedAt = nowMs();
            try {
                const response = await originalFetch(...args);
                const activeState = window.__posPerfDebugState;
                if (activeState && activeState.trackFetch) {
                    activeState.trackFetch(args[0], startedAt, nowMs(), true, response.status);
                }
                return response;
            } catch (error) {
                const activeState = window.__posPerfDebugState;
                if (activeState && activeState.trackFetch) {
                    activeState.trackFetch(args[0], startedAt, nowMs(), false, null);
                }
                throw error;
            }
        };
        window.__posPerfFetchPatched = true;
    }

    if (!window.__posPerfAlpinePatched && window.Alpine && typeof window.Alpine.initTree === 'function') {
        const originalInitTree = window.Alpine.initTree.bind(window.Alpine);
        window.Alpine.initTree = function (root, ...rest) {
            const activeState = window.__posPerfDebugState;
            const isPosRoot = !!(root && root.querySelector && root.querySelector('[x-ref="inputBusqueda"]'));
            if (activeState && isPosRoot) {
                activeState.marks.alpine_init_start_ms = nowMs() - activeState.startedAt;
            }

            const result = originalInitTree(root, ...rest);

            if (activeState && isPosRoot) {
                activeState.marks.alpine_init_end_ms = nowMs() - activeState.startedAt;
                if (typeof window.__posPerfWaitForInput === 'function') {
                    window.__posPerfWaitForInput(activeState);
                }
            }
            return result;
        };
        window.__posPerfAlpinePatched = true;
    } else {
        requestAnimationFrame(() => waitForInput(state));
    }

    state.trackFetch = trackFetch;
})();
