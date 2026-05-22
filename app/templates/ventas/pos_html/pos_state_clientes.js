(function () {
        const POS_STATE_KEY = 'pos_venta_actual';
        const POS_STATE_MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 horas
        const PENDING_SALES_KEY = 'pos_ventas_pendientes_v1';
        const LAST_SALE_KEY = 'pos_ultima_venta';
    const POS_EMPRESA = {{ empresa| tojson
    }};
    const REPARACION_DATA = {{ (reparacion_data if reparacion_data is defined else None)| tojson }};
    const AGENDA_TURNO_DATA = {{ (agenda_turno_data if agenda_turno_data is defined else None)| tojson }};
    const CLIENTE_SERVICIO_DATA = {{ (cliente_servicio_data if cliente_servicio_data is defined else None)| tojson }};
    const COLA_COBRO_DATA = {{ (cola_cobro_data if cola_cobro_data is defined else None)| tojson }};
    const REPARACION_TOKEN = {{ (reparacion_token if reparacion_token is defined else None)| tojson }};
    const VENDEDORES_CAJEROS = {{ (vendedores_cajeros if vendedores_cajeros is defined else [])|tojson }};
    const VENDEDOR_ID_INICIAL = {{ (vendedor_default_id if vendedor_default_id is defined else None)|tojson }};
    const OCULTAR_SELECTOR_VENDEDOR_POS = {{ (ocultar_selector_vendedor_pos if ocultar_selector_vendedor_pos is defined else False)|tojson }};
    const CAJA_FLUJO_ENVIADO_ACTIVO = {{ (caja_flujo_enviado_activo if caja_flujo_enviado_activo is defined else False)|tojson }};
    const PUEDE_ENVIAR_CAJA_VENTA = {{ (puede_enviar_caja_venta if puede_enviar_caja_venta is defined else False)|tojson }};
    const CAJA_EXIGIR_CAJERO_PARA_COBRO = {{ (caja_exigir_cajero_para_cobro if caja_exigir_cajero_para_cobro is defined else False)|tojson }};
    const PUEDE_COBRAR_POS_DIRECTO = {{ (puede_cobrar_pos_directo if puede_cobrar_pos_directo is defined else False)|tojson }};
    const SOLO_REGISTRO_VENDEDOR = {{ (solo_registro_vendedor if solo_registro_vendedor is defined else False)|tojson }};
    const POS_VENTAS_CREDITO_ACTIVO = {{ (ventas_credito_activo if ventas_credito_activo is defined else False)|tojson }};
    const POS_METODO_CREDITO = {{ (metodo_credito_pos if metodo_credito_pos is defined else None)|tojson }};
    const POS_PUEDE_CREAR_PRODUCTO_RAPIDO = {{ (puede_crear_producto_rapido if puede_crear_producto_rapido is defined else False)|tojson }};
    const POS_CATEGORIAS_PRODUCTO_RAPIDO = {{ (categorias_pos_rapido if categorias_pos_rapido is defined else [])|tojson }};

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
            creditoModo: (POS_INITIAL_STATE && (POS_INITIAL_STATE.creditoModo === 'cuenta_corriente' || POS_INITIAL_STATE.creditoModo === 'cuotas'))
                ? POS_INITIAL_STATE.creditoModo
                : 'cuenta_corriente',
            enviandoCaja: false,
            reparacionId: null,
            clienteServicioId: null,
            clienteServicioIds: [],
            colaCobroId: null,
            reparacionToken: (typeof REPARACION_TOKEN !== 'undefined' && REPARACION_TOKEN !== null) ? String(REPARACION_TOKEN) : '',

            // Nuevo cliente dropdown data
            clientesDefault: [], // Clientes cargados inicialmente
            descuento: 0,
            subtotal: 0,
            total: 0,
            procesando: false,

            // Pagos mÃºltiples
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
            puedeCrearProductoRapido: !!POS_PUEDE_CREAR_PRODUCTO_RAPIDO,
            categoriasProductoRapido: Array.isArray(POS_CATEGORIAS_PRODUCTO_RAPIDO) ? POS_CATEGORIAS_PRODUCTO_RAPIDO : [],
            mostrarModalProductoRapido: false,
            guardandoProductoRapido: false,
            productoRapidoForm: {
                codigo: '',
                nombre: '',
                precio_venta: '',
                id_categoria: '',
                stock_minimo: 0,
                sobre_pedido: true,
            },

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
                limiteCredito: 0,
                creditoDisponible: 0,
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
                    limiteCredito: 0,
                    creditoDisponible: 0,
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

            async consultarResumenCreditoCliente(clienteId, opciones = {}) {
                const clienteIdNormalizado = Number(clienteId || 0);
                if (!this.ventasCreditoActivo || !clienteIdNormalizado || clienteIdNormalizado === 1) {
                    return null;
                }

                const forzar = !!(opciones && opciones.forzar === true);
                if (!forzar) {
                    const cache = this.resumenCreditoCache[clienteIdNormalizado];
                    if (cache) {
                        return { ...cache };
                    }
                }

                const response = await fetch(`/cobranzas/api/clientes/${clienteIdNormalizado}/resumen`);
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.mensaje || data.error || 'No se pudo consultar deuda del cliente');
                }

                const resumen = {
                    clienteId: clienteIdNormalizado,
                    saldoTotal: Number(data.saldo_total || 0),
                    cuentasAbiertas: Number(data.cuentas_abiertas || 0),
                    cuentasVencidas: Number(data.cuentas_vencidas || 0),
                    limiteCredito: Number(data.limite_credito || 0),
                    creditoDisponible: Number(data.credito_disponible || 0),
                    urlCliente: data.url_cliente || '',
                    urlCobrar: data.url_cobrar || '',
                };
                this.resumenCreditoCache[clienteIdNormalizado] = resumen;
                return { ...resumen };
            },

            async refrescarResumenCreditoCliente(clienteId) {
                const clienteIdNormalizado = Number(clienteId || 0);
                if (!clienteIdNormalizado || clienteIdNormalizado === 1) {
                    return null;
                }
                delete this.resumenCreditoCache[clienteIdNormalizado];
                return await this.consultarResumenCreditoCliente(clienteIdNormalizado, { forzar: true });
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
                    if (typeof this.sincronizarLimiteCreditoEdicion === 'function') {
                        this.sincronizarLimiteCreditoEdicion({ limite_credito: cache.limiteCredito || 0 });
                    }
                    return;
                }

                this.resumenCreditoCliente = {
                    clienteId,
                    saldoTotal: 0,
                    cuentasAbiertas: 0,
                    cuentasVencidas: 0,
                    limiteCredito: 0,
                    creditoDisponible: 0,
                    cargando: true,
                    urlCliente: '',
                    urlCobrar: '',
                };

                try {
                    const resumen = await this.consultarResumenCreditoCliente(clienteId);
                    if (Number(this.clienteId || 0) === clienteId) {
                        this.resumenCreditoCliente = { ...resumen, cargando: false };
                        if (typeof this.sincronizarLimiteCreditoEdicion === 'function') {
                            this.sincronizarLimiteCreditoEdicion({ limite_credito: resumen.limiteCredito || 0 });
                        }
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

{% include "ventas/pos_html/pos_state_runtime.js" %}
{% include "ventas/pos_html/pos_state_storage.js" %}
