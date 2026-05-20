(function () {
    const originalPosApp = window.posApp;
    if (typeof originalPosApp !== 'function') {
        return;
    }

    window.posApp = function patchedPosApp() {
        const app = originalPosApp();
        if (!app || typeof app !== 'object') {
            return app;
        }

        app.actualizarPreciosSegunCliente = function actualizarPreciosSegunClientePatched(opciones = {}) {
            const esMayorista = this.usaPrecioMayorista();
            const silent = !!(opciones && opciones.silent === true);

            let productosActualizados = 0;
            let productosSinPrecioMayorista = 0;

            for (const item of this.carrito || []) {
                if (item.precio_manual === true || item.precio_opcion_id) continue;
                const precioAnterior = item.precio;

                if (esMayorista) {
                    if (item.precio_mayorista && item.precio_mayorista > 0) {
                        item.precio = item.precio_mayorista;
                    } else {
                        productosSinPrecioMayorista++;
                    }
                } else if (item.precio_base && item.precio_base > 0) {
                    item.precio = item.precio_base;
                }

                if (item.precio !== precioAnterior) {
                    productosActualizados++;
                }
            }

            this.actualizarTotal();

            if (!silent && productosActualizados > 0) {
                const tipoMensaje = esMayorista ? 'Precios mayoristas aplicados' : 'Precios minoristas aplicados';
                mostrarNotificacion(`${tipoMensaje} a ${productosActualizados} producto(s)`, 'info');
            }

            if (!silent && esMayorista && productosSinPrecioMayorista > 0) {
                mostrarNotificacion(`${productosSinPrecioMayorista} producto(s) no tienen precio mayorista definido`, 'warning');
            }
        };

        const originalConstruirPayloadVenta = app.construirPayloadVenta;
        if (typeof originalConstruirPayloadVenta === 'function') {
            app.construirPayloadVenta = function construirPayloadVentaPatched(...args) {
                const payload = originalConstruirPayloadVenta.apply(this, args) || {};
                payload.usar_precio_mayorista = this.usaPrecioMayorista() === true;
                return payload;
            };
        }

        const originalEnviarVentaACaja = app.enviarVentaACaja;
        if (typeof originalEnviarVentaACaja === 'function') {
            app.enviarVentaACaja = async function enviarVentaACajaPatched(...args) {
                const originalFetch = window.fetch;
                const self = this;
                window.fetch = async function patchedFetch(input, init) {
                    try {
                        if (String(input || '').includes('/ventas/enviar-a-caja') && init && typeof init.body === 'string') {
                            const payload = JSON.parse(init.body);
                            payload.usar_precio_mayorista = self.usaPrecioMayorista() === true;
                            init.body = JSON.stringify(payload);
                        }
                    } catch (e) {
                    }
                    return originalFetch.call(this, input, init);
                };
                try {
                    return await originalEnviarVentaACaja.apply(this, args);
                } finally {
                    window.fetch = originalFetch;
                }
            };
        }

        const originalRestaurarEstado = app.restaurarEstado;
        if (typeof originalRestaurarEstado === 'function') {
            app.restaurarEstado = async function restaurarEstadoConPrecioSincronizado(...args) {
                const result = await originalRestaurarEstado.apply(this, args);
                if (this.carrito && this.carrito.length > 0 && typeof this.actualizarPreciosSegunCliente === 'function') {
                    this.actualizarPreciosSegunCliente({ silent: true });
                }
                return result;
            };
        }

        return app;
    };
})();
