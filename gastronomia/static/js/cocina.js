(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const board = document.getElementById('kds-board');
  const alertBox = document.getElementById('kds-alert');
  let lastEventId = 0;
  let pollTimer = null;
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
  ];
  const stateMeta = {
    enviado_cocina: {
      label: 'Nuevo',
      pill: 'border-amber-400/20 bg-amber-400/15 text-amber-300',
      action: 'Pasar a preparacion',
      actionClass: 'bg-sky-500 hover:bg-sky-400 focus:ring-sky-300',
    },
    preparando: {
      label: 'En preparacion',
      pill: 'border-emerald-400/20 bg-emerald-400/15 text-emerald-300',
      action: 'Marcar como listo',
      actionClass: 'bg-emerald-500 hover:bg-emerald-400 focus:ring-emerald-300',
    },
    listo: {
      label: 'Listo',
      pill: 'border-sky-400/20 bg-sky-400/15 text-sky-300',
    },
  };

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
  const ageMinutes = (iso) => {
    const start = new Date(iso || Date.now()).getTime();
    return Math.max(0, Math.floor((Date.now() - start) / 60000));
  };
  const elapsed = (iso) => `${ageMinutes(iso)} min`;
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
  const timeDotClass = (order) => {
    const minutes = ageMinutes(order.fecha_envio_cocina || order.fecha_creacion);
    if (minutes >= 12) return 'bg-red-400 shadow-red-400/40';
    if (minutes >= 7) return 'bg-orange-400 shadow-orange-400/40';
    if (minutes >= 4) return 'bg-amber-400 shadow-amber-400/40';
    return 'bg-emerald-400 shadow-emerald-400/40';
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
    const groups = Object.fromEntries(columns.map((column) => [column.key, []]));
    orders.forEach((order) => {
      if (groups[order.estado]) groups[order.estado].push(order);
    });
    const total = Object.values(groups).reduce((acc, current) => acc + current.length, 0);
    board.innerHTML = columns.map((column) => renderColumn(column, groups[column.key] || [])).join('');
    if (!total) {
      board.innerHTML = `
        <div class="rounded-2xl border border-dashed border-slate-700/80 bg-slate-900/45 p-10 text-center text-slate-400 xl:col-span-3">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-slate-500">
            <i class="fas fa-check"></i>
          </div>
          <p class="text-base font-bold text-slate-300">Sin pedidos pendientes en cocina.</p>
          <p class="mt-1 text-sm">Los pedidos enviados desde el POS apareceran aca automaticamente.</p>
        </div>
      `;
    }
  };
  const renderColumn = (column, orders) => `
    <section class="kds-column">
      <div class="mb-4 flex items-center justify-between gap-3 border-b border-slate-700/60 pb-3">
        <div class="flex items-center gap-3">
          <span class="flex h-9 w-9 items-center justify-center rounded-lg border ${column.iconBox}">
            <i class="fas ${column.icon}"></i>
          </span>
          <div>
            <p class="text-xs font-black uppercase tracking-[0.20em] ${column.accent}">Cocina</p>
            <h2 class="text-lg font-black text-slate-100">${column.title}</h2>
          </div>
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
    <article class="kds-card" data-order="${order.id_pedido}">
      <div class="flex items-start justify-between gap-3">
        <div class="flex min-w-0 gap-3">
          <div class="border-r border-slate-700/80 pr-3">
            <h2 class="text-2xl font-black leading-none text-slate-100">#${order.id_pedido}</h2>
            <p class="mt-2 flex items-center gap-2 text-xs font-bold text-slate-400">
              <span class="h-2 w-2 rounded-full shadow-lg ${timeDotClass(order)}"></span>
              ${elapsed(order.fecha_envio_cocina || order.fecha_creacion)}
            </p>
          </div>
          <div class="min-w-0 pt-0.5">
            <p class="truncate text-sm font-black text-slate-200">${displayOrigin(order)}</p>
            <div class="mt-3 space-y-1.5">
              ${(order.items || []).map((item) => `
                <div class="grid grid-cols-[auto_1fr] gap-2 text-sm leading-tight">
                  <span class="font-black text-slate-100">${item.cantidad}</span>
                  <span class="text-slate-200">${escapeHtml(item.nombre_producto)}</span>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
        <span class="shrink-0 rounded-lg border px-2 py-1 text-[10px] font-black uppercase tracking-wide ${stateMeta[order.estado]?.pill || 'border-slate-600 bg-slate-800 text-slate-300'}">${stateMeta[order.estado]?.label || escapeHtml(order.estado)}</span>
      </div>
      <div class="mt-4 space-y-2">
        ${renderDetails(order)}
      </div>
      <div class="mt-3 flex items-center justify-end border-t border-slate-700/70 pt-3">
        <span class="text-sm font-black text-slate-200">${money(order.total)}</span>
      </div>
      ${renderActions(order)}
    </article>
  `;
  const renderDetails = (order) => {
    const itemDetails = (order.items || []).map((item) => {
      const modifierText = item.modificadores?.length ? item.modificadores.map(displayModifier).join(', ') : '';
      const modifiers = modifierText ? renderNote(modifierText, 'mt-1 text-xs font-semibold text-slate-400') : '';
      const notes = item.notas
        ? renderNote(item.notas, 'mt-2 rounded-lg border border-amber-400/20 bg-amber-400/10 px-2 py-1 text-xs font-bold text-amber-200')
        : '';
      return modifiers || notes ? `<div>${modifiers}${notes}</div>` : '';
    }).join('');
    const orderNotes = order.notas
      ? renderNote(order.notas, 'rounded-lg border border-amber-400/25 bg-amber-400/10 p-2 text-xs font-bold text-amber-200')
      : '';
    return `${itemDetails}${orderNotes}`;
  };
  const renderActions = (order) => {
    if (order.estado === 'enviado_cocina') {
      return `
        <div class="mt-3">
          <button type="button" data-action="tomar" class="w-full rounded-lg px-4 py-3 text-sm font-black text-white shadow-lg shadow-sky-950/30 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 ${stateMeta.enviado_cocina.actionClass}">${stateMeta.enviado_cocina.action}</button>
        </div>
      `;
    }
    if (order.estado === 'preparando') {
      return `
        <div class="mt-3">
          <button type="button" data-action="listo" class="w-full rounded-lg px-4 py-3 text-sm font-black text-white shadow-lg shadow-emerald-950/30 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 ${stateMeta.preparando.actionClass}">${stateMeta.preparando.action}</button>
        </div>
      `;
    }
    return `
      <div class="mt-3 rounded-lg border border-sky-400/20 bg-sky-400/10 px-4 py-3 text-center text-sm font-black text-sky-200">
        Esperando entrega o retiro
      </div>
    `;
  };
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
