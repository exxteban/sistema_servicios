(function () {
  const number = (value) => Number(value || 0);

  const basePromotionSubtotal = (basePrice, quantity, promotion) => {
    const qty = Math.max(0, Number(quantity || 0));
    const type = promotion?.tipo || '';
    if (type === 'porcentaje') return basePrice * qty * (1 - (number(promotion.valor) / 100));
    if (type === 'monto_fijo') return Math.max(0, basePrice - number(promotion.valor)) * qty;
    if (type === 'precio_promocional') return number(promotion.valor) * qty;
    if (type === 'cantidad') {
      const takes = Math.max(0, Number(promotion.cantidad_lleva || 0));
      const pays = Math.max(0, Number(promotion.cantidad_paga || 0));
      const bonus = takes > pays ? Math.floor(qty / takes) * (takes - pays) : 0;
      return basePrice * (qty - bonus);
    }
    return basePrice * qty;
  };

  const subtotal = (item) => {
    if (item.subtotal_guardado !== undefined && item.subtotal_guardado !== null) {
      return number(item.subtotal_guardado);
    }
    const qty = Math.max(0, Number(item.cantidad || 0));
    const unitPrice = number(item.precio_unitario);
    const basePrice = number(item.precio_base ?? unitPrice);
    const extras = Math.max(0, unitPrice - basePrice);
    return basePromotionSubtotal(basePrice, qty, item.promocion_activa) + (extras * qty);
  };

  window.GastronomiaPromociones = {subtotal};
}());
