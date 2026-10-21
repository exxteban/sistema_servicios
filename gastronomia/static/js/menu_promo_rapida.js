// Modal "Hacer promo": elige entre promo sobre el producto o combo (menu_combo.js).
// La promo se guarda con la API de promociones existente (/api/tienda/admin/promociones).
(function () {
  // En el sistema de pestanas la pagina puede estar cargada dos veces: trabajar solo sobre la copia propia.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const modal = scope.querySelector('#gastro-promo-modal');
  if (!modal) return;

  const csrf = scope.querySelector('#csrf-token')?.value || '';
  const puedePromos = modal.dataset.puedePromos === '1';
  const q = (selector) => modal.querySelector(selector);
  const pasos = Array.from(modal.querySelectorAll('[data-promo-paso]'));
  const errorBox = q('[data-promo-error]');
  const valorCampo = q('[data-promo-valor-campo]');
  const valorInput = q('[data-promo-valor]');
  const nombreInput = q('[data-promo-nombre]');
  const guardar = q('[data-promo-guardar]');
  const ERRORES = {
    promo_superpuesta: 'Este producto ya tiene otra promo activa en esas fechas.',
    valor_invalido: 'Revisa el valor de la promo.',
    cantidades_invalidas: 'Revisa las cantidades de la promo.',
    nombre_requerido: 'Ponele un nombre a la promo.',
  };
  let productos = [];
  try {
    productos = JSON.parse(scope.querySelector('#gastro-promo-productos-data')?.textContent || '[]');
  } catch (_error) {
    productos = [];
  }
  let producto = null;
  let tipo = '';
  let nombreEditado = false;

  const formatoGs = (valor) => `Gs. ${Math.round(Number(valor) || 0).toLocaleString('es-PY')}`;
  const numero = (texto) => Number(String(texto || '').replace(/\./g, '').replace(',', '.').replace(/[^\d.]/g, '')) || 0;

  const mostrarError = (mensaje) => {
    errorBox.textContent = mensaje || '';
    errorBox.classList.toggle('hidden', !mensaje);
  };

  const irA = (paso) => {
    pasos.forEach((nodo) => nodo.classList.toggle('hidden', nodo.dataset.promoPaso !== paso));
    mostrarError('');
    if (paso === 'combo') {
      modal.dispatchEvent(new CustomEvent('gastro:combo-abrir', {detail: {producto, productos}}));
    }
  };

  const abrir = (productoId) => {
    producto = productos.find((item) => String(item.id) === String(productoId));
    if (!producto) return;
    q('[data-promo-producto-nombre]').textContent = producto.nombre;
    tipo = '';
    nombreEditado = false;
    modal.querySelectorAll('[data-promo-tipo]').forEach((boton) => boton.classList.remove('activa'));
    valorCampo.classList.add('hidden');
    q('[data-promo-detalle]').classList.add('hidden');
    modal.classList.remove('hidden');
    irA(puedePromos ? 'elegir' : 'combo');
  };

  const cerrar = () => modal.classList.add('hidden');

  const nombreSugerido = () => {
    const valor = numero(valorInput.value);
    if (tipo === '2x1' || tipo === '3x2') return `${tipo} en ${producto.nombre}`;
    if (tipo === 'porcentaje') return `${valor || ''}% menos en ${producto.nombre}`;
    return `${producto.nombre} a ${formatoGs(valor)}`;
  };

  const actualizarAyuda = () => {
    const valor = numero(valorInput.value);
    const ayuda = q('[data-promo-valor-ayuda]');
    if (tipo === 'porcentaje') {
      ayuda.textContent = valor > 0 && valor < 100
        ? `Queda a ${formatoGs(producto.precio * (1 - valor / 100))} (antes ${formatoGs(producto.precio)}).`
        : 'Escribi un numero entre 1 y 99.';
    } else if (tipo === 'precio') {
      ayuda.textContent = `Hoy cuesta ${formatoGs(producto.precio)}.`;
    }
    if (!nombreEditado) nombreInput.value = nombreSugerido();
  };

  const elegirTipo = (nuevoTipo) => {
    tipo = nuevoTipo;
    modal.querySelectorAll('[data-promo-tipo]').forEach((boton) => {
      boton.classList.toggle('activa', boton.dataset.promoTipo === tipo);
    });
    const conValor = tipo === 'porcentaje' || tipo === 'precio';
    valorCampo.classList.toggle('hidden', !conValor);
    q('[data-promo-valor-label]').textContent = tipo === 'porcentaje' ? 'Cuanto % de descuento?' : 'Nuevo precio (Gs.)';
    valorInput.value = tipo === 'porcentaje' ? '20' : '';
    q('[data-promo-detalle]').classList.remove('hidden');
    actualizarAyuda();
    if (tipo === 'precio') valorInput.focus();
  };

  const fechaLocal = (fecha) => {
    const dos = (n) => String(n).padStart(2, '0');
    return `${fecha.getFullYear()}-${dos(fecha.getMonth() + 1)}-${dos(fecha.getDate())}T${dos(fecha.getHours())}:${dos(fecha.getMinutes())}`;
  };

  const armarPayload = () => {
    const valor = numero(valorInput.value);
    if (tipo === 'porcentaje' && !(valor > 0 && valor < 100)) throw new Error('El descuento tiene que ser entre 1 y 99 %.');
    if (tipo === 'precio' && !(valor > 0 && valor < Number(producto.precio))) {
      throw new Error(`El precio especial tiene que ser menor a ${formatoGs(producto.precio)}.`);
    }
    const inicio = new Date();
    const dias = Number(q('[data-promo-dias]').value || 30);
    const fin = new Date(inicio);
    if (dias === 1) {
      fin.setHours(23, 59, 0, 0);
    } else {
      fin.setDate(fin.getDate() + dias);
    }
    const cantidad = {'2x1': [2, 1], '3x2': [3, 2]}[tipo];
    return {
      nombre: nombreInput.value.trim(),
      descripcion_corta: '',
      tipo: cantidad ? 'cantidad' : (tipo === 'porcentaje' ? 'porcentaje' : 'precio_promocional'),
      valor: cantidad ? 1 : valor,
      cantidad_lleva: cantidad ? cantidad[0] : null,
      cantidad_paga: cantidad ? cantidad[1] : null,
      fecha_inicio: fechaLocal(inicio),
      fecha_fin: fechaLocal(fin),
      activa: true,
      productos: [],
      productos_gastronomia: [producto.id],
      cliente_id_gastronomia: modal.dataset.clienteId,
    };
  };

  const guardarPromo = async () => {
    mostrarError('');
    const payload = armarPayload();
    guardar.disabled = true;
    try {
      const response = await fetch('/api/tienda/admin/promociones', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(ERRORES[data.error] || data.mensaje || 'No se pudo crear la promo.');
      cerrar();
      await scope.gastroMenuReload?.({
        message: `Promo "${payload.nombre}" creada y activa.`,
        ok: true,
        state: {mainTab: 'menu-cargado', menuTab: 'promociones', editProductId: ''},
      });
    } finally {
      guardar.disabled = false;
    }
  };

  scope.addEventListener('click', (event) => {
    const boton = event.target.closest('[data-promo-producto]');
    if (boton) abrir(boton.dataset.promoProducto);
  });
  modal.addEventListener('click', (event) => {
    if (event.target.closest('[data-promo-cerrar]')) {
      cerrar();
      return;
    }
    const ir = event.target.closest('[data-promo-ir]');
    if (ir) {
      irA(ir.dataset.promoIr);
      return;
    }
    const tipoBoton = event.target.closest('[data-promo-tipo]');
    if (tipoBoton) elegirTipo(tipoBoton.dataset.promoTipo);
  });
  valorInput.addEventListener('input', actualizarAyuda);
  nombreInput.addEventListener('input', () => {
    nombreEditado = true;
  });
  guardar.addEventListener('click', () => {
    guardarPromo().catch((error) => mostrarError(error.message));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !modal.classList.contains('hidden')) cerrar();
  });

  scope.gastroPromoModal = {cerrar, mostrarError};
}());
