(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const alertBox = document.getElementById('gastro-menu-alert');
  const tbody = document.getElementById('categorias-body');
  let draggedRow = null;
  let previousOrder = [];

  const rows = () => Array.from(tbody?.querySelectorAll('[data-category-order-row]') || []);
  const currentOrder = () => rows().map((row) => Number(row.dataset.categoryOrderRow)).filter(Boolean);

  const showAlert = (message, ok) => {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };

  const setRowsSaving = (saving) => {
    rows().forEach((row) => row.classList.toggle('is-saving', saving));
    tbody?.querySelectorAll('[data-category-drag-handle]').forEach((button) => {
      button.disabled = saving;
    });
  };

  const restoreOrder = (order) => {
    if (!tbody || !order.length) return;
    const rowById = new Map(rows().map((row) => [Number(row.dataset.categoryOrderRow), row]));
    order.forEach((id) => {
      const row = rowById.get(Number(id));
      if (row) tbody.appendChild(row);
    });
  };

  const updateOrderCells = (categorias) => {
    const ordersById = new Map((categorias || []).map((categoria) => [
      Number(categoria.id_categoria),
      Number(categoria.orden || 0),
    ]));
    rows().forEach((row) => {
      const order = ordersById.get(Number(row.dataset.categoryOrderRow));
      if (!order) return;
      const orderCell = row.querySelector('[data-category-order-value]');
      const editButton = row.querySelector('[data-edit-category]');
      if (orderCell) orderCell.textContent = String(order);
      if (editButton) editButton.dataset.categoryOrder = String(order);
    });
  };

  const saveOrder = async (order) => {
    setRowsSaving(true);
    try {
      const response = await fetch('/api/gastronomia/categorias/orden', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({categorias: order}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo guardar el orden.');
      updateOrderCells(data.categorias || []);
      showAlert('Orden de categorias guardado.', true);
    } catch (error) {
      restoreOrder(previousOrder);
      showAlert(error.message, false);
    } finally {
      setRowsSaving(false);
    }
  };

  const rowFromEvent = (event) => event.target.closest('[data-category-order-row]');

  tbody?.addEventListener('dragstart', (event) => {
    const handle = event.target.closest('[data-category-drag-handle]');
    const row = rowFromEvent(event);
    if (!handle || !row) {
      event.preventDefault();
      return;
    }
    draggedRow = row;
    previousOrder = currentOrder();
    row.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', row.dataset.categoryOrderRow || '');
  });

  tbody?.addEventListener('dragover', (event) => {
    if (!draggedRow) return;
    const targetRow = rowFromEvent(event);
    if (!targetRow || targetRow === draggedRow) return;
    event.preventDefault();
    const box = targetRow.getBoundingClientRect();
    const insertAfter = event.clientY > box.top + (box.height / 2);
    tbody.insertBefore(draggedRow, insertAfter ? targetRow.nextSibling : targetRow);
  });

  tbody?.addEventListener('drop', (event) => {
    if (!draggedRow) return;
    event.preventDefault();
    const nextOrder = currentOrder();
    if (nextOrder.join(',') !== previousOrder.join(',')) {
      saveOrder(nextOrder);
    }
  });

  tbody?.addEventListener('dragend', () => {
    if (draggedRow) draggedRow.classList.remove('is-dragging');
    draggedRow = null;
  });
}());
