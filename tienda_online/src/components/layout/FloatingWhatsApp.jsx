export default function FloatingWhatsApp({ phone, message, onClick }) {
  if (!phone) return null
  const digits = phone.replace(/\D/g, '')
  const url = `https://wa.me/${digits}?text=${encodeURIComponent(message || 'Hola')}`

  return (
    <a href={url} target="_blank" rel="noreferrer" onClick={onClick} style={{
        position: 'fixed',
        right: 16,
        bottom: 16,
      width: 54,
      height: 54,
      borderRadius: '50%',
      display: 'grid',
      placeItems: 'center',
      background: '#22c55e',
      color: '#fff',
      fontWeight: 700
    }}>
      WA
    </a>
  )
}
