import { useEffect, useState } from 'react'
import { tiendaApi } from '../services/tiendaApi'

export function useTiendaConfig(slug) {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    tiendaApi.getConfig(slug)
      .then((data) => {
        if (!alive) return
        setConfig(data)
      })
      .catch(() => {
        if (!alive) return
        setConfig(null)
        setError('No pudimos cargar la configuración de la tienda.')
      })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [slug, retryKey])

  return {
    config,
    loading,
    error,
    retry: () => setRetryKey((current) => current + 1)
  }
}
