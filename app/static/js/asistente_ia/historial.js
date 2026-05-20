(function () {
    const historialLista = document.getElementById('ia-historial-lista');
    const historialDetalle = document.getElementById('ia-historial-detalle');
    const historialEstado = document.getElementById('ia-historial-detalle-estado');
    const historialDetalleLink = document.getElementById('ia-historial-detalle-link');
    const historialPage = document.getElementById('ia-historial-page');
    const historialPages = document.getElementById('ia-historial-pages');
    const historialTotal = document.getElementById('ia-historial-total');
    const historialPerPage = document.getElementById('ia-historial-per-page');
    const historialPrev = document.getElementById('ia-historial-prev');
    const historialNext = document.getElementById('ia-historial-next');
    const historialForm = document.getElementById('ia-historial-filtros');
    const historialQ = document.getElementById('ia-historial-q');
    const historialUsername = document.getElementById('ia-historial-username');
    if (!historialLista || !historialDetalle) return;

    const historialState = {
        page: 1,
        total: 0,
        perPage: 20,
        pages: 1,
        controller: null,
        selectedId: null,
        items: [],
    };

    async function getJson(url) {
        const response = await fetch(url, {
            headers: {
                Accept: 'application/json',
            },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.mensaje || 'No se pudo cargar la informacion.');
        }
        return data;
    }

    function formatNumber(value) {
        const number = Number(value || 0);
        return number.toLocaleString('es-PY');
    }

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function prettyJson(value) {
        if (value === null || value === undefined || value === '') return '';
        try {
            return JSON.stringify(value, null, 2);
        } catch (error) {
            return String(value);
        }
    }

    function interactionUrl(id) {
        return `/asistente-ia/historial/${id}`;
    }

    function setDetalleLink(id) {
        if (!historialDetalleLink) return;
        if (!id) {
            historialDetalleLink.classList.add('hidden');
            historialDetalleLink.setAttribute('href', '#');
            return;
        }
        historialDetalleLink.classList.remove('hidden');
        historialDetalleLink.setAttribute('href', interactionUrl(id));
    }

    function resetDetalle(message) {
        historialState.selectedId = null;
        historialEstado.textContent = 'Sin seleccionar';
        historialDetalle.innerHTML = `
            <p class="text-sm text-gray-500 dark:text-gray-400">${escapeHtml(
                message || 'Selecciona una consulta del historial para ver el contenido completo.'
            )}</p>
        `;
        setDetalleLink(null);
        updateSelectedState();
    }

    function updateSelectedState() {
        historialLista.querySelectorAll('.ia-historial-item').forEach((button) => {
            const active = String(button.dataset.id || '') === String(historialState.selectedId || '');
            button.classList.toggle('border-blue-500', active);
            button.classList.toggle('bg-blue-50', active);
            button.classList.toggle('dark:border-blue-500', active);
            button.classList.toggle('dark:bg-blue-950/30', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
    }

    function renderHistorial(items) {
        const rows = Array.isArray(items) ? items : [];
        if (!rows.length) {
            historialLista.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">No hay consultas para mostrar.</p>';
            return;
        }
        historialLista.innerHTML = rows.map((item) => `
            <button type="button"
                    class="ia-historial-item w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-left hover:bg-gray-100 transition dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-700"
                    data-id="${item.id_audit}">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                        <p class="truncate text-sm font-semibold text-gray-800 dark:text-gray-100">${escapeHtml(item.username || 'Sin usuario')}</p>
                        <p class="mt-1 line-clamp-2 text-xs text-gray-600 dark:text-gray-300">${escapeHtml(item.pregunta_preview || '')}</p>
                    </div>
                    <div class="shrink-0 text-right">
                        <p class="text-xs font-semibold text-gray-700 dark:text-gray-200">${formatNumber(item.tokens_total || 0)}</p>
                        <p class="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            P ${formatNumber(item.tokens_prompt || 0)} / R ${formatNumber(item.tokens_completion || 0)}
                        </p>
                        <p class="mt-1 text-[11px] text-gray-500 dark:text-gray-400">${escapeHtml(item.estado || '')} | ${formatNumber(item.tools_count || 0)} tools</p>
                    </div>
                </div>
            </button>
        `).join('');
        historialLista.querySelectorAll('.ia-historial-item').forEach((button) => {
            button.addEventListener('click', () => loadHistorialDetalle(button.dataset.id));
        });
        updateSelectedState();
    }

    function pageWindow(current, total) {
        const pages = new Set([1, total, current - 1, current, current + 1]);
        return Array.from(pages)
            .filter((page) => page >= 1 && page <= total)
            .sort((a, b) => a - b);
    }

    function renderDetalle(item) {
        historialEstado.textContent = item.estado || 'ok';
        historialState.selectedId = item.id_audit || null;
        setDetalleLink(item.id_audit || null);
        updateSelectedState();
        const tools = Array.isArray(item.tools_usadas) && item.tools_usadas.length
            ? item.tools_usadas.join(', ')
            : 'Sin tools';
        const argumentosNormalizados = prettyJson(item.argumentos_normalizados);
        const resultadoResumido = String(item.resultado_resumido || '').trim();
        historialDetalle.innerHTML = `
            <div class="grid gap-2 text-xs text-gray-500 dark:text-gray-400 lg:grid-cols-3">
                <p>Usuario: <span class="font-semibold text-gray-700 dark:text-gray-200">${escapeHtml(item.username || 'Sin usuario')}</span></p>
                <p>Fecha: <span class="font-semibold text-gray-700 dark:text-gray-200">${escapeHtml(item.fecha_hora || '')}</span></p>
                <p>Modelo: <span class="font-semibold text-gray-700 dark:text-gray-200">${escapeHtml(item.modelo || '')}</span></p>
                <p>Provider: <span class="font-semibold text-gray-700 dark:text-gray-200">${escapeHtml(item.provider || '')}</span></p>
                <p>Estado: <span class="font-semibold text-gray-700 dark:text-gray-200">${escapeHtml(item.estado || 'ok')}</span></p>
                <p>Tokens total: <span class="font-semibold text-gray-700 dark:text-gray-200">${formatNumber(item.tokens_total || 0)}</span></p>
                <p>Prompt: <span class="font-semibold text-gray-700 dark:text-gray-200">${formatNumber(item.tokens_prompt || 0)}</span></p>
                <p>Respuesta: <span class="font-semibold text-gray-700 dark:text-gray-200">${formatNumber(item.tokens_completion || 0)}</span></p>
            </div>
            <div>
                <div class="mb-1 flex items-center justify-between gap-2">
                    <h3 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Pregunta</h3>
                    <span class="text-[11px] text-gray-400 dark:text-gray-500">${formatNumber((item.pregunta || '').length)} caracteres</span>
                </div>
                <pre class="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 text-sm text-gray-800 dark:bg-gray-900 dark:text-gray-100">${escapeHtml(item.pregunta || '')}</pre>
            </div>
            <div>
                <div class="mb-1 flex items-center justify-between gap-2">
                    <h3 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Respuesta completa</h3>
                    <span class="text-[11px] text-gray-400 dark:text-gray-500">${formatNumber((item.respuesta || '').length)} caracteres</span>
                </div>
                <pre class="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 text-sm text-gray-800 dark:bg-gray-900 dark:text-gray-100">${escapeHtml(item.respuesta || '')}</pre>
            </div>
            ${resultadoResumido ? `
                <div>
                    <h3 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Resumen tecnico</h3>
                    <pre class="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">${escapeHtml(resultadoResumido)}</pre>
                </div>
            ` : ''}
            <div>
                <h3 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Tools usadas</h3>
                <pre class="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 text-sm text-gray-800 dark:bg-gray-900 dark:text-gray-100">${escapeHtml(tools)}</pre>
            </div>
            ${argumentosNormalizados ? `
                <div>
                    <h3 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Argumentos normalizados</h3>
                    <pre class="mt-1 overflow-x-auto whitespace-pre rounded-lg bg-gray-50 p-3 text-xs text-gray-800 dark:bg-gray-900 dark:text-gray-100">${escapeHtml(argumentosNormalizados)}</pre>
                </div>
            ` : ''}
        `;
    }

    function updatePaginacion() {
        const total = Number(historialState.total || 0);
        const pages = Math.max(1, Math.ceil(total / historialState.perPage));
        historialState.pages = pages;
        const desde = total ? ((historialState.page - 1) * historialState.perPage) + 1 : 0;
        const hasta = Math.min(historialState.page * historialState.perPage, total);
        historialPage.textContent = `Pagina ${historialState.page} de ${pages}`;
        if (historialTotal) {
            historialTotal.textContent = total ? `Mostrando ${desde}-${hasta} de ${formatNumber(total)} consultas` : 'Sin resultados';
        }
        historialPrev.disabled = historialState.page <= 1;
        historialNext.disabled = historialState.page >= pages;
        if (!historialPages) return;
        let previous = 0;
        historialPages.innerHTML = pageWindow(historialState.page, pages).map((page) => {
            const gap = previous && page - previous > 1 ? '<span class="px-1 text-xs text-gray-400">...</span>' : '';
            previous = page;
            const active = page === historialState.page;
            return `${gap}<button type="button"
                        class="ia-historial-page-btn inline-flex h-8 min-w-8 items-center justify-center rounded-lg border px-2 text-xs font-semibold transition ${active ? 'border-blue-600 bg-blue-600 text-white' : 'border-gray-300 text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-700'}"
                        data-page="${page}">${page}</button>`;
        }).join('');
        historialPages.querySelectorAll('.ia-historial-page-btn').forEach((button) => {
            button.addEventListener('click', () => {
                const page = Number(button.dataset.page || 1);
                if (page === historialState.page) return;
                historialState.page = page;
                loadHistorial();
            });
        });
    }

    function loadHistorial() {
        if (historialState.controller) {
            historialState.controller.abort();
        }
        historialState.controller = new AbortController();
        const q = encodeURIComponent(historialQ ? historialQ.value.trim() : '');
        const username = encodeURIComponent(historialUsername ? historialUsername.value.trim() : '');
        historialLista.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">Cargando historial...</p>';
        const url = `/asistente-ia/api/historial?page=${historialState.page}&per_page=${historialState.perPage}&q=${q}&username=${username}`;
        fetch(url, { headers: { Accept: 'application/json' }, signal: historialState.controller.signal })
            .then(async (response) => {
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.mensaje || 'No se pudo cargar la informacion.');
                return data;
            })
            .then((data) => {
                historialState.total = Number(data.total || 0);
                historialState.perPage = Number(data.per_page || 20);
                historialState.items = Array.isArray(data.items) ? data.items : [];
                renderHistorial(historialState.items);
                updatePaginacion();
                if (!historialState.items.length) {
                    resetDetalle('No hay consultas para mostrar con los filtros actuales.');
                    return;
                }
                const selectedVisible = historialState.items.some(
                    (item) => String(item.id_audit) === String(historialState.selectedId || '')
                );
                const nextId = selectedVisible
                    ? historialState.selectedId
                    : historialState.items[0].id_audit;
                if (nextId) {
                    loadHistorialDetalle(nextId, { fromListReload: true });
                }
            })
            .catch((error) => {
                if (error.name === 'AbortError') return;
                historialLista.innerHTML = `<p class="text-sm text-red-600 dark:text-red-300">${escapeHtml(error.message)}</p>`;
                resetDetalle('No se pudo cargar el detalle.');
            });
    }

    function loadHistorialDetalle(id, options) {
        const settings = options || {};
        historialState.selectedId = id;
        updateSelectedState();
        setDetalleLink(id);
        historialEstado.textContent = 'Cargando...';
        historialDetalle.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">Cargando detalle...</p>';
        getJson(`/asistente-ia/api/historial/${id}`)
            .then((data) => {
                renderDetalle(data.item || {});
                if (!settings.fromListReload) {
                    const card = historialLista.querySelector(`.ia-historial-item[data-id="${id}"]`);
                    if (card && typeof card.scrollIntoView === 'function') {
                        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    }
                }
            })
            .catch((error) => {
                historialEstado.textContent = 'Error';
                historialDetalle.innerHTML = `<p class="text-sm text-red-600 dark:text-red-300">${escapeHtml(error.message)}</p>`;
            });
    }

    historialForm.addEventListener('submit', (event) => {
        event.preventDefault();
        historialState.page = 1;
        loadHistorial();
    });
    historialPrev.addEventListener('click', () => {
        if (historialState.page <= 1) return;
        historialState.page -= 1;
        loadHistorial();
    });
    historialNext.addEventListener('click', () => {
        if (historialState.page >= historialState.pages) return;
        historialState.page += 1;
        loadHistorial();
    });
    if (historialPerPage) {
        historialPerPage.addEventListener('change', () => {
            historialState.perPage = Number(historialPerPage.value || 20);
            historialState.page = 1;
            loadHistorial();
        });
    }

    loadHistorial();
})();
