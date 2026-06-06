import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Footer from '../components/layout/Footer'
import FloatingWhatsApp from '../components/layout/FloatingWhatsApp'
import SocialSideRails from '../components/layout/SocialSideRails'
import { useTiendaConfig } from '../hooks/useTiendaConfig'
import { tiendaApi } from '../services/tiendaApi'
import ImageGallery from '../components/ui/ImageGallery'
import ProductoPageSkeleton from '../components/ui/ProductoPageSkeleton'
import ProductPriceBlock from '../components/ui/ProductPriceBlock'
import ProductoCard from '../components/ui/ProductoCard'
import GastronomiaOrderPanel from '../components/ui/GastronomiaOrderPanel'
import TrustSignals from '../components/ui/TrustSignals'
import ProductModifiersSelector, { getModifiersTotal, getSelectedModifiers } from '../components/ui/ProductModifiersSelector'
import { useQuickOrderCart } from '../hooks/useQuickOrderCart'
import { useMetaPixelPageView, useMetaPixelProductView } from '../hooks/useMetaPixel'
import { trackMetaPixelContact } from '../services/metaPixel'
import { resolveStoreTheme } from '../themes/storeTheme'
import { buildGastronomiaOrderHref } from '../utils/gastronomiaOrder'
import { buildProductPath, formatGs, getStoreHeaderTitle, isTruthyFlag, normalizeText, parseProductIdFromParam } from '../utils/storeFormatting'
import WebBotWidget from '../features/web-bot/components/WebBotWidget'

