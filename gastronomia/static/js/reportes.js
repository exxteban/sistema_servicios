(function () {
  const alertBox = document.getElementById('report-alert');
  const kpis = document.getElementById('report-kpis');
  const topProducts = document.getElementById('top-products');
  const salesMethods = document.getElementById('sales-methods');
  const voidableSales = document.getElementById('voidable-sales');
  const fromInput = document.getElementById('report-from');
  const toInput = document.getElementById('report-to');
  const csrf = document.getElementById('csrf-token')?.value || '';

  const today = new Date().toISOString().slice(0, 10);
  fromInput.value = today;
  toInput.value = today;

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const apiJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {})},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
    return data;
  };
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));

  const loadReport = async () => {
    const params = new URLSearchParams({desde: fromInput.value, hasta: toInput.value});
    const data = await apiJson(`/api/gastronomia/reportes/resumen?${params.toString()}`);
    render(data.resumen || {});
  };
  const render = (summary) => {
    renderKpis(summary);
    renderProducts(summary.productos_mas_vendidos || []);
    renderMethods(summary.ventas_por_metodo || []);
    renderVoidableSales(summary.ventas_anulables || []);
  };
  const renderKpis = (summary) => {
    const items = [
      ['Ventas', money(summary.ventas_total), 'Total cobrado'],
      ['Pedidos', summary.pedidos_cobrados || 0, 'Pedidos cobrados'],
      ['Ticket promedio', money(summary.ticket_promedio), 'Promedio por pedido'],
      ['Preparacion', `${summary.tiempo_promedio_preparacion_min || 0} min`, 'Tiempo promedio'],
      ['Anulados', summary.pedidos_cancelados || 0, 'Pedidos cancelados'],
    ];
    kpis.innerHTML = items.map(([title, value, note]) => `
      <article class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <p class="text-sm font-semibold text-gray-500">${escapeHtml(note)}</p>
        <h2 class="mt-2 text-2xl font-black text-gray-900 dark:text-white">${escapeHtml(value)}</h2>
        <p class="mt-1 text-sm font-bold text-violet-600 dark:text-violet-300">${escapeHtml(title)}</p>
      </article>
    `).join('');
  };
  const renderProducts = (items) => {
    topProducts.innerHTML = items.map((item) => `
      <div class="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-3 dark:bg-gray-900/40">
        <div>
          <strong class="text-gray-900 dark:text-white">${escapeHtml(item.nombre_producto)}</strong>
          <p class="text-sm text-gray-500">${item.cantidad} unidades</p>
        </div>
        <span class="font-black text-emerald-700 dark:text-emerald-300">${money(item.total)}</span>
      </div>
    `).join('') || '<div class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">Sin ventas en el periodo.</div>';
  };
  const renderMethods = (items) => {
    salesMethods.innerHTML = items.map((item) => `
      <div class="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-3 dark:bg-gray-900/40">
        <div>
          <strong class="capitalize text-gray-900 dark:text-white">${escapeHtml(item.metodo_pago)}</strong>
          <p class="text-sm text-gray-500">${item.cantidad} pagos</p>
        </div>
        <span class="font-black text-emerald-700 dark:text-emerald-300">${money(item.total)}</span>
      </div>
    `).join('') || '<div class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">Sin cobros en el periodo.</div>';
  };
  const renderVoidableSales = (items) => {
    if (!voidableSales) return;
    voidableSales.innerHTML = items.map((item) => `
      <div class="grid gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/40 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <strong class="text-gray-900 dark:text-white">${escapeHtml(item.codigo_entrega || `#${item.id_pedido}`)}</strong>
            <span class="rounded-full bg-white px-2 py-1 text-xs font-black uppercase tracking-wide text-gray-500 dark:bg-gray-800 dark:text-gray-300">Venta #${escapeHtml(item.id_venta)}</span>
            <span class="rounded-full bg-emerald-50 px-2 py-1 text-xs font-black uppercase tracking-wide text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-200">${escapeHtml(item.metodo_pago)}</span>
          </div>
          <p class="mt-1 text-sm font-semibold text-gray-600 dark:text-gray-300">${escapeHtml(saleLabel(item))}</p>
          <p class="mt-1 text-xs font-semibold text-gray-500">${escapeHtml(formatDateTime(item.fecha_pago))} - Estado ${escapeHtml(item.estado_pedido)}</p>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center md:justify-end">
          <strong class="text-lg text-gray-900 dark:text-white">${money(item.total_cobrado)}</strong>
          <button type="button" data-void-sale="${item.id_pedido}" data-venta-id="${item.id_venta}" class="rounded-lg bg-rose-600 px-3 py-2 text-sm font-black text-white hover:bg-rose-700" data-permiso="anular_venta">
            Anular venta
          </button>
        </div>
      </div>
    `).join('') || '<div class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">No hay ventas cobradas para anular en el periodo.</div>';
    if (window.aplicarPermisosUI) window.aplicarPermisosUI();
  };
  const saleLabel = (item) => {
    const parts = [item.tipo_pedido || 'mostrador'];
    if (item.mesa) parts.push(`Mesa ${item.mesa}`);
    if (item.referencia_entrega) parts.push(item.referencia_entrega);
    return parts.join(' - ');
  };
  const formatDateTime = (value) => {
    if (!value) return 'Sin fecha';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('es-PY', {dateStyle: 'short', timeStyle: 'short'});
  };
  const voidSale = async (pedidoId, ventaId) => {
    if (!window.confirm(`Anular la venta #${ventaId}? Se restaurara stock y se reversara caja.`)) return;
    const runAuthorized = window.ejecutarConAutorizacion || ((_permiso, _accion, callback) => callback(null));
    await runAuthorized(
      'anular_venta',
      `Anular venta gastronomia #${ventaId}`,
      async (idAutorizacion) => {
        await apiJson(`/api/gastronomia/reportes/pedidos/${pedidoId}/anular-venta`, {
          method: 'POST',
          body: JSON.stringify({id_autorizacion: idAutorizacion || null}),
        });
        showAlert(`Venta #${ventaId} anulada correctamente.`, true);
        await loadReport();
      },
      'venta',
      ventaId
    );
  };

  document.getElementById('load-report')?.addEventListener('click', () => {
    loadReport().catch((error) => showAlert(error.message, false));
  });
  voidableSales?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-void-sale]');
    if (!button) return;
    voidSale(Number(button.dataset.voidSale), Number(button.dataset.ventaId))
      .catch((error) => showAlert(error.message, false));
  });
  loadReport().catch((error) => showAlert(error.message, false));
}());
