import { Link } from 'react-router-dom'
import { buildCategoryPath, getReadableTextColor, normalizeText } from '../../utils/storeFormatting'

export default function CategoryFilter({ slug, categorias, loading, error, retry, selectedSlug, themeKey, brandColor }) {
  const activeChipStyle = normalizeText(brandColor)
    ? {
        background: brandColor,
        borderColor: brandColor,
        color: getReadableTextColor(brandColor),
        boxShadow: '0 10px 22px rgba(15, 23, 42, 0.14)'
      }
    : undefined

  if (loading) {
    return (
      <div className="flex gap-3 overflow-x-auto pb-4 mb-8 snap-x hide-scrollbar">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-10 w-24 bg-gray-200 rounded-full animate-pulse flex-shrink-0"></div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="mb-8 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
        <span>{error}</span>
        <button
          type="button"
          onClick={retry}
          className="w-fit rounded-full border border-amber-300 px-4 py-2 font-semibold text-amber-900 transition hover:bg-amber-100"
        >
          Reintentar categorías
        </button>
      </div>
    )
  }

  if (!categorias || categorias.length === 0) return null

  return (
    <div className={`category-filter category-filter-${themeKey} flex gap-3 overflow-x-auto pb-4 mb-8 snap-x hide-scrollbar px-1`} role="tablist" aria-label="Filtrar productos por categoría">
      <Link
        to={`/tienda/${slug}`}
        className={`category-chip ${!selectedSlug ? 'category-chip-active' : ''}`}
        aria-current={!selectedSlug ? 'page' : undefined}
        style={!selectedSlug ? activeChipStyle : undefined}
      >
        Todas
      </Link>
      {categorias.map(cat => (
        <Link
          to={buildCategoryPath(slug, cat)}
          key={cat.id}
          className={`category-chip ${selectedSlug === cat.slug ? 'category-chip-active' : ''}`}
          aria-current={selectedSlug === cat.slug ? 'page' : undefined}
          style={selectedSlug === cat.slug ? activeChipStyle : undefined}
        >
          {cat.nombre}
        </Link>
      ))}
    </div>
  )
}
