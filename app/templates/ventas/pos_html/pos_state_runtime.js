            init() {
                if (this.categoriasProductoRapido.length > 0 && !this.productoRapidoForm.id_categoria) {
                    this.productoRapidoForm.id_categoria = this.categoriasProductoRapido[0].id_categoria;
                }
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
                        // DespuÃ©s de cargar clientes, intentar restaurar estado guardado
                        this.restaurarEstado();
                    }
                });

                // Configurar watchers para auto-guardar estado
                this.$watch('carrito', () => this.guardarEstado(), { deep: true });
                this.$watch('clienteId', () => {
                    this.guardarEstado();
                    this.actualizarResumenCreditoCliente();
                    if (typeof this.actualizarBeneficiosFidelizacion === 'function') {
                        this.actualizarBeneficiosFidelizacion();
                    }
                });
                this.$watch('vendedorId', () => this.guardarEstado());
                this.$watch('descuento', () => this.guardarEstado());
                this.$watch('beneficioFidelizacionId', () => this.guardarEstado());
                this.$watch('pagos', () => this.guardarEstado(), { deep: true });
                this.$watch('alertaClienteFielActiva', () => this.guardarEstado());
                this.$watch('condicionVenta', () => this.guardarEstado());
                this.$watch('creditoModo', () => this.guardarEstado());
                this.$watch('creditoCuotas', () => this.guardarEstado());
                this.$watch('creditoFrecuenciaDias', () => this.guardarEstado());
                this.$watch('creditoPrimerVencimiento', () => this.guardarEstado());
                this.$watch('creditoTasaInteresPct', () => this.guardarEstado());
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

            // --- Carga de ReparaciÃ³n ---
            cargarDatosReparacion() {
                try {
                    sessionStorage.removeItem(POS_STATE_KEY); // Limpiar estado anterior
                    this.condicionVenta = 'contado';
                    this.creditoModo = 'cuenta_corriente';
                    this.beneficioFidelizacionId = null;
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
                            .catch(e => console.error('Error cargando cliente de reparaciÃ³n:', e));
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
                        mostrarNotificacion('Abono de reparaciÃ³n aplicado como descuento', 'info');
                    }

                    this.actualizarTotal();
                    mostrarNotificacion('Datos de reparaciÃ³n cargados', 'success');

                } catch (e) {
                    console.error('Error cargando datos de reparaciÃ³n:', e);
                    mostrarNotificacion('Error al cargar datos de la reparaciÃ³n', 'error');
                }
            },

            cargarDatosPendienteCaja() {
                try {
                    sessionStorage.removeItem(POS_STATE_KEY);
                    this.condicionVenta = 'contado';
                    this.creditoModo = 'cuenta_corriente';
                    this.reparacionId = null;
                    this.colaCobroId = Number(COLA_COBRO_DATA.id) || null;
                    this.beneficioFidelizacionId = Number(COLA_COBRO_DATA.beneficio_fidelizacion_id || 0) || null;
                    if (COLA_COBRO_DATA.reparacion_id) {
                        this.reparacionId = Number(COLA_COBRO_DATA.reparacion_id) || null;
                    }

                    if (COLA_COBRO_DATA.items && Array.isArray(COLA_COBRO_DATA.items)) {
                        this.carrito = COLA_COBRO_DATA.items.map(item => ({
                            tipo: item.tipo || 'producto',
                            id_item: item.id,
                            id_producto: item.id_producto || ((item.tipo || 'producto') === 'servicio' ? null : item.id),
                            id_servicio: item.id_servicio || ((item.tipo || 'producto') === 'servicio' ? item.id : null),
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
