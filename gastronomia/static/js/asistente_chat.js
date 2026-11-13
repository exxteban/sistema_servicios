(function () {
  // El sistema abre pantallas en pestanas internas: puede haber varios paneles en el DOM.
  function iniciarPendientes() {
    document.querySelectorAll('[data-gastro-asistente]:not([data-iniciado])').forEach(iniciar);
  }
  iniciarPendientes();

  // El refresco silencioso del Dashboard reemplaza el HTML del panel pero solo re-ejecuta
  // scripts inline, no este archivo: el boton nuevo quedaba sin listeners. Un observer
  // (uno solo por documento) inicializa cualquier panel que aparezca despues.
  if (!window.__gastroAsistenteObserver && window.MutationObserver) {
    let pendiente = false;
    window.__gastroAsistenteObserver = new MutationObserver(() => {
      if (pendiente) return;
      pendiente = true;
      requestAnimationFrame(() => {
        pendiente = false;
        window.__gastroAsistenteIniciarPendientes();
      });
    });
    window.__gastroAsistenteObserver.observe(document.body, { childList: true, subtree: true });
  }
  window.__gastroAsistenteIniciarPendientes = iniciarPendientes;

  function iniciar(root) {
    root.dataset.iniciado = '1';

    const $ = (sel) => root.querySelector(sel);
    const panel = $('[data-asistente-panel]');
    const fondo = $('[data-asistente-fondo]');
    const abrirBtn = $('[data-asistente-abrir]');
    const lanzador = $('[data-asistente-lanzador]');
    const pestana = $('[data-asistente-expandir]');
    const CLAVE_COLAPSADO = 'gastro_asistente_colapsado';
    const lista = $('[data-asistente-mensajes]');
    const form = $('[data-asistente-form]');
    const input = $('[data-asistente-input]');
    const boton = $('[data-asistente-enviar]');
    const avisoRecarga = $('[data-asistente-recargar]');
    const CLAVE_ABIERTO = 'gastro_asistente_abierto';
    let enviando = false;

    function guardarAbierto(valor) {
        try { sessionStorage.setItem(CLAVE_ABIERTO, valor ? '1' : '0'); } catch (e) { /* sin storage */ }
    }

    const CLAVE_ANCHO = 'gastro_asistente_ancho';
    const ANCHO_MIN = 300;
    const ANCHO_DEFECTO = 448;

    function anchoMaximo() {
        return Math.max(ANCHO_MIN, Math.round(window.innerWidth * 0.9));
    }

    function aplicarAncho(px, guardar) {
        const ancho = Math.min(anchoMaximo(), Math.max(ANCHO_MIN, Math.round(px)));
        panel.style.maxWidth = 'none';
        panel.style.width = ancho + 'px';
        if (guardar) {
            try { localStorage.setItem(CLAVE_ANCHO, String(ancho)); } catch (e) { /* sin storage */ }
        }
    }

    function restaurarAncho() {
        if (window.innerWidth <= 640) {
            panel.style.width = '';
            panel.style.maxWidth = '';
            return;
        }
        let guardado = 0;
        try { guardado = parseInt(localStorage.getItem(CLAVE_ANCHO) || '0', 10); } catch (e) { /* sin storage */ }
        aplicarAncho(guardado || ANCHO_DEFECTO, false);
    }

    function iniciarResize() {
        const handle = $('[data-asistente-resize]');
        if (!handle) return;
        handle.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            handle.setPointerCapture(e.pointerId);
            panel.classList.add('ga-arrastrando');
            const mover = (ev) => aplicarAncho(window.innerWidth - ev.clientX, false);
            const soltar = () => {
                panel.classList.remove('ga-arrastrando');
                handle.removeEventListener('pointermove', mover);
                handle.removeEventListener('pointerup', soltar);
                handle.removeEventListener('pointercancel', soltar);
                aplicarAncho(panel.getBoundingClientRect().width, true);
            };
            handle.addEventListener('pointermove', mover);
            handle.addEventListener('pointerup', soltar);
            handle.addEventListener('pointercancel', soltar);
        });
        handle.addEventListener('dblclick', () => {
            try { localStorage.removeItem(CLAVE_ANCHO); } catch (e) { /* sin storage */ }
            aplicarAncho(ANCHO_DEFECTO, false);
        });
        handle.addEventListener('keydown', (e) => {
            const paso = e.shiftKey ? 80 : 24;
            const actual = panel.getBoundingClientRect().width;
            if (e.key === 'ArrowLeft') { e.preventDefault(); aplicarAncho(actual + paso, true); }
            if (e.key === 'ArrowRight') { e.preventDefault(); aplicarAncho(actual - paso, true); }
        });
    }

    function ajustarTope() {
        const nav = document.querySelector('.crm-topnav');
        const tope = nav ? Math.max(0, nav.getBoundingClientRect().bottom) : 0;
        root.style.setProperty('--ga-top', tope + 'px');
    }

    function estaColapsado() {
        try { return localStorage.getItem(CLAVE_COLAPSADO) === '1'; } catch (e) { return false; }
    }

    function mostrarLanzador(colapsado) {
        lanzador.classList.toggle('ga-oculto', colapsado);
        pestana.classList.toggle('ga-oculto', !colapsado);
    }

    function colapsar(valor) {
        try { localStorage.setItem(CLAVE_COLAPSADO, valor ? '1' : '0'); } catch (e) { /* sin storage */ }
        mostrarLanzador(valor);
    }

    function abrir() {
        ajustarTope();
        panel.classList.add('ga-abierto');
        panel.setAttribute('aria-hidden', 'false');
        fondo.classList.remove('ga-oculto');
        lanzador.classList.add('ga-oculto');
        pestana.classList.add('ga-oculto');
        guardarAbierto(true);
        // Siempre se relee: otra pestana interna pudo haber chateado o limpiado mientras tanto.
        if (!enviando) cargarHistorial();
        document.dispatchEvent(new CustomEvent('gastro-asistente:abierto'));
        setTimeout(() => input.focus(), 200);
    }

    function cerrar() {
        panel.classList.remove('ga-abierto');
        panel.setAttribute('aria-hidden', 'true');
        fondo.classList.add('ga-oculto');
        mostrarLanzador(estaColapsado());
        guardarAbierto(false);
    }

    // Sin "\": el navegador trata "/\host" como "//host" (enlace a otro sitio).
    const ENLACE_RE = /\[([^\]\n]{1,80})\]\((\/(?![\/\\])[^)\s\\]{0,300})\)/g;

    function esRutaInterna(href) {
        try { return new URL(href, window.location.origin).origin === window.location.origin; } catch (e) { return false; }
    }

    function tituloPestana(href) {
        if (href.includes('/salon')) return ['Configurar salon', 'fas fa-chair'];
        if (href.includes('/pos')) return ['POS Touch', 'fas fa-tablet-alt'];
        if (href.includes('/caja')) return ['Caja', 'fas fa-cash-register'];
        if (href.includes('/cocina')) return ['Cocina', 'fas fa-fire'];
        if (href.includes('/delivery')) return ['Delivery', 'fas fa-motorcycle'];
        return ['Cargar menu', 'fas fa-utensils'];
    }

    // Solo convierte enlaces internos [texto](/ruta); el resto queda como texto plano (sin innerHTML).
    function pintarTexto(div, texto) {
        let ultimo = 0;
        texto.replace(ENLACE_RE, (completo, etiqueta, href, pos) => {
            if (!esRutaInterna(href)) return completo;
            div.appendChild(document.createTextNode(texto.slice(ultimo, pos)));
            const a = document.createElement('a');
            const [titulo, icono] = tituloPestana(href);
            a.href = href;
            a.className = 'ga-enlace app-tab-link';
            a.setAttribute('data-tab-url', href);
            a.setAttribute('data-tab-title', titulo);
            a.setAttribute('data-tab-icon', icono);
            a.textContent = etiqueta;
            if (href.startsWith('/gastronomia/menu')) {
                // El runtime de pestanas corre el script del Menu antes de cambiar la URL: le pasamos el
                // destino por la misma clave que usa menu_config.js para restaurar estado tras recargar.
                const recordarDestino = () => {
                    try { sessionStorage.setItem('gastro-menu-alert', JSON.stringify({ message: '', ok: true, url: href })); } catch (e) { /* sin storage */ }
                };
                a.addEventListener('pointerdown', recordarDestino);
                a.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') recordarDestino(); });
            }
            div.appendChild(a);
            ultimo = pos + completo.length;
            return completo;
        });
        div.appendChild(document.createTextNode(texto.slice(ultimo)));
    }

    function burbuja(texto, rol) {
        const div = document.createElement('div');
        div.className = 'ga-msg ' + (rol === 'user' ? 'ga-msg-user' : 'ga-msg-bot');
        if (rol === 'user') div.textContent = texto;
        else pintarTexto(div, texto || '');
        lista.appendChild(div);
        lista.scrollTop = lista.scrollHeight;
        return div;
    }

    function mostrarBienvenida() {
        lista.innerHTML = '';
        const tpl = $('[data-asistente-bienvenida-tpl]');
        lista.appendChild(tpl.content.cloneNode(true));
        lista.querySelectorAll('[data-asistente-sugerencia]').forEach((btn) => {
            btn.addEventListener('click', () => enviar(btn.textContent));
        });
    }

    async function pedir(url, metodo, body) {
        const resp = await fetch(url, {
            method: metodo,
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': root.dataset.csrf },
            body: metodo === 'GET' ? undefined : JSON.stringify(body || {}),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.mensaje || 'No se pudo conectar con el asistente.');
        return data;
    }

    function mostrarPropuesta(propuesta) {
        const modulo = window.GastroAsistentePropuesta;
        if (!modulo || !propuesta) return;
        modulo.pintar(propuesta, {
            lista,
            base: root.dataset.urlPropuesta,
            pedir,
            alResolver: (data) => {
                burbuja(data.mensaje || 'Listo.', 'assistant');
                if (data.hubo_cambios) avisoRecarga.classList.remove('ga-oculto');
                // La barra "Se guardaron cambios" achica la lista: sin esto el resultado queda tapado.
                lista.scrollTop = lista.scrollHeight;
            },
        });
    }

    async function cargarHistorial() {
        try {
            const data = await pedir(root.dataset.urlHistorial, 'GET');
            $('[data-asistente-aviso]').classList.toggle('ga-oculto', !!data.ia_habilitada);
            const historial = data.historial || [];
            if (!historial.length && !data.propuesta) return mostrarBienvenida();
            lista.innerHTML = '';
            historial.forEach((m) => burbuja(m.content, m.role));
            mostrarPropuesta(data.propuesta);
        } catch (err) {
            mostrarBienvenida();
        }
    }

    async function enviar(texto) {
        const mensaje = (texto || '').trim();
        if (!mensaje || enviando) return;
        enviando = true;
        boton.disabled = true;
        const bienvenida = lista.querySelector('[data-asistente-bienvenida]');
        if (bienvenida) bienvenida.remove();
        burbuja(mensaje, 'user');
        input.value = '';
        const pensando = burbuja('Pensando y cargando...', 'assistant');
        pensando.classList.add('ga-pensando');
        try {
            const capturador = window.GastroAsistenteContexto;
            const contexto = capturador ? capturador.capturar(root) : {};
            const data = await pedir(root.dataset.urlChat, 'POST', { mensaje, contexto });
            pensando.textContent = '';
            pintarTexto(pensando, data.mensaje || 'Listo.');
            $('[data-asistente-aviso]').classList.toggle('ga-oculto', data.estado !== 'desactivado');
            if (data.hubo_cambios) avisoRecarga.classList.remove('ga-oculto');
            mostrarPropuesta(data.propuesta);
        } catch (err) {
            pensando.textContent = err.message;
        } finally {
            pensando.classList.remove('ga-pensando');
            document.dispatchEvent(new CustomEvent('gastro-asistente:respuesta'));
            enviando = false;
            boton.disabled = false;
            lista.scrollTop = lista.scrollHeight;
            input.focus();
        }
    }

    async function limpiar() {
        if (enviando) return;
        try { await pedir(root.dataset.urlLimpiar, 'POST'); } catch (e) { /* igual limpiamos la vista */ }
        avisoRecarga.classList.add('ga-oculto');
        input.value = '';
        mostrarBienvenida();
    }

    root.__abrirAsistente = abrir;
    root.__cerrarAsistente = cerrar;
    window.addEventListener('resize', () => { ajustarTope(); restaurarAncho(); });
    restaurarAncho();
    iniciarResize();
    abrirBtn.addEventListener('click', abrir);
    $('[data-asistente-colapsar]').addEventListener('click', () => colapsar(true));
    pestana.addEventListener('click', () => colapsar(false));
    mostrarLanzador(estaColapsado());
    $('[data-asistente-cerrar]').addEventListener('click', cerrar);
    fondo.addEventListener('click', cerrar);
    $('[data-asistente-limpiar]').addEventListener('click', limpiar);
    $('[data-asistente-recargar-btn]').addEventListener('click', async () => {
        guardarAbierto(true);
        avisoRecarga.classList.add('ga-oculto');
        const actual = window.location.pathname + window.location.search;
        if (typeof window.appNavigateActiveTab === 'function') {
            // Recarga solo la pestana interna activa (no todo el sistema).
            try { await window.appNavigateActiveTab(actual); return; } catch (e) { /* fallback abajo */ }
        }
        window.location.reload();
    });
    form.addEventListener('submit', (e) => { e.preventDefault(); enviar(input.value); });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(input.value); }
        if (e.key === 'Escape') cerrar();
    });

    let abiertoAntes = false;
    try { abiertoAntes = sessionStorage.getItem(CLAVE_ABIERTO) === '1'; } catch (e) { /* sin storage */ }
    if (abiertoAntes || new URLSearchParams(window.location.search).get('asistente') === '1') abrir();
  }
})();
