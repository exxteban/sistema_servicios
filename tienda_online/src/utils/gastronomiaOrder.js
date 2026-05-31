import { formatGs, normalizeText } from './storeFormatting'

function getPhoneDigits(phone) {
  return String(phone || '').replace(/\D/g, '')
}

function isRemovableModifier(modifier) {
  return modifier?.tipo_grupo === 'ingrediente_removible'
}

function formatModifierName(modifier) {
  const name = normalizeText(modifier?.nombre) || 'ingrediente'
  return isRemovableModifier(modifier) ? `Sin ${name}` : name
}

export function buildWhatsAppUrl(phone, message) {
  const digits = getPhoneDigits(phone)
  if (!digits) return ''
  return `https://wa.me/${digits}?text=${encodeURIComponent(message || 'Hola')}`
}

export function buildGastronomiaOrderMessage(config, items = []) {
  const storeName = normalizeText(config?.nombre_tienda)
  const introStore = storeName ? ` de ${storeName}` : ''

  if (!Array.isArray(items) || items.length === 0) {
    return `Hola, vengo de la tienda web${introStore} y quiero hacer un pedido.`
  }

  const total = items.reduce((acc, item) => acc + Number(item.subtotal || 0), 0)
  const lines = [
    `Hola, vengo de la tienda web${introStore} y quiero hacer este pedido:`,
    ''
  ]

  items.forEach((item) => {
    lines.push(
      `- ${item.nombre} x${item.quantity} (${formatGs(item.precio)} c/u): ${formatGs(item.subtotal)}`
    )
    if (item.modifiers?.length) {
      item.modifiers.forEach((modifier) => {
        const modifierTotal = Number(modifier.precio_delta || 0) * Number(modifier.cantidad || 0)
        const label = formatModifierName(modifier)
        const quantityText = isRemovableModifier(modifier) && Number(modifier.cantidad || 0) === 1 ? '' : ` x${modifier.cantidad}`
        lines.push(
          `  * ${label}${quantityText}: ${modifierTotal > 0 ? `+ ${formatGs(modifierTotal)}` : 'sin costo'}`
        )
      })
    }
  })

  lines.push('')
  lines.push(`Total estimado: ${formatGs(total)}`)
  lines.push('¿Me confirman disponibilidad y si es para retiro o entrega?')

  return lines.join('\n')
}

export function buildGastronomiaOrderHref(config, items = []) {
  return buildWhatsAppUrl(config?.telefono_whatsapp, buildGastronomiaOrderMessage(config, items))
}
