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
                precio_manual: it.precio_manual === true,
                precio_opcion_id: it.precio_opcion_id || null,
                nombre: it.nombre,
                codigo: it.codigo
            })),
            pagos: pagosNormalizados,
            id_cliente: this.clienteId,
            beneficio_fidelizacion_id: this.beneficioFidelizacionId || null,
            id_usuario_vendedor: this.vendedorId,
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

                    if (cerrarEnDashboardPrincipal) {
                        this.programarVueltaDashboardPrincipal();
                    }
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
        const pagosInmediatos = pagos.filter(pago => !pago || pago.es_credito !== true);
        const montoFinanciado = pagos
            .filter(pago => pago && pago.es_credito === true)
            .reduce((sum, pago) => sum + (parseFloat(pago.monto) || 0), 0);
        const resumenCuotas = (this.esVentaCredito() && this.creditoModo === 'cuotas' && typeof this.resumenCreditoCuotas === 'function')
            ? this.resumenCreditoCuotas()
            : null;

        // CÃ¡lculos
        const subtotal = this.subtotal || 0;
        const descuento = parseFloat(this.descuento) || 0;
        const beneficioDescuento = (typeof this.beneficioFidelizacionDescuentoEstimado === 'function')
            ? (parseFloat(this.beneficioFidelizacionDescuentoEstimado()) || 0)
            : 0;
        const beneficioResumen = (typeof this.resumenBeneficioFidelizacionSeleccionado === 'function')
            ? this.resumenBeneficioFidelizacionSeleccionado()
            : '';
        const total = this.total || 0;
        const totalPagado = pagosInmediatos.reduce((sum, pago) => sum + (parseFloat(pago.monto) || 0), 0);
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
            const esCredito = !!(p && p.es_credito);
            const etiqueta = esCredito
                ? `${p.nombre || 'Credito'} (financiado)`
                : (p.nombre || 'Pago');
            const n = this.escapeHtml(etiqueta);
            const m = parseFloat(p.monto) || 0;
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
      ${beneficioDescuento > 0 ? `<tr><td>${this.escapeHtml(beneficioResumen || 'Beneficio fidelización')}</td><td class="right" style="white-space:nowrap;">- ${moneda} ${this.formatNumber(beneficioDescuento)}</td></tr>` : ``}
      <tr><td><strong>Total</strong></td><td class="right" style="white-space:nowrap;"><strong>${moneda} ${this.formatNumber(total)}</strong></td></tr>
    </tbody>
  </table>
  ${pagosRows ? `<div class="sep"></div><div class="small"><div class="muted" style="margin-bottom: 4px;">Detalle de pago</div>${pagosRows}</div>` : ``}
  <div class="sep"></div>
  <table>
    <tbody>
      <tr><td>${this.esVentaCredito() ? 'Cobrado ahora' : 'Total pagado'}</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(totalPagado)}</td></tr>
      ${montoFinanciado > 0 ? `<tr><td>Saldo financiado</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(montoFinanciado)}</td></tr>` : ``}
      ${resumenCuotas && resumenCuotas.totalConInteres > 0 ? `<tr><td>Interes total (${this.formatNumber(resumenCuotas.tasaInteresPct)}%)</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(resumenCuotas.interesTotal)}</td></tr>` : ``}
      ${resumenCuotas && resumenCuotas.totalConInteres > 0 ? `<tr><td>Total en cuotas</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(resumenCuotas.totalConInteres)}</td></tr>` : ``}
      ${resumenCuotas && resumenCuotas.totalConInteres > 0 ? `<tr><td>Cuota estimada</td><td class="right" style="white-space:nowrap;">${moneda} ${this.formatNumber(resumenCuotas.cuotaEstimada)}</td></tr>` : ``}
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
        const colaId = this.colaCobroId;
        this.carrito = [];
        this.descuento = 0;
        this.pagos = [];
        this.beneficioFidelizacionId = null;
        this.condicionVenta = 'contado';
        this.creditoModo = 'cuenta_corriente';
        this.creditoCuotas = 3;
        this.creditoFrecuenciaDias = 30;
        this.creditoPrimerVencimiento = '';
        this.creditoTasaInteresPct = 0;
        this.clienteId = 1;
        this.clienteSeleccionado = this.clientesDefault.find(c => c.id_cliente == 1) || null;
        this.vendedorId = (typeof VENDEDOR_ID_INICIAL !== 'undefined' && VENDEDOR_ID_INICIAL !== null)
            ? Number(VENDEDOR_ID_INICIAL)
            : null;
        this.reparacionId = null;
        this.clienteServicioId = null;
        this.clienteServicioIds = [];
        this.agendaActividadId = null;
        this.colaCobroId = null;
        this.forzarPrecioMayorista = false;  // Reset del toggle mayorista
        this.bloquearPrecioMayorista = false;
        this.actualizarTotal();
        this.limpiarEstadoGuardado();
        if (rid) {
            sessionStorage.setItem(`pos_reparacion_skip_${rid}`, '1');
            sessionStorage.setItem(`pos_reparacion_skip_token_${rid}`, this.reparacionToken || '');
        }
        if (colaId) {
            sessionStorage.setItem(`pos_cola_skip_${colaId}`, '1');
            sessionStorage.setItem(`pos_cola_skip_token_${colaId}`, this.reparacionToken || '');
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
