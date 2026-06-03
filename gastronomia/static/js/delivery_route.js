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
  let routeMode = 'repartidor';
  let refreshTimer = null;
  let gpsWatchId = null;
  let gpsOrderId = null;
  let lastGpsSentAt = 0;
  const gpsTrackingEnabled = root.dataset.gpsTracking === '1';
  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const showAlert = (message, ok) => {
    const warning = ok === 'warning';
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok === true ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : warning ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-red-200 bg-red-50 text-red-800'}`;
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
  const load = async ({keepAlert = false} = {}) => {
    if (!keepAlert) hideAlert();
    const data = await apiJson('/api/gastronomia/delivery/ruta');
    routeMode = data.modo || 'repartidor';
    orders = data.pedidos || [];
    if (data.repartidor) {
      driverName.textContent = `Ruta de ${data.repartidor.nombre}`;
    } else if (routeMode === 'operativo') {
      driverName.textContent = 'Vista operativa de pedidos delivery listos o en camino.';
    } else {
      driverName.textContent = 'Usuario sin repartidor vinculado.';
    }
    if (data.mensaje) showAlert(data.mensaje, routeMode === 'sin_repartidor' ? 'warning' : true);
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
    const trackingUrl = window.GastroWhatsApp?.trackingUrl(order) || '';
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
        <div class="mt-4 grid gap-2 sm:grid-cols-4">
          ${renderDestinationButton(order)}
          ${trackingUrl ? `<button type="button" data-copy-tracking="${order.id_pedido}" class="rounded-lg border border-sky-200 px-3 py-2 text-center text-sm font-black text-sky-700 hover:bg-sky-50"><i class="fas fa-link"></i> Copiar</button>` : ''}
          ${whatsappUrl ? `<a href="${escapeHtml(whatsappUrl)}" target="${whatsappTarget}" class="rounded-lg border border-green-200 px-3 py-2 text-center text-sm font-black text-green-700 hover:bg-green-50">WhatsApp</a>` : ''}
          ${order.estado === 'listo' ? `<button type="button" data-action="salir" data-order-id="${order.id_pedido}" class="rounded-lg bg-orange-600 px-3 py-2 text-sm font-black text-white hover:bg-orange-700">Salgo ahora</button>` : ''}
          ${renderGpsButton(order)}
          <button type="button" data-action="entregar" data-order-id="${order.id_pedido}" class="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-black text-white hover:bg-emerald-700">Entregado</button>
        </div>
      </article>
    `;
  };
  const renderDestinationButton = (order) => {
    const url = destinationUrl(order);
    if (!url) return '';
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="rounded-lg bg-sky-600 px-3 py-2 text-center text-sm font-black text-white hover:bg-sky-700">Ir al destino</a>`;
  };
  const destinationUrl = (order) => {
    const lat = Number(order.destino_latitud);
    const lng = Number(order.destino_longitud);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${lat},${lng}`)}`;
    }
    const locationUrl = String(order.ubicacion_entrega_url || '').trim();
    if (/^https?:\/\//i.test(locationUrl)) return locationUrl;
    const address = String(order.direccion_entrega || '').trim();
    if (!address) return '';
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
  };
  const renderGpsButton = (order) => {
    if (!gpsTrackingEnabled || order.estado !== 'en_camino') return '';
    const active = Number(gpsOrderId || 0) === Number(order.id_pedido || 0);
    return `<button type="button" data-start-gps="${order.id_pedido}" class="rounded-lg border border-sky-200 px-3 py-2 text-sm font-black ${active ? 'bg-sky-600 text-white' : 'text-sky-700 hover:bg-sky-50'}">${active ? 'GPS activo' : 'Activar GPS'}</button>`;
  };
  const emptyRoute = () => {
    const message = routeMode === 'sin_repartidor'
      ? 'Vincula este usuario a un repartidor activo desde Delivery > Repartidores.'
      : 'No tenes pedidos asignados para entregar.';
    return `<div class="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm font-semibold text-gray-500 dark:border-gray-700 dark:bg-gray-800">${message}</div>`;
  };
  const changeState = async (orderId, action) => {
    await apiJson(`/api/gastronomia/delivery/ruta/pedidos/${orderId}/${action}`, {method: 'POST', body: '{}'});
    showAlert(action === 'entregar' ? 'Pedido marcado como entregado.' : 'Pedido marcado en camino.', true);
    await load({keepAlert: true});
    if (action === 'salir') startGpsTracking(orderId);
    if (action === 'entregar') stopGpsTracking(orderId);
  };
  const startGpsTracking = (orderId) => {
    if (!gpsTrackingEnabled) return;
    if (!navigator.geolocation) {
      showAlert('Este telefono/navegador no permite GPS desde la web.', false);
      return;
    }
    if (gpsWatchId !== null) navigator.geolocation.clearWatch(gpsWatchId);
    gpsOrderId = Number(orderId || 0);
    lastGpsSentAt = 0;
    gpsWatchId = navigator.geolocation.watchPosition(
      (position) => sendGpsPosition(gpsOrderId, position).catch(() => {}),
      () => showAlert('No se pudo activar GPS. Revisa el permiso de ubicacion del telefono.', false),
      {enableHighAccuracy: true, maximumAge: 10000, timeout: 15000},
    );
    showAlert('GPS activo para esta entrega mientras la hoja de ruta siga abierta.', true);
    render();
  };
  const stopGpsTracking = (orderId) => {
    if (gpsWatchId === null) return;
    if (orderId && Number(orderId) !== Number(gpsOrderId)) return;
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
    gpsOrderId = null;
    lastGpsSentAt = 0;
  };
  const sendGpsPosition = async (orderId, position) => {
    if (!orderId || !position?.coords) return;
    const now = Date.now();
    if (now - lastGpsSentAt < 15000) return;
    lastGpsSentAt = now;
    await apiJson(`/api/gastronomia/delivery/ruta/pedidos/${orderId}/ubicacion`, {
      method: 'POST',
      body: JSON.stringify({
        latitud: position.coords.latitude,
        longitud: position.coords.longitude,
        precision_metros: position.coords.accuracy,
      }),
    });
  };
  const copyTrackingLink = async (orderId) => {
    const order = orders.find((item) => Number(item.id_pedido) === Number(orderId));
    if (!order) throw new Error('Pedido no encontrado.');
    const copied = await window.GastroWhatsApp?.copyTrackingUrl(order);
    if (!copied) throw new Error('No se pudo copiar el link.');
    showAlert('Link de estado copiado.', true);
  };
  ordersBox.addEventListener('click', (event) => {
    const copyButton = event.target.closest('[data-copy-tracking]');
    if (copyButton) {
      copyTrackingLink(copyButton.dataset.copyTracking).catch((error) => showAlert(error.message, false));
      return;
    }
    const gpsButton = event.target.closest('[data-start-gps]');
    if (gpsButton) {
      startGpsTracking(gpsButton.dataset.startGps);
      return;
    }
    const button = event.target.closest('[data-action]');
    if (!button) return;
    changeState(button.dataset.orderId, button.dataset.action).catch((error) => showAlert(error.message, false));
  });
  refreshButton?.addEventListener('click', () => load().catch((error) => showAlert(error.message, false)));
  load().catch((error) => showAlert(error.message, false));
  refreshTimer = window.setInterval(() => load({keepAlert: true}).catch(() => {}), 10000);
  window.addEventListener('beforeunload', () => {
    if (refreshTimer) window.clearInterval(refreshTimer);
    stopGpsTracking();
  });
}());
