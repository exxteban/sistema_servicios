            beneficiosFidelizacion: {
                clienteId: null,
                cantidad: 0,
                cargando: false,
                error: '',
                items: [],
            },
            beneficiosFidelizacionCache: {},
            beneficioFidelizacionId: null,

            limpiarBeneficiosFidelizacion() {
                this.beneficiosFidelizacion = {
                    clienteId: null,
                    cantidad: 0,
                    cargando: false,
                    error: '',
                    items: [],
                };
                this.beneficioFidelizacionId = null;
            },

            beneficioFidelizacionSeleccionado() {
                const id = Number(this.beneficioFidelizacionId || 0);
                if (!id) return null;
                return (this.beneficiosFidelizacion.items || []).find(item => Number(item.id_movimiento || 0) === id) || null;
            },

            beneficioFidelizacionEsAplicablePos(item = null) {
                const beneficio = item || this.beneficioFidelizacionSeleccionado();
                return !!(beneficio && beneficio.pos_aplicable === true);
            },

            beneficioFidelizacionDescuentoEstimado() {
                const beneficio = this.beneficioFidelizacionSeleccionado();
                if (!beneficio || !this.beneficioFidelizacionEsAplicablePos(beneficio)) return 0;
                const subtotal = Number(parseFloat(this.subtotal) || 0);
                const descuentoManual = Number(parseFloat(this.descuento) || 0);
                const base = Math.max(0, subtotal - descuentoManual);
                if (base <= 0) return 0;
                const valor = Number(parseFloat(beneficio.valor) || 0);
                if (beneficio.tipo === 'descuento_porcentaje') {
                    return Math.max(0, (base * valor) / 100);
                }
                if (beneficio.tipo === 'descuento_monto' || beneficio.tipo === 'saldo_favor') {
                    return Math.max(0, Math.min(base, valor));
                }
                return 0;
            },

            resumenBeneficioFidelizacionSeleccionado() {
                const beneficio = this.beneficioFidelizacionSeleccionado();
                return beneficio ? String(beneficio.resumen || '').trim() : '';
            },

            validarBeneficioFidelizacionAntesDeProcesar() {
                const beneficio = this.beneficioFidelizacionSeleccionado();
                if (!beneficio) return true;
                const subtotal = Number(parseFloat(this.subtotal) || 0);
                const descuentoManual = Number(parseFloat(this.descuento) || 0);
                const base = Math.max(0, subtotal - descuentoManual);
                const descuentoBeneficio = Number(parseFloat(this.beneficioFidelizacionDescuentoEstimado()) || 0);
                if (base <= 0 || descuentoBeneficio >= base) {
                    mostrarNotificacion('El beneficio seleccionado deja el total en cero o negativo. Ajuste el descuento manual o no lo aplique.', 'warning');
                    return false;
                }
                return true;
            },

            seleccionarBeneficioFidelizacion(idMovimiento = null) {
                if (!idMovimiento) {
                    this.beneficioFidelizacionId = null;
                    this.actualizarTotal();
                    return;
                }
                const beneficio = (this.beneficiosFidelizacion.items || []).find(
                    item => Number(item.id_movimiento || 0) === Number(idMovimiento)
                );
                if (!beneficio) {
                    this.beneficioFidelizacionId = null;
                    this.actualizarTotal();
                    return;
                }
                if (!this.beneficioFidelizacionEsAplicablePos(beneficio)) {
                    mostrarNotificacion('Ese beneficio requiere aplicación manual y no descuenta en POS.', 'info');
                    return;
                }
                this.beneficioFidelizacionId = Number(beneficio.id_movimiento);
                this.actualizarTotal();
            },

            async actualizarBeneficiosFidelizacion(cliente = null) {
                const clienteActual = cliente || this.clienteSeleccionado;
                const clienteId = Number(clienteActual && clienteActual.id_cliente ? clienteActual.id_cliente : (this.clienteId || 0));
                if (!clienteId || clienteId === 1) {
                    this.limpiarBeneficiosFidelizacion();
                    return;
                }

                const cache = this.beneficiosFidelizacionCache[clienteId];
                if (cache) {
                    this.beneficiosFidelizacion = { ...cache, cargando: false, error: '' };
                    const seleccionadoSigue = (cache.items || []).some(item => Number(item.id_movimiento || 0) === Number(this.beneficioFidelizacionId || 0));
                    if (!seleccionadoSigue) this.beneficioFidelizacionId = null;
                    this.actualizarTotal();
                    return;
                }

                this.beneficiosFidelizacion = {
                    clienteId,
                    cantidad: 0,
                    cargando: true,
                    error: '',
                    items: [],
                };
                this.beneficioFidelizacionId = null;

                try {
                    const response = await fetch(`/clientes/${clienteId}/fidelizacion_json`);
                    const data = await response.json();
                    if (!response.ok || !data.success) {
                        throw new Error(data.error || 'No se pudo cargar la fidelización del cliente');
                    }
                    const resumenPos = data.beneficios_pos || { cantidad: 0, items: [] };
                    const resumen = {
                        clienteId,
                        cantidad: Number(resumenPos.cantidad || 0),
                        cargando: false,
                        error: '',
                        items: Array.isArray(resumenPos.items) ? resumenPos.items : [],
                    };
                    this.beneficiosFidelizacionCache[clienteId] = resumen;
                    if (Number(this.clienteId || 0) === clienteId) {
                        this.beneficiosFidelizacion = { ...resumen };
                        this.actualizarTotal();
                    }
                } catch (e) {
                    if (Number(this.clienteId || 0) === clienteId) {
                        this.beneficiosFidelizacion = {
                            clienteId,
                            cantidad: 0,
                            cargando: false,
                            error: e.message || 'No se pudo cargar la fidelización del cliente',
                            items: [],
                        };
                        this.actualizarTotal();
                    }
                }
            },

            async refrescarBeneficiosFidelizacion(clienteId = null) {
                const id = Number(clienteId || this.clienteId || 0);
                if (!id || id === 1) {
                    this.limpiarBeneficiosFidelizacion();
                    return;
                }
                delete this.beneficiosFidelizacionCache[id];
                await this.actualizarBeneficiosFidelizacion({ id_cliente: id });
            },
