import { useEffect, useMemo, useState } from 'react'
import { tiendaApi } from '../../services/tiendaApi'
import { buildGastronomiaOrderHref } from '../../utils/gastronomiaOrder'
import { formatGs } from '../../utils/storeFormatting'

const CUSTOMER_STORAGE_PREFIX = 'tienda-online:gastronomia-customer:'

function readStoredCustomer(slug) {
  if (typeof window === 'undefined' || !slug) return null
  try {
    return JSON.parse(window.localStorage.getItem(`${CUSTOMER_STORAGE_PREFIX}${slug}`) || 'null')
  } catch {
    return null
  }
}

function storeCustomer(slug, customer) {
  if (typeof window === 'undefined' || !slug || !customer?.telefono || !customer?.token) return
  window.localStorage.setItem(`${CUSTOMER_STORAGE_PREFIX}${slug}`, JSON.stringify(customer))
}

function formatModifierLabel(modifier) {
  return modifier?.tipo_grupo === 'ingrediente_removible' ? `Sin ${modifier.nombre}` : modifier.nombre
}

export default function GastronomiaOrderPanel({
  slug,
  config,
  items,
  totalItems,
  totalAmount,
  whatsAppHref,
  onIncrement,
  onDecrement,
  onClear,
  onReplaceItems,
  onWhatsAppClick
}) {
  const hasItems = items.length > 0
  const canSendWhatsApp = Boolean(whatsAppHref)
  const deliveryEnabled = config?.tienda_delivery_activo !== false
  const pickupEnabled = config?.tienda_retiro_activo !== false
  const hasOrderMode = deliveryEnabled || pickupEnabled
  const defaultOrderMode = deliveryEnabled ? 'delivery' : 'retiro'
  const storedCustomer = useMemo(() => readStoredCustomer(slug), [slug])
  const [form, setForm] = useState({
    tipo_pedido: defaultOrderMode,
    nombre: storedCustomer?.nombre || '',
    celular: storedCustomer?.telefono || '',
    direccion_entrega: '',
    referencia_entrega: '',
    notas: '',
    recordar_datos: true
  })
  const [profile, setProfile] = useState(null)
  const [status, setStatus] = useState({ type: '', message: '', trackingUrl: '' })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setForm((current) => {
      if (current.tipo_pedido === 'delivery' && deliveryEnabled) return current
      if (current.tipo_pedido === 'retiro' && pickupEnabled) return current
      return { ...current, tipo_pedido: defaultOrderMode }
    })
  }, [defaultOrderMode, deliveryEnabled, pickupEnabled])

  useEffect(() => {
    if (!slug || !storedCustomer?.telefono || !storedCustomer?.token) return
    let alive = true
    tiendaApi.getGastronomiaPerfil(slug, {
      telefono: storedCustomer.telefono,
      token: storedCustomer.token
    }).then((data) => {
      if (!alive || !data?.encontrado) return
      setProfile(data)
      const direccion = data.direcciones?.[0]
      setForm((current) => ({
        ...current,
        nombre: data.cliente?.nombre || current.nombre,
        celular: data.cliente?.celular || current.celular,
        direccion_entrega: direccion?.direccion || current.direccion_entrega,
        referencia_entrega: direccion?.referencia || current.referencia_entrega
      }))
    }).catch(() => {})
    return () => {
      alive = false
    }
  }, [slug, storedCustomer?.telefono, storedCustomer?.token])

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }))
    if (status.type === 'error') setStatus({ type: '', message: '', trackingUrl: '' })
  }

  const repeatLastOrder = () => {
    const lastItems = profile?.ultimo_pedido?.items || []
    if (!lastItems.length || !onReplaceItems) return
    onReplaceItems(lastItems)
    setStatus({ type: 'success', message: 'Cargamos tu ultimo pedido. Podes ajustarlo antes de confirmar.', trackingUrl: '' })
  }

  const submitOrder = async (event) => {
    event.preventDefault()
    if (!hasItems || submitting) return
    if (!hasOrderMode) {
      setStatus({ type: 'error', message: 'Esta tienda todavia no tiene una modalidad de pedido activa.', trackingUrl: '' })
      return
    }
    setSubmitting(true)
    setStatus({ type: '', message: '', trackingUrl: '' })
    try {
      const response = await tiendaApi.postGastronomiaPedido(slug, {
        ...form,
        token_cliente: storedCustomer?.token || '',
        items
      })
      if (form.recordar_datos && response?.token_cliente) {
        storeCustomer(slug, {
          nombre: response.cliente?.nombre || form.nombre,
          telefono: response.cliente?.celular || form.celular,
          token: response.token_cliente
        })
      }
      setProfile(response?.perfil || null)
      setStatus({
        type: 'success',
        message: `Pedido ${response?.pedido?.codigo_entrega || ''} recibido. Te avisaremos cuando avance.`,
        trackingUrl: response?.pedido?.url_seguimiento_publica || response?.pedido?.url_seguimiento || ''
      })
      onClear()
    } catch (error) {
      setStatus({
        type: 'error',
        message: error?.response?.data?.mensaje || 'No pudimos registrar el pedido. Podes enviarlo por WhatsApp.',
        trackingUrl: ''
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <section id="pedido-rapido" className="gastronomia-order-panel" aria-live="polite">
        <div className="gastronomia-order-panel__header">
          <div>
            <p className="gastronomia-order-panel__eyebrow">Pedido rapido</p>
            <h2 className="gastronomia-order-panel__title">Armá tu pedido en segundos</h2>
            <p className="gastronomia-order-panel__description">
              Seleccioná uno o varios productos y confirmá sin crear una cuenta.
            </p>
            {profile?.cliente?.nombre ? (
              <div className="gastronomia-order-panel__welcome">
                Hola {profile.cliente.nombre}. {profile.ultimo_pedido?.items?.length ? 'Podes repetir tu ultimo pedido en un toque.' : 'Ya tenemos tus datos para pedir mas rapido.'}
                {profile.ultimo_pedido?.items?.length ? (
                  <button type="button" onClick={repeatLastOrder}>Repetir ultimo pedido</button>
                ) : null}
              </div>
            ) : null}
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
            </div>
            <form className="gastronomia-order-form" onSubmit={submitOrder}>
              {!hasOrderMode ? (
                <div className="gastronomia-order-panel__notice">
                  Esta tienda todavia no habilito delivery ni retiro. Podes consultar por WhatsApp.
                </div>
              ) : (
                <>
                  <div className="gastronomia-order-form__type">
                    {deliveryEnabled ? <button type="button" className={form.tipo_pedido === 'delivery' ? 'is-active' : ''} onClick={() => updateForm('tipo_pedido', 'delivery')}>Delivery</button> : null}
                    {pickupEnabled ? <button type="button" className={form.tipo_pedido === 'retiro' ? 'is-active' : ''} onClick={() => updateForm('tipo_pedido', 'retiro')}>Retiro</button> : null}
                  </div>
                  <div className="gastronomia-order-form__grid">
                    <label>
                      Nombre
                      <input value={form.nombre} onChange={(event) => updateForm('nombre', event.target.value)} placeholder="Tu nombre" required />
                    </label>
                    <label>
                      WhatsApp
                      <input value={form.celular} onChange={(event) => updateForm('celular', event.target.value)} placeholder="0981 123 456" required />
                    </label>
                    {form.tipo_pedido === 'delivery' ? (
                      <label className="gastronomia-order-form__wide">
                        Dirección
                        <input value={form.direccion_entrega} onChange={(event) => updateForm('direccion_entrega', event.target.value)} placeholder="Barrio, calle, casa" required />
                      </label>
                    ) : null}
                    <label className="gastronomia-order-form__wide">
                      Referencia o nota
                      <input value={form.referencia_entrega} onChange={(event) => updateForm('referencia_entrega', event.target.value)} placeholder="Ej: portón negro, retirar a las 21:00" />
                    </label>
                  </div>
                  <label className="gastronomia-order-form__remember">
                    <input type="checkbox" checked={form.recordar_datos} onChange={(event) => updateForm('recordar_datos', event.target.checked)} />
                    Recordar mis datos para la proxima vez
                  </label>
                  <div className="gastronomia-order-form__actions">
                    <button type="submit" className="btn btn-primary gastronomia-order-panel__submit" disabled={submitting}>
                      {submitting ? 'Confirmando...' : 'Confirmar pedido'}
                    </button>
                    {canSendWhatsApp ? (
                      <a href={buildGastronomiaOrderHref(config, items)} target="_blank" rel="noreferrer" className="gastronomia-order-form__whatsapp" onClick={onWhatsAppClick}>
                        WhatsApp
                      </a>
                    ) : null}
                  </div>
                </>
              )}
            </form>
          </>
        )}
        {status.message ? (
          <div className={`gastronomia-order-status is-${status.type}`}>
            <span>{status.message}</span>
            {status.trackingUrl ? <a href={status.trackingUrl} target="_blank" rel="noreferrer">Ver seguimiento</a> : null}
          </div>
        ) : null}
      </section>

      {hasItems ? (
        <div className="gastronomia-order-floating">
          <div className="gastronomia-order-floating__summary">
            <span>{totalItems} {totalItems === 1 ? 'producto' : 'productos'}</span>
            <strong>{formatGs(totalAmount)}</strong>
          </div>
          <a href="#pedido-rapido" className="btn btn-primary gastronomia-order-floating__submit">Confirmar</a>
        </div>
      ) : null}
    </>
  )
}
