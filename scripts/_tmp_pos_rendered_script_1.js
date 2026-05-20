
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
(function () {
        const POS_STATE_KEY = 'pos_venta_actual';
        const POS_STATE_MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 horas
        const PENDING_SALES_KEY = 'pos_ventas_pendientes_v1';
        const LAST_SALE_KEY = 'pos_ultima_venta';
    const POS_EMPRESA = {"direccion": "Santa Rosa c/ 10 de Agosto", "nombre": "Pablito\u0027s Cell", "ruc": "00000000-0", "telefono": "0984758819"};
    const REPARACION_DATA = null;
    const COLA_COBRO_DATA = null;
    const REPARACION_TOKEN = null;
    const VENDEDORES_CAJEROS = [{"id_usuario": 1, "nombre_completo": "Administrador del Sistema", "rol": "Administrador"}];
    const VENDEDOR_ID_INICIAL = 1;
    const OCULTAR_SELECTOR_VENDEDOR_POS = true;
    const CAJA_FLUJO_ENVIADO_ACTIVO = false;
    const PUEDE_ENVIAR_CAJA_VENTA = true;
    const CAJA_EXIGIR_CAJERO_PARA_COBRO = false;
    const PUEDE_COBRAR_POS_DIRECTO = true;
    const SOLO_REGISTRO_VENDEDOR = false;
    const POS_VENTAS_CREDITO_ACTIVO = false;
    const POS_METODO_CREDITO = null;

    function readInitialPosState() {
        try {
            const raw = sessionStorage.getItem(POS_STATE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            const ageMs = Date.now() - Number(parsed && parsed.timestamp ? parsed.timestamp : 0);
            if (!Number.isFinite(ageMs) || ageMs > POS_STATE_MAX_AGE_MS) {
                sessionStorage.removeItem(POS_STATE_KEY);
                return null;
            }
            return parsed;
        } catch (e) {
            return null;
        }
    }

    const POS_INITIAL_STATE = readInitialPosState();

    function posApp() {
        return {
            busqueda: '',
            resultados: [],
            carrito: [],
            estadoRestaurado: false,
            ultimaVentaId: null,
            isOnline: true,
            forzarPrecioMayorista: false,
            bloquearPrecioMayorista: false,
            ventasPendientes: [],
            mostrarModalVentaPendiente: false,
            ventaPendienteActual: null,
            offlineTicketHtml: '',
            printFocusPollId: null,
            printFocusTimeoutId: null,
            printEnCurso: false,

            // Client Search State
            buscandoCliente: false,
            busquedaCliente: '',
            clientesEncontrados: [],
            mostrarResultadosClientes: false,

            clienteId: 1, // Default a consumidor final
            clienteSeleccionado: null,
            alertaClienteFielActiva: POS_INITIAL_STATE && typeof POS_INITIAL_STATE.alertaClienteFielActiva === 'boolean'
                ? POS_INITIAL_STATE.alertaClienteFielActiva
                : true,
            clienteFielResumen: {
                clienteId: null,
                cantidadCompras: 0,
                cargando: false,
                error: '',
                urlHistorial: ''
            },
            clienteFielCache: {},
            vendedoresCajeros: (typeof VENDEDORES_CAJEROS !== 'undefined' && Array.isArray(VENDEDORES_CAJEROS)) ? VENDEDORES_CAJEROS : [],
            vendedorId: (typeof VENDEDOR_ID_INICIAL !== 'undefined' && VENDEDOR_ID_INICIAL !== null) ? Number(VENDEDOR_ID_INICIAL) : null,
            ocultarSelectorVendedorPos: !!OCULTAR_SELECTOR_VENDEDOR_POS,
            cajaFlujoEnviadoActivo: !!CAJA_FLUJO_ENVIADO_ACTIVO,
            puedeEnviarCajaVenta: !!PUEDE_ENVIAR_CAJA_VENTA,
            cajaExigirCajeroParaCobro: !!CAJA_EXIGIR_CAJERO_PARA_COBRO,
            puedeCobrarPosDirecto: !!PUEDE_COBRAR_POS_DIRECTO,
            soloRegistroVendedor: !!SOLO_REGISTRO_VENDEDOR,
            ventasCreditoActivo: !!POS_VENTAS_CREDITO_ACTIVO,
            creditoMetodoPagoId: POS_METODO_CREDITO ? Number(POS_METODO_CREDITO.id_metodo_pago || 0) : null,
            creditoMetodoPagoNombre: POS_METODO_CREDITO ? String(POS_METODO_CREDITO.nombre || 'Credito Tienda') : 'Credito Tienda',
            condicionVenta: (POS_INITIAL_STATE && POS_INITIAL_STATE.condicionVenta === 'credito' && POS_VENTAS_CREDITO_ACTIVO && POS_METODO_CREDITO)
                ? 'credito'
                : 'contado',
            creditoModo: (POS_INITIAL_STATE && POS_INITIAL_STATE.creditoModo === 'cuenta_corriente')
                ? 'cuenta_corriente'
                : 'cuenta_corriente',
            enviandoCaja: false,
            reparacionId: null,
            colaCobroId: null,
            reparacionToken: (typeof REPARACION_TOKEN !== 'undefined' && REPARACION_TOKEN !== null) ? String(REPARACION_TOKEN) : '',

            // Nuevo cliente dropdown data
            clientesDefault: [], // Clientes cargados inicialmente
            descuento: 0,
            subtotal: 0,
            total: 0,
            procesando: false,

            // Pagos múltiples
            pagos: [],
            totalPagado: 0,
            saldoPendiente: 0,
            vuelto: 0,

            // Control de stock warnings
            mostrarModalStock: false,
            itemsConWarning: [],

            // Modal de precios por opciones
            mostrarModalPrecioOpciones: false,
            productoPrecioOpciones: null,
            preciosOpcionesActuales: [],

            // Vista previa de venta (antes de registrar)
            mostrarModalVistaPrevia: false,
            ticketPreviewHtml: '',
            confirmandoVenta: false,

            // CRM Historial
            mostrarModalHistorial: false,
            historialCargando: false,
            historialDatos: {
                cliente: null,
                historial: [],
                estadisticas: { total_gastado: 0, cantidad_compras: 0, promedio_compra: 0 }
            },
            resumenCreditoCliente: {
                clienteId: null,
                saldoTotal: 0,
                cuentasAbiertas: 0,
                cuentasVencidas: 0,
                cargando: false,
                urlCliente: '',
                urlCobrar: '',
            },
            resumenCreditoCache: {},

            limpiarResumenCreditoCliente() {
                this.resumenCreditoCliente = {
                    clienteId: null,
                    saldoTotal: 0,
                    cuentasAbiertas: 0,
                    cuentasVencidas: 0,
                    cargando: false,
                    urlCliente: '',
                    urlCobrar: '',
                };
            },

            clienteTieneDeudaVisible() {
                return !!(this.resumenCreditoCliente && this.resumenCreditoCliente.saldoTotal > 0 && this.resumenCreditoCliente.cuentasAbiertas > 0);
            },

            clienteEstaMoraVisible() {
                return !!(this.resumenCreditoCliente && this.resumenCreditoCliente.cuentasVencidas > 0);
            },

            async actualizarResumenCreditoCliente(cliente = null) {
                if (!this.ventasCreditoActivo) {
                    this.limpiarResumenCreditoCliente();
                    return;
                }

                const clienteId = Number(cliente && cliente.id_cliente ? cliente.id_cliente : (this.clienteId || 0));
                if (!clienteId || clienteId === 1) {
                    this.limpiarResumenCreditoCliente();
                    return;
                }

                const cache = this.resumenCreditoCache[clienteId];
                if (cache) {
                    this.resumenCreditoCliente = { ...cache, cargando: false };
                    return;
                }

                this.resumenCreditoCliente = {
                    clienteId,
                    saldoTotal: 0,
                    cuentasAbiertas: 0,
                    cuentasVencidas: 0,
                    cargando: true,
                    urlCliente: '',
                    urlCobrar: '',
                };

                try {
                    const response = await fetch(`/cobranzas/api/clientes/${clienteId}/resumen`);
                    const data = await response.json();
                    if (!response.ok || !data.success) {
                        throw new Error(data.mensaje || data.error || 'No se pudo consultar deuda del cliente');
                    }

                    const resumen = {
                        clienteId,
                        saldoTotal: Number(data.saldo_total || 0),
                        cuentasAbiertas: Number(data.cuentas_abiertas || 0),
                        cuentasVencidas: Number(data.cuentas_vencidas || 0),
                        urlCliente: data.url_cliente || '',
                        urlCobrar: data.url_cobrar || '',
                    };
                    this.resumenCreditoCache[clienteId] = resumen;

                    if (Number(this.clienteId || 0) === clienteId) {
                        this.resumenCreditoCliente = { ...resumen, cargando: false };
                    }
                } catch (e) {
                    if (Number(this.clienteId || 0) === clienteId) {
                        this.limpiarResumenCreditoCliente();
                    }
                }
            },

            abrirCobranzaCliente(url) {
                const destino = String(url || '').trim();
                if (!destino) return;
                if (typeof window.appOpenTab === 'function') {
                    window.appOpenTab(destino, 'Cobranzas', 'fas fa-hand-holding-usd', {
                        activate: true,
                        scroll: true,
                        preferExistingByTitle: false,
                    });
                    return;
                }
                window.location.href = destino;
            },
            creditoCuotas: 3,
            creditoFrecuenciaDias: 30,
            creditoPrimerVencimiento: '',

            creditoModoCuotasActivo() {
                return this.esVentaCredito() && this.creditoModo === 'cuotas';
            },

            asegurarFechaPrimerVencimientoCredito() {
                if (this.creditoPrimerVencimiento) return;
                const dias = Math.max(1, parseInt(this.creditoFrecuenciaDias) || 30);
                const fecha = new Date();
                fecha.setDate(fecha.getDate() + dias);
                this.creditoPrimerVencimiento = fecha.toISOString().slice(0, 10);
            },

            cuotaEstimadaCredito() {
                if (!this.creditoModoCuotasActivo()) return 0;
                const cuotas = Math.max(1, parseInt(this.creditoCuotas) || 1);
                return this.montoFinanciadoActual() / cuotas;
            },

            creditoPlanPayload() {
                if (!this.esVentaCredito() || this.creditoModo !== 'cuotas') {
                    return null;
                }
                this.asegurarFechaPrimerVencimientoCredito();
                return {
                    cantidad_cuotas: Math.max(2, parseInt(this.creditoCuotas) || 0),
                    frecuencia_dias: Math.max(1, parseInt(this.creditoFrecuenciaDias) || 0),
                    fecha_primer_vencimiento: this.creditoPrimerVencimiento || null,
                };
            },

            validarCreditoCuotasAntesDeProcesar() {
                if (!this.creditoModoCuotasActivo()) return true;

                const cuotas = parseInt(this.creditoCuotas) || 0;
                const frecuenciaDias = parseInt(this.creditoFrecuenciaDias) || 0;
                this.asegurarFechaPrimerVencimientoCredito();

                if (cuotas < 2) {
                    mostrarNotificacion('Define al menos 2 cuotas para usar el modo cuotas.', 'warning');
                    return false;
                }
                if (cuotas > 60) {
                    mostrarNotificacion('La cantidad de cuotas no puede superar 60.', 'warning');
                    return false;
                }
                if (frecuenciaDias <= 0 || frecuenciaDias > 365) {
                    mostrarNotificacion('La frecuencia entre cuotas debe estar entre 1 y 365 dias.', 'warning');
                    return false;
                }
                if (!this.creditoPrimerVencimiento) {
                    mostrarNotificacion('Define la fecha del primer vencimiento.', 'warning');
                    return false;
                }

                const fechaVenta = new Date();
                fechaVenta.setHours(0, 0, 0, 0);
                const primerVencimiento = new Date(`${this.creditoPrimerVencimiento}T00:00:00`);
                if (Number.isNaN(primerVencimiento.getTime())) {
                    mostrarNotificacion('La fecha del primer vencimiento no es valida.', 'warning');
                    return false;
                }
                if (primerVencimiento < fechaVenta) {
                    mostrarNotificacion('La fecha del primer vencimiento no puede ser anterior a hoy.', 'warning');
                    return false;
                }
                return true;
            },

            init() {
                this.isOnline = navigator.onLine;
                this.cargarVentasPendientes();
                this.cargarUltimaVenta();
                if (this.isOnline) {
                    this.sincronizarVentasPendientes();
                }
                const self = this;
                window.addEventListener('online', () => {
                    self.isOnline = true;
                    self.sincronizarVentasPendientes();
                });
                window.addEventListener('offline', () => {
                    self.isOnline = false;
                });

                // Cargar cliente por defecto (Consumidor Final id=1)
                this.buscarClientes('', true).then(() => {
                    if (typeof REPARACION_DATA !== 'undefined' && REPARACION_DATA && REPARACION_DATA.id) {
                        const rid = REPARACION_DATA.id;
                        const skipKey = `pos_reparacion_skip_${rid}`;
                        const skipTokenKey = `pos_reparacion_skip_token_${rid}`;
                        const skip = sessionStorage.getItem(skipKey) === '1';
                        const tokenActual = this.reparacionToken || '';
                        const tokenSkip = sessionStorage.getItem(skipTokenKey) || '';
                        if (skip && tokenSkip === tokenActual) {
                            this.restaurarEstado();
                        } else {
                            this.cargarDatosReparacion();
                        }
                    } else if (typeof COLA_COBRO_DATA !== 'undefined' && COLA_COBRO_DATA && COLA_COBRO_DATA.id) {
                        this.cargarDatosPendienteCaja();
                    } else {
                        // Después de cargar clientes, intentar restaurar estado guardado
                        this.restaurarEstado();
                    }
                });

                // Configurar watchers para auto-guardar estado
                this.$watch('carrito', () => this.guardarEstado(), { deep: true });
                this.$watch('clienteId', () => {
                    this.guardarEstado();
                    this.actualizarResumenCreditoCliente();
                });
                this.$watch('vendedorId', () => this.guardarEstado());
                this.$watch('descuento', () => this.guardarEstado());
                this.$watch('pagos', () => this.guardarEstado(), { deep: true });
                this.$watch('alertaClienteFielActiva', () => this.guardarEstado());
                this.$watch('condicionVenta', () => this.guardarEstado());
                this.$watch('creditoModo', () => this.guardarEstado());
                this.enfocarBusqueda();
            },

            enfocarBusqueda() {
                this.$nextTick(() => {
                    const input = this.$refs.inputBusqueda;
                    if (!input || typeof input.focus !== 'function') return;
                    try {
                        input.focus({ preventScroll: true });
                    } catch (e) {
                        input.focus();
                    }
                    if (typeof input.select === 'function') input.select();
                });
            },

            limpiarRestauracionFocoImpresion() {
                if (this.printFocusPollId) {
                    clearInterval(this.printFocusPollId);
                    this.printFocusPollId = null;
                }
                if (this.printFocusTimeoutId) {
                    clearTimeout(this.printFocusTimeoutId);
                    this.printFocusTimeoutId = null;
                }
            },

            configurarRestauracionFocoImpresion(printWindow) {
                this.limpiarRestauracionFocoImpresion();
                const restaurar = () => {
                    this.limpiarRestauracionFocoImpresion();
                    this.enfocarBusqueda();
                };

                const onFocus = () => restaurar();
                const onVis = () => {
                    if (!document.hidden) restaurar();
                };

                window.addEventListener('focus', onFocus, { once: true });
                document.addEventListener('visibilitychange', onVis, { once: true });

                if (printWindow) {
                    this.printFocusPollId = setInterval(() => {
                        try {
                            if (printWindow.closed) restaurar();
                        } catch (e) {
                            restaurar();
                        }
                    }, 250);
                }

                this.printFocusTimeoutId = setTimeout(restaurar, 1500);
            },

            async imprimirTicketVenta(idVenta) {
                const abrirFallback = () => {
                    const w = window.open(`/ventas/${idVenta}/ticket`, '_blank');
                    if (!w) return false;
                    this.configurarRestauracionFocoImpresion(w);
                    return true;
                };

                if (this.printEnCurso) return true;
                this.printEnCurso = true;

                try {
                    const frame = this.$refs.ticketPrintFrame;
                    if (!frame) {
                        return abrirFallback();
                    }

                    const url = `/ventas/${idVenta}/ticket?embedded=1&_=${Date.now()}`;

                    return await new Promise((resolve) => {
                        let finished = false;

                        const finish = (ok) => {
                            if (finished) return;
                            finished = true;
                            try { frame.onload = null; } catch (e) { }
                            this.printEnCurso = false;
                            resolve(ok);
                        };

                        const fallback = () => {
                            this.enfocarBusqueda();
                            finish(abrirFallback());
                        };

                        frame.onload = () => {
                            setTimeout(() => {
                                try {
                                    frame.contentWindow.focus();
                                    frame.contentWindow.print();
                                    this.enfocarBusqueda();
                                    finish(true);
                                } catch (e) {
                                    fallback();
                                }
                            }, 150);
                        };

                        try {
                            frame.src = url;
                        } catch (e) {
                            fallback();
                            return;
                        }

                        setTimeout(() => {
                            if (!finished) fallback();
                        }, 5000);
                    });
                } catch (e) {
                    this.printEnCurso = false;
                    return abrirFallback();
                }
            },

            // --- Carga de Reparación ---
            cargarDatosReparacion() {
                try {
                    sessionStorage.removeItem(POS_STATE_KEY); // Limpiar estado anterior
                    this.condicionVenta = 'contado';
                    this.creditoModo = 'cuenta_corriente';
                    this.reparacionId = REPARACION_DATA.id || null;
                    if (this.reparacionId) {
                        sessionStorage.removeItem(`pos_reparacion_skip_${this.reparacionId}`);
                        sessionStorage.removeItem(`pos_reparacion_skip_token_${this.reparacionId}`);
                    }

                    // 1. Cargar Items
                    if (REPARACION_DATA.items && Array.isArray(REPARACION_DATA.items)) {
                        this.carrito = REPARACION_DATA.items.map(item => ({
                            id_producto: item.id,
                            codigo: item.codigo || '',
                            nombre: item.nombre,
                            precio: parseFloat(item.precio),
                            precio_base: parseFloat(item.precio_base || item.precio),
                            precio_mayorista: item.precio_mayorista ? parseFloat(item.precio_mayorista) : null,
                            precio_manual: item.precio_manual === true,
                            cantidad: parseInt(item.cantidad),
                            iva: parseInt(item.iva),
                            stock_disponible: parseInt(item.stock),
                            stock_minimo: parseInt(item.stock_minimo || 0),
                            stock_restante: null,
                            es_servicio: item.es_servicio,
                            stock_warning: false,
                            low_stock_warning: false,
                            green_stock_hint: false
                        }));

                        this.carrito.forEach(item => this.validarStockItem(item));
                    }

                    // 2. Cargar Cliente
                    if (REPARACION_DATA.cliente_id && REPARACION_DATA.cliente_id != 1) {
                        this.clienteId = REPARACION_DATA.cliente_id;
                        // Buscar detalles del cliente
                        fetch(`/clientes/${this.clienteId}/historial_json`)
                            .then(r => r.json())
                            .then(d => {
                                if (d.success && d.cliente) {
                                    this.clienteSeleccionado = d.cliente;
                                    this.actualizarAlertaClienteFiel(d.cliente);
                                    // Actualizar precios si corresponde
                                    if (this.usaPrecioMayorista()) {
                                        this.actualizarPreciosSegunCliente();
                                    }
                                }
                            })
                            .catch(e => console.error('Error cargando cliente de reparación:', e));
                    }

                    if (REPARACION_DATA.id_usuario_vendedor) {
                        const candidato = Number(REPARACION_DATA.id_usuario_vendedor);
                        if (this.vendedoresCajeros.some(v => Number(v.id_usuario) === candidato)) {
                            this.vendedorId = candidato;
                        }
                    }

                    // 3. Cargar Abono
                    if (REPARACION_DATA.abono > 0) {
                        this.descuento = parseFloat(REPARACION_DATA.abono);
                        mostrarNotificacion('Abono de reparación aplicado como descuento', 'info');
                    }

                    this.actualizarTotal();
                    mostrarNotificacion('Datos de reparación cargados', 'success');

                } catch (e) {
                    console.error('Error cargando datos de reparación:', e);
                    mostrarNotificacion('Error al cargar datos de la reparación', 'error');
                }
            },

            cargarDatosPendienteCaja() {
                try {
                    sessionStorage.removeItem(POS_STATE_KEY);
                    this.condicionVenta = 'contado';
                    this.creditoModo = 'cuenta_corriente';
                    this.reparacionId = null;
                    this.colaCobroId = Number(COLA_COBRO_DATA.id) || null;
                    if (COLA_COBRO_DATA.reparacion_id) {
                        this.reparacionId = Number(COLA_COBRO_DATA.reparacion_id) || null;
                    }

                    if (COLA_COBRO_DATA.items && Array.isArray(COLA_COBRO_DATA.items)) {
                        this.carrito = COLA_COBRO_DATA.items.map(item => ({
                            id_producto: item.id,
                            codigo: item.codigo || '',
                            nombre: item.nombre,
                            precio: parseFloat(item.precio),
                            precio_base: parseFloat(item.precio_base || item.precio),
                            precio_mayorista: item.precio_mayorista ? parseFloat(item.precio_mayorista) : null,
                            precio_manual: item.precio_manual === true,
                            precio_opcion_id: item.precio_opcion_id || null,
                            cantidad: parseInt(item.cantidad),
                            iva: parseInt(item.iva),
                            stock_disponible: parseInt(item.stock),
                            stock_minimo: parseInt(item.stock_minimo || 0),
                            stock_restante: null,
                            es_servicio: item.es_servicio,
                            stock_warning: false,
                            low_stock_warning: false,
                            green_stock_hint: false
                        }));

                        this.carrito.forEach(item => this.validarStockItem(item));
                    }

                    if (COLA_COBRO_DATA.cliente_id && COLA_COBRO_DATA.cliente_id != 1) {
                        this.clienteId = COLA_COBRO_DATA.cliente_id;
                        fetch(`/clientes/${this.clienteId}/historial_json`)
                            .then(r => r.json())
                            .then(d => {
                                if (d.success && d.cliente) {
                                    this.clienteSeleccionado = d.cliente;
                                    this.actualizarAlertaClienteFiel(d.cliente);
                                    if (this.usaPrecioMayorista()) {
                                        this.actualizarPreciosSegunCliente();
                                    }
                                }
                            })
                            .catch(e => console.error('Error cargando cliente de pendiente:', e));
                    }

                    if (COLA_COBRO_DATA.id_usuario_vendedor) {
                        const candidato = Number(COLA_COBRO_DATA.id_usuario_vendedor);
                        if (this.vendedoresCajeros.some(v => Number(v.id_usuario) === candidato)) {
                            this.vendedorId = candidato;
                        }
                    }

                    if (COLA_COBRO_DATA.descuento > 0) {
                        this.descuento = parseFloat(COLA_COBRO_DATA.descuento);
                    }

                    this.limpiarColaCobroDeUrl();
                    this.actualizarTotal();
                    mostrarNotificacion(`Pendiente #${this.colaCobroId} cargado`, 'success');
                } catch (e) {
                    console.error('Error cargando pendiente de caja:', e);
                    mostrarNotificacion('Error al cargar pendiente de caja', 'error');
                }
            },

            limpiarColaCobroDeUrl() {
                try {
                    const url = new URL(window.location.href);
                    if (!url.searchParams.has('cola_id')) return;
                    url.searchParams.delete('cola_id');
                    const nuevaUrl = `${url.pathname}${url.search}${url.hash}`;
                    window.history.replaceState({}, document.title, nuevaUrl);
                } catch (e) {
                }
            },

            // --- Persistencia de Estado ---

            guardarEstado() {
                // No guardar si estamos restaurando o si el carrito está vacío y no hay cambios
                const vendedorInicial = (typeof VENDEDOR_ID_INICIAL !== 'undefined' && VENDEDOR_ID_INICIAL !== null)
                    ? Number(VENDEDOR_ID_INICIAL)
                    : null;
                if (this.carrito.length === 0 && this.pagos.length === 0 && this.descuento === 0 && this.clienteId === 1 && this.alertaClienteFielActiva === true && (
                    this.vendedorId === vendedorInicial || !this.vendedorId
                ) && this.condicionVenta === 'contado') {
                    sessionStorage.removeItem(POS_STATE_KEY);
                    return;
                }

                const estado = {
                    carrito: this.carrito.map(item => ({
                        id_producto: item.id_producto,
                        cantidad: item.cantidad,
                        precio: item.precio,
                        precio_manual: item.precio_manual === true,
                        precio_opcion_id: item.precio_opcion_id || null
                    })),
                    clienteId: this.clienteId,
                    vendedorId: this.vendedorId,
                    alertaClienteFielActiva: this.alertaClienteFielActiva === true,
                    descuento: this.descuento,
                    condicionVenta: this.condicionVenta,
                    creditoModo: this.creditoModo,
                    pagos: this.pagos,
                    timestamp: Date.now()
                };

                try {
                    sessionStorage.setItem(POS_STATE_KEY, JSON.stringify(estado));
                } catch (e) {
                    console.warn('Error guardando estado del POS:', e);
                }
            },

            async restaurarEstado() {
                try {
                    const guardado = sessionStorage.getItem(POS_STATE_KEY);
                    if (!guardado) return;

                    const estado = JSON.parse(guardado);

                    // Verificar age del estado
                    if (Date.now() - estado.timestamp > POS_STATE_MAX_AGE_MS) {
                        sessionStorage.removeItem(POS_STATE_KEY);
                        return;
                    }

                    // Restaurar carrito validando con servidor
                    if (estado.carrito && estado.carrito.length > 0) {
                        await this.validarYRestaurarCarrito(estado.carrito);
                    }

                    // Restaurar cliente
                    if (estado.clienteId && estado.clienteId !== 1) {
                        this.clienteId = estado.clienteId;
                        // Buscar datos del cliente
                        const clienteEncontrado = this.clientesDefault.find(c => c.id_cliente == estado.clienteId);
                        if (clienteEncontrado) {
                            this.clienteSeleccionado = clienteEncontrado;
                        }
                    }

                    if (estado.vendedorId) {
                        const vendedorRecuperado = Number(estado.vendedorId);
                        if (this.vendedoresCajeros.some(v => Number(v.id_usuario) === vendedorRecuperado)) {
                            this.vendedorId = vendedorRecuperado;
                        }
                    }

                    if (typeof estado.alertaClienteFielActiva === 'boolean') {
                        this.alertaClienteFielActiva = estado.alertaClienteFielActiva;
                    }

                    // Restaurar descuento
                    if (estado.descuento) {
                        this.descuento = estado.descuento;
                    }

                    if (estado.condicionVenta === 'credito' && this.ventasCreditoActivo && this.creditoMetodoPagoId) {
                        this.condicionVenta = 'credito';
                    }
                    if (estado.creditoModo === 'cuenta_corriente') {
                        this.creditoModo = 'cuenta_corriente';
                    }

                    // Restaurar pagos
                    if (estado.pagos && estado.pagos.length > 0) {
                        this.pagos = estado.pagos;
                    }

                    await this.actualizarAlertaClienteFiel();
                    this.actualizarTotal();
                    this.estadoRestaurado = true;

                    if (this.carrito.length > 0) {
                        mostrarNotificacion('Venta en progreso restaurada', 'info');
                    }

                } catch (e) {
                    console.warn('Error restaurando estado del POS:', e);
                    sessionStorage.removeItem(POS_STATE_KEY);
                }
            },

            async validarYRestaurarCarrito(carritoGuardado) {
                const ids = carritoGuardado.map(item => item.id_producto);

                try {
                    const response = await fetch('/ventas/validar-carrito', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ids })
                    });

                    const data = await response.json();
                    const productosValidados = data.productos || {};

                    const carritoRestaurado = [];
                    const productosEliminados = [];

                    for (const itemGuardado of carritoGuardado) {
                        const validacion = productosValidados[String(itemGuardado.id_producto)];

                        if (validacion && validacion.existe) {
                            const esMayorista = this.usaPrecioMayorista();
                            let precioAplicar = (esMayorista && validacion.precio_mayorista)
                                ? validacion.precio_mayorista
                                : validacion.precio;
                            let precioManual = false;
                            let precioOpcionId = null;

                            if (itemGuardado.precio_opcion_id) {
                                const opciones = Array.isArray(validacion.precios_opciones) ? validacion.precios_opciones : [];
                                const encontrada = opciones.find(o => String(o.id) === String(itemGuardado.precio_opcion_id));
                                if (encontrada && encontrada.precio !== undefined && encontrada.precio !== null) {
                                    precioAplicar = parseFloat(encontrada.precio) || 0;
                                    precioManual = true;
                                    precioOpcionId = encontrada.id;
                                }
                            } else if (itemGuardado.precio_manual === true) {
                                const p = parseFloat(itemGuardado.precio);
                                if (!Number.isNaN(p) && p >= 0) {
                                    precioAplicar = p;
                                    precioManual = true;
                                }
                            }

                            const nuevoItem = {
                                id_producto: itemGuardado.id_producto,
                                codigo: validacion.codigo,
                                nombre: validacion.nombre,
                                precio: precioAplicar,
                                precio_base: validacion.precio,
                                precio_mayorista: validacion.precio_mayorista,
                                cantidad: itemGuardado.cantidad,
                                iva: validacion.iva,
                                precio_manual: precioManual,
                                precio_opcion_id: precioOpcionId,
                                stock_disponible: validacion.stock,
                                stock_minimo: validacion.stock_minimo,
                                stock_restante: null,
                                es_servicio: validacion.es_servicio,
                                stock_warning: false,
                                low_stock_warning: false,
                                green_stock_hint: false
                            };
                            this.validarStockItem(nuevoItem);
                            carritoRestaurado.push(nuevoItem);
                        } else {
                            productosEliminados.push(itemGuardado.id_producto);
                        }
                    }

                    this.carrito = carritoRestaurado;

                    if (productosEliminados.length > 0) {
                        mostrarNotificacion(`${productosEliminados.length} producto(s) ya no disponible(s) fueron removidos`, 'warning');
                    }

                } catch (e) {
                    console.warn('Error validando carrito con servidor:', e);
                }
            },

            limpiarEstadoGuardado() {
                sessionStorage.removeItem(POS_STATE_KEY);
            },

            cargarVentasPendientes() {
                try {
                    const raw = localStorage.getItem(PENDING_SALES_KEY);
                    if (!raw) {
                        this.ventasPendientes = [];
                        return;
                    }
                    const data = JSON.parse(raw);
                    if (!Array.isArray(data)) {
                        this.ventasPendientes = [];
                        return;
                    }
                    this.ventasPendientes = data.filter(v => v && v.client_request_id && v.payload && v.payload.items && v.payload.pagos);
                } catch (e) {
                    this.ventasPendientes = [];
                }
            },

            guardarVentasPendientes() {
                try {
                    localStorage.setItem(PENDING_SALES_KEY, JSON.stringify(this.ventasPendientes));
                } catch (e) {
                }
            },

            generarClientRequestId() {
                try {
                    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
                        return window.crypto.randomUUID();
                    }
                } catch (e) {
                }
                return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            },

            escapeHtml(value) {
                const s = String(value ?? '');
                return s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
            },

            generarTicketProvisionalHtml(ventaPendiente) {
                const payload = ventaPendiente.payload || {};
                const empresa = POS_EMPRESA || {};
                const items = Array.isArray(payload.items) ? payload.items : [];
                const pagos = Array.isArray(payload.pagos) ? payload.pagos : [];
                const subtotal = items.reduce((sum, it) => sum + ((parseFloat(it.precio) || 0) * (parseInt(it.cantidad) || 0)), 0);
                const descuento = parseFloat(payload.descuento) || 0;
                const total = Math.max(0, subtotal - descuento);
                const totalPagado = pagos.reduce((sum, p) => sum + (parseFloat(p.monto) || 0), 0);
                const vuelto = Math.max(0, totalPagado - total);
                const fecha = new Date(ventaPendiente.created_at || Date.now()).toLocaleString('es-PY');
                const moneda = '₲';

                const rows = items.map(it => {
                    const nombre = this.escapeHtml(it.nombre || '');
                    const codigo = this.escapeHtml(it.codigo || '');
                    const cant = parseInt(it.cantidad) || 0;
                    const precio = parseFloat(it.precio) || 0;
                    const lineTotal = precio * cant;
                    return `
                            <tr>
                                <td style="vertical-align: top;">
                                    <div>${nombre}</div>
                                    <div style="font-size: 11px; color:#444;">${codigo ? codigo + ' - ' : ''}${moneda} ${this.formatNumber(precio)}</div>
                                </td>
                                <td style="text-align:right; white-space:nowrap; vertical-align: top;">${cant}</td>
                                <td style="text-align:right; white-space:nowrap; vertical-align: top;">${moneda} ${this.formatNumber(lineTotal)}</td>
                            </tr>
                        `;
                }).join('');

                const pagosResumen = new Map();
                for (const p of pagos) {
                    const n = this.escapeHtml(p.nombre || 'Pago');
                    const m = parseFloat(p.monto) || 0;
                    const ref = String(p.referencia || '').trim();
                    const curr = pagosResumen.get(n) || { monto: 0, refs: new Set() };
                    curr.monto += m;
                    if (ref) curr.refs.add(this.escapeHtml(ref));
                    pagosResumen.set(n, curr);
                }
                const pagosRows = [...pagosResumen.entries()].map(([n, info]) => {
                    const refs = [...info.refs];
                    const refLine = refs.length ? `<div style="font-size: 11px; color:#444;">Ref: ${refs.join(', ')}</div>` : ``;
                    return `<div style="display:flex; justify-content: space-between; gap: 8px;"><span>${n}</span><span style="white-space:nowrap;">${moneda} ${this.formatNumber(info.monto)}</span></div>${refLine}`;
                }).join('');

                return `<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ticket Provisional</title>
  <style>
    @page { size: 58mm auto; margin: 0; }
    html, body { padding:0; margin:0; }
    body { font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #000; width: 58mm; max-width: 58mm; padding: 3mm; box-sizing: border-box; }
    .center { text-align: center; }
    .right { text-align: right; }
    .muted { color: #444; }
    .sep { border-top: 1px dashed #000; margin: 8px 0; }
    .h1 { font-size: 14px; font-weight: 700; margin: 0; }
    .small { font-size: 11px; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th, td { padding: 3px 0; vertical-align: top; }
    th { font-size: 11px; font-weight: 700; border-bottom: 1px solid #000; }
    div,span,td,th,p { word-break: normal; overflow-wrap: break-word; }
    .col-cant { width: 10mm; }
    .col-total { width: 16mm; }
  </style>
</head>
<body>
  <div class="center">
    ${empresa.nombre ? `<div class="h1">${this.escapeHtml(empresa.nombre)}</div>` : ``}
    ${empresa.ruc ? `<div class="small muted">RUC: ${this.escapeHtml(empresa.ruc)}</div>` : ``}
    ${empresa.telefono ? `<div class="small muted">Tel: ${this.escapeHtml(empresa.telefono)}</div>` : ``}
    ${empresa.direccion ? `<div class="small muted">${this.escapeHtml(empresa.direccion)}</div>` : ``}
  </div>
  <div class="sep"></div>
  <div class="center" style="font-weight:700;">TICKET PROVISIONAL</div>
  <div class="small muted center">Se sincroniza cuando vuelva la conexión</div>
  <div class="sep"></div>
  <div class="small">
    <div>Fecha: <span style="white-space:nowrap;">${this.escapeHtml(fecha)}</span></div>
    <div>Ref: <span style="white-space:nowrap;">${this.escapeHtml(ventaPendiente.client_request_id)}</span></div>
  </div>
  <div class="sep"></div>
  <table>
    <thead>
      <tr>
        <th>Prod</th>
        <th class="right col-cant" style="white-space:nowrap;">Cant</th>
        <th class="right col-total" style="white-space:nowrap;">Total</th>
      </tr>
    </thead>
    <tbody>
      ${rows}
    </tbody>
  </table>
  <div class="sep"></div>
  <table>
    <tbody>
      <tr><td>Subtotal</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(subtotal)}</td></tr>
      ${descuento > 0 ? `<tr><td>Descuento</td><td class="right" style="white-space:nowrap;">- ${moneda} ${this.formatNumber(descuento)}</td></tr>` : ``}
      <tr><td><strong>Total</strong></td><td class="right" style="white-space:nowrap;"><strong>${moneda} ${this.formatNumber(total)}</strong></td></tr>
    </tbody>
  </table>
  ${pagosRows ? `<div class="sep"></div><div class="small"><div class="muted" style="margin-bottom: 4px;">Detalle de pago</div>${pagosRows}</div>` : ``}
  <div class="sep"></div>
  <table>
    <tbody>
      <tr><td>Total pagado</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(totalPagado)}</td></tr>
      ${vuelto > 0 ? `<tr><td>Vuelto</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(vuelto)}</td></tr>` : ``}
    </tbody>
  </table>
  <div class="sep"></div>
  <div class="center small muted">Gracias por su compra</div>
</body>
</html>`;
            },
            guardarVentaPendiente(payload, clientRequestId) {
                const ventaPendiente = {
                    client_request_id: clientRequestId,
                    payload: payload,
                    created_at: Date.now()
                };
                ventaPendiente.ticket_html = this.generarTicketProvisionalHtml(ventaPendiente);
                this.ventasPendientes = [ventaPendiente, ...(this.ventasPendientes || [])];
                this.guardarVentasPendientes();
                this.ventaPendienteActual = ventaPendiente;
                this.offlineTicketHtml = ventaPendiente.ticket_html;
                this.mostrarModalVentaPendiente = true;
                this.limpiarVenta();
                mostrarNotificacion('Venta guardada para sincronizar', 'warning');
            },

            aceptarVentaPendiente() {
                this.mostrarModalVentaPendiente = false;
                this.ventaPendienteActual = null;
                this.offlineTicketHtml = '';
            },

            imprimirTicketProvisional() {
                const frame = this.$refs.ticketOfflineFrame;
                try {
                    if (frame && frame.contentWindow) {
                        const w = frame.contentWindow;
                        const onAfter = () => this.enfocarBusqueda();
                        try {
                            w.addEventListener('afterprint', onAfter, { once: true });
                        } catch (e) {
                        }
                        w.focus();
                        w.print();
                        setTimeout(() => this.enfocarBusqueda(), 600);
                    }
                } catch (e) {
                }
            },

            async sincronizarVentasPendientes() {
                if (!this.isOnline) return;
                if (!this.ventasPendientes || this.ventasPendientes.length === 0) return;

                const pendientes = [...this.ventasPendientes];
                for (const venta of pendientes) {
                    const payload = venta.payload || {};
                    payload.client_request_id = venta.client_request_id;
                    try {
                        const response = await fetch('/ventas/procesar', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        const data = await response.json();
                        if (response.ok && data && data.success) {
                            this.ventasPendientes = (this.ventasPendientes || []).filter(v => v.client_request_id !== venta.client_request_id);
                            this.guardarVentasPendientes();
                            if (data.id_venta) {
                                mostrarNotificacion(`Venta sincronizada: #${data.id_venta}`, 'success');
                            } else {
                                mostrarNotificacion('Venta sincronizada', 'success');
                            }
                            try {
                                window.dispatchEvent(new CustomEvent('dashboard:refresh-totals'));
                                if (window.dashboardRefreshTotals) window.dashboardRefreshTotals();
                            } catch (e) {
                            }
                            continue;
                        }
                        if (response.status === 403 && (data.error || '').includes('Se requiere autorización')) {
                            mostrarNotificacion('Sincronización pendiente: requiere autorización', 'warning');
                            return;
                        }
                        mostrarNotificacion('No se pudo sincronizar una venta pendiente', 'error');
                        return;
                    } catch (e) {
                        return;
                    }
                }
            },

            // --- Lógica de Clientes ---

            async buscarClientes(query, esInicial = false) {
                try {
                    const response = await fetch(`/clientes/buscar_json?q=${encodeURIComponent(query)}`);
                    const data = await response.json();

                    if (esInicial) {
                        // Buscar ID 1 para setearlo
                        const defaultCliente = data.items.find(c => c.id_cliente == 1);
                        if (defaultCliente) {
                            this.clienteSeleccionado = defaultCliente;
                            this.clienteId = defaultCliente.id_cliente;
                            this.actualizarAlertaClienteFiel(defaultCliente);
                        }
                        // Guardar lista inicial para mostrar cuando no hay busqueda
                        this.clientesDefault = data.items;
                        this.clientesEncontrados = data.items;
                    } else {
                        this.clientesEncontrados = data.items;
                    }

                    // Si el query está vacío, mostrar los default
                    if (!query && !esInicial) {
                        this.clientesEncontrados = this.clientesDefault;
                    }

                } catch (e) {
                    console.error('Error buscando clientes:', e);
                }
            },

            seleccionarCliente(cliente) {
                const usabaMayorista = this.usaPrecioMayorista();
                this.clienteSeleccionado = cliente;
                this.clienteId = cliente.id_cliente;
                this.actualizarAlertaClienteFiel(cliente);

                // Si cambia el estado de mayorista (y no hay toggle manual), actualizar precios
                if (!this.forzarPrecioMayorista && usabaMayorista !== this.usaPrecioMayorista() && this.carrito.length > 0) {
                    this.actualizarPreciosSegunCliente();
                }
            },

            limpiarAlertaClienteFiel() {
                this.clienteFielResumen = {
                    clienteId: null,
                    cantidadCompras: 0,
                    cargando: false,
                    error: '',
                    urlHistorial: ''
                };
            },

            toggleAlertaClienteFiel() {
                this.alertaClienteFielActiva = !this.alertaClienteFielActiva;

                if (!this.alertaClienteFielActiva) {
                    this.limpiarAlertaClienteFiel();
                    return;
                }

                this.actualizarAlertaClienteFiel();
            },

            async actualizarAlertaClienteFiel(cliente = null) {
                const clienteActual = cliente || this.clienteSeleccionado;
                const clienteId = Number(clienteActual && clienteActual.id_cliente ? clienteActual.id_cliente : 0);

                if (!this.alertaClienteFielActiva || !clienteId || clienteId === 1) {
                    this.limpiarAlertaClienteFiel();
                    return;
                }

                const cache = this.clienteFielCache[clienteId];
                if (cache) {
                    this.clienteFielResumen = { ...cache, cargando: false, error: '' };
                    return;
                }

                this.clienteFielResumen = {
                    clienteId,
                    cantidadCompras: 0,
                    cargando: true,
                    error: '',
                    urlHistorial: ''
                };

                try {
                    const response = await fetch(`/clientes/${clienteId}/historial_json`);
                    const data = await response.json();

                    if (!response.ok || !data.success) {
                        throw new Error(data.error || 'No se pudo cargar el historial');
                    }

                    const resumen = {
                        clienteId,
                        cantidadCompras: Number((data.estadisticas && data.estadisticas.cantidad_compras) || 0),
                        urlHistorial: (data.cliente && data.cliente.url_historial) || ''
                    };

                    this.clienteFielCache[clienteId] = resumen;

                    if (this.clienteSeleccionado && Number(this.clienteSeleccionado.id_cliente) === clienteId) {
                        this.clienteFielResumen = { ...resumen, cargando: false, error: '' };
                    }
                } catch (e) {
                    if (this.clienteSeleccionado && Number(this.clienteSeleccionado.id_cliente) === clienteId) {
                        this.clienteFielResumen = {
                            clienteId,
                            cantidadCompras: 0,
                            cargando: false,
                            error: e.message || 'No se pudo cargar el historial',
                            urlHistorial: ''
                        };
                    }
                }
            },

            esClienteMayorista(cliente = null) {
                const clienteActual = cliente || this.clienteSeleccionado;
                const tipoCliente = String((clienteActual && clienteActual.tipo) || '').trim().toLowerCase();
                return tipoCliente === 'mayorista' || tipoCliente === 'empresa';
            },

            usaPrecioMayorista() {
                if (this.forzarPrecioMayorista) return true;
                if (this.bloquearPrecioMayorista) return false;
                return this.esClienteMayorista();
            },

            estadoPrecioMayoristaTexto() {
                if (this.usaPrecioMayorista()) {
                    return this.forzarPrecioMayorista ? 'Activado manualmente' : 'Automático por cliente';
                }

                if (this.esClienteMayorista() && this.bloquearPrecioMayorista) {
                    return 'Desactivado manualmente';
                }

                return 'Click para activar';
            },

            alertaPrecioMayoristaTexto() {
                if (!this.esClienteMayorista()) return '';
                if (this.bloquearPrecioMayorista) return 'Cliente mayorista detectado, pero el precio mayorista quedó desactivado manualmente.';
                return 'Cliente mayorista detectado. Se aplican precios mayoristas automáticamente.';
            },

            togglePrecioMayorista() {
                const estabaActivo = this.usaPrecioMayorista();
                const esClienteMayorista = this.esClienteMayorista();

                if (estabaActivo) {
                    this.forzarPrecioMayorista = false;
                    this.bloquearPrecioMayorista = esClienteMayorista;
                } else {
                    this.forzarPrecioMayorista = !esClienteMayorista;
                    this.bloquearPrecioMayorista = false;
                }

                const precioMayoristaActivo = this.usaPrecioMayorista();
                const estadoTexto = precioMayoristaActivo ? 'ACTIVADO' : 'DESACTIVADO';
                mostrarNotificacion(`Precio Mayorista ${estadoTexto}`, precioMayoristaActivo ? 'success' : 'info');

                if (this.carrito.length > 0) {
                    this.actualizarPreciosSegunCliente();
                }
            },

            // Actualizar precios del carrito según tipo de cliente o toggle
            actualizarPreciosSegunCliente() {
                const esMayorista = this.usaPrecioMayorista();

                let productosActualizados = 0;
                let productosSinPrecioMayorista = 0;

                for (const item of this.carrito) {
                    if (item.precio_manual === true || item.precio_opcion_id) continue;
                    const precioAnterior = item.precio;

                    if (esMayorista) {
                        // Intentar aplicar precio mayorista
                        if (item.precio_mayorista && item.precio_mayorista > 0) {
                            item.precio = item.precio_mayorista;
                        } else {
                            // No tiene precio mayorista, mantener precio base
                            productosSinPrecioMayorista++;
                        }
                    } else {
                        // Volver a precio base (minorista)
                        if (item.precio_base && item.precio_base > 0) {
                            item.precio = item.precio_base;
                        }
                    }

                    if (item.precio !== precioAnterior) {
                        productosActualizados++;
                    }
                }

                this.actualizarTotal();

                if (productosActualizados > 0) {
                    const tipoMensaje = esMayorista ? 'Precios mayoristas aplicados' : 'Precios minoristas aplicados';
                    mostrarNotificacion(`${tipoMensaje} a ${productosActualizados} producto(s)`, 'info');
                }

                if (esMayorista && productosSinPrecioMayorista > 0) {
                    mostrarNotificacion(`${productosSinPrecioMayorista} producto(s) no tienen precio mayorista definido`, 'warning');
                }
            },

            // --- CRM Historial ---
            async verHistorialCliente() {
                if (!this.clienteSeleccionado) return;

                mostrarNotificacion('Cargando historial...', 'info');

                console.log('Fetching history for client:', this.clienteSeleccionado.id_cliente);
                this.mostrarModalHistorial = true;
                this.historialCargando = true;

                try {
                    const response = await fetch(`/clientes/${this.clienteSeleccionado.id_cliente}/historial_json`);
                    console.log('History response status:', response.status);

                    if (!response.ok) throw new Error('Network response was not ok');

                    const data = await response.json();
                    console.log('History data:', data);

                    if (data.success) {
                        this.historialDatos = data;
                    } else {
                        mostrarNotificacion('Error cargando historial: ' + data.error, 'error');
                        this.mostrarModalHistorial = false;
                    }
                } catch (e) {
                    console.error('Error fetching history:', e);
                    mostrarNotificacion('Error de conexión al cargar historial', 'error');
                    this.mostrarModalHistorial = false;
                } finally {
                    this.historialCargando = false;
                }
            },


            // Modal Nuevo Cliente

            // Modal Nuevo Cliente
            mostrarModalCliente: false,
            modoEdicion: false,
            nuevoCliente: {
                id_cliente: null,
                nombre: '',
                ruc_ci: '',
                telefono: '',
                direccion: '',
                email: '',
                tipo: 'minorista',
                limite_credito: 0
            },

            abrirModalCliente() {
                this.modoEdicion = false;
                this.nuevoCliente = { id_cliente: null, nombre: '', ruc_ci: '', telefono: '', direccion: '', email: '', tipo: 'minorista', limite_credito: 0 }; // Reset
                this.mostrarModalCliente = true;
            },

            editarCliente() {
                if (!this.clienteSeleccionado) return;
                this.modoEdicion = true;
                const c = this.clienteSeleccionado;
                this.nuevoCliente = {
                    id_cliente: c.id_cliente,
                    nombre: c.nombre,
                    ruc_ci: c.ruc_ci || '',
                    telefono: c.telefono || '',
                    direccion: c.direccion || '',
                    email: c.email || '',
                    tipo: c.tipo || 'minorista',
                    limite_credito: c.limite_credito || 0
                };
                this.mostrarModalCliente = true;
            },

            cerrarModalCliente() {
                this.mostrarModalCliente = false;
            },

            async guardarCliente() {
                if (!this.nuevoCliente.nombre) return;

                const url = this.modoEdicion
                    ? `/clientes/editar_json/${this.nuevoCliente.id_cliente}`
                    : '/clientes/crear_json';

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.nuevoCliente)
                    });

                    const data = await response.json();

                    if (data.success) {
                        // Seleccionar el nuevo cliente
                        this.seleccionarCliente(data.cliente);
                        this.cerrarModalCliente();
                        // Refrescar lista default por si acaso (opcional)
                        mostrarNotificacion(this.modoEdicion ? 'Cliente actualizado correctamente' : 'Cliente creado correctamente', 'success');
                    } else {
                        mostrarNotificacion('Error: ' + data.error, 'error');
                    }
                } catch (e) {
                    mostrarNotificacion('Error de conexión al crear cliente', 'error');
                }
            },

            async buscarProductos() {
                if (this.busqueda.length < 2) {
                    this.resultados = [];
                    return;
                }

                const response = await fetch(`/productos/buscar?q=${encodeURIComponent(this.busqueda)}`);
                this.resultados = await response.json();
            },

            abrirModalPrecioOpciones(producto) {
                this.productoPrecioOpciones = producto || null;
                const opts = (producto && Array.isArray(producto.precios_opciones)) ? producto.precios_opciones : [];
                this.preciosOpcionesActuales = [...opts].sort((a, b) => (parseFloat(a.precio) || 0) - (parseFloat(b.precio) || 0));
                this.mostrarModalPrecioOpciones = true;
            },

            cerrarModalPrecioOpciones() {
                this.mostrarModalPrecioOpciones = false;
                this.productoPrecioOpciones = null;
                this.preciosOpcionesActuales = [];
                this.enfocarBusqueda();
            },

            confirmarPrecioOpcion(opcion) {
                const producto = this.productoPrecioOpciones;
                if (!producto || !opcion) return;
                this.mostrarModalPrecioOpciones = false;
                this.agregarProductoConPrecioOpcion(producto, opcion);
                this.productoPrecioOpciones = null;
                this.preciosOpcionesActuales = [];
            },

            agregarProductoConPrecioOpcion(producto, opcion) {
                const precio = parseFloat(opcion.precio) || 0;
                const precioOpcionId = opcion.id || null;
                const existente = this.carrito.find(item => item.id_producto === producto.id && String(item.precio_opcion_id || '') === String(precioOpcionId || ''));

                if (existente) {
                    existente.cantidad++;
                    this.validarStockItem(existente);
                } else {
                    const nuevoItem = {
                        id_producto: producto.id,
                        codigo: producto.codigo,
                        nombre: producto.nombre,
                        precio: precio,
                        precio_base: producto.precio,
                        precio_mayorista: producto.precio_mayorista,
                        cantidad: 1,
                        iva: producto.iva,
                        precio_manual: true,
                        precio_opcion_id: precioOpcionId,
                        stock_disponible: producto.stock,
                        stock_minimo: producto.stock_minimo,
                        stock_restante: null,
                        es_servicio: producto.es_servicio,
                        stock_warning: false,
                        low_stock_warning: false,
                        green_stock_hint: false
                    };
                    this.validarStockItem(nuevoItem);
                    this.carrito.push(nuevoItem);
                }

                this.busqueda = '';
                this.resultados = [];
                this.actualizarTotal();
                this.enfocarBusqueda();
            },

            agregarProducto(producto) {
                if (producto && producto.precios_opciones && producto.precios_opciones.length > 0) {
                    this.abrirModalPrecioOpciones(producto);
                    return;
                }

                const existente = this.carrito.find(item => item.id_producto === producto.id && !item.precio_opcion_id);

                // Determinar precio según toggle o tipo de cliente
                const esMayorista = this.usaPrecioMayorista();
                const precioAplicar = (esMayorista && producto.precio_mayorista)
                    ? producto.precio_mayorista
                    : producto.precio;

                if (existente) {
                    existente.cantidad++;
                    this.validarStockItem(existente);
                } else {
                    const nuevoItem = {
                        id_producto: producto.id,
                        codigo: producto.codigo,
                        nombre: producto.nombre,
                        precio: precioAplicar,
                        precio_base: producto.precio,
                        precio_mayorista: producto.precio_mayorista,
                        cantidad: 1,
                        iva: producto.iva,
                        stock_disponible: producto.stock,
                        stock_minimo: producto.stock_minimo,
                        stock_restante: null,
                        es_servicio: producto.es_servicio,
                        precio_manual: false,
                        precio_opcion_id: null,
                        stock_warning: false,
                        low_stock_warning: false,
                        green_stock_hint: false
                    };
                    this.validarStockItem(nuevoItem);
                    this.carrito.push(nuevoItem);
                }

                this.busqueda = '';
                this.resultados = [];
                this.actualizarTotal();
                this.enfocarBusqueda();
            },

            async agregarPorEnter() {
                const q = (this.busqueda || '').trim();
                if (!q) return;

                try {
                    const response = await fetch(`/productos/buscar_exacto?q=${encodeURIComponent(q)}`);
                    if (response.ok) {
                        const producto = await response.json();
                        if (producto && producto.id) {
                            this.agregarProducto(producto);
                            return;
                        }
                    }
                } catch (e) { }

                await this.buscarProductos();
                this.agregarPrimero();
            },

            agregarPrimero() {
                if (this.resultados.length > 0) {
                    this.agregarProducto(this.resultados[0]);
                }
            },

            eliminarItem(index) {
                const rid = this.reparacionId;
                this.carrito.splice(index, 1);
                this.actualizarTotal();
                if (rid && this.carrito.length === 0) {
                    sessionStorage.setItem(`pos_reparacion_skip_${rid}`, '1');
                    sessionStorage.setItem(`pos_reparacion_skip_token_${rid}`, this.reparacionToken || '');
                    this.reparacionId = null;
                }
            },

            actualizarTotal() {
                this.subtotal = this.carrito.reduce((sum, item) => {
                    const precio = parseFloat(item.precio) || 0;
                    const cantidad = parseInt(item.cantidad) || 0;
                    return sum + (precio * cantidad);
                }, 0);
                const descuento = parseFloat(this.descuento) || 0;
                this.total = Math.max(0, (parseFloat(this.subtotal) || 0) - descuento);
                this.normalizarPagosAlCambiarTotal();
                this.sincronizarPagoCredito();
                this.calcularSaldoPendiente();
            },

            normalizarPagosAlCambiarTotal() {
                const total = parseFloat(this.total) || 0;
                if (!Array.isArray(this.pagos)) this.pagos = [];

                if (this.carrito.length === 0 || total <= 0) {
                    if (this.pagos.length > 0) this.pagos = [];
                    return;
                }

                const redondear = (v) => Math.max(0, Math.round(parseFloat(v) || 0));
                const pagos = this.pagos.map(p => ({ ...(p || {}) }));
                let totalManual = 0;
                const autoIndices = [];

                for (let i = 0; i < pagos.length; i++) {
                    const pago = pagos[i] || {};
                    pago.monto = redondear(pago.monto);
                    if (pago.auto === true) {
                        autoIndices.push(i);
                    } else {
                        totalManual += pago.monto;
                    }
                    pagos[i] = pago;
                }

                const restante = Math.max(0, total - totalManual);

                if (autoIndices.length > 0) {
                    const totalAutoActual = autoIndices.reduce((s, idx) => s + (redondear(pagos[idx].monto)), 0);

                    if (totalAutoActual > 0) {
                        const factor = restante / totalAutoActual;
                        let asignado = 0;
                        for (let k = 0; k < autoIndices.length; k++) {
                            const idx = autoIndices[k];
                            if (k === autoIndices.length - 1) {
                                pagos[idx].monto = redondear(restante - asignado);
                            } else {
                                const nuevo = redondear(pagos[idx].monto * factor);
                                pagos[idx].monto = nuevo;
                                asignado += nuevo;
                            }
                        }
                    } else {
                        for (const idx of autoIndices) pagos[idx].monto = 0;
                        pagos[autoIndices[0]].monto = redondear(restante);
                    }
                }

                this.pagos = pagos.filter(p => (redondear(p.monto) > 0));
            },

            ventasCreditoDisponible() {
                return !!(this.ventasCreditoActivo && this.creditoMetodoPagoId && !this.soloRegistroVendedor && !this.debeEnviarACajaAntesDeCobrar());
            },

            esVentaCredito() {
                return this.ventasCreditoDisponible() && this.condicionVenta === 'credito';
            },

            seleccionarCondicionVenta(condicion) {
                if (condicion === 'credito') {
                    if (!this.ventasCreditoDisponible()) {
                        mostrarNotificacion('La venta a credito no esta disponible en este flujo.', 'warning');
                        return;
                    }
                    if (this.reparacionId || this.colaCobroId) {
                        mostrarNotificacion('El credito simple desde POS no esta habilitado todavia para reparaciones o pendientes de caja.', 'warning');
                        return;
                    }
                    this.condicionVenta = 'credito';
                    this.creditoModo = 'cuotas';
                    this.asegurarFechaPrimerVencimientoCredito();
                } else {
                    this.condicionVenta = 'contado';
                }
                this.sincronizarPagoCredito();
                this.calcularSaldoPendiente();
            },

            seleccionarModoCredito(modo) {
                if (modo !== 'cuenta_corriente' && modo !== 'cuotas') {
                    return;
                }
                this.creditoModo = modo;
                if (modo === 'cuotas') {
                    this.asegurarFechaPrimerVencimientoCredito();
                }
                this.sincronizarPagoCredito();
                this.calcularSaldoPendiente();
            },

            _esPagoCredito(pago) {
                return !!(pago && this.creditoMetodoPagoId && parseInt(pago.id_metodo_pago) === parseInt(this.creditoMetodoPagoId));
            },

            _pagosSinCredito() {
                return (this.pagos || []).filter(pago => !this._esPagoCredito(pago));
            },

            montoAnticipoActual() {
                return this._pagosSinCredito().reduce((sum, pago) => sum + (parseFloat(pago.monto) || 0), 0);
            },

            montoFinanciadoActual() {
                if (!this.esVentaCredito()) return 0;
                const total = parseFloat(this.total) || 0;
                return Math.max(0, total - this.montoAnticipoActual());
            },

            creditoRequiereClienteFormal() {
                return this.esVentaCredito() && Number(this.clienteId || 0) <= 1;
            },

            puedeAgregarPagoManual() {
                return (parseFloat(this.total) || 0) > 0;
            },

            sincronizarPagoCredito() {
                if (!Array.isArray(this.pagos)) this.pagos = [];
                const pagosSinCredito = this._pagosSinCredito().map(pago => ({ ...(pago || {}), es_credito: false }));

                if (!this.esVentaCredito()) {
                    this.pagos = pagosSinCredito;
                    return;
                }

                const montoFinanciado = this.montoFinanciadoActual();
                this.pagos = pagosSinCredito;
                if (montoFinanciado <= 0.0001) {
                    return;
                }

                this.pagos.push({
                    id_metodo_pago: this.creditoMetodoPagoId,
                    nombre: this.creditoMetodoPagoNombre,
                    monto: Math.round(montoFinanciado),
                    auto: true,
                    es_credito: true,
                });
            },

            puedeConfirmarVentaActual() {
                if (this.requiereSeleccionVendedor() && !this.vendedorId) return false;
                if (this.esVentaCredito()) {
                    return !this.creditoRequiereClienteFormal() && this.montoFinanciadoActual() > 0.0001;
                }
                return (parseFloat(this.saldoPendiente) || 0) <= 0.0001;
            },

            validarVentaCreditoAntesDeProcesar() {
                if (!this.esVentaCredito()) return true;
                if (this.creditoRequiereClienteFormal()) {
                    mostrarNotificacion('Selecciona un cliente real antes de registrar una venta a credito.', 'warning');
                    return false;
                }
                if (this.montoFinanciadoActual() <= 0.0001) {
                    mostrarNotificacion('No queda saldo para financiar. Si el cliente paga todo ahora, usa contado.', 'warning');
                    return false;
                }
                if (!this.validarCreditoCuotasAntesDeProcesar()) {
                    return false;
                }
                return true;
            },

            // Validar stock de un item individual
            validarStockItem(item) {
                if (item.es_servicio) {
                    item.stock_warning = false;
                    item.low_stock_warning = false;
                    item.green_stock_hint = false;
                    item.stock_restante = null;
                    return;
                }

                const stockDisponible = parseInt(item.stock_disponible) || 0;
                const cantidad = parseInt(item.cantidad) || 0;
                const stockMinimo = (item.stock_minimo !== undefined && item.stock_minimo !== null) ? (parseInt(item.stock_minimo) || 0) : null;

                const stockLuego = stockDisponible - cantidad;
                item.stock_restante = stockLuego;

                if (stockDisponible <= 0 || cantidad > stockDisponible || stockLuego <= 0) {
                    item.stock_warning = true;
                } else {
                    item.stock_warning = false;
                }

                if (!item.stock_warning && stockMinimo !== null) {
                    item.low_stock_warning = stockLuego <= stockMinimo;
                } else {
                    item.low_stock_warning = false;
                }

                if (!item.stock_warning && !item.low_stock_warning && stockMinimo !== null) {
                    item.green_stock_hint = stockLuego > stockMinimo;
                } else {
                    item.green_stock_hint = false;
                }
            },

            // Verificar si hay warnings de stock en el carrito
            verificarStockWarnings() {
                return this.carrito.filter(item => item.stock_warning);
            },

            // Funciones de pagos múltiples
            agregarPago(id, nombre) {
                if (this.creditoMetodoPagoId && parseInt(id) === parseInt(this.creditoMetodoPagoId)) {
                    return;
                }
                const existente = (this.pagos || []).find(
                    pago => !this._esPagoCredito(pago) && parseInt(pago.id_metodo_pago) === parseInt(id)
                );
                if (existente) {
                    existente.auto = false;
                } else {
                    this.pagos.push({
                        id_metodo_pago: id,
                        nombre: nombre,
                        monto: this.esVentaCredito() ? 0 : (this.saldoPendiente > 0 ? this.saldoPendiente : 0),
                        auto: !this.esVentaCredito(),
                        es_credito: false,
                    });
                }
                this.calcularSaldoPendiente();
            },

            eliminarPago(index) {
                if (this.pagos[index] && this.pagos[index].es_credito) {
                    return;
                }
                this.pagos.splice(index, 1);
                this.calcularSaldoPendiente();
            },

            pagarTodoEfectivo() {
                this.pagos = [{
                    id_metodo_pago: 1,
                    nombre: "Efectivo",
                    monto: this.total,
                    auto: true
                }];
                this.calcularSaldoPendiente();
            },

    calcularSaldoPendiente() {
        this.sincronizarPagoCredito();
        this.totalPagado = this.pagos.reduce((sum, pago) => sum + (parseFloat(pago.monto) || 0), 0);
        const tolerancia = 0.0001;
        const saldo = (parseFloat(this.total) || 0) - this.totalPagado;
        const vuelto = this.totalPagado - (parseFloat(this.total) || 0);
        this.saldoPendiente = saldo > tolerancia ? saldo : 0;
        this.vuelto = vuelto > tolerancia ? vuelto : 0;
    },

    _efectivoPagado() {
        const efectivoId = 1;
    return this.pagos.reduce((sum, pago) => {
        try {
            if (parseInt(pago.id_metodo_pago) === efectivoId) {
                return sum + (parseFloat(pago.monto) || 0);
            }
        } catch (e) { }
        return sum;
    }, 0);
            },

    _validarVueltoAntesDeProcesar() {
        const tolerancia = 0.0001;
        const vuelto = parseFloat(this.vuelto) || 0;
        if (vuelto <= tolerancia) return true;
        const efectivoPagado = this._efectivoPagado();
        if (efectivoPagado <= tolerancia) {
            mostrarNotificacion('El vuelto solo es válido con pago en efectivo.', 'warning');
            return false;
        }
        if ((efectivoPagado + tolerancia) < vuelto) {
            mostrarNotificacion('El vuelto supera el efectivo recibido.', 'warning');
            return false;
        }
        return true;
    },

    _validarVendedorSeleccionado() {
        if (this.ocultarSelectorVendedorPos) {
            return true;
        }
        const vid = Number(this.vendedorId || 0);
        if (!vid) {
            mostrarNotificacion('Seleccione vendedor/cajero antes de procesar la venta.', 'warning');
            return false;
        }
        const existe = this.vendedoresCajeros.some(v => Number(v.id_usuario) === vid);
        if (!existe) {
            mostrarNotificacion('El vendedor/cajero seleccionado no es válido.', 'error');
            return false;
        }
        return true;
    },

    requiereSeleccionVendedor() {
        return !this.ocultarSelectorVendedorPos;
    },

    debeEnviarACajaAntesDeCobrar() {
        return !!(this.cajaFlujoEnviadoActivo && this.cajaExigirCajeroParaCobro && !this.puedeCobrarPosDirecto);
    },

    async enviarVentaACaja() {
        if (this.enviandoCaja || this.procesando) return;
        if (this.carrito.length === 0) return;
        if (!this.cajaFlujoEnviadoActivo) {
            mostrarNotificacion('El flujo de envío a caja está desactivado en configuración.', 'warning');
            return;
        }
        if (!this.puedeEnviarCajaVenta) {
            mostrarNotificacion('No tenés permisos para enviar ventas a caja.', 'error');
            return;
        }
        if (this.reparacionId) {
            mostrarNotificacion('Para reparaciones, usá "Enviar a caja" desde el detalle de reparación.', 'warning');
            return;
        }
        if (!this.isOnline) {
            mostrarNotificacion('Se requiere conexión para enviar la venta a caja.', 'warning');
            return;
        }
        if (!this._validarVendedorSeleccionado()) return;

        this.enviandoCaja = true;
        try {
            const payload = {
                items: this.carrito.map(it => ({
                    id_producto: it.id_producto,
                    cantidad: it.cantidad,
                    precio: it.precio,
                    precio_manual: it.precio_manual === true,
                    precio_opcion_id: it.precio_opcion_id || null,
                    nombre: it.nombre,
                    codigo: it.codigo
                })),
                id_cliente: this.clienteId,
                id_usuario_vendedor: this.vendedorId,
                forzar_precio_mayorista: this.forzarPrecioMayorista === true,
                descuento: this.descuento,
                client_request_id: this.generarClientRequestId(),
            };

            const response = await fetch('/ventas/enviar-a-caja', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json().catch(() => ({}));

            if (!response.ok || !data || !data.success) {
                mostrarNotificacion((data && data.error) ? data.error : 'No se pudo enviar la venta a caja', 'error');
                return;
            }

            this.mostrarModalVistaPrevia = false;
            this.ticketPreviewHtml = '';
            mostrarNotificacion(data.mensaje || 'Venta enviada a caja correctamente', 'success');
            this.limpiarVenta();
            this.enfocarBusqueda();
        } catch (e) {
            mostrarNotificacion('Error de conexión al enviar la venta a caja', 'error');
        } finally {
            this.enviandoCaja = false;
        }
    },

            async procesarVenta() {
        if (this.procesando || this.enviandoCaja) return;
        if (this.carrito.length === 0) return;
        if (!this._validarVendedorSeleccionado()) return;
        if (this.debeEnviarACajaAntesDeCobrar()) {
            if (this.puedeEnviarCajaVenta) {
                mostrarNotificacion('El cobro final debe realizarse en caja. Use "Enviar a Caja".', 'warning');
            } else {
                mostrarNotificacion('El cobro final debe realizarse en caja y tu usuario no tiene permiso para enviar pendientes.', 'error');
            }
            return;
        }
        if (!this.validarVentaCreditoAntesDeProcesar()) return;
        if (this.saldoPendiente > 0) {
            mostrarNotificacion('Aún falta pagar ₲ ' + this.formatNumber(this.saldoPendiente), 'warning');
            return;
        }
        if (!this._validarVueltoAntesDeProcesar()) return;

        // Verificar si hay warnings de stock
        const itemsConProblemas = this.verificarStockWarnings();
        if (itemsConProblemas.length > 0) {
            this.itemsConWarning = itemsConProblemas;
            this.mostrarModalStock = true;
            return;
        }

        // Mostrar vista previa en lugar de procesar directamente
        this.mostrarVistaPrevia();
    },

            async confirmarVenta() {
        // Después del modal de stock, mostrar vista previa
        this.mostrarModalStock = false;
        this.mostrarVistaPrevia();
    },

    mostrarVistaPrevia() {
        // Generar el HTML del ticket para vista previa
        this.ticketPreviewHtml = this.generarTicketPreviewHtml();
        this.mostrarModalVistaPrevia = true;
    },

    cancelarVistaPrevia() {
        this.mostrarModalVistaPrevia = false;
        this.ticketPreviewHtml = '';
    },

            async confirmarYProcesarVenta() {
        if (this.confirmandoVenta || this.procesando) return;
        this.confirmandoVenta = true;
        try {
            await this.ejecutarVenta();
        } finally {
            this.confirmandoVenta = false;
        }
    },

    construirPayloadVenta(requestId, idAutorizacion = null) {
        const payload = {
            items: this.carrito.map(it => ({
                id_producto: it.id_producto,
                cantidad: it.cantidad,
                precio: it.precio,
                precio_manual: it.precio_manual === true,
                precio_opcion_id: it.precio_opcion_id || null,
                nombre: it.nombre,
                codigo: it.codigo
            })),
            pagos: this.pagos,
            id_cliente: this.clienteId,
            id_usuario_vendedor: this.vendedorId,
            forzar_precio_mayorista: this.forzarPrecioMayorista === true,
            descuento: this.descuento,
            condicion_venta: this.condicionVenta,
            credito_modo: this.esVentaCredito() ? this.creditoModo : null,
            credito_plan: this.creditoPlanPayload(),
            client_request_id: requestId
        };
        if (idAutorizacion) payload.id_autorizacion = idAutorizacion;
        if (this.reparacionId) payload.reparacion_id = this.reparacionId;
        if (this.colaCobroId) payload.cola_cobro_id = this.colaCobroId;
        if (this.colaCobroId) payload.debug_perf = true;
        return payload;
    },

            async ejecutarVenta(idAutorizacion = null, clientRequestId = null) {
        if (this.procesando) return;
        this.procesando = true;

        try {
            if (!this._validarVendedorSeleccionado()) {
                this.procesando = false;
                return;
            }
            if (!this._validarVueltoAntesDeProcesar()) {
                this.procesando = false;
                return;
            }
            const requestId = clientRequestId || this.generarClientRequestId();
            const payload = this.construirPayloadVenta(requestId, idAutorizacion);

            if (!this.isOnline) {
                this.procesando = false;
                this.guardarVentaPendiente(payload, requestId);
                return;
            }

            const t0 = (window.performance && typeof window.performance.now === 'function')
                ? window.performance.now()
                : Date.now();
            const response = await fetch('/ventas/procesar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            const t1 = (window.performance && typeof window.performance.now === 'function')
                ? window.performance.now()
                : Date.now();
            if (data && data.perf && window.console && typeof window.console.info === 'function') {
                window.console.info('[POS] ventas/procesar', {
                    request_id: requestId,
                    network_ms: Math.round(t1 - t0),
                    backend: data.perf
                });
            }

            if (!response.ok && response.status === 403 && !idAutorizacion && (data.error || '').includes('Se requiere autorización')) {
                this.procesando = false;
                const codigoPermiso = data.codigo_permiso || 'vender_sin_stock';
                const accion = (codigoPermiso === 'venta_credito')
                    ? 'Venta a crédito en POS'
                    : 'Vender sin stock en POS';
                await ejecutarConAutorizacion(
                    codigoPermiso,
                    accion,
                    async (idAutorizacionReintento) => {
                        if (!idAutorizacionReintento) {
                            mostrarNotificacion('No se pudo obtener autorización', 'error');
                            return;
                        }
                        await this.ejecutarVenta(idAutorizacionReintento, requestId);
                    },
                    'venta',
                    null
                );
                return;
            }

            if (data.success) {
                // Cerrar modal de vista previa
                this.mostrarModalVistaPrevia = false;
                this.ticketPreviewHtml = '';

                // Guardar última venta para reimpresión
                const idVenta = data.id_venta;
                const cerrarPosAlFinalizar = !this.soloRegistroVendedor && !!this.colaCobroId;
                let impresionOk = true;
                if (idVenta) {
                    this.guardarUltimaVenta(idVenta);

                    impresionOk = await this.imprimirTicketVenta(idVenta);
                    if (!impresionOk) {
                        mostrarNotificacion('Venta #' + idVenta + ' registrada. No se pudo abrir la impresión, use "Reimprimir Último Ticket"', 'warning');
                    }
                }

                // Mostrar resumen de venta
                let mensaje = `Venta #${idVenta} registrada correctamente`;
                if (this.vuelto > 0) {
                    mensaje += ` - Vuelto: ₲ ${this.formatNumber(this.vuelto)}`;
                }
                mostrarNotificacion(mensaje, 'success');

                // Mostrar advertencias de stock si las hay
                if (data.stock_warnings && data.stock_warnings.length > 0) {
                    mostrarNotificacion(`${data.stock_warnings.length} producto(s) quedaron sin stock`, 'warning');
                }
                if (data.low_stock_warnings && data.low_stock_warnings.length > 0) {
                    mostrarNotificacion(`${data.low_stock_warnings.length} producto(s) con stock bajo`, 'info');
                }

                // Limpiar carrito
                this.limpiarVenta();
                this.enfocarBusqueda();
                try {
                    window.dispatchEvent(new CustomEvent('dashboard:refresh-totals'));
                    window.dispatchEvent(new CustomEvent('caja:venta-cobrada', {
                        detail: { id_venta: idVenta }
                    }));
                    localStorage.setItem('caja_estado_refresh_v1', String(Date.now()));
                    if (window.dashboardRefreshTotals) window.dashboardRefreshTotals();
                } catch (e) {
                }
                if (cerrarPosAlFinalizar && impresionOk) {
                    const cajaEstadoUrl = "/caja/";
                    if (typeof window.appOpenTab === 'function') {
                        window.appOpenTab(cajaEstadoUrl, 'Caja', 'fas fa-wallet', {
                            activate: false,
                            scroll: false,
                            preferExistingByTitle: true
                        });
                    }
                    if (typeof window.appCloseActiveTab === 'function') {
                        const cerrado = window.appCloseActiveTab();
                        if (cerrado && typeof window.appOpenTab === 'function') {
                            window.appOpenTab(cajaEstadoUrl, 'Caja', 'fas fa-wallet', {
                                activate: true,
                                scroll: true,
                                preferExistingByTitle: true
                            });
                            return;
                        }
                    }
                    if (typeof window.appOpenTab === 'function') {
                        window.appOpenTab(cajaEstadoUrl, 'Caja', 'fas fa-wallet', {
                            activate: true,
                            scroll: true,
                            preferExistingByTitle: true
                        });
                        return;
                    }
                    window.location.href = cajaEstadoUrl;
                    return;
                }
            } else {
                let mensajeError = 'Error: ' + data.error;
                if (data.stock_warnings && data.stock_warnings.length > 0) {
                    mensajeError += '\n\nProductos con problema de stock:\n' + data.stock_warnings.map(w => `- ${w.codigo} ${w.producto} (disp: ${w.stock_disponible}, sol: ${w.cantidad_solicitada})`).join('\n');
                }
                mostrarNotificacion(mensajeError, 'error');
            }
        } catch (error) {
            const requestId = clientRequestId || this.generarClientRequestId();
            const payload = this.construirPayloadVenta(requestId, idAutorizacion);
            this.procesando = false;
            this.guardarVentaPendiente(payload, requestId);
            return;
        }

        this.procesando = false;
    },

    generarTicketPreviewHtml() {
        const empresa = POS_EMPRESA || {};
        const items = this.carrito || [];
        const pagos = this.pagos || [];

        // Cálculos
        const subtotal = this.subtotal || 0;
        const descuento = parseFloat(this.descuento) || 0;
        const total = this.total || 0;
        const totalPagado = this.totalPagado || 0;
        // Si aún no se pagó todo, simulamos que se paga el total para el ticket (o mostramos lo real)
        // En vista previa, mostramos lo que se VA a registrar.
        // Si es solo vista previa antes de pagar, asumimos que se completará el pago o mostramos el estado actual.
        // Generalmente el ticket final muestra los pagos realizados.
        // Si el usuario paga exacto o mas, calculamos el vuelto
        const vuelto = Math.max(0, totalPagado - total);

        const fecha = new Date().toLocaleString('es-PY');
        const moneda = '₲';
        const clienteNombre = this.clienteSeleccionado ? this.clienteSeleccionado.nombre : 'Consumidor Final';
        const clienteRuc = this.clienteSeleccionado ? (this.clienteSeleccionado.ruc_ci || 'Sin RUC') : '44444401-7';

        const rows = items.map(it => {
            const nombre = this.escapeHtml(it.nombre || '');
            const codigo = this.escapeHtml(it.codigo || '');
            const cant = parseInt(it.cantidad) || 0;
            const precio = parseFloat(it.precio) || 0;
            const lineTotal = precio * cant;
            return `
                            <tr>
                                <td style="vertical-align: top;">
                                    <div>${nombre}</div>
                                    <div style="font-size: 11px; color:#444;">${codigo ? codigo + ' - ' : ''}${moneda} ${this.formatNumber(precio)}</div>
                                </td>
                                <td style="text-align:right; white-space:nowrap; vertical-align: top;">${cant}</td>
                                <td style="text-align:right; white-space:nowrap; vertical-align: top;">${moneda} ${this.formatNumber(lineTotal)}</td>
                            </tr>
                        `;
        }).join('');

        const pagosResumen = new Map();
        for (const p of pagos) {
            const n = this.escapeHtml(p.nombre || 'Pago');
            const m = parseFloat(p.monto) || 0;
            // const ref = String(p.referencia || '').trim(); // Si tuvieramos referencia
            const curr = pagosResumen.get(n) || { monto: 0 };
            curr.monto += m;
            pagosResumen.set(n, curr);
        }
        const pagosRows = [...pagosResumen.entries()].map(([n, info]) => {
            return `<div style="display:flex; justify-content: space-between; gap: 8px;"><span>${n}</span><span style="white-space:nowrap;">${moneda} ${this.formatNumber(info.monto)}</span></div>`;
        }).join('');

        return `<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vista Previa</title>
  <style>
    @page { size: 58mm auto; margin: 0; }
    html, body { padding:0; margin:0; }
    body { font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #000; width: 58mm; max-width: 58mm; padding: 3mm; box-sizing: border-box; background: white; margin: 0 auto; text-rendering: geometricPrecision; }
    .center { text-align: center; }
    .right { text-align: right; }
    .muted { color: #444; }
    .sep { border-top: 1px dashed #000; margin: 8px 0; }
    .h1 { font-size: 14px; font-weight: 700; margin: 0; }
    .small { font-size: 11px; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th, td { padding: 3px 0; vertical-align: top; }
    th { font-size: 11px; font-weight: 700; border-bottom: 1px solid #000; text-align: left; }
    div,span,td,th,p { word-break: normal; overflow-wrap: break-word; }
    
    .col-cant { width: 10mm; text-align: right; }
    .col-total { width: 16mm; text-align: right; }

    /* Marca de agua estilo "Vista Previa" */
    .watermark {
        position: fixed;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%) rotate(-45deg);
        font-size: 30px;
        color: rgba(200, 200, 200, 0.4);
        z-index: 100;
        font-weight: bold;
        pointer-events: none;
        white-space: nowrap;
    }
  </style>
</head>
<body>
  <div class="watermark">VISTA PREVIA</div>
  <div class="center">
    ${empresa.nombre ? `<div class="h1">${this.escapeHtml(empresa.nombre)}</div>` : ``}
    ${empresa.ruc ? `<div class="small muted">RUC: ${this.escapeHtml(empresa.ruc)}</div>` : ``}
    ${empresa.telefono ? `<div class="small muted">Tel: ${this.escapeHtml(empresa.telefono)}</div>` : ``}
    ${empresa.direccion ? `<div class="small muted">${this.escapeHtml(empresa.direccion)}</div>` : ``}
  </div>
  <div class="sep"></div>
  <div class="small">
    <div>Fecha: <span style="white-space:nowrap;">${this.escapeHtml(fecha)}</span></div>
    <div>Cliente: ${this.escapeHtml(clienteNombre)}</div>
    <div>RUC/CI: ${this.escapeHtml(clienteRuc)}</div>
  </div>
  <div class="sep"></div>
  <table>
    <thead>
      <tr>
        <th>Prod</th>
        <th class="right col-cant" style="white-space:nowrap;">Cant</th>
        <th class="right col-total" style="white-space:nowrap;">Total</th>
      </tr>
    </thead>
    <tbody>
      ${rows}
    </tbody>
  </table>
  <div class="sep"></div>
  <table>
    <tbody>
      <tr><td>Subtotal</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(subtotal)}</td></tr>
      ${descuento > 0 ? `<tr><td>Descuento</td><td class="right" style="white-space:nowrap;">- ${moneda} ${this.formatNumber(descuento)}</td></tr>` : ``}
      <tr><td><strong>Total</strong></td><td class="right" style="white-space:nowrap;"><strong>${moneda} ${this.formatNumber(total)}</strong></td></tr>
    </tbody>
  </table>
  ${pagosRows ? `<div class="sep"></div><div class="small"><div class="muted" style="margin-bottom: 4px;">Detalle de pago</div>${pagosRows}</div>` : ``}
  <div class="sep"></div>
  <table>
    <tbody>
      <tr><td>Total pagado</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(totalPagado)}</td></tr>
      ${vuelto > 0 ? `<tr><td>Vuelto</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(vuelto)}</td></tr>` : ``}
    </tbody>
  </table>
  <div class="sep"></div>
  <div class="center small muted">*** VISTA PREVIA ***</div>
</body>
</html>`;
    },

    limpiarVenta() {
        const rid = this.reparacionId;
        this.carrito = [];
        this.descuento = 0;
        this.pagos = [];
        this.condicionVenta = 'contado';
        this.creditoModo = 'cuenta_corriente';
        this.creditoCuotas = 3;
        this.creditoFrecuenciaDias = 30;
        this.creditoPrimerVencimiento = '';
        this.clienteId = 1;
        this.clienteSeleccionado = this.clientesDefault.find(c => c.id_cliente == 1) || null;
        this.vendedorId = (typeof VENDEDOR_ID_INICIAL !== 'undefined' && VENDEDOR_ID_INICIAL !== null)
            ? Number(VENDEDOR_ID_INICIAL)
            : null;
        this.reparacionId = null;
        this.colaCobroId = null;
        this.forzarPrecioMayorista = false;  // Reset del toggle mayorista
        this.bloquearPrecioMayorista = false;
        this.actualizarTotal();
        this.limpiarEstadoGuardado();
        if (rid) {
            sessionStorage.setItem(`pos_reparacion_skip_${rid}`, '1');
            sessionStorage.setItem(`pos_reparacion_skip_token_${rid}`, this.reparacionToken || '');
        }
        this.enfocarBusqueda();
    },

    formatNumber(num) {
        return new Intl.NumberFormat('es-PY').format(Math.round(num));
    },

    // --- Reimprimir Último Ticket ---
    cargarUltimaVenta() {
        try {
            const guardado = localStorage.getItem(LAST_SALE_KEY);
            if (guardado) {
                const data = JSON.parse(guardado);
                // Verificar que no sea demasiado antiguo (24 horas)
                if (Date.now() - data.timestamp < 24 * 60 * 60 * 1000) {
                    this.ultimaVentaId = data.id_venta;
                } else {
                    localStorage.removeItem(LAST_SALE_KEY);
                }
            }
        } catch (e) {
            console.warn('Error cargando última venta:', e);
        }
    },

    guardarUltimaVenta(idVenta) {
        try {
            localStorage.setItem(LAST_SALE_KEY, JSON.stringify({
                id_venta: idVenta,
                timestamp: Date.now()
            }));
            this.ultimaVentaId = idVenta;
        } catch (e) {
            console.warn('Error guardando última venta:', e);
        }
    },

    reimprimirUltimoTicket() {
        if (!this.ultimaVentaId) {
            mostrarNotificacion('No hay ninguna venta reciente para reimprimir', 'warning');
            return;
        }
        this.imprimirTicketVenta(this.ultimaVentaId).then((ok) => {
            if (ok) {
                mostrarNotificacion(`Reimprimiendo ticket #${this.ultimaVentaId}`, 'success');
            } else {
                mostrarNotificacion('No se pudo abrir la impresión del ticket', 'warning');
            }
        });
    }
        }
    }
    window.posApp = posApp;
    }) ();
