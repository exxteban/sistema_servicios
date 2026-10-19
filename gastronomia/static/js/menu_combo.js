// Paso "Armar combo" del modal Hacer promo: junta productos del menu a un precio.
(function () {
  const modal = document.getElementById('gastro-promo-modal');
  const paso = modal?.querySelector('[data-promo-paso="combo"]');
  if (!modal || !paso) return;

  const csrf = document.getElementById('csrf-token')?.value || '';
  const q = (selector) => paso.querySelector(selector);
  const incluidosNode = q('[data-combo-incluidos]');
  const buscar = q('[data-combo-buscar]');
  const resultados = q('[data-combo-resultados]');
  const bebidaCheck = q('[data-combo-bebida-check]');
  const bebidasBox = q('[data-combo-bebidas]');
  const bebidasLista = q('[data-combo-bebidas-lista]');
  const precioInput = q('[data-combo-precio]');
  const nombreInput = q('[data-combo-nombre]');
  const guardar = q('[data-combo-guardar]');
  const guardarTexto = q('[data-combo-guardar-texto]');
  let productos = [];
  let incluidos = [];
  let nombreEditado = false;

  const formatoGs = (valor) => `Gs. ${Math.round(Number(valor) || 0).toLocaleString('es-PY')}`;
  const numero = (texto) => Number(String(texto || '').replace(/\./g, '').replace(',', '.').replace(/[^\d.]/g, '')) || 0;
  const error = (mensaje) => window.gastroPromoModal?.mostrarError(mensaje);

  const bebidasElegidas = () => Array.from(bebidasLista.querySelectorAll('input:checked'))
    .map((input) => productos.find((item) => String(item.id) === input.value))
    .filter(Boolean);

  const conBebida = () => bebidaCheck.checked && bebidasElegidas().length > 0;

  const elemento = (tag, clase, texto) => {
    const nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
  };

  const renderIncluidos = () => {
    incluidosNode.innerHTML = '';
    incluidos.forEach((producto, indice) => {
      const fila = elemento('div', 'gastro-combo-item');
      fila.appendChild(elemento('span', '', `${producto.nombre} · ${formatoGs(producto.precio)}`));
      const quitar = elemento('button', 'gastro-extras-remove');
      quitar.type = 'button';
      quitar.dataset.comboQuitar = String(indice);
      quitar.title = 'Quitar del combo';
      quitar.innerHTML = '<i class="fas fa-times"></i>';
      fila.appendChild(quitar);
      incluidosNode.appendChild(fila);
    });
  };

  const renderBebidas = () => {
    bebidasLista.innerHTML = '';
    productos.filter((item) => item.es_bebida).forEach((bebida) => {
      const label = elemento('label', 'flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = String(bebida.id);
      input.checked = true;
      label.append(input, elemento('span', '', `${bebida.nombre} (${formatoGs(bebida.precio)})`));
      bebidasLista.appendChild(label);
    });
    if (!bebidasLista.children.length) {
      bebidasLista.appendChild(elemento('p', 'text-xs text-gray-500', 'No hay productos en una categoria de bebidas.'));
    }
  };

  const actualizar = () => {
    const bebidas = conBebida() ? bebidasElegidas() : [];
    const masBarata = bebidas.length ? Math.min(...bebidas.map((item) => Number(item.precio) || 0)) : 0;
    const separado = incluidos.reduce((total, item) => total + (Number(item.precio) || 0), 0) + masBarata;
    const precio = numero(precioInput.value);
    q('[data-combo-separado]').textContent = formatoGs(separado);
    const ahorro = q('[data-combo-ahorro]');
    ahorro.classList.toggle('hidden', !(precio > 0 && precio < separado));
    ahorro.textContent = `El cliente ahorra ${formatoGs(separado - precio)}${bebidas.length ? ' (con la bebida mas barata)' : ''}.`;

    if (!nombreEditado) {
      const partes = incluidos.map((item) => item.nombre);
      if (bebidas.length) partes.push('bebida');
      nombreInput.value = partes.length ? `Combo ${partes.join(' + ')}`.slice(0, 160) : '';
    }

    const conStock = [...new Set([...incluidos, ...bebidas].filter((item) => item.control_stock_venta).map((item) => item.nombre))];
    const aviso = q('[data-combo-aviso]');
    aviso.classList.toggle('hidden', !conStock.length);
    aviso.textContent = `Ojo: ${conStock.join(', ')} se agota por unidades y vender el combo no le descuenta unidades.`;

    const cosas = incluidos.length + (bebidas.length ? 1 : 0);
    let motivo = '';
    if (cosas < 2) motivo = 'Suma al menos otro producto o la bebida';
    else if (!(precio > 0)) motivo = 'Escribi el precio del combo';
    else if (!nombreInput.value.trim()) motivo = 'Ponele un nombre';
    guardar.disabled = Boolean(motivo);
    guardarTexto.textContent = motivo || 'Crear combo';
  };

  const renderResultados = () => {
    const texto = buscar.value.trim().toLowerCase();
    resultados.innerHTML = '';
    if (!texto) return;
    productos
      .filter((item) => item.nombre.toLowerCase().includes(texto))
      .slice(0, 6)
      .forEach((item) => {
        const boton = elemento('button', 'gastro-combo-item w-full text-left hover:border-emerald-400');
        boton.type = 'button';
        boton.dataset.comboAgregar = String(item.id);
        boton.append(elemento('span', '', item.nombre), elemento('span', 'text-emerald-700 dark:text-emerald-300', `+ ${formatoGs(item.precio)}`));
        resultados.appendChild(boton);
      });
  };

  const guardarCombo = async () => {
    error('');
    guardar.disabled = true;
    try {
      const response = await fetch('/api/gastronomia/combos', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({
          nombre: nombreInput.value.trim(),
          precio: precioInput.value.trim(),
          producto_ids: incluidos.map((item) => item.id),
          bebida_ids: conBebida() ? bebidasElegidas().map((item) => item.id) : [],
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.mensaje || 'No se pudo crear el combo.');
      window.gastroPromoModal?.cerrar();
      await window.gastroMenuReload?.({
        message: [`Combo "${data.producto.nombre}" creado en la categoria Combos.`, ...(data.avisos || [])].join(' '),
        ok: true,
        state: {mainTab: 'menu-cargado', menuTab: 'productos', editProductId: ''},
      });
    } finally {
      actualizar();
    }
  };

  modal.addEventListener('gastro:combo-abrir', (event) => {
    productos = event.detail.productos || [];
    incluidos = event.detail.producto ? [event.detail.producto] : [];
    nombreEditado = false;
    buscar.value = '';
    precioInput.value = '';
    bebidaCheck.checked = false;
    bebidasBox.classList.add('hidden');
    resultados.innerHTML = '';
    renderIncluidos();
    renderBebidas();
    actualizar();
  });

  paso.addEventListener('click', (event) => {
    const agregar = event.target.closest('[data-combo-agregar]');
    if (agregar) {
      const producto = productos.find((item) => String(item.id) === agregar.dataset.comboAgregar);
      if (producto && incluidos.length < 10) incluidos.push(producto);
      buscar.value = '';
      resultados.innerHTML = '';
      renderIncluidos();
      actualizar();
      return;
    }
    const quitar = event.target.closest('[data-combo-quitar]');
    if (quitar) {
      incluidos.splice(Number(quitar.dataset.comboQuitar), 1);
      renderIncluidos();
      actualizar();
    }
  });
  buscar.addEventListener('input', renderResultados);
  bebidaCheck.addEventListener('change', () => {
    bebidasBox.classList.toggle('hidden', !bebidaCheck.checked);
    actualizar();
  });
  bebidasLista.addEventListener('change', actualizar);
  precioInput.addEventListener('input', actualizar);
  nombreInput.addEventListener('input', () => {
    nombreEditado = true;
    actualizar();
  });
  guardar.addEventListener('click', () => {
    guardarCombo().catch((err) => error(err.message));
  });
}());
