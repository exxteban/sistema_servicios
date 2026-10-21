// Plantillas de arranque: el usuario elige rubro, tilda productos y pone precios.
(function () {
  // En el sistema de pestanas la pagina puede estar cargada dos veces: trabajar solo sobre la copia propia.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const raiz = scope.querySelector('#gastro-plantillas');
  const dataNode = scope.querySelector('#gastro-menu-plantillas-data');
  if (!raiz || !dataNode) return;

  const csrf = scope.querySelector('#csrf-token')?.value || '';
  const rubros = raiz.querySelector('[data-plantilla-rubros]');
  const paso2 = raiz.querySelector('[data-plantilla-paso2]');
  const lista = raiz.querySelector('[data-plantilla-lista]');
  const aplicar = raiz.querySelector('[data-plantilla-aplicar]');
  const aplicarTexto = raiz.querySelector('[data-plantilla-aplicar-texto]');
  const promoBox = raiz.querySelector('[data-plantilla-promo]');
  const promoCheck = raiz.querySelector('[data-plantilla-promo-check]');
  const promoNombre = raiz.querySelector('[data-plantilla-promo-nombre]');
  const puedePromos = raiz.dataset.puedePromos === '1';
  let plantillaActual = null;
  let plantillas = [];
  try {
    plantillas = JSON.parse(dataNode.textContent || '[]');
  } catch (_error) {
    plantillas = [];
  }

  const avisar = (mensaje, ok) => {
    if (typeof scope.gastroMenuShowAlert === 'function') {
      scope.gastroMenuShowAlert(mensaje, ok);
    } else {
      window.alert(mensaje);
    }
  };

  const resumenExtras = (producto) => {
    const nombres = (texto) => texto.split('\n').map((linea) => linea.split('|')[0].trim()).filter(Boolean);
    const partes = [
      ...nombres(producto.removibles || '').map((nombre) => `sin ${nombre}`),
      ...nombres(producto.adicionales || '').map((nombre) => `+ ${nombre}`),
    ];
    return partes.length ? `Incluye opciones: ${partes.join(', ')}` : '';
  };

  const filas = () => Array.from(lista.querySelectorAll('[data-plantilla-fila]'));

  // La promo depende de un producto de la plantilla: se oculta si se destilda.
  const filaPromo = () => {
    const promo = plantillaActual?.promo;
    if (!promo || !puedePromos) return null;
    return filas().find((fila) => fila.dataset.original === promo.producto) || null;
  };

  const actualizarPromo = () => {
    const fila = filaPromo();
    const activa = Boolean(fila && fila.querySelector('[data-plantilla-check]').checked);
    promoBox?.classList.toggle('hidden', !activa);
    if (!activa || !promoNombre) return;
    const {lleva, paga} = plantillaActual.promo;
    const nombre = fila.querySelector('[data-plantilla-nombre]').value.trim() || plantillaActual.promo.producto;
    promoNombre.textContent = `"${lleva}x${paga} en ${nombre}"`;
  };

  const actualizarBoton = () => {
    const marcadas = filas().filter((fila) => fila.querySelector('[data-plantilla-check]').checked);
    const sinPrecio = marcadas.filter((fila) => !fila.querySelector('[data-plantilla-precio]').value.trim());
    filas().forEach((fila) => {
      fila.classList.toggle('is-off', !fila.querySelector('[data-plantilla-check]').checked);
    });
    actualizarPromo();
    aplicar.disabled = marcadas.length === 0 || sinPrecio.length > 0;
    if (!marcadas.length) {
      aplicarTexto.textContent = 'Marca al menos un producto';
    } else if (sinPrecio.length) {
      aplicarTexto.textContent = `Falta el precio de ${sinPrecio.length} producto${sinPrecio.length === 1 ? '' : 's'}`;
    } else {
      aplicarTexto.textContent = `Cargar ${marcadas.length} producto${marcadas.length === 1 ? '' : 's'}`;
    }
  };

  const crearFila = (categoria, producto) => {
    const fila = document.createElement('div');
    fila.dataset.plantillaFila = '';
    fila.dataset.categoria = categoria.nombre;
    fila.dataset.original = producto.nombre;
    fila.dataset.removibles = producto.removibles || '';
    fila.dataset.adicionales = producto.adicionales || '';
    fila.innerHTML = `
      <div class="gastro-template-row">
        <input type="checkbox" data-plantilla-check checked class="h-5 w-5">
        <input type="text" data-plantilla-nombre maxlength="160" class="gastro-template-input" aria-label="Nombre del producto">
        <input type="text" data-plantilla-precio inputmode="decimal" placeholder="Precio Gs." class="gastro-template-input" aria-label="Precio">
      </div>
      <p data-plantilla-extras class="ml-8 mt-1 text-xs text-gray-500 dark:text-gray-400"></p>`;
    fila.querySelector('[data-plantilla-nombre]').value = producto.nombre;
    const extras = resumenExtras(producto);
    const extrasNode = fila.querySelector('[data-plantilla-extras]');
    extrasNode.textContent = extras;
    extrasNode.classList.toggle('hidden', !extras);
    return fila;
  };

  const mostrarPlantilla = (clave) => {
    const plantilla = plantillas.find((item) => item.clave === clave);
    if (!plantilla) return;
    plantillaActual = plantilla;
    rubros.querySelectorAll('[data-rubro]').forEach((boton) => {
      boton.classList.toggle('activa', boton.dataset.rubro === clave);
    });
    lista.innerHTML = '';
    plantilla.categorias.forEach((categoria) => {
      const bloque = document.createElement('div');
      bloque.className = 'space-y-2';
      const titulo = document.createElement('h3');
      titulo.className = 'text-sm font-bold text-amber-700 dark:text-amber-300';
      titulo.textContent = categoria.nombre;
      bloque.appendChild(titulo);
      categoria.productos.forEach((producto) => bloque.appendChild(crearFila(categoria, producto)));
      lista.appendChild(bloque);
    });
    paso2.classList.remove('hidden');
    actualizarBoton();
    paso2.scrollIntoView({behavior: 'smooth', block: 'start'});
  };

  const recolectar = () => filas()
    .filter((fila) => fila.querySelector('[data-plantilla-check]').checked)
    .map((fila) => ({
      categoria: fila.dataset.categoria,
      nombre: fila.querySelector('[data-plantilla-nombre]').value.trim(),
      precio: fila.querySelector('[data-plantilla-precio]').value.trim(),
      removibles: fila.dataset.removibles,
      adicionales: fila.dataset.adicionales,
    }));

  const promoElegida = () => {
    const fila = filaPromo();
    if (!fila || promoBox.classList.contains('hidden') || !promoCheck?.checked) return null;
    return {plantilla: plantillaActual.clave, producto: fila.querySelector('[data-plantilla-nombre]').value.trim()};
  };

  const enviar = async () => {
    aplicar.disabled = true;
    aplicarTexto.textContent = 'Cargando...';
    try {
      const response = await fetch('/api/gastronomia/menu-plantillas/aplicar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({productos: recolectar(), promo: promoElegida()}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.mensaje || 'No se pudo cargar la plantilla.');
      let mensaje = `Listo: se cargaron ${data.creados.length} productos.`;
      if (data.omitidos.length) {
        mensaje += ` Ya tenias ${data.omitidos.length} (${data.omitidos.join(', ')}), no se duplicaron.`;
      }
      if (data.promo_creada) {
        mensaje += ` La promo "${data.promo_creada}" quedo pausada en Promociones.`;
      }
      if (typeof scope.gastroMenuReload === 'function') {
        await scope.gastroMenuReload({
          message: mensaje,
          ok: true,
          state: {mainTab: 'menu-cargado', menuTab: 'productos', editProductId: ''},
        });
        return;
      }
      window.location.reload();
    } catch (error) {
      avisar(error.message, false);
      actualizarBoton();
    }
  };

  plantillas.forEach((plantilla) => {
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.dataset.rubro = plantilla.clave;
    boton.className = 'gastro-template-card';
    boton.innerHTML = `<i class="fas ${plantilla.icono}"></i><span></span>`;
    boton.querySelector('span').textContent = plantilla.nombre;
    rubros.appendChild(boton);
  });

  rubros.addEventListener('click', (event) => {
    const boton = event.target.closest('[data-rubro]');
    if (boton) mostrarPlantilla(boton.dataset.rubro);
  });
  lista.addEventListener('input', actualizarBoton);
  lista.addEventListener('change', actualizarBoton);
  aplicar.addEventListener('click', () => {
    enviar().catch((error) => avisar(error.message, false));
  });
}());
