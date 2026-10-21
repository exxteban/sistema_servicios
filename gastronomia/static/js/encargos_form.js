// Formulario de alta y edicion de encargos (dialogo del tablero).
// El total que se muestra es estimado; el servidor recalcula precios, promociones y extras.
(() => {
  const ui = window.EncargosUI;
  const root = document.querySelector('[data-gastro-encargos]');
  const dialog = document.getElementById('encargo-form-dialog');
  const form = document.getElementById('encargo-form');
  if (!ui || !root || !dialog || !form) return;

  const itemsEl = form.querySelector('[data-items]');
  const totalEl = form.querySelector('[data-total]');
  const errorEl = form.querySelector('[data-form-error]');
  const submitBtn = form.querySelector('[data-submit]');
  const senaBlock = form.querySelector('[data-sena-block]');
  const senaFields = form.querySelector('[data-sena-fields]');
  const fotosEl = form.querySelector('[data-fotos]');
  const maxFotos = Number(root.dataset.maxFotos || 0);
  form.querySelector('[data-max-fotos]').textContent = String(maxFotos);
  form.querySelector('[data-fotos-block]').classList.toggle('hidden', maxFotos <= 0);

  let productos = null;
  let editing = null;
  let onSaved = () => {};

  const cargarProductos = async () => {
    if (productos) return productos;
    const data = await ui.apiJson('/api/gastronomia/productos');
    productos = (data.productos || []).filter((p) => p.disponible !== false);
    return productos;
  };

  const opcionesProductos = (selectedId) => productos.map((p) => `
    <option value="${p.id_producto}" data-precio="${Number(p.precio || 0)}" ${Number(p.id_producto) === Number(selectedId) ? 'selected' : ''}>
      ${ui.escapeHtml(p.nombre)} - ${ui.money(p.precio)}
    </option>`).join('');

  const itemRow = (item = {}) => {
    const row = document.createElement('div');
    row.className = 'grid gap-2 rounded-lg border border-gray-200 p-2 dark:border-gray-700 sm:grid-cols-[1fr_80px_auto]';
    row.dataset.opciones = JSON.stringify((item.modificadores || []).map((m) => m.opcion_id));
    row.dataset.productoOriginal = item.producto_id || '';
    row.innerHTML = `
      <select data-producto class="h-10 rounded-lg border border-gray-200 px-2 text-sm dark:border-gray-700 dark:bg-gray-900">
        <option value="">Elegi un producto</option>${opcionesProductos(item.producto_id)}
      </select>
      <input data-cantidad type="number" min="1" step="1" value="${Number(item.cantidad || 1)}" aria-label="Cantidad"
             class="h-10 rounded-lg border border-gray-200 px-2 text-sm dark:border-gray-700 dark:bg-gray-900">
      <button type="button" data-remove class="h-10 rounded-lg px-3 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10" aria-label="Quitar"><i class="fas fa-trash"></i></button>
      <input data-texto maxlength="240" placeholder='Texto en la torta (ej. "Feliz cumple Ana")' value="${ui.escapeHtml(item.texto_personalizado || '')}"
             class="h-10 rounded-lg border border-gray-200 px-2 text-sm dark:border-gray-700 dark:bg-gray-900 sm:col-span-3">
      <input data-notas maxlength="240" placeholder="Notas del producto (sabor, relleno, decoracion)" value="${ui.escapeHtml(item.notas || '')}"
             class="h-10 rounded-lg border border-gray-200 px-2 text-sm dark:border-gray-700 dark:bg-gray-900 sm:col-span-3">
    `;
    row.querySelector('[data-remove]').addEventListener('click', () => { row.remove(); actualizarTotal(); });
    row.addEventListener('input', actualizarTotal);
    row.addEventListener('change', actualizarTotal);
    return row;
  };

  const actualizarTotal = () => {
    let total = 0;
    itemsEl.querySelectorAll('[data-producto]').forEach((select) => {
      const precio = Number(select.selectedOptions[0]?.dataset.precio || 0);
      const cantidad = Math.max(1, Number(select.parentElement.querySelector('[data-cantidad]').value || 1));
      total += precio * cantidad;
    });
    totalEl.textContent = `Total estimado: ${ui.money(total)}`;
  };

  const leerItems = () => [...itemsEl.children].map((row) => {
    const productoId = Number(row.querySelector('[data-producto]').value || 0);
    // Los extras elegidos en el POS se conservan si no se cambio el producto.
    const opciones = String(productoId) === row.dataset.productoOriginal ? JSON.parse(row.dataset.opciones || '[]') : [];
    return {
      producto_id: productoId,
      cantidad: Math.max(1, Number(row.querySelector('[data-cantidad]').value || 1)),
      texto_personalizado: row.querySelector('[data-texto]').value.trim(),
      notas: row.querySelector('[data-notas]').value.trim(),
      opciones,
    };
  }).filter((item) => item.producto_id);

  const renderFotos = (fotos) => {
    fotosEl.innerHTML = (fotos || []).map((foto) => {
      const url = ui.safePhotoUrl(foto.url);
      return url ? `
        <span class="relative block h-16 w-16 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
          <img src="${ui.escapeHtml(url)}" alt="Foto de referencia" class="h-full w-full object-cover">
          <button type="button" data-delete-foto="${foto.id_foto}" class="absolute right-0 top-0 rounded-bl bg-black/60 px-1 text-xs text-white" aria-label="Borrar foto">&times;</button>
        </span>` : '';
    }).join('');
  };

  fotosEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-delete-foto]');
    if (!button || !editing) return;
    try {
      await window.EncargoFotos.remove(editing.id_pedido, button.dataset.deleteFoto);
      editing.fotos = (editing.fotos || []).filter((f) => String(f.id_foto) !== button.dataset.deleteFoto);
      renderFotos(editing.fotos);
      onSaved();
    } catch (error) {
      ui.showError(errorEl, error.message);
    }
  });

  form.cobrar_sena.addEventListener('change', () => senaFields.classList.toggle('hidden', !form.cobrar_sena.checked));
  form.querySelector('[data-add-item]').addEventListener('click', () => { itemsEl.appendChild(itemRow()); actualizarTotal(); });
  ui.closeOnButtons(dialog);

  const subirFotos = async (pedidoId) => {
    const archivos = [...(form.fotos.files || [])];
    const errores = [];
    for (const archivo of archivos) {
      try {
        await window.EncargoFotos.upload(pedidoId, archivo);
      } catch (error) {
        errores.push(`${archivo.name}: ${error.message}`);
      }
    }
    return errores;
  };

  const payload = () => {
    const data = {
      nombre_cliente: form.nombre_cliente.value.trim(),
      celular_cliente: form.celular_cliente.value.trim(),
      fecha_programada: `${form.fecha.value}T${form.hora.value}`,
      notas: form.notas.value.trim(),
      tipo_pedido: 'retiro',
      items: leerItems(),
    };
    if (!editing && form.cobrar_sena.checked) {
      data.sena = {
        monto: Number(form.sena_monto.value || 0),
        metodo_pago: form.sena_metodo.value,
        referencia: form.sena_referencia.value.trim(),
      };
    }
    return data;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    ui.showError(errorEl, '');
    const data = payload();
    if (!data.items.length) {
      ui.showError(errorEl, 'Agrega al menos un producto.');
      return;
    }
    submitBtn.disabled = true;
    try {
      const url = editing ? `/api/gastronomia/encargos/${editing.id_pedido}` : '/api/gastronomia/encargos';
      const result = await ui.apiJson(url, {method: editing ? 'PUT' : 'POST', body: JSON.stringify(data)});
      const errores = await subirFotos(result.pedido.id_pedido);
      const avisos = [result.aviso, ...errores].filter(Boolean);
      dialog.close();
      onSaved(avisos.length ? avisos.join(' ') : (editing ? 'Encargo actualizado.' : 'Encargo guardado.'), !avisos.length);
    } catch (error) {
      ui.showError(errorEl, error.message);
    } finally {
      submitBtn.disabled = false;
    }
  });

  const open = async (encargo = null, callback = () => {}) => {
    onSaved = callback;
    editing = encargo;
    form.reset();
    ui.showError(errorEl, '');
    senaFields.classList.add('hidden');
    senaBlock.classList.toggle('hidden', Boolean(encargo));
    form.querySelector('[data-form-title]').textContent = encargo ? `Editar encargo ${encargo.codigo_entrega || ''}` : 'Nuevo encargo';
    itemsEl.innerHTML = '<p class="text-sm text-gray-500">Cargando productos...</p>';
    dialog.showModal();
    try {
      await cargarProductos();
    } catch (error) {
      ui.showError(errorEl, error.message);
      return;
    }
    itemsEl.innerHTML = '';
    if (encargo) {
      form.nombre_cliente.value = encargo.nombre_cliente || '';
      form.celular_cliente.value = encargo.celular_cliente || '';
      form.fecha.value = String(encargo.fecha_programada || '').slice(0, 10);
      form.hora.value = ui.hora(encargo.fecha_programada);
      form.notas.value = encargo.notas || '';
      (encargo.items || []).forEach((item) => itemsEl.appendChild(itemRow(item)));
    } else {
      const manana = new Date();
      manana.setDate(manana.getDate() + 1);
      form.fecha.value = ui.isoDia(manana);
      itemsEl.appendChild(itemRow());
    }
    renderFotos(encargo?.fotos || []);
    actualizarTotal();
  };

  window.EncargoForm = {open};
})();
