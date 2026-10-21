(function () {
  // En el sistema de pestanas la pagina puede estar cargada dos veces: trabajar solo sobre la copia propia.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const root = scope.querySelector('[data-gastro-stock]');
  if (!root) return;

  const buttons = Array.from(root.querySelectorAll('[data-stock-subtab]'));
  const panels = Array.from(root.querySelectorAll('[data-stock-subtab-panel]'));

  function switchSubtab(tabId) {
    buttons.forEach((button) => {
      const active = button.dataset.stockSubtab === tabId;
      button.classList.toggle('activa', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.stockSubtabPanel !== tabId);
    });
  }

  root.querySelector('.gastro-stock-subtabs')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-stock-subtab]');
    if (button) switchSubtab(button.dataset.stockSubtab);
  });
})();
