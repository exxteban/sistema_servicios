import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Header from '../components/layout/Header'
import Footer from '../components/layout/Footer'
import FloatingWhatsApp from '../components/layout/FloatingWhatsApp'
import HeroBanner from '../components/layout/HeroBanner'
import CatalogDesktopShowcase from '../components/layout/CatalogDesktopShowcase'
import SocialSideRails from '../components/layout/SocialSideRails'
import ProductoCard from '../components/ui/ProductoCard'
import GastronomiaOrderPanel from '../components/ui/GastronomiaOrderPanel'
import CatalogHighlightsCarousel from '../components/ui/CatalogHighlightsCarousel'
import SkeletonCard from '../components/ui/SkeletonCard'
import CategoryFilter from '../components/ui/CategoryFilter'
import WebBotWidget from '../features/web-bot/components/WebBotWidget'
import { useQuickOrderCart } from '../hooks/useQuickOrderCart'
import { useMetaPixelPageView } from '../hooks/useMetaPixel'
import { useCategorias } from '../hooks/useCategorias'
import { useProductos } from '../hooks/useProductos'
import { useTiendaConfig } from '../hooks/useTiendaConfig'
import { trackMetaPixelContact } from '../services/metaPixel'
import { resolveStoreTheme } from '../themes/storeTheme'
import { getStoreWhatsAppMessage } from '../utils/gastronomiaBudget'
import { buildGastronomiaOrderHref, buildGastronomiaOrderMessage } from '../utils/gastronomiaOrder'
import { buildCategoryPath, isTruthyFlag, normalizeCategoryRef } from '../utils/storeFormatting'

