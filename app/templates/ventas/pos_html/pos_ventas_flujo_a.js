            esVentaCreditoPendiente(payload = null) {
                const ventaPayload = payload || {};
                const pagos = Array.isArray(ventaPayload.pagos) ? ventaPayload.pagos : [];
                return pagos.some(pago => {
                    if (!pago) return false;
                    if (pago.es_credito === true) return true;
                    if (!this.creditoMetodoPagoId) return false;
                    return parseInt(pago.id_metodo_pago) === parseInt(this.creditoMetodoPagoId);
                });
            },

            guardarVentaPendiente(payload, clientRequestId) {
                if (this.esVentaCreditoPendiente(payload)) {
                    mostrarNotificacion('Las ventas a credito requieren conexion estable. Reintente cuando el POS vuelva a estar online.', 'error');
                    return;
                }
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
                if (typeof this.actualizarBeneficiosFidelizacion === 'function') {
                    this.actualizarBeneficiosFidelizacion(cliente);
                }
                if (typeof this.actualizarResumenCreditoCliente === 'function') {
                    this.actualizarResumenCreditoCliente(cliente);
                }

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
            guardandoLimiteCredito: false,
            limiteCreditoEdicion: 0,
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

            sincronizarLimiteCreditoEdicion(cliente = null) {
                const origen = cliente || this.clienteSeleccionado || {};
                const limiteCliente = Number(origen && origen.limite_credito);
                const limiteResumen = Number(this.resumenCreditoCliente && this.resumenCreditoCliente.limiteCredito);
                if (Number.isFinite(limiteCliente)) {
                    this.limiteCreditoEdicion = Math.max(0, limiteCliente);
                    return;
                }
                if (Number.isFinite(limiteResumen)) {
                    this.limiteCreditoEdicion = Math.max(0, limiteResumen);
                    return;
                }
                this.limiteCreditoEdicion = 0;
            },

            async guardarLimiteCreditoCliente() {
                if (this.guardandoLimiteCredito) return;
                const cliente = this.clienteSeleccionado;
                const clienteId = Number(cliente && cliente.id_cliente ? cliente.id_cliente : 0);
                if (!clienteId || clienteId === 1) return;

                const limiteCredito = Math.max(0, Number(this.limiteCreditoEdicion || 0));
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                this.guardandoLimiteCredito = true;
                try {
                    const response = await fetch(`/clientes/${clienteId}/limite_credito_json`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
                        },
                        body: JSON.stringify({
                            limite_credito: limiteCredito,
                        })
                    });
                    const data = await response.json();
                    if (!response.ok || !data.success) {
                        throw new Error(data.error || 'No se pudo actualizar el limite de credito');
                    }

                    const clienteActualizado = {
                        ...cliente,
                        ...(data.cliente || {}),
                        limite_credito: Number((data.cliente && data.cliente.limite_credito) || limiteCredito),
                    };
                    this.clienteSeleccionado = clienteActualizado;
                    this.limiteCreditoEdicion = Number(clienteActualizado.limite_credito || 0);

                    if (Array.isArray(this.clientesDefault)) {
                        this.clientesDefault = this.clientesDefault.map(item => Number(item.id_cliente) === clienteId
                            ? { ...item, ...clienteActualizado }
                            : item);
                    }
                    if (Array.isArray(this.clientesEncontrados)) {
                        this.clientesEncontrados = this.clientesEncontrados.map(item => Number(item.id_cliente) === clienteId
                            ? { ...item, ...clienteActualizado }
                            : item);
                    }
                    if (this.resumenCreditoCache && this.resumenCreditoCache[clienteId]) {
                        this.resumenCreditoCache[clienteId] = {
                            ...this.resumenCreditoCache[clienteId],
                            limiteCredito: Number(clienteActualizado.limite_credito || 0),
                            creditoDisponible: Number((data.cliente && data.cliente.credito_disponible) || this.resumenCreditoCache[clienteId].creditoDisponible || 0),
                        };
                    }
                    if (typeof this.refrescarResumenCreditoCliente === 'function') {
                        await this.refrescarResumenCreditoCliente(clienteId);
                    }
                    if (typeof this.actualizarResumenCreditoCliente === 'function') {
                        await this.actualizarResumenCreditoCliente(clienteActualizado);
                    }
                    mostrarNotificacion('Limite de credito actualizado', 'success');
                } catch (e) {
                    mostrarNotificacion(e.message || 'No se pudo actualizar el limite de credito', 'error');
                } finally {
                    this.guardandoLimiteCredito = false;
                }
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
                        this.sincronizarLimiteCreditoEdicion(data.cliente);
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

            resetProductoRapidoForm() {
                this.productoRapidoForm = {
                    codigo: '',
                    nombre: '',
                    precio_venta: '',
                    id_categoria: this.categoriasProductoRapido.length > 0 ? this.categoriasProductoRapido[0].id_categoria : '',
                    stock_minimo: 0,
                    sobre_pedido: true,
                };
            },

            generarCodigoProductoRapido() {
                const ahora = new Date();
                const y = String(ahora.getFullYear()).slice(-2);
                const m = String(ahora.getMonth() + 1).padStart(2, '0');
                const d = String(ahora.getDate()).padStart(2, '0');
                const hh = String(ahora.getHours()).padStart(2, '0');
                const mm = String(ahora.getMinutes()).padStart(2, '0');
                const ss = String(ahora.getSeconds()).padStart(2, '0');
                return `SP-${y}${m}${d}-${hh}${mm}${ss}`;
            },

            abrirModalProductoRapido() {
                if (!this.puedeCrearProductoRapido) {
                    mostrarNotificacion('No tiene permisos para crear productos.', 'warning');
                    return;
                }
                if (!this.categoriasProductoRapido || this.categoriasProductoRapido.length === 0) {
                    mostrarNotificacion('No hay categorías activas para crear el producto.', 'warning');
                    return;
                }
                this.resetProductoRapidoForm();
                this.mostrarModalProductoRapido = true;
                this.$nextTick(() => {
                    if (this.$refs.inputProductoRapidoNombre) this.$refs.inputProductoRapidoNombre.focus();
                });
            },

            cerrarModalProductoRapido() {
                this.mostrarModalProductoRapido = false;
                this.guardandoProductoRapido = false;
                this.enfocarBusqueda();
            },

            async guardarProductoRapido() {
                if (this.guardandoProductoRapido) return;
                const nombre = String(this.productoRapidoForm.nombre || '').trim();
                const precioVenta = Number(this.productoRapidoForm.precio_venta || 0);
                const idCategoria = Number(this.productoRapidoForm.id_categoria || 0);
                const stockMinimo = Math.max(0, parseInt(this.productoRapidoForm.stock_minimo || 0, 10) || 0);
                const esSobrePedido = this.productoRapidoForm.sobre_pedido === true;

                if (!nombre) {
                    mostrarNotificacion('Ingrese un nombre para el producto.', 'warning');
                    return;
                }
                if (!idCategoria) {
                    mostrarNotificacion('Seleccione una categoría.', 'warning');
                    return;
                }
                if (!Number.isFinite(precioVenta) || precioVenta <= 0) {
                    mostrarNotificacion('El precio de venta debe ser mayor a cero.', 'warning');
                    return;
                }

                let codigo = String(this.productoRapidoForm.codigo || '').trim().toUpperCase();
                if (!codigo) {
                    codigo = this.generarCodigoProductoRapido();
                }
                if (esSobrePedido && !codigo.startsWith('SP-')) {
                    codigo = `SP-${codigo}`;
                }

                const payload = {
                    codigo: codigo,
                    nombre: nombre,
                    id_categoria: idCategoria,
                    precio_compra: 0,
                    precio_venta: Math.round(precioVenta),
                    stock_minimo: stockMinimo,
                    porcentaje_iva: 10,
                };

                this.guardandoProductoRapido = true;
                try {
                    const response = await fetch('/productos/crear_rapido', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    const data = await response.json();
                    if (!response.ok || !data.success || !data.producto) {
                        mostrarNotificacion((data && data.error) ? data.error : 'No se pudo crear el producto rápido.', 'error');
                        return;
                    }

                    let productoPos = null;
                    try {
                        const respProducto = await fetch(`/productos/buscar_exacto?q=${encodeURIComponent(data.producto.codigo || codigo)}`);
                        if (respProducto.ok) {
                            const productoExacto = await respProducto.json();
                            if (productoExacto && productoExacto.id) {
                                productoPos = productoExacto;
                            }
                        }
                    } catch (e) {
                    }

                    if (!productoPos) {
                        productoPos = {
                            id: data.producto.id,
                            codigo: data.producto.codigo || codigo,
                            nombre: data.producto.nombre || nombre,
                            precio: Number(data.producto.precio_venta || payload.precio_venta),
                            precio_mayorista: data.producto.precio_mayorista ? Number(data.producto.precio_mayorista) : null,
                            iva: 10,
                            stock: 0,
                            stock_minimo: Number(data.producto.stock_minimo || stockMinimo),
                            es_servicio: false,
                            precios_opciones: [],
                        };
                    }

                    this.agregarProducto(productoPos);
                    this.mostrarModalProductoRapido = false;
                    this.resetProductoRapidoForm();
                    mostrarNotificacion('Producto rápido creado y agregado al carrito.', 'success');
                } catch (e) {
                    mostrarNotificacion('Error de conexión al crear producto rápido.', 'error');
                } finally {
                    this.guardandoProductoRapido = false;
                }
            },

            async buscarProductos() {
                if (this.busqueda.length < 2) {
                    this.resultados = [];
                    return;
                }

                const response = await fetch(`/ventas/catalogo/buscar?q=${encodeURIComponent(this.busqueda)}`);
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
