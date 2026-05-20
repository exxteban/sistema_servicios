import { Link, useParams } from 'react-router-dom'
import Footer from '../../../components/layout/Footer'
import { useMetaPixelPageView } from '../../../hooks/useMetaPixel'
import { useTiendaConfig } from '../../../hooks/useTiendaConfig'
import { useWebBotSession } from '../hooks/useWebBotSession'
import WebBotChat from '../components/WebBotChat'

export default function WebBotStandalonePage() {
  const { slug } = useParams()
  const { config } = useTiendaConfig(slug)
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
  } = useWebBotSession(slug, 'robot_link')

  const brandColor = botConfig?.color || config?.color_primario || '#2563eb'
  const storeName = config?.nombre_tienda || 'la tienda'
  const canOpenWhatsAppQueue = Boolean(config?.telefono_whatsapp)

  useMetaPixelPageView(config?.meta_pixel_id || '')

  async function handleDirectWhatsApp(event) {
    event.preventDefault()
    if (!canOpenWhatsAppQueue || handoffLoading) return
    await requestHandoff('usuario_desde_link_bot')
  }

  return (
    <div style={{ minHeight: '100vh', background: `linear-gradient(160deg, ${brandColor} 0%, #0f172a 100%)` }}>
      <main style={{ maxWidth: 1180, margin: '0 auto', padding: '32px 20px 48px', display: 'grid', gap: 24, gridTemplateColumns: 'minmax(0, 1fr)' }}>
        <div style={{ color: '#fff', display: 'grid', gap: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', opacity: 0.82 }}>Link Bot</div>
          <h1 style={{ margin: 0, fontSize: 'clamp(1.6rem, 3.2vw, 2.7rem)', lineHeight: 1.08, fontWeight: 900, maxWidth: 860 }}>
            Consultá el catálogo de {storeName} o pasá tu consulta al WhatsApp de la tienda.
          </h1>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, maxWidth: 680, opacity: 0.9 }}>
            Este asistente te ayuda a encontrar productos, precios y datos clave de la tienda. Si hace falta una persona, te envía al chat de WhatsApp para que entres a la cola de atención.
          </p>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Link
              to={`/tienda/${slug}`}
              style={{ padding: '12px 18px', borderRadius: 999, background: '#fff', color: '#0f172a', textDecoration: 'none', fontWeight: 800 }}
            >
              Ver catálogo
            </Link>
            {canOpenWhatsAppQueue ? (
              <button
                type="button"
                onClick={handleDirectWhatsApp}
                disabled={handoffLoading}
                style={{
                  padding: '12px 18px',
                  borderRadius: 999,
                  border: '1px solid rgba(255,255,255,0.4)',
                  color: '#fff',
                  background: 'transparent',
                  textDecoration: 'none',
                  fontWeight: 800,
                  cursor: handoffLoading ? 'not-allowed' : 'pointer',
                  opacity: handoffLoading ? 0.7 : 1
                }}
              >
                {handoffLoading ? 'Abriendo WhatsApp...' : 'Entrar a WhatsApp'}
              </button>
            ) : null}
          </div>
        </div>

        <div style={{ minHeight: 640, borderRadius: 28, overflow: 'hidden', boxShadow: '0 30px 80px rgba(15, 23, 42, 0.28)' }}>
          <WebBotChat
            title={botConfig?.assistant_name || 'Asistente IA'}
            subtitle={botConfig?.disclaimer || ''}
            color={brandColor}
            messages={messages}
            actions={actions}
            loading={loading}
            sending={sending}
            botTyping={botTyping}
            handoffLoading={handoffLoading}
            error={error}
            onSend={sendMessage}
            onAction={(action) => requestHandoff(action.motivo)}
          />
        </div>
      </main>
      <Footer config={config} themeKey="moderno" />
    </div>
  )
}
