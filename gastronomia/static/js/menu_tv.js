(function () {
  const root = document.querySelector('[data-menu-tv]');
  const content = document.getElementById('menu-tv-content');
  const title = document.getElementById('menu-tv-title');
  const subtitle = document.getElementById('menu-tv-subtitle');
  const clock = document.getElementById('menu-tv-clock');
  if (!root || !content || !title || !subtitle || !clock) return;

  let refreshTimer = null;
  const slug = root.dataset.slug || '';
  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const tickClock = () => {
    clock.textContent = new Date().toLocaleTimeString('es-PY', {hour: '2-digit', minute: '2-digit'});
  };
  const load = async () => {
    const response = await fetch(`/api/gastronomia/public/menu-tv/${encodeURIComponent(slug)}`, {
      headers: {'Accept': 'application/json'},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Menu no disponible.');
    render(data);
    scheduleRefresh(data.config?.intervalo_refresco_seg);
  };
  const scheduleRefresh = (seconds) => {
    window.clearTimeout(refreshTimer);
    const interval = Math.max(15, Number(seconds || 60)) * 1000;
    refreshTimer = window.setTimeout(() => load().catch(renderError), interval);
  };
  const render = (data) => {
    const config = data.config || {};
    document.body.classList.toggle('menu-tv-high', config.tema === 'alto_contraste');
    title.textContent = config.titulo || 'Menu';
    subtitle.textContent = config.subtitulo || '';
    content.innerHTML = (data.categorias || []).map((category) => renderCategory(category, config)).join('') || `
      <div class="menu-tv-empty">Menu no disponible por el momento.</div>
    `;
  };
  const renderCategory = (category, config) => `
    <article class="menu-tv-category">
      <h2>${escapeHtml(category.nombre)}</h2>
      ${(category.productos || []).map((product) => renderProduct(product, config)).join('')}
    </article>
  `;
  const renderProduct = (product, config) => `
    <div class="menu-tv-product ${product.disponible ? '' : 'menu-tv-soldout'}">
      <div>
        <h3>${escapeHtml(product.nombre)}</h3>
        ${product.descripcion ? `<p>${escapeHtml(product.descripcion)}</p>` : ''}
        ${product.disponible ? '' : '<span class="menu-tv-badge">Agotado</span>'}
      </div>
      ${config.mostrar_precios ? `<strong class="menu-tv-price">${money(product.precio)}</strong>` : ''}
    </div>
  `;
  const renderError = (error) => {
    content.innerHTML = `<div class="menu-tv-empty">${escapeHtml(error.message)}</div>`;
  };

  tickClock();
  window.setInterval(tickClock, 1000);
  load().catch(renderError);
}());
