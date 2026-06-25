(function () {
  if (window.__gastroKdsCleanup) window.__gastroKdsCleanup();
  const root = document.querySelector('[data-gastro-kds]');
  const csrf = document.getElementById('csrf-token')?.value || '';
  const board = document.getElementById('kds-board');
  const alertBox = document.getElementById('kds-alert');
  const soundEnabledInput = document.getElementById('kds-sound-enabled');
  const soundProfileInput = document.getElementById('kds-sound-profile');
  const soundVolumeInput = document.getElementById('kds-sound-volume');
  const soundVolumeLabel = document.getElementById('kds-sound-volume-label');
  const testSoundButton = document.getElementById('kds-test-sound');
  const settingsToggle = document.getElementById('kds-settings-toggle');
  const settingsPanel = document.getElementById('kds-toolbar');
  if (!root || !board || !alertBox) return;

  let orders = [];
  let lastEventId = 0;
  let pollTimer = null;
  let tickTimer = null;
  let lastPaintedMinutes = new Map();
  let destroyed = false;
  let audioContext = null;
  const activeControllers = new Set();
  const pendingOrders = new Set();
  let soundSettings = {enabled: true, profile: 'clasico', volume: 65};
  const kitchenStates = new Set(['enviado_cocina', 'preparando', 'listo', 'en_camino']);
  const nextStateByAction = {tomar: 'preparando', listo: 'listo', salir: 'en_camino', entregar: 'entregado'};
  const columns = [
    {
      key: 'enviado_cocina',
      title: 'Por preparar',
      icon: 'fa-clipboard-list',
      accent: 'text-amber-300',
      iconBox: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
      counter: 'bg-amber-400 text-slate-950',
    },
    {
      key: 'preparando',
      title: 'En preparacion',
      icon: 'fa-utensils',
      accent: 'text-emerald-300',
      iconBox: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
      counter: 'bg-emerald-400 text-slate-950',
    },
    {
      key: 'listo',
      title: 'Listo',
      icon: 'fa-circle-check',
      accent: 'text-sky-300',
      iconBox: 'border-sky-400/30 bg-sky-400/10 text-sky-300',
      counter: 'bg-sky-400 text-slate-950',
    },
    {
      key: 'en_camino',
      title: 'En camino',
      icon: 'fa-motorcycle',
      accent: 'text-rose-300',
      iconBox: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
      counter: 'bg-rose-400 text-slate-950',
    },
  ];
  const stateMeta = {
    enviado_cocina: {
      label: 'Nuevo',
      pill: 'border-amber-400/20 bg-amber-400/15 text-amber-300',
      action: 'Pasar a preparacion',
      actionClass: 'bg-sky-500 hover:bg-sky-400 focus:ring-sky-300',
    },
    preparando: {
      label: 'Preparando',
      pill: 'border-emerald-400/20 bg-emerald-400/15 text-emerald-300',
      action: 'Marcar como listo',
      actionClass: 'bg-emerald-500 hover:bg-emerald-400 focus:ring-emerald-300',
    },
    listo: {
      label: 'Listo',
      pill: 'border-sky-400/20 bg-sky-400/15 text-sky-300',
      action: 'Marcar entregado',
      actionClass: 'bg-sky-500 hover:bg-sky-400 focus:ring-sky-300',
    },
    en_camino: {
      label: 'En camino',
      pill: 'border-rose-400/20 bg-rose-400/15 text-rose-300',
      action: 'Marcar entregado',
      actionClass: 'bg-rose-500 hover:bg-rose-400 focus:ring-rose-300',
    },
  };

  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const apiJson = async (url, options = {}) => {
    const controller = new AbortController();
    activeControllers.add(controller);
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {})},
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
      return data;
    } finally {
      activeControllers.delete(controller);
    }
  };
  const parseTimestamp = (iso) => {
    if (!iso) return Date.now();
    const value = String(iso);
    const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
    const normalized = /^\d{4}-\d{2}-\d{2}T/.test(value) && !hasTimezone ? `${value}Z` : value;
    const timestamp = new Date(normalized).getTime();
    return Number.isNaN(timestamp) ? Date.now() : timestamp;
  };
  const ageMinutes = (iso) => Math.max(0, Math.floor((Date.now() - parseTimestamp(iso)) / 60000));
  const elapsed = (iso) => `${ageMinutes(iso)} min`;
  const orderMinutes = (order) => ageMinutes(order.fecha_envio_cocina || order.fecha_creacion);
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const displayModifier = (modifier) => (
    modifier?.tipo_grupo === 'ingrediente_removible' ? `Sin ${modifier.nombre_opcion}` : modifier?.nombre_opcion
  );
  const displayOrigin = (order) => {
    if (order.mesa) return `Mesa ${escapeHtml(order.mesa)}`;
    const type = String(order.tipo_pedido || 'mostrador').replace(/_/g, ' ');
    return escapeHtml(type.charAt(0).toUpperCase() + type.slice(1));
  };
  const deliveryCode = (order) => escapeHtml(order.codigo_entrega || `#${String(order.id_pedido || 0).padStart(3, '0')}`);
  const timeDotClass = (order) => {
    const minutes = ageMinutes(order.fecha_envio_cocina || order.fecha_creacion);
    if (minutes >= 12) return 'bg-red-500';
    if (minutes >= 7) return 'bg-orange-500';
    if (minutes >= 4) return 'bg-amber-500';
    return 'bg-emerald-500';
  };
  const cardUrgencyClass = (order) => {
    const minutes = ageMinutes(order.fecha_envio_cocina || order.fecha_creacion);
    if (minutes >= 12) return 'kds-card--late';
    if (minutes >= 6) return 'kds-card--soon';
    return 'kds-card--fresh';
  };
  const isExclusionNote = (note) => /\b(sin|no|quitar|sacar|excluir|evitar|alergia|alergico|al[eé]rgico)\b/i.test(String(note || ''));
  const renderNote = (note, normalClasses) => {
    if (!note) return '';
    if (!isExclusionNote(note)) return `<p class="${normalClasses}">${escapeHtml(note)}</p>`;
    return `
      <p class="kds-warning-note flex items-start gap-2 rounded-lg p-3 text-sm font-black uppercase tracking-wide">
        <i class="fas fa-triangle-exclamation mt-0.5 shrink-0"></i>
        <span>${escapeHtml(note)}</span>
      </p>
    `;
  };
  const syncSoundControls = () => {
    if (soundEnabledInput) soundEnabledInput.checked = Boolean(soundSettings.enabled);
    if (soundProfileInput) soundProfileInput.value = soundSettings.profile || 'clasico';
    if (soundVolumeInput) soundVolumeInput.value = Number(soundSettings.volume || 0);
    if (soundVolumeLabel) soundVolumeLabel.textContent = `${Number(soundSettings.volume || 0)}%`;
  };
  const loadSoundSettings = async () => {
    const data = await apiJson('/api/gastronomia/cocina/preferencias-sonido');
    soundSettings = {...soundSettings, ...(data.preferencias || {})};
    syncSoundControls();
  };
  const saveSoundSettings = async (partial = {}) => {
    soundSettings = {
      ...soundSettings,
      ...partial,
      enabled: Boolean(partial.enabled ?? soundEnabledInput?.checked ?? soundSettings.enabled),
      profile: partial.profile || soundProfileInput?.value || soundSettings.profile,
      volume: Number(partial.volume ?? soundVolumeInput?.value ?? soundSettings.volume),
    };
    syncSoundControls();
    const data = await apiJson('/api/gastronomia/cocina/preferencias-sonido', {
      method: 'POST',
      body: JSON.stringify(soundSettings),
    });
    soundSettings = {...soundSettings, ...(data.preferencias || {})};
    syncSoundControls();
  };
  const getAudioContext = () => {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioContext) audioContext = new Ctx();
    if (audioContext.state === 'suspended') audioContext.resume().catch(() => {});
    return audioContext;
  };
  const beep = (context, when, frequency, duration, gainValue) => {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, when);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, gainValue), when + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, when + duration);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(when);
    oscillator.stop(when + duration + 0.02);
  };
  const profileSequence = (profile) => {
    if (profile === 'suave') return [[0, 740, 0.14], [0.18, 880, 0.18]];
    if (profile === 'urgente') return [[0, 830, 0.12], [0.15, 830, 0.12], [0.3, 1100, 0.22]];
    return [[0, 740, 0.14], [0.17, 988, 0.18], [0.39, 740, 0.14]];
  };
  const playKitchenSound = async () => {
    if (!soundSettings.enabled) return;
    const context = getAudioContext();
    if (!context) return;
    const gainValue = Math.max(0.0001, Math.min(0.35, Number(soundSettings.volume || 0) / 260));
    const startAt = context.currentTime + 0.01;
    profileSequence(soundSettings.profile).forEach(([offset, frequency, duration]) => {
      beep(context, startAt + offset, frequency, duration, gainValue);
    });
  };

  const loadBoard = async () => {
    const data = await apiJson('/api/gastronomia/cocina/pedidos');
    if (destroyed) return;
    orders = data.pedidos || [];
    lastEventId = Math.max(lastEventId, Number(data.ultimo_evento_id || 0));
    render(orders);
  };
  const pollEvents = async () => {
    if (destroyed || pendingOrders.size) return;
    try {
      const data = await apiJson(`/api/gastronomia/cocina/eventos?after=${lastEventId}`);
      if (destroyed) return;
      const events = data.eventos || [];
      lastEventId = Math.max(lastEventId, Number(data.ultimo_evento_id || 0), ...events.map((event) => Number(event.id_evento || 0)));
      if (events.length) applyOrderEvents(events);
    } catch (error) {
      if (error.name === 'AbortError' || destroyed) return;
      showAlert(error.message, false);
    }
  };
  const applyOrderEvents = (events) => {
    const newIncomingOrders = events.filter((event) => {
      const order = event?.payload?.pedido;
      if (!order?.id_pedido || order.estado !== 'enviado_cocina') return false;
      return !orders.some((item) => Number(item.id_pedido) === Number(order.id_pedido));
    }).length;
    let changed = false;
    events.forEach((event) => {
      const order = event?.payload?.pedido;
      if (!order?.id_pedido) return;
      changed = applyOrderSnapshot(order) || changed;
    });
    if (!changed) return;
    sortOrders();
    render(orders);
    if (newIncomingOrders > 0) playKitchenSound().catch(() => {});
  };
  const applyOrderSnapshot = (order) => {
    const orderId = Number(order.id_pedido);
    const index = orders.findIndex((item) => Number(item.id_pedido) === orderId);
    const visible = kitchenStates.has(order.estado);
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
      const dateDiff = parseTimestamp(a.fecha_envio_cocina || a.fecha_creacion)
        - parseTimestamp(b.fecha_envio_cocina || b.fecha_creacion);
      return dateDiff || Number(a.id_pedido || 0) - Number(b.id_pedido || 0);
    });
  };
  const render = (orders) => {
    if (destroyed) return;
    const groups = Object.fromEntries(columns.map((column) => [column.key, []]));
    orders.forEach((order) => {
      if (groups[order.estado]) groups[order.estado].push(order);
    });
    const total = Object.values(groups).reduce((acc, current) => acc + current.length, 0);
    board.innerHTML = columns.map((column) => renderColumn(column, groups[column.key] || [])).join('');
    if (!total) {
      board.innerHTML = `
        <div class="rounded-2xl border border-dashed border-slate-700/80 bg-slate-900/45 p-10 text-center text-slate-400 xl:col-span-4">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-slate-500">
            <i class="fas fa-check"></i>
          </div>
          <p class="text-base font-bold text-slate-300">Sin pedidos pendientes en cocina.</p>
          <p class="mt-1 text-sm">Los pedidos enviados desde el POS apareceran aca automaticamente.</p>
        </div>
      `;
    }
    lastPaintedMinutes = new Map(orders.map((order) => [Number(order.id_pedido), orderMinutes(order)]));
  };
  // Repinta el tablero cuando el contador de minutos de algun pedido cambia,
  // independientemente del polling de eventos (que no re-renderiza si no hay cambios).
  const minutesHaveChanged = () => orders.some((order) => orderMinutes(order) !== lastPaintedMinutes.get(Number(order.id_pedido)));
  const tickIfNeeded = () => {
    if (destroyed) return;
    if (minutesHaveChanged()) render(orders);
  };
  const renderColumn = (column, orders) => `
    <section class="kds-column">
      <div class="mb-2 flex items-center justify-between gap-3 border-b border-slate-700/60 pb-2">
        <div class="flex items-center gap-2">
          <span class="flex h-8 w-8 items-center justify-center rounded-lg border ${column.iconBox}">
            <i class="fas ${column.icon}"></i>
          </span>
          <h2 class="text-base font-black text-slate-100">${column.title}</h2>
        </div>
        <span class="inline-flex h-7 min-w-7 items-center justify-center rounded-full px-2 text-sm font-black ${column.counter}">${orders.length}</span>
      </div>
      <div class="kds-column-body space-y-3">
        ${orders.length ? orders.map(renderOrder).join('') : `
          <div class="rounded-xl border border-dashed border-slate-700/80 bg-slate-900/40 p-5 text-center text-sm font-semibold text-slate-500">
            Sin pedidos en esta columna.
          </div>
        `}
      </div>
    </section>
  `;
  const renderOrder = (order) => `
    <article class="kds-card ${cardUrgencyClass(order)}" data-order="${order.id_pedido}">
      <div class="kds-order-top">
        <div class="kds-order-code border-r border-slate-700/80 pr-3">
          <h2 class="text-xl font-black leading-none text-slate-100">${deliveryCode(order)}</h2>
          <p class="mt-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">Pedido #${order.id_pedido}</p>
          <p class="mt-2 flex items-center gap-2 text-xs font-bold text-slate-400">
              <span class="h-2.5 w-2.5 rounded-full ${timeDotClass(order)}"></span>
              ${elapsed(order.fecha_envio_cocina || order.fecha_creacion)}
          </p>
        </div>
        <div class="kds-order-info">
          <div class="flex items-start justify-between gap-2">
            <p class="kds-origin text-sm font-black text-slate-200">${displayOrigin(order)}</p>
            <span class="kds-state-pill shrink-0 rounded-lg border px-2 py-1 text-[10px] font-black uppercase tracking-wide ${stateMeta[order.estado]?.pill || 'border-slate-600 bg-slate-800 text-slate-300'}">${stateMeta[order.estado]?.label || escapeHtml(order.estado)}</span>
          </div>
          ${order.referencia_entrega ? `<p class="mt-1 text-xs font-black uppercase tracking-wide text-sky-200">${escapeHtml(order.referencia_entrega)}</p>` : ''}
          ${order.celular_cliente ? `<p class="mt-1 kds-contact text-xs font-bold text-slate-400">Cel: ${escapeHtml(order.celular_cliente)}</p>` : ''}
          ${order.direccion_entrega ? `<p class="mt-1 kds-contact text-xs font-bold text-slate-400">Dir: ${escapeHtml(order.direccion_entrega)}</p>` : ''}
        </div>
      </div>
      <div class="kds-items">
        ${(order.items || []).map(renderItem).join('')}
      </div>
      ${renderOrderNotes(order)}
      ${renderActions(order)}
    </article>
  `;
  const renderItemExtras = (item) => {
    const modifierText = item.modificadores?.length ? item.modificadores.map(displayModifier).join(', ') : '';
    const modifiers = modifierText ? renderNote(modifierText, 'text-xs font-semibold text-slate-400') : '';
    const notes = item.notas
      ? renderNote(item.notas, 'rounded-lg border border-amber-400/20 bg-amber-400/10 px-2 py-1 text-xs font-bold text-amber-200')
      : '';
    return modifiers || notes ? `<div class="kds-item-extra">${modifiers}${notes}</div>` : '';
  };
  const renderItem = (item) => `
    <div class="kds-item">
      <div class="kds-item-row">
        <span class="kds-item-qty">${item.cantidad}</span>
        <span class="kds-item-name text-slate-200">${escapeHtml(item.nombre_producto)}</span>
      </div>
      ${renderItemExtras(item)}
    </div>
  `;
  const renderOrderNotes = (order) => (
    order.notas
      ? `<div class="mt-3">${renderNote(order.notas, 'rounded-lg border border-amber-400/25 bg-amber-400/10 p-2 text-xs font-bold text-amber-200')}</div>`
      : ''
  );
  const renderActions = (order) => {
    const pending = pendingOrders.has(Number(order.id_pedido));
    const disabledAttrs = pending ? 'disabled aria-busy="true"' : '';
    const disabledClass = pending ? ' opacity-70 cursor-not-allowed' : '';
    if (order.estado === 'enviado_cocina') {
      return `
        <div class="mt-3">
          <button type="button" data-action="tomar" ${disabledAttrs} class="w-full rounded-lg px-4 py-3.5 text-base font-black text-white shadow-lg shadow-sky-950/30 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 ${stateMeta.enviado_cocina.actionClass}${disabledClass}">${pending ? 'Actualizando...' : stateMeta.enviado_cocina.action}</button>
        </div>
      `;
    }
    if (order.estado === 'preparando') {
      return `
        <div class="mt-3">
          <button type="button" data-action="listo" ${disabledAttrs} class="w-full rounded-lg px-4 py-3.5 text-base font-black text-white shadow-lg shadow-emerald-950/30 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 ${stateMeta.preparando.actionClass}${disabledClass}">${pending ? 'Actualizando...' : stateMeta.preparando.action}</button>
        </div>
      `;
    }
    if (order.estado === 'listo' && order.tipo_pedido === 'delivery') {
      return `
        <div class="mt-3 space-y-2">
          <div class="rounded-lg border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-center text-sm font-black text-sky-200">
            Listo para delivery
          </div>
          <button type="button" data-action="salir" ${disabledAttrs} class="w-full rounded-lg px-4 py-3.5 text-base font-black text-white shadow-lg shadow-sky-950/30 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 ${stateMeta.listo.actionClass}${disabledClass}">${pending ? 'Actualizando...' : 'Marcar en camino'}</button>
        </div>
      `;
    }
    const meta = stateMeta[order.estado] || stateMeta.listo;
    return `
      <div class="mt-3 space-y-2">
        <div class="rounded-lg border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-center text-sm font-black text-sky-200">
          Esperando entrega o retiro
        </div>
        <button type="button" data-action="entregar" ${disabledAttrs} class="w-full rounded-lg px-4 py-3.5 text-base font-black text-white shadow-lg shadow-sky-950/30 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 ${meta.actionClass}${disabledClass}">${pending ? 'Actualizando...' : meta.action}</button>
      </div>
    `;
  };
  const changeState = async (orderId, action, button) => {
    const numericOrderId = Number(orderId || 0);
    const nextState = nextStateByAction[action];
    const currentOrder = orders.find((order) => Number(order.id_pedido) === numericOrderId);
    const previousOrder = currentOrder ? structuredOrderClone(currentOrder) : null;
    if (!numericOrderId || !nextState || pendingOrders.has(numericOrderId)) return;

    pendingOrders.add(numericOrderId);
    setButtonBusy(button, true);
    if (currentOrder) {
      applyOrderSnapshot(buildOptimisticOrder(currentOrder, nextState));
      sortOrders();
      render(orders);
    }

    try {
      const data = await apiJson(`/api/gastronomia/cocina/pedidos/${numericOrderId}/${action}`, {method: 'POST', body: '{}'});
      if (destroyed) return;
      if (data?.pedido?.id_pedido) {
        applyOrderSnapshot(data.pedido);
        sortOrders();
        render(orders);
        showAlert(`Pedido #${data.pedido.id_pedido} actualizado.`, true);
      } else {
        showAlert(`Pedido #${numericOrderId} actualizado.`, true);
      }
      await loadBoard();
    } catch (error) {
      if (previousOrder) {
        applyOrderSnapshot(previousOrder);
        sortOrders();
        render(orders);
      }
      await loadBoard().catch(() => {});
      throw error;
    } finally {
      pendingOrders.delete(numericOrderId);
      setButtonBusy(button, false);
      render(orders);
    }
  };
  const structuredOrderClone = (order) => JSON.parse(JSON.stringify(order));
  const buildOptimisticOrder = (order, nextState) => {
    const now = new Date().toISOString();
    return {
      ...structuredOrderClone(order),
      estado: nextState,
      fecha_inicio_preparacion: nextState === 'preparando' ? (order.fecha_inicio_preparacion || now) : order.fecha_inicio_preparacion,
      fecha_listo: nextState === 'listo' ? (order.fecha_listo || now) : order.fecha_listo,
      fecha_entrega: nextState === 'entregado' ? (order.fecha_entrega || now) : order.fecha_entrega,
    };
  };
  const setButtonBusy = (button, busy) => {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle('opacity-70', busy);
    button.classList.toggle('cursor-not-allowed', busy);
    if (busy) {
      button.dataset.originalText = button.textContent;
      button.textContent = 'Actualizando...';
    } else if (button.dataset.originalText) {
      button.textContent = button.dataset.originalText;
      delete button.dataset.originalText;
    }
  };

  const handleBoardClick = (event) => {
    const button = event.target.closest('[data-action]');
    const card = event.target.closest('[data-order]');
    if (!button || !card) return;
    if (button.disabled) return;
    if (pendingOrders.has(Number(card.dataset.order || 0))) return;
    changeState(card.dataset.order, button.dataset.action, button).catch((error) => {
      if (error.name === 'AbortError' || destroyed) return;
      setButtonBusy(button, false);
      showAlert(error.message, false);
    });
  };
  const cleanup = () => {
    destroyed = true;
    clearInterval(pollTimer);
    clearInterval(tickTimer);
    board.removeEventListener('click', handleBoardClick);
    soundEnabledInput?.removeEventListener('change', handleSoundEnabledChange);
    soundProfileInput?.removeEventListener('change', handleSoundProfileChange);
    soundVolumeInput?.removeEventListener('input', handleSoundVolumeInput);
    soundVolumeInput?.removeEventListener('change', handleSoundVolumeChange);
    testSoundButton?.removeEventListener('click', handleTestSoundClick);
    settingsToggle?.removeEventListener('click', handleSettingsToggleClick);
    activeControllers.forEach((controller) => controller.abort());
    activeControllers.clear();
    if (window.__gastroKdsCleanup === cleanup) window.__gastroKdsCleanup = null;
  };
  const handleSoundEnabledChange = () => {
    saveSoundSettings({enabled: Boolean(soundEnabledInput?.checked)}).catch((error) => showAlert(error.message, false));
  };
  const handleSoundProfileChange = () => {
    saveSoundSettings({profile: soundProfileInput?.value || 'clasico'}).catch((error) => showAlert(error.message, false));
  };
  const handleSoundVolumeInput = () => {
    soundSettings.volume = Number(soundVolumeInput?.value || 0);
    syncSoundControls();
  };
  const handleSoundVolumeChange = () => {
    saveSoundSettings({volume: Number(soundVolumeInput?.value || 0)}).catch((error) => showAlert(error.message, false));
  };
  const handleTestSoundClick = () => {
    playKitchenSound().catch((error) => showAlert(error.message, false));
  };
  const setSettingsOpen = (open) => {
    if (!settingsPanel || !settingsToggle) return;
    settingsPanel.hidden = !open;
    settingsToggle.setAttribute('aria-expanded', String(open));
    try {
      localStorage.setItem('kds-settings-open', open ? '1' : '0');
    } catch (e) {}
  };
  const handleSettingsToggleClick = () => {
    setSettingsOpen(settingsPanel?.hidden ?? true);
  };

  window.__gastroKdsCleanup = cleanup;
  board.addEventListener('click', handleBoardClick);
  soundEnabledInput?.addEventListener('change', handleSoundEnabledChange);
  soundProfileInput?.addEventListener('change', handleSoundProfileChange);
  soundVolumeInput?.addEventListener('input', handleSoundVolumeInput);
  soundVolumeInput?.addEventListener('change', handleSoundVolumeChange);
  testSoundButton?.addEventListener('click', handleTestSoundClick);
  settingsToggle?.addEventListener('click', handleSettingsToggleClick);
  setSettingsOpen((() => {
    try {
      return localStorage.getItem('kds-settings-open') === '1';
    } catch (e) {
      return false;
    }
  })());
  loadSoundSettings().catch((error) => showAlert(error.message, false));
  loadBoard()
    .catch((error) => {
      if (error.name === 'AbortError' || destroyed) return;
      showAlert(error.message, false);
    })
    .finally(() => {
      if (!destroyed) {
        pollTimer = setInterval(pollEvents, 2000);
        tickTimer = setInterval(tickIfNeeded, 15000);
      }
    });
  window.addEventListener('beforeunload', cleanup, {once: true});
}());
