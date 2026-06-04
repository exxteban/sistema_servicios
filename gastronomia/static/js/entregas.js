(function () {
  const form = document.getElementById('entregas-filters');
  const summaryEl = document.getElementById('entregas-summary');
  const listEl = document.getElementById('entregas-list');
  const paginationEl = document.getElementById('entregas-pagination');
  const alertBox = document.getElementById('entregas-alert');
  const fechaInput = form?.querySelector('[name="fecha"]');
  const searchInput = form?.querySelector('[name="q"]');
  if (!form || !summaryEl || !listEl || !paginationEl || !alertBox || !fechaInput || !searchInput) return;

  const state = {page: 1, perPage: 8};

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const time = (iso) => {
    if (!iso) return '--:--';
    const match = String(iso).match(/T(\d{2}):(\d{2})/);
    if (match) return `${match[1]}:${match[2]}`;
    return new Date(iso).toLocaleTimeString('es-PY', {hour: '2-digit', minute: '2-digit'});
  };
  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const hideAlert = () => {
    alertBox.className = 'hidden rounded-lg border px-4 py-3 text-sm font-semibold';
    alertBox.textContent = '';
  };
  const params = () => {
    const data = new FormData(form);
    const query = new URLSearchParams();
    for (const [key, value] of data.entries()) {
      if (String(value || '').trim()) query.set(key, value);
    }
    query.set('page', state.page);
    query.set('per_page', state.perPage);
    return query;
  };
  const load = async () => {
    hideAlert();
    const response = await fetch(`/api/gastronomia/entregas?${params().toString()}`, {
      headers: {'Accept': 'application/json'},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudieron cargar las entregas.');
    if (data.fecha) fechaInput.value = data.fecha;
    if (data.paginacion?.pagina) state.page = data.paginacion.pagina;
    renderSummary(data.resumen || {});
    renderOrders(data.pedidos || []);
    renderPagination(data.paginacion || {});
  };
  const renderSummary = (summary) => {
    const cards = [
      ['En historial', summary.cantidad_historial ?? summary.cantidad_entregada ?? 0, 'Pedidos finalizados para la fecha'],
      ['Total vendido', money(summary.total_vendido), 'Suma de pedidos del historial'],
      ['Pagados', summary.cantidad_pagada || 0, money(summary.total_pagado)],
      ['Pendientes', summary.cantidad_pendiente_pago || 0, 'Aun sin pago registrado'],
    ];
    summaryEl.innerHTML = cards.map(([title, value, hint]) => `
      <article class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <p class="text-xs font-black uppercase tracking-wide text-gray-500">${title}</p>
        <strong class="mt-2 block text-3xl font-black text-gray-900 dark:text-white">${value}</strong>
        <span class="mt-1 block text-sm text-gray-500">${hint}</span>
      </article>
    `).join('');
  };
  const renderOrders = (orders) => {
    listEl.innerHTML = orders.map(renderOrder).join('') || `
      <div class="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-800">
        No hay entregas para los filtros seleccionados.
      </div>
    `;
  };
  const renderPagination = (pagination) => {
    const total = Number(pagination.total || 0);
    const page = Number(pagination.pagina || 1);
    const perPage = Number(pagination.por_pagina || state.perPage);
    const pages = Number(pagination.paginas || 1);
    const start = total ? ((page - 1) * perPage) + 1 : 0;
    const end = Math.min(page * perPage, total);
    paginationEl.innerHTML = `
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p class="text-sm font-semibold text-gray-500 dark:text-gray-400">
          Mostrando ${start}-${end} de ${total} entregas
        </p>
        <div class="flex items-center gap-2">
          <button type="button" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}
                  class="rounded-lg border border-gray-200 px-3 py-2 text-sm font-bold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900">
            Anterior
          </button>
          <span class="rounded-lg bg-gray-100 px-3 py-2 text-sm font-black text-gray-700 dark:bg-gray-900 dark:text-gray-200">
            ${page} / ${pages}
          </span>
          <button type="button" data-page="${page + 1}" ${page >= pages ? 'disabled' : ''}
                  class="rounded-lg border border-gray-200 px-3 py-2 text-sm font-bold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900">
            Siguiente
          </button>
        </div>
      </div>
    `;
  };
  const renderOrder = (order) => `
    <article class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-xl font-black text-gray-900 dark:text-white">${escapeHtml(order.codigo_entrega || `#${order.id_pedido}`)}</h2>
            <span class="rounded-full bg-emerald-100 px-2 py-1 text-xs font-bold uppercase text-emerald-800">${escapeHtml(order.estado)}</span>
            <span class="rounded-full ${order.pagado ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800'} px-2 py-1 text-xs font-bold uppercase">${order.pagado ? 'Pagado' : 'Pendiente pago'}</span>
          </div>
          <p class="mt-2 text-sm font-semibold text-gray-500">
            ${time(order.fecha_entrega || (order.pago && order.pago.fecha_pago))} - ${escapeHtml(order.tipo_pedido)}${order.mesa ? ` - Mesa ${escapeHtml(order.mesa)}` : ''}${order.referencia_entrega ? ` - ${escapeHtml(order.referencia_entrega)}` : ''}
          </p>
          <div class="mt-4 flex flex-wrap gap-2">
            ${(order.items || []).map((item) => `
              <span class="rounded-lg bg-gray-100 px-3 py-2 text-sm font-semibold text-gray-700 dark:bg-gray-900 dark:text-gray-200">
                ${item.cantidad} x ${escapeHtml(item.nombre_producto)}
              </span>
            `).join('')}
          </div>
        </div>
        <div class="text-left lg:text-right">
          <strong class="block text-2xl font-black text-emerald-700 dark:text-emerald-300">${money(order.total)}</strong>
          <a href="/gastronomia/pedidos/${order.id_pedido}/ticket?preview=1"
             class="mt-3 inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-bold text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900">
            <i class="fas fa-receipt"></i>Ticket
          </a>
        </div>
      </div>
    </article>
  `;

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    state.page = 1;
    load().catch((error) => showAlert(error.message, false));
  });
  searchInput.addEventListener('input', () => {
    window.clearTimeout(searchInput._timer);
    state.page = 1;
    searchInput._timer = window.setTimeout(() => load().catch((error) => showAlert(error.message, false)), 300);
  });
  paginationEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-page]');
    if (!button || button.disabled) return;
    state.page = Number(button.dataset.page || 1);
    load().catch((error) => showAlert(error.message, false));
  });
  load().catch((error) => showAlert(error.message, false));
}());
