import React from 'react'
import TrustSignals from '../ui/TrustSignals'
import { isTruthyFlag, normalizeText, normalizeUrl } from '../../utils/storeFormatting'

function ContactIcon({ type }) {
  if (type === 'whatsapp') {
    return (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.133-.132.298-.347.447-.52.149-.174.198-.298.298-.497.099-.198.05-.372-.025-.521-.075-.149-.669-1.611-.916-2.207-.242-.579-.487-.5-.67-.51l-.571-.01a1.1 1.1 0 0 0-.793.372c-.273.298-1.041 1.017-1.041 2.48s1.066 2.877 1.214 3.076c.149.198 2.095 3.198 5.076 4.485.708.306 1.261.489 1.693.626.712.227 1.36.195 1.872.118.571-.086 1.758-.719 2.005-1.413.248-.695.248-1.29.174-1.414-.075-.124-.273-.198-.57-.347Z" />
      </svg>
    )
  }

  if (type === 'email') {
    return (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
        <polyline points="22,6 12,13 2,6"></polyline>
      </svg>
    )
  }

  if (type === 'instagram') {
    return (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2.2c3.19 0 3.58.01 4.85.07 1.17.05 1.97.24 2.43.41.61.24 1.05.52 1.5.97.45.45.73.89.97 1.5.17.46.36 1.26.41 2.43.06 1.27.07 1.66.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.24 1.97-.41 2.43-.24.61-.52 1.05-.97 1.5-.45.45-.89.73-1.5.97-.46.17-1.26.36-2.43.41-1.27.06-1.66.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.97-.24-2.43-.41a4.02 4.02 0 0 1-1.5-.97 4.02 4.02 0 0 1-.97-1.5c-.17-.46-.36-1.26-.41-2.43C2.21 15.58 2.2 15.19 2.2 12s.01-3.58.07-4.85c.05-1.17.24-1.97.41-2.43.24-.61.52-1.05.97-1.5.45-.45.89-.73 1.5-.97.46-.17 1.26-.36 2.43-.41C8.42 2.21 8.81 2.2 12 2.2zm0 1.8c-3.14 0-3.51.01-4.77.06-1.01.05-1.56.21-1.92.35-.47.18-.8.4-1.15.75-.35.35-.57.68-.75 1.15-.14.36-.3.91-.35 1.92-.05 1.26-.06 1.63-.06 4.77 0 3.14.01 3.51.06 4.77.05 1.01.21 1.56.35 1.92.18.47.4.8.75 1.15.35.35.68.57 1.15.75.36.14.91.3 1.92.35 1.26.05 1.63.06 4.77.06 3.14 0 3.51-.01 4.77-.06 1.01-.05 1.56-.21 1.92-.35.47-.18.8-.4 1.15-.75.35-.35.57-.68.75-1.15.14-.36.3-.91.35-1.92.05-1.26.06-1.63.06-4.77 0-3.14-.01-3.51-.06-4.77-.05-1.01-.21-1.56-.35-1.92a2.22 2.22 0 0 0-.75-1.15 2.22 2.22 0 0 0-1.15-.75c-.36-.14-.91-.3-1.92-.35-1.26-.05-1.63-.06-4.77-.06zm0 3.1A4.9 4.9 0 1 1 7.1 12 4.9 4.9 0 0 1 12 7.1zm0 8A3.1 3.1 0 1 0 8.9 12 3.1 3.1 0 0 0 12 15.1zm6.24-8.96a1.14 1.14 0 1 1-1.14-1.14 1.14 1.14 0 0 1 1.14 1.14z" />
      </svg>
    )
  }

  if (type === 'facebook') {
    return (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M13.4 21v-8h2.7l.41-3.12H13.4V7.89c0-.9.25-1.51 1.55-1.51h1.66V3.59A22.6 22.6 0 0 0 14.2 3c-2.38 0-4.01 1.45-4.01 4.13v2.75H7.5V13h2.69v8h3.21z" />
      </svg>
    )
  }

  if (type === 'youtube') {
    return (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M23.5 7.2a3 3 0 0 0-2.1-2.12C19.6 4.6 12 4.6 12 4.6s-7.6 0-9.4.48A3 3 0 0 0 .5 7.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 4.8 3 3 0 0 0 2.1 2.12c1.8.48 9.4.48 9.4.48s7.6 0 9.4-.48a3 3 0 0 0 2.1-2.12A31 31 0 0 0 24 12a31 31 0 0 0-.5-4.8zM9.6 15.4V8.6l6 3.4-6 3.4z" />
      </svg>
    )
  }

  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M10 13a5 5 0 0 0 7.07 0l2.83-2.83a5 5 0 0 0-7.07-7.07L10.7 5.23"></path>
      <path d="M14 11a5 5 0 0 0-7.07 0L4.1 13.83a5 5 0 0 0 7.07 7.07l2.12-2.12"></path>
    </svg>
  )
}

