(function () {
  // Piezas visuales de "Cuanto ganamos". Solo arman HTML; reportes_ganancia.js las carga.
  const money = (value) => `Gs. ${Math.round(Number(value || 0)).toLocaleString('es-PY')}`;
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
  const pct = (part, total) => (total > 0 ? (part / total) * 100 : 0);
  const clamp = (value) => Math.max(0, Math.min(100, value));
  // "De cada Gs. 10.000": mas facil de imaginar que un porcentaje.
  const deCada10mil = (part, total) => money(Math.round(pct(part, total)) * 100);
  const dayLabel = (iso, opts = {weekday: 'short', day: '2-digit', month: '2-digit'}) => {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('es-PY', opts);
  };
  const card = 'rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800';
  const muted = 'text-gray-500 dark:text-gray-400';

  const hero = (data) => {
    const t = data.totales || {};
    const periodo = data.periodo || {};
    const largo = {weekday: 'long', day: 'numeric', month: 'long'};
    const corto = {day: 'numeric', month: 'long'};
    const rango = periodo.desde === periodo.hasta
      ? dayLabel(periodo.desde, largo)
      : `Del ${dayLabel(periodo.desde, corto)} al ${dayLabel(periodo.hasta, corto)}`;
    const titulo = rango.charAt(0).toUpperCase() + rango.slice(1);
    if (!(t.ventas > 0)) {
      return `<div class="${card} text-center">
        <p class="text-sm font-semibold ${muted}">${escapeHtml(titulo)}</p>
        <p class="mt-2 text-xl font-black text-gray-900 dark:text-white">Todavía no hay ventas cobradas en este período.</p>
      </div>`;
    }
    const gano = t.ganancia_neta >= 0;
    const tono = gano
      ? 'border-emerald-200 bg-emerald-50 dark:border-gray-700 dark:bg-emerald-500/10'
      : 'border-rose-200 bg-rose-50 dark:border-gray-700 dark:bg-rose-500/10';
    const color = gano ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300';
    const frase = gano
      ? `De cada <strong>Gs. 10.000</strong> que vendiste, te quedaron <strong>${deCada10mil(t.ganancia_neta, t.ventas)}</strong> limpios.`
      : 'Los gastos fueron más grandes que lo que dejaron las ventas. Mirá abajo en qué se fue la plata.';
    const ticket = t.pedidos > 0 ? t.ventas / t.pedidos : 0;
    return `<div class="rounded-2xl border p-5 text-center ${tono}">
      <p class="text-sm font-semibold ${muted}">${escapeHtml(titulo)}</p>
      <p class="mt-1 text-base font-bold text-gray-700 dark:text-gray-200">
        <i class="fas ${gano ? 'fa-arrow-trend-up' : 'fa-arrow-trend-down'} mr-1 ${color}"></i>${gano ? 'Ganaste' : 'Perdiste'}
      </p>
      <p class="text-4xl font-black tracking-tight ${color}">${money(Math.abs(t.ganancia_neta))}</p>
      <p class="mx-auto mt-2 max-w-xl text-sm text-gray-700 dark:text-gray-200">${frase}</p>
      <p class="mt-2 text-xs font-semibold ${muted}">${t.pedidos} pedido(s) cobrados · ticket promedio ${money(ticket)}</p>
    </div>`;
  };

  // Cascada: cada resta arranca donde termino el renglon anterior.
  const steps = (t) => {
    const ventas = Number(t.ventas || 0);
    const local = Number(t.gastos_caja || 0) + Number(t.gastos_fijos || 0);
    const rows = [
      {label: 'Vendiste', help: 'Lo cobrado en el período', monto: ventas, tipo: 'total', desde: 0},
      {label: 'Ingredientes', help: 'Lo que costó preparar lo que vendiste (según las recetas)', monto: t.costo, tipo: 'resta', desde: t.ganancia_bruta},
      {label: 'Te queda después de cocinar', help: 'Ventas menos ingredientes', monto: t.ganancia_bruta, tipo: 'subtotal', desde: 0},
      {label: 'Gastos del local', help: 'Gas, luz, alquiler, delivery y otros pagos', monto: local, tipo: 'resta', desde: t.ganancia_bruta - local},
      {label: 'Sueldos', help: Number(t.sueldos) > 0 ? 'Pagos al personal' : 'No hay sueldos cargados en el período', monto: t.sueldos, tipo: 'resta', desde: t.ganancia_neta},
      {label: 'Ganancia limpia', help: 'Lo que realmente queda', monto: t.ganancia_neta, tipo: 'final', desde: 0},
    ];
    const barColor = {total: 'bg-slate-500', resta: 'bg-rose-400', subtotal: 'bg-emerald-400', final: 'bg-emerald-600'};
    const body = rows.map((row) => {
      const monto = Number(row.monto || 0);
      const esResta = row.tipo === 'resta';
      const negativo = !esResta && monto < 0;
      const left = clamp(pct(Math.max(0, row.desde), ventas));
      const width = Math.min(clamp(pct(Math.abs(monto), ventas)), 100 - left);
      const fuerte = row.tipo === 'subtotal' || row.tipo === 'final';
      return `<li class="${fuerte ? 'border-t border-dashed border-gray-300 pt-3 dark:border-gray-600' : ''}">
        <div class="flex items-baseline justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm ${fuerte ? 'font-black' : 'font-bold'} text-gray-900 dark:text-white">${fuerte ? '= ' : esResta ? '− ' : ''}${row.label}</p>
            <p class="text-xs ${muted}">${row.help}</p>
          </div>
          <p class="shrink-0 text-right text-sm font-black ${negativo ? 'text-rose-700 dark:text-rose-300' : 'text-gray-900 dark:text-white'}">
            ${esResta && monto > 0 ? '− ' : negativo ? '− ' : ''}${money(Math.abs(monto))}
            <span class="block text-xs font-semibold ${muted}">${ventas > 0 ? `${Math.round(pct(Math.abs(monto), ventas))}% de lo vendido` : ''}</span>
          </p>
        </div>
        <div class="relative mt-1.5 h-2.5 rounded-full bg-gray-100 dark:bg-gray-700/60">
          <div class="absolute inset-y-0 rounded-full ${negativo ? 'bg-rose-600' : barColor[row.tipo]}" style="left:${left}%;width:${width}%"></div>
        </div>
      </li>`;
    }).join('');
    return `<div class="${card}">
      <h3 class="text-base font-black text-gray-900 dark:text-white">Cómo se llega a ese número</h3>
      <ol class="mt-3 space-y-3">${body}</ol>
    </div>`;
  };

  const semaforo = (valor, bien, atencion) => {
    if (valor <= bien) return {txt: 'Bien', icon: 'fa-circle-check', cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200'};
    if (valor <= atencion) return {txt: 'Atención', icon: 'fa-triangle-exclamation', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200'};
    return {txt: 'Alto', icon: 'fa-circle-exclamation', cls: 'bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-200'};
  };

  const medidor = (titulo, exacto, bien, atencion, explicacion) => {
    // Se compara el mismo numero que se muestra: 35,2% no puede decir "35%" y "Atencion".
    const valor = Math.round(exacto);
    const estado = semaforo(valor, bien, atencion);
    const escala = 80;
    return `<div>
      <div class="flex items-center justify-between gap-2">
        <p class="text-sm font-bold text-gray-900 dark:text-white">${titulo}</p>
        <span class="rounded-full px-2.5 py-0.5 text-xs font-black ${estado.cls}"><i class="fas ${estado.icon} mr-1"></i>${estado.txt}</span>
      </div>
      <p class="mt-1 text-3xl font-black text-gray-900 dark:text-white">${valor}%</p>
      <div class="relative mt-2 flex h-2.5 gap-1 overflow-hidden rounded-full">
        <div class="bg-emerald-400" style="width:${bien / escala * 100}%"></div>
        <div class="bg-amber-500" style="width:${(atencion - bien) / escala * 100}%"></div>
        <div class="flex-1 bg-rose-400"></div>
      </div>
      <div class="relative h-3">
        <span class="absolute -top-1 -translate-x-1/2 text-xs leading-none text-gray-900 dark:text-white" style="left:${clamp(valor / escala * 100)}%">▲</span>
      </div>
      <p class="text-xs ${muted}">${explicacion}</p>
    </div>`;
  };

  const salud = (t) => {
    if (!(t.ventas > 0)) return '';
    if (!(t.costo > 0)) {
      return `<div class="${card}">
        <h3 class="text-base font-black text-gray-900 dark:text-white">Salud del negocio</h3>
        <p class="mt-2 text-sm ${muted}">Para ver si los precios están bien, cargá el costo de los ingredientes en Menú &gt; Stock &gt; Recetas.</p>
      </div>`;
    }
    const comida = pct(t.costo, t.ventas);
    const primo = pct(Number(t.costo) + Number(t.sueldos || 0), t.ventas);
    const partes = [medidor(
      'Ingredientes sobre ventas', comida, 35, 40,
      `De cada Gs. 10.000 vendidos, ${deCada10mil(t.costo, t.ventas)} se van en ingredientes. Lo sano en gastronomía es hasta 35%.`,
    )];
    if (Number(t.sueldos) > 0) {
      partes.push(medidor(
        'Ingredientes + sueldos', primo, 60, 65,
        'Es el costo principal de un restaurante. Si pasa de 65%, casi no queda para alquiler, luz y ganancia.',
      ));
    }
    return `<div class="${card}">
      <h3 class="text-base font-black text-gray-900 dark:text-white">Salud del negocio</h3>
      <div class="mt-3 space-y-5">${partes.join('')}</div>
    </div>`;
  };

  const gastos = (detalle) => {
    const tipos = {caja: 'Caja', fijo: 'Fijo', sueldo: 'Sueldo'};
    const visibles = detalle.slice(0, 7);
    const resto = detalle.slice(7).reduce((acc, item) => acc + Number(item.monto || 0), 0);
    if (resto > 0) visibles.push({concepto: 'Otros gastos', tipo: '', monto: resto, veces: detalle.length - 7});
    const max = Math.max(...visibles.map((item) => Number(item.monto || 0)), 1);
    const body = visibles.map((item) => `<li>
        <div class="flex items-baseline justify-between gap-3 text-sm">
          <span class="min-w-0 truncate font-semibold text-gray-900 dark:text-white" title="${escapeHtml(item.concepto)}">${escapeHtml(item.concepto)}
            ${tipos[item.tipo] ? `<span class="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold uppercase ${muted} dark:bg-gray-700">${tipos[item.tipo]}</span>` : ''}
          </span>
          <span class="shrink-0 font-black text-gray-900 dark:text-white">${money(item.monto)}</span>
        </div>
        <div class="mt-1 h-2 rounded-full bg-gray-100 dark:bg-gray-700/60">
          <div class="h-2 rounded-full bg-rose-400" style="width:${pct(item.monto, max)}%"></div>
        </div>
      </li>`).join('');
    return `<div class="${card}">
      <h3 class="text-base font-black text-gray-900 dark:text-white">¿En qué se fue la plata?</h3>
      <p class="text-xs ${muted}">Gastos pagados en el período, sin contar ingredientes.</p>
      ${body ? `<ul class="mt-3 space-y-3">${body}</ul>` : `<p class="mt-3 text-sm ${muted}">No se registraron gastos en este período.</p>`}
    </div>`;
  };

  window.GananciaUI = {money, escapeHtml, pct, dayLabel, deCada10mil, card, muted, hero, steps, salud, gastos};
}());
