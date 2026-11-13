/* Panel del asistente como asistente unico en gastronomia:
   - los accesos "Asistente IA" (barra de arriba, menu lateral, insights) abren el panel en vez de la pagina vieja;
   - para root, muestra el consumo diario y cierra el panel al ir a Historial / Panel IA. */
(function () {
    if (window.__gastroAsistenteGlobal) return;
    window.__gastroAsistenteGlobal = true;

    function rootGlobal() {
        return document.querySelector('[data-gastro-asistente][data-global]');
    }

    // Captura en window: corre antes que el runtime de pestanas, que abriria /asistente-ia en una pestana.
    window.addEventListener('click', (e) => {
        const enlace = e.target.closest && e.target.closest('[data-asistente-ia-link]');
        if (!enlace || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
        const root = rootGlobal();
        if (!root || typeof root.__abrirAsistente !== 'function') return;
        e.preventDefault();
        e.stopImmediatePropagation();
        root.__abrirAsistente();
    }, true);

    function formato(n) {
        return Number(n || 0).toLocaleString('es-PY');
    }

    async function actualizarConsumo() {
        const root = rootGlobal();
        const barra = root && root.querySelector('[data-asistente-root]');
        if (!barra) return;
        try {
            const resp = await fetch(barra.dataset.urlConsumo, { headers: { Accept: 'application/json' } });
            const data = resp.ok ? await resp.json() : null;
            const consumo = data && data.consumo_diario;
            const texto = barra.querySelector('[data-asistente-consumo]');
            if (!consumo) { texto.textContent = ''; return; }
            texto.textContent = consumo.sin_limite
                ? `Hoy: ${formato(consumo.usado)} tokens`
                : `Hoy: ${formato(consumo.usado)} / ${formato(consumo.limite)} tokens`;
            texto.title = 'Tu consumo diario de la IA (lo ve solo root)';
        } catch (err) { /* el consumo es informativo: sin red no se muestra */ }
    }

    document.addEventListener('gastro-asistente:abierto', actualizarConsumo);
    document.addEventListener('gastro-asistente:respuesta', actualizarConsumo);
    // Tambien en captura: el runtime de pestanas corta la propagacion del clic en sus enlaces.
    window.addEventListener('click', (e) => {
        const enlace = e.target.closest && e.target.closest('[data-asistente-root] a');
        const root = rootGlobal();
        if (enlace && root && typeof root.__cerrarAsistente === 'function') root.__cerrarAsistente();
    }, true);
})();
