import { useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { formatGs } from '../../utils/storeFormatting'
import StoreImage from './StoreImage'

export default function CatalogHighlightsCarousel({
  slug,
  title,
  subtitle,
  items
}) {
  const trackRef = useRef(null)
  const autoplayPausedRef = useRef(false)
  const autoplayResumeTimeoutRef = useRef(null)
  const carouselLabel = title || 'Selección de productos'

  if (!items?.length) return null

  const scrollTrack = useCallback((direction, behavior = 'smooth') => {
    const node = trackRef.current
    if (!node) return

    const distance = Math.min(node.clientWidth * 0.9, 720)
    const maxScrollLeft = Math.max(0, node.scrollWidth - node.clientWidth)
    const nextScrollLeft = node.scrollLeft + direction * distance

    if (direction > 0 && nextScrollLeft >= maxScrollLeft - 24) {
      node.scrollTo({ left: 0, behavior })
      return
    }

    if (direction < 0 && node.scrollLeft <= 24) {
      node.scrollTo({ left: maxScrollLeft, behavior })
      return
    }

    node.scrollBy({ left: direction * distance, behavior })
  }, [])

  const pauseAutoplay = useCallback(() => {
    autoplayPausedRef.current = true
    if (autoplayResumeTimeoutRef.current) {
      window.clearTimeout(autoplayResumeTimeoutRef.current)
      autoplayResumeTimeoutRef.current = null
    }
  }, [])

  const resumeAutoplay = useCallback((delay = 0) => {
    if (autoplayResumeTimeoutRef.current) {
      window.clearTimeout(autoplayResumeTimeoutRef.current)
    }

    autoplayResumeTimeoutRef.current = window.setTimeout(() => {
      autoplayPausedRef.current = false
      autoplayResumeTimeoutRef.current = null
    }, delay)
  }, [])

  useEffect(() => {
    const node = trackRef.current
    if (!node || items.length < 2) return undefined

    const reduceMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const touchOrSmallQuery = window.matchMedia('(max-width: 767px), (pointer: coarse)')
    if (reduceMotionQuery.matches || touchOrSmallQuery.matches) return undefined

    const intervalId = window.setInterval(() => {
      if (autoplayPausedRef.current) return

      const hasOverflow = node.scrollWidth - node.clientWidth > 24
      if (!hasOverflow) return

      scrollTrack(1)
    }, 4500)

    return () => {
      window.clearInterval(intervalId)
      if (autoplayResumeTimeoutRef.current) {
        window.clearTimeout(autoplayResumeTimeoutRef.current)
        autoplayResumeTimeoutRef.current = null
      }
    }
  }, [items.length, scrollTrack])

  return (
    <section className="catalog-highlights-block" aria-label={carouselLabel}>
      <div className="catalog-highlights-header">
        <div>
          <h2 className="catalog-section-title">{carouselLabel}</h2>
          {subtitle ? <p className="catalog-highlights-subtitle">{subtitle}</p> : null}
        </div>
        <div className="catalog-highlights-controls">
          <button
            type="button"
            className="catalog-highlights-control"
            onClick={() => {
              pauseAutoplay()
              scrollTrack(-1)
              resumeAutoplay(7000)
            }}
            aria-label={`Ver elementos anteriores de ${carouselLabel}`}
          >
            ←
          </button>
          <button
            type="button"
            className="catalog-highlights-control"
            onClick={() => {
              pauseAutoplay()
              scrollTrack(1)
              resumeAutoplay(7000)
            }}
            aria-label={`Ver más elementos de ${carouselLabel}`}
          >
            →
          </button>
        </div>
      </div>

      <div
        ref={trackRef}
        className="catalog-highlights-track"
        onMouseEnter={pauseAutoplay}
        onMouseLeave={() => resumeAutoplay(1200)}
        onFocusCapture={pauseAutoplay}
        onBlurCapture={() => resumeAutoplay(1200)}
      >
        {items.map((producto) => (
          <Link key={producto.id} to={`/tienda/${slug}/producto/${producto.id}`} className="catalog-highlight-card">
            <div className="catalog-highlight-media">
              {producto.imagenes?.[0]?.url ? (
                <StoreImage
                  src={producto.imagenes[0].card_url || producto.imagenes[0].url}
                  fallbackSources={producto.imagenes[0].card_fallback_urls || producto.imagenes[0].fallback_urls}
                  alt={producto.nombre}
                  width={producto.imagenes[0].width || undefined}
                  height={producto.imagenes[0].height || undefined}
                  loading="lazy"
                  decoding="async"
                  sizes="(max-width: 767px) 86vw, 320px"
                />
              ) : (
                <span>{producto.nombre?.slice(0, 1) || 'P'}</span>
              )}
              {producto.es_oferta ? (
                <span className="catalog-highlight-badge">
                  {producto.descuento_porcentaje ? `-${producto.descuento_porcentaje}%` : 'Oferta'}
                </span>
              ) : null}
            </div>
            <div className="catalog-highlight-body">
              <span className="catalog-mini-product-badge">
                {resolveProductBadge(producto)}
              </span>
              <strong>{producto.nombre}</strong>
              {producto.descripcion_corta ? <p>{producto.descripcion_corta}</p> : null}
              <div className="catalog-highlight-footer">
                <span>{formatGs(producto.precio)}</span>
                <span>Ver producto</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}

function resolveProductBadge(producto) {
  if (producto?.es_oferta) return 'Oferta'
  if (producto?.es_destacado) return 'Destacado'
  return producto?.categoria || 'Producto'
}
