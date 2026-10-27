(function () {
  // Panel "Costo y ganancia" del editor de recetas. Escucha gastro:recipe-changed de stock_config.js.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const root = scope.querySelector('[data-gastro-stock]');
  if (!root) return;

  const csrf = scope.querySelector('#csrf-token')?.value || '';
  const panel = scope.querySelector('#stock-recipe-costs');
  const recipeProduct = scope.querySelector('#stock-recipe-product');
  const recipeList = scope.querySelector('#stock-recipe-summary');
  const alertBox = scope.querySelector('#gastro-stock-alert');

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const showAlert = (message, ok = true) => {
    alertBox.textContent = message;
    alertBox.className = `mt-3 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const apiJson = async (url, {method = 'GET', body = null} = {}) => {
    const response = await fetch(url, {
      method,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
    return data;
  };
  // Food cost sano en hamburgueseria: 30-35% => ganancia bruta 65% o mas.
  const marginTone = (pct) => {
    if (pct >= 60) return 'text-emerald-700 dark:text-emerald-300';
    if (pct >= 45) return 'text-amber-600 dark:text-amber-300';
    return 'text-red-600 dark:text-red-300';
  };
  const inputClass = 'w-28 rounded-lg border border-gray-200 px-2 py-1 text-right text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100';

  const renderSummaries = (items) => {
    const byId = new Map(items.map((item) => [String(item.producto_id), item]));
    recipeList?.querySelectorAll('[data-recipe-row]').forEach((row) => {
      const badge = row.querySelector('[data-recipe-margin]');
      if (!badge) return;
      const item = byId.get(row.dataset.recipeRow);
      if (!item?.tiene_costo) {
        badge.textContent = 'Sin costo';
        badge.className = 'text-xs font-bold text-gray-400';
        return;
      }
      badge.textContent = `Gana ${money(item.ganancia)} (${item.ganancia_pct}%)`;
      badge.className = `text-xs font-bold ${marginTone(item.ganancia_pct)}`;
    });
  };

  const loadSummaries = async () => {
    const data = await apiJson('/api/gastronomia/stock/costos/resumen');
    renderSummaries(data.productos || []);
  };

  const renderCost = (cost) => {
    const rows = (cost.insumos || []).map((item) => `
      <div class="grid grid-cols-[1fr_auto] items-center gap-2 text-sm">
        <span class="min-w-0 truncate"><strong>${escapeHtml(item.insumo_nombre)}</strong> x ${item.cantidad} ${escapeHtml(item.unidad_stock)}</span>
        <span class="flex items-center gap-2">
          <input type="number" min="0" step="1" value="${Math.round(item.precio_compra)}" data-cost-insumo="${item.insumo_id}"
                 title="Costo de compra por ${escapeHtml(item.unidad_stock)}" aria-label="Costo de ${escapeHtml(item.insumo_nombre)}" class="${inputClass} ${item.precio_compra > 0 ? '' : 'border-red-300'}">
          <span class="w-24 text-right text-xs font-bold text-gray-500">${money(item.subtotal)}</span>
        </span>
      </div>
    `).join('') || '<p class="text-xs font-semibold text-gray-500">Sin insumos en la receta: el costo es solo el extra.</p>';
    const warning = cost.insumos_sin_precio
      ? `<p class="mt-2 text-xs font-bold text-red-600">${cost.insumos_sin_precio} insumo(s) sin costo cargado. Escribe cuanto pagas por unidad.</p>`
      : '';
    panel.innerHTML = `
      <h4 class="text-sm font-bold text-gray-900 dark:text-white">Costo y ganancia por plato</h4>
      <p class="mt-1 text-xs font-semibold text-gray-500">Costo de compra por unidad de cada insumo. Se guarda al salir del campo.</p>
      <div class="mt-3 space-y-2">${rows}</div>
      ${warning}
      <div class="mt-3 border-t border-gray-100 pt-3 dark:border-gray-700">
        <div class="grid grid-cols-[1fr_auto] items-center gap-2 text-sm">
          <span><strong>Extra fijo</strong> <span class="text-xs text-gray-500">(verduras, salsas, aceite)</span></span>
          <span class="flex items-center gap-2">
            <input id="stock-cost-extra" type="number" min="0" step="100" value="${Math.round(cost.costo_extra)}" aria-label="Costo extra fijo" class="${inputClass}">
            <span class="w-24 text-right text-xs font-bold text-gray-500">${money(cost.costo_extra)}</span>
          </span>
        </div>
        <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
          <label class="inline-flex items-center gap-2 text-xs font-semibold text-gray-600 dark:text-gray-300">
            <input id="stock-cost-extra-all" type="checkbox"> Usar el mismo extra en toda la categoria
          </label>
          <button id="stock-cost-extra-save" type="button" class="rounded-lg border border-gray-200 px-3 py-1 text-xs font-bold text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200">Guardar extra</button>
        </div>
      </div>
      <div class="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-900">
        <div><p class="text-xs font-semibold text-gray-500">Precio</p><p class="text-sm font-black text-gray-900 dark:text-white">${money(cost.precio)}</p></div>
        <div><p class="text-xs font-semibold text-gray-500">Costo</p><p class="text-sm font-black text-gray-900 dark:text-white">${money(cost.costo_total)}</p></div>
        <div><p class="text-xs font-semibold text-gray-500">Ganancia</p><p class="text-sm font-black ${marginTone(cost.ganancia_pct)}">${money(cost.ganancia)} <span class="text-xs">(${cost.ganancia_pct}%)</span></p></div>
      </div>
    `;
    panel.classList.remove('hidden');
  };

  const loadCost = async () => {
    if (!recipeProduct.value) {
      panel.classList.add('hidden');
      panel.innerHTML = '';
      return;
    }
    const data = await apiJson(`/api/gastronomia/stock/productos/${recipeProduct.value}/costo`);
    renderCost(data.costo || {});
  };

  const refresh = () => Promise.all([loadCost(), loadSummaries()]).catch((error) => showAlert(error.message, false));

  const savePurchasePrice = async (input) => {
    await apiJson(`/api/gastronomia/stock/insumos/${input.dataset.costInsumo}/precio-compra`, {
      method: 'PUT',
      body: {precio_compra: Number(input.value || 0)},
    });
    showAlert('Costo del insumo guardado. Se actualiza en todos los platos que lo usan.');
    await refresh();
  };

  const saveExtra = async () => {
    const all = scope.querySelector('#stock-cost-extra-all')?.checked;
    const data = await apiJson(`/api/gastronomia/stock/productos/${recipeProduct.value}/costo-extra`, {
      method: 'PUT',
      body: {monto: Number(scope.querySelector('#stock-cost-extra')?.value || 0), aplicar_categoria: Boolean(all)},
    });
    showAlert(all ? `Extra aplicado a ${data.actualizados} plato(s) de la categoria.` : 'Extra fijo guardado.');
    await refresh();
  };

  panel?.addEventListener('change', (event) => {
    const input = event.target.closest('[data-cost-insumo]');
    if (input) savePurchasePrice(input).catch((error) => showAlert(error.message, false));
  });
  panel?.addEventListener('click', (event) => {
    if (event.target.closest('#stock-cost-extra-save')) saveExtra().catch((error) => showAlert(error.message, false));
  });
  panel?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    if (event.target.id === 'stock-cost-extra') {
      event.preventDefault();
      saveExtra().catch((error) => showAlert(error.message, false));
    }
  });
  root.addEventListener('gastro:recipe-changed', refresh);
  loadSummaries().catch((error) => showAlert(error.message, false));
}());
