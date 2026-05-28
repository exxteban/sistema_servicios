(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const alertBox = document.getElementById('gastro-menu-alert');
  const productoForm = document.getElementById('producto-form');
  const menuTvForm = document.getElementById('menu-tv-form');
  const productoSubmit = document.getElementById('producto-submit');
  const productoCancelEdit = document.getElementById('producto-cancel-edit');
  const productoImageInput = document.getElementById('producto-imagen-archivo');
  const productoImagePreview = document.getElementById('producto-imagen-preview');
  const productoImageEmpty = document.getElementById('producto-imagen-empty');
  const productoImageName = document.getElementById('producto-imagen-nombre');
  const mainTabButtons = Array.from(document.querySelectorAll('[data-main-tab]'));
  const mainTabPanels = Array.from(document.querySelectorAll('[data-main-tab-panel]'));
  const entryTabButtons = Array.from(document.querySelectorAll('[data-entry-tab]'));
  const entryTabPanels = Array.from(document.querySelectorAll('[data-entry-tab-panel]'));
  const tabButtons = Array.from(document.querySelectorAll('[data-menu-tab]'));
  const tabPanels = Array.from(document.querySelectorAll('[data-menu-tab-panel]'));
  let productoImageObjectUrl = '';

  const showAlert = (message, ok) => {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };

  const formData = (form) => Object.fromEntries(new FormData(form).entries());

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

  const apiMultipart = async (url, {method = 'POST', body} = {}) => {
    const response = await fetch(url, {
      method,
      headers: {'X-CSRFToken': csrf},
      body,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
    return data;
  };

  const postJson = (url, body) => apiJson(url, {method: 'POST', body});

  const ingredientesRemovibles = (producto) => (producto.grupos_opciones || [])
    .find((grupo) => grupo.tipo === 'ingrediente_removible')?.opciones
    ?.map((opcion) => opcion.nombre)
    .join('\n') || '';

  const clearObjectUrl = () => {
    if (!productoImageObjectUrl) return;
    URL.revokeObjectURL(productoImageObjectUrl);
    productoImageObjectUrl = '';
  };

  const renderImagePreview = ({url = '', fileName = '', emptyText = 'Sin imagen'} = {}) => {
    if (!productoImagePreview || !productoImageEmpty || !productoImageName) return;
    if (url) {
      productoImagePreview.src = url;
      productoImagePreview.classList.remove('hidden');
      productoImageEmpty.classList.add('hidden');
    } else {
      productoImagePreview.src = '';
      productoImagePreview.classList.add('hidden');
      productoImageEmpty.textContent = emptyText;
      productoImageEmpty.classList.remove('hidden');
    }
    productoImageName.textContent = fileName || (url ? 'Imagen actual del producto.' : 'Puedes elegir una imagen desde tu computadora. El sistema la guardara dentro del servidor.');
  };

  const syncImageSelection = () => {
    const file = productoImageInput?.files?.[0];
    if (!file) {
      clearObjectUrl();
      renderImagePreview({
        url: productoForm?.imagen_url?.value || '',
        emptyText: 'Sin imagen',
      });
      return;
    }
    if (productoForm?.quitar_imagen) {
      productoForm.quitar_imagen.checked = false;
    }
    clearObjectUrl();
    productoImageObjectUrl = URL.createObjectURL(file);
    renderImagePreview({
      url: productoImageObjectUrl,
      fileName: `Archivo seleccionado: ${file.name}`,
    });
  };

  const switchTab = (tabId) => {
    tabButtons.forEach((button) => {
      const active = button.dataset.menuTab === tabId;
      button.classList.toggle('activa', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    tabPanels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.menuTabPanel !== tabId);
    });
  };

  const switchMainTab = (tabId) => {
    mainTabButtons.forEach((button) => {
      const active = button.dataset.mainTab === tabId;
      button.classList.toggle('activa', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    mainTabPanels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.mainTabPanel !== tabId);
    });
  };

  const switchEntryTab = (tabId) => {
    entryTabButtons.forEach((button) => {
      const active = button.dataset.entryTab === tabId;
      button.classList.toggle('activa', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    entryTabPanels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.entryTabPanel !== tabId);
    });
  };

  const syncProductBadges = (article, producto) => {
    if (!article || !producto) return;
    const badges = {
      visible: article.querySelector('[data-product-badge="visible"]'),
      tv: article.querySelector('[data-product-badge="tv"]'),
      disponible: article.querySelector('[data-product-badge="disponible"]'),
      stock: article.querySelector('[data-product-badge="stock"]'),
    };
    if (badges.visible) {
      badges.visible.textContent = producto.visible ? 'Visible en menu' : 'Oculto en menu';
    }
    if (badges.tv) {
      badges.tv.textContent = producto.visible_en_tv ? 'Visible en TV' : 'Oculto en TV';
    }
    if (badges.disponible) {
      badges.disponible.textContent = producto.disponible ? 'Disponible' : 'Agotado';
      badges.disponible.className = producto.disponible
        ? 'rounded-full px-2 py-1 bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200'
        : 'rounded-full px-2 py-1 gastro-soldout-badge';
    }
    if (badges.stock) {
      badges.stock.textContent = producto.control_stock_venta
        ? `Stock: ${Number(producto.stock_disponible || 0)}`
        : 'Sin control stock';
    }
  };

  const resetProductoForm = () => {
    if (!productoForm) return;
    clearObjectUrl();
    productoForm.reset();
    productoForm.id_producto.value = '';
    productoForm.imagen_url.value = '';
    productoForm.disponible.checked = true;
    productoForm.visible.checked = true;
    productoForm.visible_en_tv.checked = true;
    productoForm.control_stock_venta.checked = false;
    productoForm.stock_disponible.value = 0;
    productoSubmit.innerHTML = '<i class="fas fa-save"></i>Guardar producto';
    productoCancelEdit.classList.add('hidden');
    renderImagePreview({emptyText: 'Sin imagen'});
  };

  const cargarProductoParaEditar = async (productoId) => {
    const data = await apiJson(`/api/gastronomia/productos/${productoId}?modificadores=1`);
    const producto = data.producto;
    clearObjectUrl();
    productoForm.reset();
    productoForm.id_producto.value = producto.id_producto;
    productoForm.categoria_id.value = producto.categoria_id;
    productoForm.nombre.value = producto.nombre || '';
    productoForm.descripcion.value = producto.descripcion || '';
    productoForm.ingredientes_removibles.value = ingredientesRemovibles(producto);
    productoForm.precio.value = producto.precio || 0;
    productoForm.orden.value = producto.orden || 0;
    productoForm.imagen_url.value = producto.imagen_url || '';
    productoForm.disponible.checked = Boolean(producto.disponible);
    productoForm.visible.checked = Boolean(producto.visible);
    productoForm.visible_en_tv.checked = Boolean(producto.visible_en_tv);
    productoForm.control_stock_venta.checked = Boolean(producto.control_stock_venta);
    productoForm.stock_disponible.value = Number(producto.stock_disponible || 0);
    productoForm.quitar_imagen.checked = false;
    productoSubmit.innerHTML = '<i class="fas fa-save"></i>Actualizar producto';
    productoCancelEdit.classList.remove('hidden');
    switchEntryTab('producto');
    renderImagePreview({
      url: producto.imagen_url || '',
      emptyText: 'Sin imagen',
    });
    productoForm.scrollIntoView({behavior: 'smooth', block: 'start'});
  };

  const toggleProductoEstado = async (input) => {
    const productId = input.dataset.productId;
    const field = input.dataset.toggleProductField;
    const previousValue = !input.checked;
    const article = input.closest('[data-product-card]');
    const relatedInputs = article ? Array.from(article.querySelectorAll('[data-toggle-product-field]')) : [input];

    relatedInputs.forEach((item) => {
      item.disabled = true;
    });
    try {
      const response = await apiJson(`/api/gastronomia/productos/${productId}/estado`, {
        method: 'PUT',
        body: {[field]: input.checked},
      });
      syncProductBadges(article, response.producto);
      showAlert('Estado del producto actualizado.', true);
    } catch (error) {
      input.checked = previousValue;
      showAlert(error.message, false);
    } finally {
      relatedInputs.forEach((item) => {
        item.disabled = false;
      });
    }
  };

  document.getElementById('categoria-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = formData(event.currentTarget);
      data.visible = event.currentTarget.visible.checked;
      await postJson('/api/gastronomia/categorias', data);
      showAlert('Categoria guardada.', true);
      window.location.reload();
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  productoForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = new FormData(event.currentTarget);
      data.set('visible', event.currentTarget.visible.checked ? '1' : '0');
      data.set('visible_en_tv', event.currentTarget.visible_en_tv.checked ? '1' : '0');
      data.set('control_stock_venta', event.currentTarget.control_stock_venta.checked ? '1' : '0');
      data.set('disponible', event.currentTarget.disponible.checked ? '1' : '0');
      data.set('quitar_imagen', event.currentTarget.quitar_imagen.checked ? '1' : '0');
      const productoId = data.get('id_producto');
      const url = productoId ? `/api/gastronomia/productos/${productoId}` : '/api/gastronomia/productos';
      await apiMultipart(url, {method: productoId ? 'PUT' : 'POST', body: data});
      showAlert('Producto guardado.', true);
      window.location.reload();
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  menuTvForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = formData(event.currentTarget);
      data.menu_tv_publico_activo = event.currentTarget.menu_tv_publico_activo.checked;
      data.menu_tv_mostrar_precios = event.currentTarget.menu_tv_mostrar_precios.checked;
      data.menu_tv_mostrar_agotados = true;
      const response = await apiJson('/api/gastronomia/menu-tv/config', {method: 'PUT', body: data});
      const urlInput = document.getElementById('menu-tv-url');
      if (urlInput) urlInput.value = response.public_url || urlInput.value;
      showAlert('Configuracion de pantalla TV guardada.', true);
    } catch (error) {
      showAlert(error.message, false);
    }
  });

  productoCancelEdit?.addEventListener('click', resetProductoForm);
  productoImageInput?.addEventListener('change', syncImageSelection);
  productoForm?.quitar_imagen?.addEventListener('change', (event) => {
    if (!event.currentTarget.checked) {
      syncImageSelection();
      return;
    }
    clearObjectUrl();
    if (productoImageInput) productoImageInput.value = '';
    renderImagePreview({emptyText: 'La imagen actual se quitara al guardar.'});
  });

  document.querySelector('.gastro-menu-tabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-menu-tab]');
    if (!button) return;
    switchTab(button.dataset.menuTab);
  });

  document.querySelector('.gastro-entry-tabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-entry-tab]');
    if (!button) return;
    switchEntryTab(button.dataset.entryTab);
  });

  document.querySelector('.gastro-main-tabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-main-tab]');
    if (!button) return;
    switchMainTab(button.dataset.mainTab);
  });

  document.querySelector('[data-gastro-menu]')?.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-toggle-product-field]');
    if (toggle) {
      toggleProductoEstado(toggle).catch((error) => showAlert(error.message, false));
      return;
    }
    const button = event.target.closest('[data-edit-product]');
    if (!button) return;
    switchMainTab('menu');
    cargarProductoParaEditar(button.dataset.editProduct).catch((error) => showAlert(error.message, false));
  });

  renderImagePreview({emptyText: 'Sin imagen'});
  switchMainTab('menu');
  switchEntryTab('categoria');
  switchTab('categorias');
}());
