import { formatGs } from '../../utils/storeFormatting'

export default function ProductPriceBlock({ producto, compact = false }) {
  const precioActual = formatGs(producto?.precio)
  const precioAnterior = producto?.precio_anterior ? formatGs(producto.precio_anterior) : null
  const ahorro = producto?.ahorro ? formatGs(producto.ahorro) : null

  return (
    <div className={`price-block ${compact ? 'price-block-compact' : ''}`}>
      <div className="price-block-main">
        <span className="price-block-current">{precioActual}</span>
        {producto?.descuento_porcentaje ? (
          <span className="price-block-discount">-{producto.descuento_porcentaje}%</span>
        ) : null}
      </div>
      {precioAnterior ? (
        <div className="price-block-secondary">
          <span className="price-block-old">{precioAnterior}</span>
          {ahorro ? <span className="price-block-saving">Ahorrás {ahorro}</span> : null}
        </div>
      ) : null}
    </div>
  )
}
