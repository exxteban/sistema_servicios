(function () {
  const form = document.getElementById('producto-form');
  if (!form) return;

  const buttons = Array.from(form.querySelectorAll('[data-producto-subtab]'));
  const panels = Array.from(form.querySelectorAll('[data-producto-subtab-panel]'));
  const defaultTab = 'datos';

  function switchSubtab(tabId) {
    buttons.forEach((button) => {
      const active = button.dataset.productoSubtab === tabId;
      button.classList.toggle('activa', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.productoSubtabPanel !== tabId);
    });
  }

  form.querySelector('.gastro-producto-subtabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-producto-subtab]');
    if (button) switchSubtab(button.dataset.productoSubtab);
  });

  // Un campo requerido en el tab oculto no puede recibir foco: mostrar su tab.
  form.addEventListener('invalid', (event) => {
    const panel = event.target.closest('[data-producto-subtab-panel]');
    if (panel?.classList.contains('hidden')) switchSubtab(panel.dataset.productoSubtabPanel);
  }, true);

  // Nuevo producto o edicion: volver siempre al primer tab.
  form.addEventListener('reset', () => switchSubtab(defaultTab));
})();
