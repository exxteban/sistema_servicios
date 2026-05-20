import { useCallback, useEffect, useState } from 'react'
import { tiendaApi } from '../services/tiendaApi'

export function useProductos(slug, query, categoria, enabled = true) {
  const [data, setData] = useState({
    productos: [],
    destacados: [],
    ofertas: [],
    recomendados: [],
    imperdibles: [],
    total: 0,
    page: 1,
    pages: 1
  })
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      setLoadingMore(false)
      return undefined
    }
    let alive = true
    const controller = new AbortController()
    setLoading(true)
    setError('')
    tiendaApi.getProductos(
      slug,
      { q: query || undefined, categoria: categoria || undefined, page: 1, per_page: 12 },
      { signal: controller.signal }
    )
      .then((res) => {
        if (alive) setData(res)
      })
      .catch(() => {
        if (!alive) return
        setError('No pudimos cargar los productos en este momento.')
        setData((current) => ({
          ...current,
          productos: [],
          destacados: [],
          ofertas: [],
          recomendados: [],
          imperdibles: [],
          total: 0,
          page: 1,
          pages: 1
        }))
      })
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
      controller.abort()
    }
  }, [slug, query, categoria, retryKey, enabled])

  const loadMore = useCallback(async () => {
    if (!enabled || data.page >= data.pages || loadingMore) return
    setLoadingMore(true)
    setError('')
    try {
      const res = await tiendaApi.getProductos(slug, {
        q: query || undefined,
        categoria: categoria || undefined,
        page: data.page + 1,
        per_page: 12
      })
      setData(prev => ({
        ...res,
        destacados: prev.destacados,
        ofertas: prev.ofertas,
        recomendados: prev.recomendados,
        imperdibles: prev.imperdibles,
        productos: [...prev.productos, ...res.productos]
      }))
    } catch {
      setError('No pudimos cargar más productos.')
    } finally {
      setLoadingMore(false)
    }
  }, [slug, query, categoria, data.page, data.pages, loadingMore, enabled])

  return {
    ...data,
    loading,
    loadingMore,
    error,
    loadMore,
    hasMore: data.page < data.pages,
    retry: () => setRetryKey((current) => current + 1)
  }
}
