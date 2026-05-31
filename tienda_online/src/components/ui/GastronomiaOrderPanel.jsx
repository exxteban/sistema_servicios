import { formatGs } from '../../utils/storeFormatting'

function formatModifierLabel(modifier) {
  return modifier?.tipo_grupo === 'ingrediente_removible' ? `Sin ${modifier.nombre}` : modifier.nombre
}

export default function GastronomiaOrderPanel({
  items,
  totalItems,
  totalAmount,
  whatsAppHref,
  onIncrement,
  onDecrement,
  onClear,
  onWhatsAppClick
}) {
  const hasItems = items.length > 0
  const canSendWhatsApp = Boolean(whatsAppHref)

  return (
    <>
      <section className="gastronomia-order-panel" aria-live="polite">
        <div className="gastronomia-order-panel__header">
          <div>
            <p className="gastronomia-order-panel__eyebrow">Pedido rapido</p>
            <h2 className="gastronomia-order-panel__title">Armá tu pedido y envialo por WhatsApp</h2>
            <p className="gastronomia-order-panel__description">
              Seleccioná uno o varios productos y enviá todo junto en un solo mensaje.
            </p>
          </div>
          {hasItems ? (
            <button type="button" className="gastronomia-order-panel__clear" onClick={onClear}>
              Vaciar
            </button>
          ) : null}
        </div>

        {!hasItems ? (
          <div className="gastronomia-order-panel__empty">
            Tocá "Agregar al pedido" en los productos que quieras incluir.
          </div>
        ) : (
          <>
            <div className="gastronomia-order-panel__items">
              {items.map((item) => (
                <div key={item.key || item.id} className="gastronomia-order-panel__item">
                  <div>
                    <p className="gastronomia-order-panel__item-name">{item.nombre}</p>
                    <p className="gastronomia-order-panel__item-price">
                      {formatGs(item.precio)} c/u
                    </p>
                    {item.modifiers?.length ? (
                      <ul className="gastronomia-order-panel__modifiers">
                        {item.modifiers.map((modifier) => (
                          <li key={`${item.key || item.id}-${modifier.id_opcion}`}>
                            {formatModifierLabel(modifier)}{modifier.tipo_grupo === 'ingrediente_removible' && Number(modifier.cantidad || 0) === 1 ? '' : ` x${modifier.cantidad}`}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  <div className="gastronomia-order-panel__item-actions">
                    <div className="gastronomia-qty-stepper gastronomia-qty-stepper-compact">
                      <button type="button" onClick={() => onDecrement(item)} aria-label={`Quitar una unidad de ${item.nombre}`}>
                        -
                      </button>
                      <span>{item.quantity}</span>
                      <button type="button" onClick={() => onIncrement(item)} aria-label={`Agregar una unidad de ${item.nombre}`}>
                        +
                      </button>
                    </div>
                    <strong className="gastronomia-order-panel__item-subtotal">{formatGs(item.subtotal)}</strong>
                  </div>
                </div>
              ))}
            </div>

            <div className="gastronomia-order-panel__footer">
              <div className="gastronomia-order-panel__totals">
                <span>{totalItems} {totalItems === 1 ? 'producto' : 'productos'}</span>
                <strong>{formatGs(totalAmount)}</strong>
              </div>
              {canSendWhatsApp ? (
                <a
                  href={whatsAppHref}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary gastronomia-order-panel__submit"
                  onClick={onWhatsAppClick}
                >
                  Enviar pedido por WhatsApp
                </a>
              ) : (
                <button type="button" className="btn btn-primary gastronomia-order-panel__submit" disabled>
                  WhatsApp no configurado
                </button>
              )}
            </div>
            {!canSendWhatsApp ? (
              <p className="gastronomia-order-panel__notice">
                La tienda todavía no tiene un número de WhatsApp configurado para recibir este pedido.
              </p>
            ) : null}
          </>
        )}
      </section>

      {hasItems && canSendWhatsApp ? (
        <div className="gastronomia-order-floating">
          <div className="gastronomia-order-floating__summary">
            <span>{totalItems} {totalItems === 1 ? 'producto' : 'productos'}</span>
            <strong>{formatGs(totalAmount)}</strong>
          </div>
          <a
            href={whatsAppHref}
            target="_blank"
            rel="noreferrer"
            className="btn btn-primary gastronomia-order-floating__submit"
            onClick={onWhatsAppClick}
          >
            Pedir por WhatsApp
          </a>
        </div>
      ) : null}
    </>
  )
}
