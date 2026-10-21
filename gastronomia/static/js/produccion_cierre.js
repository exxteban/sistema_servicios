// Cierre del dia de produccion: conteo de lo que quedo y destino del sobrante.
(() => {
  const ui = window.EncargosUI;
  const dialog = document.getElementById('produccion-cierre-dialog');
  if (!ui || !dialog) return;

  const form = dialog.querySelector('form');
  const filasEl = dialog.querySelector('[data-cierre-filas]');
  const errorEl = dialog.querySelector('[data-error]');
  let alTerminar = () => {};

  const DESTINOS = [
    ['sigue', 'Sigue a la venta'],
    ['vencido', 'Se descarta (vencido)'],
    ['regalado', 'Se regala'],
    ['consumo_propio', 'Consumo propio'],
  ];
  const input = 'h-10 w-full rounded-lg border border-gray-200 px-3 text-sm font-semibold dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100';

  const fila = (p) => `
    <div class="grid items-center gap-2 rounded-lg border border-gray-100 p-2 sm:grid-cols-3 dark:border-gray-700" data-producto-id="${p.producto_id}">
      <div>
        <p class="text-sm font-bold">${ui.escapeHtml(p.nombre)}</p>
        <p class="text-xs text-gray-500 dark:text-gray-400">Segun sistema: ${p.stock}</p>
      </div>
      <input type="number" min="0" max="10000" name="quedan" placeholder="Quedan" aria-label="Quedan de ${ui.escapeHtml(p.nombre)}" class="${input}">
      <select name="destino" aria-label="Que se hace con lo que quedo" class="${input}">
        ${DESTINOS.map(([valor, label]) => `<option value="${valor}">${label}</option>`).join('')}
      </select>
    </div>`;

  const abrir = (productos, onDone) => {
    alTerminar = onDone || (() => {});
    ui.showError(errorEl, '');
    filasEl.innerHTML = productos.map(fila).join('');
    dialog.showModal();
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const items = [...filasEl.querySelectorAll('[data-producto-id]')]
      .map((el) => ({
        producto_id: Number(el.dataset.productoId),
        quedan: el.querySelector('[name="quedan"]').value,
        destino: el.querySelector('[name="destino"]').value,
      }))
      .filter((item) => item.quedan !== '');
    if (!items.length) {
      ui.showError(errorEl, 'Carga lo que quedo de al menos un producto.');
      return;
    }
    try {
      const data = await ui.apiJson('/api/gastronomia/produccion/cierre', {method: 'POST', body: JSON.stringify({items})});
      dialog.close();
      alTerminar(`Dia cerrado: ${data.registros.length} movimiento(s) registrados.`);
    } catch (error) {
      ui.showError(errorEl, error.message);
    }
  });

  ui.closeOnButtons(dialog);
  window.ProduccionCierre = {abrir};
})();
