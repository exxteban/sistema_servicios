(function () {
  const root = document.querySelector('[data-gastro-delivery]');
  const csrf = document.getElementById('csrf-token')?.value || '';
  const board = document.getElementById('delivery-board');
  const summary = document.getElementById('delivery-summary');
  const alertBox = document.getElementById('delivery-alert');
  const searchInput = document.getElementById('delivery-search');
  const refreshButton = document.getElementById('delivery-refresh');
  if (!root || !board || !summary || !alertBox) return;

  const activeStates = ['abierto', 'enviado_cocina', 'preparando', 'listo', 'en_camino'];
  const columns = [
    {key: 'abierto', title: 'Recibidos'},
    {key: 'enviado_cocina', title: 'En cocina'},
    {key: 'preparando', title: 'Preparando'},
    {key: 'listo', title: 'Listos'},
    {key: 'en_camino', title: 'En camino'},
  ];
  const stateLabels = {
    abierto: 'Recibido',
    enviado_cocina: 'En cocina',
    preparando: 'Preparando',
    listo: 'Listo',
    en_camino: 'En camino',
  };
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
    const params = new URLSearchParams({tipo_pedido: 'delivery', estados: activeStates.join(',')});
    const data = await apiJson(`/api/gastronomia/pedidos?${params.toString()}`);
    orders = data.pedidos || [];
    render();
  };
  const filteredOrders = () => {
    const term = (searchInput?.value || '').trim().toLowerCase();
    if (!term) return orders;
    return orders.filter((order) => [
      order.codigo_entrega,
      order.referencia_entrega,
      order.nombre_cliente,
      order.celular_cliente,
      order.direccion_entrega,
      ...(order.items || []).map((item) => item.nombre_producto),
    ].join(' ').toLowerCase().includes(term));
  };
  const render = () => {
    const visible = filteredOrders();
    renderSummary(visible);
    const grouped = Object.fromEntries(columns.map((column) => [column.key, []]));
    visible.forEach((order) => grouped[order.estado]?.push(order));
    board.innerHTML = columns.map((column) => renderColumn(column, grouped[column.key] || [])).join('');
  };
  const renderSummary = (visible) => {
    summary.innerHTML = columns.map((column) => `
      <article class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <p class="text-xs font-black uppercase tracking-wide text-gray-500">${column.title}</p>
        <strong class="mt-2 block text-3xl font-black text-gray-900 dark:text-white">${visible.filter((order) => order.estado === column.key).length}</strong>
      </article>
    `).join('');
  };
  const renderColumn = (column, columnOrders) => `
    <section class="rounded-xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div class="mb-3 flex items-center justify-between gap-3 border-b border-gray-100 pb-3 dark:border-gray-700">
        <h2 class="font-black text-gray-900 dark:text-white">${column.title}</h2>
        <span class="rounded-full bg-orange-100 px-2 py-1 text-xs font-black text-orange-800">${columnOrders.length}</span>
      </div>
      <div class="space-y-3">${columnOrders.length ? columnOrders.map(renderOrder).join('') : emptyColumn()}</div>
    </section>
  `;
  const emptyColumn = () => '<div class="rounded-lg border border-dashed border-gray-300 p-5 text-center text-sm font-semibold text-gray-500 dark:border-gray-700">Sin pedidos.</div>';
  const renderOrder = (order) => {
    const phone = phoneDigits(order.celular_cliente);
    return `
      <article class="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900" data-order="${order.id_pedido}">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h3 class="text-lg font-black text-gray-900 dark:text-white">${escapeHtml(order.codigo_entrega || `#${order.id_pedido}`)}</h3>
            <p class="text-xs font-bold uppercase text-gray-500">${elapsed(order.fecha_creacion)}</p>
          </div>
          <strong class="whitespace-nowrap text-sm font-black text-orange-700 dark:text-orange-300">${money(order.total)}</strong>
        </div>
        <div class="mt-3 space-y-1 text-sm leading-snug text-gray-700 dark:text-gray-200">
          ${order.nombre_cliente || order.referencia_entrega ? `<p class="break-words"><strong>Cliente:</strong> ${escapeHtml(order.nombre_cliente || order.referencia_entrega)}</p>` : ''}
          ${order.celular_cliente ? `<p class="break-words"><strong>Cel:</strong> ${escapeHtml(order.celular_cliente)}</p>` : ''}
          ${order.direccion_entrega ? `<p class="break-words"><strong>Dir:</strong> ${escapeHtml(order.direccion_entrega)}</p>` : ''}
          ${Number(order.costo_envio || 0) > 0 ? `<p><strong>Envio:</strong> ${money(order.costo_envio)}</p>` : ''}
          ${order.tiempo_estimado_minutos ? `<p><strong>Estimado:</strong> ${order.tiempo_estimado_minutos} min</p>` : ''}
        </div>
        <div class="mt-3 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs font-black uppercase tracking-wide text-orange-800 dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-200">
          ${stateLabels[order.estado] || escapeHtml(order.estado)}
        </div>
        <div class="mt-3 flex flex-wrap gap-1.5">
          ${(order.items || []).map((item) => `<span class="rounded bg-white px-2 py-1 text-xs font-bold text-gray-700 dark:bg-gray-800 dark:text-gray-200">${item.cantidad} x ${escapeHtml(item.nombre_producto)}</span>`).join('')}
        </div>
        <div class="mt-3 grid gap-2">
          <div class="grid gap-2" style="grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) 2.5rem;">
            <a href="/gastronomia/cocina" class="rounded-lg border border-orange-200 px-2 py-2 text-center text-xs font-black text-orange-800 hover:bg-orange-50 dark:border-orange-500/30 dark:text-orange-200 dark:hover:bg-orange-500/10">Cocina</a>
            <a href="/gastronomia/pedidos/${order.id_pedido}/ticket?preview=1" class="rounded-lg border border-gray-200 px-2 py-2 text-center text-xs font-black text-gray-700 hover:bg-white dark:border-gray-700 dark:text-gray-200">Ticket</a>
            <a href="${escapeHtml(order.url_seguimiento || '#')}" target="_blank" rel="noopener" class="rounded-lg border border-gray-200 px-2 py-2 text-center text-xs font-black text-gray-700 hover:bg-white dark:border-gray-700 dark:text-gray-200">Estado</a>
            ${phone ? `<a href="https://wa.me/${phone}" target="_blank" rel="noopener" title="Abrir WhatsApp" aria-label="Abrir WhatsApp" class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-green-200 text-lg text-green-700 hover:bg-green-50"><i class="fab fa-whatsapp"></i></a>` : '<span title="Sin celular" aria-label="Sin celular para WhatsApp" class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-200 text-lg text-gray-400"><i class="fab fa-whatsapp"></i></span>'}
          </div>
        </div>
      </article>
    `;
  };
  const elapsed = (iso) => {
    const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso || Date.now()).getTime()) / 60000));
    return `${minutes} min desde ingreso`;
  };
  const phoneDigits = (phone) => {
    const digits = String(phone || '').replace(/\D+/g, '');
    if (!digits) return '';
    return digits.startsWith('595') ? digits : `595${digits.replace(/^0+/, '')}`;
  };
  searchInput?.addEventListener('input', render);
  refreshButton?.addEventListener('click', () => load().catch((error) => showAlert(error.message, false)));
  load().catch((error) => showAlert(error.message, false));
}());
