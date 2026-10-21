// Render de un grupo de modificadores en el modal de producto del POS (extraido de pos.js).
(() => {
  const render = (group, selectedOptions, {escapeHtml, money, formatModifierName}) => {
    const isRemovable = group.tipo === 'ingrediente_removible';
    const inputType = isRemovable ? 'checkbox' : (group.max_selecciones === 1 ? 'radio' : 'checkbox');
    const helper = isRemovable ? 'Marca los ingredientes que NO debe llevar.' : 'Selecciona las opciones para este item.';
    return `
      <section class="pos-modifier-group rounded-lg border border-gray-200 p-4 dark:border-gray-700">
        <div class="pos-modifier-group-head flex items-center justify-between gap-3">
          <h3 class="font-bold text-gray-900 dark:text-white">${escapeHtml(group.nombre)}</h3>
          <span class="pos-modifier-group-limit text-xs font-semibold text-gray-500">${group.min_selecciones || 0}-${group.max_selecciones || 0}</span>
        </div>
        <p class="pos-modifier-group-helper mt-1 text-xs font-semibold text-gray-500 dark:text-gray-400">${helper}</p>
        <div class="pos-modifier-group-options mt-3 grid gap-2 sm:grid-cols-2">
          ${(group.opciones || []).map((option) => `
            <label class="pos-modifier-option rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold dark:border-gray-700 dark:text-gray-100">
              <span class="pos-modifier-option-copy">
                <input type="${inputType}" name="group-${group.id_grupo}" value="${option.id_opcion}" class="pos-modifier-option-input" ${selectedOptions.includes(Number(option.id_opcion)) ? 'checked' : ''}>
                <span class="pos-modifier-option-name">${escapeHtml(formatModifierName({...option, tipo_grupo: group.tipo}))}</span>
              </span>
              <span class="pos-modifier-option-price">${option.precio_delta > 0 ? `+${money(option.precio_delta)}` : option.precio_delta < 0 ? `-${money(Math.abs(option.precio_delta))}` : 'Sin costo'}</span>
            </label>
          `).join('')}
        </div>
      </section>
    `;
  };

  window.PosModifierGroups = {render};
})();
