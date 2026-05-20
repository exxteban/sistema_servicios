(function () {
    'use strict';

    const form        = document.getElementById('ia-chat-form');
    const input       = document.getElementById('ia-chat-input');
    const messages    = document.getElementById('ia-chat-messages');
    const status      = document.getElementById('ia-chat-status');
    const clearButton = document.getElementById('ia-chat-clear');
    if (!form || !input || !messages) return;

    let usagePanel = document.getElementById('ia-chat-usage');
    let usageLabel = document.getElementById('ia-chat-usage-label');
    let usageBar   = document.getElementById('ia-chat-usage-bar');

    /* ── Helpers ── */
    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function setStatus(text) {
        if (status) status.textContent = text || '';
    }

    /* ── Auto-resize textarea ── */
    function autoResize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 128) + 'px';
    }
    input.addEventListener('input', autoResize);

    /* ── Chips de sugerencias ── */
    const chipsContainer = document.getElementById('ia-chips');
    if (chipsContainer) {
        chipsContainer.addEventListener('click', (event) => {
            const chip = event.target.closest('.ia-chip');
            if (!chip) return;
            const prompt = chip.dataset.prompt || '';
            if (!prompt) return;
            input.value = prompt;
            autoResize();
            input.focus();
        });
    }

    /* ── Renderizado de mensajes ── */
    function removeWelcome() {
        const welcome = messages.querySelector('.ia-welcome');
        if (welcome) welcome.remove();
    }

    function addMessage(role, text) {
        removeWelcome();
        const row = document.createElement('div');
        row.className = `ia-msg-row ia-msg-row--${role}`;

        if (role === 'assistant') {
            const avatar = document.createElement('div');
            avatar.className = 'ia-msg-avatar ia-msg-avatar--assistant';
            avatar.setAttribute('aria-hidden', 'true');
            avatar.innerHTML = '<i class="fas fa-robot"></i>';
            row.appendChild(avatar);
        }

        const bubble = document.createElement('div');
        bubble.className = `ia-bubble ia-bubble--${role}`;
        bubble.textContent = text;
        row.appendChild(bubble);

        if (role === 'user') {
            const avatar = document.createElement('div');
            avatar.className = 'ia-msg-avatar ia-msg-avatar--user';
            avatar.setAttribute('aria-hidden', 'true');
            avatar.innerHTML = '<i class="fas fa-user"></i>';
            row.appendChild(avatar);
        }

        messages.appendChild(row);
        scrollToBottom();
        return row;
    }

    /* ── Indicador "pensando" ── */
    let typingRow = null;

    function showTyping() {
        if (typingRow) return;
        removeWelcome();
        typingRow = document.createElement('div');
        typingRow.className = 'ia-msg-row ia-msg-row--assistant';

        const avatar = document.createElement('div');
        avatar.className = 'ia-msg-avatar ia-msg-avatar--assistant';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.innerHTML = '<i class="fas fa-robot"></i>';

        const bubble = document.createElement('div');
        bubble.className = 'ia-bubble ia-bubble--assistant';
        bubble.innerHTML = '<div class="ia-typing"><span></span><span></span><span></span></div>';

        typingRow.appendChild(avatar);
        typingRow.appendChild(bubble);
        messages.appendChild(typingRow);
        scrollToBottom();
    }

    function hideTyping() {
        if (typingRow) {
            typingRow.remove();
            typingRow = null;
        }
    }

    function scrollToBottom() {
        messages.scrollTop = messages.scrollHeight;
    }

    /* ── Barra de consumo ── */
    function updateUsage(consumo) {
        if (!usagePanel || !usageLabel || !usageBar || !consumo) return;
        const used       = Number(consumo.usado   || 0);
        const limit      = Number(consumo.limite  || 0);
        const remaining  = consumo.restante;
        const percentage = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;

        usagePanel.dataset.used      = String(used);
        usagePanel.dataset.limit     = String(limit);
        usagePanel.dataset.remaining = remaining === null || remaining === undefined ? '' : String(remaining);

        usageLabel.textContent = limit > 0
            ? `${used.toLocaleString('es-PY')} / ${limit.toLocaleString('es-PY')}`
            : `${used.toLocaleString('es-PY')} tokens`;

        usageBar.style.setProperty('--usage', `${percentage}%`);
        usageBar.classList.remove('ia-usage-strip-fill--warn', 'ia-usage-strip-fill--danger');
        if (percentage >= 90) {
            usageBar.classList.add('ia-usage-strip-fill--danger');
        } else if (percentage >= 70) {
            usageBar.classList.add('ia-usage-strip-fill--warn');
        }
    }

    /* ── Action card ── */
    function payloadLines(payload) {
        return Object.entries(payload || {})
            .filter(([, v]) => v !== null && v !== undefined && v !== '' && (!Array.isArray(v) || v.length))
            .slice(0, 6)
            .map(([k, v]) => {
                const label = k.replaceAll('_', ' ');
                const text  = Array.isArray(v) ? v.join(', ') : String(v);
                return `${label}: ${text}`;
            });
    }

    function addActionCard(action) {
        if (!action || !action.id_accion) return;

        const row = document.createElement('div');
        row.className = 'ia-msg-row ia-msg-row--assistant';

        const card = document.createElement('div');
        card.className = 'ia-action-card';

        const title = document.createElement('div');
        title.className = 'font-semibold mb-1';
        title.textContent = action.tipo_label || 'Acción asistida';
        card.appendChild(title);

        const lines = payloadLines(action.payload);
        if (lines.length) {
            const list = document.createElement('div');
            list.className = 'space-y-0.5 text-xs whitespace-pre-wrap mb-2';
            lines.forEach((line) => {
                const item = document.createElement('div');
                item.textContent = line;
                list.appendChild(item);
            });
            card.appendChild(list);
        }

        const controls = document.createElement('div');
        controls.className = 'flex items-center gap-2 mt-2';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-600 px-3 text-xs font-semibold text-white hover:bg-amber-700 transition disabled:opacity-60 disabled:cursor-not-allowed';
        btn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i><span>Confirmar</span>';

        const note = document.createElement('span');
        note.className = 'text-xs opacity-75';
        note.textContent = 'No ejecuta cambios automáticos.';

        controls.appendChild(btn);
        controls.appendChild(note);
        card.appendChild(controls);
        row.appendChild(card);
        messages.appendChild(row);
        scrollToBottom();

        btn.addEventListener('click', async () => {
            btn.disabled = true;
            setStatus('Confirmando...');
            try {
                const data = await postJson(`/asistente-ia/api/acciones/${action.id_accion}/confirmar`, {});
                note.textContent = data.mensaje || 'Confirmación registrada.';
                setStatus('');
            } catch (err) {
                btn.disabled = false;
                setStatus(err.message);
            }
        });
    }

    /* ── Fetch helpers ── */
    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Accept':       'application/json',
                'Content-Type': 'application/json',
                'X-CSRFToken':  csrfToken(),
            },
            body: JSON.stringify(payload || {}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.mensaje || 'No se pudo procesar la solicitud.');
        return data;
    }

    async function getJson(url) {
        const response = await fetch(url, { headers: { Accept: 'application/json' } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.mensaje || 'No se pudo cargar la información.');
        return data;
    }

    /* ── Envío del formulario ── */
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        autoResize();
        addMessage('user', text);
        showTyping();
        setStatus('');

        const sendBtn = form.querySelector('button[type="submit"]');
        if (sendBtn) sendBtn.disabled = true;

        try {
            const data = await postJson('/asistente-ia/api/chat', { mensaje: text });
            hideTyping();
            addMessage('assistant', data.mensaje || '');
            addActionCard(data.accion);
            updateUsage(data.consumo_diario);
            const estado = data.estado && data.estado !== 'ok' ? data.estado : '';
            setStatus(estado);
        } catch (err) {
            hideTyping();
            setStatus(err.message);
        } finally {
            if (sendBtn) sendBtn.disabled = false;
            input.focus();
        }
    });

    /* ── Limpiar conversación ── */
    clearButton.addEventListener('click', async () => {
        setStatus('');
        try {
            await postJson('/asistente-ia/api/limpiar', {});
            messages.innerHTML = '';
            /* Restaurar bienvenida */
            messages.innerHTML = `
                <div class="ia-welcome">
                    <div class="ia-welcome-icon">
                        <i class="fas fa-robot" aria-hidden="true"></i>
                    </div>
                    <div>
                        <p class="ia-welcome-title">¡Hola! Soy tu asistente IA</p>
                        <p class="ia-welcome-sub">
                            Puedo ayudarte a consultar ventas, cobranzas, inventario, gastos corrientes, caja y fidelización.
                            Escribí tu pregunta o elegí una sugerencia.
                        </p>
                    </div>
                    <div class="ia-welcome-chips" id="ia-chips">
                        <button type="button" class="ia-chip" data-prompt="¿Cuánto vendí hoy?">
                            <i class="fas fa-chart-line" aria-hidden="true"></i> Ventas de hoy
                        </button>
                        <button type="button" class="ia-chip" data-prompt="¿Cuál es el estado de caja?">
                            <i class="fas fa-cash-register" aria-hidden="true"></i> Estado de caja
                        </button>
                        <button type="button" class="ia-chip" data-prompt="¿Qué productos tienen stock bajo?">
                            <i class="fas fa-boxes-stacked" aria-hidden="true"></i> Stock bajo
                        </button>
                        <button type="button" class="ia-chip" data-prompt="¿Cuánto se cobró este mes?">
                            <i class="fas fa-hand-holding-dollar" aria-hidden="true"></i> Cobranzas del mes
                        </button>
                        <button type="button" class="ia-chip" data-prompt="¿Cuáles son los gastos de esta semana?">
                            <i class="fas fa-receipt" aria-hidden="true"></i> Gastos recientes
                        </button>
                    </div>
                </div>`;
            /* Re-bind chips */
            const newChips = document.getElementById('ia-chips');
            if (newChips) {
                newChips.addEventListener('click', (e) => {
                    const chip = e.target.closest('.ia-chip');
                    if (!chip) return;
                    input.value = chip.dataset.prompt || '';
                    autoResize();
                    input.focus();
                });
            }
        } catch (err) {
            setStatus(err.message);
        }
    });

    /* ── Enter para enviar, Shift+Enter para nueva línea ── */
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    /* ── Carga inicial del consumo ── */
    getJson('/asistente-ia/api/consumo-usuario')
        .then((data) => updateUsage(data.consumo_diario))
        .catch(() => {});

    scrollToBottom();
})();
