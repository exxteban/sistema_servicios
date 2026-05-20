import axios from 'axios'

const configuredBaseURL = (import.meta.env.VITE_API_BASE_URL || '').trim()
const isLocalhostBaseURL = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(configuredBaseURL)
const baseURL = configuredBaseURL && !isLocalhostBaseURL ? configuredBaseURL : ''

const api = axios.create({ baseURL })

export const webBotApi = {
  getConfig: (slug) => api.get(`/api/tienda/${slug}/bot/config`).then((response) => response.data),
  createSession: (slug, payload) => api.post(`/api/tienda/${slug}/bot/session`, payload).then((response) => response.data),
  getSession: (slug, token) => api.get(`/api/tienda/${slug}/bot/session/${token}`).then((response) => response.data),
  sendMessage: (slug, token, mensaje) =>
    api.post(`/api/tienda/${slug}/bot/session/${token}/messages`, { mensaje }).then((response) => response.data),
  createHandoff: (slug, token, motivo) =>
    api.post(`/api/tienda/${slug}/bot/session/${token}/handoff`, { motivo }).then((response) => response.data)
}
