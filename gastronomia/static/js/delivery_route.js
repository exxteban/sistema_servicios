(function () {
  const root = document.querySelector('[data-gastro-delivery-route]');
  const csrf = document.getElementById('csrf-token')?.value || '';
  const ordersBox = document.getElementById('route-orders');
  const summary = document.getElementById('route-summary');
  const alertBox = document.getElementById('route-alert');
  const driverName = document.getElementById('route-driver-name');
  const refreshButton = document.getElementById('route-refresh');
  if (!root || !ordersBox || !summary || !alertBox) return;

  let orders = [];
  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const hideAlert = () => {
    alertBox.className = 'hidden rounded-lg border px-4 py-3 text-sm font-semibold';
    alertBox.textContent = '';
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
  const load = async () => {
    hideAlert();
    const data = await apiJson('/api/gastronomia/delivery/ruta');
    orders = data.pedidos || [];
    driverName.textContent = data.repartidor ? `Ruta de ${data.repartidor.nombre}` : 'Pedidos asignados para entregar.';
    render();
  };
  const render = () => {
    summary.innerHTML = [
      {title: 'Listos para salir', count: orders.filter((order) => order.estado === 'listo').length},
      {title: 'En camino', count: orders.filter((order) => order.estado === 'en_camino').length},
    ].map((item) => `
      <article class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <p class="text-xs font-black uppercase tracking-wide text-gray-500">${item.title}</p>
        <strong class="mt-2 block text-3xl font-black text-gray-900 dark:text-white">${item.count}</strong>
      </article>
    `).join('');
    ordersBox.innerHTML = orders.length ? orders.map(renderOrder).join('') : emptyRoute();
  };
  const renderOrder = (order) => {
    const whatsappUrl = window.GastroWhatsApp?.buildOrderWhatsAppUrl(order, order.celular_cliente) || '';
    const whatsappTarget = escapeHtml(window.GastroWhatsApp?.target || 'gastro-whatsapp');
    return `
      <article class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800" data-order="${order.id_pedido}">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 class="text-2xl font-black text-gray-900 dark:text-white">${escapeHtml(order.codigo_entrega || `#${order.id_pedido}`)}</h2>
            <p class="text-xs font-black uppercase tracking-wide text-orange-600 dark:text-orange-300">${order.estado === 'en_camino' ? 'En camino' : 'Listo para salir'}</p>
          </div>
          <strong class="text-lg font-black text-gray-900 dark:text-white">${money(order.total)}</strong>
        </div>
        <div class="mt-4 grid gap-2 text-sm text-gray-700 dark:text-gray-200">
          <p><strong>Cliente:</strong> ${escapeHtml(order.nombre_cliente || order.referencia_entrega || 'Sin nombre')}</p>
          ${order.celular_cliente ? `<p><strong>Cel:</strong> ${escapeHtml(order.celular_cliente)}</p>` : ''}
          <p><strong>Direccion:</strong> ${escapeHtml(order.direccion_entrega || 'Sin direccion')}</p>
          ${order.notas ? `<p><strong>Notas:</strong> ${escapeHtml(order.notas)}</p>` : ''}
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          ${(order.items || []).map((item) => `<span class="rounded bg-gray-100 px-2 py-1 text-xs font-bold text-gray-700 dark:bg-gray-900 dark:text-gray-200">${item.cantidad} x ${escapeHtml(item.nombre_producto)}</span>`).join('')}
        </div>
        <div class="mt-4 grid gap-2 sm:grid-cols-3">
          ${whatsappUrl ? `<a href="${escapeHtml(whatsappUrl)}" target="${whatsappTarget}" class="rounded-lg border border-green-200 px-3 py-2 text-center text-sm font-black text-green-700 hover:bg-green-50">WhatsApp</a>` : ''}
          ${order.estado === 'listo' ? `<button type="button" data-action="salir" data-order-id="${order.id_pedido}" class="rounded-lg bg-orange-600 px-3 py-2 text-sm font-black text-white hover:bg-orange-700">Salgo ahora</button>` : ''}
          <button type="button" data-action="entregar" data-order-id="${order.id_pedido}" class="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-black text-white hover:bg-emerald-700">Entregado</button>
        </div>
      </article>
    `;
  };
  const emptyRoute = () => '<div class="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm font-semibold text-gray-500 dark:border-gray-700 dark:bg-gray-800">No tenes pedidos asignados para entregar.</div>';
  const changeState = async (orderId, action) => {
    await apiJson(`/api/gastronomia/delivery/ruta/pedidos/${orderId}/${action}`, {method: 'POST', body: '{}'});
    showAlert(action === 'entregar' ? 'Pedido marcado como entregado.' : 'Pedido marcado en camino.', true);
    await load();
  };
  ordersBox.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    changeState(button.dataset.orderId, button.dataset.action).catch((error) => showAlert(error.message, false));
  });
  refreshButton?.addEventListener('click', () => load().catch((error) => showAlert(error.message, false)));
  load().catch((error) => showAlert(error.message, false));
}());
