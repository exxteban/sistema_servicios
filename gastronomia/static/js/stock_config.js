(function () {
  const root = document.querySelector('[data-gastro-stock]');
  if (!root) return;

  const csrf = document.getElementById('csrf-token')?.value || '';
  const alertBox = document.getElementById('gastro-stock-alert');
  const insumoSelect = document.getElementById('stock-insumo-select');
  const recipeProduct = document.getElementById('stock-recipe-product');
  const recipeInsumo = document.getElementById('stock-recipe-insumo');
  const recipeQuantity = document.getElementById('stock-recipe-quantity');
  let insumos = [];
  let recipeItems = [];
  let recipeOptions = [];
  let recipeSummaries = [];

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
  const selectedInsumo = () => insumos.find((item) => String(item.id_producto) === String(insumoSelect.value));
  const selectedRecipeInsumo = () => insumos.find((item) => String(item.id_producto) === String(recipeInsumo.value));
  const selectedRecipeSummary = () => recipeSummaries.find((item) => String(item.producto_id) === String(recipeProduct.value));
  const formObject = (form) => Object.fromEntries(new FormData(form).entries());

  const fillInsumoOptions = () => {
    const current = insumoSelect.value;
    const options = insumos.map((item) => `<option value="${item.id_producto}">${escapeHtml(item.nombre)}</option>`).join('');
    insumoSelect.innerHTML = options || '<option value="">Sin productos de inventario</option>';
    recipeInsumo.innerHTML = options || '<option value="">Sin productos de inventario</option>';
    if (current && insumos.some((item) => String(item.id_producto) === current)) insumoSelect.value = current;
  };

  const renderInsumo = () => {
    const item = selectedInsumo();
    const summary = document.getElementById('stock-insumo-summary');
    const presentations = document.getElementById('stock-presentations');
    const entrySelect = document.querySelector('#stock-entry-form [name="presentacion_id"]');
    if (!item) {
      summary.textContent = 'No hay insumos disponibles.';
      presentations.innerHTML = '';
      entrySelect.innerHTML = '<option value="">Unidad base</option>';
      return;
    }
    summary.textContent = `Stock actual: ${item.stock_actual} ${item.unidad_stock}. Minimo: ${item.stock_minimo} ${item.unidad_stock}.`;
    document.querySelector('#stock-insumo-config [name="unidad_stock"]').value = item.unidad_stock;
    document.querySelector('#stock-insumo-config [name="stock_minimo"]').value = item.stock_minimo;
    document.querySelector('#stock-adjust-form [name="stock_fisico"]').value = Math.max(0, Number(item.stock_actual || 0));
    presentations.innerHTML = (item.presentaciones || []).map((row) => `
      <div class="flex items-center justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm dark:bg-gray-900">
        <span><strong>${escapeHtml(row.nombre)}</strong>: ${row.factor_unidad_base} ${escapeHtml(item.unidad_stock)}</span>
        <button type="button" data-delete-presentation="${row.id_presentacion}" class="text-xs font-bold text-red-600">Eliminar</button>
      </div>
    `).join('') || '<p class="text-xs font-semibold text-gray-500">Sin presentaciones. La entrada usara la unidad base.</p>';
    entrySelect.innerHTML = '<option value="">Unidad base</option>' + (item.presentaciones || [])
      .map((row) => `<option value="${row.id_presentacion}">${escapeHtml(row.nombre)} x ${row.factor_unidad_base}</option>`)
      .join('');
  };

  const loadInsumos = async () => {
    const data = await apiJson('/api/gastronomia/stock/insumos');
    insumos = data.insumos || [];
    fillInsumoOptions();
    renderInsumo();
    renderRecipe();
  };

  const syncRecipeControls = () => {
    const enabled = Boolean(recipeProduct.value);
    [recipeInsumo, recipeQuantity, document.getElementById('stock-recipe-add'), document.getElementById('stock-recipe-save')]
      .forEach((control) => { control.disabled = !enabled; });
    const summary = selectedRecipeSummary();
    const state = document.getElementById('stock-recipe-state');
    if (!enabled) {
      state.textContent = 'Selecciona un producto del menu para configurar su receta.';
      return;
    }
    state.textContent = summary?.receta_activa
      ? `Receta activa de ${summary.producto_nombre}: descuenta ${summary.cantidad_insumos} insumo(s).`
      : `${summary?.producto_nombre || 'Este producto'} todavia no descuenta insumos. Agrega el primer insumo.`;
  };

  const renderRecipeSummaries = () => {
    document.getElementById('stock-recipe-summary').innerHTML = recipeSummaries.map((item) => `
      <div class="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm ${item.receta_activa ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-400/30 dark:bg-emerald-500/10' : 'border-red-200 bg-red-50 dark:border-red-400/30 dark:bg-red-500/10'}">
        <div>
          <strong class="text-gray-900 dark:text-white">${escapeHtml(item.producto_nombre)}</strong>
          <span class="ml-2 text-xs font-bold ${item.receta_activa ? 'text-emerald-700 dark:text-emerald-200' : 'text-red-700 dark:text-red-200'}">
            ${item.receta_activa ? `${item.cantidad_insumos} insumo(s), receta activa` : 'Sin receta: no descuenta'}
          </span>
        </div>
        <button type="button" data-edit-recipe-product="${item.producto_id}" class="text-xs font-bold text-amber-700 dark:text-amber-200">Configurar</button>
      </div>
    `).join('') || '<p class="text-xs font-semibold text-gray-500">No hay productos cargados en el menu.</p>';
    syncRecipeControls();
  };

  const loadRecipeSummaries = async () => {
    const data = await apiJson('/api/gastronomia/stock/recetas/resumen');
    recipeSummaries = data.productos || [];
    renderRecipeSummaries();
  };

  const renderRecipe = () => {
    const container = document.getElementById('stock-recipe-items');
    container.innerHTML = recipeItems.map((row, index) => `
      <div class="flex items-center justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm dark:bg-gray-900">
        <span><strong>${escapeHtml(row.insumo_nombre)}</strong>: ${row.cantidad} ${escapeHtml(row.unidad_stock)}</span>
        <button type="button" data-delete-recipe-index="${index}" class="text-xs font-bold text-red-600">Quitar</button>
      </div>
    `).join('') || '<p class="text-xs font-semibold text-gray-500">Este producto aun no tiene receta.</p>';
  };

  const loadRecipe = async () => {
    if (!recipeProduct.value) {
      recipeItems = [];
      recipeOptions = [];
      renderRecipe();
      syncRecipeControls();
      return;
    }
    const data = await apiJson(`/api/gastronomia/stock/productos/${recipeProduct.value}/receta`);
    recipeItems = data.receta?.items || [];
    recipeOptions = data.receta?.opciones || [];
    renderRecipe();
    syncRecipeControls();
  };

  insumoSelect.addEventListener('change', renderInsumo);
  recipeProduct.addEventListener('change', () => loadRecipe().catch((error) => showAlert(error.message, false)));

  const persistRecipe = async ({confirmation = false} = {}) => {
    if (!recipeProduct.value) throw new Error('Paso 1: selecciona el producto del menu que quieres configurar.');
    const data = await apiJson(`/api/gastronomia/stock/productos/${recipeProduct.value}/receta`, {
      method: 'PUT',
      body: {items: recipeItems.map(({insumo_id, cantidad}) => ({insumo_id, cantidad})), opciones: recipeOptions},
    });
    recipeItems = data.receta?.items || [];
    recipeOptions = data.receta?.opciones || [];
    await loadRecipeSummaries();
    renderRecipe();
    syncRecipeControls();
    const plato = data.receta?.producto_nombre || 'Producto';
    showAlert(recipeItems.length
      ? `${plato}: receta activa con ${recipeItems.length} insumo(s). Los proximos pedidos descontaran stock automaticamente.`
      : `${plato}: receta vacia. Este producto no descontara insumos.`,
    recipeItems.length > 0);
  };

  document.getElementById('stock-recipe-add').addEventListener('click', async () => {
    if (!recipeProduct.value) return showAlert('Paso 1: selecciona el producto del menu antes de agregar insumos.', false);
    const insumo = selectedRecipeInsumo();
    const cantidad = Math.max(0, Number(recipeQuantity.value || 0));
    if (!insumo || cantidad <= 0) return showAlert('Selecciona un insumo y una cantidad valida.', false);
    const existing = recipeItems.find((item) => Number(item.insumo_id) === Number(insumo.id_producto));
    if (existing) {
      existing.cantidad = Number(existing.cantidad || 0) + cantidad;
    } else {
      recipeItems.push({
        insumo_id: insumo.id_producto,
        insumo_nombre: insumo.nombre,
        cantidad,
        unidad_stock: insumo.unidad_stock,
      });
    }
    renderRecipe();
    try {
      await persistRecipe();
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-recipe-items').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-delete-recipe-index]');
    if (!button) return;
    recipeItems.splice(Number(button.dataset.deleteRecipeIndex), 1);
    renderRecipe();
    try {
      await persistRecipe();
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-recipe-save').addEventListener('click', async () => {
    try {
      await persistRecipe({confirmation: true});
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-recipe-summary').addEventListener('click', (event) => {
    const button = event.target.closest('[data-edit-recipe-product]');
    if (!button) return;
    recipeProduct.value = button.dataset.editRecipeProduct;
    loadRecipe().catch((error) => showAlert(error.message, false));
  });

  document.getElementById('stock-insumo-config').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const item = selectedInsumo();
      if (!item) throw new Error('Selecciona un insumo.');
      await apiJson(`/api/gastronomia/stock/insumos/${item.id_producto}`, {method: 'PUT', body: formObject(event.currentTarget)});
      await loadInsumos();
      showAlert('Unidad base guardada.');
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-presentation-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const item = selectedInsumo();
      if (!item) throw new Error('Selecciona un insumo.');
      await apiJson(`/api/gastronomia/stock/insumos/${item.id_producto}/presentaciones`, {method: 'POST', body: formObject(event.currentTarget)});
      event.currentTarget.reset();
      await loadInsumos();
      showAlert('Presentacion agregada.');
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-presentations').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-delete-presentation]');
    if (!button) return;
    try {
      await apiJson(`/api/gastronomia/stock/presentaciones/${button.dataset.deletePresentation}`, {method: 'DELETE'});
      await loadInsumos();
      showAlert('Presentacion eliminada.');
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-entry-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const item = selectedInsumo();
      if (!item) throw new Error('Selecciona un insumo.');
      await apiJson(`/api/gastronomia/stock/insumos/${item.id_producto}/entradas`, {method: 'POST', body: formObject(event.currentTarget)});
      await loadInsumos();
      showAlert('Entrada registrada.');
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.getElementById('stock-adjust-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const item = selectedInsumo();
      if (!item) throw new Error('Selecciona un insumo.');
      await apiJson(`/api/gastronomia/stock/insumos/${item.id_producto}/ajuste`, {method: 'PUT', body: formObject(event.currentTarget)});
      await loadInsumos();
      showAlert('Stock fisico ajustado.');
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  syncRecipeControls();
  Promise.all([loadInsumos(), loadRecipeSummaries()]).catch((error) => showAlert(error.message, false));
}());