export default function Footer({ config, themeKey }) {
  const currentYear = new Date().getFullYear()
  const tituloPrincipal = normalizeText(config?.titulo_footer) || 'Nuestra Tienda'
  const mostrarTituloPrincipal = isTruthyFlag(config?.mostrar_titulo_footer ?? true)
  const descripcionFooter = normalizeText(config?.texto_footer_descripcion) || normalizeText(config?.texto_portada) || 'Descubre nuestros mejores productos al mejor precio. ¡Gracias por elegirnos!'
  const telefonoWhatsApp = normalizeText(config?.telefono_whatsapp)
  const emailContacto = normalizeText(config?.email_contacto) || `contacto@${config?.slug || 'tienda'}.com`
  const sitioWeb = normalizeText(config?.sitio_web)
  const instagramUrl = normalizeText(config?.instagram_url)
  const facebookUrl = normalizeText(config?.facebook_url)
  const youtubeUrl = normalizeText(config?.youtube_url)
  const mostrarFooterEnlaces = isTruthyFlag(config?.mostrar_footer_enlaces ?? true)
  const mostrarEmail = isTruthyFlag(config?.mostrar_email_contacto)
  const baseStorePath = config?.slug ? `/tienda/${config.slug}` : '/tienda/demo'
  const trustSignals = config?.senales_confianza || []
  const politicas = [
    isTruthyFlag(config?.mostrar_politicas_envio) && normalizeText(config?.texto_politicas_envio) && {
      label: normalizeText(config?.texto_politicas_envio),
      href: normalizeUrl(config?.link_politicas_envio)
    },
    isTruthyFlag(config?.mostrar_politicas_cambios) && normalizeText(config?.texto_politicas_cambios) && {
      label: normalizeText(config?.texto_politicas_cambios),
      href: normalizeUrl(config?.link_politicas_cambios)
    }
  ].filter(Boolean)
  const contactos = [
    telefonoWhatsApp && {
      label: telefonoWhatsApp,
      href: `https://wa.me/${telefonoWhatsApp.replace(/\D/g, '')}`,
      type: 'whatsapp'
    },
    mostrarEmail && {
      label: emailContacto,
      href: `mailto:${emailContacto}`,
      type: 'email'
    },
    isTruthyFlag(config?.mostrar_sitio_web) && sitioWeb && { label: 'Sitio Web', href: normalizeUrl(sitioWeb), type: 'web' },
    isTruthyFlag(config?.mostrar_instagram) && instagramUrl && { label: 'Instagram', href: normalizeUrl(instagramUrl), type: 'instagram' },
    isTruthyFlag(config?.mostrar_facebook) && facebookUrl && { label: 'Facebook', href: normalizeUrl(facebookUrl), type: 'facebook' },
    isTruthyFlag(config?.mostrar_youtube) && youtubeUrl && { label: 'YouTube', href: normalizeUrl(youtubeUrl), type: 'youtube' }
  ].filter(Boolean)
  const enlacesRapidos = [
    { label: 'Inicio', href: baseStorePath },
    { label: 'Catálogo Completo', href: `${baseStorePath}#catalogo-main` },
    isTruthyFlag(config?.mostrar_destacados ?? true) && { label: 'Productos Destacados', href: `${baseStorePath}#destacados` },
    isTruthyFlag(config?.mostrar_ofertas ?? true) && { label: 'Ofertas Especiales', href: `${baseStorePath}#ofertas` },
    isTruthyFlag(config?.mostrar_seccion_recomendados) && { label: 'Recomendados', href: `${baseStorePath}#recomendados` },
    isTruthyFlag(config?.mostrar_seccion_imperdibles) && { label: 'Imperdibles', href: `${baseStorePath}#imperdibles` }
  ].filter(Boolean)

  return (
    <footer className={`store-footer store-footer-${themeKey}`}>
      {trustSignals.length > 0 && (
        <div className="container mx-auto px-4 mb-8">
          <div
            className="rounded-3xl border border-slate-200 px-5 py-5 shadow-sm"
            style={{
              background: 'linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(248,250,252,0.96) 100%)'
            }}
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="max-w-2xl">
                <p
                  className="m-0"
                  style={{
                    color: 'var(--text-secondary)',
                    fontSize: '0.76rem',
                    fontWeight: 800,
                    letterSpacing: '0.18em',
                    marginBottom: 8,
                    textTransform: 'uppercase'
                  }}
                >
                  Compra con confianza
                </p>
                <h3 className="m-0 text-xl font-extrabold text-slate-900">
                  Beneficios rápidos antes de escribirnos
                </h3>
              </div>
              <div className="lg:max-w-3xl lg:flex-1">
                <TrustSignals items={trustSignals} compact />
              </div>
            </div>
          </div>
        </div>
      )}
      <div className="container mx-auto px-4 grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
        <div>
          {mostrarTituloPrincipal && <h3 className="text-xl font-bold text-gray-900 mb-4">{tituloPrincipal}</h3>}
          <p className="text-gray-600 leading-relaxed m-0">
            {descripcionFooter}
          </p>
          {politicas.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-3">
              {politicas.map((item) => (
                item.href ? (
                  <a key={item.label} href={item.href} target="_blank" rel="noreferrer" className="text-sm font-semibold text-gray-600 hover:text-gray-900 transition-colors">
                    {item.label}
                  </a>
                ) : (
                  <span key={item.label} className="text-sm font-semibold text-gray-600">
                    {item.label}
                  </span>
                )
              ))}
            </div>
          )}
        </div>

        {mostrarFooterEnlaces ? (
          <div>
            <h4 className="text-lg font-semibold text-gray-900 mb-4">Enlaces Rápidos</h4>
            <ul className="list-none p-0 m-0 flex flex-col gap-2">
              {enlacesRapidos.map((item) => (
                <li key={item.label}>
                  <a href={item.href} className="text-gray-600 hover:text-gray-900 transition-colors">
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : <div />}

        <div id="contacto-tienda" style={{ scrollMarginTop: '100px' }}>
          <h4 className="text-lg font-semibold text-gray-900 mb-4">Contacto</h4>
          <ul className="list-none p-0 m-0 flex flex-col gap-3 text-gray-600">
            {contactos.map((item) => (
              <li key={item.label}>
                <a href={item.href} target="_blank" rel="noreferrer" className="footer-contact-link inline-flex items-center gap-3 text-gray-600 hover:text-gray-900 transition-colors">
                  <span className={`footer-contact-icon footer-contact-icon-${item.type}`}>
                    <ContactIcon type={item.type} />
                  </span>
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="container mx-auto px-4 border-t border-gray-200 pt-6 flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-gray-500">
        <p className="m-0 text-center md:text-left">&copy; {currentYear} {config?.nombre_tienda || 'Tienda'}. Todos los derechos reservados.</p>
        <div className="flex flex-col items-center md:items-end gap-1 font-semibold">
          <span>Desarrollado con ❤️</span>
          <a
            href="https://demosaas.pysystems.online/"
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors underline underline-offset-2"
          >
            ¿Te interesa este sistema? Conócelo acá
          </a>
        </div>
      </div>
    </footer>
  )
}
