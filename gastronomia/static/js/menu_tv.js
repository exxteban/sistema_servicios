(function () {
  const root = document.querySelector('[data-menu-tv]');
  const content = document.getElementById('menu-tv-content');
  const title = document.getElementById('menu-tv-title');
  const subtitle = document.getElementById('menu-tv-subtitle');
  const clock = document.getElementById('menu-tv-clock');
  const status = document.getElementById('menu-tv-status');
  if (!root || !content || !title || !subtitle || !clock) return;

  const slug = root.dataset.slug || '';
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let refreshTimer = null;
  let rotationTimer = null;
  let resizeTimer = null;
  let animationFrame = null;
  let currentData = null;

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
    currentData = data;
    clearRotation();
    const config = data.config || {};
    document.body.classList.toggle('menu-tv-high', config.tema === 'alto_contraste');
    title.textContent = config.titulo || 'Menu';
    subtitle.textContent = config.subtitulo || '';
    content.className = 'menu-tv-grid';
    const categorias = (data.categorias || []).filter((category) => productsForCategory(category, config).length);
    content.innerHTML = categorias.map((category) => renderCategory(category, config)).join('') || `
      <div class="menu-tv-empty">Menu no disponible por el momento.</div>
    `;
    window.requestAnimationFrame(() => setupShowcase(data));
  };

  const productsForCategory = (category, config) => (
    category.productos || []
  ).filter((product) => config.mostrar_agotados || product.disponible);

  const renderCategory = (category, config) => {
    const products = productsForCategory(category, config);
    return `
      <article class="menu-tv-category">
        <h2>${escapeHtml(category.nombre)}</h2>
        ${products.map((product) => renderProduct(product, config)).join('')}
      </article>
    `;
  };

  const renderProduct = (product, config) => {
    const image = renderProductImage(product);
    const previousPrice = product.precio_anterior
      ? `<span class="menu-tv-price-old">${money(product.precio_anterior)}</span>`
      : '';
    const price = config.mostrar_precios ? `${previousPrice}<strong class="menu-tv-price">${money(product.precio)}</strong>` : '';
    const promotionBadge = product.promocion_activa?.etiqueta
      ? `<span class="menu-tv-promo-badge">${escapeHtml(product.promocion_activa.etiqueta)}</span>`
      : '';
    return `
    <div class="menu-tv-product ${image ? 'menu-tv-product--with-image' : ''} ${product.disponible ? '' : 'menu-tv-soldout'}">
      ${image}
      <div class="menu-tv-product-details">
        <div class="menu-tv-product-head">
          <h3>${escapeHtml(product.nombre)}</h3>
          ${price}
        </div>
        ${product.descripcion ? `<p>${escapeHtml(product.descripcion)}</p>` : ''}
        ${promotionBadge}
        ${product.disponible ? '' : '<span class="menu-tv-badge">Agotado</span>'}
      </div>
    </div>
  `;
  };

  const safeImageUrl = (value) => {
    const url = String(value || '').trim();
    if (!url || /^javascript:/i.test(url)) return '';
    return url;
  };

  const renderProductImage = (product) => {
    const imageUrl = safeImageUrl(product?.imagen_url);
    if (!imageUrl) return '';
    return `
      <div class="menu-tv-product-image-wrap">
        <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(product.nombre)}" class="menu-tv-product-image" loading="lazy" onerror="this.closest('.menu-tv-product-image-wrap').remove()">
      </div>
    `;
  };

  const setupShowcase = (data) => {
    if (prefersReducedMotion.matches) {
      setStatus('');
      return;
    }
    const config = data.config || {};
    const mode = chooseRotationMode(config.modo_rotacion);
    if (mode === 'slides' && activateSlides(data)) {
      return;
    }
    if (!hasOverflow()) {
      setStatus('');
      return;
    }
    activateScroll();
  };

  const hasOverflow = () => document.documentElement.scrollHeight > window.innerHeight + 24;

  const chooseRotationMode = (mode) => {
    if (mode === 'scroll' || mode === 'slides') return mode;
    return window.innerWidth >= 980 ? 'slides' : 'scroll';
  };

  const activateSlides = (data) => {
    const pages = buildSlidePages(data);
    if (pages.length <= 1) {
      return false;
    }
    document.body.classList.add('menu-tv-slides-active');
    content.className = 'menu-tv-slides';
    content.innerHTML = pages.map((page, index) => `
      <section class="menu-tv-slide ${index === 0 ? 'is-active' : ''}" data-slide-index="${index}">
        ${page.categorias.map((category) => renderCategory(category, data.config || {})).join('')}
      </section>
    `).join('');
    rotateSlides(0, pages.length);
    return true;
  };

  const buildSlidePages = (data) => {
    const layout = estimateSlideLayout();
    const pages = [];
    let current = [];
    const config = data.config || {};
    (data.categorias || []).forEach((category) => {
      const products = productsForCategory(category, config);
      for (let offset = 0; offset < products.length; offset += layout.productsPerCard) {
        const chunk = products.slice(offset, offset + layout.productsPerCard);
        if (current.length >= layout.columns) {
          pages.push({categorias: current});
          current = [];
        }
        current.push({...category, productos: chunk});
      }
    });
    if (current.length) pages.push({categorias: current});
    return pages;
  };

  const estimateSlideLayout = () => {
    const headerBottom = root.querySelector('.menu-tv-header')?.getBoundingClientRect().bottom || 180;
    const availableHeight = Math.max(320, window.innerHeight - headerBottom - 72);
    const columns = Math.max(1, Math.floor(content.clientWidth / 540));
    const rowHeight = window.innerWidth >= 1200 ? 134 : 150;
    return {
      columns,
      productsPerCard: Math.max(2, Math.floor(availableHeight / rowHeight) - 1),
    };
  };

  const rotateSlides = (index, total) => {
    const slides = Array.from(content.querySelectorAll('.menu-tv-slide'));
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle('is-active', slideIndex === index);
    });
    setStatus(`Pantalla ${index + 1} de ${total}`);
    rotationTimer = window.setTimeout(() => rotateSlides((index + 1) % total, total), 8200);
  };

  const activateScroll = () => {
    document.body.classList.add('menu-tv-scrolling');
    const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    if (maxScroll < 24) {
      setStatus('');
      return;
    }
    setStatus('Recorriendo menu');
    rotationTimer = window.setTimeout(() => animateScroll(0, maxScroll, scrollDuration(maxScroll), () => {
      rotationTimer = window.setTimeout(() => animateScroll(maxScroll, 0, 900, () => {
        rotationTimer = window.setTimeout(activateScroll, 1800);
      }), 2600);
    }), 1800);
  };

  const scrollDuration = (distance) => Math.max(9000, Math.min(28000, distance * 18));

  const animateScroll = (from, to, duration, done) => {
    const started = performance.now();
    const step = (now) => {
      const progress = Math.min(1, (now - started) / duration);
      const eased = progress < 0.5 ? 2 * progress * progress : 1 - ((-2 * progress + 2) ** 2) / 2;
      window.scrollTo(0, from + ((to - from) * eased));
      if (progress < 1) {
        animationFrame = window.requestAnimationFrame(step);
        return;
      }
      done?.();
    };
    animationFrame = window.requestAnimationFrame(step);
  };

  const setStatus = (message) => {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('is-visible', Boolean(message));
  };

  const clearRotation = () => {
    window.clearTimeout(rotationTimer);
    window.cancelAnimationFrame(animationFrame);
    document.body.classList.remove('menu-tv-slides-active', 'menu-tv-scrolling');
    setStatus('');
    window.scrollTo(0, 0);
  };

  const renderError = (error) => {
    clearRotation();
    content.className = 'menu-tv-grid';
    content.innerHTML = `<div class="menu-tv-empty">${escapeHtml(error.message)}</div>`;
  };

  window.addEventListener('resize', () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      if (currentData) render(currentData);
    }, 220);
  });

  tickClock();
  window.setInterval(tickClock, 1000);
  load().catch(renderError);
}());
