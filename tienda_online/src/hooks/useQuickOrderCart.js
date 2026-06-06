import { useEffect, useMemo, useState } from 'react'
import { calculatePromotionSubtotal } from '../utils/promotions'

const STORAGE_PREFIX = 'tienda-online:gastronomia-order:'

function clampQuantity(value) {
  const numericValue = Number(value || 0)
  if (!Number.isFinite(numericValue)) return 0
  return Math.max(0, Math.min(99, Math.round(numericValue)))
}

function normalizeModifiers(modifiers = []) {
  return modifiers
    .map((modifier) => ({
      id_opcion: modifier.id_opcion,
      nombre: modifier.nombre || 'Opcion',
      cantidad: clampQuantity(modifier.cantidad),
      precio_delta: Number(modifier.precio_delta || 0),
      nombre_grupo: modifier.nombre_grupo || '',
      tipo_grupo: modifier.tipo_grupo || ''
    }))
    .filter((modifier) => modifier.id_opcion && modifier.cantidad > 0)
    .sort((a, b) => String(a.id_opcion).localeCompare(String(b.id_opcion)))
}

function buildCustomizedKey(producto, modifiers) {
  const signature = modifiers.length
    ? modifiers.map((modifier) => `${modifier.id_opcion}x${modifier.cantidad}`).join('|')
    : 'sin-opciones'
  return `custom:${producto.id}:${signature}`
}

function normalizeCartItem(producto, quantity, options = {}) {
  const nextQuantity = clampQuantity(quantity)
  const modifiers = normalizeModifiers(options.modifiers || producto?.modifiers)
  const isCustomized = Boolean(options.allowCustomization || producto?.customized || modifiers.length > 0)
  if (!producto?.id || nextQuantity <= 0 || (!isCustomized && productRequiresCustomization(producto))) return null

  const precio = Number(options.unitPrice ?? producto.precio ?? 0)
  const basePrice = Number(options.basePrice ?? producto.basePrice ?? producto.precio ?? precio)
  const promotion = options.promotion ?? producto.promocion_activa ?? null
  const key = String(options.key || producto.key || producto.cartKey || (isCustomized ? buildCustomizedKey(producto, modifiers) : producto.id))
  return {
    key,
    id: producto.id,
    nombre: producto.nombre || 'Producto',
    precio,
    basePrice,
    promotion,
    modifiers,
    customized: isCustomized,
    quantity: nextQuantity,
    subtotal: calculatePromotionSubtotal(precio, nextQuantity, promotion, basePrice)
  }
}

function productRequiresCustomization(producto) {
  return Boolean(producto?.tiene_opciones || producto?.grupos_opciones?.some((grupo) => grupo?.opciones?.length > 0))
}

function cartItemsAreEqual(currentItem, nextItem) {
  return currentItem?.key === nextItem?.key &&
    currentItem?.nombre === nextItem?.nombre &&
    Number(currentItem?.precio || 0) === Number(nextItem?.precio || 0) &&
    Number(currentItem?.promotion?.id || 0) === Number(nextItem?.promotion?.id || 0) &&
    Number(currentItem?.quantity || 0) === Number(nextItem?.quantity || 0) &&
    Number(currentItem?.subtotal || 0) === Number(nextItem?.subtotal || 0)
}

function getCartKey(producto) {
  return String(producto?.key || producto?.cartKey || producto?.id || '')
}

function readStoredCart(storageKey) {
  if (typeof window === 'undefined' || !storageKey) return {}

  try {
    const rawValue = window.localStorage.getItem(storageKey)
    if (!rawValue) return {}

    const parsedValue = JSON.parse(rawValue)
    if (!parsedValue || typeof parsedValue !== 'object') return {}

    return Object.values(parsedValue).reduce((acc, item) => {
      const normalizedItem = normalizeCartItem(item, item?.quantity, {
        allowCustomization: Boolean(item?.customized || item?.modifiers?.length),
        key: item?.key,
        modifiers: item?.modifiers,
        unitPrice: item?.precio,
        basePrice: item?.basePrice,
        promotion: item?.promotion
      })
      if (normalizedItem) {
        acc[normalizedItem.key] = normalizedItem
      }
      return acc
    }, {})
  } catch {
    return {}
  }
}

