(function () {
  const warningStates = new Set(['ocupada', 'esperando_cocina', 'listo', 'pagada']);
  const confirmed = new Set();
  const labels = {
    libre: 'Libre',
    ocupada: 'Ocupada',
    esperando_cocina: 'En cocina',
    listo: 'Lista',
    pagada: 'Pagada',
  };

  const key = (value) => String(value || '').trim().toLowerCase();
  const findMesa = (mesas, mesaNombre) => (mesas || []).find((mesa) => key(mesa.nombre) === key(mesaNombre));
  const isBusy = (mesa) => mesa && warningStates.has(mesa.estado_salon);
  const confirmationKey = (mesa) => `${key(mesa.nombre)}:${mesa.estado_salon}:${mesa.pedidos_activos_count || 0}`;

  const message = (mesa) => {
    if (mesa.estado_salon === 'pagada') {
      return `La mesa ${mesa.nombre} ya fue cobrada pero aun no fue liberada. ¿Queres cargar otro pedido igual?`;
    }
    return `La mesa ${mesa.nombre} ya tiene un pedido activo. ¿Queres cargar otro pedido igual?`;
  };

  const confirmSelection = (mesas, mesaNombre) => {
    const mesa = findMesa(mesas, mesaNombre);
    if (!isBusy(mesa)) return true;
    const token = confirmationKey(mesa);
    if (confirmed.has(token)) return true;
    if (!window.confirm(message(mesa))) return false;
    confirmed.add(token);
    return true;
  };

  const render = (mesas, selectedName, escapeHtml) => (mesas || []).map((mesa) => {
    const status = labels[mesa.estado_salon] || mesa.estado_salon || 'Libre';
    const statusClass = isBusy(mesa) ? ` mesa-selector-btn--${mesa.estado_salon}` : '';
    return `
      <button type="button" data-table-name="${escapeHtml(mesa.nombre)}" class="mesa-selector-btn${statusClass} ${selectedName === mesa.nombre ? 'activa' : ''}">
        <span>${escapeHtml(mesa.nombre)}</span>
        <small>${escapeHtml(status)}</small>
      </button>
    `;
  }).join('');

  window.GastronomiaTableWarnings = {confirmSelection, render};
}());
