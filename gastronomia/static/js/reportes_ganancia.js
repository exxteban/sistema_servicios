(function () {
  // Seccion "Cuanto ganamos" de reportes. Usa el mismo rango Desde/Hasta que reportes.js.
  const section = document.querySelector('[data-report-profit]');
  const ui = window.GananciaUI;
  if (!section || !ui) return;

  const {money, escapeHtml, pct, dayLabel, card, muted} = ui;
  const fromInput = document.getElementById('report-from');
  const toInput = document.getElementById('report-to');
  const el = (id) => document.getElementById(id);

  const isoLocal = (date) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  };

  const avisos = (data) => {
    const t = data.totales || {};
    const notes = [];
    const sinCosto = data.platos_sin_costo || [];
    if (sinCosto.length) {
      const parte = Math.round(pct(t.unidades_sin_costo, t.unidades));
      const nombres = sinCosto.slice(0, 5).map((item) => escapeHtml(item.nombre)).join(', ');
      notes.push(['amber', 'fa-triangle-exclamation',
        `<strong>${parte}% de lo vendido no tiene costo cargado</strong> (${nombres}${sinCosto.length > 5 ? '…' : ''}), así que la ganancia real es menor a la que ves. Cargalo en Menú &gt; Stock &gt; Recetas.`]);
    }
    const mercaderia = Number(data.compras || 0) + Number(t.insumos_caja || 0);
    if (mercaderia > 0) {
      const desglose = t.insumos_caja > 0 && data.compras > 0
        ? ` (${money(data.compras)} en compras y ${money(t.insumos_caja)} pagados de la caja)` : '';
      notes.push(['gray', 'fa-basket-shopping',
        `Compraste <strong>${money(mercaderia)}</strong> de mercadería${desglose} y, según las recetas, usaste <strong>${money(t.costo)}</strong>. Es solo para comparar: no se resta de la ganancia. Si durante varias semanas comprás mucho más de lo que usás, hay desperdicio o recetas mal cargadas.`]);
    }
    const styles = {
      amber: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-gray-700 dark:bg-amber-500/10 dark:text-amber-100',
      gray: 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300',
    };
    return notes.map(([kind, icon, text]) => `<p class="flex gap-2 rounded-lg border px-3 py-2 text-sm ${styles[kind]}">
      <i class="fas ${icon} mt-0.5"></i><span>${text}</span></p>`).join('');
  };

  // Barras arriba (gano) / abajo (perdio) de una linea en cero.
  const dias = (days) => {
    if (days.length < 2) return '';
    const max = Math.max(...days.map((day) => Math.abs(Number(day.ganancia_neta || 0))), 1);
    const hayPerdidas = days.some((day) => day.ganancia_neta < 0);
    const alto = 72;
    const bars = days.map((day) => {
      const valor = Number(day.ganancia_neta || 0);
      const h = Math.max(valor === 0 ? 0 : 2, Math.round(Math.abs(valor) / max * alto));
      const tip = `${dayLabel(day.fecha)} · ${valor < 0 ? 'Pérdida' : 'Ganancia'} ${money(Math.abs(valor))} · Vendiste ${money(day.ventas)}`;
      return `<div class="relative flex flex-1 flex-col items-center hover:opacity-80" style="min-width:10px" title="${escapeHtml(tip)}">
        <div class="flex w-full items-end justify-center" style="height:${alto}px">
          ${valor > 0 ? `<div class="w-full rounded-t bg-emerald-500" style="max-width:28px;height:${h}px"></div>` : ''}
        </div>
        <div class="w-full border-t border-gray-300 dark:border-gray-600"></div>
        ${hayPerdidas ? `<div class="flex w-full items-start justify-center" style="height:${alto}px">
          ${valor < 0 ? `<div class="w-full rounded bg-rose-500" style="max-width:28px;height:${h}px"></div>` : ''}
        </div>` : ''}
        ${days.length <= 31 ? `<span class="mt-1 text-[10px] font-semibold ${muted}">${Number(day.fecha.slice(8))}</span>` : ''}
      </div>`;
    }).join('');
    const filas = days.slice().reverse().map((day) => `<tr class="border-t border-gray-100 dark:border-gray-700">
        <td class="px-2 py-1.5 font-semibold capitalize text-gray-900 dark:text-white">${escapeHtml(dayLabel(day.fecha))}</td>
        <td class="px-2 py-1.5 text-right">${money(day.ventas)}</td>
        <td class="px-2 py-1.5 text-right ${muted}">${money(day.costo)}</td>
        <td class="px-2 py-1.5 text-right ${muted}">${money(day.gastos)}</td>
        <td class="px-2 py-1.5 text-right font-bold ${day.ganancia_neta < 0 ? 'text-rose-700 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'}">${day.ganancia_neta < 0 ? '− ' : ''}${money(Math.abs(day.ganancia_neta))}</td>
      </tr>`).join('');
    return `<div class="${card}">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h3 class="text-base font-black text-gray-900 dark:text-white">Día a día</h3>
        <p class="text-xs ${muted}"><span class="mr-1 inline-block h-2 w-2 rounded-sm bg-emerald-500"></span>Ganaste
          <span class="ml-3 mr-1 inline-block h-2 w-2 rounded-sm bg-rose-500"></span>Perdiste</p>
      </div>
      <div class="mt-3 flex gap-1 overflow-x-auto pb-1">${bars}</div>
      <p class="mt-2 text-xs ${muted}">Los días que pagás alquiler o sueldos pueden salir en rojo aunque vendas bien: mirá la semana o el mes completo.</p>
      <details class="mt-2">
        <summary class="cursor-pointer text-xs font-bold text-violet-700 dark:text-violet-300">Ver los números de cada día</summary>
        <div class="mt-2 overflow-x-auto"><table class="min-w-full text-sm">
          <thead><tr class="text-xs uppercase ${muted}"><th class="px-2 py-1 text-left">Día</th><th class="px-2 py-1 text-right">Vendiste</th><th class="px-2 py-1 text-right">Ingredientes</th><th class="px-2 py-1 text-right">Gastos</th><th class="px-2 py-1 text-right">Resultado</th></tr></thead>
          <tbody>${filas}</tbody>
        </table></div>
      </details>
    </div>`;
  };

  const listaPlatos = (titulo, ayuda, items, icon) => {
    const body = items.map((item) => `<li class="flex items-baseline justify-between gap-3 py-2">
        <div class="min-w-0">
          <p class="truncate text-sm font-bold text-gray-900 dark:text-white">${escapeHtml(item.nombre)}</p>
          <p class="text-xs ${muted}">Vendiste ${item.cantidad} · te deja ${money(item.ganancia / Math.max(item.cantidad, 1))} c/u</p>
        </div>
        <p class="shrink-0 text-right text-sm font-black ${item.ganancia < 0 ? 'text-rose-700 dark:text-rose-300' : 'text-gray-900 dark:text-white'}">${money(item.ganancia)}
          <span class="block text-xs font-semibold ${muted}">${item.ganancia_pct}% de margen</span></p>
      </li>`).join('');
    return `<div class="${card}">
      <h3 class="text-base font-black text-gray-900 dark:text-white"><i class="fas ${icon} mr-1 ${muted}"></i>${titulo}</h3>
      <p class="text-xs ${muted}">${ayuda}</p>
      ${body ? `<ul class="mt-2 divide-y divide-gray-100 dark:divide-gray-700">${body}</ul>` : `<p class="mt-3 text-sm ${muted}">Sin platos con costo cargado en el período.</p>`}
    </div>`;
  };

  const platos = (dishes) => {
    const conCosto = dishes.filter((item) => item.costo_unitario > 0);
    const mejores = conCosto.slice(0, 5);
    const peores = conCosto.slice().sort((a, b) => a.ganancia_pct - b.ganancia_pct).slice(0, 5);
    return listaPlatos('Los que más plata te dejan', 'Ganancia total del período, después de ingredientes.', mejores, 'fa-trophy')
      + listaPlatos('Los que menos te dejan por venta', 'Margen más bajo. Revisá el precio o la receta.', peores, 'fa-magnifying-glass-dollar');
  };

  const render = (data) => {
    const t = data.totales || {};
    el('profit-hero').innerHTML = ui.hero(data);
    el('profit-warnings').innerHTML = avisos(data);
    const conVentas = t.ventas > 0;
    el('profit-tabs').classList.toggle('hidden', !conVentas);
    if (!conVentas) {
      el('profit-days').innerHTML = '';
      return;
    }
    el('profit-steps').innerHTML = ui.steps(t);
    el('profit-health').innerHTML = ui.salud(t);
    el('profit-expenses').innerHTML = ui.gastos(data.gastos_detalle || []);
    el('profit-days').innerHTML = dias(data.dias || []);
    el('profit-dishes').innerHTML = platos(data.platos || []);
  };

  const load = async () => {
    const params = new URLSearchParams({desde: fromInput.value, hasta: toInput.value});
    const response = await fetch(`/api/gastronomia/reportes/ganancia?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo calcular la ganancia.');
    render(data.ganancia || {});
  };
  const loadSafe = () => load().catch((error) => {
    el('profit-warnings').innerHTML = `<p class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">${escapeHtml(error.message)}</p>`;
  });

  const ACTIVO = ['border-violet-300', 'bg-violet-50', 'text-violet-700', 'dark:bg-violet-500/15', 'dark:text-violet-200'];
  // Pestañas de la seccion: cada una muestra un grupo de datos para no hacer scroll largo.
  const TAB_ACTIVA = ['bg-violet-600', 'text-white', 'shadow-sm'];
  const TAB_INACTIVA = ['text-gray-600', 'dark:text-gray-300'];
  const mostrarTab = (nombre) => {
    section.querySelectorAll('[data-profit-tab]').forEach((tab) => {
      const activa = tab.dataset.profitTab === nombre;
      tab.setAttribute('aria-selected', String(activa));
      TAB_ACTIVA.forEach((cls) => tab.classList.toggle(cls, activa));
      TAB_INACTIVA.forEach((cls) => tab.classList.toggle(cls, !activa));
    });
    section.querySelectorAll('[data-profit-panel]').forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.profitPanel !== nombre);
    });
  };
  mostrarTab('resumen');
  const marcarRango = (button) => section.querySelectorAll('[data-profit-range]').forEach((btn) => {
    const activo = btn === button;
    btn.setAttribute('aria-pressed', String(activo));
    ACTIVO.forEach((cls) => btn.classList.toggle(cls, activo));
  });
  const shell = section.closest('[data-gastro-reportes]');
  const rangoInicial = shell?.dataset.inicioRango || (shell?.dataset.inicioDesde ? '' : 'hoy');
  marcarRango(rangoInicial ? section.querySelector(`[data-profit-range="${rangoInicial}"]`) : null);
  // Si cambian las fechas a mano, ningun atajo queda marcado.
  [fromInput, toInput].forEach((input) => input.addEventListener('change', () => marcarRango(null)));

  section.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-profit-tab]');
    if (tab) {
      mostrarTab(tab.dataset.profitTab);
      return;
    }
    const button = event.target.closest('[data-profit-range]');
    if (!button) return;
    const today = new Date();
    const from = new Date(today);
    if (button.dataset.profitRange === '7') from.setDate(today.getDate() - 6);
    if (button.dataset.profitRange === 'mes') from.setDate(1);
    fromInput.value = isoLocal(from);
    toInput.value = isoLocal(today);
    marcarRango(button);
    // Recarga todo el reporte (reportes.js) y esta seccion con el mismo rango.
    el('load-report')?.click();
  });
  el('load-report')?.addEventListener('click', loadSafe);
  loadSafe().then(() => {
    if (shell?.dataset.inicioVer === 'ganancia') section.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
}());
