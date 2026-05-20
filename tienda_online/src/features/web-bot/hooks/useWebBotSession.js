import { useEffect, useState } from 'react'
import { webBotApi } from '../services/webBotApi'

const SESSION_TTL_MS = 24 * 60 * 60 * 1000
const SESSION_SYNC_MS = 4000

function buildOptimisticUserMessage(text) {
  return {
    id: `temp-user-${Date.now()}`,
    direccion: 'entrante',
    remitente: 'cliente',
    tipo_mensaje: 'text',
    contenido: text,
    created_at: new Date().toISOString(),
    optimistic: true,
    failed: false
  }
}

export function useWebBotSession(slug, origin = 'tienda_widget', enabled = true) {
  const [sessionToken, setSessionToken] = useState('')
  const [botConfig, setBotConfig] = useState(null)
  const [messages, setMessages] = useState([])
  const [estado, setEstado] = useState('bot')
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(Boolean(enabled))
  const [sending, setSending] = useState(false)
  const [botTyping, setBotTyping] = useState(false)
  const [handoffLoading, setHandoffLoading] = useState(false)
  const [error, setError] = useState('')
  const [lastActivityAt, setLastActivityAt] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function startFreshSession() {
      if (!enabled || !slug) {
        if (!cancelled) setLoading(false)
        return null
      }

      setLoading(true)
      setError('')
      try {
        const config = await webBotApi.getConfig(slug)
        if (cancelled) return
        setBotConfig(config)
        const session = await webBotApi.createSession(slug, { origen: origin })
        if (cancelled) return
        setSessionToken(session.session_token)
        setMessages(session.historial || [])
        setEstado(session.estado || 'bot')
        setActions([])
        setBotConfig(session.bot || config)
        setLastActivityAt(Date.now())
        return session
      } catch {
        if (cancelled) return
        setError('No pudimos iniciar el asistente en este momento.')
        return null
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    if (enabled) {
      startFreshSession()
    } else {
      setLoading(false)
    }

    return () => {
      cancelled = true
    }
  }, [enabled, origin, slug])

  useEffect(() => {
    if (!enabled || !sessionToken || !lastActivityAt) return undefined

    const timeoutMs = Math.max(0, SESSION_TTL_MS - (Date.now() - lastActivityAt))
    const timeoutId = window.setTimeout(() => {
      setSessionToken('')
      setMessages([])
      setActions([])
      setEstado('bot')
      setBotTyping(false)
      setSending(false)
      setHandoffLoading(false)
      setError('')
      setLastActivityAt(0)
    }, timeoutMs)

    return () => window.clearTimeout(timeoutId)
  }, [enabled, lastActivityAt, sessionToken])

  useEffect(() => {
    if (!enabled || !sessionToken || !slug) return undefined

    let cancelled = false

    const syncSession = async () => {
      try {
        const session = await webBotApi.getSession(slug, sessionToken)
        if (cancelled) return
        setMessages(session.historial || [])
        setEstado(session.estado || 'bot')
        setBotConfig((current) => session.bot || current)
      } catch (syncError) {
        if (cancelled) return
        if (syncError?.response?.data?.error === 'sesion_expirada') {
          setSessionToken('')
          setMessages([])
          setActions([])
          setEstado('bot')
          setError('')
          setLastActivityAt(0)
        }
      }
    }

    const intervalId = window.setInterval(syncSession, SESSION_SYNC_MS)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [enabled, sessionToken, slug])

  useEffect(() => {
    if (!enabled || loading || sessionToken || !slug) return

    let cancelled = false

    async function restartExpiredSession() {
      setLoading(true)
      try {
        const session = await webBotApi.createSession(slug, { origen: origin })
        if (cancelled) return
        setSessionToken(session.session_token)
        setMessages(session.historial || [])
        setEstado(session.estado || 'bot')
        setActions([])
        setBotConfig((current) => session.bot || current)
        setLastActivityAt(Date.now())
      } catch {
        if (cancelled) return
        setError('No pudimos reiniciar el chat en este momento.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    restartExpiredSession()

    return () => {
      cancelled = true
    }
  }, [enabled, loading, origin, sessionToken, slug])

  async function sendMessage(text) {
    const cleanText = (text || '').trim()
    if (!cleanText || !sessionToken) return
    const optimisticMessage = buildOptimisticUserMessage(cleanText)
    setMessages((current) => [...current, optimisticMessage])
    setSending(true)
    setBotTyping(true)
    setError('')
    try {
      const response = await webBotApi.sendMessage(slug, sessionToken, cleanText)
      setMessages(response.historial || [])
      setEstado(response.estado || 'bot')
      setActions(response.acciones || [])
      setLastActivityAt(Date.now())
      return response
    } catch (sendError) {
      if (sendError?.response?.data?.error === 'sesion_expirada') {
        setSessionToken('')
        setMessages([])
        setActions([])
        setEstado('bot')
        setError('')
        setLastActivityAt(0)
        return null
      }
      setMessages((current) =>
        current.map((message) =>
          message.id === optimisticMessage.id
            ? { ...message, optimistic: false, failed: true }
            : message
        )
      )
      setError('No pudimos enviar tu mensaje. Intentá de nuevo.')
      return null
    } finally {
      setSending(false)
      setBotTyping(false)
    }
  }

  async function requestHandoff(motivo = 'usuario_solicita_whatsapp') {
    if (!sessionToken) return null
    setHandoffLoading(true)
    setError('')
    try {
      const response = await webBotApi.createHandoff(slug, sessionToken, motivo)
      setEstado(response.estado || 'handoff')
      setActions([])
      setLastActivityAt(Date.now())
      if (response.whatsapp_url) {
        window.open(response.whatsapp_url, '_blank', 'noopener,noreferrer')
      }
      return response
    } catch (handoffError) {
      if (handoffError?.response?.data?.error === 'sesion_expirada') {
        setSessionToken('')
        setMessages([])
        setActions([])
        setEstado('bot')
        setError('')
        setLastActivityAt(0)
        return null
      }
      if (handoffError?.response?.data?.error === 'telefono_requerido') {
        setError('Antes de pedir asesor, pasanos tu número de teléfono en el chat.')
        return null
      }
      setError('No pudimos enviarte al chat de WhatsApp en este momento.')
      return null
    } finally {
      setHandoffLoading(false)
    }
  }

  return {
    botConfig,
    messages,
    estado,
    actions,
    loading,
    sending,
    botTyping,
    handoffLoading,
    error,
    sendMessage,
    requestHandoff
  }
}
