import { Link } from 'react-router-dom'
import TrustSignals from '../ui/TrustSignals'
import StoreImage from '../ui/StoreImage'
import { formatGs, isTruthyFlag, normalizeText } from '../../utils/storeFormatting'

export default function CatalogDesktopShowcase({
  children,
  config,
  slug,
  featuredProducts,
  sectionLinks,
  totalProducts,
  offerCount,
  onWhatsAppClick
}) {
  const storeName = normalizeText(config?.nombre_tienda) || 'tu tienda'
  const supportMessage = config?.mensaje_whatsapp_general || config?.mensaje_whatsapp || 'Hola, vengo de la tienda web.'
  const baseStorePath = `/tienda/${slug}`
  const whatsappUrl = buildWhatsAppUrl(config?.telefono_whatsapp, supportMessage)
  const trustItems = buildTrustItems(config, whatsappUrl)
  const promoPanelTitle = normalizeText(config?.titulo_panel_promociones_catalogo) || 'Promos, accesos y recordatorios'
  const trustPanelTitle = normalizeText(config?.titulo_panel_confianza_catalogo) || 'Comprá con respaldo'
  const featuredPanelKicker = normalizeText(config?.kicker_panel_destacados_catalogo) || 'Top esta semana'
  const featuredPanelTitle = normalizeText(config?.titulo_panel_destacados_catalogo) || 'Productos que más llaman la atención'
  const supportCardKicker = normalizeText(config?.kicker_cta_whatsapp_catalogo) || 'Atención directa'
  const supportCardTitle = normalizeText(config?.titulo_cta_whatsapp_catalogo) || 'Te asesoramos por WhatsApp'
  const supportCardText = normalizeText(
    (isTruthyFlag(config?.mostrar_texto_apoyo_whatsapp) && config?.texto_apoyo_whatsapp)
      || (isTruthyFlag(config?.mostrar_recordatorio_whatsapp) && config?.texto_recordatorio_whatsapp)
  )
  const offersHref = `${baseStorePath}#${offerCount > 0 ? 'ofertas' : 'catalogo-main'}`
  const stats = [
    { label: 'Productos visibles', value: totalProducts || 0, href: `${baseStorePath}#catalogo-main` },
    { label: 'Ofertas activas', value: offerCount || 0, href: offersHref },
    { label: 'Canales directos', value: whatsappUrl ? 2 : 1, href: `${baseStorePath}#contacto-tienda` }
  ]

  return (
    <div className="catalog-showcase-layout">
      <aside className="catalog-side-panel">
        <div className="catalog-panel-stack">
          <section className="catalog-panel-card catalog-panel-card-promo">
            <h3 className="catalog-panel-title">{promoPanelTitle}</h3>
            <div className="catalog-panel-stats">
              {stats.map((stat) => (
                <a
                  key={stat.label}
                  href={stat.href}
                  className="catalog-panel-stat"
                >
                  <strong>{stat.value}</strong>
                  <span>{stat.label}</span>
                </a>
              ))}
            </div>
          </section>

          {sectionLinks.length > 0 && (
            <section className="catalog-panel-card">
              <h3 className="catalog-panel-title">Explorá {storeName}</h3>
              <div className="catalog-shortcuts">
                {sectionLinks.map((section) => (
                  <a key={section.id} href={`#${section.id}`} className="catalog-shortcut-link">
                    <span>{section.label}</span>
                    <span aria-hidden="true">→</span>
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>
      </aside>

      <div className="catalog-main-column">
        {children}
      </div>

      <aside className="catalog-side-panel">
        <div className="catalog-panel-stack">
          {trustItems.length > 0 && (
            <section className="catalog-panel-card">
              <h3 className="catalog-panel-title">{trustPanelTitle}</h3>
              <TrustSignals items={trustItems} compact />
            </section>
          )}

          {featuredProducts.length > 0 && (
            <section className="catalog-panel-card">
              <span className="catalog-panel-kicker">{featuredPanelKicker}</span>
              <h3 className="catalog-panel-title">{featuredPanelTitle}</h3>
              <div className="catalog-mini-product-list">
                {featuredProducts.map((producto) => (
                  <Link
                    key={producto.id}
                    to={`/tienda/${slug}/producto/${producto.id}`}
                    className="catalog-mini-product"
                  >
                    <div className="catalog-mini-product-image">
                      {producto.imagenes?.[0]?.url ? (
                        <StoreImage
                          src={producto.imagenes[0].card_url || producto.imagenes[0].url}
                          fallbackSources={producto.imagenes[0].card_fallback_urls || producto.imagenes[0].fallback_urls}
                          alt={producto.nombre}
                          width={producto.imagenes[0].width || undefined}
                          height={producto.imagenes[0].height || undefined}
                          loading="lazy"
                          decoding="async"
                          sizes="64px"
                        />
                      ) : (
                        <span>{producto.nombre?.slice(0, 1) || 'P'}</span>
                      )}
                    </div>
                    <div className="catalog-mini-product-body">
                      <span className="catalog-mini-product-badge">
                        {resolveProductBadge(producto)}
                      </span>
                      <strong>{producto.nombre}</strong>
                      <span>{formatGs(producto.precio)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {whatsappUrl && (
            <a href={whatsappUrl} target="_blank" rel="noreferrer" onClick={onWhatsAppClick} className="catalog-support-card">
              <span className="catalog-panel-kicker">{supportCardKicker}</span>
              <strong>{supportCardTitle}</strong>
              {supportCardText ? <span>{supportCardText}</span> : null}
            </a>
          )}
        </div>
      </aside>
    </div>
  )
}

function buildWhatsAppUrl(phone, message) {
  const digits = String(phone || '').replace(/\D/g, '')
  if (!digits) return ''
  return `https://wa.me/${digits}?text=${encodeURIComponent(message || 'Hola')}`
}

function resolveProductBadge(producto) {
  if (producto?.es_oferta) return 'Oferta'
  if (producto?.es_destacado) return 'Destacado'
  return producto?.categoria || 'Producto'
}

function buildTrustItems(config, whatsappUrl) {
  const configTrustItems = Array.isArray(config?.senales_confianza)
    ? config.senales_confianza
      .map((item, index) => buildTrustItem(
        normalizeText(item?.key) || ['whatsapp', 'envios', 'retiro', 'garantia'][index] || 'whatsapp',
        normalizeText(item?.text),
        whatsappUrl
      ))
      .filter((item) => item.text)
      .slice(0, 4)
    : []

  if (configTrustItems.length > 0) {
    return configTrustItems
  }

  const customItems = Array.isArray(config?.beneficios_home_items)
    ? config.beneficios_home_items
      .map((item, index) => buildTrustItem(
        ['envios', 'garantia', 'retiro', 'whatsapp'][index] || 'whatsapp',
        normalizeText(item),
        whatsappUrl
      ))
      .filter((item) => item.text)
      .slice(0, 4)
    : []

  if (customItems.length > 0) {
    return customItems
  }

  return [
    buildTrustItem('envios', 'Envíos coordinados y respuesta rápida', whatsappUrl),
    buildTrustItem('garantia', 'Asesoramiento antes y después de la compra', whatsappUrl),
    buildTrustItem('retiro', 'Retiro o entrega según tu zona', whatsappUrl),
    buildTrustItem('whatsapp', 'Atención directa por WhatsApp', whatsappUrl)
  ]
}

function buildTrustItem(key, text, whatsappUrl) {
  return {
    key,
    text,
    href: key === 'whatsapp' ? whatsappUrl : '',
    target: key === 'whatsapp' && whatsappUrl ? '_blank' : undefined
  }
}
