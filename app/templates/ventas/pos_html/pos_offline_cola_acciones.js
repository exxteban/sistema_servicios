// Acciones de la cola offline (consultar, reintentar, descartar) y timeouts de los
// envíos directos del POS. Se aplica sobre posApp después de pos_offline_resilience.js,
// del que usa fetchResponseConTimeout / fetchJsonConTimeout / sincronizarVentasPendientes.
(function () {
    const originalPosApp = window.posApp;
    if (typeof originalPosApp !== 'function') return;

    const { PROCESAR_TIMEOUT_MS, ENVIAR_CAJA_TIMEOUT_MS, now } = window.POSOfflineColaDB;

    // Firma del pedido enviado a caja sin su client_request_id. Si coincide con un
    // envío anterior que quedó sin respuesta, el body sale con aquel id.
    function reusarIdEnvioCaja(init, sinConfirmar) {
        if (!init || typeof init.body !== 'string') return { init, firma: '', id: '' };
        let payload;
        try {
            payload = JSON.parse(init.body);
        } catch (e) {
            return { init, firma: '', id: '' };
        }
        const { client_request_id: idOriginal, ...resto } = payload || {};
        const firma = JSON.stringify(resto);
        const id = (sinConfirmar && sinConfirmar.firma === firma && sinConfirmar.id) ? sinConfirmar.id : idOriginal;
        if (!id || id === idOriginal) return { init, firma, id: idOriginal || '' };
        return { init: { ...init, body: JSON.stringify({ ...payload, client_request_id: id }) }, firma, id };
    }

    window.POSOfflineColaAcciones = { reusarIdEnvioCaja };

    window.posApp = function posAppOfflineColaAcciones() {
        const app = originalPosApp();
        if (!app || typeof app !== 'object') return app;
        app._envioCajaSinConfirmar = null;

        app.consultarVentaYaRegistrada = async function consultarVentaYaRegistrada(clientRequestId) {
            const id = String(clientRequestId || '').trim();
            if (!id) return null;
            try {
                const { response, data } = await this.fetchJsonConTimeout(`/ventas/sync-status/${encodeURIComponent(id)}`, {}, {
                    timeoutMs: 5000,
                    slowMs: 1500,
                    markSlow: false,
                });
                if (response.ok && data && data.success && data.exists) return data;
            } catch (e) {
            }
            return null;
        };

        app.ventaPendienteEsDescartable = function ventaPendienteEsDescartable(venta) {
            // Solo se puede descartar manualmente una venta detenida por error permanente,
            // nunca una que todavia se va a reintentar sola (asi no se pierde nada por error).
            return String((venta && venta.estado_sync) || 'pendiente') === 'error';
        };

        app.reintentarVentaPendiente = function reintentarVentaPendiente(clientRequestId) {
            const id = String(clientRequestId || '').trim();
            const venta = (this.ventasPendientes || []).find(v => v.client_request_id === id);
            if (venta) {
                venta.estado_sync = 'pendiente';
                venta.ultimo_error = '';
                venta.updated_at = now();
                this.guardarVentasPendientes();
            }
            return this.sincronizarVentasPendientes();
        };

        app.descartarVentaPendiente = function descartarVentaPendiente(clientRequestId) {
            const id = String(clientRequestId || '').trim();
            if (!id) return;
            const venta = (this.ventasPendientes || []).find(v => v.client_request_id === id);
            if (!venta) return;
            if (!this.ventaPendienteEsDescartable(venta)) {
                mostrarNotificacion('Solo se pueden descartar ventas detenidas por error. Esta se reintentara sola.', 'warning');
                return;
            }
            const total = (typeof this.formatNumber === 'function') ? this.formatNumber(this.totalVentaPendiente(venta)) : this.totalVentaPendiente(venta);
            const confirmar = window.confirm(
                '¿Descartar definitivamente esta venta en cola?\n\n' +
                `Total: ₲ ${total}\n` +
                `Motivo del error: ${venta.ultimo_error || 'desconocido'}\n\n` +
                'Esta accion NO se puede deshacer. Solo hacelo si confirmaste que la venta no debe registrarse.'
            );
            if (!confirmar) return;
            this.ventasPendientes = (this.ventasPendientes || []).filter(v => v.client_request_id !== id);
            this.guardarVentasPendientes();
            if (!this.ventasPendientes.some(v => (v.estado_sync || '') === 'error')) {
                this.ultimaSincronizacionError = '';
            }
            mostrarNotificacion('Venta descartada de la cola local', 'info');
        };

        const originalEjecutarVenta = app.ejecutarVenta;
        if (typeof originalEjecutarVenta === 'function') {
            app.ejecutarVenta = async function ejecutarVentaConTimeout(...args) {
                const originalFetch = window.fetch;
                const self = this;
                window.fetch = function fetchPosConTimeout(input, init) {
                    if (String(input || '').includes('/ventas/procesar')) {
                        return self.fetchResponseConTimeout(input, init, { timeoutMs: PROCESAR_TIMEOUT_MS, slowMs: 1800 }, originalFetch.bind(this));
                    }
                    return originalFetch.call(this, input, init);
                };
                try {
                    return await originalEjecutarVenta.apply(this, args);
                } finally {
                    window.fetch = originalFetch;
                }
            };
        }

        const originalEnviarVentaACaja = app.enviarVentaACaja;
        if (typeof originalEnviarVentaACaja === 'function') {
            app.enviarVentaACaja = async function enviarVentaACajaConTimeout(...args) {
                const originalFetch = window.fetch;
                const self = this;
                window.fetch = async function fetchCajaConTimeout(input, init) {
                    if (!String(input || '').includes('/ventas/enviar-a-caja')) {
                        return originalFetch.call(this, input, init);
                    }
                    const envio = reusarIdEnvioCaja(init, self._envioCajaSinConfirmar);
                    try {
                        const response = await self.fetchResponseConTimeout(input, envio.init, { timeoutMs: ENVIAR_CAJA_TIMEOUT_MS, slowMs: 1500 }, originalFetch.bind(this));
                        // Hubo respuesta: el servidor ya decidió sobre este envío.
                        self._envioCajaSinConfirmar = null;
                        return response;
                    } catch (error) {
                        // Sin respuesta (timeout/corte): el pendiente pudo haberse creado.
                        // Si el mozo reintenta con el mismo pedido, se reusa el id y el
                        // servidor devuelve el pendiente existente en vez de duplicarlo.
                        if (envio.firma) self._envioCajaSinConfirmar = { firma: envio.firma, id: envio.id };
                        throw error;
                    }
                };
                try {
                    return await originalEnviarVentaACaja.apply(this, args);
                } finally {
                    window.fetch = originalFetch;
                }
            };
        }

        return app;
    };
})();
