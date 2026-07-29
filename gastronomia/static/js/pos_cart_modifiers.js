(function () {
  const visualFor = (modifier) => {
    if (modifier?.tipo_grupo === 'ingrediente_removible') {
      return {className: 'pos-cart-modifier--remove', icon: 'fa-minus'};
    }
    if (modifier?.tipo_grupo === 'extra') {
      return {className: 'pos-cart-modifier--extra', icon: 'fa-plus'};
    }
    return {className: 'pos-cart-modifier--choice', icon: 'fa-check'};
  };

  const render = (selections = [], formatName, escapeHtml) => {
    if (!selections.length) return '';
    const items = selections.map((modifier) => {
      const visual = visualFor(modifier);
      return `
        <li class="pos-cart-modifier ${visual.className}">
          <i class="fas ${visual.icon}" aria-hidden="true"></i>
          <span>${escapeHtml(formatName(modifier))}</span>
        </li>
      `;
    }).join('');
    return `<ul class="pos-cart-modifiers" aria-label="Cambios del producto">${items}</ul>`;
  };

  window.GastronomiaCartModifiers = {render};
}());
