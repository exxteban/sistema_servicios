# Iconos de marcas de electronica

Este documento describe como implementar los iconos/logos de marcas de electronica usados en las tarjetas del sistema de talleres. La idea es replicar el comportamiento visual y tecnico en otro sistema sin mezclar autos ni motos.

## Alcance

- Aplica solo a ordenes/reparaciones de electronica.
- El texto de entrada normalmente es `marca_modelo`, por ejemplo `Samsung A15`, `iPhone 13`, `Xiaomi Redmi Note`, `Motorola Edge 40`.
- No debe usar logos de autos ni motos para esta implementacion.
- Si no se detecta marca, no se muestra icono.

## Proveedor de logos

Proveedor principal:

```text
https://cdn.simpleicons.org/{slug}?viewbox=auto
```

Ejemplos:

```text
https://cdn.simpleicons.org/samsung?viewbox=auto
https://cdn.simpleicons.org/apple?viewbox=auto
https://cdn.simpleicons.org/xiaomi?viewbox=auto
https://cdn.simpleicons.org/motorola?viewbox=auto
```

Fallback por favicon:

```text
https://www.google.com/s2/favicons?domain={dominio}&sz=64
```

Ejemplo para Samsung:

```text
https://www.google.com/s2/favicons?domain=samsung.com&sz=64
```

## Marcas y aliases

Usar una tabla de marcas con `brand`, `slug` y `aliases`. El `slug` es el nombre usado por Simple Icons.

```python
ELECTRONICS_BRANDS = (
    {'brand': 'Samsung',   'slug': 'samsung',   'aliases': ('samsung',)},
    {'brand': 'Apple',     'slug': 'apple',     'aliases': ('apple', 'iphone', 'ipad', 'macbook', 'imac', 'mac')},
    {'brand': 'Xiaomi',    'slug': 'xiaomi',    'aliases': ('xiaomi', 'redmi', 'poco', 'mi ')},
    {'brand': 'Motorola',  'slug': 'motorola',  'aliases': ('motorola', 'moto g', 'moto e', 'moto edge', 'moto')},
    {'brand': 'Huawei',    'slug': 'huawei',    'aliases': ('huawei', 'honor')},
    {'brand': 'Sony',      'slug': 'sony',      'aliases': ('sony', 'xperia', 'playstation', 'ps4', 'ps5')},
    {'brand': 'LG',        'slug': 'lg',        'aliases': ('lg',)},
    {'brand': 'Lenovo',    'slug': 'lenovo',    'aliases': ('lenovo',)},
    {'brand': 'Dell',      'slug': 'dell',      'aliases': ('dell',)},
    {'brand': 'HP',        'slug': 'hp',        'aliases': ('hp', 'hewlett packard', 'hewlett-packard')},
    {'brand': 'Asus',      'slug': 'asus',      'aliases': ('asus', 'rog')},
    {'brand': 'Acer',      'slug': 'acer',      'aliases': ('acer',)},
    {'brand': 'Nokia',     'slug': 'nokia',     'aliases': ('nokia',)},
    {'brand': 'OnePlus',   'slug': 'oneplus',   'aliases': ('oneplus', 'one plus')},
    {'brand': 'Oppo',      'slug': 'oppo',      'aliases': ('oppo',)},
    {'brand': 'Vivo',      'slug': 'vivo',      'aliases': ('vivo',)},
    {'brand': 'Realme',    'slug': 'realme',    'aliases': ('realme',)},
    {'brand': 'TCL',       'slug': 'tcl',       'aliases': ('tcl',)},
    {'brand': 'Microsoft', 'slug': 'microsoft', 'aliases': ('microsoft', 'surface', 'xbox')},
    {'brand': 'Google',    'slug': 'google',    'aliases': ('google', 'pixel')},
)
```

## Reglas de deteccion

Normalizar el texto antes de comparar:

- Convertir a minusculas.
- Quitar tildes/acentos.
- Reemplazar guiones y signos por espacios.
- Compactar espacios repetidos.
- Comparar por alias exacto, alias al inicio o alias como palabra completa.

Ejemplos validos:

- `Samsung A15` detecta `Samsung`.
- `iPhone 13` detecta `Apple`.
- `Redmi Note 12` detecta `Xiaomi`.
- `Moto Edge 40` detecta `Motorola`.
- `Surface Pro` detecta `Microsoft`.
- `Pixel 8` detecta `Google`.

## Resultado esperado del resolver

La funcion debe devolver `None` si no hay match. Si hay match, devolver un objeto similar a este:

```json
{
  "brand": "Samsung",
  "url": "https://cdn.simpleicons.org/samsung?viewbox=auto",
  "fallback_url": "https://www.google.com/s2/favicons?domain=samsung.com&sz=64",
  "fallback_urls": [
    "https://www.google.com/s2/favicons?domain=samsung.com&sz=64"
  ],
  "fallback_label": "SA"
}
```

