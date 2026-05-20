import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { trackMetaPixelPageView, trackMetaPixelViewContent } from '../services/metaPixel'

export function useMetaPixelPageView(pixelId) {
  const location = useLocation()

  useEffect(() => {
    if (!pixelId) return
    trackMetaPixelPageView(pixelId)
  }, [location.pathname, location.search, pixelId])
}

export function useMetaPixelProductView(pixelId, producto) {
  useEffect(() => {
    if (!pixelId || !producto?.id) return
    trackMetaPixelViewContent(pixelId, {
      content_ids: [String(producto.id)],
      content_name: producto.nombre || 'Producto',
      content_type: 'product',
      currency: 'PYG',
      value: Number(producto.precio) || 0
    })
  }, [pixelId, producto])
}
