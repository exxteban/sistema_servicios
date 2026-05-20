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
