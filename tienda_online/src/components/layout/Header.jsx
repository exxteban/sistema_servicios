import SearchBar from '../ui/SearchBar'

export default function Header({ config, query, onChange, themeKey }) {
  const logoUrl = typeof config?.logo_url === 'string' ? config.logo_url.trim() : ''
  const storeName = config?.nombre_tienda || 'Tienda Online'

  return (
    <header className={`store-header store-header-${themeKey}`}>
      <div className="container mx-auto px-4 py-4">
        <div className={`store-header-inner store-header-inner-${themeKey}`}>
          <div className="store-header-brand flex-wrap sm:flex-nowrap">
            {logoUrl && (
              <div className="h-14 w-14 shrink-0 overflow-hidden rounded-2xl shadow-[0_10px_30px_rgba(15,23,42,0.16)] ring-1 ring-black/10">
                <img
                  src={logoUrl}
                  alt={`Logo de ${storeName}`}
                  className="h-full w-full object-cover"
                  loading="eager"
                  decoding="async"
                />
              </div>
            )}
            <div className="min-w-0">
              <h1 className="store-header-title truncate">
                {storeName}
              </h1>
            </div>
          </div>
          <div className="store-header-search">
            <SearchBar value={query} onChange={onChange} />
          </div>
        </div>
      </div>
    </header>
  )
}
