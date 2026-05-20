const STORE_THEMES = {
  moderno: {
    key: 'moderno',
    wrapperClass: 'store-style-moderno',
    sectionOrderHome: ['hero', 'categories', 'destacados', 'ofertas', 'recomendados', 'imperdibles', 'catalog'],
    sectionOrderResults: ['categories', 'catalog'],
    labels: {
      destacados: 'Productos Destacados',
      ofertas: 'Ofertas Especiales',
      recomendados: 'Recomendados para vos',
      imperdibles: 'Imperdibles de la tienda',
      catalogoHome: 'Todo el Catálogo',
      catalogoResultados: 'Resultados'
    }
  },
  clasico: {
    key: 'clasico',
    wrapperClass: 'store-style-clasico',
    sectionOrderHome: ['hero', 'destacados', 'categories', 'recomendados', 'catalog', 'ofertas', 'imperdibles'],
    sectionOrderResults: ['categories', 'catalog'],
    labels: {
      destacados: 'Selección de Vitrina',
      ofertas: 'Promociones de Temporada',
      recomendados: 'Selección Recomendada',
      imperdibles: 'Piezas Imperdibles',
      catalogoHome: 'Catálogo General',
      catalogoResultados: 'Resultados'
    }
  },
  minimalista: {
    key: 'minimalista',
    wrapperClass: 'store-style-minimalista',
    sectionOrderHome: ['hero', 'categories', 'recomendados', 'catalog', 'destacados', 'ofertas', 'imperdibles'],
    sectionOrderResults: ['categories', 'catalog'],
    labels: {
      destacados: 'Selección Curada',
      ofertas: 'Últimas Ofertas',
      recomendados: 'Recomendados',
      imperdibles: 'No Te Los Pierdas',
      catalogoHome: 'Colección',
      catalogoResultados: 'Resultados'
    }
  },
  boutique: {
    key: 'boutique',
    wrapperClass: 'store-style-boutique',
    sectionOrderHome: ['hero', 'destacados', 'recomendados', 'catalog', 'categories', 'ofertas', 'imperdibles'],
    sectionOrderResults: ['categories', 'catalog'],
    labels: {
      destacados: 'Selección Boutique',
      ofertas: 'Piezas en Promoción',
      recomendados: 'Selección Editorial',
      imperdibles: 'Favoritos Imperdibles',
      catalogoHome: 'Colección Completa',
      catalogoResultados: 'Piezas Encontradas'
    }
  },
  tech: {
    key: 'tech',
    wrapperClass: 'store-style-tech',
    sectionOrderHome: ['hero', 'categories', 'ofertas', 'destacados', 'recomendados', 'imperdibles', 'catalog'],
    sectionOrderResults: ['categories', 'catalog'],
    labels: {
      destacados: 'Top de la Semana',
      ofertas: 'Deals Flash',
      recomendados: 'Recomendados por IA',
      imperdibles: 'No Te Los Podés Perder',
      catalogoHome: 'Todo el Inventario',
      catalogoResultados: 'Resultados'
    }
  },
  retail: {
    key: 'retail',
    wrapperClass: 'store-style-retail',
    sectionOrderHome: ['hero', 'categories', 'ofertas', 'destacados', 'catalog', 'recomendados', 'imperdibles'],
    sectionOrderResults: ['categories', 'catalog'],
    labels: {
      destacados: 'Top en Tendencia',
      ofertas: 'Ofertas del Día',
      recomendados: 'Recomendados',
      imperdibles: 'Últimas Unidades',
      catalogoHome: 'Catálogo Completo',
      catalogoResultados: 'Resultados'
    }
  }
}

export function resolveStoreTheme(estiloTienda) {
  return STORE_THEMES[estiloTienda] || STORE_THEMES.moderno
}
