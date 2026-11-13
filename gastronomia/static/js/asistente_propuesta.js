// Tarjeta "Revisa antes de guardar" del asistente IA: nada se guarda hasta tocar Confirmar.
(function () {
    function texto(tag, clase, contenido) {
        const el = document.createElement(tag);
        if (clase) el.className = clase;
        if (contenido) el.textContent = contenido;
        return el;
    }

    function cerrarAnteriores(lista) {
        lista.querySelectorAll('[data-asistente-propuesta]:not([data-resuelta])').forEach((card) => {
            card.dataset.resuelta = '1';
            const acciones = card.querySelector('.ga-prop-acciones');
            if (acciones) acciones.replaceWith(texto('p', 'ga-prop-estado', 'Reemplazada por una propuesta nueva (no se guardo).'));
        });
    }

    // opts: { lista, base, pedir(url, metodo), alResolver(data) }
    function pintar(propuesta, opts) {
        if (!propuesta || !Array.isArray(propuesta.resumen)) return;
        const existente = opts.lista.querySelector(`[data-asistente-propuesta="${propuesta.id}"]`);
        if (existente) return;
        cerrarAnteriores(opts.lista);

        const card = texto('div', 'ga-propuesta');
        card.dataset.asistentePropuesta = String(propuesta.id);
        card.appendChild(texto('p', 'ga-prop-titulo', 'Revisa antes de guardar'));
        const ul = texto('ul', 'ga-prop-lista');
        propuesta.resumen.forEach((linea) => ul.appendChild(texto('li', '', linea)));
        card.appendChild(ul);
        card.appendChild(texto('p', 'ga-prop-nota', 'Todavia no se guardo nada. Solo se guarda si tocas Confirmar.'));

        const acciones = texto('div', 'ga-prop-acciones');
        const confirmar = texto('button', 'ga-prop-confirmar', 'Confirmar y guardar');
        const cancelar = texto('button', 'ga-prop-cancelar', 'Cancelar');
        confirmar.type = 'button';
        cancelar.type = 'button';
        acciones.append(confirmar, cancelar);
        card.appendChild(acciones);

        async function resolver(accion) {
            confirmar.disabled = true;
            cancelar.disabled = true;
            card.dataset.resuelta = '1';
            let data;
            try {
                data = await opts.pedir(`${opts.base}/${propuesta.id}/${accion}`, 'POST');
            } catch (err) {
                data = { ok: false, mensaje: err.message };
            }
            const etiqueta = !data.ok ? 'No se pudo: ' + (data.mensaje || 'error')
                : accion === 'confirmar' ? 'Confirmado' : 'Cancelado';
            acciones.replaceWith(texto('p', 'ga-prop-estado', etiqueta));
            if (data.ok) opts.alResolver(data);
        }

        confirmar.addEventListener('click', () => resolver('confirmar'));
        cancelar.addEventListener('click', () => resolver('cancelar'));
        opts.lista.appendChild(card);
        opts.lista.scrollTop = opts.lista.scrollHeight;
    }

    window.GastroAsistentePropuesta = { pintar };
})();
