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
  const detallesPagadosAbiertos = new Set();

  const estadoStyles = {
    libre: 'bg-emerald-100 text-emerald-800',
    ocupada: 'bg-sky-100 text-sky-800',
    esperando_cocina: 'bg-amber-100 text-amber-800',
    listo: 'bg-rose-100 text-rose-800',
    pagada: 'bg-indigo-100 text-indigo-800',
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
    const pagado = Boolean(pedido?.pagado);
    const editable = pedido?.estado === 'abierto' && !pedido?.pagado;
    const cobrable = estadosCobrables.has(pedido?.estado) && !pedido?.pagado;
    return `
      <div class="mt-4 rounded-lg ${pagado ? 'bg-indigo-50 dark:bg-indigo-950/30' : 'bg-gray-50 dark:bg-gray-900/40'} p-3">
        <div class="flex justify-between gap-3">
          <strong class="text-gray-900 dark:text-white">Pedido #${pedido.id_pedido}</strong>
          <span class="font-bold text-emerald-700 dark:text-emerald-300">${money(pedido.total)}</span>
        </div>
        <p class="mt-1 text-sm font-semibold ${pagado ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-500'}">${pagado ? 'Pagado' : escapeHtml(pedido.estado)}</p>
        ${renderPedidoAcciones(pedido, editable, cobrable)}
        ${pagado ? renderPedidoPagadoDetalle(pedido) : ''}
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
    if (pedido?.pagado) {
      acciones.push(`
        <button type="button"
                data-toggle-paid-detail="${pedido.id_pedido}"
                class="rounded-lg border border-indigo-200 px-3 py-2 text-center text-xs font-bold text-indigo-700 hover:bg-indigo-50">
          Ver detalle
        </button>
      `);
      acciones.push(`
        <button type="button"
                data-release-table="${pedido.id_pedido}"
                class="rounded-lg border border-gray-300 px-3 py-2 text-center text-xs font-bold text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800">
          Liberar mesa
        </button>
      `);
    }
    if (!acciones.length) return '';
    return `<div class="mt-3 grid gap-2 sm:grid-cols-2">${acciones.join('')}</div>`;
  };
  const renderPedidoPagadoDetalle = (pedido) => {
    if (!detallesPagadosAbiertos.has(String(pedido.id_pedido))) return '';
    const items = Array.isArray(pedido.items) ? pedido.items : [];
    const pago = pedido.pago || {};
    return `
      <div class="mt-3 rounded-lg border border-indigo-100 bg-white p-3 text-sm text-gray-700 dark:border-indigo-900 dark:bg-gray-950 dark:text-gray-200">
        <div class="flex justify-between gap-3 font-bold">
          <span>Total cobrado</span>
          <span>${money(pago.total_cobrado || pedido.total)}</span>
        </div>
        <p class="mt-1 text-xs font-semibold text-gray-500">Metodo: ${escapeHtml(pago.metodo_pago || 'pendiente')}</p>
        <div class="mt-3 space-y-2">
          ${items.map((item) => `
            <div class="flex justify-between gap-3 rounded-md bg-indigo-50 px-2 py-1 dark:bg-indigo-950/40">
              <span>${escapeHtml(item.nombre_producto)} x${Number(item.cantidad || 0)}</span>
              <span class="font-semibold">${money(item.subtotal)}</span>
            </div>
          `).join('') || '<p class="text-xs text-gray-500">Sin items cargados.</p>'}
        </div>
      </div>
    `;
  };
  const renderNuevoPedidoAccion = (mesa) => {
    if (!puedeEditarPedido) return '';
    if (mesa.estado_salon === 'pagada') {
      return `
        <p class="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-center text-xs font-bold text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-200">
          Libera la mesa para cargar otro pedido.
        </p>
      `;
    }
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
  const releaseTable = async (pedidoId) => {
    await apiJson(`/api/gastronomia/salon/pedidos/${pedidoId}/liberar-mesa`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    detallesPagadosAbiertos.delete(String(pedidoId));
    showAlert(`Mesa liberada para el pedido #${pedidoId}.`, true);
    await loadSalon();
  };

  board?.addEventListener('click', (event) => {
    const detailButton = event.target.closest('[data-toggle-paid-detail]');
    if (detailButton) {
      const pedidoId = String(detailButton.dataset.togglePaidDetail || '');
      if (detallesPagadosAbiertos.has(pedidoId)) detallesPagadosAbiertos.delete(pedidoId);
      else detallesPagadosAbiertos.add(pedidoId);
      renderBoard();
      return;
    }

    const releaseButton = event.target.closest('[data-release-table]');
    if (!releaseButton) return;
    const pedidoId = Number(releaseButton.dataset.releaseTable || 0);
    if (!pedidoId) return;
    if (!window.confirm('La mesa quedara libre para usar nuevamente. ¿Continuar?')) return;
    releaseTable(pedidoId).catch((error) => showAlert(error.message, false));
  });
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
