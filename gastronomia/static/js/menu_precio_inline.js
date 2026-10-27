(function () {
  // Edicion rapida del precio base desde "Menu cargado > Productos" sin abrir el formulario.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const panel = scope.querySelector('[data-menu-tab-panel="productos"]');
  const csrf = scope.querySelector('#csrf-token')?.value || '';
  if (!panel) return;

  const showAlert = (message, ok) => scope.gastroMenuShowAlert?.(message, ok);
  const formatearGs = (valor) => `Gs. ${Math.round(Number(valor) || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`;

  const guardarPrecio = async (productoId, precio) => {
    const response = await fetch(`/api/gastronomia/productos/${productoId}/estado`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      body: JSON.stringify({precio}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.mensaje || data.error || 'No se pudo guardar el precio.');
    return data.producto;
  };

  const editarPrecio = (button) => {
    const input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'decimal';
    input.value = Math.round(Number(button.dataset.price) || 0);
    input.className = 'gastro-inline-price-input';
    input.setAttribute('aria-label', button.getAttribute('aria-label') || 'Precio');
    button.hidden = true;
    button.after(input);
    input.focus();
    input.select();

    let terminado = false;
    const cerrar = () => {
      terminado = true;
      input.remove();
      button.hidden = false;
    };

    const confirmar = async () => {
      if (terminado) return;
      const nuevo = input.value.trim();
      if (!nuevo || nuevo === String(Math.round(Number(button.dataset.price) || 0))) {
        cerrar();
        return;
      }
      terminado = true;
      input.disabled = true;
      try {
        const producto = await guardarPrecio(button.dataset.inlinePrice, nuevo);
        button.dataset.price = producto.precio;
        button.textContent = formatearGs(producto.precio);
        showAlert(`Precio de ${producto.nombre} actualizado a ${formatearGs(producto.precio)}.`, true);
        cerrar();
      } catch (error) {
        showAlert(error.message, false);
        terminado = false;
        input.disabled = false;
        input.focus();
        input.select();
      }
    };

    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        confirmar();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        cerrar();
        button.focus();
      }
    });
    input.addEventListener('blur', confirmar);
  };

  panel.addEventListener('click', (event) => {
    const button = event.target.closest('[data-inline-price]');
    if (button) editarPrecio(button);
  });
}());
