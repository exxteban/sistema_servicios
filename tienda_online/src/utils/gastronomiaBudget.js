export function getStoreWhatsAppMessage(config, fallback = 'Hola, vengo de la tienda web.') {
  const configured = config?.mensaje_whatsapp_general || config?.mensaje_whatsapp
  if (configured) return configured
  if (config?.es_gastronomia) {
    return [
      'Hola, vengo de la tienda web y quiero solicitar un presupuesto para gastronomia.',
      '- Productos, bebidas o servicio requerido:',
      '- Cantidad estimada:',
      '- Fecha y hora:',
      '- Comentarios:'
    ].join('\n')
  }
  return fallback
}
