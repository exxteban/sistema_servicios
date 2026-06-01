import axios from 'axios'

const configuredBaseURL = (import.meta.env.VITE_API_BASE_URL || '').trim()
const isLocalhostBaseURL = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(configuredBaseURL)
const baseURL = configuredBaseURL && !isLocalhostBaseURL ? configuredBaseURL : ''
const devBackendOrigin = (import.meta.env.VITE_DEV_BACKEND_ORIGIN || 'http://127.0.0.1:5003').trim()

const api = axios.create({ baseURL })
const bootstrapCache = new Map()
const bootstrapPromises = new Map()

function uniqueValues(values) {
  return Array.from(new Set(values.filter(Boolean)))
}

function getAssetOrigin() {
  if (baseURL) {
    return new URL(baseURL, window.location.origin).origin
  }

  if (import.meta.env.DEV) {
    return new URL(devBackendOrigin).origin
  }

  return window.location.origin
}

function localMediaPath(value) {
  const normalizedValue = typeof value === 'string' ? value.trim().replace(/\\/g, '/') : ''
  if (!normalizedValue) return ''

  const lowerNormalized = normalizedValue.toLowerCase()
  const mediaSegment = '/api/tienda/media/'
  const mediaIndex = lowerNormalized.indexOf(mediaSegment)
  if (mediaIndex >= 0) {
    return `/api/tienda/media/${normalizedValue.slice(mediaIndex + mediaSegment.length).replace(/^\/+/, '')}`
  }

  const staticUploadSegment = 'static/tienda_uploads/'
  const staticUploadIndex = lowerNormalized.indexOf(staticUploadSegment)
  if (staticUploadIndex >= 0) {
    return `/api/tienda/media/${normalizedValue.slice(staticUploadIndex + staticUploadSegment.length).replace(/^\/+/, '')}`
  }

  const uploadSegment = 'tienda_uploads/'
  const uploadIndex = lowerNormalized.indexOf(uploadSegment)
  if (uploadIndex >= 0) {
    return `/api/tienda/media/${normalizedValue.slice(uploadIndex + uploadSegment.length).replace(/^\/+/, '')}`
  }

  return ''
}

function resolveMediaUrl(value) {
  const rawValue = typeof value === 'string' ? value.trim() : ''
  if (!rawValue) return rawValue
  const normalizedValue = rawValue.replace(/\\/g, '/')
  const localPath = localMediaPath(normalizedValue)
  if (localPath) {
    return import.meta.env.DEV ? new URL(localPath, `${getAssetOrigin()}/`).toString() : localPath
  }
  if (/^(?:[a-z]+:)?\/\//i.test(normalizedValue) || /^(data:|blob:|mailto:|tel:)/i.test(normalizedValue)) {
    return normalizedValue
  }
  const staticMatch = normalizedValue.match(/(?:^|\/)(static\/.*)$/i)
  if (staticMatch?.[1]) {
    return new URL(`/${staticMatch[1].replace(/^\/+/, '')}`, `${getAssetOrigin()}/`).toString()
  }
  const uploadSegment = 'tienda_uploads/'
  const lowerNormalized = normalizedValue.toLowerCase()
  const uploadIndex = lowerNormalized.indexOf(uploadSegment)
  if (uploadIndex >= 0) {
    const uploadPath = normalizedValue.slice(uploadIndex).replace(/^\/+/, '')
    return new URL(`/static/${uploadPath}`, `${getAssetOrigin()}/`).toString()
  }

  return new URL(normalizedValue, `${getAssetOrigin()}/`).toString()
}

function resolveMediaCandidates(value) {
  const rawValue = typeof value === 'string' ? value.trim() : ''
  if (!rawValue) return []
  const normalizedValue = rawValue.replace(/\\/g, '/')
  const candidates = []
  const pushCandidate = (candidate) => {
    if (!candidate) return
    const localPath = localMediaPath(candidate)
    if (localPath) {
      candidates.push(import.meta.env.DEV ? new URL(localPath, `${getAssetOrigin()}/`).toString() : localPath)
      if (!import.meta.env.DEV) {
        candidates.push(new URL(localPath, `${getAssetOrigin()}/`).toString())
      }
      return
    }
    if (/^(?:[a-z]+:)?\/\//i.test(candidate) || /^(data:|blob:|mailto:|tel:)/i.test(candidate)) {
      candidates.push(candidate)
      return
    }
    if (candidate.startsWith('/')) {
      candidates.push(import.meta.env.DEV ? new URL(candidate, `${getAssetOrigin()}/`).toString() : candidate)
      if (!import.meta.env.DEV) {
        candidates.push(new URL(candidate, `${getAssetOrigin()}/`).toString())
      }
      return
    }
    candidates.push(new URL(candidate, `${getAssetOrigin()}/`).toString())
  }

  pushCandidate(normalizedValue)

  const staticMatch = normalizedValue.match(/(?:^|\/)(static\/tienda_uploads\/.+)$/i)
  if (staticMatch?.[1]) {
    const staticPath = `/${staticMatch[1].replace(/^\/+/, '')}`
    const mediaPath = `/api/tienda/media/${staticMatch[1].replace(/^static\/tienda_uploads\//i, '')}`
    pushCandidate(staticPath)
    pushCandidate(mediaPath)
  }

  const mediaMatch = normalizedValue.match(/\/api\/tienda\/media\/(.+)$/i)
  if (mediaMatch?.[1]) {
    pushCandidate(`/api/tienda/media/${mediaMatch[1].replace(/^\/+/, '')}`)
    pushCandidate(`/static/tienda_uploads/${mediaMatch[1].replace(/^\/+/, '')}`)
  }

  const uploadMatch = normalizedValue.match(/tienda_uploads\/(.+)$/i)
  if (uploadMatch?.[1]) {
    const uploadPath = uploadMatch[1].replace(/^\/+/, '')
    pushCandidate(`/api/tienda/media/${uploadPath}`)
    pushCandidate(`/static/tienda_uploads/${uploadPath}`)
  }

  return uniqueValues(candidates)
}

