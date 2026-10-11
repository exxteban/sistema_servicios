            // --- Factura electronica (opt-in por venta, default OFF) ---
            // La venta se registra igual que siempre; recien despues se emite el DE
            // (/facturacion-electronica/emitir-pos) y se imprime el KuDE. Si la
            // emision falla, sale el ticket normal y el envio automatico reintenta.
            feConfig: {{ (factura_electronica_pos if factura_electronica_pos is defined else None) | tojson }},
            feEmitir: false,
            feError: '',

            feDisponible() {
                return !this.soloRegistroVendedor && !!(this.feConfig && this.feConfig.lista);
            },

            feSolicitada() {
                return this.feDisponible() && this.feEmitir === true;
            },

            feClienteNombre() {
                const cliente = this.clienteSeleccionado;
                if (!cliente || Number(cliente.id_cliente) === 1) return 'Consumidor final';
                return `${cliente.nombre || 'Cliente'} (${cliente.ruc_ci || 'sin RUC'})`;
            },

            feReset() {
                this.feEmitir = false;
                this.feError = '';
            },

            // Mismas reglas que la emision, antes de cobrar: despues la venta ya
            // queda a nombre de ese cliente.
            async feValidarAntesDeCobrar() {
                this.feError = '';
                if (!this.feSolicitada()) return true;
                if (!this.isOnline) {
                    this.feError = 'Sin conexion no se puede emitir la factura electronica. Desmarque la opcion o espere la conexion.';
                    return false;
                }
                try {
                    const response = await fetch('/ventas/pos/factura-electronica/validar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id_cliente: this.clienteId, total: this.total }),
                    });
                    const data = await response.json().catch(() => ({}));
                    if (response.ok && data.ok) return true;
                    this.feError = data.mensaje || 'No se puede facturar esta venta.';
                } catch (e) {
                    this.feError = 'No se pudo validar la factura electronica. Revise la conexion.';
                }
                return false;
            },

            async feEstadoEmitido(idVenta) {
                try {
                    const response = await fetch(`/facturacion-electronica/estado-pos/${idVenta}`, { cache: 'no-store' });
                    const data = await response.json().catch(() => ({}));
                    if (response.ok && data.success) return data;
                } catch (e) {
                    // sin red: se cae al ticket
                }
                return null;
            },

            imprimirKude(kudeUrl) {
                const sep = kudeUrl.includes('?') ? '&' : '?';
                // preview=1 apaga el auto-print del KuDE: lo imprime el iframe del POS.
                return this.imprimirDocumentoEnFrame(`${kudeUrl}${sep}preview=1&_=${Date.now()}`, kudeUrl);
            },

            // --- Progreso visible mientras se emite (si no, la pantalla parece colgada) ---
            feEtapas: [
                { key: 'venta', label: 'Registrando la venta' },
                { key: 'factura', label: 'Generando y firmando la factura electronica' },
                { key: 'imprimir', label: 'Abriendo el comprobante para imprimir' },
            ],
            feProgreso: { visible: false, error: false, segundos: 0, estados: {}, detalles: {} },
            feProgresoTimer: null,

            feEstadoEtapa(key) {
                return this.feProgreso.estados[key] || 'pendiente';
            },

            feEtapa(key, estado, detalle = '') {
                this.feProgreso.estados = { ...this.feProgreso.estados, [key]: estado };
                this.feProgreso.detalles = { ...this.feProgreso.detalles, [key]: detalle };
                if (estado === 'error') this.feProgreso.error = true;
            },

            feProgresoAbrir() {
                clearInterval(this.feProgresoTimer);
                const inicio = Date.now();
                this.feProgreso = { visible: true, error: false, segundos: 0, estados: {}, detalles: {} };
                this.feProgresoTimer = setInterval(() => {
                    this.feProgreso.segundos = Math.floor((Date.now() - inicio) / 1000);
                }, 500);
            },

            feProgresoCerrar() {
                clearInterval(this.feProgresoTimer);
                this.feProgresoTimer = null;
                this.feProgreso.visible = false;
            },

            async feImprimirConProgreso(antesDeImprimir, detalle, imprimir) {
                if (!this.feProgreso.error) this.feEtapa('factura', 'ok');
                this.feEtapa('imprimir', 'activa', detalle);
                antesDeImprimir();
                try {
                    return await imprimir();
                } finally {
                    this.feProgresoCerrar();
                }
            },

            // Devuelve si se pudo abrir la impresion (KuDE o, si fallo, el ticket).
            async feEmitirEImprimir(idVenta, antesDeImprimir = () => {}) {
                const timeoutMs = Number(this.feConfig && this.feConfig.timeout_ms) || 110000;
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeoutMs);
                let detalle = 'no se pudo emitir la factura electronica.';
                this.feProgresoAbrir();
                this.feEtapa('venta', 'ok', `Venta #${idVenta} registrada`);
                this.feEtapa('factura', 'activa');
                try {
                    const response = await fetch(`/facturacion-electronica/emitir-pos/${idVenta}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        signal: controller.signal,
                    });
                    const data = await response.json().catch(() => ({}));
                    if (response.ok && data.success && data.kude_url) {
                        return await this.feImprimirConProgreso(antesDeImprimir, 'Factura (KuDE)',
                            () => this.imprimirKude(data.kude_url));
                    }
                    if (data.error) detalle = data.error;
                } catch (e) {
                    detalle = e && e.name === 'AbortError'
                        ? 'la factura electronica tardo demasiado en responder.'
                        : 'fallo la factura electronica.';
                } finally {
                    clearTimeout(timer);
                }
                const recuperado = await this.feEstadoEmitido(idVenta);
                if (recuperado && recuperado.kude_url) {
                    return await this.feImprimirConProgreso(antesDeImprimir, 'Factura (KuDE)',
                        () => this.imprimirKude(recuperado.kude_url));
                }
                this.feEtapa('factura', 'error', detalle);
                mostrarNotificacion(`Venta #${idVenta} cobrada, pero ${detalle} Se imprime el ticket normal; la factura se reintenta sola.`, 'warning');
                // Que se alcance a leer el motivo antes del dialogo de impresion.
                await new Promise((resolve) => setTimeout(resolve, 1800));
                return await this.feImprimirConProgreso(antesDeImprimir, 'Ticket normal',
                    () => this.imprimirTicketVenta(idVenta));
            },

