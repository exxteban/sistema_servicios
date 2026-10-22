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
        const numeroFactura = this.escapeHtml((this.numeroFactura || '').trim());
        const origenGastronomia = !!(this.colaCobroId && this.gastronomiaPedidoId && this.gastronomiaCodigoEntrega);
        const origenEntrega = this.gastronomiaMesa
            ? `Mesa ${this.escapeHtml(this.gastronomiaMesa)}`
            : this.escapeHtml((this.gastronomiaTipoPedido || '').replace(/_/g, ' '));
        const referenciaEntrega = this.escapeHtml(this.gastronomiaReferenciaEntrega || '');

        const rows = items.map(it => {
            const nombre = this.escapeHtml(it.nombre || '');
            const codigo = this.escapeHtml(it.codigo || '');
            const cant = parseInt(it.cantidad) || 0;
            const precio = parseFloat(it.precio) || 0;
            const lineTotal = this.subtotalItemPromocion(it);
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
    .pickup-code { font-size: 20px; font-weight: 900; letter-spacing: 1px; }
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
    ${origenGastronomia ? `<div>Pedido gastro: #${this.escapeHtml(this.gastronomiaPedidoId)}</div>` : ``}
    ${origenGastronomia ? `<div class="pickup-code">Codigo: ${this.escapeHtml(this.gastronomiaCodigoEntrega)}</div>` : ``}
    ${origenGastronomia && referenciaEntrega ? `<div>Entrega: ${referenciaEntrega}</div>` : ``}
    ${origenGastronomia && origenEntrega ? `<div>Origen: ${origenEntrega}</div>` : ``}
    <div>Fecha: <span style="white-space:nowrap;">${this.escapeHtml(fecha)}</span></div>
    <div>Cliente: ${this.escapeHtml(clienteNombre)}</div>
    <div>RUC/CI: ${this.escapeHtml(clienteRuc)}</div>
    ${numeroFactura ? `<div>Nº Factura: ${numeroFactura}</div>` : ``}
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
        if (typeof this.feReset === 'function') this.feReset();
        const rid = this.reparacionId;
        const colaId = this.colaCobroId;
        this.carrito = [];
        this.descuento = 0;
        this.pagos = [];
        this.beneficioFidelizacionId = null;
        this.numeroFactura = '';
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
        this.gastronomiaPedidoId = null;
        this.gastronomiaCodigoEntrega = '';
        this.gastronomiaReferenciaEntrega = '';
        this.gastronomiaTipoPedido = '';
        this.gastronomiaMesa = '';
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