`fallback_label` son iniciales de la marca. Para una sola palabra se usan las primeras dos letras: `SA`, `AP`, `XI`, `MO`, etc.

## Dimensiones visuales

Contenedor del logo:

- Ancho: `32px`.
- Alto: `32px`.
- Border radius: `12px` aproximadamente.
- Display: flex.
- Alineacion: centrado horizontal y vertical.
- No debe deformarse ni crecer con el texto.

Imagen interna:

- Ancho: `20px`.
- Alto: `20px`.
- `object-fit: contain`.
- `loading="lazy"` si aparece en listados o tableros.

Equivalente Tailwind:

```html
<span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-[10px] font-black text-slate-500 shadow-sm dark:border-white/10 dark:bg-white dark:text-slate-500" style="background-color: #fff !important;">
  <img src="LOGO_URL" alt="Samsung" loading="lazy" class="h-5 w-5 object-contain">
  <span class="hidden">SA</span>
</span>
```

## Colores en modo claro

Contenedor:

- Fondo: `#ffffff`.
- Borde: `#e2e8f0` aproximado, equivalente a `border-slate-200`.
- Texto fallback: `#64748b` aproximado, equivalente a `text-slate-500`.
- Sombra: suave, equivalente a `shadow-sm`.

Imagen:

- No aplicar filtro CSS.
- Usar el color original entregado por Simple Icons.
- Mantener fondo blanco para que logos oscuros o de marca se vean bien.

## Colores en modo oscuro

Contenedor:

- Fondo: mantener `#ffffff` tambien en dark mode.
- Borde: `rgba(255, 255, 255, 0.10)`, equivalente a `dark:border-white/10`.
- Texto fallback: `#64748b`, equivalente a `dark:text-slate-500`.

Importante: aunque el sistema este en dark mode, el contenedor del logo queda blanco. Esto evita que logos negros, azules o multicolor pierdan contraste.

Imagen:

- No invertir colores.
- No aplicar `filter: invert()`.
- No cambiar opacidad.

## Fallback de imagen

Si falla el logo principal:

1. Probar cada URL de `fallback_urls` en orden.
2. Si todos fallan, ocultar el `img`.
3. Mostrar el `fallback_label` dentro del contenedor.

Ejemplo de `onerror` usado en template:

```html
onerror="const sources=(this.dataset.fallbackSrcs||'').split('|').filter(Boolean); const idx=Number(this.dataset.fallbackIdx||'0'); if (idx < sources.length) { this.dataset.fallbackIdx=String(idx + 1); this.src=sources[idx]; return; } this.style.display='none'; this.nextElementSibling.classList.remove('hidden');"
```

## Ubicacion recomendada en la tarjeta

El logo va antes del nombre del equipo, alineado con el titulo principal:

```html
<div class="mt-2 flex items-center gap-2 min-w-0">
  <!-- logo -->
  <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-[10px] font-black text-slate-500 shadow-sm dark:border-white/10 dark:bg-white dark:text-slate-500" style="background-color: #fff !important;">
    <img src="https://cdn.simpleicons.org/samsung?viewbox=auto" alt="Samsung" loading="lazy" class="h-5 w-5 object-contain">
    <span class="hidden">SA</span>
  </span>

  <!-- titulo -->
  <p class="min-w-0 truncate text-sm font-bold text-slate-950 dark:text-white">Samsung A15</p>
</div>
```

## Reglas de UX

- No mostrar un icono generico si no hay marca detectada. Es mejor no mostrar nada.
- No usar emojis para marcas.
- No mezclar categorias. Para electronica solo usar la tabla de electronica.
- El logo no debe reemplazar el texto del equipo; solo lo acompaña.
- El `alt` debe ser el nombre de la marca detectada.
- El titulo del equipo debe seguir visible y truncado si no cabe.

## Pseudocodigo del resolver

```python
def resolve_electronics_brand_logo(text):
    normalized = normalize(text)
    if not normalized:
        return None

    for spec in ELECTRONICS_BRANDS:
        if matches_alias(normalized, spec['aliases']):
            slug = spec['slug']
            domain = f'{slug}.com'
            return {
                'brand': spec['brand'],
                'url': f'https://cdn.simpleicons.org/{slug}?viewbox=auto',
                'fallback_url': f'https://www.google.com/s2/favicons?domain={domain}&sz=64',
                'fallback_urls': [f'https://www.google.com/s2/favicons?domain={domain}&sz=64'],
                'fallback_label': initials(spec['brand']),
            }

    return None
```

## Archivos de referencia en este sistema

- Resolver actual: `app/services/brand_logos.py`.
- Adaptacion de tarjetas: `app/services/dashboard_taller_items.py`.
- Render visual: `app/templates/dashboard/_taller_view.html`.
