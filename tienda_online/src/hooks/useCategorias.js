import { useEffect, useState } from 'react'
import { tiendaApi } from '../services/tiendaApi'

export function useCategorias(slug) {
  const [categorias, setCategorias] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    tiendaApi.getCategorias(slug)
      .then((res) => alive && setCategorias(res))
      .catch(() => {
        if (!alive) return
        setCategorias([])
        setError('No pudimos cargar las categorías.')
      })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [slug, retryKey])

  return {
    categorias,
    loading,
    error,
    retry: () => setRetryKey((current) => current + 1)
  }
}
