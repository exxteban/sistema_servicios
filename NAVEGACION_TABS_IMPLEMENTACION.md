# Implementación: Navegación con Historial en Sistema de Pestañas (Tabs)

## Problema que resuelve

En sistemas Flask/Jinja2 con un motor de pestañas SPA custom (carga de contenido via AJAX con `?partial=1`), los botones "Volver" estaban hardcodeados a URLs fijas, el `document.title` del browser nunca cambiaba, y el botón "Atrás" del navegador no funcionaba dentro de las tabs.

## Arquitectura del sistema de tabs (contexto)

El sistema usa:
- `layout_refactored.html` — layout principal
- `base.html` — router condicional: si `?partial=1` renderiza solo contenido, si no extiende el layout
- `layout/tab_runtime_js_part1.html` — motor de tabs parte 1 (estructuras de datos, funciones core)
- `layout/tab_runtime_js_part2.html` — motor de tabs parte 2 (`loadContent`, funciones globales, eventos)

Ambos archivos JS se incluyen dentro de un único `<script>` inline en el layout, dentro de un IIFE, por lo que comparten scope.

---

## Cambio 1: `layout_refactored.html`

Agregar inicialización de `window.__appBaseTitle` **antes** de incluir los scripts de tabs. Extrae el título base del `<title>` del documento para usarlo en `document.title` dinámico.

```html
{% if current_user.is_authenticated and not embed_mode %}
<script>
    // Título base de la aplicación para document.title dinámico
    // Se extrae del <title> del documento, tomando la parte después del primer " - "
    (function() {
        try {
            const fullTitle = document.title || '';
            const sepIdx = fullTitle.indexOf(' - ');
            window.__appBaseTitle = sepIdx > 0 ? fullTitle.slice(sepIdx + 3) : fullTitle || 'MiApp';
        } catch { window.__appBaseTitle = 'MiApp'; }
    })();
{% include 'layout/tab_runtime_js_part1.html' %}
{% include 'layout/tab_runtime_js_part2.html' %}
</script>
{% endif %}
```

> Adaptar `'MiApp'` al nombre de tu aplicación como fallback.

---

## Cambio 2: `layout/tab_runtime_js_part1.html`

### 2a. Agregar estructuras de historial interno por tab

Justo después de las declaraciones de los Maps existentes (`tabButtonsById`, `tabPanelsById`, etc.):

```javascript
// Historial de navegación por tab: tabId -> [url, url, ...]
const tabHistoryById = new Map();
const TAB_HISTORY_MAX = 50;
```

### 2b. Inicializar historial de la tab principal

Justo antes de la función `openTab` (después de los event listeners del tab-bar):

```javascript
// Inicializar historial de la tab principal con la URL actual
pushTabHistory(principalTabId, window.location.pathname + window.location.search);
```

### 2c. Agregar funciones `pushTabHistory` y `popTabHistory`

Agregar estas dos funciones antes de `closeTab`:

```javascript
function pushTabHistory(tabId, url) {
    try {
        const normalized = normalizeKey(url);
        if (!normalized) return;
        let stack = tabHistoryById.get(tabId);
        if (!stack) {
            stack = [];
            tabHistoryById.set(tabId, stack);
        }
        // No duplicar si es la misma URL que la última
        if (stack.length > 0 && stack[stack.length - 1] === normalized) return;
        stack.push(normalized);
        if (stack.length > TAB_HISTORY_MAX) stack.shift();
    } catch { }
}

function popTabHistory(tabId) {
    try {
        const stack = tabHistoryById.get(tabId);
        if (!stack || stack.length < 2) return null;
        stack.pop(); // quitar la actual
        return stack[stack.length - 1]; // retornar la anterior
    } catch { return null; }
}
```

### 2d. Modificar `closeTab` para limpiar el historial

Agregar `tabHistoryById.delete(tabId);` junto a las otras eliminaciones:

