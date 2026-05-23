function agendaServicioForm() {
    return {
        clientesUrl: '',
        serviciosUrl: '',
        clienteServiciosUrl: '',
        clienteSeleccionado: null,
        clienteId: '',
        clienteBusqueda: '',
        clientesEncontrados: [],
        mostrarResultadosClientes: false,
        cargandoClientes: false,
        clienteFetchId: 0,
        servicioSeleccionado: null,
        servicioId: '',
        servicioBusqueda: '',
        serviciosEncontrados: [],
        mostrarResultadosServicios: false,
        cargandoServicios: false,
        servicioFetchId: 0,
        servicioPrecioOpcionId: '',
        clienteServicios: [],
        clienteServicioId: '',
        reparacionId: '',
        ventaId: '',
        prioridadSeleccionada: 'media',
        mostrarAgendaEnSeleccionado: 'solo_responsable',
        recordatorioParaSeleccionado: 'solo_responsable',
        tituloManual: false,
        fechaFinAuto: false,

        init() {
            const el = this.$el;
            if (!el || !el.dataset) return;
            this.clientesUrl = el.dataset.clientesUrl || '';
            this.serviciosUrl = el.dataset.serviciosUrl || '';
            this.clienteServiciosUrl = el.dataset.clienteServiciosUrl || '';
            this.clienteSeleccionado = this.parseJson(el.dataset.clienteInicial);
            const clienteServicioInicial = this.parseJson(el.dataset.clienteServicioInicial);
            this.servicioSeleccionado = this.parseJson(el.dataset.servicioInicial);
            const reparacionInicial = this.parseJson(el.dataset.reparacionInicial);
            const ventaInicial = this.parseJson(el.dataset.ventaInicial);

            if (clienteServicioInicial) {
                this.clienteServicioId = clienteServicioInicial.id_cliente_servicio || '';
                if (!this.clienteSeleccionado) this.clienteSeleccionado = clienteServicioInicial.cliente || null;
                if (!this.servicioSeleccionado) this.servicioSeleccionado = clienteServicioInicial.servicio || null;
            }
            this.clienteId = this.clienteSeleccionado ? this.clienteSeleccionado.id_cliente : '';
            this.servicioId = this.servicioSeleccionado ? this.servicioSeleccionado.id_servicio : '';
            this.reparacionId = reparacionInicial ? reparacionInicial.id_reparacion : '';
            this.ventaId = ventaInicial ? ventaInicial.id_venta : '';
            this.mostrarAgendaEnSeleccionado = String(el.dataset.mostrarAgendaEn || 'solo_responsable');
            this.recordatorioParaSeleccionado = String(el.dataset.recordatorioA || 'solo_responsable');

            const prioridadInput = el.querySelector('select[name="prioridad"]');
            this.prioridadSeleccionada = prioridadInput ? String(prioridadInput.value || 'media') : 'media';
            const tituloInput = this.$refs.tituloInput;
            this.tituloManual = Boolean(tituloInput && tituloInput.value.trim());
            if (this.clienteId) this.buscarClienteServicios();
            this.sincronizarTitulo();
            this.sincronizarValidacionRecordatorio();
            ['fechaInicioInput', 'fechaFinInput', 'recordatorioInput'].forEach((ref) => {
                const input = this.$refs[ref];
                if (!input) return;
                input.addEventListener('input', () => this.sincronizarValidacionRecordatorio());
                input.addEventListener('change', () => this.sincronizarValidacionRecordatorio());
            });
        },

        parseJson(raw) {
            try {
                return raw ? JSON.parse(raw) : null;
            } catch (_error) {
                return null;
            }
        },

        detalleCliente(cliente) {
            if (!cliente) return '';
            return [cliente.ruc_ci, cliente.telefono, cliente.email].filter(Boolean).join(' - ') || 'Sin datos extra';
        },

        detalleServicio(servicio) {
            if (!servicio) return '';
            const partes = [];
            if (servicio.categoria) partes.push(servicio.categoria);
            if (servicio.duracion_minutos) partes.push(`${servicio.duracion_minutos} min`);
            partes.push(this.formatearMonto(servicio.precio));
            return partes.filter(Boolean).join(' - ');
        },

        capitalizar(texto) {
            texto = String(texto || '').replace(/_/g, ' ');
            return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : '';
        },

        formatearMonto(valor) {
            return `Gs. ${new Intl.NumberFormat('es-PY').format(Number(valor || 0))}`;
        },

        async manejarBusquedaCliente() {
            const termino = this.clienteBusqueda.trim();
            if (this.clienteSeleccionado && termino !== this.clienteSeleccionado.nombre) {
                this.limpiarCliente({ conservarTexto: true });
            }
            this.mostrarResultadosClientes = true;
            await this.buscarClientes(termino, true);
        },

        async buscarClientes(query = '', abrir = false) {
            if (abrir) this.mostrarResultadosClientes = true;
            const fetchId = ++this.clienteFetchId;
            this.cargandoClientes = true;
            try {
                const url = new URL(this.clientesUrl, window.location.origin);
                if ((query || '').trim()) url.searchParams.set('q', query.trim());
                const response = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
                const data = await response.json();
                if (fetchId === this.clienteFetchId) this.clientesEncontrados = Array.isArray(data.items) ? data.items : [];
            } catch (_error) {
                if (fetchId === this.clienteFetchId) this.clientesEncontrados = [];
            } finally {
                if (fetchId === this.clienteFetchId) this.cargandoClientes = false;
            }
        },

        seleccionarCliente(cliente) {
            this.clienteSeleccionado = cliente;
            this.clienteId = cliente ? cliente.id_cliente : '';
            this.clienteBusqueda = '';
            this.clientesEncontrados = [];
            this.mostrarResultadosClientes = false;
            this.clienteServicioId = '';
            this.buscarClienteServicios();
            this.sincronizarTitulo();
        },

        limpiarCliente(options = {}) {
            this.clienteSeleccionado = null;
            this.clienteId = '';
            if (!options.conservarTexto) this.clienteBusqueda = '';
            this.clienteServicios = [];
            this.clienteServicioId = '';
            this.sincronizarTitulo();
        },

        async manejarBusquedaServicio() {
            const termino = this.servicioBusqueda.trim();
            if (this.servicioSeleccionado && termino !== this.servicioSeleccionado.nombre) {
                this.limpiarServicio({ conservarTexto: true });
            }
            this.mostrarResultadosServicios = true;
            await this.buscarServicios(termino, true);
        },

        async buscarServicios(query = '', abrir = false) {
            if (abrir) this.mostrarResultadosServicios = true;
            const fetchId = ++this.servicioFetchId;
            this.cargandoServicios = true;
            try {
                const url = new URL(this.serviciosUrl, window.location.origin);
                if ((query || '').trim()) url.searchParams.set('q', query.trim());
                const response = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
                const data = await response.json();
                if (fetchId === this.servicioFetchId) this.serviciosEncontrados = Array.isArray(data.items) ? data.items : [];
            } catch (_error) {
                if (fetchId === this.servicioFetchId) this.serviciosEncontrados = [];
            } finally {
                if (fetchId === this.servicioFetchId) this.cargandoServicios = false;
            }
        },

        seleccionarServicio(servicio) {
            this.servicioSeleccionado = servicio;
            this.servicioId = servicio ? servicio.id_servicio : '';
            this.servicioBusqueda = '';
            this.serviciosEncontrados = [];
            this.mostrarResultadosServicios = false;
            this.clienteServicioId = '';
            this.servicioPrecioOpcionId = '';
            this.sincronizarTitulo();
            this.sincronizarFechaFin();
        },

        limpiarServicio(options = {}) {
            this.servicioSeleccionado = null;
            this.servicioId = '';
            this.servicioPrecioOpcionId = '';
            if (!options.conservarTexto) this.servicioBusqueda = '';
            this.sincronizarTitulo();
        },

        get servicioOpciones() {
            const opciones = this.servicioSeleccionado ? this.servicioSeleccionado.opciones : [];
            return Array.isArray(opciones) ? opciones : [];
        },

        async buscarClienteServicios() {
            if (!this.clienteId || !this.clienteServiciosUrl) {
                this.clienteServicios = [];
                return;
            }
            try {
                const url = new URL(this.clienteServiciosUrl, window.location.origin);
                url.searchParams.set('cliente_id', this.clienteId);
                const response = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
                const data = await response.json();
                this.clienteServicios = Array.isArray(data.items) ? data.items : [];
            } catch (_error) {
                this.clienteServicios = [];
            }
        },

        seleccionarClienteServicio(asignacion) {
            this.clienteServicioId = asignacion ? asignacion.id_cliente_servicio : '';
            if (asignacion && asignacion.servicio) this.seleccionarServicio(asignacion.servicio);
            if (asignacion && asignacion.cliente) this.seleccionarCliente(asignacion.cliente);
            this.clienteServicioId = asignacion ? asignacion.id_cliente_servicio : '';
        },

        sincronizarTitulo() {
            const input = this.$refs.tituloInput;
            if (!input || this.tituloManual) return;
            const servicio = this.servicioSeleccionado ? this.servicioSeleccionado.nombre : 'Servicio';
            const cliente = this.clienteSeleccionado ? this.clienteSeleccionado.nombre : '';
            input.value = cliente ? `${servicio} - ${cliente}` : servicio;
        },

        sincronizarFechaFin() {
            const inicioInput = this.$refs.fechaInicioInput;
            const finInput = this.$refs.fechaFinInput;
            if (!inicioInput || !finInput || !inicioInput.value || !this.servicioSeleccionado) return;
            if (finInput.value && !this.fechaFinAuto) return;
            const inicio = new Date(inicioInput.value);
            if (Number.isNaN(inicio.getTime())) return;
            const minutos = Number(this.servicioSeleccionado.duracion_minutos || 30);
            inicio.setMinutes(inicio.getMinutes() + Math.max(minutos, 1));
            finInput.value = this.toDatetimeLocal(inicio);
            this.fechaFinAuto = true;
            this.sincronizarValidacionRecordatorio();
        },

        toDatetimeLocal(date) {
            const pad = (value) => String(value).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
        },

        sincronizarValidacionRecordatorio() {
            const startInput = this.$refs.fechaInicioInput;
            const endInput = this.$refs.fechaFinInput;
            const reminderInput = this.$refs.recordatorioInput;
            const help = this.$refs.recordatorioHelp;
            if (!startInput || !endInput || !reminderInput) return;
            endInput.setCustomValidity('');
            reminderInput.setCustomValidity('');
            reminderInput.removeAttribute('max');
            if (help) help.textContent = '';
            const startDate = startInput.value ? new Date(startInput.value) : null;
            const endDate = endInput.value ? new Date(endInput.value) : null;
            if (!startDate || !endDate || Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return;
            const diffMinutes = Math.floor((endDate.getTime() - startDate.getTime()) / 60000);
            if (diffMinutes <= 0) {
                endInput.setCustomValidity('La fecha fin debe ser posterior al inicio.');
                return;
            }
            const maxReminder = Math.max(0, diffMinutes - 1);
            reminderInput.setAttribute('max', String(maxReminder));
            const reminderValue = reminderInput.value === '' ? null : Number.parseInt(reminderInput.value, 10);
            if (reminderValue !== null && Number.isFinite(reminderValue) && reminderValue >= diffMinutes) {
                reminderInput.setCustomValidity('El recordatorio debe ser menor a la duracion.');
            }
        },
    };
}
