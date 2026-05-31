(function () {
  const alertBox = document.getElementById('pos-alert');
  const csrf = document.getElementById('csrf-token')?.value || '';
  let timer = null;
  let requestVersion = 0;

  const clearPreview = () => {
    if (!alertBox || alertBox.dataset.stockPreview !== '1') return;
    alertBox.textContent = '';
    alertBox.className = 'mb-4 hidden rounded-lg border px-4 py-3 text-sm font-semibold';
    delete alertBox.dataset.stockPreview;
  };
  const showPreview = (alerts) => {
    if (!alertBox) return;
    const messages = alerts.map((item) => item.mensaje).filter(Boolean);
    if (!messages.length) {
      clearPreview();
      return;
    }
    alertBox.textContent = `Alerta de stock: ${messages.join(' ')}`;
    alertBox.className = 'mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900';
    alertBox.dataset.stockPreview = '1';
  };
  const requestPreview = async (items, version) => {
    try {
      const response = await fetch('/api/gastronomia/stock/previsualizar-pedido', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({items}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo verificar el stock.');
      if (version === requestVersion) showPreview(data.alertas || []);
    } catch (error) {
      if (version === requestVersion) console.error('Stock preview failed:', error);
    }
  };
  const refresh = (items) => {
    clearTimeout(timer);
    requestVersion += 1;
    if (!items?.length) {
      clearPreview();
      return;
    }
    const version = requestVersion;
    timer = setTimeout(() => requestPreview(items.map((item) => ({
      producto_id: item.producto_id,
      cantidad: item.cantidad,
      opciones: item.opciones || [],
    })), version), 120);
  };

  window.GastronomiaStockAlerts = {refresh};
}());