```javascript
function closeTab(tabId) {
    if (tabId === principalTabId) return;
    const btn = tabButtonsById.get(tabId);
    const panel = tabPanelsById.get(tabId);
    const isActive = btn && btn.getAttribute('aria-selected') === 'true';

    if (btn) btn.remove();
    if (panel) panel.remove();

    tabButtonsById.delete(tabId);
    tabPanelsById.delete(tabId);
    tabLoadersById.delete(tabId);
    tabHistoryById.delete(tabId);  // ← NUEVO

    // ... resto igual
}
```

### 2e. Modificar `setActiveTab` para actualizar `document.title` y `history.replaceState`

Reemplazar el bloque `saveState()` al final de `setActiveTab` con esto (agregar antes del `saveState()`):

```javascript
// Actualizar document.title y URL del browser al cambiar de tab
try {
    const activePanel = tabPanelsById.get(tabId);
    // Para tabs secundarias: solo actualizar si el panel tiene contenido cargado
    // Para la tab principal: siempre actualizar (tiene contenido del servidor)
    const isPrincipal = tabId === principalTabId;
    const hasContent = activePanel && (isPrincipal || activePanel.querySelector('[data-app-tab-content]'));
    if (activePanel && hasContent) {
        const appTitle = window.__appBaseTitle || 'MiApp';
        const currentKey = getKeyByTabId(tabId);
        const meta = currentKey ? tabMetaByKey.get(currentKey) : null;
        const savedPageTitle = meta ? (meta.pageTitle || '').trim() : '';
        let fullTitle = appTitle;

        if (savedPageTitle) {
            fullTitle = `${savedPageTitle} - ${appTitle}`;
        } else {
            const btn = tabButtonsById.get(tabId);
            const labelEl = btn ? btn.querySelector('span.whitespace-nowrap') : null;
            const tabLabel = labelEl ? labelEl.textContent.trim() : '';
            if (tabLabel && tabLabel !== 'Dashboard') {
                fullTitle = `${tabLabel} - ${appTitle}`;
            }
        }

        document.title = fullTitle;

        // replaceState: reflejar la URL de la tab activa en el browser sin agregar
        // una entrada nueva al historial
        try {
            const tabUrl = meta ? (meta.url || currentKey) : null;
            if (tabUrl) {
                const absUrl = new URL(tabUrl, window.location.origin).toString();
                history.replaceState(
                    { tabId, url: normalizeKey(tabUrl), appNav: true },
                    fullTitle,
                    absUrl
                );
            } else if (isPrincipal) {
                history.replaceState(
                    { tabId: principalTabId, url: normalizeKey(DASHBOARD_URL), appNav: true },
                    fullTitle,
                    DASHBOARD_URL
                );
            }
        } catch { }
    }
} catch { }

saveState();
```

### 2f. Modificar `extractTabHtml` para extraer `pageTitle`

En la función `extractTabHtml`, en el bloque que maneja `partialContent`, agregar `pageTitle` al objeto retornado:

```javascript
const partialContent = doc.getElementById('partial-content');
if (partialContent) {
    const partialScripts = doc.getElementById('partial-scripts');
    const extracted = splitNodeHtml(partialContent);
    const extraScripts = partialScripts ? (partialScripts.innerHTML || '') : '';
    return {
        contentHtml: extracted.contentHtml,
        scriptsHtml: [extracted.scriptsHtml, extraScripts].filter(Boolean).join('\n'),
        stylesHtml: collectExtraStyles([partialContent, partialScripts]),
        pageTitle: (partialContent.getAttribute('data-page-title') || '').trim()  // ← NUEVO
    };
}
```

> **Por qué**: `extractTabHtml` extrae el `innerHTML` del `#partial-content`, descartando el div wrapper. El atributo `data-page-title` está en ese div wrapper, así que hay que leerlo antes de extraer el contenido.

### 2g. Modificar el listener de links en `applyPayload` para detectar "Volver"

En `applyPayload`, el bloque que registra listeners en `a[href]` debe detectar links de "Volver" y llamar `appGoBack()` en lugar de `loadContent()`. **Reemplazar el bloque completo** `contentDiv.querySelectorAll('a[href]').forEach(...)`:

