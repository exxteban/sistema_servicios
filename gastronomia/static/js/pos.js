(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const productsGrid = document.getElementById('products-grid');
  const productSearch = document.getElementById('product-search');
  const cartItems = document.getElementById('cart-items');
  const cartTotal = document.getElementById('cart-total');
  const alertBox = document.getElementById('pos-alert');
  const modal = document.getElementById('modifier-modal');
  const modalName = document.getElementById('modal-product-name');
  const modalPrice = document.getElementById('modal-product-price');
  const modalGroups = document.getElementById('modifier-groups');
  const modalQty = document.getElementById('modal-qty');
  const modalNote = document.getElementById('modal-note');
  const modalModeLabel = document.getElementById('modal-mode-label');
  const configuredProductButton = document.getElementById('add-configured-product');
  const root = document.querySelector('[data-gastro-pos]');
  const orderTypeInput = document.getElementById('order-type');
  const tableNameInput = document.getElementById('table-name');
  const tablePickerSection = document.getElementById('table-picker-section');
  const tableGrid = document.getElementById('table-grid');

  let products = [];
  let mesas = [];
  let selectedCategory = '';
  let cart = [];
  let activeProduct = null;
  let editingItemKey = null;
  let lastOrderId = null;

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const apiJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
    return data;
  };

  const loadProducts = async () => {
    const data = await apiJson('/api/gastronomia/productos?publico=1&modificadores=1');
    products = data.productos || [];
    renderProducts();
  };
  const loadMesas = async () => {
    const data = await apiJson('/api/gastronomia/salon/mesas');
    mesas = data.mesas || [];
    renderMesas();
  };

  const renderProducts = () => {
    const searchTerm = (productSearch?.value || '').trim().toLowerCase();
    const categoryProducts = selectedCategory
      ? products.filter((product) => String(product.categoria_id) === String(selectedCategory))
      : products;
    const visible = searchTerm
      ? categoryProducts.filter((product) => `${product.nombre} ${product.descripcion || ''}`.toLowerCase().includes(searchTerm))
      : categoryProducts;
    productsGrid.innerHTML = visible.map((product) => `
      <button type="button" data-product="${product.id_producto}" class="min-h-36 rounded-xl border border-gray-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-orange-300 hover:shadow-md dark:border-gray-700 dark:bg-gray-900">
        <span class="block text-base font-black text-gray-900 dark:text-white">${escapeHtml(product.nombre)}</span>
        <span class="mt-2 line-clamp-2 block min-h-10 text-sm text-gray-600 dark:text-gray-400">${escapeHtml(product.descripcion || 'Toca para configurar el item.')}</span>
        <span class="mt-5 block text-xl font-black text-orange-600 dark:text-orange-300">${money(product.precio)}</span>
      </button>
    `).join('') || `
      <div class="rounded-xl border border-dashed border-gray-300 p-8 text-center text-gray-500 dark:border-gray-700 sm:col-span-2 2xl:col-span-3">
        ${products.length ? 'No hay productos para esta busqueda o categoria.' : 'Sin productos disponibles. Revisa que el producto este visible y disponible en Cargar menu.'}
      </div>
    `;
  };
  const renderMesas = () => {
    if (!tableGrid) return;
    tableGrid.innerHTML = mesas.map((mesa) => `
      <button
        type="button"
        data-table-name="${escapeHtml(mesa.nombre)}"
        class="mesa-selector-btn ${tableNameInput?.value === mesa.nombre ? 'activa' : ''}"
      >
        ${escapeHtml(mesa.nombre)}
      </button>
    `).join('') || '<div class="col-span-4 rounded-lg border border-dashed border-gray-300 p-4 text-center text-sm text-gray-500 dark:border-gray-700">Sin mesas cargadas.</div>';
  };
  const syncOrderTypeUi = () => {
    const currentType = orderTypeInput?.value || 'mostrador';
    document.querySelectorAll('[data-order-type]').forEach((button) => {
      button.classList.toggle('activa', button.dataset.orderType === currentType);
    });
    if (tablePickerSection) {
      tablePickerSection.classList.toggle('hidden', currentType !== 'mesa');
    }
    if (currentType !== 'mesa' && tableNameInput) {
      tableNameInput.value = '';
      renderMesas();
    }
  };
  const setOrderType = (type) => {
    if (!orderTypeInput) return;
    orderTypeInput.value = type;
    syncOrderTypeUi();
  };
  const setMesa = (mesaNombre) => {
    if (!tableNameInput) return;
    tableNameInput.value = mesaNombre;
    renderMesas();
  };

  const openProduct = (product, item = null) => {
    activeProduct = product;
    editingItemKey = item?.key || null;
    modalName.textContent = product.nombre;
    modalPrice.textContent = money(product.precio);
    modalQty.value = item?.cantidad || 1;
    modalNote.value = item?.notas || '';
    modalGroups.innerHTML = (product.grupos_opciones || [])
      .map((group) => renderGroup(group, item?.opciones || []))
      .join('');
    if (configuredProductButton) {
      configuredProductButton.textContent = editingItemKey ? 'Guardar cambios' : 'Agregar';
    }
    if (modalModeLabel) {
      modalModeLabel.textContent = editingItemKey ? 'Editar item del pedido' : 'Configurar producto';
    }
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  };

  const renderGroup = (group, selectedOptions = []) => {
    const isRemovable = group.tipo === 'ingrediente_removible';
    const inputType = isRemovable ? 'checkbox' : (group.max_selecciones === 1 ? 'radio' : 'checkbox');
    const helper = isRemovable ? 'Marca los ingredientes que NO debe llevar.' : 'Selecciona las opciones para este item.';
    return `
      <section class="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
        <div class="flex items-center justify-between gap-3">
          <h3 class="font-bold text-gray-900 dark:text-white">${escapeHtml(group.nombre)}</h3>
          <span class="text-xs font-semibold text-gray-500">${group.min_selecciones || 0}-${group.max_selecciones || 0}</span>
        </div>
        <p class="mt-1 text-xs font-semibold text-gray-500 dark:text-gray-400">${helper}</p>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          ${(group.opciones || []).map((option) => `
            <label class="flex min-h-14 items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold dark:border-gray-700 dark:text-gray-100">
              <span><input type="${inputType}" name="group-${group.id_grupo}" value="${option.id_opcion}" class="mr-2" ${selectedOptions.includes(Number(option.id_opcion)) ? 'checked' : ''}>${escapeHtml(formatModifierName({...option, tipo_grupo: group.tipo}))}</span>
              <span>${option.precio_delta ? `+${money(option.precio_delta)}` : ''}</span>
            </label>
          `).join('')}
        </div>
      </section>
    `;
  };

  const addConfiguredProduct = async () => {
    const selectedOptions = Array.from(modal.querySelectorAll('#modifier-groups input:checked')).map((input) => Number(input.value));
    const validation = await apiJson(`/api/gastronomia/productos/${activeProduct.id_producto}/validar-selecciones`, {
      method: 'POST',
      body: JSON.stringify({opciones: selectedOptions}),
    });
    const configuredItem = {
      key: editingItemKey || `${Date.now()}-${Math.random()}`,
      producto_id: activeProduct.id_producto,
      nombre: activeProduct.nombre,
      cantidad: Math.max(1, Number(modalQty.value || 1)),
      precio_unitario: validation.total,
      opciones: selectedOptions,
      selecciones: validation.selecciones || [],
      notas: modalNote.value.trim(),
    };
    if (editingItemKey) {
      cart = cart.map((item) => item.key === editingItemKey ? configuredItem : item);
    } else {
      cart.push(configuredItem);
    }
    lastOrderId = null;
    closeModal();
    renderCart();
  };

  const editCartItem = (itemKey) => {
    const item = cart.find((cartItem) => cartItem.key === itemKey);
    const product = products.find((productItem) => String(productItem.id_producto) === String(item?.producto_id));
    if (!item || !product) {
      showAlert('No se pudo abrir el item para editar.', false);
      return;
    }
    openProduct(product, item);
  };

  const renderCart = () => {
    cartItems.innerHTML = cart.map((item) => `
      <article class="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
        <div class="grid grid-cols-[44px_1fr_auto] items-start gap-3">
          <span class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 text-sm font-black text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white">${item.cantidad}</span>
          <div class="min-w-0">
            <h3 class="font-black leading-tight text-gray-900 dark:text-white">${escapeHtml(item.nombre)}</h3>
            <p class="mt-1 text-xs text-gray-500">${escapeHtml(item.selecciones.map(formatModifierName).join(', '))}</p>
            ${item.notas ? `<p class="mt-1 rounded bg-orange-50 px-2 py-1 text-xs font-bold text-orange-700 dark:bg-orange-500/10 dark:text-orange-200">${escapeHtml(item.notas)}</p>` : ''}
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button type="button" data-edit="${item.key}" class="rounded-lg border border-amber-200 px-2 py-1 text-sm font-bold text-amber-700 hover:bg-amber-50" aria-label="Editar ${escapeHtml(item.nombre)}">
              <i class="fas fa-pen" aria-hidden="true"></i>
            </button>
            <button type="button" data-remove="${item.key}" class="rounded-lg border border-red-200 px-2 py-1 text-sm font-bold text-red-600 hover:bg-red-50" aria-label="Quitar ${escapeHtml(item.nombre)}">
              <i class="fas fa-times" aria-hidden="true"></i>
            </button>
          </div>
        </div>
        <div class="mt-2 flex justify-between text-sm">
          <span class="font-semibold text-gray-500">${money(item.precio_unitario)} c/u</span>
          <strong class="font-black text-gray-900 dark:text-white">${money(item.precio_unitario * item.cantidad)}</strong>
        </div>
      </article>
    `).join('') || '<div class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">Sin items.</div>';
    cartTotal.textContent = money(cart.reduce((sum, item) => sum + item.precio_unitario * item.cantidad, 0));
  };

  const buildOrderPayload = () => ({
    tipo_pedido: orderTypeInput?.value || 'mostrador',
    mesa: tableNameInput?.value.trim() || '',
    notas: document.getElementById('order-notes').value.trim(),
    items: cart.map((item) => ({
      producto_id: item.producto_id,
      cantidad: item.cantidad,
      opciones: item.opciones,
      notas: item.notas,
    })),
  });

  const saveOrder = async () => {
    if (!cart.length) throw new Error('El pedido debe tener items.');
    if ((orderTypeInput?.value || '') === 'mesa' && !(tableNameInput?.value || '').trim()) {
      throw new Error('Selecciona una mesa.');
    }
    const data = await apiJson('/api/gastronomia/pedidos', {
      method: 'POST',
      body: JSON.stringify(buildOrderPayload()),
    });
    lastOrderId = data.pedido.id_pedido;
    cart = [];
    if (tableNameInput && (orderTypeInput?.value || '') !== 'mesa') {
      tableNameInput.value = '';
    }
    renderCart();
    showAlert(`Pedido #${lastOrderId} guardado.`, true);
    return lastOrderId;
  };

  const sendKitchen = async () => {
    const pedidoId = lastOrderId || await saveOrder();
    await apiJson(`/api/gastronomia/pedidos/${pedidoId}/enviar-cocina`, {method: 'POST', body: '{}'});
    lastOrderId = null;
    showAlert(`Pedido #${pedidoId} enviado a cocina.`, true);
  };

  const openAdvancedCheckoutAndSendKitchen = async () => {
    const pedidoId = lastOrderId || await saveOrder();
    const data = await apiJson(`/api/gastronomia/pedidos/${pedidoId}/cobro-avanzado`, {
      method: 'POST',
      body: JSON.stringify({enviar_cocina: true}),
    });
    lastOrderId = null;
    window.location.href = data.checkout_url;
  };

  const closeModal = () => {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    activeProduct = null;
    editingItemKey = null;
  };

  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }[char]));
  const formatModifierName = (modifier) => (
    modifier?.tipo_grupo === 'ingrediente_removible' ? `Sin ${modifier.nombre}` : modifier?.nombre
  );

  document.getElementById('category-tabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-category]');
    if (!button) return;
    selectedCategory = button.dataset.category;
    document.querySelectorAll('.pos-category').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    renderProducts();
  });
  productSearch?.addEventListener('input', renderProducts);
  document.getElementById('order-type-buttons')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-order-type]');
    if (!button) return;
    setOrderType(button.dataset.orderType || 'mostrador');
  });
  tableGrid?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-table-name]');
    if (!button) return;
    setMesa(button.dataset.tableName || '');
  });
  productsGrid?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-product]');
    if (!button) return;
    const product = products.find((item) => String(item.id_producto) === String(button.dataset.product));
    if (product) openProduct(product);
  });
  cartItems?.addEventListener('click', (event) => {
    const editButton = event.target.closest('[data-edit]');
    if (editButton) {
      editCartItem(editButton.dataset.edit);
      return;
    }
    const button = event.target.closest('[data-remove]');
    if (!button) return;
    cart = cart.filter((item) => item.key !== button.dataset.remove);
    lastOrderId = null;
    renderCart();
  });
  document.getElementById('close-modal')?.addEventListener('click', closeModal);
  document.getElementById('add-configured-product')?.addEventListener('click', () => addConfiguredProduct().catch((error) => showAlert(error.message, false)));
  document.getElementById('clear-cart')?.addEventListener('click', () => { cart = []; lastOrderId = null; renderCart(); });
  document.getElementById('save-order')?.addEventListener('click', () => saveOrder().catch((error) => showAlert(error.message, false)));
  document.getElementById('send-kitchen')?.addEventListener('click', () => sendKitchen().catch((error) => showAlert(error.message, false)));
  document.getElementById('charge-send-kitchen')?.addEventListener('click', () => openAdvancedCheckoutAndSendKitchen().catch((error) => showAlert(error.message, false)));

  const mesaInicial = root?.dataset.mesaInicial || '';
  if (mesaInicial) {
    setOrderType('mesa');
    setMesa(mesaInicial);
  }
  syncOrderTypeUi();
  loadProducts().catch((error) => showAlert(error.message, false));
  loadMesas().catch((error) => showAlert(error.message, false));
  renderCart();
}());
