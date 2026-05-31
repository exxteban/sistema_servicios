import { useMemo } from 'react'
import { formatGs } from '../../utils/storeFormatting'
import StoreImage from './StoreImage'

export default function ProductModifiersSelector({ grupos = [], selections, onChange, basePrice = 0 }) {
  const visibles = useMemo(() => grupos.filter((grupo) => grupo?.opciones?.length), [grupos])
  if (!visibles.length) return null

  const totalExtras = visibles.reduce((total, grupo) => (
    total + grupo.opciones.reduce((subtotal, opcion) => {
      const cantidad = selections[opcion.id_opcion] || 0
      return subtotal + cantidad * Number(opcion.precio_delta || 0)
    }, 0)
  ), 0)

  const setQuantity = (grupo, opcion, nextQuantity) => {
    const maxGrupo = Math.max(1, Number(grupo.max_selecciones || 1))
    const currentGroupCount = grupo.opciones.reduce((total, item) => {
      if (item.id_opcion === opcion.id_opcion) return total
      return total + Number(selections[item.id_opcion] || 0)
    }, 0)
    const maxForOption = Math.max(0, maxGrupo - currentGroupCount)
    const quantity = Math.min(maxForOption, Math.max(0, Number(nextQuantity || 0)))
    onChange({
      ...selections,
      [opcion.id_opcion]: quantity
    })
  }

  return (
    <section className="product-modifiers-panel" aria-label="Extras del producto">
      <div className="product-modifiers-header">
        <div>
          <h2>Personalizar</h2>
          <p>Elegí extras o cambios antes de consultar por WhatsApp.</p>
        </div>
        <div className="product-modifiers-total">
          <span>Total</span>
          <strong>{formatGs(Number(basePrice || 0) + totalExtras)}</strong>
        </div>
      </div>
      <div className="product-modifier-groups">
        {visibles.map((grupo) => (
          <div className="product-modifier-group" key={grupo.id_grupo}>
            <div className="product-modifier-group-title">
              <h3>{grupo.nombre}</h3>
              <span>Máx. {grupo.max_selecciones || 1}</span>
            </div>
            <div className="product-modifier-options">
              {grupo.opciones.map((opcion) => {
                const quantity = Number(selections[opcion.id_opcion] || 0)
                return (
                  <article className={`product-modifier-option ${quantity > 0 ? 'is-selected' : ''}`} key={opcion.id_opcion}>
                    <div className="product-modifier-image">
                      <StoreImage src={opcion.imagen_url} fallbackSources={opcion.fallback_urls} alt={opcion.nombre} />
                    </div>
                    <div className="product-modifier-copy">
                      <strong>{opcion.nombre}</strong>
                      <span>{Number(opcion.precio_delta || 0) > 0 ? `+ ${formatGs(opcion.precio_delta)}` : 'Sin costo'}</span>
                    </div>
                    <div className="product-modifier-stepper" aria-label={`Cantidad de ${opcion.nombre}`}>
                      <button type="button" onClick={() => setQuantity(grupo, opcion, quantity - 1)} disabled={quantity <= 0}>-</button>
                      <span>{quantity}</span>
                      <button type="button" onClick={() => setQuantity(grupo, opcion, quantity + 1)}>+</button>
                    </div>
                  </article>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export function getSelectedModifiers(grupos = [], selections = {}) {
  return grupos.flatMap((grupo) => (grupo.opciones || [])
    .map((opcion) => ({
      ...opcion,
      cantidad: Number(selections[opcion.id_opcion] || 0),
      nombre_grupo: grupo.nombre,
      tipo_grupo: grupo.tipo || ''
    }))
    .filter((opcion) => opcion.cantidad > 0))
}

export function getModifiersTotal(selected = []) {
  return selected.reduce((total, opcion) => total + opcion.cantidad * Number(opcion.precio_delta || 0), 0)
}