```javascript
contentDiv.querySelectorAll('a[href]').forEach(link => {
    if (link.classList.contains('app-tab-link')) return;
    if (link.hasAttribute('download')) return;
    if (link.getAttribute('target') === '_blank') return;

    const href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) return;

    try {
        const linkUrl = new URL(href, window.location.origin);
        if (linkUrl.origin !== window.location.origin) return;

        // Detectar si es un link "Volver/Regresar" para usar appGoBack()
        const linkText = (link.textContent || '').trim().toLowerCase();
        const hasBackIcon = link.querySelector('.fa-arrow-left, .fa-chevron-left, .fa-angle-left');
        const isBackLink = !link.hasAttribute('data-no-back') && (
            hasBackIcon || /^(volver|regresar|back|ir atr[aá]s)/.test(linkText)
        );

        link.addEventListener('click', async (e) => {
            e.preventDefault();
            if (isBackLink && window.appGoBack) {
                window.appGoBack();
                return;
            }
            const currentKey = getKeyByTabId(tabId);
            if (currentKey) {
                const meta = tabMetaByKey.get(currentKey) || { url: currentKey, title: '', iconClass: '' };
                meta.url = normalizeKey(linkUrl.toString());
                tabMetaByKey.set(currentKey, meta);
            }
            await loadContent(linkUrl.toString());
            saveState();
        });
    } catch { }
});
```

> **Por qué**: El listener genérico de links se registra primero. Si se agrega un segundo listener separado para "Volver", ambos se ejecutan y se producen dos navegaciones simultáneas. La solución es integrar la detección dentro del único listener.

> **Escape hatch**: Si un link "Volver" específico NO debe usar `appGoBack()` (ej: quiere ir siempre a una URL fija), agregar `data-no-back` al elemento `<a>`.

---

## Cambio 3: `layout/tab_runtime_js_part2.html`

### 3a. Modificar `loadContent` para aceptar `options` y hacer `pushState`

Cambiar la firma de `loadContent(targetUrl)` a `loadContent(targetUrl, options = {})` y agregar la lógica de `pushState` después de `applyPayload`:

```javascript
async function loadContent(targetUrl, options = {}) {
    const loadSeq = ++currentLoadSeq;
    const posPerfActive = isPosPerfTarget(targetUrl);
    // Si viene de popstate no hacemos pushState (el browser ya movió el historial)
    const skipPushState = options.skipPushState === true;

    // ... (resto del fetch igual que antes) ...

    // Después de: await applyPayload(payload);
    // Agregar este bloque:

    // Actualizar document.title y pushState en el historial del browser
    try {
        const activeTabId = getActiveTabId();
        if (activeTabId === tabId) {
            const pageTitle = (payload.pageTitle || '').trim();
            const appTitle = window.__appBaseTitle || 'MiApp';
            const fullTitle = pageTitle ? `${pageTitle} - ${appTitle}` : appTitle;
            document.title = fullTitle;

            // Guardar el título en el meta de la tab para que setActiveTab lo use
            const currentKey2 = getKeyByTabId(tabId);
            if (currentKey2) {
                const meta2 = tabMetaByKey.get(currentKey2) || { url: currentKey2, title: '', iconClass: '' };
                meta2.pageTitle = pageTitle;
                if (!meta2.title) {
                    meta2.title = pageTitle;
                    syncTabButtonMeta(tabId, meta2);
                }
                tabMetaByKey.set(currentKey2, meta2);
            }

            // pushState: sincronizar la URL del browser con el contenido activo
            // Solo si no venimos de un popstate (para no crear loops)
            if (!skipPushState) {
                try {
                    const resolvedUrl = normalizeKey((response && response.url) ? response.url : targetUrl);
                    const absUrl = new URL(resolvedUrl, window.location.origin).toString();
                    // No hacer pushState si la URL ya es la actual (evita duplicados)
                    const currentHref = window.location.href.split('?')[0] + (window.location.search || '');
                    const targetHref = absUrl.split('?')[0] + (new URL(absUrl).search || '');
                    if (normalizeKey(currentHref) !== normalizeKey(targetHref)) {
                        history.pushState(
                            { tabId, url: resolvedUrl, appNav: true },
                            fullTitle,
                            absUrl
                        );
                    } else {
                        history.replaceState(
                            { tabId, url: resolvedUrl, appNav: true },
                            fullTitle,
                            absUrl
                        );
                    }
                } catch { }
            }
        }
    } catch { }
}
```