export default function CatalogoPage() {
  const { slug, categoryRef } = useParams()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const { config, loading: loadingConfig, error: configError, retry: retryConfig } = useTiendaConfig(slug)
  const { categorias, loading: loadingCategorias, error: categoriasError, retry: retryCategorias } = useCategorias(slug)
  const theme = resolveStoreTheme(config?.estilo_tienda)
  const normalizedCategoryRef = categoryRef ? normalizeCategoryRef(categoryRef) : ''
  const selectedCategory = useMemo(
    () => (normalizedCategoryRef ? categorias.find((item) => item.slug === normalizedCategoryRef) || null : null),
    [categorias, normalizedCategoryRef]
  )
  const categoriaId = selectedCategory?.id || null
  const productsEnabled = !normalizedCategoryRef || !!selectedCategory || !!categoriasError
  const {
    productos,
    destacados,
    ofertas,
    recomendados,
    imperdibles,
    loading,
    loadingMore,
    error: productosError,
    loadMore,
    hasMore,
    retry: retryProductos
  } = useProductos(slug, query, categoriaId, productsEnabled)
  const quickOrderEnabled = isTruthyFlag(config?.es_gastronomia)
  const quickOrderProducts = useMemo(() => {
    const seenIds = new Set()
    return [productos, destacados, ofertas, recomendados, imperdibles].flatMap((collection) => collection || []).filter((producto) => {
      if (!producto?.id || seenIds.has(producto.id)) return false
      seenIds.add(producto.id)
      return true
    })
  }, [destacados, imperdibles, ofertas, productos, recomendados])
  const {
    items: quickOrderItems,
    totalItems: quickOrderCount,
    totalAmount: quickOrderTotal,
    increment: incrementQuickOrder,
    decrement: decrementQuickOrder,
    clearCart: clearQuickOrder,
    getQuantity: getQuickOrderQuantity
  } = useQuickOrderCart(quickOrderEnabled ? slug : '', quickOrderProducts)
  const skeletons = useMemo(() => Array.from({ length: 8 }), [])
  const ctaCatalogo = config?.texto_cta_catalogo || 'Consultar'
  const mostrarHero = isTruthyFlag(config?.mostrar_hero_tienda ?? true)
  const mostrarDestacados = isTruthyFlag(config?.mostrar_destacados ?? true)
  const mostrarOfertas = isTruthyFlag(config?.mostrar_ofertas ?? true)
  const mostrarRecomendados = isTruthyFlag(config?.mostrar_seccion_recomendados)
  const mostrarImperdibles = isTruthyFlag(config?.mostrar_seccion_imperdibles)
  const metaPixelId = config?.meta_pixel_id || ''
  const tituloDestacados = config?.titulo_destacados || theme.labels.destacados
  const tituloOfertas = config?.titulo_ofertas || theme.labels.ofertas
  const tituloRecomendados = config?.titulo_recomendados || theme.labels.recomendados
  const tituloImperdibles = config?.titulo_imperdibles || theme.labels.imperdibles
  const isHome = !query && !selectedCategory
  const spotlightProducts = useMemo(() => {
    const uniqueProducts = []
    const seenIds = new Set()

    const coleccionesDestacadas = []
    if (mostrarDestacados && destacados?.length) {
      coleccionesDestacadas.push(destacados)
    }
    if (mostrarOfertas && ofertas?.length) {
      coleccionesDestacadas.push(ofertas)
    }

    coleccionesDestacadas.forEach((collection) => {
      collection.forEach((producto) => {
        if (!producto?.id || seenIds.has(producto.id)) return
        seenIds.add(producto.id)
        uniqueProducts.push(producto)
      })
    })

    return uniqueProducts.slice(0, 4)
  }, [destacados, mostrarDestacados, mostrarOfertas, ofertas])
  const tituloCarrusel = useMemo(() => {
    const tieneDestacados = mostrarDestacados && destacados?.length > 0
    const tieneOfertas = mostrarOfertas && ofertas?.length > 0

    if (tieneDestacados && tieneOfertas) {
      return 'Selección especial'
    }
    if (tieneDestacados) {
      return tituloDestacados
    }
    if (tieneOfertas) {
      return tituloOfertas
    }
    return ''
  }, [destacados, mostrarDestacados, mostrarOfertas, ofertas, tituloDestacados, tituloOfertas])
  const quickOrderWhatsAppHref = useMemo(
    () => buildGastronomiaOrderHref(config, quickOrderItems),
    [config, quickOrderItems]
  )
  const floatingWhatsAppMessage = useMemo(() => {
    if (quickOrderEnabled && quickOrderItems.length > 0) {
      return buildGastronomiaOrderMessage(config, quickOrderItems)
    }
    return getStoreWhatsAppMessage(config)
  }, [config, quickOrderEnabled, quickOrderItems])

  useMetaPixelPageView(metaPixelId)

  useEffect(() => {
    const storeName = config?.nombre_tienda || 'Tienda Online'
    const title = selectedCategory
      ? `${selectedCategory.nombre} | ${storeName}`
      : config?.nombre_tienda
        ? `${config.nombre_tienda} | Tienda Online`
        : 'Tienda Online'
    const baseDescription = config?.subtitulo_hero_tienda || config?.texto_portada || config?.texto_footer_descripcion || 'Catálogo online con atención rápida por WhatsApp.'
    const description = selectedCategory
      ? `Explora ${selectedCategory.nombre} en ${storeName}. ${baseDescription}`.slice(0, 200)
      : baseDescription
    applyPageMeta(title, description)
  }, [config, selectedCategory])

  useEffect(() => {
    if (!normalizedCategoryRef || loadingCategorias || categoriasError) return
    if (!selectedCategory) {
      navigate(`/tienda/${slug}`, { replace: true })
      return
    }

    const expectedPath = buildCategoryPath(slug, selectedCategory)
    const currentPath = `/tienda/${slug}/categoria/${categoryRef || ''}`
    if (expectedPath !== currentPath) {
      navigate(expectedPath, { replace: true })
    }
  }, [categoryRef, categoriasError, loadingCategorias, navigate, normalizedCategoryRef, selectedCategory, slug])

  const handleRetry = () => {
    retryConfig()
    retryCategorias()
    retryProductos()
  }

  const trackCatalogWhatsAppClick = (producto = null) => {
    if (!metaPixelId) return
    trackMetaPixelContact(metaPixelId, {
      content_name: producto?.nombre || config?.nombre_tienda || 'Catalogo',
      content_ids: producto?.id ? [String(producto.id)] : undefined,
      content_type: producto?.id ? 'product' : 'catalog',
      currency: 'PYG',
      value: Number(producto?.precio) || 0
    })
  }

  const renderProductCard = (producto) => (
    <ProductoCard
      key={producto.id}
      slug={slug}
      producto={producto}
      brandColor={config?.color_primario}
      themeKey={theme.key}
      ctaText={ctaCatalogo}
      onWhatsAppClick={trackCatalogWhatsAppClick}
      quickOrderEnabled={quickOrderEnabled}
      selectedQuantity={quickOrderEnabled ? getQuickOrderQuantity(producto.id) : 0}
      onIncrementQuickOrder={incrementQuickOrder}
      onDecrementQuickOrder={decrementQuickOrder}
    />
  )

  const renderProductSection = (id, title, items) => (
    <div id={id} className={`catalog-block catalog-block-${theme.key}`}>
      <h2 className="catalog-section-title">{title}</h2>
      <section className={`grid catalog-grid catalog-grid-${theme.key}`}>
        {items.map((p) => renderProductCard(p))}
      </section>
    </div>
  )

  if (!config && loadingConfig) {
    return (
      <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': '#2563eb' }}>
        <Header config={config} query={query} onChange={setQuery} themeKey={theme.key} />
        <main className="container" style={{ padding: '24px 0 84px' }}>
          <div className="rounded-3xl border border-slate-200 bg-white px-6 py-10 text-center text-slate-600 shadow-sm">
            Cargando tienda...
          </div>
        </main>
      </div>
    )
  }

  if (!config && configError) {
    return (
      <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': '#2563eb' }}>
        <Header config={config} query={query} onChange={setQuery} themeKey={theme.key} />
        <main className="container" style={{ padding: '24px 0 84px' }}>
          <ErrorPanel
            title="No pudimos abrir la tienda"
            message={configError}
            actionLabel="Reintentar"
            onAction={handleRetry}
          />
        </main>
      </div>
    )
  }

  const sectionNodes = {
    hero: isHome && mostrarHero ? <HeroBanner config={config} themeKey={theme.key} /> : <div style={{ height: 16 }}></div>,
    heroSpotlight: isHome && spotlightProducts.length > 0 ? (
      <CatalogHighlightsCarousel
        slug={slug}
        title={tituloCarrusel}
        items={spotlightProducts}
      />
    ) : null,
    categories: (
      <div id="catalogo-main" style={{ scrollMarginTop: '100px' }}>
        <CategoryFilter
          slug={slug}
          categorias={categorias}
          loading={loadingCategorias}
          error={categoriasError}
          retry={retryCategorias}
          selectedSlug={selectedCategory?.slug || ''}
          themeKey={theme.key}
        />
        {quickOrderEnabled ? (
          <GastronomiaOrderPanel
            items={quickOrderItems}
            totalItems={quickOrderCount}
            totalAmount={quickOrderTotal}
            whatsAppHref={quickOrderWhatsAppHref}
            onIncrement={incrementQuickOrder}
            onDecrement={decrementQuickOrder}
            onClear={clearQuickOrder}
            onWhatsAppClick={() => trackCatalogWhatsAppClick()}
          />
        ) : null}
      </div>
    ),
    destacados: isHome && mostrarDestacados && !loading && destacados?.length > 0 ? renderProductSection('destacados', tituloDestacados, destacados) : null,
    ofertas: isHome && mostrarOfertas && !loading && ofertas?.length > 0 ? renderProductSection('ofertas', tituloOfertas, ofertas) : null,
    recomendados: isHome && mostrarRecomendados && !loading && recomendados?.length > 0 ? renderProductSection('recomendados', tituloRecomendados, recomendados) : null,
    imperdibles: isHome && mostrarImperdibles && !loading && imperdibles?.length > 0 ? renderProductSection('imperdibles', tituloImperdibles, imperdibles) : null,
    catalog: (
      <div className={`catalog-block catalog-block-${theme.key}`}>
        <div className="catalog-heading-row">
          <h2 className="catalog-section-title">
            {selectedCategory?.nombre || (isHome ? theme.labels.catalogoHome : theme.labels.catalogoResultados)}
          </h2>
        </div>
        {productosError ? (
          <div className="mb-6">
            <ErrorPanel
              title="Hubo un problema al cargar el catálogo"
              message={productosError}
              actionLabel="Volver a intentar"
              onAction={retryProductos}
              compact
            />
          </div>
        ) : null}
        <section className={`grid catalog-grid catalog-grid-${theme.key}`}>
          {loading && skeletons.map((_, i) => <SkeletonCard key={i} />)}
          {!loading && productos.map((p) => renderProductCard(p))}
          {!loading && !productosError && productos.length === 0 && (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '48px 0', color: 'var(--text-secondary)' }}>
              No se encontraron productos.
            </div>
          )}
        </section>
      </div>
    )
  }

  const sectionOrder = isHome
    ? theme.sectionOrderHome.reduce((acc, sectionId) => {
      acc.push(sectionId)
      if (sectionId === 'hero' && spotlightProducts.length > 0) {
        acc.push('heroSpotlight')
      }
      return acc
    }, [])
    : theme.sectionOrderResults
  const sectionLinks = [
    isHome && mostrarDestacados && destacados?.length > 0 ? { id: 'destacados', label: tituloDestacados } : null,
    isHome && mostrarOfertas && ofertas?.length > 0 ? { id: 'ofertas', label: tituloOfertas } : null,
    isHome && mostrarRecomendados && recomendados?.length > 0 ? { id: 'recomendados', label: tituloRecomendados } : null,
    isHome && mostrarImperdibles && imperdibles?.length > 0 ? { id: 'imperdibles', label: tituloImperdibles } : null,
    { id: 'catalogo-main', label: isHome ? theme.labels.catalogoHome : theme.labels.catalogoResultados }
  ].filter(Boolean)

  const pageContent = (
    <>
      {sectionOrder.map((sectionId) => sectionNodes[sectionId]).filter(Boolean)}

      {hasMore && (
        <div style={{ textAlign: 'center', marginTop: '24px' }}>
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            style={{
              background: 'white',
              color: 'var(--brand)',
              border: '2px solid var(--brand)',
              padding: '12px 32px',
              borderRadius: '9999px',
              fontSize: '1rem',
              fontWeight: 600,
              cursor: loadingMore ? 'not-allowed' : 'pointer',
              opacity: loadingMore ? 0.7 : 1,
              transition: 'all 0.2s'
            }}
          >
            {loadingMore ? 'Cargando...' : 'Cargar más productos'}
          </button>
        </div>
      )}
    </>
  )

  return (
    <div className={`theme-wrapper ${theme.wrapperClass}`} style={{ '--brand': config?.color_primario || '#2563eb' }}>
      <Header config={config} query={query} onChange={setQuery} themeKey={theme.key} />
      <main className={`container ${isHome ? 'catalog-page-viewport' : ''}`} style={{ padding: '24px 0 84px' }}>
        {configError ? (
          <div className="mb-6">
            <ErrorPanel
              title="Algunos datos de la tienda no se pudieron actualizar"
              message={configError}
              actionLabel="Reintentar"
              onAction={retryConfig}
              compact
            />
          </div>
        ) : null}
        {isHome ? (
          <CatalogDesktopShowcase
            config={config}
            slug={slug}
            featuredProducts={spotlightProducts}
            sectionLinks={sectionLinks}
            totalProducts={productos.length}
            offerCount={ofertas?.length || 0}
            onWhatsAppClick={() => trackCatalogWhatsAppClick()}
          >
            {pageContent}
          </CatalogDesktopShowcase>
        ) : pageContent}
      </main>
      <SocialSideRails config={config} />
      <Footer config={config} themeKey={theme.key} />
      {!(quickOrderEnabled && quickOrderCount > 0) ? (
        <FloatingWhatsApp
          phone={config?.telefono_whatsapp}
          message={floatingWhatsAppMessage}
          onClick={() => trackCatalogWhatsAppClick()}
        />
      ) : null}
      <WebBotWidget slug={slug} />
    </div>
  )
}

function ErrorPanel({ title, message, actionLabel, onAction, compact = false }) {
  return (
    <div className={`rounded-3xl border border-rose-200 bg-white px-6 ${compact ? 'py-5' : 'py-8'} text-center shadow-sm`}>
      <h2 className={`m-0 font-extrabold text-slate-900 ${compact ? 'text-xl' : 'text-2xl'}`}>{title}</h2>
      <p className="mx-auto mb-0 mt-3 max-w-2xl text-sm leading-6 text-slate-600">{message}</p>
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
