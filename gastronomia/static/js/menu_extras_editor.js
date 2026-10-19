// Editor visual de extras: reemplaza los textarea "nombre | precio" por filas.
// El textarea sigue siendo la fuente que se envia al backend; este editor solo
// lo lee y lo reescribe, asi el formato del servidor no cambia.
(function () {
  const SEPARADORES = ['|', '=', ':'];
  const TEXTOS = {
    removible: {
      nombre: 'Ingrediente (ej: cebolla)',
      precio: 'Descuenta Gs. (opcional)',
      agregar: 'Agregar ingrediente',
      vacio: 'Todavia no agregaste ingredientes que el cliente pueda quitar.',
    },
    adicional: {
      nombre: 'Adicional (ej: queso extra)',
      precio: 'Precio Gs.',
      agregar: 'Agregar adicional',
      vacio: 'Todavia no agregaste adicionales con precio.',
    },
  };

  const parsearLinea = (linea) => {
    const texto = linea.trim();
    if (!texto) return null;
    const separador = SEPARADORES.find((sep) => texto.includes(sep));
    if (!separador) return {nombre: texto, precio: ''};
    const corte = texto.lastIndexOf(separador);
    return {nombre: texto.slice(0, corte).trim(), precio: texto.slice(corte + 1).trim()};
  };

  // El backend separa por linea, ";" y (en removibles) ",": se limpian del nombre.
  const limpiarNombre = (nombre, tipo) => {
    const prohibidos = tipo === 'removible' ? /[|=:;,\n]/g : /[|=:;\n]/g;
    return nombre.replace(prohibidos, ' ').replace(/\s+/g, ' ').trim();
  };

  // En removibles la coma separa ingredientes: se descartan los decimales.
  const limpiarPrecio = (precio, tipo) => (tipo === 'removible' ? precio.split(',')[0] : precio)
    .replace(/[^\d.,]/g, '');

  const crearEditor = (textarea) => {
    const tipo = textarea.dataset.extrasEditor === 'removible' ? 'removible' : 'adicional';
    const textos = TEXTOS[tipo];
    const contenedor = document.createElement('div');
    contenedor.className = 'gastro-extras-editor mt-2 space-y-2';
    const lista = document.createElement('div');
    lista.className = 'space-y-2';
    const vacio = document.createElement('p');
    vacio.className = 'gastro-extras-empty';
    vacio.textContent = textos.vacio;
    const agregar = document.createElement('button');
    agregar.type = 'button';
    agregar.className = 'gastro-extras-add';
    agregar.innerHTML = `<i class="fas fa-plus"></i>${textos.agregar}`;
    contenedor.append(lista, vacio, agregar);
    textarea.classList.add('hidden');
    textarea.insertAdjacentElement('afterend', contenedor);

    const filas = () => Array.from(lista.querySelectorAll('[data-extra-row]'));

    const serializar = () => {
      textarea.value = filas()
        .map((fila) => {
          const nombre = limpiarNombre(fila.querySelector('[data-extra-nombre]').value, tipo);
          const precio = limpiarPrecio(fila.querySelector('[data-extra-precio]').value, tipo);
          if (!nombre) return '';
          return precio ? `${nombre} | ${precio}` : nombre;
        })
        .filter(Boolean)
        .join('\n');
      vacio.classList.toggle('hidden', filas().length > 0);
    };

    const agregarFila = ({nombre = '', precio = ''} = {}, enfocar = false) => {
      const fila = document.createElement('div');
      fila.dataset.extraRow = '';
      fila.className = 'gastro-extras-row';
      fila.innerHTML = `
        <input data-extra-nombre type="text" maxlength="140" class="gastro-extras-input">
        <input data-extra-precio type="text" inputmode="decimal" class="gastro-extras-input">
        <button type="button" data-extra-quitar class="gastro-extras-remove" title="Quitar"><i class="fas fa-times"></i></button>`;
      const inputNombre = fila.querySelector('[data-extra-nombre]');
      const inputPrecio = fila.querySelector('[data-extra-precio]');
      inputNombre.placeholder = textos.nombre;
      inputNombre.setAttribute('aria-label', textos.nombre);
      inputNombre.value = nombre;
      inputPrecio.placeholder = textos.precio;
      inputPrecio.setAttribute('aria-label', textos.precio);
      inputPrecio.value = precio;
      lista.appendChild(fila);
      if (enfocar) inputNombre.focus();
      serializar();
    };

    const cargarDesdeTextarea = () => {
      lista.innerHTML = '';
      textarea.value.split('\n').map(parsearLinea).filter(Boolean).forEach((item) => agregarFila(item));
      serializar();
    };

    lista.addEventListener('input', serializar);
    lista.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      agregarFila({}, true);
    });
    lista.addEventListener('click', (event) => {
      const quitar = event.target.closest('[data-extra-quitar]');
      if (!quitar) return;
      quitar.closest('[data-extra-row]')?.remove();
      serializar();
    });
    agregar.addEventListener('click', () => agregarFila({}, true));

    const form = textarea.form;
    form?.addEventListener('reset', () => window.setTimeout(cargarDesdeTextarea, 0));
    form?.addEventListener('gastro:extras-refresh', cargarDesdeTextarea);
    cargarDesdeTextarea();
  };

  document.querySelectorAll('textarea[data-extras-editor]').forEach(crearEditor);
}());
