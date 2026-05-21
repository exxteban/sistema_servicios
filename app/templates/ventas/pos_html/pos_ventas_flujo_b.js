                if (!producto || !opcion) return;
                this.mostrarModalPrecioOpciones = false;
                this.agregarProductoConPrecioOpcion(producto, opcion);
                this.productoPrecioOpciones = null;
                this.preciosOpcionesActuales = [];
            },

            agregarProductoConPrecioOpcion(producto, opcion) {
                const precio = parseFloat(opcion.precio) || 0;
                const precioOpcionId = opcion.id || null;
                const tipo = producto.tipo || 'producto';
                const existente = this.carrito.find(item => (item.tipo || 'producto') === tipo && item.id_item === producto.id && String(item.precio_opcion_id || '') === String(precioOpcionId || ''));

                if (existente) {
                    existente.cantidad++;
                    this.validarStockItem(existente);
                } else {
                    const nuevoItem = {
                        tipo: tipo,
                        id_item: producto.id,
                        id_producto: tipo === 'servicio' ? null : producto.id,
                        id_servicio: tipo === 'servicio' ? producto.id : null,
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

                const tipo = producto.tipo || 'producto';
                const existente = this.carrito.find(item => (item.tipo || 'producto') === tipo && item.id_item === producto.id && !item.precio_opcion_id);

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
                        tipo: tipo,
                        id_item: producto.id,
                        id_producto: tipo === 'servicio' ? null : producto.id,
                        id_servicio: tipo === 'servicio' ? producto.id : null,
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
                    const response = await fetch(`/ventas/catalogo/buscar_exacto?q=${encodeURIComponent(q)}`);
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
                const descuentoBeneficio = (typeof this.beneficioFidelizacionDescuentoEstimado === 'function')
                    ? (parseFloat(this.beneficioFidelizacionDescuentoEstimado()) || 0)
                    : 0;
                this.total = Math.max(0, (parseFloat(this.subtotal) || 0) - descuento - descuentoBeneficio);
                this.normalizarPagosAlCambiarTotal();
                this.sincronizarPagoCredito();
                this.calcularSaldoPendiente();
            },

            _redondearMontoPago(valor) {
                return Math.max(0, Math.round(parseFloat(valor) || 0));
            },

            normalizarPagosAlCambiarTotal({ conservarManualesEnCero = false, conservarAutosEnCero = false } = {}) {
                const total = parseFloat(this.total) || 0;
                if (!Array.isArray(this.pagos)) this.pagos = [];

                if (this.carrito.length === 0 || total <= 0) {
                    if (this.pagos.length > 0) this.pagos = [];
                    return;
                }

                const pagos = this.pagos.map(p => ({ ...(p || {}) }));
                let totalManual = 0;
                const autoIndices = [];

                for (let i = 0; i < pagos.length; i++) {
                    const pago = pagos[i] || {};
                    pago.monto = this._redondearMontoPago(pago.monto);
                    if (pago.auto === true) {
                        autoIndices.push(i);
                    } else {
                        totalManual += pago.monto;
                    }
                    pagos[i] = pago;
                }

                const restante = Math.max(0, total - totalManual);

                if (autoIndices.length > 0) {
                    const totalAutoActual = autoIndices.reduce((s, idx) => s + (this._redondearMontoPago(pagos[idx].monto)), 0);

                    if (totalAutoActual > 0) {
                        const factor = restante / totalAutoActual;
                        let asignado = 0;
                        for (let k = 0; k < autoIndices.length; k++) {
                            const idx = autoIndices[k];
                            if (k === autoIndices.length - 1) {
                                pagos[idx].monto = this._redondearMontoPago(restante - asignado);
                            } else {
                                const nuevo = this._redondearMontoPago(pagos[idx].monto * factor);
                                pagos[idx].monto = nuevo;
                                asignado += nuevo;
                            }
                        }
                    } else {
                        for (const idx of autoIndices) pagos[idx].monto = 0;
                        pagos[autoIndices[0]].monto = this._redondearMontoPago(restante);
                    }
                }

                this.pagos = pagos.filter(p => {
                    const monto = this._redondearMontoPago(p.monto);
                    if (monto > 0) return true;
                    if (p.auto === true) return conservarAutosEnCero;
                    return conservarManualesEnCero;
                });
            },

            recalcularPagosTrasEditarMonto() {
                this.sincronizarPagoCredito();
                this.normalizarPagosAlCambiarTotal({ conservarManualesEnCero: true, conservarAutosEnCero: true });
                this._actualizarTotalesPago();
            },

            montoMaximoEditablePago(index) {
                const total = this._redondearMontoPago(this.total);
                if (!Array.isArray(this.pagos) || !this.pagos[index] || this.pagos[index].es_credito) {
                    return total;
                }
                let totalManualOtros = 0;
                for (let i = 0; i < this.pagos.length; i++) {
                    if (i === index) continue;
                    const pago = this.pagos[i] || {};
                    if (pago.es_credito || pago.auto === true) continue;
                    totalManualOtros += this._redondearMontoPago(pago.monto);
                }
                return Math.max(0, total - totalManualOtros);
            },

            _avisarExcesoPagoMixto() {
                const ahora = Date.now();
                const ultimo = Number(this.ultimoAvisoExcesoPagoMixtoAt || 0);
                if (ahora - ultimo < 900) return;
                this.ultimoAvisoExcesoPagoMixtoAt = ahora;
                mostrarNotificacion('Ese monto supera lo pendiente. En pagos mixtos solo puedes completar el total exacto.', 'warning');
            },

            manejarInputMontoPago(index) {
                const pago = Array.isArray(this.pagos) ? this.pagos[index] : null;
                if (!pago || pago.es_credito) return;

                pago.auto = false;
                const montoNormalizado = this._redondearMontoPago(pago.monto);
                const montoMaximo = this.montoMaximoEditablePago(index);

                if (montoNormalizado > montoMaximo) {
                    pago.monto = montoMaximo;
                    this._avisarExcesoPagoMixto();
                } else {
                    pago.monto = montoNormalizado;
                }

                this.recalcularPagosTrasEditarMonto();
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
                    if (typeof this.actualizarResumenCreditoCliente === 'function') {
                        this.actualizarResumenCreditoCliente();
                    }
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
                if ((parseFloat(this.total) || 0) <= 0.0001) return false;
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
                const clienteActual = Number(this.clienteId || 0);
                const resumenActual = Number((this.resumenCreditoCliente && this.resumenCreditoCliente.clienteId) || 0);
                if (clienteActual > 1 && clienteActual === resumenActual && !this.resumenCreditoCliente.cargando && !this.clientePuedeCubrirCompromisoCredito()) {
                    mostrarNotificacion(this.mensajeCreditoInsuficienteActual(), 'warning');
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
                    const montoInicial = this.esVentaCredito() ? 0 : (this.saldoPendiente > 0 ? this.saldoPendiente : 0);
                    this.pagos.push({
                        id_metodo_pago: id,
                        nombre: nombre,
                        monto: montoInicial,
                        auto: !this.esVentaCredito() && montoInicial > 0,
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
                    id_metodo_pago: {{ (efectivo_id if efectivo_id is defined else 1) }},
                    nombre: {{ (efectivo_nombre if efectivo_nombre is defined else 'Efectivo') | tojson }},
                    monto: this.total,
                    auto: true
                }];
                this.calcularSaldoPendiente();
            },

    _actualizarTotalesPago() {
        this.totalPagado = this.pagos.reduce((sum, pago) => sum + (parseFloat(pago.monto) || 0), 0);
        const tolerancia = 0.0001;
        const saldo = (parseFloat(this.total) || 0) - this.totalPagado;
        const vuelto = this.totalPagado - (parseFloat(this.total) || 0);
        this.saldoPendiente = saldo > tolerancia ? saldo : 0;
        this.vuelto = vuelto > tolerancia ? vuelto : 0;
    },

    calcularSaldoPendiente() {
        this.sincronizarPagoCredito();
        this._actualizarTotalesPago();
    },

    _efectivoPagado() {
        const efectivoId = {{ (efectivo_id if efectivo_id is defined else 1) }};
    return this.pagos.reduce((sum, pago) => {
        try {
            if (parseInt(pago.id_metodo_pago) === efectivoId) {
                return sum + (parseFloat(pago.monto) || 0);
            }
        } catch (e) { }
        return sum;
    }, 0);
            },

    _totalNoEfectivoPagado() {
        const efectivoId = {{ (efectivo_id if efectivo_id is defined else 1) }};
        return this.pagos.reduce((sum, pago) => {
            try {
                if (parseInt(pago.id_metodo_pago) !== efectivoId) {
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
        const totalNoEfectivo = this._totalNoEfectivoPagado();
        if (totalNoEfectivo > tolerancia) {
            mostrarNotificacion('Con pagos mixtos no se admite vuelto. Ajusta los montos para que coincidan con el total.', 'warning');
            return false;
        }
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
                id_cliente: this.clienteId,
                beneficio_fidelizacion_id: this.beneficioFidelizacionId || null,
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
        if (typeof this.validarBeneficioFidelizacionAntesDeProcesar === 'function' && !this.validarBeneficioFidelizacionAntesDeProcesar()) return;
        if (this.saldoPendiente > 0) {
            mostrarNotificacion('Aún falta pagar ₲ ' + this.formatNumber(this.saldoPendiente), 'warning');
            return;
        }
        if (!this._validarVueltoAntesDeProcesar()) return;

        // Verificar si hay warnings de stock
        const itemsConProblemas = this.verificarStockWarnings();
