// Idempotente: el dashboard se re-dibuja en segundo plano al volver a su pestaña
// (refresco silencioso) y el script inline del template vuelve a llamar al init.
// Las tarjetas viven en un grid por grupo: se reordenan dentro de su grupo y el
// orden guardado es la concatenacion de todos los grupos.
window.initGastroDashboardCardOrder = function () {
  const grids = Array.from(document.querySelectorAll('[data-dashboard-card-grid]'))
    .filter((grid) => grid.dataset.cardOrderReady !== '1');
  if (!grids.length) return;
  grids.forEach((grid) => { grid.dataset.cardOrderReady = '1'; });
  const csrf = document.getElementById('csrf-token')?.value
    || document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
    || '';
  let draggedCard = null;
  let armedCard = null;
  let previousOrder = [];
  let orderSaveQueued = false;
  let suppressNextClick = false;

  const cards = () => grids.flatMap((grid) => Array.from(grid.querySelectorAll('[data-dashboard-card-id]')));
  const currentOrder = () => cards().map((card) => String(card.dataset.dashboardCardId || '')).filter(Boolean);

  const setSaving = (saving) => {
    cards().forEach((card) => card.classList.toggle('is-saving', saving));
  };

  const restoreOrder = (order) => {
    if (!order.length) return;
    const cardById = new Map(cards().map((card) => [String(card.dataset.dashboardCardId || ''), card]));
    order.forEach((id) => {
      const card = cardById.get(String(id));
      if (card) card.parentElement.appendChild(card);
    });
  };

  const saveOrder = async (order) => {
    setSaving(true);
    try {
      const response = await fetch('/api/gastronomia/dashboard/orden', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({cards: order}),
      });
      const data = await response.json();
      if (!response.ok || data.ok !== true) {
        throw new Error(data.mensaje || data.error || 'No se pudo guardar el orden.');
      }
    } catch (error) {
      restoreOrder(previousOrder);
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const cardFromEvent = (event) => event.target.closest('[data-dashboard-card-id]');

  const persistChangedOrder = () => {
    if (!draggedCard || orderSaveQueued) return;
    const nextOrder = currentOrder();
    if (nextOrder.join(',') !== previousOrder.join(',')) {
      orderSaveQueued = true;
      suppressNextClick = true;
      saveOrder(nextOrder);
    }
  };

  const shouldInsertAfter = (event, targetCard) => {
    const box = targetCard.getBoundingClientRect();
    const sameVisualRow = event.clientY >= box.top && event.clientY <= box.bottom;
    if (sameVisualRow) {
      return event.clientX > box.left + (box.width / 2);
    }
    return event.clientY > box.top + (box.height / 2);
  };

  grids.forEach((grid) => {
    grid.addEventListener('pointerdown', (event) => {
      const handle = event.target.closest('[data-dashboard-card-drag-handle]');
      if (!handle) return;
      armedCard = handle.closest('[data-dashboard-card-id]');
    });

    grid.addEventListener('keydown', (event) => {
      const handle = event.target.closest('[data-dashboard-card-drag-handle]');
      if (!handle || !['Enter', ' '].includes(event.key)) return;
      event.preventDefault();
      handle.closest('[data-dashboard-card-id]')?.focus();
    });

    grid.addEventListener('click', (event) => {
      if (event.target.closest('[data-dashboard-card-drag-handle]')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        suppressNextClick = false;
        return;
      }
      if (!suppressNextClick) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      suppressNextClick = false;
    }, true);

    grid.addEventListener('dragstart', (event) => {
      const handle = event.target.closest('[data-dashboard-card-drag-handle]');
      const card = cardFromEvent(event);
      if (!card || (armedCard !== card && !handle)) {
        event.preventDefault();
        return;
      }
      draggedCard = card;
      previousOrder = currentOrder();
      orderSaveQueued = false;
      card.classList.add('is-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', card.dataset.dashboardCardId || '');
    });

    grid.addEventListener('dragover', (event) => {
      if (!draggedCard) return;
      const targetCard = cardFromEvent(event);
      if (!targetCard || targetCard === draggedCard || targetCard.parentElement !== draggedCard.parentElement) return;
      event.preventDefault();
      const insertAfter = shouldInsertAfter(event, targetCard);
      grid.insertBefore(draggedCard, insertAfter ? targetCard.nextSibling : targetCard);
    });

    grid.addEventListener('drop', (event) => {
      if (!draggedCard) return;
      event.preventDefault();
      suppressNextClick = true;
      persistChangedOrder();
    });

    grid.addEventListener('dragend', () => {
      persistChangedOrder();
      if (draggedCard) draggedCard.classList.remove('is-dragging');
      draggedCard = null;
      armedCard = null;
    });
  });
};

window.initGastroDashboardCardOrder();
