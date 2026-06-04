(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const root = document.querySelector('[data-gastro-salon]');
  const board = document.getElementById('salon-board');
  const alertBox = document.getElementById('salon-alert');
  const moveTableGrid = document.getElementById('move-table-grid');
  const puedeCobrar = root?.dataset.puedeCobrar === '1';
  const puedeEditarPedido = root?.dataset.puedeEditarPedido === '1';
  const estadosCobrables = new Set(['abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado']);
  let mesas = [];
  let mesaDestino = '';

  const estadoStyles = {
    libre: 'bg-emerald-100 text-emerald-800',
    ocupada: 'bg-sky-100 text-sky-800',
    esperando_cocina: 'bg-amber-100 text-amber-800',
    listo: 'bg-rose-100 text-rose-800',
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
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));

  const loadSalon = async () => {
    const data = await apiJson('/api/gastronomia/salon/estado');
    mesas = data.mesas || [];
    renderBoard();
    renderMoveGrid();
  };
  const renderBoard = () => {
    board.innerHTML = mesas.map(renderMesa).join('') || `
      <div class="rounded-xl border border-dashed border-gray-300 p-10 text-center text-gray-500 dark:border-gray-700 sm:col-span-2 lg:col-span-3">
        Carga las primeras mesas del salon.
      </div>
    `;
  };
  const renderMesa = (mesa) => {
    const pedidos = Array.isArray(mesa.pedidos_activos) && mesa.pedidos_activos.length
      ? mesa.pedidos_activos
      : (mesa.pedido_activo ? [mesa.pedido_activo] : []);
    const statusClass = estadoStyles[mesa.estado_salon] || 'bg-gray-100 text-gray-800';
    return `
      <article class="salon-card" data-table="${mesa.id_mesa}">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-2xl font-black text-gray-900 dark:text-white">${escapeHtml(mesa.nombre)}</h2>
            <p class="mt-1 text-sm font-semibold text-gray-500">${escapeHtml(mesa.ubicacion || 'Salon')} - ${mesa.capacidad} lugares</p>
          </div>
          <span class="rounded-full px-3 py-1 text-xs font-bold ${statusClass}">${escapeHtml(mesa.estado_salon)}</span>
        </div>
        ${pedidos.length > 1 ? `
          <p class="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">
            ${pedidos.length} pedidos activos en esta mesa
          </p>
        ` : ''}
        ${pedidos.map(renderPedidoResumen).join('')}
        <div class="mt-4 grid gap-2">
          ${renderNuevoPedidoAccion(mesa)}
        </div>
      </article>
    `;
  };
  const renderPedidoResumen = (pedido) => {
    const editable = pedido?.estado === 'abierto' && !pedido?.pagado;
    const cobrable = estadosCobrables.has(pedido?.estado) && !pedido?.pagado;
    return `
      <div class="mt-4 rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
        <div class="flex justify-between gap-3">
          <strong class="text-gray-900 dark:text-white">Pedido #${pedido.id_pedido}</strong>
          <span class="font-bold text-emerald-700 dark:text-emerald-300">${money(pedido.total)}</span>
        </div>
        <p class="mt-1 text-sm text-gray-500">${escapeHtml(pedido.estado)}</p>
        ${renderPedidoAcciones(pedido, editable, cobrable)}
      </div>
    `;
  };
  const renderPedidoAcciones = (pedido, editable, cobrable) => {
    const acciones = [];
    if (editable && puedeEditarPedido) {
      acciones.push(`
        <a href="/gastronomia/pos?pedido=${encodeURIComponent(pedido.id_pedido)}"
           class="rounded-lg border border-amber-200 px-3 py-2 text-center text-xs font-bold text-amber-700 hover:bg-amber-50">
          Editar pedido
        </a>
      `);
    }
    if (cobrable && puedeCobrar) {
      acciones.push(`
        <a href="/gastronomia/caja?pedido=${encodeURIComponent(pedido.id_pedido)}"
           class="rounded-lg border border-emerald-200 px-3 py-2 text-center text-xs font-bold text-emerald-700 hover:bg-emerald-50">
          Cobrar pedido
        </a>
      `);
    }
    if (!acciones.length) return '';
    return `<div class="mt-3 grid gap-2 sm:grid-cols-2">${acciones.join('')}</div>`;
  };
  const renderNuevoPedidoAccion = (mesa) => {
    if (!puedeEditarPedido) return '';
    return `
      <a href="/gastronomia/pos?mesa=${encodeURIComponent(mesa.nombre)}"
         class="rounded-xl bg-indigo-600 px-4 py-3 text-center text-sm font-bold text-white hover:bg-indigo-700">
        Nuevo pedido
      </a>
    `;
  };
  const renderMoveGrid = () => {
    if (!moveTableGrid) return;
    moveTableGrid.innerHTML = mesas.map((mesa) => `
      <button
        type="button"
        data-move-table="${escapeHtml(mesa.nombre)}"
        class="mesa-boton ${mesaDestino === mesa.nombre ? 'activa' : ''}"
      >
        ${escapeHtml(mesa.nombre)}
      </button>
    `).join('') || '<div class="col-span-3 rounded-lg border border-dashed border-gray-300 p-4 text-center text-sm text-gray-500 dark:border-gray-700">Sin mesas cargadas.</div>';
  };
  const moveOrder = async () => {
    const pedidoId = Number(document.getElementById('move-order-id').value || 0);
    if (!pedidoId) throw new Error('Indica el numero de pedido.');
    if (!mesaDestino) throw new Error('Selecciona la mesa destino.');
    await apiJson(`/api/gastronomia/salon/pedidos/${pedidoId}/mover`, {
      method: 'POST',
      body: JSON.stringify({mesa: mesaDestino}),
    });
    showAlert(`Pedido #${pedidoId} movido.`, true);
    mesaDestino = '';
    document.getElementById('move-order-id').value = '';
    await loadSalon();
  };

  moveTableGrid?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-move-table]');
    if (!button) return;
    mesaDestino = button.dataset.moveTable || '';
    renderMoveGrid();
  });
  document.getElementById('move-order')?.addEventListener('click', () => {
    moveOrder().catch((error) => showAlert(error.message, false));
  });
  loadSalon().catch((error) => showAlert(error.message, false));
}());
