/* Flujo de importacion de ventas historicas: subir -> revisar -> confirmar. */
(function () {
  const raiz = document.querySelector('[data-importar-ventas]');
  if (!raiz) return;
  const R = window.ImportarVentasRender;
  const csrf = document.getElementById('csrf-token')?.value || '';
  const $ = (id) => document.getElementById(id);
  let estado = null;

  async function api(url, opciones = {}) {
    const resp = await fetch(url, {...opciones, headers: {'X-CSRFToken': csrf, ...(opciones.headers || {})}});
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) throw new Error(data.error || data.mensaje || 'Error inesperado.');
    return data;
  }

  function alerta(texto, tipo = 'error') {
    const caja = $('imp-alert');
    if (!texto) { caja.classList.add('hidden'); return; }
    const clases = tipo === 'ok'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-200'
      : 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200';
    caja.className = `mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${clases}`;
    caja.textContent = texto;
    caja.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }

  function crearEstado(analisis) {
    const nuevo = {analisis, menu: analisis.menu, dias: {}, grupos: {}, alias: {}, aliasInfo: {}};
    analisis.dias.forEach((dia) => { nuevo.dias[dia.indice] = {fecha: dia.fecha, incluir: true}; });
    analisis.grupos.forEach((grupo) => {
      nuevo.grupos[grupo.clave] = {accion: grupo.accion, nombre: grupo.nombre, precio: grupo.precio, producto_id: grupo.producto_id};
      grupo.alias.forEach((alias) => { nuevo.alias[alias.alias] = grupo.clave; nuevo.aliasInfo[alias.alias] = alias; });
    });
    return nuevo;
  }

  function totalesIncluidos() {
    const incluidos = estado.analisis.dias.filter((dia) => estado.dias[dia.indice].incluir);
    return {
      dias: new Set(incluidos.map((dia) => estado.dias[dia.indice].fecha).filter(Boolean)).size,
      pedidos: incluidos.reduce((s, dia) => s + dia.filas, 0),
      total: incluidos.reduce((s, dia) => s + dia.suma, 0),
    };
  }

  function fechasRepetidas() {
    const vistas = new Set();
    const repetidas = new Set();
    Object.values(estado.dias).filter((d) => d.incluir && d.fecha).forEach((d) => {
      (vistas.has(d.fecha) ? repetidas : vistas).add(d.fecha);
    });
    return repetidas;
  }

  function dibujar() {
    const a = estado.analisis;
    const totales = totalesIncluidos();
    $('imp-resumen').innerHTML = R.resumen(totales);
    $('imp-hojas').innerHTML = R.hojas(a.hojas);
    $('imp-dias').innerHTML = R.dias(a.dias, estado.dias, fechasRepetidas());
    const sinDetalle = R.sinDetalle(a.totales_sin_detalle);
    $('imp-sin-detalle').innerHTML = sinDetalle;
    $('imp-sin-detalle').classList.toggle('hidden', !sinDetalle);
    $('imp-grupos').innerHTML = R.grupos(a.grupos, estado);
    const previa = a.importacion_previa;
    $('imp-previa').classList.toggle('hidden', !previa);
    if (previa) {
      $('imp-previa').textContent = `Este mismo archivo ya se importo (importacion #${previa.id_importacion}). Deshacela abajo antes de volver a cargarlo.`;
    }
    const faltan = a.dias.filter((dia) => estado.dias[dia.indice].incluir && !estado.dias[dia.indice].fecha).length;
    $('imp-confirmar').disabled = Boolean(previa) || faltan > 0 || totales.dias === 0;
    $('imp-confirmar-texto').textContent = faltan
      ? `Falta la fecha en ${faltan} dia(s).`
      : `Se van a importar ${R.fmt.format(totales.pedidos)} ventas por ${R.dinero(totales.total)} en ${totales.dias} dia(s), pagadas en efectivo, sin tocar el stock.`;
  }

  function dibujarCategorias(categorias) {
    const opciones = ['<option value="">Menu (se crea si no existe)</option>']
      .concat(categorias.map((c) => `<option value="${c.id_categoria}">${c.nombre.replace(/</g, '&lt;')}</option>`));
    $('imp-categoria').innerHTML = opciones.join('');
  }

  async function analizar(evento) {
    evento.preventDefault();
    const archivo = $('imp-archivo').files[0];
    if (!archivo) return;
    alerta('');
    $('imp-analizar').disabled = true;
    try {
      const datos = new FormData();
      datos.append('archivo', archivo);
      const resp = await api('/api/gastronomia/importar-ventas/analizar', {method: 'POST', body: datos});
      estado = crearEstado(resp.analisis);
      dibujarCategorias(resp.analisis.categorias);
      dibujar();
      $('imp-paso-revisar').classList.remove('hidden');
      $('imp-paso-revisar').scrollIntoView({behavior: 'smooth'});
    } catch (error) {
      alerta(error.message);
    } finally {
      $('imp-analizar').disabled = false;
    }
  }

  function payload() {
    return {
      token: estado.analisis.token,
      nombre_archivo: estado.analisis.nombre_archivo,
      categoria_id: $('imp-categoria').value || null,
      dias: Object.entries(estado.dias).map(([indice, d]) => ({indice: Number(indice), fecha: d.fecha, incluir: d.incluir})),
      grupos: Object.entries(estado.grupos).map(([clave, g]) => ({clave, ...g})),
      alias: estado.alias,
    };
  }

  async function confirmar() {
    const totales = totalesIncluidos();
    if (!window.confirm(`Importar ${totales.pedidos} ventas por ${R.dinero(totales.total)}? Se puede deshacer despues.`)) return;
    const boton = $('imp-confirmar');
    const textoBoton = boton.innerHTML;
    boton.disabled = true;
    boton.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Importando...';
    try {
      const resp = await api('/api/gastronomia/importar-ventas/aplicar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload()),
      });
      const imp = resp.importacion;
      const creados = imp.productos_creados.length ? ` Productos nuevos en el menu: ${imp.productos_creados.length}.` : '';
      alerta(`Listo: se importaron ${imp.pedidos} ventas por ${R.dinero(imp.total)} (${imp.dias} dias).${creados}`, 'ok');
      reiniciar();
      cargarHistorial();
    } catch (error) {
      alerta(error.message);
      boton.disabled = false;
    } finally {
      boton.innerHTML = textoBoton;
    }
  }

  function reiniciar() {
    estado = null;
    $('imp-form').reset();
    $('imp-paso-revisar').classList.add('hidden');
  }

  async function cargarHistorial() {
    try {
      const resp = await api('/api/gastronomia/importar-ventas');
      $('imp-historial').innerHTML = R.historial(resp.importaciones);
    } catch (error) {
      $('imp-historial').textContent = error.message;
    }
  }

  async function revertir(boton) {
    const id = boton.dataset.revertir;
    if (boton.disabled || !window.confirm(`Deshacer la importacion #${id}? Se borran sus ventas y cajas historicas.`)) return;
    boton.disabled = true;
    boton.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Deshaciendo...';
    try {
      const resp = await api(`/api/gastronomia/importar-ventas/${id}/revertir`, {method: 'POST'});
      alerta(`Importacion #${id} deshecha: se borraron ${resp.importacion.pedidos_borrados} ventas.`, 'ok');
      cargarHistorial();
    } catch (error) {
      alerta(error.message);
      cargarHistorial();
    }
  }

  function alCambiar(evento) {
    const el = evento.target;
    if (!estado) return;
    if (el.dataset.diaIncluir !== undefined) estado.dias[el.dataset.diaIncluir].incluir = el.checked;
    else if (el.dataset.diaFecha !== undefined) estado.dias[el.dataset.diaFecha].fecha = el.value;
    else if (el.dataset.grupoNombre !== undefined) { estado.grupos[el.dataset.grupoNombre].nombre = el.value; return; }
    else if (el.dataset.grupoPrecio !== undefined) { estado.grupos[el.dataset.grupoPrecio].precio = el.value; return; }
    else if (el.dataset.grupoAccion !== undefined) {
      const grupo = estado.grupos[el.dataset.grupoAccion];
      if (el.value.startsWith('p:')) {
        grupo.accion = 'existente';
        grupo.producto_id = Number(el.value.slice(2));
      } else {
        grupo.accion = el.value;
      }
    } else if (el.dataset.aliasMover !== undefined) estado.alias[el.dataset.aliasMover] = el.value;
    else return;
    dibujar();
  }

  $('imp-form').addEventListener('submit', analizar);
  $('imp-confirmar').addEventListener('click', confirmar);
  $('imp-cancelar').addEventListener('click', () => { reiniciar(); alerta(''); });
  raiz.addEventListener('change', alCambiar);
  raiz.addEventListener('input', (evento) => {
    if (evento.target.dataset.grupoNombre !== undefined || evento.target.dataset.grupoPrecio !== undefined) alCambiar(evento);
  });
  raiz.addEventListener('click', (evento) => {
    const boton = evento.target.closest('[data-revertir]');
    if (boton) revertir(boton);
  });
  cargarHistorial();
})();
