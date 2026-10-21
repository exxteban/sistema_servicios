// Produccion del dia: tandas, merma, porciones (abrir torta) y reporte de merma.
(() => {
  const ui = window.EncargosUI;
  const root = document.querySelector('[data-gastro-produccion]');
  const filasEl = document.getElementById('produccion-filas');
  const vacioEl = document.getElementById('produccion-vacio');
  const alertEl = document.getElementById('produccion-alert');
  if (!ui || !root || !filasEl || !vacioEl || !alertEl) return;

  const API = '/api/gastronomia/produccion';
  const puedeConfigurar = root.dataset.puedeConfigurar === '1';
  let productos = [];
  let actual = null;

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
    <button type="button" data-action="${action}" data-id="${id}" class="rounded-lg px-3 py-1.5 text-xs font-bold ${clase}">${label}</button>`;

  const acciones = (p) => {
    const items = [
      boton('tanda', p.producto_id, '+ Tanda', 'bg-amber-500 text-white hover:bg-amber-600'),
      boton('merma', p.producto_id, 'Merma', 'border border-gray-200 text-gray-700 dark:border-gray-600 dark:text-gray-200'),
    ];
    if (p.relacion_porciones) {
      items.push(boton('abrir', p.producto_id, `Abrir (${p.relacion_porciones.porciones})`, 'bg-violet-600 text-white hover:bg-violet-700'));
    }
    if (puedeConfigurar) {
      items.push(boton('porciones', p.producto_id, p.relacion_porciones ? 'Porciones' : '+ Porciones', 'text-violet-700 dark:text-violet-300'));
    }
    return items.join('');
  };

  const render = () => {
    vacioEl.classList.toggle('hidden', productos.length > 0);
    filasEl.innerHTML = productos.map((p) => `
      <tr>
        <td class="px-3 py-2">
          <p class="font-bold text-gray-900 dark:text-white">${ui.escapeHtml(p.nombre)}</p>
          ${p.relacion_porciones ? `<p class="text-xs text-gray-500 dark:text-gray-400">1 = ${p.relacion_porciones.porciones} x ${ui.escapeHtml(p.relacion_porciones.porcion || '')}</p>` : ''}
        </td>
        <td class="px-3 py-2 text-right font-black ${p.stock <= 0 ? 'text-rose-600 dark:text-rose-300' : ''}">${p.stock}</td>
        <td class="px-3 py-2 text-right">${p.producido}</td>
        <td class="px-3 py-2 text-right">${p.vendido}</td>
        <td class="px-3 py-2 text-right">${p.merma}</td>
        <td class="px-3 py-2"><div class="flex flex-wrap justify-end gap-1">${acciones(p)}</div></td>
      </tr>`).join('');
  };

  const cargar = async () => {
    try {
      const data = await ui.apiJson(`${API}/dia`);
      productos = data.productos || [];
      render();
    } catch (error) {
      showAlert(error.message, false);
    }
  };

  const abrirDialogo = (id, producto) => {
    const dialog = document.getElementById(id);
    const form = dialog.querySelector('form');
    form.reset();
    ui.showError(dialog.querySelector('[data-error]'), '');
    dialog.querySelector('[data-producto]').textContent = producto.nombre;
    dialog.showModal();
    return {dialog, form};
  };

  const enviar = (dialogId, url, method, body, mensaje) => async () => {
    const dialog = document.getElementById(dialogId);
    try {
      await ui.apiJson(url, {method, body: body ? JSON.stringify(body) : undefined});
      dialog.close();
      showAlert(mensaje);
      cargar();
    } catch (error) {
      ui.showError(dialog.querySelector('[data-error]'), error.message);
    }
  };

  const abrirPorciones = (producto) => {
    const {dialog, form} = abrirDialogo('produccion-porciones-dialog', producto);
    const relacion = producto.relacion_porciones;
    const select = form.elements.producto_porcion_id;
    select.innerHTML = '<option value="">Elegir...</option>' + productos
      .filter((p) => p.producto_id !== producto.producto_id)
      .map((p) => `<option value="${p.producto_id}">${ui.escapeHtml(p.nombre)}</option>`).join('');
    if (relacion) {
      select.value = String(relacion.producto_porcion_id);
      form.elements.porciones.value = relacion.porciones;
    }
    dialog.querySelector('[data-quitar]').classList.toggle('hidden', !relacion);
  };

  filasEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    actual = productos.find((p) => p.producto_id === Number(button.dataset.id));
    if (!actual) return;
    showAlert('');
    const action = button.dataset.action;
    if (action === 'tanda') abrirDialogo('produccion-tanda-dialog', actual);
    if (action === 'merma') abrirDialogo('produccion-merma-dialog', actual);
    if (action === 'porciones') abrirPorciones(actual);
    if (action === 'abrir') {
      const rel = actual.relacion_porciones;
      if (!window.confirm(`Abrir 1 "${actual.nombre}" en ${rel.porciones} porciones?`)) return;
      try {
        await ui.apiJson(`${API}/productos/${actual.producto_id}/abrir`, {method: 'POST'});
        showAlert(`Se abrio 1 "${actual.nombre}": +${rel.porciones} porciones.`);
        cargar();
      } catch (error) {
        showAlert(error.message, false);
      }
    }
  });

  document.querySelector('[data-form="tanda"]').addEventListener('submit', (event) => {
    event.preventDefault();
    const cantidad = event.currentTarget.elements.cantidad.value;
    enviar('produccion-tanda-dialog', `${API}/tandas`, 'POST',
      {producto_id: actual.producto_id, cantidad}, `Tanda cargada: +${cantidad} "${actual.nombre}".`)();
  });

  document.querySelector('[data-form="merma"]').addEventListener('submit', (event) => {
    event.preventDefault();
    const {cantidad, motivo, observacion} = event.currentTarget.elements;
    enviar('produccion-merma-dialog', `${API}/mermas`, 'POST', {
      producto_id: actual.producto_id, cantidad: cantidad.value, motivo: motivo.value, observacion: observacion.value,
    }, `Merma registrada: -${cantidad.value} "${actual.nombre}".`)();
  });

  const porcionesForm = document.querySelector('[data-form="porciones"]');
  porcionesForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const {producto_porcion_id: porcion, porciones} = event.currentTarget.elements;
    enviar('produccion-porciones-dialog', `${API}/productos/${actual.producto_id}/porciones`, 'PUT',
      {producto_porcion_id: porcion.value, porciones: porciones.value}, 'Porciones guardadas.')();
  });
  porcionesForm.querySelector('[data-quitar]').addEventListener('click', () => {
    enviar('produccion-porciones-dialog', `${API}/productos/${actual.producto_id}/porciones`, 'DELETE',
      null, 'Porciones quitadas.')();
  });

  document.getElementById('produccion-cierre')?.addEventListener('click', () => {
    if (!productos.length) {
      showAlert('No hay productos con control de stock para cerrar.', false);
      return;
    }
    window.ProduccionCierre?.abrir(productos, (mensaje) => {
      showAlert(mensaje);
      cargar();
      cargarMerma();
    });
  });

  ['produccion-tanda-dialog', 'produccion-merma-dialog', 'produccion-porciones-dialog']
    .forEach((id) => ui.closeOnButtons(document.getElementById(id)));

  // Reporte de merma (solo si la seccion existe: permiso de reportes o menu).
  const mermaForm = document.getElementById('merma-filtros');
  const mermaEl = document.getElementById('merma-reporte');

  const renderMerma = (data) => {
    if (!data.productos.length) {
      mermaEl.innerHTML = '<p class="text-gray-500 dark:text-gray-400">Sin merma en el periodo.</p>';
      return;
    }
    mermaEl.innerHTML = `
      <div class="overflow-x-auto"><table class="min-w-full text-sm">
        <thead><tr class="text-left text-[11px] font-black uppercase text-gray-500 dark:text-gray-300">
          <th class="py-2 pr-3">Producto</th><th class="py-2 pr-3">Motivos</th>
          <th class="py-2 pr-3 text-right">Unidades</th><th class="py-2 text-right">Costo</th></tr></thead>
        <tbody class="divide-y divide-gray-100 dark:divide-gray-700">${data.productos.map((p) => `
          <tr>
            <td class="py-2 pr-3 font-bold">${ui.escapeHtml(p.nombre)}</td>
            <td class="py-2 pr-3 text-xs text-gray-600 dark:text-gray-300">${p.motivos.map((m) => `${ui.escapeHtml(m.motivo_label)}: ${m.cantidad}`).join(' · ')}</td>
            <td class="py-2 pr-3 text-right">${p.cantidad}</td>
            <td class="py-2 text-right">${ui.money(p.costo)}${p.sin_costo ? ' <span class="text-xs text-amber-700 dark:text-amber-300">(sin receta)</span>' : ''}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr class="font-black"><td class="py-2" colspan="2">Total</td>
          <td class="py-2 pr-3 text-right">${data.total_unidades}</td><td class="py-2 text-right">${ui.money(data.total_costo)}</td></tr></tfoot>
      </table></div>`;
  };

  const cargarMerma = async () => {
    if (!mermaForm || !mermaEl) return;
    const params = new URLSearchParams();
    ['desde', 'hasta'].forEach((campo) => {
      if (mermaForm.elements[campo].value) params.set(campo, mermaForm.elements[campo].value);
    });
    try {
      const data = await ui.apiJson(`${API}/merma?${params}`);
      mermaForm.elements.desde.value = data.desde;
      mermaForm.elements.hasta.value = data.hasta;
      renderMerma(data);
    } catch (error) {
      mermaEl.textContent = error.message;
    }
  };

  mermaForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    cargarMerma();
  });

  cargar();
  cargarMerma();
})();
