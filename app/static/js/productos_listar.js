function productosApp(config) {
    const initialConfig = config || {};

    return {
        modalAjuste: {
            visible: false,
            idProducto: null,
            nombre: '',
            stockActual: 0,
            tipo: 'entrada',
            cantidad: 1,
            motivo: '',
            observaciones: ''
        },
        modalHistorial: {
            visible: false,
            idProducto: null,
            nombre: '',
            codigo: '',
            historial: [],
            cargando: false,
            error: ''
        },
        guardando: false,
        busqueda: initialConfig.buscar || '',
        categoriaSeleccionada: initialConfig.categoriaId || '',
        autoBusquedaHabilitada: true,

        init() {
            try {
                this.autoBusquedaHabilitada = window.localStorage.getItem('productos_auto_busqueda') !== 'false';
            } catch (error) {}
        },

        guardarPreferenciaAutoBusqueda() {
            try {
                window.localStorage.setItem('productos_auto_busqueda', this.autoBusquedaHabilitada ? 'true' : 'false');
            } catch (error) {}
        },

        manejarInputBusqueda() {
            if (!this.autoBusquedaHabilitada || !this.$refs.filtrosForm) return;
            this.$refs.filtrosForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        },

        limpiarBusqueda(form) {
            this.busqueda = '';
            this.$nextTick(() => {
                if (form) {
                    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                }
            });
        },

        abrirModalAjuste(id, nombre, stock) {
            this.modalAjuste = {
                visible: true,
                idProducto: id,
                nombre: nombre,
                stockActual: stock,
                tipo: 'entrada',
                cantidad: 1,
                motivo: '',
                observaciones: ''
            };
        },

        cerrarModalAjuste() {
            this.modalAjuste.visible = false;
        },

        async abrirModalHistorial(id, nombre, codigo) {
            this.modalHistorial = {
                visible: true,
                idProducto: id,
                nombre: nombre,
                codigo: codigo,
                historial: [],
                cargando: true,
                error: ''
            };

            try {
                const response = await fetch(`/productos/${id}/historial_compras`);
                const data = await response.json().catch(() => ({}));

                if (!response.ok) {
                    this.modalHistorial.error = data.error || 'No se pudo cargar el historial.';
                    return;
                }

                this.modalHistorial.historial = Array.isArray(data.historial) ? data.historial : [];
            } catch (error) {
                console.error('Error cargando historial:', error);
                this.modalHistorial.error = 'Error de conexion al cargar el historial.';
            } finally {
                this.modalHistorial.cargando = false;
            }
        },

        cerrarModalHistorial() {
            this.modalHistorial.visible = false;
        },

        async togglePublicacionTienda(idProducto, publicadoActual) {
            const response = await fetch(`/api/tienda/admin/producto/${idProducto}/publicar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ publicar: !publicadoActual })
            });
            if (!response.ok) {
                alert('No se pudo actualizar la publicacion en tienda');
                return;
            }
            location.reload();
        },

        async guardarAjuste() {
            if (!this.modalAjuste.motivo) {
                alert('Debe seleccionar un motivo');
                return;
            }

            if (this.modalAjuste.cantidad <= 0) {
                alert('La cantidad debe ser mayor a 0');
                return;
            }

            this.guardando = true;

            try {
                const response = await fetch(`/productos/${this.modalAjuste.idProducto}/ajuste_rapido`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        tipo: this.modalAjuste.tipo,
                        cantidad: this.modalAjuste.cantidad,
                        motivo: this.modalAjuste.motivo,
                        observaciones: this.modalAjuste.observaciones
                    })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    const tipoTexto = this.modalAjuste.tipo === 'entrada' ? 'agregadas' : 'retiradas';
                    alert(`${this.modalAjuste.cantidad} unidades ${tipoTexto}. Stock nuevo: ${data.stock_nuevo}`);
                    location.reload();
                } else {
                    alert('Error: ' + (data.error || 'No se pudo guardar el ajuste'));
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error de conexion al guardar el ajuste');
            } finally {
                this.guardando = false;
            }
        }
    };
}