function normalizeConfig(config) {
  if (!config) return config

  return {
    ...config,
    logo_url: resolveMediaUrl(config.logo_url),
    logo_fallback_urls: resolveMediaCandidates(config.logo_url),
    imagen_portada: resolveMediaUrl(config.imagen_portada),
    imagen_portada_fallback_urls: resolveMediaCandidates(config.imagen_portada)
  }
}

function normalizeProduct(producto) {
  if (!producto) return producto

  return {
    ...producto,
    imagenes: Array.isArray(producto.imagenes)
      ? producto.imagenes.map((imagen) => {
          const originalUrl = resolveMediaUrl(imagen?.url)
          const cardSource = imagen?.card_url || imagen?.thumbnail_url || imagen?.url
          const cardUrl = resolveMediaUrl(cardSource)
          return {
            ...imagen,
            url: originalUrl,
            card_url: cardUrl,
            thumbnail_url: cardUrl,
            fallback_urls: resolveMediaCandidates(imagen?.url),
            card_fallback_urls: resolveMediaCandidates(cardSource)
          }
        })
      : [],
    grupos_opciones: Array.isArray(producto.grupos_opciones)
      ? producto.grupos_opciones.map((grupo) => ({
          ...grupo,
          opciones: Array.isArray(grupo.opciones)
            ? grupo.opciones.map((opcion) => ({
                ...opcion,
                imagen_url: resolveMediaUrl(opcion?.imagen_url),
                fallback_urls: resolveMediaCandidates(opcion?.imagen_url)
              }))
            : []
        }))
      : []
  }
}

function normalizeProductCollection(responseData) {
  if (!responseData) return responseData

  return {
    ...responseData,
    productos: Array.isArray(responseData.productos) ? responseData.productos.map(normalizeProduct) : [],
    destacados: Array.isArray(responseData.destacados) ? responseData.destacados.map(normalizeProduct) : [],
    ofertas: Array.isArray(responseData.ofertas) ? responseData.ofertas.map(normalizeProduct) : [],
    recomendados: Array.isArray(responseData.recomendados) ? responseData.recomendados.map(normalizeProduct) : [],
    imperdibles: Array.isArray(responseData.imperdibles) ? responseData.imperdibles.map(normalizeProduct) : []
  }
}

function normalizeBootstrap(responseData) {
  if (!responseData) return responseData

  return {
    ...responseData,
    config: normalizeConfig(responseData.config),
    categorias: Array.isArray(responseData.categorias) ? responseData.categorias : [],
    catalogo: normalizeProductCollection(responseData.catalogo)
  }
}

function isFirstPageCatalogRequest(params = {}) {
  return !params.q && !params.categoria && Number(params.page || 1) === 1
}

function getCachedBootstrap(slug) {
  const cacheKey = String(slug || '')
  if (!cacheKey) return Promise.resolve(null)
  if (bootstrapCache.has(cacheKey)) {
    return Promise.resolve(bootstrapCache.get(cacheKey))
  }
  if (bootstrapPromises.has(cacheKey)) {
    return bootstrapPromises.get(cacheKey)
  }

  const promise = api.get(`/api/tienda/${slug}/bootstrap`)
    .then((response) => normalizeBootstrap(response.data))
    .then((data) => {
      bootstrapCache.set(cacheKey, data)
      bootstrapPromises.delete(cacheKey)
      return data
    })
    .catch((error) => {
      bootstrapPromises.delete(cacheKey)
      throw error
    })

  bootstrapPromises.set(cacheKey, promise)
  return promise
}

export const tiendaApi = {
  getBootstrap: (slug) => getCachedBootstrap(slug),
  getConfig: (slug) => getCachedBootstrap(slug).then(data => data?.config),
  getCategorias: (slug) => getCachedBootstrap(slug).then(data => data?.categorias || []),
  getProductos: (slug, params = {}, options = {}) => {
    if (isFirstPageCatalogRequest(params)) {
      return getCachedBootstrap(slug).then(data => data?.catalogo)
    }
    return api.get(`/api/tienda/${slug}/productos`, { params, signal: options.signal }).then(r => normalizeProductCollection(r.data))
  },
  getProducto: (slug, id, options = {}) => api.get(`/api/tienda/${slug}/producto/${id}`, { signal: options.signal }).then(r => ({
    ...normalizeProduct(r.data),
    relacionados: Array.isArray(r.data?.relacionados) ? r.data.relacionados.map(normalizeProduct) : []
  })),
  postLead: (payload) => api.post('/api/tienda/lead', payload).then(r => r.data)
}
