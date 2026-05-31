import { Link } from 'react-router-dom'
import ProductPriceBlock from './ProductPriceBlock'
import { promotionBadge } from '../../utils/promotions'
import StoreImage from './StoreImage'
import { buildProductPath } from '../../utils/storeFormatting'

export default function ProductoCard({
  slug,
  producto,
  brandColor,
  themeKey,
  ctaText = 'Consultar',
  onWhatsAppClick,
  quickOrderEnabled = false,
  selectedQuantity = 0,
  onIncrementQuickOrder,
  onDecrementQuickOrder
}) {
  const btnStyle = brandColor ? { background: brandColor, borderColor: brandColor } : {}
  const btnClass = brandColor ? 'btn btn-primary product-btn' : 'btn btn-brand-whatsapp product-btn'
  const productPath = buildProductPath(slug, producto)
  const requiresCustomization = quickOrderEnabled && Boolean(
    producto.tiene_opciones || producto.grupos_opciones?.some((grupo) => grupo?.opciones?.length > 0)
  )

  return (
    <article className={`card product-card product-card-${themeKey} group`}>
      <Link to={productPath} className="card-image-wrap relative block">
        {producto.imagenes?.[0]?.url ? (
          <StoreImage
            src={producto.imagenes[0].card_url || producto.imagenes[0].url}
            fallbackSources={producto.imagenes[0].card_fallback_urls || producto.imagenes[0].fallback_urls}
            alt={producto.nombre}
            width={producto.imagenes[0].width || undefined}
            height={producto.imagenes[0].height || undefined}
            loading="lazy"
            decoding="async"
            sizes="(max-width: 640px) 92vw, (max-width: 1200px) 46vw, 280px"
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg className="w-12 h-12 text-gray-300" fill="none" strokeWidth="1.5" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5z"></path>
            </svg>
          </div>
        )}
        {producto.es_oferta && (
          <span className="product-badge absolute top-3 left-3 text-white text-xs font-bold px-2 py-1 rounded-full z-10">
            {promotionBadge(producto)}
          </span>
        )}
      </Link>
      <div className="card-content flex flex-col flex-grow">
        {producto.es_servicio ? (
          <span className="product-card-category">Servicio</span>
        ) : null}
        {producto.categoria ? (
          <span className="product-card-category">
            {producto.categoria}
          </span>
        ) : null}
        <h3 className="product-title mb-1 line-clamp-2 leading-tight">
          {producto.nombre}
        </h3>

        <div className="product-action">
          <ProductPriceBlock producto={producto} compact />

          {quickOrderEnabled ? (
            <div className="product-quick-order">
              {requiresCustomization ? (
                <Link
                  to={productPath}
                  className={`${btnClass} product-btn`}
                  style={{ width: '100%', ...btnStyle }}
                >
                  Personalizar pedido
                </Link>
              ) : selectedQuantity > 0 ? (
                <div className="gastronomia-qty-stepper">
                  <button type="button" onClick={() => onDecrementQuickOrder?.(producto)} aria-label={`Quitar una unidad de ${producto.nombre}`}>
                    -
                  </button>
                  <span>{selectedQuantity}</span>
                  <button type="button" onClick={() => onIncrementQuickOrder?.(producto)} aria-label={`Agregar una unidad de ${producto.nombre}`}>
                    +
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className={`${btnClass} product-btn`}
                  style={{ width: '100%', ...btnStyle }}
                  onClick={() => onIncrementQuickOrder?.(producto)}
                >
                  Agregar al pedido
                </button>
              )}

              <p className="product-quick-order__hint">
                {requiresCustomization
                  ? 'Este producto tiene opciones. Elegí el detalle antes de pedir.'
                  : selectedQuantity > 0
                    ? 'Incluido en tu pedido.'
                    : 'Podés sumar varios y enviar todo junto.'}
              </p>
              {!requiresCustomization ? (
                <Link to={productPath} className="product-quick-order__link">
                  Ver detalle
                </Link>
              ) : null}
            </div>
          ) : (
            <a
              className={btnClass}
              href={producto.whatsapp_link || '#'}
              onClick={() => onWhatsAppClick?.(producto)}
              target="_blank"
              rel="noreferrer"
              style={{ width: '100%', ...btnStyle }}
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347zM12 21.054a9.05 9.05 0 0 1-4.609-1.257l-.33-.195-3.424.897.913-3.338-.214-.342a9.04 9.04 0 0 1-1.386-4.765 9.05 9.05 0 1 1 9.05 9.05M12 1.15A10.82 10.82 0 0 0 1.171 11.97 10.82 10.82 0 0 0 2.651 17.3l-1.48 5.41 5.539-1.452h.001c1.636.896 3.475 1.366 5.318 1.366A10.81 10.81 0 1 0 12 1.151z" />
              </svg>
              {ctaText}
            </a>
          )}
        </div>
      </div>
    </article>
  )
}