export function useQuickOrderCart(slug, productosActuales = []) {
  const storageKey = slug ? `${STORAGE_PREFIX}${slug}` : ''
  const [cartMap, setCartMap] = useState(() => readStoredCart(storageKey))
  const latestProductsById = useMemo(() => {
    return productosActuales.reduce((acc, producto) => {
      if (producto?.id) acc[producto.id] = producto
      return acc
    }, {})
  }, [productosActuales])

  useEffect(() => {
    setCartMap(readStoredCart(storageKey))
  }, [storageKey])

  useEffect(() => {
    if (typeof window === 'undefined' || !storageKey) return
    window.localStorage.setItem(storageKey, JSON.stringify(cartMap))
  }, [cartMap, storageKey])

  useEffect(() => {
    const latestIds = Object.keys(latestProductsById)
    if (!latestIds.length) return

    setCartMap((current) => {
      let changed = false
      const nextMap = Object.values(current).reduce((acc, item) => {
        const latestProduct = latestProductsById[item.id]
        if (!latestProduct) {
          acc[item.key] = item
          return acc
        }

        const refreshedItem = item.customized
          ? normalizeCartItem(item, item.quantity, {
              allowCustomization: true,
              key: item.key,
              modifiers: item.modifiers,
              unitPrice: item.precio,
              basePrice: item.basePrice,
              promotion: latestProduct.promocion_activa ?? null
            })
          : normalizeCartItem(latestProduct, item.quantity)
        if (!refreshedItem) {
          changed = true
          return acc
        }

        acc[refreshedItem.key] = refreshedItem
        if (!cartItemsAreEqual(item, refreshedItem)) changed = true
        return acc
      }, {})

      return changed ? nextMap : current
    })
  }, [latestProductsById])

  const items = useMemo(
    () => Object.values(cartMap).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
    [cartMap]
  )

  const totalItems = useMemo(
    () => items.reduce((acc, item) => acc + Number(item.quantity || 0), 0),
    [items]
  )

  const totalAmount = useMemo(
    () => items.reduce((acc, item) => acc + Number(item.subtotal || 0), 0),
    [items]
  )

  const setQuantity = (producto, quantity) => {
    if (!producto?.id) return

    setCartMap((current) => {
      const nextItem = normalizeCartItem(producto, quantity)
      if (!nextItem) {
        const nextMap = { ...current }
        delete nextMap[getCartKey(producto)]
        return nextMap
      }

      return {
        ...current,
        [nextItem.key]: nextItem
      }
    })
  }

  const addCustomizedItem = (producto, modifiers = [], unitPrice = producto?.precio, quantity = 1) => {
    if (!producto?.id) return null
    const normalizedModifiers = normalizeModifiers(modifiers)
    const key = buildCustomizedKey(producto, normalizedModifiers)

    setCartMap((current) => {
      const currentQuantity = Number(current?.[key]?.quantity || 0)
      const nextItem = normalizeCartItem(producto, currentQuantity + clampQuantity(quantity), {
        allowCustomization: true,
        key,
        modifiers: normalizedModifiers,
        unitPrice,
        basePrice: producto.precio
      })
      if (!nextItem) return current
      return {
        ...current,
        [nextItem.key]: nextItem
      }
    })

    return key
  }

  const increment = (producto) => {
    if (!producto?.id) return
    setCartMap((current) => {
      const cartKey = getCartKey(producto)
      const currentQuantity = Number(current?.[cartKey]?.quantity || 0)
      const nextItem = normalizeCartItem(producto, currentQuantity + 1)
      if (!nextItem) return current
      return {
        ...current,
        [nextItem.key]: nextItem
      }
    })
  }

  const decrement = (producto) => {
    if (!producto?.id) return
    setCartMap((current) => {
      const cartKey = getCartKey(producto)
      const currentQuantity = Number(current?.[cartKey]?.quantity || 0)
      const nextItem = normalizeCartItem(producto, currentQuantity - 1)
      if (!nextItem) {
        const nextMap = { ...current }
        delete nextMap[cartKey]
        return nextMap
      }
      return {
        ...current,
        [nextItem.key]: nextItem
      }
    })
  }

  const clearCart = () => setCartMap({})
  const getQuantity = (productId) => Number(cartMap?.[String(productId)]?.quantity || 0)

  return {
    items,
    totalItems,
    totalAmount,
    setQuantity,
    addCustomizedItem,
    increment,
    decrement,
    clearCart,
    getQuantity
  }
}
