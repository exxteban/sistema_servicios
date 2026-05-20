import { useEffect, useMemo, useRef, useState } from 'react'

function MessageBubble({ message, brandColor }) {
  const isOutgoing = message.direccion === 'saliente'
  const bubbleStyle = isOutgoing
    ? { background: brandColor || '#2563eb', color: '#fff' }
    : { background: '#fff', color: '#0f172a', border: '1px solid #e2e8f0' }

  return (
    <div style={{ display: 'flex', justifyContent: isOutgoing ? 'flex-end' : 'flex-start' }}>
      <div style={{ maxWidth: '84%', padding: '12px 14px', borderRadius: 18, ...bubbleStyle }}>
        <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.5 }}>{message.contenido}</div>
        {message.failed ? <div style={{ marginTop: 6, fontSize: 12, opacity: 0.8 }}>No enviado</div> : null}
      </div>
    </div>
  )
}

function TypingBubble({ brandColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          maxWidth: '84%',
          padding: '12px 14px',
          borderRadius: 18,
          background: brandColor || '#2563eb',
          color: '#fff'
        }}
      >
        <span style={{ fontSize: 14, lineHeight: 1.5 }}>Escribiendo...</span>
      </div>
    </div>
  )
}

export default function WebBotChat({
  title,
  subtitle,
  color,
  messages,
  actions,
  loading,
  sending,
  botTyping,
  handoffLoading,
  error,
  onSend,
  onAction,
  onClose,
  compact = false
}) {
  const [draft, setDraft] = useState('')
  const messagesContainerRef = useRef(null)
  const inputRef = useRef(null)
  const shouldStickToBottomRef = useRef(true)
  const lastScrollKeyRef = useRef('')
  const brandColor = color || '#2563eb'
  const visibleMessages = useMemo(() => messages || [], [messages])
  const lastMessage = visibleMessages[visibleMessages.length - 1]
  const scrollKey = `${visibleMessages.length}:${lastMessage?.id || ''}:${lastMessage?.failed ? 'failed' : 'ok'}:${botTyping ? 'typing' : 'idle'}`

  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return

    const hasNewScrollState = lastScrollKeyRef.current !== scrollKey
    lastScrollKeyRef.current = scrollKey
    if (!hasNewScrollState || !shouldStickToBottomRef.current) return

    container.scrollTo({
      top: container.scrollHeight,
      behavior: loading ? 'auto' : 'smooth'
    })
  }, [loading, scrollKey])

  useEffect(() => {
    if (!loading && !sending) {
      focusInput(true)
    }
  }, [loading, sending])

  function focusInput(preventScroll = false) {
    if (!inputRef.current) return
    if (preventScroll) {
      try {
        inputRef.current.focus({ preventScroll: true })
        return
      } catch {
      }
    }
    inputRef.current.focus()
  }

  function handleMessagesScroll(event) {
    const container = event.currentTarget
    const remainingScroll = container.scrollHeight - container.scrollTop - container.clientHeight
    shouldStickToBottomRef.current = remainingScroll < 48
  }

  function handleSubmit(event) {
    event.preventDefault()
    const cleanText = draft.trim()
    if (!cleanText || sending) return
    shouldStickToBottomRef.current = true
    onSend(cleanText)
    setDraft('')
    focusInput(true)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f8fafc' }}>
      <div style={{ padding: compact ? '14px 16px' : '18px 20px', background: brandColor, color: '#fff' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', opacity: 0.9 }}>Asistente IA</div>
            <div style={{ fontSize: compact ? 18 : 22, fontWeight: 800, marginTop: 2 }}>{title}</div>
            {subtitle ? <div style={{ fontSize: 13, lineHeight: 1.4, marginTop: 4, opacity: 0.92 }}>{subtitle}</div> : null}
          </div>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              style={{ border: 'none', background: 'rgba(255,255,255,0.14)', color: '#fff', width: 36, height: 36, borderRadius: 999, cursor: 'pointer' }}
            >
              ✕
            </button>
          ) : null}
        </div>
      </div>

      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowAnchor: 'none',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 10
        }}
      >
        {loading ? <div style={{ color: '#475569', fontSize: 14 }}>Cargando asistente...</div> : null}
        {!loading && visibleMessages.map((message) => (
          <MessageBubble key={message.id} message={message} brandColor={brandColor} />
        ))}
        {!loading && botTyping ? <TypingBubble brandColor={brandColor} /> : null}
        {!loading && visibleMessages.length === 0 ? <div style={{ color: '#475569', fontSize: 14 }}>Todavía no hay mensajes.</div> : null}
      </div>

      {actions?.length ? (
        <div style={{ padding: '0 16px 12px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {actions.map((action) => (
            <button
              key={`${action.type}-${action.label}`}
              type="button"
              onClick={() => onAction(action)}
              disabled={handoffLoading}
              style={{
                border: 'none',
                background: brandColor,
                color: '#fff',
                padding: '10px 14px',
                borderRadius: 999,
                fontWeight: 700,
                cursor: handoffLoading ? 'not-allowed' : 'pointer',
                opacity: handoffLoading ? 0.7 : 1
              }}
            >
              {handoffLoading ? 'Enviando a WhatsApp...' : action.label}
            </button>
          ))}
        </div>
      ) : null}

      {error ? <div style={{ padding: '0 16px 12px', color: '#b91c1c', fontSize: 13 }}>{error}</div> : null}

      <form onSubmit={handleSubmit} style={{ padding: 16, borderTop: '1px solid #e2e8f0', background: '#fff' }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Escribí tu consulta..."
            disabled={loading}
            readOnly={sending}
            aria-disabled={loading || sending}
            style={{
              flex: 1,
              borderRadius: 999,
              border: '1px solid #cbd5e1',
              padding: '12px 14px',
              outline: 'none',
              fontSize: 14
            }}
          />
          <button
            type="submit"
            disabled={loading || sending || !draft.trim()}
            style={{
              border: 'none',
              borderRadius: 999,
              background: brandColor,
              color: '#fff',
              padding: '0 18px',
              fontWeight: 700,
              cursor: loading || sending || !draft.trim() ? 'not-allowed' : 'pointer',
              opacity: loading || sending || !draft.trim() ? 0.65 : 1
            }}
          >
            {sending ? '...' : 'Enviar'}
          </button>
        </div>
      </form>
    </div>
  )
}
