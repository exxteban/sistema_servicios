// Venta por peso en el POS: un producto "kg" pide el peso y la linea vale peso x precio/kg.
// El servidor recalcula y es la fuente de verdad (gastronomia/services/peso_service.py).
(() => {
  const block = document.getElementById('modal-peso');
  const input = document.getElementById('modal-peso-kg');
  const shortcutsEl = document.getElementById('modal-peso-atajos');
  const totalEl = document.getElementById('modal-peso-total');
  const qtyInput = document.getElementById('modal-qty');
  const priceEl = document.getElementById('modal-product-price');
  const PESO_MAX = 50;
  let current = null;
  let format = (value) => String(value);

  const isWeighted = (product) => product?.unidad_venta === 'kg';
  const basePrice = (product) => Number(product?.precio_base ?? product?.precio ?? 0);
  const kgLabel = (peso) => `${Number(peso).toFixed(3).replace('.', ',')} kg`;
  const shortcuts = () => String(block?.dataset.atajos || '')
    .split(',').map((value) => Number(value)).filter((value) => value > 0);

  const parseWeight = (value) => {
    const text = String(value ?? '').trim().replace(',', '.');
    const peso = Number(text);
    if (!text || !Number.isFinite(peso) || peso <= 0) throw new Error('Ingresa el peso en kg (mayor a cero).');
    if (peso > PESO_MAX) throw new Error(`El peso no puede superar ${PESO_MAX} kg.`);
    if (Math.round(peso * 1000) !== peso * 1000) throw new Error('El peso admite hasta 3 decimales (gramos).');
    return peso;
  };

  const lineAmount = (product, peso) => Math.round(basePrice(product) * peso * 100) / 100;

  const refreshTotal = () => {
    if (!current || !totalEl) return;
    try {
      totalEl.textContent = `Total de la pieza: ${format(lineAmount(current, parseWeight(input.value)))} (sin extras)`;
    } catch (error) {
      totalEl.textContent = '';
    }
  };

  const priceLabel = (product, money) => (isWeighted(product) ? `${money(basePrice(product))} / kg` : null);

  // Se llama al abrir el modal de producto (nuevo o editando una linea).
  const prepare = (product, item, money) => {
    format = money;
    current = isWeighted(product) ? product : null;
    block?.classList.toggle('hidden', !current);
    if (qtyInput) {
      qtyInput.disabled = Boolean(current);
      if (current) qtyInput.value = 1;
    }
    if (!current) return;
    if (priceEl) priceEl.textContent = priceLabel(product, money);
    input.value = item?.peso_kg ? String(item.peso_kg).replace('.', ',') : '';
    shortcutsEl.innerHTML = shortcuts().map((peso) => `
      <button type="button" data-peso="${peso}" class="rounded-lg border border-violet-300 px-3 py-2 text-sm font-bold text-violet-700 dark:text-violet-300">${kgLabel(peso)}</button>
    `).join('');
    refreshTotal();
    setTimeout(() => input.focus(), 0);
  };

  // Ajusta la linea armada por pos.js antes de sumarla al carrito. Lanza Error si el peso no es valido.
  const apply = (configuredItem, product) => {
    if (!isWeighted(product)) return configuredItem;
    const peso = parseWeight(input.value);
    const linea = lineAmount(product, peso);
    const extras = Number(configuredItem.precio_unitario || 0) - basePrice(product);
    return Object.assign(configuredItem, {
      cantidad: 1,
      peso_kg: peso,
      precio_base: linea,
      precio_unitario: linea + extras,
      promocion_activa: null,
      nombre: `${product.nombre} · ${kgLabel(peso)}`,
    });
  };

  shortcutsEl?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-peso]');
    if (!button) return;
    input.value = String(button.dataset.peso).replace('.', ',');
    refreshTotal();
  });
  input?.addEventListener('input', refreshTotal);

  window.PosPeso = {prepare, apply, priceLabel};
})();
