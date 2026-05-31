export function calculatePromotionSubtotal(unitPrice, quantity, promotion, basePrice = unitPrice) {
  const qty = Math.max(0, Number(quantity || 0))
  const unit = Number(unitPrice || 0)
  if (promotion?.tipo !== 'cantidad') return unit * qty

  const base = Number(basePrice || 0)
  const extras = Math.max(0, unit - base)
  const takes = Math.max(0, Number(promotion.cantidad_lleva || 0))
  const pays = Math.max(0, Number(promotion.cantidad_paga || 0))
  const bonus = takes > pays ? Math.floor(qty / takes) * (takes - pays) : 0
  return (base * (qty - bonus)) + (extras * qty)
}

export function promotionBadge(producto) {
  return producto?.promocion_activa?.etiqueta ||
    (producto?.descuento_porcentaje ? `-${producto.descuento_porcentaje}%` : 'OFERTA')
}
