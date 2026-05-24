(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const board = document.getElementById('salon-config-board');
  const alertBox = document.getElementById('salon-config-alert');
  let mesas = [];

  const showAlert = (message, ok) => {
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };
  const apiJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {})},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'Solicitud invalida.');
    return data;
  };
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));

  const loadMesas = async () => {
    const data = await apiJson('/api/gastronomia/salon/mesas');
    mesas = data.mesas || [];
    renderBoard();
  };
  const renderBoard = () => {
    if (!board) return;
    board.innerHTML = mesas.map((mesa) => `
      <article class="salon-config-card">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-lg font-bold text-gray-900 dark:text-white">${escapeHtml(mesa.nombre)}</h3>
            <p class="mt-1 text-sm text-gray-500">${escapeHtml(mesa.ubicacion || 'Salon')}</p>
          </div>
          <button type="button" data-edit="${mesa.id_mesa}" class="rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 dark:border-gray-700 dark:text-gray-200">
            Editar
          </button>
        </div>
        <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div class="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/40">
            <span class="block text-gray-500">Capacidad</span>
            <strong class="text-gray-900 dark:text-white">${mesa.capacidad || 0}</strong>
          </div>
          <div class="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/40">
            <span class="block text-gray-500">Orden</span>
            <strong class="text-gray-900 dark:text-white">${mesa.orden || 0}</strong>
          </div>
        </div>
      </article>
    `).join('') || '<div class="rounded-xl border border-dashed border-gray-300 p-8 text-center text-gray-500 dark:border-gray-700 sm:col-span-2 xl:col-span-3">Sin mesas cargadas.</div>';
  };
  const resetForm = () => {
    document.getElementById('table-id').value = '';
    document.getElementById('table-name-input').value = '';
    document.getElementById('table-location').value = '';
    document.getElementById('table-capacity').value = 4;
    document.getElementById('table-order').value = 0;
  };
  const fillForm = (mesa) => {
    document.getElementById('table-id').value = mesa.id_mesa;
    document.getElementById('table-name-input').value = mesa.nombre;
    document.getElementById('table-location').value = mesa.ubicacion || '';
    document.getElementById('table-capacity').value = mesa.capacidad || 4;
    document.getElementById('table-order').value = mesa.orden || 0;
  };
  const saveTable = async () => {
    const id = document.getElementById('table-id').value;
    const payload = {
      nombre: document.getElementById('table-name-input').value.trim(),
      ubicacion: document.getElementById('table-location').value.trim(),
      capacidad: Number(document.getElementById('table-capacity').value || 4),
      orden: Number(document.getElementById('table-order').value || 0),
    };
    const url = id ? `/api/gastronomia/salon/mesas/${id}` : '/api/gastronomia/salon/mesas';
    await apiJson(url, {method: id ? 'PUT' : 'POST', body: JSON.stringify(payload)});
    showAlert('Mesa guardada.', true);
    resetForm();
    await loadMesas();
  };

  board?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-edit]');
    if (!button) return;
    const mesa = mesas.find((item) => Number(item.id_mesa) === Number(button.dataset.edit));
    if (mesa) fillForm(mesa);
  });
  document.getElementById('table-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    saveTable().catch((error) => showAlert(error.message, false));
  });
  document.getElementById('reset-table-form')?.addEventListener('click', resetForm);
  loadMesas().catch((error) => showAlert(error.message, false));
}());