También agregar `pushTabHistory` en el bloque de actualización de meta (después de `meta.url = resolved`):

```javascript
// Registrar en historial interno de la tab
pushTabHistory(tabId, resolved);
```

### 3b. Reemplazar `appGoBack` con versión que delega al browser

```javascript
// Navega hacia atrás en el historial de la tab activa.
// Delega al browser (history.back()) para que el popstate maneje la carga.
window.appGoBack = function () {
    try {
        window.history.back();
    } catch { }
};
```

### 3c. Agregar listener `popstate`

Agregar después de `appGoBack` y antes de `appReloadActiveTab`:

```javascript
// Manejar el botón Atrás/Adelante del browser
window.addEventListener('popstate', async (e) => {
    try {
        const state = e.state;

        // Estado con appNav: navegación interna registrada por nuestro sistema
        if (state && state.appNav && state.tabId && state.url) {
            const targetTabId = state.tabId;
            const targetUrl = state.url;

            // Activar la tab correcta si no está activa
            if (getActiveTabId() !== targetTabId) {
                setActiveTab(targetTabId);
            }

            // Cargar el contenido sin hacer pushState (el browser ya movió el historial)
            const loader = tabLoadersById.get(targetTabId);
            if (loader) {
                const currentKey = getKeyByTabId(targetTabId);
                if (currentKey) {
                    const meta = tabMetaByKey.get(currentKey) || { url: currentKey, title: '', iconClass: '' };
                    meta.url = normalizeKey(targetUrl);
                    tabMetaByKey.set(currentKey, meta);
                }
                await loader(targetUrl, { skipPushState: true });
                saveState();
            }
            return;
        }

        // Estado sin appNav (estado inicial del browser o estado externo):
        // Usar el historial interno de la tab activa en lugar de recargar.
        // Esto evita recargas completas cuando el browser tiene estados previos
        // sin información de nuestro sistema.
        const tabId = getActiveTabId();
        const prevUrl = popTabHistory(tabId);

        if (prevUrl) {
            const loader = tabLoadersById.get(tabId);
            if (loader) {
                const currentKey = getKeyByTabId(tabId);
                if (currentKey) {
                    const meta = tabMetaByKey.get(currentKey) || { url: currentKey, title: '', iconClass: '' };
                    meta.url = prevUrl;
                    tabMetaByKey.set(currentKey, meta);
                }
                // Registrar el estado en el browser para que futuros popstate lo reconozcan
                try {
                    const absUrl = new URL(prevUrl, window.location.origin).toString();
                    history.replaceState(
                        { tabId, url: prevUrl, appNav: true },
                        document.title,
                        absUrl
                    );
                } catch { }
                await loader(prevUrl, { skipPushState: true });
                saveState();
            } else if (tabId !== principalTabId) {
                closeTab(tabId);
            }
        } else if (tabId !== principalTabId) {
            // Sin historial interno: cerrar la tab y volver a la anterior
            closeTab(tabId);
        }
        // Si es la tab principal sin historial: no hacer nada (ya estamos al inicio)
    } catch { }
});
```

### 3d. Inicializar el estado del browser al arrancar

Al final del IIFE, después de `restoreState()` / `setActiveTab()`:

```javascript
// Inicializar el estado del browser con la URL actual al arrancar.
// Esto permite que popstate funcione correctamente desde el primer momento.
try {
    const initUrl = normalizeKey(window.location.href);
    const initTitle = document.title;
    const activeId = getActiveTabId();
    // Solo hacer replaceState si no hay ya un estado appNav
    if (!history.state || !history.state.appNav) {
        history.replaceState(
            { tabId: activeId, url: initUrl, appNav: true },
            initTitle,
            window.location.href
        );
    }
} catch { }
```

---

## Cambio 4 (opcional): Macro Jinja2 para botón "Volver"

Crear `app/templates/macros/navigation.html` para nuevos templates:

```jinja2
{% macro back_button(label="Volver", fallback_url=None, extra_class="", icon_class="fas fa-arrow-left") %}
{% set fb = fallback_url or 'javascript:void(0)' %}
<button type="button"
    data-back-fallback="{{ fb | e }}"
    onclick="if(window.appGoBack){window.appGoBack();}else{window.location.href=this.dataset.backFallback;}"
    class="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors {{ extra_class }}"
    aria-label="{{ label }}">
    <i class="{{ icon_class }}"></i>
    {{ label }}
</button>
{% endmacro %}
```

Uso en templates:
```jinja2
{% from 'macros/navigation.html' import back_button %}
{{ back_button() }}
{{ back_button("Volver al listado", fallback_url=url_for('modulo.listar')) }}
```

---

## Cómo funciona el sistema completo

### Navegación hacia adelante
Cuando `loadContent` carga una URL nueva:
1. Hace `history.pushState({ tabId, url, appNav: true }, título, url)`
2. La URL del browser cambia a la URL real del contenido
3. El `document.title` se actualiza con el `data-page-title` de la respuesta parcial

### Botón "Atrás" del browser / Alt+←
1. Dispara `popstate` con el estado guardado
2. Si `state.appNav === true`: activa la tab correcta y carga el contenido con `skipPushState: true`
3. Si no hay `state.appNav` (estado inicial del browser): usa el historial interno de la tab como fallback

### Botón "Volver" dentro del sistema
1. El listener de links detecta automáticamente `<a>` con ícono `fa-arrow-left` o texto "Volver/Regresar"
2. Llama `appGoBack()` → `history.back()` → dispara `popstate` → mismo flujo que arriba

### Cambio de tab con el tab-bar
1. `setActiveTab` hace `history.replaceState` con la URL de la tab activa
2. El browser refleja la URL correcta sin agregar entrada al historial

### Recarga de página en cualquier URL
- Flask sirve la página completa normalmente (no requiere cambios en el backend)
- El sistema de tabs restaura el estado desde `localStorage`

---

## Requisitos del backend (base.html)

El `base.html` debe exponer `data-page-title` en el div `#partial-content` para que el sistema pueda leer el título de cada página:

```jinja2
{% if request.args.get('partial') %}
{% set page_title = '' %}
{% if self.title is defined %}
{% set page_title = self.title() %}
{% endif %}
<div id="partial-content" data-page-title="{{ page_title | striptags | trim | e }}">
    {% block content %}{% endblock %}
</div>
{% else %}
{% extends "layout_refactored.html" %}
{% endif %}
```

Cada template debe definir `{% block title %}` para que el título funcione:

```jinja2
{% extends "base.html" %}
{% block title %}Nombre de la Página{% endblock %}
{% block content %}
  ...
{% endblock %}
```

---

## Notas importantes

- **`data-no-back`**: Si un link tiene ícono `fa-arrow-left` o texto "Volver" pero NO debe usar `appGoBack()`, agregar el atributo `data-no-back` al `<a>`.
- **Tab principal**: La tab principal (Dashboard) no tiene `loader` en `tabLoadersById`. El `popstate` para la tab principal usa el historial interno y navega con `location.href` si es necesario.
- **Múltiples tabs**: La URL del browser siempre refleja la tab activa. Al cambiar de tab, `replaceState` actualiza la URL sin crear entradas extra en el historial.
- **`skipPushState`**: Cuando `loadContent` se llama desde `popstate`, se pasa `{ skipPushState: true }` para evitar que se agregue una entrada duplicada al historial del browser.
