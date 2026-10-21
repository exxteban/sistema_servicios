// Utilidades compartidas por las pantallas de encargos (tablero, formulario y acciones).
(() => {
  const csrfToken = () => document.getElementById('csrf-token')?.value || '';

  const apiJson = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo completar la accion.');
    return data;
  };

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  // fecha_programada llega en hora local sin zona ("2026-10-23T15:00:00").
  const hora = (iso) => String(iso || '').slice(11, 16) || '--:--';
  const isoDia = (date) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  };
  const diaLegible = (isoDate) => {
    const [y, m, d] = String(isoDate || '').split('-').map(Number);
    if (!y) return isoDate || '';
    const date = new Date(y, m - 1, d);
    const texto = date.toLocaleDateString('es', {weekday: 'long', day: 'numeric', month: 'long'});
    return texto.charAt(0).toUpperCase() + texto.slice(1);
  };

  const safePhotoUrl = (url) => (typeof url === 'string' && url.startsWith('/static/') ? url : '');

  const showError = (element, message) => {
    if (!element) return;
    element.textContent = message || '';
    element.classList.toggle('hidden', !message);
  };

  const closeOnButtons = (dialog) => {
    dialog?.querySelectorAll('[data-close]').forEach((button) => {
      button.addEventListener('click', () => dialog.close());
    });
  };

  window.EncargosUI = {apiJson, money, escapeHtml, hora, isoDia, diaLegible, safePhotoUrl, showError, closeOnButtons};
})();
