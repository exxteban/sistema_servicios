            // --- Persistencia de Estado ---

            guardarEstado() {
                // No guardar si estamos restaurando o si el carrito estÃ¡ vacÃ­o y no hay cambios
                const vendedorInicial = (typeof VENDEDOR_ID_INICIAL !== 'undefined' && VENDEDOR_ID_INICIAL !== null)
                    ? Number(VENDEDOR_ID_INICIAL)
                    : null;
                if (this.carrito.length === 0 && this.pagos.length === 0 && this.descuento === 0 && !this.beneficioFidelizacionId && this.clienteId === 1 && this.alertaClienteFielActiva === true && (
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
                    beneficioFidelizacionId: this.beneficioFidelizacionId,
                    vendedorId: this.vendedorId,
                    alertaClienteFielActiva: this.alertaClienteFielActiva === true,
                    descuento: this.descuento,
                    condicionVenta: this.condicionVenta,
                    creditoModo: this.creditoModo,
                    creditoCuotas: this.creditoCuotas,
                    creditoFrecuenciaDias: this.creditoFrecuenciaDias,
                    creditoPrimerVencimiento: this.creditoPrimerVencimiento,
                    creditoTasaInteresPct: this.creditoTasaInteresPct,
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

                    if (estado.beneficioFidelizacionId) {
                        this.beneficioFidelizacionId = Number(estado.beneficioFidelizacionId) || null;
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
                    if (estado.creditoModo === 'cuenta_corriente' || estado.creditoModo === 'cuotas') {
                        this.creditoModo = estado.creditoModo;
                    }
                    if (Number.isFinite(Number(estado.creditoCuotas))) {
                        this.creditoCuotas = Number(estado.creditoCuotas);
                    }
                    if (Number.isFinite(Number(estado.creditoFrecuenciaDias))) {
                        this.creditoFrecuenciaDias = Number(estado.creditoFrecuenciaDias);
                    }
                    if (typeof estado.creditoPrimerVencimiento === 'string') {
                        this.creditoPrimerVencimiento = estado.creditoPrimerVencimiento;
                    }
                    if (Number.isFinite(Number(estado.creditoTasaInteresPct))) {
                        this.creditoTasaInteresPct = Number(estado.creditoTasaInteresPct);
                    }
                    if (this.condicionVenta === 'credito' && this.creditoModo === 'cuotas' && !this.creditoPrimerVencimiento) {
                        this.asegurarFechaPrimerVencimientoCredito();
                    }

                    // Restaurar pagos
                    if (estado.pagos && estado.pagos.length > 0) {
                        this.pagos = estado.pagos;
                    }

                    await this.actualizarAlertaClienteFiel();
                    if (typeof this.actualizarBeneficiosFidelizacion === 'function') {
                        await this.actualizarBeneficiosFidelizacion();
                    }
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
                const moneda = 'Gs.';

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
  <div class="small muted center">Se sincroniza cuando vuelva la conexiÃ³n</div>
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
