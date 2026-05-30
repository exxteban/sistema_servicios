(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const panel = document.getElementById('modificadores-panel');
  const productForm = document.getElementById('producto-form');
  const list = document.getElementById('modificadores-lista');
  const alertBox = document.getElementById('modificadores-alert');
  const groupSelect = document.getElementById('modificador-opcion-grupo');
  const emptyState = document.getElementById('modificadores-empty');
  const editor = document.getElementById('modificadores-editor');
  let currentProductId = '';
  let pollCount = 0;

  if (!panel || !productForm || !list) return;

  const showAlert = (message, ok) => {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `mt-3 rounded-lg border px-3 py-2 text-xs font-bold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };

  const showEmptyState = () => {
    currentProductId = '';
    panel.classList.remove('hidden');
    emptyState?.classList.remove('hidden');
    editor?.classList.add('hidden');
    list.innerHTML = '';
    if (groupSelect) {
      groupSelect.innerHTML = '<option value="">Primero guarda o edita un producto</option>';
    }
  };

  const showEditor = () => {
    panel.classList.remove('hidden');
    emptyState?.classList.add('hidden');
    editor?.classList.remove('hidden');
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

  const apiMultipart = async (url, body) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: {'X-CSRFToken': csrf},
      body,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
    return data;
  };

  const money = (value) => `Gs. ${Number(value || 0).toLocaleString('es-PY', {maximumFractionDigits: 0})}`;

  const render = (grupos) => {
    groupSelect.innerHTML = grupos.length
      ? grupos.map((grupo) => `<option value="${grupo.id_grupo}">${escapeHtml(grupo.nombre)}</option>`).join('')
      : '<option value="">Primero crea un grupo</option>';

    list.innerHTML = grupos.length ? grupos.map((grupo) => `
      <article class="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h4 class="font-bold text-gray-900 dark:text-white">${escapeHtml(grupo.nombre)}</h4>
            <p class="mt-1 text-xs font-semibold text-gray-500 dark:text-gray-400">${escapeHtml(grupo.tipo)} - max. ${grupo.max_selecciones}</p>
          </div>
          <button type="button" data-delete-group="${grupo.id_grupo}" class="rounded-lg border border-red-200 px-2 py-1 text-xs font-bold text-red-700 hover:bg-red-50 dark:border-red-400/40 dark:text-red-200">Eliminar</button>
        </div>
        <div class="mt-3 grid gap-2">
          ${(grupo.opciones || []).map(renderOption).join('') || '<p class="text-xs font-semibold text-gray-500">Sin opciones cargadas.</p>'}
        </div>
      </article>
    `).join('') : '<p class="rounded-lg border border-dashed border-gray-300 p-4 text-center text-sm font-semibold text-gray-500 dark:border-gray-700">Este producto todavia no tiene modificadores.</p>';
  };

  const renderOption = (opcion) => `
    <div class="flex items-center gap-3 rounded-lg border border-gray-100 p-2 dark:border-gray-800">
      <div class="h-12 w-12 flex-shrink-0 overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800">
        ${opcion.imagen_url ? `<img src="${escapeAttr(opcion.imagen_url)}" alt="" class="h-full w-full object-cover">` : ''}
      </div>
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-bold text-gray-900 dark:text-white">${escapeHtml(opcion.nombre)}</p>
        <p class="text-xs font-semibold text-gray-500 dark:text-gray-400">${money(opcion.precio_delta)}</p>
      </div>
      <button type="button" data-delete-option="${opcion.id_opcion}" class="rounded-lg border border-red-200 px-2 py-1 text-xs font-bold text-red-700 hover:bg-red-50 dark:border-red-400/40 dark:text-red-200">Quitar</button>
    </div>
  `;

  const loadModifiers = async (productId) => {
    if (!productId) {
      showEmptyState();
      return;
    }
    currentProductId = String(productId);
    showEditor();
    const data = await apiJson(`/api/gastronomia/productos/${currentProductId}?modificadores=1`);
    render(data.producto?.grupos_opciones || []);
  };

  const createGroup = async () => {
    const nombre = document.getElementById('modificador-grupo-nombre')?.value?.trim();
    if (!currentProductId) {
      showAlert('Primero guarda el producto para poder cargar extras.', false);
      return;
    }
    if (!nombre) return;
    await apiJson(`/api/gastronomia/productos/${currentProductId}/grupos-opciones`, {
      method: 'POST',
      body: {
        nombre,
        tipo: document.getElementById('modificador-grupo-tipo')?.value || 'extra',
        max_selecciones: document.getElementById('modificador-grupo-max')?.value || 5,
      },
    });
    document.getElementById('modificador-grupo-nombre').value = '';
    showAlert('Grupo creado.', true);
    await loadModifiers(currentProductId);
  };

  const createOption = async () => {
    const grupoId = groupSelect?.value;
    const nombre = document.getElementById('modificador-opcion-nombre')?.value?.trim();
    if (!currentProductId) {
      showAlert('Primero guarda el producto para poder cargar extras.', false);
      return;
    }
    if (!grupoId || !nombre) return;
    const data = new FormData();
    data.set('nombre', nombre);
    data.set('precio_delta', document.getElementById('modificador-opcion-precio')?.value || '0');
    const file = document.getElementById('modificador-opcion-imagen')?.files?.[0];
    if (file) data.set('imagen_archivo', file);
    await apiMultipart(`/api/gastronomia/grupos-opciones/${grupoId}/opciones`, data);
    document.getElementById('modificador-opcion-nombre').value = '';
    document.getElementById('modificador-opcion-precio').value = '0';
    document.getElementById('modificador-opcion-imagen').value = '';
    showAlert('Opcion agregada.', true);
    await loadModifiers(currentProductId);
  };

  panel.addEventListener('click', async (event) => {
    try {
      if (event.target.closest('#modificador-recargar')) await loadModifiers(currentProductId);
      if (event.target.closest('#modificador-grupo-crear')) await createGroup();
      if (event.target.closest('#modificador-opcion-crear')) await createOption();
      const deleteGroup = event.target.closest('[data-delete-group]')?.dataset?.deleteGroup;
      if (deleteGroup && window.confirm('Se eliminara este grupo con sus opciones. Deseas continuar?')) {
        await apiJson(`/api/gastronomia/grupos-opciones/${deleteGroup}`, {method: 'DELETE'});
        await loadModifiers(currentProductId);
      }
      const deleteOption = event.target.closest('[data-delete-option]')?.dataset?.deleteOption;
      if (deleteOption) {
        await apiJson(`/api/gastronomia/opciones/${deleteOption}`, {method: 'DELETE'});
        await loadModifiers(currentProductId);
      }
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  document.querySelector('[data-gastro-menu]')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-edit-product]');
    if (!button) return;
    setTimeout(() => loadModifiers(button.dataset.editProduct).catch((error) => showAlert(error.message, false)), 350);
  });

  document.getElementById('producto-cancel-edit')?.addEventListener('click', showEmptyState);

  const detectProductId = () => {
    const value = productForm.id_producto?.value || '';
    if (value && value !== currentProductId) {
      loadModifiers(value).catch((error) => showAlert(error.message, false));
    }
    if (!value && currentProductId) showEmptyState();
    pollCount += 1;
    if (pollCount < 18) window.setTimeout(detectProductId, 700);
  };

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const escapeAttr = escapeHtml;

  showEmptyState();
  detectProductId();
}());
