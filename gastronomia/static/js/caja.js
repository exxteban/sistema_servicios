(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const ordersEl = document.getElementById('caja-orders');
  const alertBox = document.getElementById('caja-alert');
  const selectedSummary = document.getElementById('selected-summary');
  const discountInput = document.getElementById('discount-amount');
  const paymentTotal = document.getElementById('payment-total');
  let orders = [];
  let selectedOrderId = null;

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

  const loadOrders = async () => {
    const data = await apiJson('/api/gastronomia/caja/pedidos');
    orders = data.pedidos || [];
    if (!orders.some((order) => Number(order.id_pedido) === Number(selectedOrderId))) {
      selectedOrderId = null;
    }
    renderOrders();
    renderSelected();
  };
  const renderOrders = () => {
    ordersEl.innerHTML = orders.map(renderOrder).join('') || `
      <div class="rounded-xl border border-dashed border-gray-300 p-10 text-center text-gray-500 dark:border-gray-700 lg:col-span-2">
        Sin pedidos pendientes de cobro.
      </div>
    `;
  };
  const renderOrder = (order) => `
    <article class="caja-card ${Number(order.id_pedido) === Number(selectedOrderId) ? 'active' : ''}" data-order="${order.id_pedido}">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h2 class="text-xl font-black text-gray-900 dark:text-white">#${order.id_pedido} ${escapeHtml(order.tipo_pedido)}</h2>
          <p class="mt-1 text-sm font-semibold text-gray-500">${order.mesa ? `Mesa ${escapeHtml(order.mesa)} - ` : ''}${escapeHtml(order.estado)}</p>
        </div>
        <strong class="text-xl text-emerald-700 dark:text-emerald-300">${money(order.total)}</strong>
      </div>
      <div class="mt-4 space-y-2">
        ${(order.items || []).map((item) => `
          <div class="flex justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2 text-sm dark:bg-gray-900/40">
            <span class="font-semibold text-gray-700 dark:text-gray-200">${item.cantidad} x ${escapeHtml(item.nombre_producto)}</span>
            <span class="font-bold text-gray-900 dark:text-white">${money(item.subtotal)}</span>
          </div>
        `).join('')}
      </div>
      <button type="button" data-select="${order.id_pedido}" class="mt-4 w-full rounded-xl border border-emerald-200 px-4 py-3 text-sm font-bold text-emerald-700 hover:bg-emerald-50">
        Seleccionar
      </button>
    </article>
  `;
  const renderSelected = () => {
    const order = orders.find((item) => Number(item.id_pedido) === Number(selectedOrderId));
    if (!order) {
      selectedSummary.textContent = 'Selecciona un pedido pendiente.';
      paymentTotal.textContent = money(0);
      return;
    }
    const discount = Math.max(0, Number(discountInput.value || 0));
    selectedSummary.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <strong class="text-gray-900 dark:text-white">Pedido #${order.id_pedido}</strong>
        <span class="font-bold text-emerald-700 dark:text-emerald-300">${money(order.total)}</span>
      </div>
      <p class="mt-2 text-sm text-gray-500">${escapeHtml(order.tipo_pedido)}${order.mesa ? ` - Mesa ${escapeHtml(order.mesa)}` : ''}</p>
    `;
    paymentTotal.textContent = money(Math.max(0, Number(order.total || 0) - discount));
  };
  const chargeSelected = async () => {
    if (!selectedOrderId) throw new Error('Selecciona un pedido para cobrar.');
    const data = await apiJson(`/api/gastronomia/caja/pedidos/${selectedOrderId}/cobrar`, {
      method: 'POST',
      body: JSON.stringify({
        metodo_pago: document.getElementById('payment-method').value,
        descuento_monto: Number(discountInput.value || 0),
        observacion: document.getElementById('payment-note').value.trim(),
      }),
    });
    showAlert(`Pedido #${data.pedido.id_pedido} cobrado.`, true);
    selectedOrderId = null;
    discountInput.value = 0;
    document.getElementById('payment-note').value = '';
    await loadOrders();
  };

  ordersEl?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-select]');
    if (!button) return;
    selectedOrderId = Number(button.dataset.select);
    renderOrders();
    renderSelected();
  });
  discountInput?.addEventListener('input', renderSelected);
  document.getElementById('charge-order')?.addEventListener('click', () => {
    chargeSelected().catch((error) => showAlert(error.message, false));
  });
  loadOrders().catch((error) => showAlert(error.message, false));
}());
