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
        if (typeof this.feReset === 'function') this.feError = '';
    },

    esCobroGastronomiaDesdeCola() {
        return !this.soloRegistroVendedor
            && !!this.colaCobroId
            && typeof COLA_COBRO_DATA !== 'undefined'
            && COLA_COBRO_DATA
            && String(COLA_COBRO_DATA.tipo_origen || '').toLowerCase() === 'gastronomia';
    },

    volverDashboardPrincipal() {
        if (this.salidaDashboardEjecutada) return;
        this.salidaDashboardEjecutada = true;
        const dashboardUrl = "{{ url_for('main.dashboard') }}";
        if (typeof window.appCloseActiveTabToPrincipal === 'function' && window.appCloseActiveTabToPrincipal()) {
            return;
        }
        window.location.href = dashboardUrl;
    },

    programarVueltaDashboardPrincipal() {
        if (this.salidaDashboardProgramada) return;
        this.salidaDashboardProgramada = true;
        let ejecutado = false;
        const volver = () => {
            if (ejecutado) return;
            ejecutado = true;
            window.removeEventListener('afterprint', despuesDeImprimir);
            window.removeEventListener('focus', despuesDeFoco);
            this.volverDashboardPrincipal();
        };
        const despuesDeImprimir = () => setTimeout(volver, 250);
        const despuesDeFoco = () => setTimeout(volver, 700);
        window.addEventListener('afterprint', despuesDeImprimir, {once: true});
        window.addEventListener('focus', despuesDeFoco, {once: true});
        setTimeout(volver, 2500);
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
        const pagosNormalizados = (Array.isArray(this.pagos) ? this.pagos : [])
            .map(pago => ({
                ...(pago || {}),
                monto: Number(parseFloat(pago && pago.monto) || 0),
            }))
            .filter(pago => pago.monto > 0.0001);
        const payload = {
            items: this.carrito.map(it => ({
                tipo: it.tipo || 'producto',
                id_producto: it.id_producto,
                id_servicio: it.id_servicio || null,
                cantidad: it.cantidad,
                precio: it.precio,
                subtotal: it.subtotal_guardado ?? null,
                subtotal_cantidad: it.subtotal_guardado_cantidad ?? null,
                promocion_activa: it.promocion_activa || null,
                precio_manual: it.precio_manual === true,
                precio_opcion_id: it.precio_opcion_id || null,
                nombre: it.nombre,
                codigo: it.codigo
            })),
            pagos: pagosNormalizados,
            id_cliente: this.clienteId,
            beneficio_fidelizacion_id: this.beneficioFidelizacionId || null,
            id_usuario_vendedor: this.vendedorId,
            numero_factura: this.mostrarNumeroFactura ? (String(this.numeroFactura || '').trim() || null) : undefined,
            usar_precio_mayorista: this.usaPrecioMayorista() === true,
            forzar_precio_mayorista: this.forzarPrecioMayorista === true,
            descuento: parseFloat(this.descuento) || 0,
            condicion_venta: this.condicionVenta,
            credito_modo: this.esVentaCredito() ? this.creditoModo : null,
            credito_plan: this.creditoPlanPayload(),
            client_request_id: requestId
        };
        if (idAutorizacion) payload.id_autorizacion = idAutorizacion;
        if (this.reparacionId) payload.reparacion_id = this.reparacionId;
        if (this.agendaActividadId) payload.agenda_actividad_id = this.agendaActividadId;
        if (Array.isArray(this.clienteServicioIds) && this.clienteServicioIds.length > 0) {
            payload.cliente_servicio_ids = this.clienteServicioIds;
        } else if (this.clienteServicioId) {
            payload.cliente_servicio_id = this.clienteServicioId;
        }
        if (this.colaCobroId) payload.cola_cobro_id = this.colaCobroId;
        if (this.colaCobroId) payload.debug_perf = true;
        return payload;
    },

            async ejecutarVenta(idAutorizacion = null, clientRequestId = null) {
        if (this.procesando) return;
        this.procesando = true;
        // Declarados fuera del try: si /ventas/procesar no responde a tiempo, la venta
        // se encola con el MISMO client_request_id que ya pudo llegar al servidor, así
        // la sincronización la reconoce (sync-status) en vez de registrarla dos veces.
        let requestId = clientRequestId;
        let payload = null;
        let ventaRegistrada = false;

        try {
            if (!this._validarVendedorSeleccionado()) {
                this.procesando = false;
                return;
            }
            if (!this._validarVueltoAntesDeProcesar()) {
                this.procesando = false;
                return;
            }
            const conFactura = typeof this.feSolicitada === 'function' && this.feSolicitada();
            if (conFactura && !(await this.feValidarAntesDeCobrar())) {
                mostrarNotificacion(this.feError, 'error');
                this.procesando = false;
                return;
            }
            requestId = requestId || this.generarClientRequestId();
            payload = this.construirPayloadVenta(requestId, idAutorizacion);

            if (!this.isOnline) {
                this.procesando = false;
                if (this.esVentaCreditoPendiente(payload)) {
                    mostrarNotificacion('Las ventas a credito requieren conexion estable. Reintente cuando el POS vuelva a estar online.', 'error');
                    return;
                }
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
                ventaRegistrada = true;
                // Cerrar modal de vista previa
                this.mostrarModalVistaPrevia = false;
                this.ticketPreviewHtml = '';

                // Guardar última venta para reimpresión
                const idVenta = data.id_venta;
                const clienteVentaId = Number(this.clienteId || 0);
                const fueVentaCredito = this.esVentaCredito();
                const cerrarPosAlFinalizar = !this.soloRegistroVendedor && !!this.colaCobroId;
                const cerrarEnDashboardPrincipal = this.esCobroGastronomiaDesdeCola();
                let impresionOk = true;
                if (idVenta) {
                    this.guardarUltimaVenta(idVenta);

                    // La emision puede tardar: la vuelta al dashboard se programa
                    // recien al imprimir, para no salir antes del KuDE o del ticket.
                    const antesDeImprimir = () => {
                        if (cerrarEnDashboardPrincipal) this.programarVueltaDashboardPrincipal();
                    };
                    if (conFactura) {
                        impresionOk = await this.feEmitirEImprimir(idVenta, antesDeImprimir);
                    } else {
                        antesDeImprimir();
                        impresionOk = await this.imprimirTicketVenta(idVenta);
                    }
                    if (!impresionOk) {
                        mostrarNotificacion('Venta #' + idVenta + ' registrada. No se pudo abrir la impresión, use "Reimprimir Último Ticket"', 'warning');
                    }
                }

                // Mostrar resumen de venta
                let mensaje = `Venta #${idVenta} registrada correctamente`;
                if (this.vuelto > 0) {
                    mensaje += ` - Vuelto: ₲ ${this.formatNumber(this.vuelto)}`;
                }
                if (data.beneficio_aplicado && data.beneficio_aplicado.resumen) {
                    mensaje += ` - Beneficio: ${data.beneficio_aplicado.resumen}`;
                }
                mostrarNotificacion(mensaje, 'success');

                // Mostrar advertencias de stock si las hay
                if (data.stock_warnings && data.stock_warnings.length > 0) {
                    mostrarNotificacion(`${data.stock_warnings.length} producto(s) quedaron sin stock`, 'warning');
                }
                if (data.low_stock_warnings && data.low_stock_warnings.length > 0) {
                    mostrarNotificacion(`${data.low_stock_warnings.length} producto(s) con stock bajo`, 'info');
                }

                if (fueVentaCredito && clienteVentaId > 1 && typeof this.refrescarResumenCreditoCliente === 'function') {
                    try {
                        await this.refrescarResumenCreditoCliente(clienteVentaId);
                    } catch (e) {
                    }
                }
                if (clienteVentaId > 1 && typeof this.refrescarBeneficiosFidelizacion === 'function') {
                    try {
                        await this.refrescarBeneficiosFidelizacion(clienteVentaId);
                    } catch (e) {
                    }
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
                if (cerrarEnDashboardPrincipal) {
                    this.volverDashboardPrincipal();
                    return;
                }
                if (cerrarPosAlFinalizar && impresionOk) {
                    const cajaEstadoUrl = "{{ url_for('caja.estado') }}";
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
                if (data && data.redirect_url) {
                    mostrarNotificacion(data.error || 'Debe abrir una caja antes de continuar.', 'warning');
                    window.location.href = data.redirect_url;
                    return;
                }
                let mensajeError = 'Error: ' + data.error;
                if (data.stock_warnings && data.stock_warnings.length > 0) {
                    mensajeError += '\n\nProductos con problema de stock:\n' + data.stock_warnings.map(w => `- ${w.codigo} ${w.producto} (disp: ${w.stock_disponible}, sol: ${w.cantidad_solicitada})`).join('\n');
                }
                mostrarNotificacion(mensajeError, 'error');
            }
        } catch (error) {
            this.procesando = false;
            if (ventaRegistrada) {
                // El servidor ya confirmó la venta; el fallo fue después (impresión,
                // refrescos). Encolarla de nuevo solo ensuciaría la cola local.
                console.warn('[POS] Error posterior a registrar la venta:', error);
                return;
            }
            requestId = requestId || this.generarClientRequestId();
            payload = payload || this.construirPayloadVenta(requestId, idAutorizacion);
            if (!Array.isArray(payload.items) || payload.items.length === 0) {
                mostrarNotificacion('No se puede guardar una venta sin productos.', 'warning');
                return;
            }
            this.guardarVentaPendiente(payload, requestId);
            return;
        }

        this.procesando = false;
    },

