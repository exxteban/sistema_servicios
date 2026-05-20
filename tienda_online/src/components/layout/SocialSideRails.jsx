import { isTruthyFlag, normalizeText, normalizeUrl } from '../../utils/storeFormatting'

function SocialIcon({ type }) {
  if (type === 'instagram') {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2.2c3.19 0 3.58.01 4.85.07 1.17.05 1.97.24 2.43.41.61.24 1.05.52 1.5.97.45.45.73.89.97 1.5.17.46.36 1.26.41 2.43.06 1.27.07 1.66.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.24 1.97-.41 2.43-.24.61-.52 1.05-.97 1.5-.45.45-.89.73-1.5.97-.46.17-1.26.36-2.43.41-1.27.06-1.66.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.97-.24-2.43-.41a4.02 4.02 0 0 1-1.5-.97 4.02 4.02 0 0 1-.97-1.5c-.17-.46-.36-1.26-.41-2.43C2.21 15.58 2.2 15.19 2.2 12s.01-3.58.07-4.85c.05-1.17.24-1.97.41-2.43.24-.61.52-1.05.97-1.5.45-.45.89-.73 1.5-.97.46-.17 1.26-.36 2.43-.41C8.42 2.21 8.81 2.2 12 2.2zm0 1.8c-3.14 0-3.51.01-4.77.06-1.01.05-1.56.21-1.92.35-.47.18-.8.4-1.15.75-.35.35-.57.68-.75 1.15-.14.36-.3.91-.35 1.92-.05 1.26-.06 1.63-.06 4.77 0 3.14.01 3.51.06 4.77.05 1.01.21 1.56.35 1.92.18.47.4.8.75 1.15.35.35.68.57 1.15.75.36.14.91.3 1.92.35 1.26.05 1.63.06 4.77.06 3.14 0 3.51-.01 4.77-.06 1.01-.05 1.56-.21 1.92-.35.47-.18.8-.4 1.15-.75.35-.35.57-.68.75-1.15.14-.36.3-.91.35-1.92.05-1.26.06-1.63.06-4.77 0-3.14-.01-3.51-.06-4.77-.05-1.01-.21-1.56-.35-1.92a2.22 2.22 0 0 0-.75-1.15 2.22 2.22 0 0 0-1.15-.75c-.36-.14-.91-.3-1.92-.35-1.26-.05-1.63-.06-4.77-.06zm0 3.1A4.9 4.9 0 1 1 7.1 12 4.9 4.9 0 0 1 12 7.1zm0 8A3.1 3.1 0 1 0 8.9 12 3.1 3.1 0 0 0 12 15.1zm6.24-8.96a1.14 1.14 0 1 1-1.14-1.14 1.14 1.14 0 0 1 1.14 1.14z" />
      </svg>
    )
  }

  if (type === 'facebook') {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M13.4 21v-8h2.7l.41-3.12H13.4V7.89c0-.9.25-1.51 1.55-1.51h1.66V3.59A22.6 22.6 0 0 0 14.2 3c-2.38 0-4.01 1.45-4.01 4.13v2.75H7.5V13h2.69v8h3.21z" />
      </svg>
    )
  }

  if (type === 'youtube') {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M23.5 7.2a3 3 0 0 0-2.1-2.12C19.6 4.6 12 4.6 12 4.6s-7.6 0-9.4.48A3 3 0 0 0 .5 7.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 4.8 3 3 0 0 0 2.1 2.12c1.8.48 9.4.48 9.4.48s7.6 0 9.4-.48a3 3 0 0 0 2.1-2.12A31 31 0 0 0 24 12a31 31 0 0 0-.5-4.8zM9.6 15.4V8.6l6 3.4-6 3.4z" />
      </svg>
    )
  }

  if (type === 'tiktok') {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.35V2h-3.13v13.15a2.9 2.9 0 1 1-2-2.75V9.23a6.03 6.03 0 1 0 5.13 5.96V8.53a7.85 7.85 0 0 0 4.77 1.62V7.07c-.34 0-.67-.13-1-.38Z" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.88 14.12a3 3 0 0 0 4.24 0l3.54-3.54a3 3 0 0 0-4.24-4.24L12 7.76" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.12 9.88a3 3 0 0 0-4.24 0l-3.54 3.54a3 3 0 1 0 4.24 4.24L12 16.24" />
    </svg>
  )
}

export default function SocialSideRails({ config }) {
  const socialLinks = [
    isTruthyFlag(config?.mostrar_instagram) && normalizeText(config?.instagram_url) && {
      id: 'instagram',
      label: 'Instagram',
      href: normalizeUrl(config?.instagram_url),
      type: 'instagram'
    },
    isTruthyFlag(config?.mostrar_facebook) && normalizeText(config?.facebook_url) && {
      id: 'facebook',
      label: 'Facebook',
      href: normalizeUrl(config?.facebook_url),
      type: 'facebook'
    },
    isTruthyFlag(config?.mostrar_youtube) && normalizeText(config?.youtube_url) && {
      id: 'youtube',
      label: 'YouTube',
      href: normalizeUrl(config?.youtube_url),
      type: 'youtube'
    },
    isTruthyFlag(config?.mostrar_tiktok) && normalizeText(config?.tiktok_url) && {
      id: 'tiktok',
      label: 'TikTok',
      href: normalizeUrl(config?.tiktok_url),
      type: 'tiktok'
    },
    isTruthyFlag(config?.mostrar_sitio_web) && normalizeText(config?.sitio_web) && {
      id: 'web',
      label: 'Web',
      href: normalizeUrl(config?.sitio_web),
      type: 'web'
    }
  ].filter(Boolean)

  if (socialLinks.length === 0) return null

  const leftLinks = socialLinks.filter((_, index) => index % 2 === 0)
  const rightLinks = socialLinks.filter((_, index) => index % 2 === 1)

  return (
    <>
      {leftLinks.length > 0 && (
        <aside className="social-side-rail social-side-rail-left">
          {leftLinks.map((item) => (
            <a
              key={item.id}
              href={item.href}
              target="_blank"
              rel="noreferrer"
              className={`social-side-rail-link social-side-rail-link-${item.type}`}
              aria-label={item.label}
              title={item.label}
            >
              <SocialIcon type={item.type} />
            </a>
          ))}
        </aside>
      )}
      {rightLinks.length > 0 && (
        <aside className="social-side-rail social-side-rail-right">
          {rightLinks.map((item) => (
            <a
              key={item.id}
              href={item.href}
              target="_blank"
              rel="noreferrer"
              className={`social-side-rail-link social-side-rail-link-${item.type}`}
              aria-label={item.label}
              title={item.label}
            >
              <SocialIcon type={item.type} />
            </a>
          ))}
        </aside>
      )}
    </>
  )
}
