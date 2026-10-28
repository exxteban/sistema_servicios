/* Dibujo de la vista previa de importacion de ventas (sin estado propio). */
(function () {
  const fmt = new Intl.NumberFormat('es-PY', {maximumFractionDigits: 0});
  const dinero = (valor) => `Gs. ${fmt.format(Number(valor || 0))}`;
  const esc = (texto) => String(texto ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const fechaLegible = (iso) => (iso ? iso.split('-').reverse().join('/') : '');
  const input = 'rounded-lg border border-gray-200 px-2 py-1 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100';

  const TIPOS_HOJA = {
    ventas: ['Ventas por pedido', 'text-emerald-700 dark:text-emerald-300', 'se importa'],
    totales: ['Totales por dia', 'text-sky-700 dark:text-sky-300', 'se usa para verificar fechas y montos'],
    egresos: ['Egresos / gastos', 'text-gray-500', 'no se importa por ahora'],
    vacia: ['Vacia', 'text-gray-400', 'se ignora'],
    otra: ['No reconocida', 'text-gray-400', 'se ignora'],
  };

  function tarjeta(titulo, valor) {
    return `<div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <p class="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">${esc(titulo)}</p>
      <p class="mt-1 text-2xl font-black text-gray-900 dark:text-white">${esc(valor)}</p></div>`;
  }

  function resumen(totales) {
    return tarjeta('Dias a importar', totales.dias) + tarjeta('Ventas (pedidos)', fmt.format(totales.pedidos)) + tarjeta('Total', dinero(totales.total));
  }

  function hojas(lista) {
    const filas = lista.map((hoja) => {
      const [nombre, color, nota] = TIPOS_HOJA[hoja.tipo] || TIPOS_HOJA.otra;
      const columnas = hoja.columnas
        ? ` &middot; columnas: ${Object.entries(hoja.columnas).map(([rol, letra]) => `${esc(rol)}=${esc(letra)}`).join(', ')}`
        : '';
      return `<li><span class="font-semibold text-gray-900 dark:text-white">${esc(hoja.nombre)}</span>:
        <span class="font-semibold ${color}">${nombre}</span> (${nota})${columnas}</li>`;
    }).join('');
    return `<p class="mb-1 font-bold text-gray-900 dark:text-white">Hojas encontradas</p><ul class="list-disc space-y-1 pl-5">${filas}</ul>`;
  }

  const AVISO_REPETIDA = 'Hay otro bloque con la misma fecha: revisa que no sea el mismo dia cargado dos veces.';

  function estadoVisible(dia, decision, repetida) {
    if (dia.estado === 'sin_fecha') return decision.fecha ? 'revisar' : 'sin_fecha';
    return repetida ? 'revisar' : dia.estado;
  }

  function dias(lista, decisiones, fechasRepetidas) {
    return lista.map((dia) => {
      const decision = decisiones[dia.indice];
      const repetida = decision.incluir && fechasRepetidas.has(decision.fecha);
      const estado = estadoVisible(dia, decision, repetida);
      const colores = {
        ok: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200',
        revisar: 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200',
        sin_fecha: 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200',
      };
      const etiqueta = {ok: 'OK', revisar: 'Revisar', sin_fecha: 'Falta fecha'}[estado] || estado;
      const origen = dia.fecha_texto ? `escrito: "${esc(dia.fecha_texto)}"` : (dia.origen_fecha === 'totales' ? 'deducida de la hoja de totales' : '');
      const avisos = dia.avisos.concat(repetida ? [AVISO_REPETIDA] : []).map((aviso) => `<li>${esc(aviso)}</li>`).join('');
      const totalEscrito = dia.total_excel === null ? '-' : fmt.format(dia.total_excel);
      const fondo = estado === 'ok' ? '' : 'bg-amber-50/60 dark:bg-amber-500/5';
      return `<tr class="${decision.incluir ? fondo : 'opacity-50'}">
        <td class="px-2 py-2"><input type="checkbox" data-dia-incluir="${dia.indice}" ${decision.incluir ? 'checked' : ''} class="h-4 w-4"></td>
        <td class="px-2 py-2 whitespace-nowrap text-gray-600 dark:text-gray-300">${esc(dia.hoja)}<br><span class="text-xs">filas ${dia.fila_inicio}-${dia.fila_fin}</span></td>
        <td class="px-2 py-2"><input type="date" data-dia-fecha="${dia.indice}" value="${esc(decision.fecha || '')}" class="${input}">
          <div class="text-xs text-gray-500">${origen}</div></td>
        <td class="px-2 py-2 text-right">${dia.filas}</td>
        <td class="px-2 py-2 text-right font-semibold">${fmt.format(dia.suma)}</td>
        <td class="px-2 py-2 text-right">${totalEscrito}</td>
        <td class="min-w-[16rem] px-2 py-2"><span class="rounded-full px-2 py-0.5 text-xs font-bold ${colores[estado] || ''}">${etiqueta}</span>
          ${avisos ? `<ul class="mt-1 list-disc pl-4 text-xs text-gray-600 dark:text-gray-300">${avisos}</ul>` : ''}</td>
      </tr>`;
    }).join('');
  }

  function sinDetalle(lista) {
    if (!lista.length) return '';
    const items = lista.map((t) => `${fechaLegible(t.fecha)} (${dinero(t.monto)})`).join(', ');
    return `<i class="fas fa-circle-info mr-1"></i>La hoja de totales tiene dias sin detalle de productos, que no se importan: ${esc(items)}.`;
  }

  function opcionesAccion(grupo, decision, menu) {
    const valor = decision.accion === 'existente' ? `p:${decision.producto_id}` : decision.accion;
    const opciones = [
      ['crear', 'Crear producto nuevo'],
      ...menu.map((p) => [`p:${p.id_producto}`, `Usar del menu: ${p.nombre}`]),
      ['varios', 'Mandar a "Varios"'],
    ];
    return opciones.map(([v, texto]) => `<option value="${esc(v)}" ${v === valor ? 'selected' : ''}>${esc(texto)}</option>`).join('');
  }

  function grupos(lista, estado) {
    const unidades = {};
    Object.entries(estado.alias).forEach(([alias, clave]) => {
      unidades[clave] = (unidades[clave] || 0) + (estado.aliasInfo[alias]?.unidades || 0);
    });
    const opcionesMover = lista.map((g) => [g.clave, estado.grupos[g.clave].nombre || g.nombre]);
    return lista.filter((g) => unidades[g.clave]).map((g) => {
      const decision = estado.grupos[g.clave];
      const aliasDelGrupo = Object.keys(estado.alias).filter((alias) => estado.alias[alias] === g.clave);
      const chips = aliasDelGrupo.map((alias) => {
        const info = estado.aliasInfo[alias];
        const mover = opcionesMover.map(([clave, nombre]) => `<option value="${esc(clave)}" ${clave === g.clave ? 'selected' : ''}>${esc(nombre)}</option>`).join('');
        return `<li class="flex flex-wrap items-center gap-2 py-1">
          <span class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs dark:bg-gray-700">${esc(info.ejemplo)}</span>
          <span class="text-xs text-gray-500">x${info.unidades}${info.nota ? ` &middot; nota: ${esc(info.nota)}` : ''}${info.multiple ? ' &middot; <b class="text-amber-600">varios productos en una celda</b>' : ''}</span>
          <select data-alias-mover="${esc(alias)}" class="${input} text-xs">${mover}</select></li>`;
      }).join('');
      const editable = decision.accion === 'crear';
      return `<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-700">
        <div class="grid gap-2 md:grid-cols-[1fr_9rem_16rem_auto] md:items-center">
          <input data-grupo-nombre="${esc(g.clave)}" value="${esc(decision.nombre)}" ${editable ? '' : 'disabled'} class="${input} font-semibold disabled:opacity-60" aria-label="Nombre del producto">
          <input data-grupo-precio="${esc(g.clave)}" type="number" min="0" step="500" value="${esc(decision.precio)}" ${editable ? '' : 'disabled'} class="${input} disabled:opacity-60" aria-label="Precio">
          <select data-grupo-accion="${esc(g.clave)}" class="${input}">${opcionesAccion(g, decision, estado.menu)}</select>
          <span class="text-sm font-bold text-gray-700 dark:text-gray-200">${fmt.format(unidades[g.clave])} u.</span>
        </div>
        <details class="mt-2"><summary class="cursor-pointer text-xs font-semibold text-violet-700 dark:text-violet-300">
          ${aliasDelGrupo.length} forma(s) de escribirlo</summary><ul class="mt-1">${chips}</ul></details>
      </div>`;
    }).join('');
  }

  function historial(lista) {
    if (!lista.length) return '<p>Todavia no hay importaciones.</p>';
    const filas = lista.map((imp) => {
      const deshecha = imp.estado !== 'aplicada';
      const accion = deshecha
        ? '<span class="text-xs font-semibold text-gray-400">Deshecha</span>'
        : `<div class="flex justify-end gap-2">
            <button type="button" data-ver-ventas="${imp.id_importacion}" class="rounded-lg border border-violet-200 px-3 py-1 text-xs font-bold text-violet-700 hover:bg-violet-50 dark:border-violet-500/40 dark:text-violet-300">Ver ventas</button>
            <button type="button" data-revertir="${imp.id_importacion}" class="rounded-lg border border-rose-200 px-3 py-1 text-xs font-bold text-rose-700 hover:bg-rose-50 dark:border-rose-500/40 dark:text-rose-300">Deshacer</button></div>`;
      return `<tr class="${deshecha ? 'opacity-60' : ''}">
        <td class="px-2 py-2">#${imp.id_importacion}</td><td class="px-2 py-2">${esc(imp.nombre_archivo || '')}</td>
        <td class="px-2 py-2">${fechaLegible(imp.fecha_desde)} - ${fechaLegible(imp.fecha_hasta)}</td>
        <td class="px-2 py-2 text-right">${fmt.format(imp.pedidos)}</td><td class="px-2 py-2 text-right">${dinero(imp.total)}</td>
        <td class="px-2 py-2 text-right">${accion}</td></tr>`;
    }).join('');
    return `<div class="overflow-x-auto"><table class="min-w-full text-sm"><thead class="text-left text-xs uppercase text-gray-500">
      <tr><th class="px-2 py-2">N.</th><th class="px-2 py-2">Archivo</th><th class="px-2 py-2">Dias</th>
      <th class="px-2 py-2 text-right">Ventas</th><th class="px-2 py-2 text-right">Total</th><th></th></tr></thead>
      <tbody class="divide-y divide-gray-100 dark:divide-gray-700">${filas}</tbody></table></div>`;
  }

  function detalleVentas(data) {
    const imp = data.importacion;
    const filas = data.ventas.map((v) => {
      const buscar = esc(`${v.texto_excel} ${v.producto} ${v.nota} ${fechaLegible(v.fecha)}`.toLowerCase());
      return `<tr data-buscar="${buscar}">
        <td class="whitespace-nowrap px-2 py-1.5">${fechaLegible(v.fecha)}</td>
        <td class="px-2 py-1.5"><span class="font-mono text-xs">${esc(v.texto_excel)}</span>
          <div class="text-xs text-gray-400">${esc(v.hoja)}${v.fila ? `, fila ${v.fila}` : ''}</div></td>
        <td class="px-2 py-1.5 font-semibold">${esc(v.producto)}${v.nota ? `<div class="text-xs font-normal text-gray-500">${esc(v.nota)}</div>` : ''}</td>
        <td class="px-2 py-1.5 text-right">${fmt.format(v.cantidad)}</td>
        <td class="whitespace-nowrap px-2 py-1.5 text-right">${dinero(v.monto)}</td></tr>`;
    }).join('');
    return `<div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p class="font-bold text-gray-900 dark:text-white">Ventas de la importacion #${imp.id_importacion}
          <span class="font-normal text-gray-500">(${fmt.format(data.ventas.length)} ventas, ${dinero(imp.total)})</span></p>
        <div class="flex gap-2">
          <input type="search" data-detalle-buscar placeholder="Buscar plato, texto o fecha..." class="${input} w-60">
          <button type="button" data-detalle-cerrar class="rounded-lg border border-gray-200 px-3 py-1 text-xs font-semibold dark:border-gray-700">Cerrar</button>
        </div></div>
      <div class="max-h-[32rem] overflow-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table class="min-w-full text-sm"><thead class="sticky top-0 bg-gray-50 text-left text-xs uppercase text-gray-500 dark:bg-gray-900">
          <tr><th class="px-2 py-2">Fecha</th><th class="px-2 py-2">En el Excel decia</th><th class="px-2 py-2">Se cargo como</th>
          <th class="px-2 py-2 text-right">Cant.</th><th class="px-2 py-2 text-right">Monto</th></tr></thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-700">${filas}</tbody></table></div>`;
  }

  window.ImportarVentasRender = {resumen, hojas, dias, sinDetalle, grupos, historial, detalleVentas, dinero, fechaLegible, fmt};
})();
