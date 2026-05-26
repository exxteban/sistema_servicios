(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const ordersEl = document.getElementById('caja-orders');
  const alertBox = document.getElementById('caja-alert');
  const selectedSummary = document.getElementById('selected-summary');
  const discountInput = document.getElementById('discount-amount');
  const paymentMethodInput = document.getElementById('payment-method');
  const paymentTotal = document.getElementById('payment-total');
  let orders = [];
  let selectedOrderId = null;
  let lastEventId = 0;
  let pollTimer = null;
  let chargeBusy = false;
  const cashStates = new Set(['abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado']);

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
  const deliveryCode = (order) => escapeHtml(order.codigo_entrega || `#${String(order.id_pedido || 0).padStart(3, '0')}`);
  const selectPaymentMethod = (button) => {
    if (!button || !paymentMethodInput) return;
    paymentMethodInput.value = button.dataset.paymentMethod || 'efectivo';
    document.querySelectorAll('[data-payment-method]').forEach((item) => {
      item.classList.toggle('active', item === button);
      item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
    });
  };

  const loadOrders = async () => {
    const data = await apiJson('/api/gastronomia/caja/pedidos');
    orders = data.pedidos || [];
    lastEventId = Math.max(lastEventId, Number(data.ultimo_evento_id || 0));
    if (!orders.some((order) => Number(order.id_pedido) === Number(selectedOrderId))) {
      selectedOrderId = null;
    }
    renderOrders();
    renderSelected();
  };
  const pollEvents = async () => {
    try {
      const data = await apiJson(`/api/gastronomia/caja/eventos?after=${lastEventId}`);
      const events = data.eventos || [];
      lastEventId = Math.max(lastEventId, Number(data.ultimo_evento_id || 0), ...events.map((event) => Number(event.id_evento || 0)));
      if (events.length) applyOrderEvents(events);
    } catch (error) {
      showAlert(error.message, false);
    }
  };
  const applyOrderEvents = (events) => {
    let changed = false;
    events.forEach((event) => {
      const order = event?.payload?.pedido;
      if (!order?.id_pedido) return;
      changed = applyOrderSnapshot(order) || changed;
    });
    if (!changed) return;
    sortOrders();
    if (!orders.some((order) => Number(order.id_pedido) === Number(selectedOrderId))) {
      selectedOrderId = null;
    }
    renderOrders();
    renderSelected();
  };
  const applyOrderSnapshot = (order) => {
    const orderId = Number(order.id_pedido);
    const index = orders.findIndex((item) => Number(item.id_pedido) === orderId);
    const visible = cashStates.has(order.estado) && !order.pagado;
    if (!visible) {
      if (index === -1) return false;
      orders.splice(index, 1);
      return true;
    }
    if (index === -1) orders.push(order);
    else orders[index] = order;
    return true;
  };
  const sortOrders = () => {
    orders.sort((a, b) => {
      const dateDiff = new Date(b.fecha_creacion || 0).getTime() - new Date(a.fecha_creacion || 0).getTime();
      return dateDiff || Number(b.id_pedido || 0) - Number(a.id_pedido || 0);
    });
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
          <h2 class="text-xl font-black text-gray-900 dark:text-white">${deliveryCode(order)} ${escapeHtml(order.tipo_pedido)}</h2>
          <p class="mt-1 text-sm font-semibold text-gray-500">${order.mesa ? `Mesa ${escapeHtml(order.mesa)} - ` : ''}${escapeHtml(order.estado)}</p>
          ${order.referencia_entrega ? `<p class="mt-1 text-xs font-black uppercase tracking-wide text-emerald-700 dark:text-emerald-300">${escapeHtml(order.referencia_entrega)}</p>` : ''}
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
        <strong class="text-gray-900 dark:text-white">Pedido ${deliveryCode(order)}</strong>
        <span class="font-bold text-emerald-700 dark:text-emerald-300">${money(order.total)}</span>
      </div>
      <p class="mt-2 text-sm text-gray-500">${escapeHtml(order.tipo_pedido)}${order.mesa ? ` - Mesa ${escapeHtml(order.mesa)}` : ''}${order.referencia_entrega ? ` - ${escapeHtml(order.referencia_entrega)}` : ''}</p>
    `;
    paymentTotal.textContent = money(Math.max(0, Number(order.total || 0) - discount));
  };
  const chargeSelected = async (ticketWindow = null) => {
    if (!selectedOrderId) throw new Error('Selecciona un pedido para cobrar.');
    if (chargeBusy) return;
    setChargeBusy(true);
    const data = await apiJson(`/api/gastronomia/caja/pedidos/${selectedOrderId}/cobrar`, {
      method: 'POST',
      body: JSON.stringify({
        metodo_pago: document.getElementById('payment-method').value,
        descuento_monto: Number(discountInput.value || 0),
        observacion: document.getElementById('payment-note').value.trim(),
      }),
    });
    showAlert(`Pedido #${data.pedido.id_pedido} cobrado.`, true);
    const ticketUrl = `/gastronomia/pedidos/${data.pedido.id_pedido}/ticket`;
    if (ticketWindow) ticketWindow.location = ticketUrl;
    else window.open(ticketUrl, '_blank');
    selectedOrderId = null;
    discountInput.value = 0;
    document.getElementById('payment-note').value = '';
    selectPaymentMethod(document.querySelector('[data-payment-method="efectivo"]'));
    applyOrderEvents([{payload: {pedido: data.pedido}}]);
    setChargeBusy(false);
  };
  const setChargeBusy = (busy) => {
    chargeBusy = busy;
    const button = document.getElementById('charge-order');
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle('opacity-70', busy);
    button.classList.toggle('cursor-not-allowed', busy);
    button.textContent = busy ? 'Cobrando...' : 'Cobrar pedido';
  };

  ordersEl?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-select]');
    if (!button) return;
    selectedOrderId = Number(button.dataset.select);
    renderOrders();
    renderSelected();
  });
  discountInput?.addEventListener('input', renderSelected);
  document.querySelectorAll('[data-payment-method]').forEach((button) => {
    button.setAttribute('aria-pressed', button.classList.contains('active') ? 'true' : 'false');
    button.addEventListener('click', () => selectPaymentMethod(button));
  });
  document.getElementById('charge-order')?.addEventListener('click', () => {
    if (chargeBusy) return;
    const ticketWindow = selectedOrderId ? window.open('', '_blank') : null;
    chargeSelected(ticketWindow).catch((error) => {
      if (ticketWindow) ticketWindow.close();
      setChargeBusy(false);
      showAlert(error.message, false);
    });
  });
  loadOrders()
    .catch((error) => showAlert(error.message, false))
    .finally(() => { pollTimer = setInterval(pollEvents, 2500); });
  window.addEventListener('beforeunload', () => clearInterval(pollTimer));
}());
