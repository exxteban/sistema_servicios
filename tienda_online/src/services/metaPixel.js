const PIXEL_SCRIPT_ID = 'meta-pixel-script'
const PIXEL_BOOTSTRAP_ID = 'meta-pixel-bootstrap'
const PIXEL_QUEUE_KEY = '__metaPixelInitializedIds'

function canUseDOM() {
  return typeof window !== 'undefined' && typeof document !== 'undefined'
}

export function normalizeMetaPixelId(value) {
  const rawValue = typeof value === 'string' ? value : String(value || '')
  const digits = rawValue.replace(/\D/g, '')
  return digits || ''
}

function ensurePixelBootstrap() {
  if (!canUseDOM()) return false
  if (typeof window.fbq === 'function') return true
  if (document.getElementById(PIXEL_BOOTSTRAP_ID)) return true

  const bootstrap = document.createElement('script')
  bootstrap.id = PIXEL_BOOTSTRAP_ID
  bootstrap.text = `!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?` +
    `n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;` +
    `n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;` +
    `t.src=v;t.id='${PIXEL_SCRIPT_ID}';s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}` +
    `(window, document,'script','https://connect.facebook.net/en_US/fbevents.js');`
  document.head.appendChild(bootstrap)
  return true
}

function ensurePixelInitialized(pixelId) {
  const normalizedPixelId = normalizeMetaPixelId(pixelId)
  if (!normalizedPixelId || !ensurePixelBootstrap() || typeof window.fbq !== 'function') {
    return ''
  }

  if (!window[PIXEL_QUEUE_KEY]) {
    window[PIXEL_QUEUE_KEY] = new Set()
  }

  if (!window[PIXEL_QUEUE_KEY].has(normalizedPixelId)) {
    window.fbq('init', normalizedPixelId)
    window[PIXEL_QUEUE_KEY].add(normalizedPixelId)
  }

  return normalizedPixelId
}

export function trackMetaPixelPageView(pixelId) {
  const normalizedPixelId = ensurePixelInitialized(pixelId)
  if (!normalizedPixelId) return
  window.fbq('trackSingle', normalizedPixelId, 'PageView')
}

export function trackMetaPixelViewContent(pixelId, payload = {}) {
  const normalizedPixelId = ensurePixelInitialized(pixelId)
  if (!normalizedPixelId) return
  window.fbq('trackSingle', normalizedPixelId, 'ViewContent', payload)
}

export function trackMetaPixelContact(pixelId, payload = {}) {
  const normalizedPixelId = ensurePixelInitialized(pixelId)
  if (!normalizedPixelId) return
  window.fbq('trackSingle', normalizedPixelId, 'Contact', payload)
}
