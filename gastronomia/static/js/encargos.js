// Tablero de encargos: encargos por dia de retiro, totales a producir y acciones.
(() => {
  const ui = window.EncargosUI;
  const root = document.querySelector('[data-gastro-encargos]');
  const filtros = document.getElementById('encargos-filtros');
  const diasEl = document.getElementById('encargos-dias');
  const vencidosEl = document.getElementById('encargos-vencidos');
  const alertEl = document.getElementById('encargos-alert');
  if (!ui || !root || !filtros || !diasEl || !vencidosEl || !alertEl) return;

  const puedeCobrar = root.dataset.puedeCobrar === '1';
  const cajaUrl = root.dataset.cajaUrl || '/gastronomia/caja';
  let encargosPorId = new Map();

  const ESTADOS = {
    abierto: ['Tomado', 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200'],
    enviado_cocina: ['En produccion', 'bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200'],
    preparando: ['Preparando', 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200'],
    listo: ['Listo para retirar', 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200'],
    entregado: ['Entregado sin cobrar', 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200'],
  };

  const showAlert = (message, ok = true) => {
    if (!message) {
      alertEl.className = 'hidden rounded-lg border px-4 py-3 text-sm font-semibold';
      return;
    }
    alertEl.textContent = message;
    alertEl.className = `rounded-lg border px-4 py-3 text-sm font-semibold ${ok
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200'
      : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100'}`;
  };

  const boton = (action, id, label, clase) => `
    <button type="button" data-action="${action}" data-id="${id}" class="rounded-lg px-3 py-2 text-xs font-bold ${clase}">${label}</button>`;

  const acciones = (e) => {
    const id = e.id_pedido;
    const items = [];
    if (e.estado === 'abierto') {
      items.push(boton('produccion', id, 'Enviar a produccion', 'bg-sky-600 text-white hover:bg-sky-700'));
      items.push(boton('editar', id, 'Editar', 'border border-gray-200 dark:border-gray-600'));
    }
    if (['abierto', 'enviado_cocina', 'preparando', 'listo'].includes(e.estado)) {
      items.push(boton('sena', id, 'Cobrar seña', 'border border-emerald-300 text-emerald-700 dark:text-emerald-300'));
    }
    if (puedeCobrar && ['listo', 'entregado'].includes(e.estado)) {
      items.push(`<a href="${cajaUrl}?pedido=${id}" class="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-700">Cobrar saldo en caja</a>`);
    }
    items.push(boton('cancelar', id, 'Cancelar', 'text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-500/10'));
    return items.join('');
  };

  const ajustable = (e, item) => item.peso_kg && ['abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado'].includes(e.estado);
  const itemsHtml = (e) => (e.items || []).map((item) => `
    <li>
      ${ajustable(e, item) ? `<button type="button" data-action="peso" data-id="${e.id_pedido}" data-item="${item.id_item}" class="float-right rounded-lg border border-violet-300 px-2 py-1 text-xs font-bold text-violet-700 dark:text-violet-300">Ajustar peso</button>` : ''}
      <span class="font-bold">${Number(item.cantidad || 0)} x ${ui.escapeHtml(item.nombre_producto)}</span>
      ${(item.modificadores || []).length ? `<span class="text-gray-500"> (${item.modificadores.map((m) => ui.escapeHtml(m.nombre_opcion)).join(', ')})</span>` : ''}
      ${item.texto_personalizado ? `<span class="ml-1 rounded bg-violet-100 px-1.5 py-0.5 text-xs font-bold text-violet-800 dark:bg-violet-500/20 dark:text-violet-200">"${ui.escapeHtml(item.texto_personalizado)}"</span>` : ''}
      ${item.notas ? `<div class="text-xs text-gray-500 dark:text-gray-400">${ui.escapeHtml(item.notas)}</div>` : ''}
    </li>`).join('');

  const fotosHtml = (e) => (e.fotos || []).map((foto) => {
    const url = ui.safePhotoUrl(foto.url);
    return url ? `<a href="${ui.escapeHtml(url)}" target="_blank" rel="noopener" class="block h-14 w-14 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
      <img src="${ui.escapeHtml(url)}" alt="Foto de referencia" loading="lazy" class="h-full w-full object-cover"></a>` : '';
  }).join('');

  const tarjeta = (e, {vencido = false} = {}) => {
    const [estadoLabel, estadoClase] = ESTADOS[e.estado] || [e.estado, ESTADOS.abierto[1]];
    return `
      <article class="rounded-xl border ${vencido ? 'border-rose-300 dark:border-rose-500/40' : 'border-gray-200 dark:border-gray-700'} bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p class="text-lg font-black text-gray-900 dark:text-white">${vencido ? `${ui.escapeHtml(String(e.fecha_programada || '').slice(0, 10))} ` : ''}${ui.hora(e.fecha_programada)} · ${ui.escapeHtml(e.nombre_cliente || '')}</p>
            <p class="text-xs font-semibold text-gray-500">${ui.escapeHtml(e.codigo_entrega)}${e.celular_cliente ? ` · ${ui.escapeHtml(e.celular_cliente)}` : ''}</p>
          </div>
          <span class="rounded-full px-2.5 py-1 text-xs font-bold ${estadoClase}">${estadoLabel}</span>
        </div>
        <ul class="mt-3 space-y-1 text-sm text-gray-800 dark:text-gray-100">${itemsHtml(e)}</ul>
        ${e.notas ? `<p class="mt-2 rounded-lg bg-amber-50 p-2 text-xs font-semibold text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">${ui.escapeHtml(e.notas)}</p>` : ''}
        ${(e.fotos || []).length ? `<div class="mt-3 flex flex-wrap gap-2">${fotosHtml(e)}</div>` : ''}
        <div class="mt-3 flex flex-wrap gap-3 text-sm">
          <span>Total <strong>${ui.money(e.total)}</strong></span>
          <span>Seña <strong>${ui.money(e.sena_vigente)}</strong></span>
          <span>Saldo <strong class="text-violet-700 dark:text-violet-300">${ui.money(e.saldo)}</strong></span>
        </div>
        <div class="mt-3 flex flex-wrap gap-2">${acciones(e)}</div>
      </article>`;
  };

  const produccionHtml = (produccion) => (produccion || []).map((p) => `
    <span class="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-bold text-violet-800 dark:bg-violet-500/15 dark:text-violet-200">${Number(p.cantidad)} ${ui.escapeHtml(p.producto)}</span>`).join('');

  const render = (data) => {
    const todos = [...(data.vencidos || []), ...(data.dias || []).flatMap((dia) => dia.encargos || [])];
    encargosPorId = new Map(todos.map((e) => [Number(e.id_pedido), e]));

    const vencidos = data.vencidos || [];
    vencidosEl.classList.toggle('hidden', !vencidos.length);
    vencidosEl.innerHTML = vencidos.length ? `
      <h2 class="mb-2 text-base font-black text-rose-700 dark:text-rose-300"><i class="fas fa-triangle-exclamation mr-1"></i>Pendientes de dias anteriores (${vencidos.length})</h2>
      <div class="grid gap-3 lg:grid-cols-2">${vencidos.map((e) => tarjeta(e, {vencido: true})).join('')}</div>` : '';

    diasEl.innerHTML = (data.dias || []).map((dia) => `
      <section class="rounded-xl border ${dia.fecha === data.hoy ? 'border-violet-300 dark:border-violet-500/40' : 'border-gray-200 dark:border-gray-700'} bg-gray-50 p-3 dark:bg-gray-900/40">
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-black text-gray-900 dark:text-white">${dia.fecha === data.hoy ? 'Hoy · ' : ''}${ui.escapeHtml(ui.diaLegible(dia.fecha))}
            <span class="ml-1 text-sm font-semibold text-gray-500">${dia.cantidad} encargo(s)</span></h2>
          <div class="flex flex-wrap gap-1">${produccionHtml(dia.produccion)}</div>
        </div>
        ${dia.encargos.length
          ? `<div class="grid gap-3 lg:grid-cols-2">${dia.encargos.map((e) => tarjeta(e)).join('')}</div>`
          : '<p class="text-sm text-gray-500">Sin encargos.</p>'}
      </section>`).join('');
  };

  const load = async () => {
    const params = new URLSearchParams({desde: filtros.desde.value, dias: filtros.dias.value});
    try {
      render(await ui.apiJson(`/api/gastronomia/encargos?${params.toString()}`));
    } catch (error) {
      showAlert(error.message, false);
    }
  };

  const recargar = (message, ok = true) => {
    if (message) showAlert(message, ok);
    load();
  };

  diasEl.parentElement.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const encargo = encargosPorId.get(Number(button.dataset.id));
    if (!encargo) return;
    const action = button.dataset.action;
    if (action === 'editar') window.EncargoForm.open(encargo, recargar);
    if (action === 'sena') window.EncargoAcciones.openSena(encargo, recargar);
    if (action === 'cancelar') window.EncargoAcciones.openCancel(encargo, recargar);
    if (action === 'peso') {
      const item = (encargo.items || []).find((i) => String(i.id_item) === button.dataset.item);
      if (item) window.EncargoAcciones.openPeso(encargo, item, recargar);
    }
    if (action === 'produccion') {
      button.disabled = true;
      try {
        await ui.apiJson(`/api/gastronomia/encargos/${encargo.id_pedido}/produccion`, {method: 'POST', body: '{}'});
        recargar('Encargo enviado a produccion: ya aparece en cocina.');
      } catch (error) {
        button.disabled = false;
        showAlert(error.message, false);
      }
    }
  });

  const moverDesde = (dias) => {
    const [y, m, d] = filtros.desde.value.split('-').map(Number);
    const fecha = new Date(y, m - 1, d);
    fecha.setDate(fecha.getDate() + dias);
    filtros.desde.value = ui.isoDia(fecha);
    load();
  };
  filtros.querySelectorAll('[data-shift]').forEach((button) => {
    button.addEventListener('click', () => moverDesde(Number(button.dataset.shift) * Number(filtros.dias.value || 7)));
  });
  filtros.querySelector('[data-hoy]').addEventListener('click', () => { filtros.desde.value = ui.isoDia(new Date()); load(); });
  filtros.addEventListener('change', load);
  document.getElementById('encargo-nuevo')?.addEventListener('click', () => window.EncargoForm.open(null, recargar));

  filtros.desde.value = ui.isoDia(new Date());
  load();
})();
