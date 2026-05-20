import { Suspense, lazy, useState } from 'react'
import { useWebBotSession } from '../hooks/useWebBotSession'

const WebBotChat = lazy(() => import('./WebBotChat'))

export default function WebBotWidget({ slug }) {
  const [open, setOpen] = useState(false)
  const floatingInsetRight = 'max(16px, calc(env(safe-area-inset-right) + 16px))'
  const floatingPanelTop = 'max(84px, calc(env(safe-area-inset-top) + 76px))'
  const floatingPanelBottom = 'max(16px, calc(env(safe-area-inset-bottom) + 16px))'
  const floatingButtonBottom = 'max(88px, calc(env(safe-area-inset-bottom) + 88px))'
  const {
    botConfig,
    messages,
    actions,
    loading,
    sending,
    botTyping,
    handoffLoading,
    error,
    sendMessage,
    requestHandoff
  } = useWebBotSession(slug, 'tienda_widget', open)

  if (!slug) return null

  return (
    <>
      {open ? (
        <div
          style={{
            position: 'fixed',
            right: floatingInsetRight,
            top: floatingPanelTop,
            bottom: floatingPanelBottom,
            width: 'min(420px, calc(100vw - 24px))',
            borderRadius: 24,
            overflow: 'hidden',
            border: '1px solid rgba(226, 232, 240, 0.95)',
            background: '#f8fafc',
            boxShadow: '0 30px 80px rgba(15, 23, 42, 0.28)',
            zIndex: 220
          }}
        >
          <Suspense fallback={<div style={{ padding: 18, color: '#475569' }}>Cargando asistente...</div>}>
            <WebBotChat
              title={botConfig?.assistant_name || 'Asistente IA'}
              subtitle={botConfig?.disclaimer || ''}
              color={botConfig?.color}
              messages={messages}
              actions={actions}
              loading={loading}
              sending={sending}
              botTyping={botTyping}
              handoffLoading={handoffLoading}
              error={error}
              onSend={sendMessage}
              onAction={(action) => requestHandoff(action.motivo)}
              onClose={() => setOpen(false)}
              compact
            />
          </Suspense>
        </div>
      ) : null}

      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          style={{
            position: 'fixed',
            right: floatingInsetRight,
            bottom: floatingButtonBottom,
            width: 60,
            height: 60,
            borderRadius: 999,
            border: 'none',
            background: botConfig?.color || '#2563eb',
            color: '#fff',
            boxShadow: '0 20px 40px rgba(15, 23, 42, 0.22)',
            cursor: 'pointer',
            zIndex: 210,
            fontSize: 26,
            fontWeight: 800
          }}
          aria-label="Abrir asistente IA"
        >
          🤖
        </button>
      ) : null}
    </>
  )
}
