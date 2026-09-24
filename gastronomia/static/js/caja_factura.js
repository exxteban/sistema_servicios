// Factura electronica en la caja gastronomica.
// La emision es la del modulo facturacion_electronica (/facturacion-electronica/emitir-pos),
// igual que en el POS del sistema padre: si falla, la venta ya quedo cobrada y se
// imprime el ticket normal; el envio automatico reintenta el documento solo.
(function () {
  const panel = document.getElementById('fe-panel');
  const csrf = document.getElementById('csrf-token')?.value || '';
  const disabled = {
    payload: () => ({}),
    requested: () => false,
    reset: () => {},
    emitir: async () => false,
  };
  if (!panel) {
    window.GastroCajaFactura = disabled;
    return;
  }

  const checkbox = document.getElementById('fe-emitir');
  const clientBox = document.getElementById('fe-cliente-box');
  const currentLabel = document.getElementById('fe-cliente-actual');
  const clearButton = document.getElementById('fe-cliente-limpiar');
  const searchInput = document.getElementById('fe-cliente-q');
  const resultsEl = document.getElementById('fe-cliente-resultados');
  const newName = document.getElementById('fe-nuevo-nombre');
  const newRuc = document.getElementById('fe-nuevo-ruc');
  const newSave = document.getElementById('fe-nuevo-guardar');
  const timeoutMs = Number(panel.dataset.feTimeoutMs) || 110000;
  let selectedClient = null;
  let searchTimer = null;

  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({}));
    return {ok: response.ok, data};
  };

  const renderClient = () => {
    currentLabel.textContent = selectedClient
      ? `${selectedClient.nombre} (${selectedClient.ruc_ci || 'sin RUC'})`
      : 'Consumidor final';
    clearButton.classList.toggle('hidden', !selectedClient);
  };
  const selectClient = (client) => {
    selectedClient = client;
    resultsEl.innerHTML = '';
    searchInput.value = '';
    renderClient();
  };
  const renderResults = (clients) => {
    resultsEl.innerHTML = clients.map((client, index) => `
      <button type="button" data-fe-client="${index}"
              class="block w-full rounded-lg border border-gray-200 px-3 py-2 text-left text-sm hover:bg-emerald-50 dark:border-gray-700">
        <strong>${escapeHtml(client.nombre)}</strong>
        <span class="block text-xs text-gray-500">${escapeHtml(client.ruc_ci || 'sin RUC')}</span>
      </button>
    `).join('') || '<p class="text-xs text-gray-500">Sin coincidencias. Podes cargarlo como cliente nuevo.</p>';
    resultsEl.querySelectorAll('[data-fe-client]').forEach((button) => {
      button.addEventListener('click', () => selectClient(clients[Number(button.dataset.feClient)]));
    });
  };
  const search = async () => {
    const q = searchInput.value.trim();
    if (q.length < 2) {
      resultsEl.innerHTML = '';
      return;
    }
    const {ok, data} = await requestJson(`/api/gastronomia/caja/clientes-factura?q=${encodeURIComponent(q)}`);
    if (ok) renderResults(data.clientes || []);
  };
  const createClient = async () => {
    const {ok, data} = await requestJson('/api/gastronomia/caja/clientes-factura', {
      method: 'POST',
      body: JSON.stringify({nombre: newName.value.trim(), ruc_ci: newRuc.value.trim()}),
    });
    if (!ok) {
      window.alert(data.mensaje || 'No se pudo guardar el cliente.');
      return;
    }
    newName.value = '';
    newRuc.value = '';
    newSave.closest('details')?.removeAttribute('open');
    selectClient(data.cliente);
  };

  const estadoEmitido = async (idVenta) => {
    try {
      const response = await fetch(`/facturacion-electronica/estado-pos/${idVenta}`, {cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.success) return data;
    } catch (error) {
      // sin red: se cae al ticket
    }
    return null;
  };
  const abrir = (url, targetWindow) => {
    if (targetWindow && !targetWindow.closed) {
      targetWindow.location = url;
      return true;
    }
    return !!window.open(url, '_blank');
  };

  // Devuelve true si abrio el KuDE; false si cayo al ticket normal.
  const emitir = async (idVenta, targetWindow, ticketUrl, notify) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let detail = 'no se pudo emitir la factura electronica.';
    try {
      const response = await fetch(`/facturacion-electronica/emitir-pos/${idVenta}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.success) return abrir(data.kude_url, targetWindow);
      if (data.error) detail = data.error;
    } catch (error) {
      detail = error?.name === 'AbortError'
        ? 'la factura electronica tardo demasiado en responder.'
        : 'fallo la factura electronica.';
    } finally {
      clearTimeout(timer);
    }
    const recovered = await estadoEmitido(idVenta);
    if (recovered) return abrir(recovered.kude_url, targetWindow);
    notify(`Venta #${idVenta} cobrada, pero ${detail} Se imprime el ticket normal; la factura se reintenta sola.`, false);
    abrir(ticketUrl, targetWindow);
    return false;
  };

  checkbox.addEventListener('change', () => clientBox.classList.toggle('hidden', !checkbox.checked));
  clearButton.addEventListener('click', () => selectClient(null));
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => search().catch(() => {}), 250);
  });
  newSave.addEventListener('click', () => createClient().catch(() => window.alert('No se pudo guardar el cliente.')));

  window.GastroCajaFactura = {
    requested: () => checkbox.checked,
    payload: () => (checkbox.checked
      ? {factura_electronica: true, id_cliente_factura: selectedClient?.id_cliente || null}
      : {}),
    reset: () => {
      checkbox.checked = false;
      clientBox.classList.add('hidden');
      selectClient(null);
    },
    emitir,
  };
}());
