// Refresca badges de tarjetas y la franja del turno sin re-dibujar el dashboard.
// Idempotente: el refresco silencioso de la pestaña vuelve a llamar al init.
(function () {
  const INTERVAL_MS = 45000;
  const BADGE_TONES = ['alert', 'info', 'neutral'];
  let timer = null;

  const dashboardVisible = () => {
    const root = document.querySelector('[data-dashboard-card-grid]');
    return Boolean(root && root.offsetParent !== null && document.visibilityState === 'visible');
  };

  const applyBadges = (badges) => {
    document.querySelectorAll('[data-dashboard-card-id]').forEach((card) => {
      const el = card.querySelector('[data-dashboard-badge]');
      if (!el) return;
      const badge = badges[card.dataset.dashboardCardId];
      BADGE_TONES.forEach((tone) => el.classList.remove(`gd-badge--${tone}`));
      el.hidden = !badge;
      el.textContent = badge ? badge.text : '';
      if (badge) el.classList.add(`gd-badge--${badge.tone}`);
      card.classList.toggle('gd-card--alert', badge?.tone === 'alert');
    });
  };

  const applyStats = (resumen) => {
    document.querySelectorAll('[data-stat]').forEach((el) => {
      const key = el.dataset.stat;
      if (!(key in resumen) || resumen[key] === null) return;
      if (key === 'caja_abierta') {
        el.textContent = resumen[key] ? 'Caja abierta' : 'Caja cerrada';
        document.querySelector('[data-stat-dot="caja_abierta"]')?.classList.toggle('is-on', Boolean(resumen[key]));
        return;
      }
      el.textContent = String(resumen[key]);
    });
  };

  const refresh = async () => {
    if (!dashboardVisible()) return;
    try {
      const response = await fetch('/api/gastronomia/dashboard/resumen', {cache: 'no-store'});
      if (!response.ok) return;
      const data = await response.json();
      if (data.ok !== true) return;
      applyBadges(data.badges || {});
      applyStats(data.resumen || {});
    } catch (error) {
      // Sin señal: se reintenta en el proximo ciclo.
    }
  };

  window.initGastroDashboardLive = function () {
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, INTERVAL_MS);
  };

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refresh();
  });
})();
