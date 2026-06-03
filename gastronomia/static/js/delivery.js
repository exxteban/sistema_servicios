(function () {
  const root = document.querySelector('[data-gastro-delivery]');
  const csrf = document.getElementById('csrf-token')?.value || '';
  const board = document.getElementById('delivery-board');
  const summary = document.getElementById('delivery-summary');
  const alertBox = document.getElementById('delivery-alert');
  const searchInput = document.getElementById('delivery-search');
  const refreshButton = document.getElementById('delivery-refresh');
  const driverForm = document.getElementById('delivery-driver-form');
  const driversList = document.getElementById('delivery-drivers-list');
  const driversCount = document.getElementById('delivery-drivers-count');
  const tabs = [...document.querySelectorAll('[data-delivery-tab]')];
  const panels = [...document.querySelectorAll('[data-delivery-panel]')];
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
  let drivers = [];

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
  const setActiveTab = (key) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.deliveryTab === key;
      tab.className = `delivery-tab rounded-lg px-4 py-2 text-sm font-black transition ${active ? 'bg-orange-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-900'}`;
    });
    panels.forEach((panel) => panel.classList.toggle('hidden', panel.dataset.deliveryPanel !== key));
  };
  const load = async () => {
    hideAlert();
    const params = new URLSearchParams({tipo_pedido: 'delivery', estados: activeStates.join(',')});
    const [data, driverData] = await Promise.all([
      apiJson(`/api/gastronomia/pedidos?${params.toString()}`),
      apiJson('/api/gastronomia/delivery/repartidores?incluir_inactivos=1'),
    ]);
    orders = data.pedidos || [];
    drivers = driverData.repartidores || [];
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
    renderDrivers();
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
    const whatsappUrl = window.GastroWhatsApp?.buildOrderWhatsAppUrl(order, order.celular_cliente) || '';
    const whatsappTarget = escapeHtml(window.GastroWhatsApp?.target || 'gastro-whatsapp');
    const trackingUrl = window.GastroWhatsApp?.trackingUrl(order) || '';
    const assigned = order.repartidor ? escapeHtml(order.repartidor.nombre) : 'Sin repartidor';
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
          <p><strong>Delivery:</strong> ${assigned}</p>
        </div>
        <div class="mt-3 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs font-black uppercase tracking-wide text-orange-800 dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-200">
          ${stateLabels[order.estado] || escapeHtml(order.estado)}
        </div>
        <div class="mt-3 flex flex-wrap gap-1.5">
          ${(order.items || []).map((item) => `<span class="rounded bg-white px-2 py-1 text-xs font-bold text-gray-700 dark:bg-gray-800 dark:text-gray-200">${item.cantidad} x ${escapeHtml(item.nombre_producto)}</span>`).join('')}
        </div>
        <div class="mt-3 grid gap-2">
          <select data-driver-select="${order.id_pedido}" class="w-full rounded-lg border border-gray-200 px-2 py-2 text-xs font-black text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
            <option value="">Sin repartidor</option>
            ${drivers.filter((driver) => driver.activo || driver.id_repartidor === order.repartidor_id).map((driver) => `<option value="${driver.id_repartidor}" ${Number(order.repartidor_id || 0) === Number(driver.id_repartidor) ? 'selected' : ''}>${escapeHtml(driver.nombre)}</option>`).join('')}
          </select>
          <div class="grid gap-2" style="grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) 2.5rem 2.5rem;">
            ${renderKitchenControl(order)}
            <a href="/gastronomia/pedidos/${order.id_pedido}/ticket?preview=1" class="rounded-lg border border-gray-200 px-2 py-2 text-center text-xs font-black text-gray-700 hover:bg-white dark:border-gray-700 dark:text-gray-200">Ticket</a>
            <a href="${escapeHtml(order.url_seguimiento_publica || order.url_seguimiento || '#')}" target="_blank" rel="noopener" class="rounded-lg border border-gray-200 px-2 py-2 text-center text-xs font-black text-gray-700 hover:bg-white dark:border-gray-700 dark:text-gray-200">Estado</a>
            ${trackingUrl ? `<button type="button" data-copy-tracking="${order.id_pedido}" title="Copiar link de estado" aria-label="Copiar link de estado" class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-sky-200 text-lg text-sky-700 hover:bg-sky-50"><i class="fas fa-link"></i></button>` : '<span title="Sin link de estado" aria-label="Sin link de estado" class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-200 text-lg text-gray-400"><i class="fas fa-link"></i></span>'}
            ${whatsappUrl ? `<a href="${escapeHtml(whatsappUrl)}" target="${whatsappTarget}" title="Compartir seguimiento por WhatsApp" aria-label="Compartir seguimiento por WhatsApp" class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-green-200 text-lg text-green-700 hover:bg-green-50"><i class="fab fa-whatsapp"></i></a>` : '<span title="Sin celular" aria-label="Sin celular para WhatsApp" class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-200 text-lg text-gray-400"><i class="fab fa-whatsapp"></i></span>'}
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            ${order.estado === 'listo' ? `<button type="button" data-state="en_camino" data-order-action="${order.id_pedido}" class="rounded-lg bg-orange-600 px-3 py-2 text-xs font-black text-white hover:bg-orange-700">Sale a entrega</button>` : ''}
            ${['listo', 'en_camino'].includes(order.estado) ? `<button type="button" data-state="entregado" data-order-action="${order.id_pedido}" class="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-black text-white hover:bg-emerald-700">Marcar entregado</button>` : ''}
          </div>
        </div>
      </article>
    `;
  };
  const renderKitchenControl = (order) => {
    const classes = 'rounded-lg border border-orange-200 px-2 py-2 text-center text-xs font-black text-orange-800 hover:bg-orange-50 dark:border-orange-500/30 dark:text-orange-200 dark:hover:bg-orange-500/10';
    if (order.estado === 'abierto') {
      return `<button type="button" data-send-kitchen="${order.id_pedido}" class="${classes}">Enviar cocina</button>`;
    }
    return `<a href="/gastronomia/cocina" class="${classes}">Cocina</a>`;
  };
  const elapsed = (iso) => {
    const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso || Date.now()).getTime()) / 60000));
    return `${minutes} min desde ingreso`;
  };
  const renderDrivers = () => {
    if (!driversList || !driversCount) return;
    driversCount.textContent = drivers.length;
    driversList.innerHTML = drivers.length ? drivers.map((driver) => `
      <article class="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-900">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="font-black text-gray-900 dark:text-white">${escapeHtml(driver.nombre)}</h3>
            <p class="text-xs font-bold text-gray-500">${driver.usuario ? `Usuario: ${escapeHtml(driver.usuario)}` : 'Sin usuario de ruta'}</p>
          </div>
          <span class="rounded-full px-2 py-1 text-xs font-black ${driver.activo ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-200 text-gray-600'}">${driver.activo ? 'Activo' : 'Inactivo'}</span>
        </div>
        <p class="mt-2 text-gray-700 dark:text-gray-200">${[driver.celular, driver.vehiculo, driver.patente].filter(Boolean).map(escapeHtml).join(' · ') || 'Sin datos extra'}</p>
        <button type="button" data-edit-driver="${driver.id_repartidor}" class="mt-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-black text-gray-700 hover:bg-white dark:border-gray-700 dark:text-gray-200">Editar</button>
      </article>
    `).join('') : '<div class="rounded-lg border border-dashed border-gray-300 p-5 text-center text-sm font-semibold text-gray-500 dark:border-gray-700">Aun no hay repartidores.</div>';
  };
  const resetDriverForm = () => {
    if (!driverForm) return;
    driverForm.reset();
    document.getElementById('delivery-driver-id').value = '';
    document.getElementById('delivery-driver-active').checked = true;
  };
  const fillDriverForm = (driver) => {
    setActiveTab('drivers');
    document.getElementById('delivery-driver-id').value = driver.id_repartidor || '';
    document.getElementById('delivery-driver-name').value = driver.nombre || '';
    document.getElementById('delivery-driver-phone').value = driver.celular || '';
    document.getElementById('delivery-driver-doc').value = driver.documento || '';
    document.getElementById('delivery-driver-vehicle').value = driver.vehiculo || '';
    document.getElementById('delivery-driver-plate').value = driver.patente || '';
    document.getElementById('delivery-driver-user').value = driver.usuario_id || '';
    document.getElementById('delivery-driver-active').checked = Boolean(driver.activo);
    document.getElementById('delivery-driver-name').focus();
  };
  const driverPayload = () => ({
    nombre: document.getElementById('delivery-driver-name').value,
    celular: document.getElementById('delivery-driver-phone').value,
    documento: document.getElementById('delivery-driver-doc').value,
    vehiculo: document.getElementById('delivery-driver-vehicle').value,
    patente: document.getElementById('delivery-driver-plate').value,
    usuario_id: document.getElementById('delivery-driver-user').value,
    activo: document.getElementById('delivery-driver-active').checked,
  });
  const saveDriver = async (event) => {
    event.preventDefault();
    const id = document.getElementById('delivery-driver-id').value;
    await apiJson(id ? `/api/gastronomia/delivery/repartidores/${id}` : '/api/gastronomia/delivery/repartidores', {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(driverPayload()),
    });
    resetDriverForm();
    showAlert('Repartidor guardado.', true);
    await load();
  };
  const assignDriver = async (orderId, repartidorId) => {
    await apiJson(`/api/gastronomia/delivery/pedidos/${orderId}/repartidor`, {
      method: 'POST',
      body: JSON.stringify({repartidor_id: repartidorId}),
    });
    await load();
  };
  const changeOrderState = async (orderId, estado) => {
    await apiJson(`/api/gastronomia/pedidos/${orderId}/estado`, {
      method: 'POST',
      body: JSON.stringify({estado}),
    });
    await load();
  };
  const sendKitchen = async (orderId) => {
    await apiJson(`/api/gastronomia/pedidos/${orderId}/enviar-cocina`, {method: 'POST', body: '{}'});
    showAlert('Pedido enviado a cocina.', true);
    await load();
  };
  const copyTrackingLink = async (orderId) => {
    const order = orders.find((item) => Number(item.id_pedido) === Number(orderId));
    if (!order) throw new Error('Pedido no encontrado.');
    const copied = await window.GastroWhatsApp?.copyTrackingUrl(order);
    if (!copied) throw new Error('No se pudo copiar el link.');
    showAlert('Link de estado copiado.', true);
  };
  searchInput?.addEventListener('input', render);
  refreshButton?.addEventListener('click', () => load().catch((error) => showAlert(error.message, false)));
  driverForm?.addEventListener('submit', (event) => saveDriver(event).catch((error) => showAlert(error.message, false)));
  document.getElementById('delivery-driver-cancel')?.addEventListener('click', resetDriverForm);
  tabs.forEach((tab) => tab.addEventListener('click', () => setActiveTab(tab.dataset.deliveryTab)));
  driversList?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-edit-driver]');
    if (!button) return;
    const driver = drivers.find((item) => Number(item.id_repartidor) === Number(button.dataset.editDriver));
    if (driver) fillDriverForm(driver);
  });
  board.addEventListener('change', (event) => {
    const select = event.target.closest('[data-driver-select]');
    if (!select) return;
    assignDriver(select.dataset.driverSelect, select.value).catch((error) => showAlert(error.message, false));
  });
  board.addEventListener('click', (event) => {
    const kitchenButton = event.target.closest('[data-send-kitchen]');
    if (kitchenButton) {
      sendKitchen(kitchenButton.dataset.sendKitchen).catch((error) => showAlert(error.message, false));
      return;
    }
    const copyButton = event.target.closest('[data-copy-tracking]');
    if (copyButton) {
      copyTrackingLink(copyButton.dataset.copyTracking).catch((error) => showAlert(error.message, false));
      return;
    }
    const button = event.target.closest('[data-order-action]');
    if (!button) return;
    changeOrderState(button.dataset.orderAction, button.dataset.state).catch((error) => showAlert(error.message, false));
  });
  setActiveTab('states');
  load().catch((error) => showAlert(error.message, false));
}());
