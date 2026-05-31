(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const productsGrid = document.getElementById('products-grid');
  const productSearch = document.getElementById('product-search');
  const cartItems = document.getElementById('cart-items');
  const cartTotal = document.getElementById('cart-total');
  const productsCount = document.getElementById('products-count');
  const alertBox = document.getElementById('pos-alert');
  const clearProductSearchButton = document.getElementById('clear-product-search');
  const editingOrderBanner = document.getElementById('editing-order-banner');
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
  const deliveryReferenceInput = document.getElementById('delivery-reference');
  const deliveryFields = document.getElementById('delivery-fields');
  const deliveryPhoneInput = document.getElementById('delivery-phone');
  const deliveryAddressInput = document.getElementById('delivery-address');
  const deliveryEstimateInput = document.getElementById('delivery-estimate');
  const deliveryShippingInput = document.getElementById('delivery-shipping-cost');
  const tableNameInput = document.getElementById('table-name');
  const tablePickerSection = document.getElementById('table-picker-section');
  const tableGrid = document.getElementById('table-grid');
  const promotions = window.GastronomiaPromociones;
  let products = [];
  let mesas = [];
  let selectedCategory = '';
  let selectedPriceChannel = '';
  let cart = [];
  let activeProduct = null;
  let editingItemKey = null;
  let activeOrderId = null;
  let lastOrderId = null;
  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const showAlert = (message, ok) => {
    delete alertBox.dataset.stockPreview;
    alertBox.textContent = message;
    alertBox.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const showSavedOrderAlert = (order, message) => {
    const warnings = (order?.alertas_stock || []).map((item) => item.mensaje).join(' ');
    showAlert(warnings ? `${message} Alerta: ${warnings}` : message, !warnings);
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
    const contentType = response.headers.get('Content-Type') || '';
    const data = contentType.includes('application/json')
      ? await response.json()
      : {mensaje: (await response.text()).trim()};
    if (!response.ok) {
      const fallbackMessage = response.status === 404
        ? 'No se encontro el recurso solicitado. Recarga la pantalla e intenta de nuevo.'
        : 'Solicitud invalida.';
      const error = new Error(data.mensaje || data.error || fallbackMessage);
      error.redirectUrl = data.redirect_url || '';
      throw error;
    }
    return data;
  };
  const loadProducts = async () => {
    const nextProducts = await window.GastronomiaChannelPrices.fetchProducts(apiJson, selectedPriceChannel);
    if (!nextProducts) return;
    products = nextProducts;
    renderProducts();
  };
  const loadMesas = async () => {
    const data = await apiJson('/api/gastronomia/salon/mesas');
    mesas = data.mesas || [];
    renderMesas();
  };
  const syncProductSearchClearButton = () => {
    if (!clearProductSearchButton) return;
    const hasValue = Boolean((productSearch?.value || '').trim());
    clearProductSearchButton.classList.toggle('hidden', !hasValue);
  };

  const renderProducts = () => {
    const searchTerm = (productSearch?.value || '').trim().toLowerCase();
    const categoryProducts = selectedCategory
      ? products.filter((product) => String(product.categoria_id) === String(selectedCategory))
      : products;
    const visible = searchTerm
      ? categoryProducts.filter((product) => `${product.nombre} ${product.descripcion || ''}`.toLowerCase().includes(searchTerm))
      : categoryProducts;
    if (productsCount) {
      productsCount.textContent = visible.length
        ? `Mostrando ${visible.length} de ${products.length} productos`
        : '';
    }
    productsGrid.innerHTML = visible.map((product) => `
      <button type="button" data-product="${product.id_producto}" ${product.disponible ? '' : 'disabled'} class="pos-product-card min-h-32 rounded-lg border border-gray-200 bg-white p-2.5 text-left shadow-sm transition dark:border-gray-700 dark:bg-gray-900 ${product.disponible ? 'hover:-translate-y-0.5 hover:border-orange-300 hover:shadow-md' : 'cursor-not-allowed opacity-60'}">
        ${renderProductImage(product)}
        <span class="flex items-start justify-between gap-2">
          <span class="block text-sm font-black leading-tight text-gray-900 dark:text-white">${escapeHtml(product.nombre)}</span>
          ${product.disponible ? '' : '<span class="pos-soldout-badge">Agotado</span>'}
        </span>
        <span class="mt-1.5 line-clamp-2 block min-h-8 text-xs text-gray-600 dark:text-gray-400">${escapeHtml(product.descripcion || 'Toca para configurar el item.')}</span>
        <span class="mt-3 block text-lg font-black text-orange-600 dark:text-orange-300">${money(product.precio)}</span>
        ${product.promocion_activa?.etiqueta ? `<span class="mt-1 inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-black text-emerald-700">${escapeHtml(product.promocion_activa.etiqueta)}</span>` : ''}
      </button>
    `).join('') || `
      <div class="rounded-xl border border-dashed border-gray-300 p-8 text-center text-gray-500 dark:border-gray-700 sm:col-span-2 2xl:col-span-3">
        ${products.length ? 'No hay productos para esta busqueda o categoria.' : 'Sin productos visibles. Revisa la configuracion del menu.'}
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
    if (deliveryFields) {
      deliveryFields.classList.toggle('hidden', currentType !== 'delivery');
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
    renderCart();
  };
  const setMesa = (mesaNombre) => {
    if (!tableNameInput) return;
    tableNameInput.value = mesaNombre;
    renderMesas();
  };
  const formatModifierName = (modifier) => (
    modifier?.tipo_grupo === 'ingrediente_removible'
      ? `Sin ${modifier.nombre || modifier.nombre_opcion || ''}`
      : modifier?.nombre || modifier?.nombre_opcion || ''
  );
  const mapOrderItemToCartItem = (item) => {
    const modifiers = item.modificadores || [];
    return {
      key: item.id_item ? `pedido-item-${item.id_item}` : `${Date.now()}-${Math.random()}`,
      producto_id: item.producto_id,
      canal_precio: item.canal_precio || null,
      nombre: item.nombre_producto,
      cantidad: Math.max(1, Number(item.cantidad || 1)),
      precio_unitario: Number(item.precio_unitario || 0),
      precio_base: Number(item.precio_original || item.precio_unitario || 0),
      promocion_activa: null,
      subtotal_guardado: Number(item.subtotal || 0),
      opciones: modifiers.map((modifier) => Number(modifier.opcion_id)).filter(Boolean),
      selecciones: modifiers.map((modifier) => ({
        ...modifier,
        nombre: modifier.nombre || modifier.nombre_opcion,
      })),
      notas: item.notas || '',
    };
  };
  const setEditingOrderState = (orderId, order = null) => {
    activeOrderId = orderId ? Number(orderId) : null;
    lastOrderId = activeOrderId;
    if (editingOrderBanner) {
      if (activeOrderId) {
        const deliveryCode = order?.codigo_entrega || `#${String(activeOrderId).padStart(3, '0')}`;
        editingOrderBanner.textContent = `Editando pedido abierto ${deliveryCode}.`;
        editingOrderBanner.classList.remove('hidden');
      } else {
        editingOrderBanner.textContent = 'Editando pedido abierto.';
        editingOrderBanner.classList.add('hidden');
      }
    }
    const saveButton = document.getElementById('save-order');
    if (saveButton) {
      saveButton.innerHTML = activeOrderId
        ? '<i class="fas fa-save"></i> Guardar cambios'
        : '<i class="fas fa-check-square"></i> Guardar pedido';
    }
  };
  const resetDraft = () => {
    cart = [];
    setEditingOrderState(null);
    if (orderTypeInput) orderTypeInput.value = 'mostrador';
    if (deliveryReferenceInput) deliveryReferenceInput.value = '';
    if (deliveryPhoneInput) deliveryPhoneInput.value = '';
    if (deliveryAddressInput) deliveryAddressInput.value = '';
    if (deliveryEstimateInput) deliveryEstimateInput.value = '';
    if (deliveryShippingInput) deliveryShippingInput.value = 0;
    if (tableNameInput) tableNameInput.value = '';
    const orderNotesInput = document.getElementById('order-notes');
    if (orderNotesInput) orderNotesInput.value = '';
    syncOrderTypeUi();
    renderCart();
  };
  const hydrateOrder = (order) => {
    if (!order) return;
    setEditingOrderState(order.id_pedido, order);
    if (orderTypeInput) orderTypeInput.value = order.tipo_pedido || 'mostrador';
    if (deliveryReferenceInput) deliveryReferenceInput.value = order.referencia_entrega || '';
    if (deliveryPhoneInput) deliveryPhoneInput.value = order.celular_cliente || '';
    if (deliveryAddressInput) deliveryAddressInput.value = order.direccion_entrega || '';
    if (deliveryEstimateInput) deliveryEstimateInput.value = order.tiempo_estimado_minutos || '';
    if (deliveryShippingInput) deliveryShippingInput.value = order.costo_envio || 0;
    if (tableNameInput) tableNameInput.value = order.mesa || '';
    const orderNotesInput = document.getElementById('order-notes');
    if (orderNotesInput) orderNotesInput.value = order.notas || '';
    cart = (order.items || []).map(mapOrderItemToCartItem);
    syncOrderTypeUi();
    renderCart();
  };
  const loadOrder = async (orderId) => {
    const data = await apiJson(`/api/gastronomia/pedidos/${orderId}`);
    const order = data.pedido;
    if (!order) throw new Error('Pedido no encontrado.');
    if (order.estado !== 'abierto') throw new Error('Solo se pueden editar pedidos abiertos.');
    if (order.pagado) throw new Error('No se puede editar un pedido que ya fue cobrado.');
    hydrateOrder(order);
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
      <section class="pos-modifier-group rounded-lg border border-gray-200 p-4 dark:border-gray-700">
        <div class="pos-modifier-group-head flex items-center justify-between gap-3">
          <h3 class="font-bold text-gray-900 dark:text-white">${escapeHtml(group.nombre)}</h3>
          <span class="pos-modifier-group-limit text-xs font-semibold text-gray-500">${group.min_selecciones || 0}-${group.max_selecciones || 0}</span>
        </div>
        <p class="pos-modifier-group-helper mt-1 text-xs font-semibold text-gray-500 dark:text-gray-400">${helper}</p>
        <div class="pos-modifier-group-options mt-3 grid gap-2 sm:grid-cols-2">
          ${(group.opciones || []).map((option) => `
            <label class="pos-modifier-option rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold dark:border-gray-700 dark:text-gray-100">
              <span class="pos-modifier-option-copy">
                <input type="${inputType}" name="group-${group.id_grupo}" value="${option.id_opcion}" class="pos-modifier-option-input" ${selectedOptions.includes(Number(option.id_opcion)) ? 'checked' : ''}>
                <span class="pos-modifier-option-name">${escapeHtml(formatModifierName({...option, tipo_grupo: group.tipo}))}</span>
              </span>
              <span class="pos-modifier-option-price">${option.precio_delta ? `+${money(option.precio_delta)}` : 'Sin costo'}</span>
            </label>
          `).join('')}
        </div>
      </section>
    `;
  };

  const addConfiguredProduct = async () => {
    window.GastronomiaChannelPrices?.ensureCanAdd(cart, activeProduct);
    const selectedOptions = Array.from(modal.querySelectorAll('#modifier-groups input:checked')).map((input) => Number(input.value));
    const validation = await apiJson(`/api/gastronomia/productos/${activeProduct.id_producto}/validar-selecciones`, {
      method: 'POST',
      body: JSON.stringify({opciones: selectedOptions, canal_precio: activeProduct.canal_precio || null}),
    });
    const configuredItem = {
      key: editingItemKey || `${Date.now()}-${Math.random()}`,
      producto_id: activeProduct.id_producto,
      canal_precio: activeProduct.canal_precio || null,
      nombre: activeProduct.nombre,
      cantidad: Math.max(1, Number(modalQty.value || 1)),
      precio_unitario: validation.total,
      precio_base: Number(activeProduct.precio_base ?? activeProduct.precio ?? 0),
      promocion_activa: validation.producto?.promocion_activa || activeProduct.promocion_activa || null,
      opciones: selectedOptions,
      selecciones: validation.selecciones || [],
      notas: modalNote.value.trim(),
    };
    if (editingItemKey) {
      cart = cart.map((item) => item.key === editingItemKey ? configuredItem : item);
    } else {
      cart.push(configuredItem);
    }
    lastOrderId = activeOrderId || null;
    closeModal();
    renderCart();
  };

  const editCartItem = async (itemKey) => {
    const item = cart.find((cartItem) => cartItem.key === itemKey);
    if (!item) {
      showAlert('No se pudo abrir el item para editar.', false);
      return;
    }
    const canal = encodeURIComponent(item.canal_precio || '');
    const data = await apiJson(`/api/gastronomia/productos/${item.producto_id}?modificadores=1&canal_precio=${canal}`);
    openProduct(data.producto, item);
  };

  const renderCart = () => {
    cartItems.innerHTML = cart.map((item) => `
      <article class="rounded-lg border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-gray-900">
        <div class="grid grid-cols-[38px_1fr_auto] items-start gap-2.5">
          <span class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 text-sm font-black text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white">${item.cantidad}</span>
          <div class="min-w-0">
            <h3 class="text-sm font-black leading-tight text-gray-900 dark:text-white">${escapeHtml(item.nombre)}</h3>
            <p class="mt-0.5 text-xs text-gray-500">${escapeHtml(item.selecciones.map(formatModifierName).join(', '))}</p>
            ${item.notas ? `<p class="mt-1 rounded bg-orange-50 px-2 py-1 text-xs font-bold text-orange-700 dark:bg-orange-500/10 dark:text-orange-200">${escapeHtml(item.notas)}</p>` : ''}
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button type="button" data-edit="${item.key}" class="rounded-lg border border-amber-200 px-2 py-1 text-xs font-bold text-amber-700 hover:bg-amber-50" aria-label="Editar ${escapeHtml(item.nombre)}">
              <i class="fas fa-pen" aria-hidden="true"></i>
            </button>
            <button type="button" data-remove="${item.key}" class="rounded-lg border border-red-200 px-2 py-1 text-xs font-bold text-red-600 hover:bg-red-50" aria-label="Quitar ${escapeHtml(item.nombre)}">
              <i class="fas fa-times" aria-hidden="true"></i>
            </button>
          </div>
        </div>
        <div class="mt-1.5 flex justify-between text-sm">
          <span class="font-semibold text-gray-500">${money(item.precio_unitario)} c/u</span>
          <strong class="font-black text-gray-900 dark:text-white">${money(promotions.subtotal(item))}</strong>
        </div>
      </article>
    `).join('') || '<div class="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">Sin items.</div>';
    cartTotal.textContent = money(cartTotalAmount());
    window.GastronomiaStockAlerts?.refresh(cart);
  };

  const cartSubtotal = () => cart.reduce((sum, item) => sum + promotions.subtotal(item), 0);
  const deliveryShippingCost = () => (
    (orderTypeInput?.value || '') === 'delivery'
      ? Math.max(0, Number(deliveryShippingInput?.value || 0))
      : 0
  );
  const cartTotalAmount = () => cartSubtotal() + deliveryShippingCost();

  const buildOrderPayload = () => ({
    tipo_pedido: orderTypeInput?.value || 'mostrador',
    mesa: tableNameInput?.value.trim() || '',
    referencia_entrega: deliveryReferenceInput?.value.trim() || '',
    nombre_cliente: deliveryReferenceInput?.value.trim() || '',
    celular_cliente: deliveryPhoneInput?.value.trim() || '',
    direccion_entrega: deliveryAddressInput?.value.trim() || '',
    tiempo_estimado_minutos: deliveryEstimateInput?.value || null,
    costo_envio: deliveryShippingCost(),
    notas: document.getElementById('order-notes').value.trim(),
    items: cart.map((item) => ({
      producto_id: item.producto_id,
      canal_precio: item.canal_precio || null,
      cantidad: item.cantidad,
      opciones: item.opciones,
      notas: item.notas,
    })),
  });

  const saveOrder = async ({resetAfterCreate = true} = {}) => {
    if (!cart.length) throw new Error('El pedido debe tener items.');
    if ((orderTypeInput?.value || '') === 'mesa' && !(tableNameInput?.value || '').trim()) {
      throw new Error('Selecciona una mesa.');
    }
    if ((orderTypeInput?.value || '') === 'delivery') {
      if (!(deliveryPhoneInput?.value || '').trim()) throw new Error('Carga el celular del cliente.');
      if (!(deliveryAddressInput?.value || '').trim()) throw new Error('Carga la direccion de entrega.');
    }
    const orderId = activeOrderId;
    const data = await apiJson(orderId ? `/api/gastronomia/pedidos/${orderId}` : '/api/gastronomia/pedidos', {
      method: orderId ? 'PUT' : 'POST',
      body: JSON.stringify(buildOrderPayload()),
    });
    const savedOrderId = Number(data?.pedido?.id_pedido || orderId || activeOrderId || lastOrderId || 0);
    if (!savedOrderId) {
      throw new Error('No se pudo guardar el pedido correctamente.');
    }
    lastOrderId = savedOrderId;
    if (orderId) {
      hydrateOrder(data.pedido);
      showSavedOrderAlert(data.pedido, `Pedido #${lastOrderId} actualizado.`);
      return lastOrderId;
    }
    if (resetAfterCreate) {
      resetDraft();
    } else {
      hydrateOrder(data.pedido);
    }
    showSavedOrderAlert(data.pedido, `Pedido #${savedOrderId} guardado.`);
    return savedOrderId;
  };

  const ensureOrderSavedForNextStep = async () => {
    if (cart.length || activeOrderId) {
      return Number(await saveOrder({resetAfterCreate: false}) || 0);
    }
    return Number(lastOrderId || 0);
  };

  const sendKitchen = async () => {
    const pedidoId = await ensureOrderSavedForNextStep();
    if (!pedidoId) throw new Error('No se pudo preparar el pedido para cocina.');
    await apiJson(`/api/gastronomia/pedidos/${pedidoId}/enviar-cocina`, {method: 'POST', body: '{}'});
    resetDraft();
    lastOrderId = null;
    showAlert(`Pedido #${pedidoId} enviado a cocina.`, true);
  };

  const openAdvancedCheckoutAndSendKitchen = async () => {
    const pedidoId = await ensureOrderSavedForNextStep();
    if (!pedidoId) throw new Error('No se pudo preparar el pedido para cobro.');
    const data = await apiJson(`/api/gastronomia/pedidos/${pedidoId}/cobro-avanzado`, {
      method: 'POST',
      body: JSON.stringify({enviar_cocina: true}),
    });
    if (data.redirect_url) {
      window.location.href = data.redirect_url;
      return;
    }
    const checkoutUrl = data.checkout_url || (data.cola_id ? `/ventas/pos?cola_id=${encodeURIComponent(data.cola_id)}` : '');
    if (!checkoutUrl) throw new Error('No se pudo abrir el checkout central.');
    resetDraft();
    lastOrderId = null;
    window.location.href = checkoutUrl;
  };

  const closeModal = () => {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    activeProduct = null;
    editingItemKey = null;
  };

  const runBusyAction = async (button, busyText, action) => {
    if (button?.disabled) return;
    const originalText = button?.textContent;
    if (button) {
      button.disabled = true;
      button.textContent = busyText;
      button.classList.add('opacity-70', 'cursor-not-allowed');
    }
    try {
      await action();
    } catch (error) {
      if (error?.redirectUrl) {
        showAlert(error.message, false);
        window.location.href = error.redirectUrl;
        return;
      }
      showAlert(error.message, false);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
        button.classList.remove('opacity-70', 'cursor-not-allowed');
      }
    }
  };

  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }[char]));
  const safeImageUrl = (value) => {
    const url = String(value || '').trim();
    if (!url || /^javascript:/i.test(url)) return '';
    return url;
  };
  const renderProductImage = (product) => {
    const imageUrl = safeImageUrl(product?.imagen_url);
    if (!imageUrl) return '';
    return `
      <span class="pos-product-image-wrap mb-2 block overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800">
        <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(product.nombre)}" class="pos-product-image" loading="lazy" onerror="this.closest('.pos-product-image-wrap').remove()">
      </span>
    `;
  };
  const fitCategoryLabels = () => {
    document.querySelectorAll('.pos-category > span:not([data-category-drag-handle])').forEach((label) => {
      label.style.fontSize = '';
      let size = parseFloat(getComputedStyle(label).fontSize || '11');
      while (label.scrollWidth > label.clientWidth && size > 7.5) {
        size -= 0.5;
        label.style.fontSize = `${size}px`;
      }
    });
  };
  document.getElementById('category-tabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-category]');
    if (!button) return;
    selectedCategory = button.dataset.category;
    selectedPriceChannel = button.dataset.priceChannel || '';
    document.querySelectorAll('.pos-category').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    loadProducts().catch((error) => showAlert(error.message, false));
  });
  productSearch?.addEventListener('input', () => {
    syncProductSearchClearButton();
    renderProducts();
  });
  clearProductSearchButton?.addEventListener('click', () => {
    if (!productSearch) return;
    productSearch.value = '';
    syncProductSearchClearButton();
    renderProducts();
    productSearch.focus();
  });
  deliveryShippingInput?.addEventListener('input', renderCart);
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
      editCartItem(editButton.dataset.edit).catch((error) => showAlert(error.message, false));
      return;
    }
    const button = event.target.closest('[data-remove]');
    if (!button) return;
    cart = cart.filter((item) => item.key !== button.dataset.remove);
    lastOrderId = null;
    renderCart();
  });
  document.getElementById('close-modal')?.addEventListener('click', closeModal);
  document.getElementById('add-configured-product')?.addEventListener('click', (event) => {
    runBusyAction(event.currentTarget, editingItemKey ? 'Guardando...' : 'Agregando...', addConfiguredProduct);
  });
  document.getElementById('clear-cart')?.addEventListener('click', resetDraft);
  document.getElementById('save-order')?.addEventListener('click', (event) => {
    runBusyAction(event.currentTarget, 'Guardando...', saveOrder);
  });
  document.getElementById('send-kitchen')?.addEventListener('click', (event) => {
    runBusyAction(event.currentTarget, 'Enviando...', sendKitchen);
  });
  document.getElementById('charge-send-kitchen')?.addEventListener('click', (event) => {
    runBusyAction(event.currentTarget, 'Abriendo cobro...', openAdvancedCheckoutAndSendKitchen);
  });

  const mesaInicial = root?.dataset.mesaInicial || '';
  const tipoInicial = root?.dataset.tipoInicial || '';
  const pedidoInicialId = Number(root?.dataset.pedidoInicialId || 0);
  if (pedidoInicialId) {
    loadOrder(pedidoInicialId).catch((error) => showAlert(error.message, false));
  } else if (mesaInicial) {
    setOrderType('mesa');
    setMesa(mesaInicial);
  } else if (tipoInicial === 'delivery') {
    setOrderType('delivery');
  }
  syncOrderTypeUi();
  loadProducts().catch((error) => showAlert(error.message, false));
  loadMesas().catch((error) => showAlert(error.message, false));
  syncProductSearchClearButton();
  fitCategoryLabels();
  window.addEventListener('resize', fitCategoryLabels);
  renderCart();
}());
