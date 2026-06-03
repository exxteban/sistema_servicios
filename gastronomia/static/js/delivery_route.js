(function () {
  const root = document.querySelector('[data-gastro-delivery-route]');
  const csrf = document.getElementById('csrf-token')?.value || '';
  const ordersBox = document.getElementById('route-orders');
  const summary = document.getElementById('route-summary');
  const alertBox = document.getElementById('route-alert');
  const gpsPanel = document.getElementById('route-gps-panel');
  const driverName = document.getElementById('route-driver-name');
  const refreshButton = document.getElementById('route-refresh');
  if (!root || !ordersBox || !summary || !alertBox) return;

  let orders = [];
  let routeMode = 'repartidor';
  let refreshTimer = null;
  let gpsWatchId = null;
  let gpsOrderId = null;
  let lastGpsSentAt = 0;
  let lastGpsFixAt = 0;
  let gpsWatchdogTimer = null;
  let gpsWatchRetries = 0;
  const GPS_MAX_WATCH_RETRIES = 5;
  const GPS_STALE_MS = 45000;
  let destinationDrafts = {};
  let destinationFeedbacks = {};
  let gpsStatusByOrder = {};
  let permissionState = 'unknown';
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
    renderGpsPanel();
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
  const gpsBlockers = () => {
    const blockers = [];
    if (!gpsTrackingEnabled) blockers.push('Tu usuario no tiene el permiso "Gastronomia - GPS Delivery". Pedile al administrador que lo active.');
    if (routeMode !== 'repartidor') blockers.push('Tu usuario no esta vinculado a un repartidor activo. Vinculalo desde Delivery > Repartidores.');
    if (typeof navigator === 'undefined' || !navigator.geolocation) blockers.push('Este navegador no soporta GPS web.');
    if (window.isSecureContext === false) blockers.push('Estas entrando por HTTP. El GPS solo funciona con HTTPS o localhost; sin eso el navegador nunca pide permiso.');
    if (permissionState === 'denied') blockers.push('El permiso de ubicacion esta bloqueado para esta pagina. Activalo en el candado/ajustes del navegador.');
    return blockers;
  };
  const renderGpsPanel = () => {
    if (!gpsPanel) return;
    const blockers = gpsBlockers();
    const enCamino = orders.filter((order) => order.estado === 'en_camino');
    const trackingActive = gpsWatchId !== null && gpsOrderId;
    const ready = blockers.length === 0;
    const statusLine = !ready
      ? '<span class="font-black text-red-700 dark:text-red-300">GPS no disponible todavia</span>'
      : trackingActive
        ? '<span class="font-black text-emerald-700 dark:text-emerald-300">GPS activo, compartiendo tu ubicacion</span>'
        : permissionState === 'granted'
          ? '<span class="font-black text-emerald-700 dark:text-emerald-300">Permiso concedido. Toca "Salgo ahora" o "Activar GPS" en un pedido en camino.</span>'
          : '<span class="font-black text-sky-700 dark:text-sky-300">Listo para activar. Proba el permiso de ubicacion abajo.</span>';
    const blockersHtml = blockers.length
      ? `<ul class="mt-2 list-disc space-y-1 pl-5 text-xs font-semibold text-red-700 dark:text-red-300">${blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
      : '';
    const hintHtml = ready && !enCamino.length
      ? '<p class="mt-2 text-xs font-semibold text-sky-700 dark:text-sky-300">Para enviar tu ubicacion al cliente necesitas un pedido en estado "En camino". Marca "Salgo ahora" en un pedido listo.</p>'
      : '';
    const buttonHtml = (ready && permissionState !== 'granted')
      ? '<button type="button" id="route-test-gps" class="mt-3 rounded-lg bg-sky-600 px-4 py-2 text-sm font-black text-white hover:bg-sky-700"><i class="fas fa-location-crosshairs"></i> Probar / activar permiso de ubicacion</button>'
      : '';
    gpsPanel.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs font-black uppercase tracking-wide text-sky-700 dark:text-sky-300">Ubicacion GPS</p>
          <p class="mt-1 text-sm">${statusLine}</p>
        </div>
        <i class="fas ${ready ? (trackingActive ? 'fa-satellite-dish text-emerald-600' : 'fa-location-dot text-sky-600') : 'fa-triangle-exclamation text-red-600'} text-2xl"></i>
      </div>
      ${blockersHtml}
      ${hintHtml}
      ${buttonHtml}
    `;
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
          ${renderGpsInfo(order)}
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          ${(order.items || []).map((item) => `<span class="rounded bg-gray-100 px-2 py-1 text-xs font-bold text-gray-700 dark:bg-gray-900 dark:text-gray-200">${item.cantidad} x ${escapeHtml(item.nombre_producto)}</span>`).join('')}
        </div>
        ${renderDestinationEditor(order)}
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
  const renderGpsInfo = (order) => {
    const gps = order.ultima_ubicacion_delivery;
    if (!gps?.latitud || !gps?.longitud) return '';
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${gps.latitud},${gps.longitud}`)}`;
    return `<p class="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-800"><strong>GPS:</strong> ultima ubicacion recibida ${escapeHtml(formatDate(gps.fecha_registro))}. <a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="underline">Ver punto</a></p>`;
  };
  const renderDestinationEditor = (order) => {
    const orderId = String(order.id_pedido || '');
    const currentValue = Object.prototype.hasOwnProperty.call(destinationDrafts, orderId)
      ? destinationDrafts[orderId]
      : order.ubicacion_entrega_url || formatCoords(order) || '';
    return `
      <div class="mt-4 rounded-xl border border-sky-100 bg-sky-50 p-3 dark:border-sky-500/30 dark:bg-sky-500/10">
        <label class="block text-xs font-black uppercase tracking-wide text-sky-800 dark:text-sky-200">
          Ubicacion exacta del destino
          <span class="mt-1 block text-[11px] normal-case font-semibold text-sky-700 dark:text-sky-300">Pega un link de Google Maps/WhatsApp o coordenadas. Se usa para el boton Ir al destino.</span>
          <span class="mt-2 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
            <input data-destination-input="${order.id_pedido}" value="${escapeHtml(currentValue)}" placeholder="Link de ubicacion o -25.3001,-57.6359" class="w-full rounded-lg border border-sky-200 px-3 py-2 text-sm font-semibold text-slate-700 dark:border-sky-500/30 dark:bg-gray-900 dark:text-gray-100">
            <button type="button" data-save-destination="${order.id_pedido}" style="background:#0369a1;color:#fff" class="rounded-lg px-3 py-2 text-sm font-black hover:opacity-90">Guardar destino</button>
            <button type="button" data-clear-destination="${order.id_pedido}" class="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-black text-red-700 hover:bg-red-50">Borrar</button>
          </span>
          <span data-destination-status="${order.id_pedido}" class="mt-2 block text-[11px] normal-case font-black ${destinationFeedbacks[orderId]?.ok === false ? 'text-red-700' : 'text-emerald-700'}">${escapeHtml(destinationFeedbacks[orderId]?.message || '')}</span>
        </label>
      </div>
    `;
  };
  const destinationUrl = (order) => {
    const lat = coordinateValue(order.destino_latitud);
    const lng = coordinateValue(order.destino_longitud);
    if (lat !== null && lng !== null) {
      return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${lat},${lng}`)}`;
    }
    const locationUrl = String(order.ubicacion_entrega_url || '').trim();
    if (/^https?:\/\//i.test(locationUrl)) return locationUrl;
    const address = String(order.direccion_entrega || '').trim();
    if (!address) return '';
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
  };
  const coordinateValue = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const formatCoords = (order) => {
    const lat = coordinateValue(order.destino_latitud);
    const lng = coordinateValue(order.destino_longitud);
    return lat !== null && lng !== null ? `${lat},${lng}` : '';
  };
  const formatDate = (value) => {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat('es-PY', {hour: '2-digit', minute: '2-digit'}).format(date);
  };
  const renderGpsButton = (order) => {
    if (!gpsTrackingEnabled || order.estado !== 'en_camino') return '';
    if (routeMode !== 'repartidor') {
      return '<span class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-center text-sm font-black text-slate-500">GPS solo repartidor</span>';
    }
    const orderId = Number(order.id_pedido || 0);
    const status = gpsStatusByOrder[orderId] || (Number(gpsOrderId || 0) === orderId ? 'active' : 'idle');
    const requesting = status === 'requesting';
    const active = status === 'active';
    const label = requesting ? 'Solicitando GPS...' : active ? 'GPS activo' : status === 'error' ? 'Reintentar GPS' : 'Activar GPS';
    return `<button type="button" data-start-gps="${order.id_pedido}" ${requesting ? 'disabled' : ''} class="rounded-lg border border-sky-200 px-3 py-2 text-sm font-black ${active ? 'bg-sky-600 text-white' : requesting ? 'bg-sky-50 text-sky-700 opacity-70' : 'text-sky-700 hover:bg-sky-50'}">${label}</button>`;
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
    if (routeMode !== 'repartidor') {
      showAlert('El GPS solo puede activarlo el usuario repartidor asignado desde su celular.', false);
      return;
    }
    if (!navigator.geolocation) {
      showAlert('Este telefono/navegador no permite GPS desde la web.', false);
      return;
    }
    if (window.isSecureContext === false) {
      showAlert('GPS requiere HTTPS o localhost. En HTTP el navegador no pide permiso de ubicacion.', false);
      return;
    }
    const numericOrderId = Number(orderId || 0);
    if (!numericOrderId) return;
    if (gpsWatchId !== null) navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchRetries = 0;
    gpsStatusByOrder[numericOrderId] = 'requesting';
    showAlert('Solicitando permiso de ubicacion del telefono...', 'warning');
    render();
    warnIfPermissionBlocked();
    navigator.geolocation.getCurrentPosition(
      (position) => activateGpsTracking(numericOrderId, position).catch((error) => {
        gpsStatusByOrder[numericOrderId] = 'error';
        showAlert(`No se pudo guardar la ubicacion GPS: ${error.message}`, false);
        render();
      }),
      (error) => {
        gpsStatusByOrder[numericOrderId] = 'error';
        showAlert(gpsErrorMessage(error), false);
        render();
      },
      {enableHighAccuracy: true, maximumAge: 0, timeout: 20000},
    );
  };
  const warnIfPermissionBlocked = () => {
    if (!navigator.permissions?.query) return;
    navigator.permissions.query({name: 'geolocation'}).then((status) => {
      if (status.state === 'denied') {
        showAlert('El permiso de ubicacion esta bloqueado para esta pagina. Activalo en el candado/ajustes del navegador y volve a intentar.', false);
      }
    }).catch(() => {});
  };
  const trackPermissionState = () => {
    if (!navigator.permissions?.query) return;
    navigator.permissions.query({name: 'geolocation'}).then((status) => {
      permissionState = status.state;
      renderGpsPanel();
      status.onchange = () => {
        permissionState = status.state;
        renderGpsPanel();
      };
    }).catch(() => {});
  };
  const testGpsPermission = () => {
    const blockers = gpsBlockers();
    if (blockers.length) {
      showAlert(blockers[0], false);
      return;
    }
    showAlert('Solicitando permiso de ubicacion al navegador...', 'warning');
    navigator.geolocation.getCurrentPosition(
      () => {
        permissionState = 'granted';
        const enCamino = orders.find((order) => order.estado === 'en_camino');
        if (enCamino) {
          showAlert('Permiso concedido. Activando GPS del pedido en camino...', true);
          startGpsTracking(enCamino.id_pedido);
        } else {
          showAlert('Permiso de ubicacion concedido. Marca "Salgo ahora" en un pedido para empezar a compartir tu posicion.', true);
        }
        renderGpsPanel();
      },
      (error) => {
        if (error?.code === 1) permissionState = 'denied';
        showAlert(gpsErrorMessage(error), false);
        renderGpsPanel();
      },
      {enableHighAccuracy: true, maximumAge: 0, timeout: 20000},
    );
  };
  const startGpsWatch = () => {
    if (!gpsOrderId) return;
    if (gpsWatchId !== null) navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = navigator.geolocation.watchPosition(
      (position) => {
        gpsWatchRetries = 0;
        sendGpsPosition(gpsOrderId, position).catch(() => {});
      },
      (error) => handleWatchError(error),
      {enableHighAccuracy: true, maximumAge: 10000, timeout: 20000},
    );
  };
  const handleWatchError = (error) => {
    if (error?.code === 1) {
      showAlert(gpsErrorMessage(error), false);
      stopGpsTracking(gpsOrderId);
      render();
      return;
    }
    if (gpsWatchRetries >= GPS_MAX_WATCH_RETRIES) {
      showAlert('El GPS dejo de actualizar. Revisa el permiso de ubicacion y la senal del telefono.', false);
      return;
    }
    gpsWatchRetries += 1;
    showAlert(`Reintentando GPS (${gpsWatchRetries}/${GPS_MAX_WATCH_RETRIES})...`, 'warning');
    startGpsWatch();
  };
  const activateGpsTracking = async (orderId, firstPosition) => {
    gpsOrderId = Number(orderId || 0);
    lastGpsSentAt = 0;
    lastGpsFixAt = Date.now();
    permissionState = 'granted';
    await sendGpsPosition(gpsOrderId, firstPosition, {force: true});
    startGpsWatch();
    startGpsWatchdog();
    gpsStatusByOrder[gpsOrderId] = 'active';
    showAlert('GPS activo: primera ubicacion guardada correctamente. Manten esta pantalla abierta.', true);
    render();
  };
  const startGpsWatchdog = () => {
    if (gpsWatchdogTimer) window.clearInterval(gpsWatchdogTimer);
    gpsWatchdogTimer = window.setInterval(() => {
      if (gpsWatchId === null || !lastGpsFixAt) return;
      if (Date.now() - lastGpsFixAt > GPS_STALE_MS) {
        showAlert('Hace rato que no llega tu ubicacion GPS. Verifica la senal y que el permiso siga activo.', 'warning');
      }
    }, 15000);
  };
  const gpsErrorMessage = (error) => {
    if (error?.code === 1) return 'Permiso de ubicacion denegado. Activalo en el candado/ajustes del navegador para usar GPS delivery.';
    if (error?.code === 2) return 'No se pudo obtener la ubicacion del telefono. Activa el GPS/ubicacion del dispositivo.';
    if (error?.code === 3) return 'El telefono tardo demasiado en entregar la ubicacion GPS. Reintenta en una zona con mejor senal.';
    return 'No se pudo activar GPS. Revisa permisos, HTTPS y que la ubicacion del telefono este encendida.';
  };
  const stopGpsTracking = (orderId) => {
    if (orderId && gpsOrderId && Number(orderId) !== Number(gpsOrderId)) return;
    if (gpsWatchdogTimer) {
      window.clearInterval(gpsWatchdogTimer);
      gpsWatchdogTimer = null;
    }
    if (gpsWatchId !== null) {
      navigator.geolocation.clearWatch(gpsWatchId);
      gpsWatchId = null;
    }
    if (gpsOrderId) delete gpsStatusByOrder[gpsOrderId];
    gpsOrderId = null;
    lastGpsSentAt = 0;
    lastGpsFixAt = 0;
    gpsWatchRetries = 0;
  };
  const sendGpsPosition = async (orderId, position, options = {}) => {
    if (!orderId || !position?.coords) return;
    lastGpsFixAt = Date.now();
    const now = Date.now();
    if (!options.force && now - lastGpsSentAt < 15000) return;
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
  const saveDestination = async (orderId) => {
    const input = document.querySelector(`[data-destination-input="${orderId}"]`);
    const key = String(orderId);
    destinationFeedbacks[key] = {message: 'Guardando destino...', ok: true};
    render();
    try {
      await apiJson(`/api/gastronomia/delivery/ruta/pedidos/${orderId}/destino`, {
        method: 'POST',
        body: JSON.stringify({ubicacion_entrega_url: input?.value || ''}),
      });
      delete destinationDrafts[key];
      destinationFeedbacks[key] = {message: input?.value ? 'Destino guardado correctamente.' : 'Destino borrado correctamente.', ok: true};
      showAlert(input?.value ? 'Destino guardado correctamente.' : 'Destino borrado correctamente.', true);
      await load({keepAlert: true});
    } catch (error) {
      destinationFeedbacks[key] = {message: `No se pudo guardar: ${error.message}`, ok: false};
      render();
      throw error;
    }
  };
  const clearDestination = async (orderId) => {
    const input = document.querySelector(`[data-destination-input="${orderId}"]`);
    if (input) input.value = '';
    destinationDrafts[String(orderId)] = '';
    await saveDestination(orderId);
  };
  ordersBox.addEventListener('input', (event) => {
    const input = event.target.closest('[data-destination-input]');
    if (!input) return;
    destinationDrafts[String(input.dataset.destinationInput)] = input.value;
  });
  ordersBox.addEventListener('click', (event) => {
    const copyButton = event.target.closest('[data-copy-tracking]');
    if (copyButton) {
      copyTrackingLink(copyButton.dataset.copyTracking).catch((error) => showAlert(error.message, false));
      return;
    }
    const destinationButton = event.target.closest('[data-save-destination]');
    if (destinationButton) {
      saveDestination(destinationButton.dataset.saveDestination).catch((error) => showAlert(error.message, false));
      return;
    }
    const clearDestinationButton = event.target.closest('[data-clear-destination]');
    if (clearDestinationButton) {
      clearDestination(clearDestinationButton.dataset.clearDestination).catch((error) => showAlert(error.message, false));
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
  gpsPanel?.addEventListener('click', (event) => {
    if (event.target.closest('#route-test-gps')) testGpsPermission();
  });
  refreshButton?.addEventListener('click', () => load().catch((error) => showAlert(error.message, false)));
  trackPermissionState();
  renderGpsPanel();
  load().catch((error) => showAlert(error.message, false));
  refreshTimer = window.setInterval(() => load({keepAlert: true}).catch(() => {}), 10000);
  window.addEventListener('beforeunload', () => {
    if (refreshTimer) window.clearInterval(refreshTimer);
    stopGpsTracking();
  });
}());
