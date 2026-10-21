// Bloque de encargo en la tarjeta de cocina: fecha de retiro y fotos de referencia.
// Cocina nunca recibe senas ni saldos (los oculta el servidor); aca solo se muestra lo operativo.
(() => {
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  const formatPickup = (value) => {
    const date = new Date(value || '');
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('es', {weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
  };

  // Solo URLs propias de static: una URL externa o con esquema no se pinta.
  const safePhotoUrl = (url) => (typeof url === 'string' && url.startsWith('/static/') ? url : '');

  const renderPhotos = (fotos) => {
    const items = (fotos || []).map((foto) => safePhotoUrl(foto.url)).filter(Boolean);
    if (!items.length) return '';
    return `
      <div class="mt-2 flex flex-wrap gap-2" aria-label="Fotos de referencia">
        ${items.map((url) => `
          <a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="block h-16 w-16 overflow-hidden rounded-lg border border-violet-400/30">
            <img src="${escapeHtml(url)}" alt="Foto de referencia" loading="lazy" class="h-full w-full object-cover">
          </a>
        `).join('')}
      </div>
    `;
  };

  // Texto a escribir en la torta, destacado para que no se pierda entre las notas.
  const renderTexts = (items) => (items || [])
    .filter((item) => item.texto_personalizado)
    .map((item) => `<p class="mt-1 text-sm font-black text-violet-200">${escapeHtml(item.nombre_producto)}: "${escapeHtml(item.texto_personalizado)}"</p>`)
    .join('');

  const render = (order) => {
    if (!order || !order.es_encargo) return '';
    const pickup = formatPickup(order.fecha_programada);
    return `
      <div class="mt-3 rounded-lg border border-violet-400/25 bg-violet-400/10 p-2 text-xs font-bold text-violet-200">
        <p><i class="fas fa-cake-candles mr-1"></i>Encargo${pickup ? ` - retira ${escapeHtml(pickup)}` : ''}</p>
        ${renderTexts(order.items)}
        ${renderPhotos(order.fotos)}
      </div>
    `;
  };

  window.CocinaEncargo = {render};
})();
