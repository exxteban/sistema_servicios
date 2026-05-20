export default function TrustSignals({ items, compact = false }) {
  if (!items?.length) return null

  return (
    <div className={`trust-signals ${compact ? 'trust-signals-compact' : ''}`}>
      {items.map((item) => (
        <TrustSignalItem key={`${item.key}-${item.text}`} item={item}>
          <span className="trust-signal-icon" aria-hidden="true">
            {resolveIcon(item.key)}
          </span>
          <span className="trust-signal-text">{item.text}</span>
        </TrustSignalItem>
      ))}
    </div>
  )
}

function TrustSignalItem({ item, children }) {
  if (item.href) {
    return (
      <a
        href={item.href}
        className="trust-signal-item"
        target={item.target}
        rel={item.target === '_blank' ? 'noreferrer' : undefined}
      >
        {children}
      </a>
    )
  }

  return (
    <div className="trust-signal-item">
      {children}
    </div>
  )
}

function resolveIcon(key) {
  const icons = {
    whatsapp: '💬',
    envios: '🚚',
    retiro: '🏬',
    garantia: '🛡️',
    horarios: '🕒',
    cobertura: '📍'
  }
  return icons[key] || '✔'
}
