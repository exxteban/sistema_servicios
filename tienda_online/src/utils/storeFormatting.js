export function formatGs(value) {
  return `₲ ${Number(value || 0).toLocaleString('es-PY')}`
}

function parseColorChannel(channel) {
  const value = Number.parseFloat(channel)
  if (Number.isNaN(value)) return null
  return Math.max(0, Math.min(255, value))
}

function parseHexColor(color) {
  const clean = normalizeText(color).replace('#', '')
  if (![3, 6].includes(clean.length) || !/^[0-9a-f]+$/i.test(clean)) return null

  const normalized = clean.length === 3
    ? clean.split('').map((char) => `${char}${char}`).join('')
    : clean

  return {
    r: Number.parseInt(normalized.slice(0, 2), 16),
    g: Number.parseInt(normalized.slice(2, 4), 16),
    b: Number.parseInt(normalized.slice(4, 6), 16)
  }
}

function parseRgbColor(color) {
  const match = normalizeText(color).match(/^rgba?\(([^)]+)\)$/i)
  if (!match) return null

  const [r, g, b] = match[1].split(',').map((part) => parseColorChannel(part.trim()))
  if ([r, g, b].some((channel) => channel === null)) return null

  return { r, g, b }
}

function getRelativeLuminance(channel) {
  const normalized = channel / 255
  return normalized <= 0.03928
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4
}

export function normalizeText(value) {
  if (value === null || value === undefined) return ''
  const clean = String(value).trim()
  if (!clean || ['none', 'false', 'null', 'undefined'].includes(clean.toLowerCase())) return ''
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
  const detailUrl = normalizeText(producto?.url_detalle)
  if (detailUrl && detailUrl.startsWith('/tienda/')) return detailUrl
  if (!productId) return `/tienda/${slug}`
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

export function getReadableTextColor(backgroundColor, lightColor = '#ffffff', darkColor = '#0f172a') {
  const parsedColor = parseHexColor(backgroundColor) || parseRgbColor(backgroundColor)
  if (!parsedColor) return lightColor

  const luminance = (
    0.2126 * getRelativeLuminance(parsedColor.r) +
    0.7152 * getRelativeLuminance(parsedColor.g) +
    0.0722 * getRelativeLuminance(parsedColor.b)
  )

  return luminance > 0.45 ? darkColor : lightColor
}

export function getStoreHeaderTitle(config) {
  return normalizeText(config?.titulo_header_tienda) || normalizeText(config?.nombre_tienda) || 'Tienda Online'
}
