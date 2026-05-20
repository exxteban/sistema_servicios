export function formatGs(value) {
  return `₲ ${Number(value || 0).toLocaleString('es-PY')}`
}

export function normalizeText(value) {
  if (value === null || value === undefined) return ''
  const clean = String(value).trim()
  if (!clean || clean.toLowerCase() === 'none') return ''
  return clean
}

export function normalizeUrl(value) {
  const clean = normalizeText(value)
  if (!clean) return ''
  if (/^(?:https?:)?\/\//i.test(clean)) return clean
  if (/^(mailto:|tel:)/i.test(clean)) return clean
  return `https://${clean}`
}

export function isTruthyFlag(value) {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value === 1
  const clean = normalizeText(value).toLowerCase()
  if (!clean) return false
  return ['1', 'true', 'on', 'yes', 'si', 'sí'].includes(clean)
}

export function slugifyForUrl(value, fallback = 'producto') {
  const clean = normalizeText(value)
  if (!clean) return fallback
  const withoutAccents = clean.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  const slug = withoutAccents
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
  return slug || fallback
}

export function buildProductPath(slug, producto) {
  const productId = producto?.id
  const productSlug = normalizeText(producto?.slug_producto) || slugifyForUrl(producto?.nombre, String(productId || 'producto'))
  return `/tienda/${slug}/producto/${productId}-${productSlug}`
}

export function buildCategoryPath(slug, categoria) {
  const categorySlug = normalizeText(categoria?.slug) || slugifyForUrl(categoria?.nombre, 'catalogo')
  return `/tienda/${slug}/categoria/${categorySlug}`
}

export function parseProductIdFromParam(value) {
  const match = normalizeText(value).match(/^(\d+)/)
  return match ? match[1] : ''
}

export function normalizeCategoryRef(value) {
  return slugifyForUrl(value, 'catalogo')
}
