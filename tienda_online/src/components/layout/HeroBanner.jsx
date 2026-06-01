import React, { useEffect, useMemo, useState } from 'react'
import { isTruthyFlag, normalizeText } from '../../utils/storeFormatting'
import StoreImage from '../ui/StoreImage'

export default function HeroBanner({ config, themeKey }) {
  const brandColor = config?.color_primario || '#2563eb'
  const coverImage = config?.imagen_portada
  const tituloHero = normalizeText(config?.titulo_hero_tienda) || normalizeText(config?.nombre_tienda) || 'Bienvenido a nuestra tienda'
  const subtituloHero = normalizeText(config?.subtitulo_hero_tienda) || normalizeText(config?.texto_portada) || 'Descubre nuestros productos destacados. Calidad y precio en un solo lugar.'
  const textoBotonHero = normalizeText(config?.texto_boton_hero) || 'Explorar catálogo'
  const beneficios = config?.beneficios_home_items || []
  const mostrarTituloHero = isTruthyFlag(config?.mostrar_titulo_hero_tienda ?? true)
  const mostrarSubtituloHero = isTruthyFlag(config?.mostrar_subtitulo_hero_tienda ?? true)
  const mostrarBotonHero = isTruthyFlag(config?.mostrar_boton_hero_tienda ?? true)
  const heroVisualTipo = normalizeText(config?.hero_visual_tipo).toLowerCase() === 'carrusel' ? 'carrusel' : 'imagen'
  const heroCarouselItems = useMemo(
    () => (Array.isArray(config?.hero_carrusel_items) ? config.hero_carrusel_items.filter((item) => normalizeText(item?.hero_image_url)) : []),
    [config?.hero_carrusel_items]
  )
  const heroCarouselSpeedMs = Math.max(2000, Math.min(15000, Number(config?.hero_carrusel_velocidad_segundos || 5) * 1000))
  const heroCarouselAnimation = ['fade', 'slide', 'zoom'].includes(normalizeText(config?.hero_carrusel_animacion).toLowerCase())
    ? normalizeText(config?.hero_carrusel_animacion).toLowerCase()
    : 'fade'
  const carouselEnabled = heroVisualTipo === 'carrusel' && heroCarouselItems.length > 0
  const [activeSlideIndex, setActiveSlideIndex] = useState(0)
  const activeHeroSlide = carouselEnabled ? heroCarouselItems[activeSlideIndex] || heroCarouselItems[0] : null
  const coverImageSource = carouselEnabled ? normalizeText(activeHeroSlide?.hero_image_url) : coverImage
  const coverFallbackSources = carouselEnabled ? [] : (config?.imagen_portada_fallback_urls || [])

  const fallbackBackground = `linear-gradient(135deg, ${brandColor} 0%, #0f172a 100%)`
  const heroMinHeight = beneficios.length > 0
    ? 'clamp(290px, 34vw, 420px)'
    : 'clamp(240px, 28vw, 360px)'

  useEffect(() => {
    setActiveSlideIndex(0)
  }, [carouselEnabled, heroCarouselItems.length])

  useEffect(() => {
    if (!carouselEnabled || heroCarouselItems.length < 2) return undefined

    const intervalId = window.setInterval(() => {
      setActiveSlideIndex((current) => (current + 1) % heroCarouselItems.length)
    }, heroCarouselSpeedMs)

    return () => window.clearInterval(intervalId)
  }, [carouselEnabled, heroCarouselItems.length, heroCarouselSpeedMs])

  return (
    <div
      className={`hero-banner hero-banner-${themeKey} relative bg-cover bg-center overflow-hidden mb-8 md:mb-12 text-white flex flex-col shadow-xl animate-fade-in-up`}
      style={{
        background: fallbackBackground,
        justifyContent: 'center',
        minHeight: heroMinHeight,
        padding: 'clamp(1.75rem, 4vw, 4rem) clamp(1rem, 3vw, 3rem)'
      }}
    >
      {carouselEnabled && heroCarouselAnimation === 'slide' ? (
        <div className="absolute inset-0 overflow-hidden">
          <div
            className="flex h-full w-full transition-transform duration-700 ease-out"
            style={{ transform: `translateX(-${activeSlideIndex * 100}%)` }}
          >
            {heroCarouselItems.map((item, index) => (
              <div key={`${item.id || item.nombre || index}-${index}`} className="relative h-full w-full shrink-0 grow-0 basis-full">
                <StoreImage
                  src={item.hero_image_url}
                  fallbackSources={item.hero_image_fallback_urls || []}
                  alt={item.nombre || ''}
                  loading={index === 0 ? 'eager' : 'lazy'}
                  fetchPriority={index === 0 ? 'high' : 'auto'}
                  decoding="async"
                  sizes="100vw"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {carouselEnabled && heroCarouselAnimation !== 'slide' ? (
        <div className="absolute inset-0">
          {heroCarouselItems.map((item, index) => (
            <StoreImage
              key={`${item.id || item.nombre || index}-${index}`}
              src={item.hero_image_url}
              fallbackSources={item.hero_image_fallback_urls || []}
              alt={item.nombre || ''}
              loading={index === 0 ? 'eager' : 'lazy'}
              fetchPriority={index === 0 ? 'high' : 'auto'}
              decoding="async"
              sizes="100vw"
              className="absolute inset-0 h-full w-full object-cover transition-all duration-700 ease-out"
              style={{
                opacity: index === activeSlideIndex ? 1 : 0,
                transform: heroCarouselAnimation === 'zoom'
                  ? `scale(${index === activeSlideIndex ? 1 : 1.08})`
                  : 'scale(1)'
              }}
            />
          ))}
        </div>
      ) : null}
      {coverImageSource && !carouselEnabled ? (
        <StoreImage
          src={coverImageSource}
          fallbackSources={coverFallbackSources}
          alt=""
          loading="eager"
          fetchPriority="high"
          decoding="async"
          sizes="100vw"
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : null}
      {coverImageSource ? (
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(rgba(15, 23, 42, 0.52), rgba(15, 23, 42, 0.82))'
          }}
        ></div>
      ) : null}
      <div
        className="absolute inset-0 opacity-10 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
          backgroundSize: '24px 24px'
        }}
      ></div>

      <div className="hero-banner-content relative z-10 mx-auto w-full" style={{ maxWidth: '760px' }}>
        {mostrarTituloHero ? (
          <h1 className="m-0 mb-3 md:mb-4 text-3xl md:text-5xl lg:text-6xl font-black tracking-tight leading-tight">
            {tituloHero}
          </h1>
        ) : null}
        {mostrarSubtituloHero ? (
          <p className="m-0 mb-6 md:mb-8 text-base md:text-xl text-white/90 leading-relaxed max-w-2xl mx-auto">
            {subtituloHero}
          </p>
        ) : null}
        {mostrarBotonHero ? (
          <button
            onClick={() => {
              document.getElementById('catalogo-main')?.scrollIntoView({ behavior: 'smooth' })
            }}
            className="hero-banner-button bg-white border-none py-3 px-6 md:py-4 md:px-8 text-base md:text-lg font-bold cursor-pointer transition-all duration-300 shadow-md hover:shadow-xl hover:-translate-y-1"
            style={{ color: brandColor }}
          >
            {textoBotonHero}
          </button>
        ) : null}
        {carouselEnabled && activeHeroSlide ? (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-3 text-sm">
            <a
              href={activeHeroSlide.url_detalle}
              className="rounded-full border border-white/30 bg-white/15 px-4 py-2 font-semibold text-white no-underline backdrop-blur-sm transition hover:bg-white/25"
            >
              {activeHeroSlide.nombre}
            </a>
            {heroCarouselItems.length > 1 ? (
              <div className="flex items-center gap-2">
                {heroCarouselItems.map((item, index) => (
                  <button
                    key={`dot-${item.id || index}`}
                    type="button"
                    onClick={() => setActiveSlideIndex(index)}
                    className="h-2.5 w-2.5 rounded-full border-none p-0"
                    style={{ background: index === activeSlideIndex ? '#ffffff' : 'rgba(255, 255, 255, 0.4)' }}
                    aria-label={`Ver slide ${index + 1} del carrusel principal`}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {beneficios.length > 0 && (
          <div className="mt-8 grid gap-3 md:grid-cols-3">
            {beneficios.map((beneficio) => (
              <div
                key={beneficio}
                className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-sm font-semibold text-white md:backdrop-blur-sm"
              >
                {beneficio}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
