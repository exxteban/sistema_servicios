// Dialogos de accion sobre un encargo: cobrar sena y cancelar (eligiendo que hacer con la sena).
(() => {
  const ui = window.EncargosUI;
  const root = document.querySelector('[data-gastro-encargos]');
  if (!ui || !root) return;

  const opcionesPermitidas = String(root.dataset.opcionesCancelacion || '').split(',').filter(Boolean);

  const senaDialog = document.getElementById('encargo-sena-dialog');
  const senaForm = document.getElementById('encargo-sena-form');
  const cancelDialog = document.getElementById('encargo-cancel-dialog');
  const cancelForm = document.getElementById('encargo-cancel-form');
  ui.closeOnButtons(senaDialog);
  ui.closeOnButtons(cancelDialog);

  let current = null;
  let onDone = () => {};

  const openSena = (encargo, callback) => {
    current = encargo;
    onDone = callback;
    senaForm.reset();
    ui.showError(senaForm.querySelector('[data-form-error]'), '');
    senaForm.querySelector('[data-sena-resumen]').textContent = (
      `${encargo.codigo_entrega} - ${encargo.nombre_cliente || ''}. Total ${ui.money(encargo.total)}, `
      + `seña ya cobrada ${ui.money(encargo.sena_vigente)}, saldo ${ui.money(encargo.saldo)}.`
    );
    senaDialog.showModal();
  };

  senaForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = senaForm.querySelector('[data-form-error]');
    try {
      await ui.apiJson(`/api/gastronomia/encargos/${current.id_pedido}/sena`, {
        method: 'POST',
        body: JSON.stringify({
          monto: Number(senaForm.monto.value || 0),
          metodo_pago: senaForm.metodo_pago.value,
          referencia: senaForm.referencia.value.trim(),
        }),
      });
      senaDialog.close();
      onDone('Seña registrada.', true);
    } catch (error) {
      ui.showError(errorEl, error.message);
    }
  });

  const retenerMonto = cancelForm.querySelector('[data-retener-monto]');
  cancelForm.addEventListener('change', () => {
    retenerMonto.classList.toggle('hidden', cancelForm.opcion.value !== 'retener_parcial');
  });

  const openCancel = (encargo, callback) => {
    current = encargo;
    onDone = callback;
    cancelForm.reset();
    retenerMonto.classList.add('hidden');
    ui.showError(cancelForm.querySelector('[data-form-error]'), '');
    const conSena = Number(encargo.sena_vigente || 0) > 0;
    cancelForm.querySelector('[data-cancel-opciones]').classList.toggle('hidden', !conSena);
    cancelForm.querySelectorAll('[data-opcion]').forEach((label) => {
      label.classList.toggle('hidden', !opcionesPermitidas.includes(label.dataset.opcion));
    });
    cancelForm.querySelector('[data-cancel-resumen]').textContent = conSena
      ? `${encargo.codigo_entrega} tiene ${ui.money(encargo.sena_vigente)} de seña. Elegi que hacer con ese dinero.`
      : `${encargo.codigo_entrega} no tiene seña. Se cancela sin movimientos de caja.`;
    cancelDialog.showModal();
  };

  cancelForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = cancelForm.querySelector('[data-form-error]');
    const conSena = Number(current.sena_vigente || 0) > 0;
    // Ninguna opcion viene preseleccionada: el operador tiene que elegir.
    if (conSena && !cancelForm.opcion.value) {
      ui.showError(errorEl, 'Elegi que hacer con la seña.');
      return;
    }
    try {
      await ui.apiJson(`/api/gastronomia/encargos/${current.id_pedido}/cancelar`, {
        method: 'POST',
        body: JSON.stringify({
          opcion: conSena ? cancelForm.opcion.value : null,
          monto_retenido: Number(cancelForm.monto_retenido.value || 0),
          motivo: cancelForm.motivo.value.trim(),
        }),
      });
      cancelDialog.close();
      onDone('Encargo cancelado.', true);
    } catch (error) {
      ui.showError(errorEl, error.message);
    }
  });

  window.EncargoAcciones = {openSena, openCancel};
})();
