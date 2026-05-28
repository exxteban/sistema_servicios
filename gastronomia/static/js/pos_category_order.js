(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const alertBox = document.getElementById('pos-alert');
  const list = document.getElementById('category-tabs');
  let draggedItem = null;
  let previousOrder = [];
  let suppressNextClick = false;

  const items = () => Array.from(list?.querySelectorAll('[data-category-order-row]') || []);
  const currentOrder = () => items().map((item) => Number(item.dataset.categoryOrderRow)).filter(Boolean);

  const showAlert = (message, ok) => {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };

  const setSaving = (saving) => {
    items().forEach((item) => item.classList.toggle('is-saving', saving));
    list?.querySelectorAll('[data-category-drag-handle]').forEach((handle) => {
      handle.style.pointerEvents = saving ? 'none' : '';
    });
  };

  const restoreOrder = (order) => {
    if (!list || !order.length) return;
    const itemById = new Map(items().map((item) => [Number(item.dataset.categoryOrderRow), item]));
    order.forEach((id) => {
      const item = itemById.get(Number(id));
      if (item) list.appendChild(item);
    });
  };

  const saveOrder = async (order) => {
    setSaving(true);
    try {
      const response = await fetch('/api/gastronomia/categorias/orden', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({categorias: order}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo guardar el orden.');
      showAlert('Orden de categorias guardado.', true);
    } catch (error) {
      restoreOrder(previousOrder);
      showAlert(error.message, false);
    } finally {
      setSaving(false);
    }
  };

  const itemFromEvent = (event) => event.target.closest('[data-category-order-row]');

  list?.addEventListener('click', (event) => {
    if (!suppressNextClick) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    suppressNextClick = false;
  }, true);

  list?.addEventListener('dragstart', (event) => {
    const handle = event.target.closest('[data-category-drag-handle]');
    const item = itemFromEvent(event);
    if (!handle || !item) {
      event.preventDefault();
      return;
    }
    draggedItem = item;
    previousOrder = currentOrder();
    item.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', item.dataset.categoryOrderRow || '');
  });

  list?.addEventListener('dragover', (event) => {
    if (!draggedItem) return;
    const targetItem = itemFromEvent(event);
    if (!targetItem || targetItem === draggedItem) return;
    event.preventDefault();
    const box = targetItem.getBoundingClientRect();
    const insertAfter = event.clientY > box.top + (box.height / 2);
    list.insertBefore(draggedItem, insertAfter ? targetItem.nextSibling : targetItem);
  });

  list?.addEventListener('drop', (event) => {
    if (!draggedItem) return;
    event.preventDefault();
    suppressNextClick = true;
    const nextOrder = currentOrder();
    if (nextOrder.join(',') !== previousOrder.join(',')) {
      saveOrder(nextOrder);
    }
  });

  list?.addEventListener('dragend', () => {
    if (draggedItem) draggedItem.classList.remove('is-dragging');
    draggedItem = null;
  });
}());
