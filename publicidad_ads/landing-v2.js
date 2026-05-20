// Activar clase JS para progressive enhancement
document.documentElement.classList.add('js');

// ===== MINI ANALYTICS =====
const analyticsEndpoint = `${window.location.origin}/api/publicidad-ads/evento`;
const analyticsLandingKey = 'publicidad_ads';
const analyticsTrackedSections = new Set();
const analyticsTrackedScrolls = new Set();

const ensureAnalyticsSessionId = () => {
  const storageKey = 'publicidad_ads_session_id';
  try {
    let value = window.localStorage.getItem(storageKey);
    if (value) return value;
    value = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `ads-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.localStorage.setItem(storageKey, value);
    return value;
  } catch (error) {
    return `ads-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
};

const getAnalyticsMeta = () => {
  const params = new URLSearchParams(window.location.search || '');
  return {
    session_id: ensureAnalyticsSessionId(),
    utm_source: params.get('utm_source') || '',
    utm_medium: params.get('utm_medium') || '',
    utm_campaign: params.get('utm_campaign') || '',
    utm_term: params.get('utm_term') || '',
    utm_content: params.get('utm_content') || '',
  };
};

const trackAnalyticsEvent = (eventType, extra = {}) => {
  if (!window.location.origin || window.location.protocol === 'file:') return;
  const payload = {
    landing: analyticsLandingKey,
    event_type: eventType,
    path: window.location.pathname || '/publicidad-ads/',
    ...getAnalyticsMeta(),
    ...extra,
  };
  const body = JSON.stringify(payload);
  if (navigator.sendBeacon) {
    const blob = new Blob([body], { type: 'application/json' });
    navigator.sendBeacon(analyticsEndpoint, blob);
    return;
  }
  fetch(analyticsEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {});
};

trackAnalyticsEvent('page_view', { label: 'landing_open' });

// Año en footer
document.getElementById('anio').textContent = '\u00A9 ' + new Date().getFullYear() + ' Todos los derechos reservados';

// ===== DIFFERENTIALS CAROUSEL =====
const differentialsTrack = document.getElementById('differentialsTrack');
const differentialsDotsWrap = document.getElementById('differentialsDots');
const differentialsPrev = document.getElementById('differentialsPrev');
const differentialsNext = document.getElementById('differentialsNext');
const differentialsViewport = document.getElementById('differentialsViewport');

if (differentialsTrack && differentialsDotsWrap && differentialsPrev && differentialsNext && differentialsViewport) {
  const slides = Array.from(differentialsTrack.querySelectorAll('.differentials-card'));
  const total = slides.length;
  let current = 0;
  let autoplayId = null;
  const autoplayDelayMs = 4200;

  const dots = slides.map((_, index) => {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.className = 'differentials-dot';
    dot.setAttribute('aria-label', `Ir a tarjeta ${index + 1}`);
    dot.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    dot.addEventListener('click', () => {
      goTo(index, true);
    });
    differentialsDotsWrap.appendChild(dot);
    return dot;
  });

  const update = () => {
    differentialsTrack.style.transform = `translateX(-${current * 100}%)`;
    dots.forEach((dot, index) => {
      dot.setAttribute('aria-selected', index === current ? 'true' : 'false');
    });
  };

  const goTo = (index, userDriven = false) => {
    current = (index + total) % total;
    update();
    if (userDriven) {
      trackAnalyticsEvent('carousel_interaction', { label: `differentials_${current + 1}` });
    }
  };

  const startAutoplay = () => {
    stopAutoplay();
    autoplayId = window.setInterval(() => {
      goTo(current + 1);
    }, autoplayDelayMs);
  };

  const stopAutoplay = () => {
    if (!autoplayId) return;
    window.clearInterval(autoplayId);
    autoplayId = null;
  };

  differentialsPrev.addEventListener('click', () => goTo(current - 1, true));
  differentialsNext.addEventListener('click', () => goTo(current + 1, true));

  differentialsViewport.addEventListener('mouseenter', stopAutoplay);
  differentialsViewport.addEventListener('mouseleave', startAutoplay);
  differentialsViewport.addEventListener('focusin', stopAutoplay);
  differentialsViewport.addEventListener('focusout', startAutoplay);

  update();
  startAutoplay();
}

// ===== LIGHTBOX =====
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightboxImg');
const lightboxClose = document.getElementById('lightboxClose');
const lightboxCaption = document.getElementById('lightboxCaption');

const getGalleryImages = () => Array.from(document.querySelectorAll('.gallery-item img, .showcase-img img'));

const openLightbox = (imgEl) => {
  const src = imgEl.getAttribute('src');
  const alt = imgEl.getAttribute('alt') || '';
  if (!src) return;
  trackAnalyticsEvent('lightbox_open', {
    label: (alt || src.split('/').pop() || 'imagen').slice(0, 120),
  });
  lightboxImg.src = src;
  lightboxImg.alt = alt;
  if (alt.trim()) {
    lightboxCaption.textContent = alt;
    lightboxCaption.hidden = false;
  } else {
    lightboxCaption.textContent = '';
    lightboxCaption.hidden = true;
  }
  lightbox.setAttribute('data-open', 'true');
  lightbox.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
  lightboxClose.focus();
};

const closeLightbox = () => {
  lightbox.setAttribute('data-open', 'false');
  lightbox.setAttribute('aria-hidden', 'true');
  lightboxImg.src = '';
  lightboxImg.alt = '';
  lightboxCaption.textContent = '';
  lightboxCaption.hidden = true;
  document.body.style.overflow = '';
};

getGalleryImages().forEach((img) => {
  img.tabIndex = 0;
  img.setAttribute('role', 'button');
  img.setAttribute('aria-label', (img.getAttribute('alt') || 'Ver imagen ampliada').trim() || 'Ver imagen ampliada');
  img.addEventListener('click', () => openLightbox(img));
  img.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openLightbox(img);
    }
  });
});

