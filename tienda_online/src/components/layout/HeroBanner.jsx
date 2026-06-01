import React from 'react'
import { normalizeText } from '../../utils/storeFormatting'
import StoreImage from '../ui/StoreImage'

export default function HeroBanner({ config, themeKey }) {
  const brandColor = config?.color_primario || '#2563eb'
  const coverImage = config?.imagen_portada
  const coverFallbackSources = config?.imagen_portada_fallback_urls || []
  const tituloHero = normalizeText(config?.titulo_hero_tienda) || normalizeText(config?.nombre_tienda) || 'Bienvenido a nuestra tienda'
  const subtituloHero = normalizeText(config?.subtitulo_hero_tienda) || normalizeText(config?.texto_portada) || 'Descubre nuestros productos destacados. Calidad y precio en un solo lugar.'
  const textoBotonHero = normalizeText(config?.texto_boton_hero) || 'Explorar catálogo'
  const beneficios = config?.beneficios_home_items || []

  const fallbackBackground = `linear-gradient(135deg, ${brandColor} 0%, #0f172a 100%)`
  const heroMinHeight = beneficios.length > 0
    ? 'clamp(290px, 34vw, 420px)'
    : 'clamp(240px, 28vw, 360px)'

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
      {coverImage ? (
        <StoreImage
          src={coverImage}
          fallbackSources={coverFallbackSources}
          alt=""
          loading="eager"
          fetchPriority="high"
          decoding="async"
          sizes="100vw"
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : null}
      {coverImage ? (
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
        <h1 className="m-0 mb-3 md:mb-4 text-3xl md:text-5xl lg:text-6xl font-black tracking-tight leading-tight">
          {tituloHero}
        </h1>
        <p className="m-0 mb-6 md:mb-8 text-base md:text-xl text-white/90 leading-relaxed max-w-2xl mx-auto">
          {subtituloHero}
        </p>

        <button
          onClick={() => {
            document.getElementById('catalogo-main')?.scrollIntoView({ behavior: 'smooth' })
          }}
          className="hero-banner-button bg-white border-none py-3 px-6 md:py-4 md:px-8 text-base md:text-lg font-bold cursor-pointer transition-all duration-300 shadow-md hover:shadow-xl hover:-translate-y-1"
          style={{ color: brandColor }}
        >
          {textoBotonHero}
        </button>
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
