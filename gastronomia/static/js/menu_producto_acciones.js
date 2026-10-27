(function () {
  // Acciones rapidas de la lista "Menu cargado > Productos": crear y duplicar sin salir a buscar el formulario.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const root = scope.querySelector('[data-gastro-menu]');
  const productoForm = scope.querySelector('#producto-form');
  if (!root || !productoForm) return;

  const acciones = () => scope.gastroMenuProducto;
  const showAlert = (message, ok) => scope.gastroMenuShowAlert?.(message, ok);

  const categoriaSugerida = (button) => button.dataset.categoryId
    || scope.querySelector('[data-menu-tab-panel="productos"] [data-filter-category]')?.value
    || '';

  const nuevoProducto = (button) => {
    const api = acciones();
    if (!api) return;
    // Desde el aviso "Editando" se sigue en la categoria del producto que estaba abierto.
    const categoriaId = button.closest?.('#producto-edit-banner')
      ? productoForm.categoria_id.value
      : categoriaSugerida(button);
    api.reset();
    api.abrirFormulario();
    if (categoriaId && categoriaId !== '0' && productoForm.categoria_id.querySelector(`option[value="${categoriaId}"]`)) {
      productoForm.categoria_id.value = categoriaId;
    }
    productoForm.dispatchEvent(new CustomEvent('gastro:extras-refresh'));
    productoForm.scrollIntoView({behavior: 'smooth', block: 'start'});
    productoForm.nombre.focus({preventScroll: true});
  };

  const duplicarProducto = async (button) => {
    const api = acciones();
    if (!api) return;
    api.abrirFormulario();
    await api.cargar(button.dataset.cloneProduct, {clonar: true});
    showAlert('Copia lista: cambia lo necesario y toca "Crear copia" para guardarla.', true);
  };

  // "Guardar y crear otro": la vista se recarga, asi que la categoria viaja por sessionStorage.
  const nuevoPendienteKey = 'gastro-menu-nuevo-en-categoria';
  scope.gastroMenuRecordarNuevo = (categoriaId) => {
    try {
      window.sessionStorage.setItem(nuevoPendienteKey, String(categoriaId || ''));
    } catch (_error) {
      // Sin storage el formulario igual queda vacio, solo sin categoria preseleccionada.
    }
  };

  const retomarNuevoPendiente = () => {
    let categoriaId = null;
    try {
      categoriaId = window.sessionStorage.getItem(nuevoPendienteKey);
      window.sessionStorage.removeItem(nuevoPendienteKey);
    } catch (_error) {
      return;
    }
    if (categoriaId === null) return;
    nuevoProducto({dataset: {categoryId: categoriaId}});
  };

  root.addEventListener('click', (event) => {
    const nuevo = event.target.closest('[data-new-product]');
    if (nuevo) {
      nuevoProducto(nuevo);
      return;
    }
    const clonar = event.target.closest('[data-clone-product]');
    if (clonar) {
      duplicarProducto(clonar).catch((error) => showAlert(error.message, false));
    }
  });

  retomarNuevoPendiente();
}());