lightboxClose.addEventListener('click', closeLightbox);
lightbox.addEventListener('click', (e) => { if (e.target === lightbox) closeLightbox(); });
window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && lightbox.getAttribute('data-open') === 'true') closeLightbox(); });

// ===== MOBILE MENU =====
const mobileToggle = document.getElementById('mobileToggle');
const mobileMenu = document.getElementById('mobileMenu');
if (mobileMenu) mobileMenu.removeAttribute('hidden');
if (mobileToggle && mobileMenu) {
  mobileToggle.addEventListener('click', () => {
    const isOpen = mobileMenu.classList.toggle('open');
    mobileToggle.setAttribute('aria-expanded', String(isOpen));
  });
  mobileMenu.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => {
      mobileMenu.classList.remove('open');
      mobileToggle.setAttribute('aria-expanded', 'false');
    });
  });
}

// ===== SCROLL SPY =====
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('.nav-links a, .mobile-menu a');
const observerSpy = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const id = entry.target.getAttribute('id');
      navLinks.forEach(link => {
        link.classList.toggle('active', link.getAttribute('href') === '#' + id);
      });
    }
  });
}, { rootMargin: '-40% 0px -55% 0px', threshold: 0 });
sections.forEach(sec => observerSpy.observe(sec));

const observerAnalyticsSections = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    const sectionId = entry.target.getAttribute('id');
    if (!sectionId || analyticsTrackedSections.has(sectionId)) return;
    analyticsTrackedSections.add(sectionId);
    trackAnalyticsEvent('section_view', { section_id: sectionId, label: sectionId });
  });
}, { rootMargin: '-15% 0px -55% 0px', threshold: 0.35 });
sections.forEach(sec => observerAnalyticsSections.observe(sec));

// ===== REVEAL ON SCROLL =====
const revealEls = document.querySelectorAll('.reveal');
const observerReveal = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      observerReveal.unobserve(entry.target);
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });
revealEls.forEach(el => observerReveal.observe(el));

// ===== CTA + SCROLL =====
document.querySelectorAll('[data-analytics-cta]').forEach((link) => {
  link.addEventListener('click', () => {
    const section = link.closest('section[id]')?.getAttribute('id') || '';
    trackAnalyticsEvent('cta_click', {
      label: link.getAttribute('data-analytics-cta') || 'cta',
      section_id: section,
    });
  });
});

window.addEventListener('scroll', () => {
  const documentHeight = document.documentElement.scrollHeight - window.innerHeight;
  if (documentHeight <= 0) return;
  const progress = (window.scrollY / documentHeight) * 100;
  [50, 90].forEach((threshold) => {
    if (progress >= threshold && !analyticsTrackedScrolls.has(threshold)) {
      analyticsTrackedScrolls.add(threshold);
      trackAnalyticsEvent('scroll_depth', { label: `scroll_${threshold}` });
    }
  });
}, { passive: true });
