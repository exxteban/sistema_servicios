(function () {
  const csrf = document.getElementById('csrf-token')?.value || '';
  const alertBox = document.getElementById('gastro-menu-alert');

  const showAlert = (message, ok) => {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'}`;
  };

  document.querySelector('[data-gastro-menu]')?.addEventListener('submit', async (event) => {
    const form = event.target.closest('[data-channel-price-form]');
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const originalText = button?.textContent || 'Guardar';
    if (button) {
      button.disabled = true;
      button.textContent = 'Guardando...';
    }
    try {
      const response = await fetch(`/api/gastronomia/precios-canales/${form.dataset.channel}/${form.dataset.productId}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({precio: new FormData(form).get('precio')}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo guardar el precio.');
      showAlert('Precio exclusivo actualizado.', true);
    } catch (error) {
      showAlert(error.message, false);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
      }
    }
  });
}());
