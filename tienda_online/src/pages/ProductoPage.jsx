import { useEffect, useState } from 'react'
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
import TrustSignals from '../components/ui/TrustSignals'
import { useMetaPixelPageView, useMetaPixelProductView } from '../hooks/useMetaPixel'
import { trackMetaPixelContact } from '../services/metaPixel'
import { resolveStoreTheme } from '../themes/storeTheme'
import { buildProductPath, isTruthyFlag, normalizeText, parseProductIdFromParam } from '../utils/storeFormatting'
import WebBotWidget from '../features/web-bot/components/WebBotWidget'

export default function ProductoPage() {
  const { slug, productRef } = useParams()
  const navigate = useNavigate()
  const { config, error: configError, retry: retryConfig } = useTiendaConfig(slug)
  const theme = resolveStoreTheme(config?.estilo_tienda)
  const [producto, setProducto] = useState(null)
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
    setError('')
    tiendaApi.getProducto(slug, productId, { signal: controller.signal })
      .then((data) => {
        if (alive) setProducto(data)
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
    const expectedPath = buildProductPath(slug, producto)
    const currentPath = `/tienda/${slug}/producto/${productRef || ''}`
    if (expectedPath !== currentPath) {
      navigate(expectedPath, { replace: true })
    }
  }, [navigate, productRef, producto, slug])

  useEffect(() => {
    if (!producto) return
    const title = config?.nombre_tienda
      ? `${producto.nombre} | ${config.nombre_tienda}`
      : `${producto.nombre} | Tienda Online`
    const tipo = producto.es_servicio ? 'servicio' : 'producto'
    const description = producto.descripcion || config?.texto_portada || `Detalle de ${tipo} disponible para consulta por WhatsApp.`
    applyPageMeta(title, description)
  }, [config, producto])

  const handleRetry = () => {
    retryConfig()
    window.location.reload()
  }

  const metaPixelId = config?.meta_pixel_id || ''

  useMetaPixelPageView(metaPixelId)
  useMetaPixelProductView(metaPixelId, producto)

  const trackProductWhatsAppClick = (item = producto) => {
    if (!metaPixelId) return
    trackMetaPixelContact(metaPixelId, {
      content_name: item?.nombre || 'Producto',
      content_ids: item?.id ? [String(item.id)] : undefined,
      content_type: item?.id ? 'product' : 'product_group',
      currency: 'PYG',
      value: Number(item?.precio) || 0
    })
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
              {config?.nombre_tienda || 'Tienda Online'}
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
  const ctaProducto = config?.texto_cta_producto || 'Comprar por WhatsApp'
  const ctaCatalogo = config?.texto_cta_catalogo || 'Consultar'
  const textoApoyo = isTruthyFlag(config?.mostrar_texto_apoyo_whatsapp) ? normalizeText(config?.texto_apoyo_whatsapp) : ''
  const recordatorio = isTruthyFlag(config?.mostrar_recordatorio_whatsapp) ? normalizeText(config?.texto_recordatorio_whatsapp) : ''
  const beneficios = config?.beneficios_producto_items || []
  const senalesProducto = isTruthyFlag(config?.mostrar_bloque_confianza_producto) ? config?.senales_confianza || [] : []
  const mostrarRelacionados = isTruthyFlag(config?.mostrar_relacionados ?? true) && producto.relacionados?.length > 0
  const whatsappHref = producto.whatsapp_link || (config?.telefono_whatsapp ? `https://wa.me/${String(config.telefono_whatsapp).replace(/\D/g, '')}` : '')

  return (
    <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': config?.color_primario || '#2563eb' }}>
      <header className="glass-header">
        <div className="container" style={{ padding: '16px 0' }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)' }}>
            {config?.nombre_tienda || 'Tienda Online'}
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
            <a
              className={btnClass}
              href={whatsappHref || undefined}
              onClick={() => trackProductWhatsAppClick()}
              target="_blank"
              rel="noreferrer"
              aria-disabled={!whatsappHref}
              style={{ width: '100%', padding: '16px 24px', fontSize: '1.1rem', pointerEvents: whatsappHref ? 'auto' : 'none', opacity: whatsappHref ? 1 : 0.6, ...btnStyle }}
            >
              <svg style={{ width: 24, height: 24 }} fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347zM12 21.054a9.05 9.05 0 0 1-4.609-1.257l-.33-.195-3.424.897.913-3.338-.214-.342a9.04 9.04 0 0 1-1.386-4.765 9.05 9.05 0 1 1 9.05 9.05M12 1.15A10.82 10.82 0 0 0 1.171 11.97 10.82 10.82 0 0 0 2.651 17.3l-1.48 5.41 5.539-1.452h.001c1.636.896 3.475 1.366 5.318 1.366A10.81 10.81 0 1 0 12 1.151z" /></svg>
              {ctaProducto}
            </a>
            {!whatsappHref ? <p className="product-cta-support">Este producto no tiene un enlace de compra disponible en este momento.</p> : null}
            {textoApoyo ? <p className="product-cta-support">{textoApoyo}</p> : null}
            {recordatorio ? <p className="product-cta-reminder">{recordatorio}</p> : null}
          </div>
        </div>
        {mostrarRelacionados && (
          <div style={{ marginTop: 48 }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 20 }}>
              {config?.titulo_relacionados || (producto.es_servicio ? 'Servicios relacionados' : 'Productos relacionados')}
            </h3>
            <div className="grid">
              {producto.relacionados.map((r) => (
                <ProductoCard key={r.id} slug={slug} producto={r} brandColor={config?.color_primario} themeKey={theme.key} ctaText={ctaCatalogo} onWhatsAppClick={trackProductWhatsAppClick} />
              ))}
            </div>
          </div>
        )}
      </main>
      <SocialSideRails config={config} />
      <Footer config={config} themeKey={theme.key} />
      <FloatingWhatsApp
        phone={config?.telefono_whatsapp}
        message={config?.mensaje_whatsapp_general || config?.mensaje_whatsapp || `Hola, me interesa ${producto.nombre}`}
        onClick={() => trackProductWhatsAppClick()}
      />
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
