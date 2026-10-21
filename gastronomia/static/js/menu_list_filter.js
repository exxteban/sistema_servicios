// Busqueda y filtros para listas agrupadas por categoria ([data-list-filter]).
// Cada item declara data-search, data-category y data-flags; los checkbox con
// data-filter-flag-off agregan su flag cuando estan desmarcados.
(function () {
  // En el sistema de pestanas la pagina puede estar cargada dos veces: trabajar solo sobre la copia propia.
  const scope = (document.currentScript && document.currentScript.closest('[data-app-tab-content]')) || document;
  const itemFlags = (item) => {
    const flags = new Set((item.dataset.flags || '').split(' ').filter(Boolean));
    item.querySelectorAll('[data-filter-flag-off]').forEach((input) => {
      if (!input.checked) flags.add(input.dataset.filterFlagOff);
    });
    return flags;
  };

  const updateStatusCounts = (root) => {
    const items = Array.from(root.querySelectorAll('[data-filter-item]'));
    const allFlags = items.map(itemFlags);
    root.querySelectorAll('[data-filter-status]').forEach((button) => {
      const status = button.dataset.filterStatus;
      const count = status ? allFlags.filter((flags) => flags.has(status)).length : items.length;
      const badge = button.querySelector('[data-filter-status-count]');
      if (badge) badge.textContent = count;
    });
  };

  const apply = (root) => {
    const search = (root.querySelector('[data-filter-search]')?.value || '').trim().toLowerCase();
    const category = root.querySelector('[data-filter-category]')?.value || '';
    const status = root.querySelector('[data-filter-status].activa')?.dataset.filterStatus || '';
    const filtering = Boolean(search || category || status);
    let visibleTotal = 0;

    root.querySelectorAll('[data-filter-group]').forEach((group) => {
      let visibleInGroup = 0;
      group.querySelectorAll('[data-filter-item]').forEach((item) => {
        const visible = (!search || (item.dataset.search || '').includes(search))
          && (!category || item.dataset.category === category)
          && (!status || itemFlags(item).has(status));
        item.classList.toggle('hidden', !visible);
        if (visible) visibleInGroup += 1;
      });
      group.classList.toggle('hidden', visibleInGroup === 0);
      const count = group.querySelector('[data-filter-group-count]');
      if (count) count.textContent = visibleInGroup;
      if (filtering && visibleInGroup) group.open = true;
      visibleTotal += visibleInGroup;
    });

    root.querySelector('[data-filter-empty]')?.classList.toggle('hidden', visibleTotal > 0);
    updateStatusCounts(root);
  };

  const bind = (root) => {
    if (root.dataset.listFilterBound) return;
    root.dataset.listFilterBound = '1';
    root.querySelector('[data-filter-search]')?.addEventListener('input', () => apply(root));
    root.querySelector('[data-filter-category]')?.addEventListener('change', () => apply(root));
    root.addEventListener('click', (event) => {
      const statusButton = event.target.closest('[data-filter-status]');
      if (statusButton) {
        root.querySelectorAll('[data-filter-status]').forEach((button) => {
          button.classList.toggle('activa', button === statusButton);
        });
        apply(root);
        return;
      }
      const expandButton = event.target.closest('[data-filter-expand]');
      if (expandButton) {
        root.querySelectorAll('[data-filter-group]').forEach((group) => {
          group.open = expandButton.dataset.filterExpand === '1';
        });
      }
    });
    // Los toggles cambian los contadores, pero no ocultan la fila mientras se edita.
    root.addEventListener('change', (event) => {
      if (event.target.closest('[data-filter-flag-off]')) updateStatusCounts(root);
    });
  };

  const init = (root) => {
    bind(root);
    apply(root);
  };

  window.GastroListFilter = {apply: init};
  scope.querySelectorAll('[data-list-filter]').forEach(init);
}());
