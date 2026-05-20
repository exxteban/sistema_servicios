(function () {
    const consumoPanel = document.getElementById('ia-consumo-panel');
    if (!consumoPanel) return;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    async function getJson(url) {
        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json',
                'X-CSRFToken': csrfToken(),
            },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.mensaje || 'No se pudo cargar la informacion.');
        }
        return data;
    }

    function formatNumber(value) {
        const number = Number(value || 0);
        return number.toLocaleString('es-PY');
    }

    function setText(id, text) {
        const element = document.getElementById(id);
        if (element) element.textContent = text;
    }

    function renderUsuarios(items) {
        const container = document.getElementById('ia-consumo-usuarios');
        if (!container) return;
        const usuarios = Array.isArray(items) ? items.slice(0, 5) : [];
        if (!usuarios.length) {
            container.innerHTML = '<p class="text-xs text-gray-500 dark:text-gray-400">Sin consumo registrado.</p>';
            return;
        }
        container.innerHTML = '';
        usuarios.forEach((item) => {
            const row = document.createElement('div');
            row.className = 'flex items-center justify-between gap-2';
            const name = document.createElement('span');
            name.className = 'truncate';
            name.textContent = item.username || 'Sin usuario';
            const tokens = document.createElement('span');
            tokens.className = 'shrink-0 font-semibold';
            tokens.textContent = formatNumber(item.tokens_total || 0);
            row.appendChild(name);
            row.appendChild(tokens);
            container.appendChild(row);
        });
    }

    function refreshConsumo() {
        getJson('/asistente-ia/api/consumo?top_n=5')
            .then((data) => {
                setText('ia-consumo-dia', formatNumber(data.consumo_dia && data.consumo_dia.tokens_total));
                setText('ia-consumo-mes', formatNumber(data.consumo_mes && data.consumo_mes.tokens_total));
                setText('ia-consumo-dia-limite', data.daily_token_budget ? `Limite ${formatNumber(data.daily_token_budget)}` : 'Sin limite diario');
                setText('ia-consumo-mes-limite', data.monthly_token_budget ? `Limite ${formatNumber(data.monthly_token_budget)}` : 'Sin limite mensual');
                renderUsuarios(data.usuarios_mes);
            })
            .catch(() => {
                setText('ia-consumo-dia-limite', 'No se pudo cargar consumo');
                setText('ia-consumo-mes-limite', 'No se pudo cargar consumo');
            });
    }

    refreshConsumo();
})();
