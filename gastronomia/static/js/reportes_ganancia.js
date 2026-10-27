(function () {
  // Seccion "Cuanto ganamos" de reportes. Usa el mismo rango Desde/Hasta que reportes.js.
  const section = document.querySelector('[data-report-profit]');
  if (!section) return;

  const fromInput = document.getElementById('report-from');
  const toInput = document.getElementById('report-to');
  const kpis = document.getElementById('profit-kpis');
  const warnings = document.getElementById('profit-warnings');
  const daysTable = document.getElementById('profit-days');
  const dishesTable = document.getElementById('profit-dishes');

  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const isoLocal = (date) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  };
  const dayLabel = (iso) => {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('es-PY', {weekday: 'short', day: '2-digit', month: '2-digit'});
  };
  const tone = (value) => (Number(value) < 0 ? 'text-red-600 dark:text-red-300' : 'text-emerald-700 dark:text-emerald-300');
  const th = (label, right = true) => `<th class="px-2 py-2 text-xs font-bold uppercase text-gray-500 ${right ? 'text-right' : 'text-left'}">${label}</th>`;
  const td = (value, extra = '') => `<td class="px-2 py-2 text-right font-semibold ${extra}">${value}</td>`;
  const empty = (cols, text) => `<tr><td colspan="${cols}" class="px-2 py-4 text-center text-sm text-gray-500">${text}</td></tr>`;

  const renderKpis = (t) => {
    const cards = [
      ['Ventas', money(t.ventas), `${t.pedidos} pedido(s)`, 'text-gray-900 dark:text-white'],
      ['Costo de lo vendido', money(t.costo), `${t.costo_pct}% de las ventas`, 'text-gray-900 dark:text-white'],
      ['Ganancia bruta', money(t.ganancia_bruta), `${t.margen_pct}% de margen`, tone(t.ganancia_bruta)],
      ['Gastos pagados', money(t.gastos), 'Caja y gastos fijos', 'text-gray-900 dark:text-white'],
      ['Ganancia neta', money(t.ganancia_neta), 'Lo que queda', tone(t.ganancia_neta)],
    ];
    kpis.innerHTML = cards.map(([title, value, note, color]) => `
      <article class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
        <p class="text-xs font-bold uppercase tracking-wide text-gray-500">${title}</p>
        <p class="mt-1 text-xl font-black ${color}">${value}</p>
        <p class="text-xs font-semibold text-gray-500">${note}</p>
      </article>
    `).join('');
  };

  const renderWarnings = (data) => {
    const notes = [];
    const sinCosto = data.platos_sin_costo || [];
    if (sinCosto.length) {
      const nombres = sinCosto.slice(0, 6).map((item) => `${escapeHtml(item.nombre)} (${item.cantidad})`).join(', ');
      notes.push(['amber', `Se vendieron platos sin costo cargado, asi que la ganancia real es menor: ${nombres}. Cargales el costo en Menu &gt; Stock &gt; Recetas.`]);
    }
    if (data.compras > 0) {
      notes.push(['gray', `Compras de mercaderia registradas en el periodo: <strong>${money(data.compras)}</strong> contra un costo estimado de <strong>${money(data.totales.costo)}</strong>. Si las compras son mucho mayores durante varias semanas, hay desperdicio o costos mal cargados.`]);
    }
    const styles = {
      amber: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-400/30 dark:bg-amber-500/10 dark:text-amber-200',
      gray: 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300',
    };
    warnings.innerHTML = notes.map(([kind, text]) => `<p class="rounded-lg border px-3 py-2 text-xs font-semibold ${styles[kind]}">${text}</p>`).join('');
  };

  const renderDays = (days) => {
    const rows = days.slice().reverse().map((day) => `
      <tr class="border-t border-gray-100 dark:border-gray-700">
        <td class="px-2 py-2 font-semibold capitalize text-gray-900 dark:text-white">${escapeHtml(dayLabel(day.fecha))}</td>
        ${td(money(day.ventas))}
        ${td(money(day.costo), 'text-gray-500')}
        ${td(money(day.gastos), 'text-gray-500')}
        ${td(money(day.ganancia_neta), tone(day.ganancia_neta))}
      </tr>
    `).join('');
    daysTable.innerHTML = `<thead><tr>${th('Dia', false)}${th('Ventas')}${th('Costo')}${th('Gastos')}${th('Ganancia')}</tr></thead>
      <tbody>${rows || empty(5, 'Sin datos en el periodo.')}</tbody>`;
  };

  const renderDishes = (dishes) => {
    const rows = dishes.slice(0, 15).map((item) => `
      <tr class="border-t border-gray-100 dark:border-gray-700">
        <td class="px-2 py-2 font-semibold text-gray-900 dark:text-white">${escapeHtml(item.nombre)}</td>
        ${td(item.cantidad)}
        ${td(money(item.ventas))}
        ${item.costo_unitario > 0
          ? td(`${money(item.ganancia)} <span class="text-xs text-gray-500">(${item.ganancia_pct}%)</span>`, tone(item.ganancia))
          : td('Sin costo', 'text-amber-600')}
      </tr>
    `).join('');
    dishesTable.innerHTML = `<thead><tr>${th('Plato', false)}${th('Cant.')}${th('Ventas')}${th('Ganancia')}</tr></thead>
      <tbody>${rows || empty(4, 'Sin ventas en el periodo.')}</tbody>`;
  };

  const load = async () => {
    const params = new URLSearchParams({desde: fromInput.value, hasta: toInput.value});
    const response = await fetch(`/api/gastronomia/reportes/ganancia?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo calcular la ganancia.');
    const profit = data.ganancia || {};
    renderKpis(profit.totales || {});
    renderWarnings(profit);
    renderDays(profit.dias || []);
    renderDishes(profit.platos || []);
  };
  const loadSafe = () => load().catch((error) => {
    warnings.innerHTML = `<p class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-800">${escapeHtml(error.message)}</p>`;
  });

  section.addEventListener('click', (event) => {
    const button = event.target.closest('[data-profit-range]');
    if (!button) return;
    const today = new Date();
    const from = new Date(today);
    if (button.dataset.profitRange === '7') from.setDate(today.getDate() - 6);
    if (button.dataset.profitRange === 'mes') from.setDate(1);
    fromInput.value = isoLocal(from);
    toInput.value = isoLocal(today);
    // Recarga todo el reporte (reportes.js) y esta seccion con el mismo rango.
    document.getElementById('load-report')?.click();
  });
  document.getElementById('load-report')?.addEventListener('click', loadSafe);
  loadSafe();
}());
