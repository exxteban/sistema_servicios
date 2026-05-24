(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const board = document.getElementById('kds-board');
  const alertBox = document.getElementById('kds-alert');
  let lastEventId = 0;
  let pollTimer = null;

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
  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const elapsed = (iso) => {
    const start = new Date(iso || Date.now()).getTime();
    const minutes = Math.max(0, Math.floor((Date.now() - start) / 60000));
    return `${minutes} min`;
  };
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));

  const loadBoard = async () => {
    const data = await apiJson('/api/gastronomia/cocina/pedidos');
    render(data.pedidos || []);
  };
  const pollEvents = async () => {
    try {
      const data = await apiJson(`/api/gastronomia/cocina/eventos?after=${lastEventId}`);
      const events = data.eventos || [];
      if (events.length) {
        lastEventId = Math.max(...events.map((event) => Number(event.id_evento || 0)));
        await loadBoard();
      }
    } catch (error) {
      showAlert(error.message, false);
    }
  };
  const render = (orders) => {
    board.innerHTML = orders.map(renderOrder).join('') || `
      <div class="rounded-xl border border-dashed border-gray-300 p-10 text-center text-gray-500 dark:border-gray-700 lg:col-span-2">
        Sin pedidos pendientes.
      </div>
    `;
  };
  const renderOrder = (order) => `
    <article class="kds-card" data-order="${order.id_pedido}">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h2 class="text-xl font-black text-gray-900 dark:text-white">#${order.id_pedido} ${escapeHtml(order.tipo_pedido)}</h2>
          <p class="mt-1 text-sm font-semibold text-gray-500">${order.mesa ? `Mesa ${escapeHtml(order.mesa)} · ` : ''}${elapsed(order.fecha_envio_cocina || order.fecha_creacion)}</p>
        </div>
        <span class="rounded-full px-3 py-1 text-sm font-bold ${order.estado === 'preparando' ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800'}">${escapeHtml(order.estado)}</span>
      </div>
      <div class="mt-4 space-y-3">
        ${(order.items || []).map((item) => `
          <div class="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
            <div class="flex justify-between gap-3">
              <strong class="text-gray-900 dark:text-white">${item.cantidad} x ${escapeHtml(item.nombre_producto)}</strong>
              <span class="text-sm font-bold text-gray-600 dark:text-gray-300">${money(item.subtotal)}</span>
            </div>
            ${item.modificadores?.length ? `<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">${escapeHtml(item.modificadores.map((mod) => mod.nombre_opcion).join(', '))}</p>` : ''}
            ${item.notas ? `<p class="mt-2 rounded bg-amber-50 px-2 py-1 text-sm font-semibold text-amber-800">${escapeHtml(item.notas)}</p>` : ''}
          </div>
        `).join('')}
      </div>
      ${order.notas ? `<p class="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-800">${escapeHtml(order.notas)}</p>` : ''}
      <div class="mt-5 grid gap-3 sm:grid-cols-2">
        <button type="button" data-action="tomar" class="rounded-xl bg-sky-600 px-4 py-4 text-base font-bold text-white hover:bg-sky-700">Preparando</button>
        <button type="button" data-action="listo" class="rounded-xl bg-emerald-600 px-4 py-4 text-base font-bold text-white hover:bg-emerald-700">Listo</button>
      </div>
    </article>
  `;
  const changeState = async (orderId, action) => {
    const data = await apiJson(`/api/gastronomia/cocina/pedidos/${orderId}/${action}`, {method: 'POST', body: '{}'});
    showAlert(`Pedido #${data.pedido.id_pedido} actualizado.`, true);
    await loadBoard();
  };

  board?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    const card = event.target.closest('[data-order]');
    if (!button || !card) return;
    changeState(card.dataset.order, button.dataset.action).catch((error) => showAlert(error.message, false));
  });
  loadBoard().catch((error) => showAlert(error.message, false));
  pollTimer = setInterval(pollEvents, 5000);
  window.addEventListener('beforeunload', () => clearInterval(pollTimer));
}());
