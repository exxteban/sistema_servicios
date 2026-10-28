(function () {
  // Pestana "Precios de ingredientes": lista solo los insumos usados en recetas y pide el precio como se compra.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const root = scope.querySelector('[data-gastro-stock]');
  const panel = scope.querySelector('[data-stock-prices]');
  if (!root || !panel) return;

  const csrf = scope.querySelector('#csrf-token')?.value || '';
  const list = panel.querySelector('#stock-prices-list');
  const progress = panel.querySelector('#stock-prices-progress');
  const precio = window.GastroPrecioInsumo;
  let insumos = [];

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const apiJson = async (url, {method = 'GET', body = null} = {}) => {
    const response = await fetch(url, {
      method,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo guardar.');
    return data;
  };
  const statusHtml = (item) => (item.precio_compra > 0
    ? '<span class="text-sm font-bold text-emerald-700 dark:text-emerald-300"><i class="fas fa-check mr-1"></i>Listo</span>'
    : '<span class="text-sm font-bold text-red-600 dark:text-red-300">Falta</span>');

  const renderProgress = () => {
    const faltan = insumos.filter((item) => item.precio_compra <= 0).length;
    progress.textContent = faltan ? `Faltan ${faltan} de ${insumos.length}` : `Todo completo (${insumos.length})`;
    progress.className = `text-sm font-bold ${faltan ? 'text-red-600 dark:text-red-300' : 'text-emerald-700 dark:text-emerald-300'}`;
  };

  const render = () => {
    // Primero los que faltan, para que se vea enseguida que completar.
    const ordenados = insumos.slice().sort((a, b) => (a.precio_compra > 0) - (b.precio_compra > 0) || a.nombre.localeCompare(b.nombre));
    list.innerHTML = ordenados.map((item) => `
      <div class="grid items-center gap-2 rounded-lg border border-gray-200 px-3 py-3 dark:border-gray-700 sm:grid-cols-[1fr_auto_5rem]">
        <span class="text-base font-bold text-gray-900 dark:text-white">${escapeHtml(item.nombre)}</span>
        <label class="flex items-center gap-2 text-sm font-semibold text-gray-600 dark:text-gray-300">
          Cuanto pagas ${precio.etiqueta(item.unidad_stock)}? Gs.
          <input type="number" min="0" step="1" inputmode="numeric" data-price-insumo="${item.id_producto}"
                 value="${item.precio_compra > 0 ? precio.aPantalla(item.precio_compra, item.unidad_stock) : ''}" placeholder="0"
                 class="w-32 rounded-lg border-2 ${item.precio_compra > 0 ? 'border-gray-200' : 'border-red-300'} px-3 py-2 text-right text-base dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100">
        </label>
        <span data-price-status="${item.id_producto}" class="sm:text-right">${statusHtml(item)}</span>
      </div>
    `).join('') || '<p class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm font-semibold text-gray-500">Todavia no hay recetas con ingredientes. Primero arma las recetas de los platos.</p>';
    renderProgress();
  };

  const load = async () => {
    const data = await apiJson('/api/gastronomia/stock/insumos/precios');
    insumos = data.insumos || [];
    render();
  };

  const save = async (input) => {
    const item = insumos.find((row) => String(row.id_producto) === input.dataset.priceInsumo);
    if (!item) return;
    const status = list.querySelector(`[data-price-status="${item.id_producto}"]`);
    status.innerHTML = '<span class="text-sm font-semibold text-gray-500">Guardando...</span>';
    try {
      const data = await apiJson(`/api/gastronomia/stock/insumos/${item.id_producto}/precio-compra`, {
        method: 'PUT',
        body: {precio_compra: precio.aBase(input.value, item.unidad_stock)},
      });
      item.precio_compra = Number(data.insumo?.precio_compra || 0);
      input.classList.toggle('border-red-300', item.precio_compra <= 0);
      input.classList.toggle('border-gray-200', item.precio_compra > 0);
      status.innerHTML = statusHtml(item);
      renderProgress();
    } catch (error) {
      status.innerHTML = `<span class="text-sm font-bold text-red-600">${escapeHtml(error.message)}</span>`;
    }
  };

  list.addEventListener('change', (event) => {
    const input = event.target.closest('[data-price-insumo]');
    if (input) save(input);
  });
  list.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && event.target.closest('[data-price-insumo]')) event.target.blur();
  });
  // Recargar al abrir la pestana: las recetas pueden haber cambiado.
  root.querySelector('[data-stock-subtab="precios"]')?.addEventListener('click', () => load().catch(() => {}));
  load().catch((error) => { list.textContent = error.message; });
}());