export default function ProductoPage() {
  const { slug, productRef } = useParams()
  const navigate = useNavigate()
  const { config, error: configError, retry: retryConfig } = useTiendaConfig(slug)
  const theme = resolveStoreTheme(config?.estilo_tienda)
  const [producto, setProducto] = useState(null)
  const [modifierSelections, setModifierSelections] = useState({})
  const [orderNotice, setOrderNotice] = useState('')
  const [error, setError] = useState('')
  const productId = parseProductIdFromParam(productRef)

  useEffect(() => {
    if (!productId) {
      setProducto(null)
      setError('No pudimos cargar este producto.')
      return undefined
    }
    let alive = true
    const controller = new AbortController()
    setProducto(null)
    setModifierSelections({})
    setOrderNotice('')
    setError('')
    tiendaApi.getProducto(slug, productId, { signal: controller.signal })
      .then((data) => {
        if (alive) {
          setProducto(data)
          setModifierSelections({})
          setOrderNotice('')
        }
      })
      .catch(() => {
        if (!alive) return
        setProducto(null)
        setError('No pudimos cargar este producto.')
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [slug, productId])

  useEffect(() => {
    if (!producto) return
    if (String(producto.id || '') !== String(productId || '')) return
    const expectedPath = buildProductPath(slug, producto)
    const currentPath = `/tienda/${slug}/producto/${productRef || ''}`
    if (expectedPath !== currentPath) {
      navigate(expectedPath, { replace: true })
    }
  }, [navigate, productId, productRef, producto, slug])

  useEffect(() => {
    if (!producto) return
    const storeName = getStoreHeaderTitle(config)
    const title = `${producto.nombre} | ${storeName}`
    const tipo = producto.es_servicio ? 'servicio' : 'producto'
    const description = producto.descripcion || config?.texto_portada || `Detalle de ${tipo} disponible para consulta por WhatsApp.`
    applyPageMeta(title, description)
  }, [config, producto])

  useEffect(() => {
    if (!productId || typeof window === 'undefined') return
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [productId])

  const handleRetry = () => {
    retryConfig()
    window.location.reload()
  }

  const metaPixelId = config?.meta_pixel_id || ''

  useMetaPixelPageView(metaPixelId)
  useMetaPixelProductView(metaPixelId, producto)

  const selectedModifiers = getSelectedModifiers(producto?.grupos_opciones || [], modifierSelections)
  const modifiersTotal = getModifiersTotal(selectedModifiers)
  const productTotal = Number(producto?.precio || 0) + modifiersTotal
  const quickOrderEnabled = Boolean(config)
  const relatedProducts = useMemo(
    () => (producto?.relacionados || []).filter((item) => String(item?.id || '') !== String(producto?.id || '')),
    [producto]
  )
  const quickOrderProducts = useMemo(
    () => [producto, ...relatedProducts].filter(Boolean),
    [producto, relatedProducts]
  )
  const {
    items: quickOrderItems,
    totalItems: quickOrderCount,
    totalAmount: quickOrderTotal,
    increment: incrementQuickOrder,
    decrement: decrementQuickOrder,
    clearCart: clearQuickOrder,
    getQuantity: getQuickOrderQuantity,
    addCustomizedItem
  } = useQuickOrderCart(quickOrderEnabled ? slug : '', quickOrderProducts)
  const quickOrderWhatsAppHref = useMemo(
    () => buildGastronomiaOrderHref(config, quickOrderItems),
    [config, quickOrderItems]
  )
  const hasProductOptions = Boolean(
    producto?.tiene_opciones || producto?.grupos_opciones?.some((grupo) => grupo?.opciones?.length > 0)
  )
  const currentProductQuantity = producto ? getQuickOrderQuantity(producto.id) : 0

  const trackProductWhatsAppClick = (item = producto) => {
    if (!metaPixelId) return
    trackMetaPixelContact(metaPixelId, {
      content_name: item?.nombre || 'Producto',
      content_ids: item?.id ? [String(item.id)] : undefined,
      content_type: item?.id ? 'product' : 'product_group',
      currency: 'PYG',
      value: item?.id === producto?.id ? productTotal : Number(item?.precio) || 0
    })
  }

  const handleAddToOrder = () => {
    if (!producto) return
    if (hasProductOptions || selectedModifiers.length > 0) {
      addCustomizedItem(producto, selectedModifiers, productTotal, 1)
    } else {
      incrementQuickOrder(producto)
    }
    setOrderNotice('Agregado al pedido. Podés seguir eligiendo productos o enviar todo junto por WhatsApp.')
    trackProductWhatsAppClick(producto)
  }

  if (!producto && !error) return (
    <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': config?.color_primario || '#2563eb' }}>
      <header className="glass-header">
        <div className="container" style={{ padding: '16px 0' }}>
          <div style={{ width: 200, height: 28, background: '#e2e8f0', borderRadius: 4 }} className="skeleton" />
        </div>
      </header>
      <ProductoPageSkeleton />
    </div>
  )

  if (error) {
    return (
      <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': config?.color_primario || '#2563eb' }}>
        <header className="glass-header">
          <div className="container" style={{ padding: '16px 0' }}>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)' }}>
              {getStoreHeaderTitle(config)}
            </h1>
          </div>
        </header>
        <main className="container" style={{ padding: '32px 0 90px' }}>
          <ErrorPanel
            title="No pudimos abrir este producto"
            message={error}
            actionLabel="Recargar página"
            onAction={handleRetry}
          />
        </main>
      </div>
    )
  }

  const btnStyle = config?.color_primario ? { background: config.color_primario, boxShadow: `0 4px 14px 0 color-mix(in srgb, ${config.color_primario} 40%, transparent)` } : {}
  const btnClass = config?.color_primario ? 'btn btn-primary product-btn' : 'btn btn-brand-whatsapp product-btn'
  const ctaCatalogo = config?.texto_cta_catalogo || 'Consultar'
  const textoApoyo = isTruthyFlag(config?.mostrar_texto_apoyo_whatsapp) ? normalizeText(config?.texto_apoyo_whatsapp) : ''
  const recordatorio = isTruthyFlag(config?.mostrar_recordatorio_whatsapp) ? normalizeText(config?.texto_recordatorio_whatsapp) : ''
  const beneficios = config?.beneficios_producto_items || []
  const senalesProducto = isTruthyFlag(config?.mostrar_bloque_confianza_producto) ? config?.senales_confianza || [] : []
  const mostrarRelacionados = isTruthyFlag(config?.mostrar_relacionados ?? true) && relatedProducts.length > 0

  return (
    <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': config?.color_primario || '#2563eb' }}>
      <header className="glass-header">
        <div className="container" style={{ padding: '16px 0' }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)' }}>
            {getStoreHeaderTitle(config)}
          </h1>
        </div>
      </header>
      <main className="container fade-in-up" style={{ padding: '32px 0 90px' }}>
        {configError ? (
          <div style={{ marginBottom: 24 }}>
            <ErrorPanel
              title="Parte de la información de la tienda no se pudo actualizar"
              message={configError}
              actionLabel="Recargar"
              onAction={handleRetry}
              compact
            />
          </div>
        ) : null}
        <Link to={`/tienda/${slug}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--brand-color)', fontWeight: 600, marginBottom: 24, textDecoration: 'none' }}>
          <svg style={{ width: 20, height: 20 }} fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"></path></svg>
          Volver al catálogo
        </Link>
        <div className={`product-page-layout product-page-layout-${theme.key}`}>
          <div className="product-page-gallery">
            <ImageGallery imagenes={producto.imagenes} nombre={producto.nombre} />
          </div>
          <div className="product-page-info">
            {producto.es_servicio ? (
              <span className="product-detail-category">Servicio</span>
            ) : null}
            {producto.categoria ? (
              <span className="product-detail-category">{producto.categoria}</span>
            ) : null}
            <h1 style={{ margin: '0 0 12px 0', fontSize: '2rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.2 }}>{producto.nombre}</h1>
            <ProductPriceBlock producto={producto} />
            <div className="product-page-description">
              <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '1.05rem', whiteSpace: 'pre-line' }}>{producto.descripcion || 'Sin descripción disponible.'}</p>
            </div>
            <ProductModifiersSelector
              grupos={producto.grupos_opciones || []}
              selections={modifierSelections}
              onChange={setModifierSelections}
              basePrice={producto.precio}
            />
            {beneficios.length > 0 && (
              <div className="product-detail-panel">
                <h2 className="product-detail-panel-title">Lo más importante</h2>
                <ul className="product-benefit-list">
                  {beneficios.map((item) => (
                    <li key={item} className="product-benefit-item">{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {senalesProducto.length > 0 && (
              <div className="product-detail-panel">
                <h2 className="product-detail-panel-title">Compra con confianza</h2>
                <TrustSignals items={senalesProducto} />
              </div>
            )}
            <section className="product-detail-order-box" aria-live="polite">
              <div className="product-detail-order-box__top">
                <div>
                  <span>Total de este producto</span>
                  <strong>{formatGs(productTotal)}</strong>
                </div>
                {currentProductQuantity > 0 && !hasProductOptions ? (
                  <div className="gastronomia-qty-stepper">
                    <button type="button" onClick={() => decrementQuickOrder(producto)} aria-label={`Quitar una unidad de ${producto.nombre}`}>
                      -
                    </button>
                    <span>{currentProductQuantity}</span>
                    <button type="button" onClick={() => incrementQuickOrder(producto)} aria-label={`Agregar una unidad de ${producto.nombre}`}>
                      +
                    </button>
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className={btnClass}
                onClick={handleAddToOrder}
                style={{ width: '100%', padding: '16px 24px', fontSize: '1.1rem', ...btnStyle }}
              >
                Agregar al pedido
              </button>
              {orderNotice ? <p className="product-detail-order-box__notice">{orderNotice}</p> : null}
              <Link to={`/tienda/${slug}`} className="product-detail-order-box__continue">
                Seguir eligiendo productos
              </Link>
            </section>
            {textoApoyo ? <p className="product-cta-support">{textoApoyo}</p> : null}
            {recordatorio ? <p className="product-cta-reminder">{recordatorio}</p> : null}
          </div>
        </div>
        {quickOrderEnabled ? (
          <div style={{ marginTop: 32 }}>
            <GastronomiaOrderPanel
              items={quickOrderItems}
              totalItems={quickOrderCount}
              totalAmount={quickOrderTotal}
              whatsAppHref={quickOrderWhatsAppHref}
              onIncrement={incrementQuickOrder}
              onDecrement={decrementQuickOrder}
              onClear={clearQuickOrder}
              onWhatsAppClick={() => trackProductWhatsAppClick()}
            />
          </div>
        ) : null}
        {mostrarRelacionados && (
          <div style={{ marginTop: 48 }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 20 }}>
              {config?.titulo_relacionados || (producto.es_servicio ? 'Servicios relacionados' : 'Productos relacionados')}
            </h3>
            <div className="grid">
              {relatedProducts.map((r) => (
                <ProductoCard
                  key={r.id}
                  slug={slug}
                  producto={r}
                  brandColor={config?.color_primario}
                  themeKey={theme.key}
                  ctaText={ctaCatalogo}
                  onWhatsAppClick={trackProductWhatsAppClick}
                  quickOrderEnabled={quickOrderEnabled}
                  selectedQuantity={quickOrderEnabled ? getQuickOrderQuantity(r.id) : 0}
                  onIncrementQuickOrder={incrementQuickOrder}
                  onDecrementQuickOrder={decrementQuickOrder}
                />
              ))}
            </div>
          </div>
        )}
      </main>
      <SocialSideRails config={config} />
      <Footer config={config} themeKey={theme.key} />
      {!(quickOrderEnabled && quickOrderCount > 0) ? (
        <FloatingWhatsApp
          phone={config?.telefono_whatsapp}
          message={`Hola, me interesa ${producto.nombre}`}
          onClick={() => trackProductWhatsAppClick()}
        />
      ) : null}
      <WebBotWidget slug={slug} />
    </div>
  )
}

function ErrorPanel({ title, message, actionLabel, onAction, compact = false }) {
  return (
    <div className="rounded-3xl border border-rose-200 bg-white px-6 py-6 text-center shadow-sm">
      <h2 style={{ margin: 0, fontSize: compact ? '1.25rem' : '1.75rem', fontWeight: 800, color: 'var(--text-primary)' }}>{title}</h2>
      <p style={{ margin: '12px auto 0', maxWidth: 680, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{message}</p>
      <button
        type="button"
        onClick={onAction}
        className="mt-5 rounded-full border border-slate-300 px-5 py-2.5 font-semibold text-slate-900 transition hover:bg-slate-50"
      >
        {actionLabel}
      </button>
    </div>
  )
}

function applyPageMeta(title, description) {
  document.title = title
  let descriptionMeta = document.querySelector('meta[name="description"]')
  if (!descriptionMeta) {
    descriptionMeta = document.createElement('meta')
    descriptionMeta.setAttribute('name', 'description')
    document.head.appendChild(descriptionMeta)
  }
  descriptionMeta.setAttribute('content', description)
}

