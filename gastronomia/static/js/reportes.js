(function () {
  const alertBox = document.getElementById('report-alert');
  const kpis = document.getElementById('report-kpis');
  const topProducts = document.getElementById('top-products');
  const salesMethods = document.getElementById('sales-methods');
  const fromInput = document.getElementById('report-from');
  const toInput = document.getElementById('report-to');

  const today = new Date().toISOString().slice(0, 10);
  fromInput.value = today;
  toInput.value = today;

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const apiJson = async (url) => {
    const response = await fetch(url);
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
  };
  const renderKpis = (summary) => {
    const items = [
      ['Ventas', money(summary.ventas_total), 'Total cobrado'],
      ['Pedidos', summary.pedidos_cobrados || 0, 'Pedidos cobrados'],
      ['Ticket promedio', money(summary.ticket_promedio), 'Promedio por pedido'],
      ['Preparacion', `${summary.tiempo_promedio_preparacion_min || 0} min`, 'Tiempo promedio'],
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

  document.getElementById('load-report')?.addEventListener('click', () => {
    loadReport().catch((error) => showAlert(error.message, false));
  });
  loadReport().catch((error) => showAlert(error.message, false));
}());
