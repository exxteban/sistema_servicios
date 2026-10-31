// Casilla de consentimiento para mensajes en el POS (BI-04).
// Al guardar un pedido con celular informa si la casilla quedo marcada. Si no lo esta y el cliente
// todavia no acepto, avisa en el POS y deja el celular como pendiente: nunca se marca por defecto.
(() => {
  const campo = (id) => document.querySelector(`#${id}`);
  const csrf = () => campo('csrf-token')?.value || document.querySelector('meta[name="csrf-token"]')?.content || '';

  const MENSAJES = {
    registrado: {texto: 'Último pedido: consentimiento registrado.', ok: true},
    ya_registrado: {texto: 'Último pedido: el cliente ya tenía el consentimiento registrado.', ok: true},
    sin_marcar: {
      texto: 'Atención: la casilla de consentimiento no estaba marcada. Ese celular no entra en la cola de mensajes hasta que el cliente acepte.',
      ok: false,
    },
  };

  const avisar = (texto, ok) => {
    const estado = campo('consentimiento-estado');
    if (!estado) return;
    estado.textContent = texto;
    estado.classList.toggle('text-emerald-700', ok);
    estado.classList.toggle('dark:text-emerald-300', ok);
    estado.classList.toggle('text-rose-700', !ok);
    estado.classList.toggle('dark:text-rose-300', !ok);
    estado.classList.remove('hidden');
  };

  // Se llama al cambiar el tipo de pedido, al limpiar y al cargar un pedido: la casilla siempre empieza sin marcar.
  const sincronizar = (tipo) => {
    const bloque = campo('cliente-contacto');
    if (!bloque) return;
    const delivery = tipo === 'delivery';
    bloque.classList.toggle('hidden', tipo === 'mesa');
    if (campo('delivery-phone')) campo('delivery-phone').placeholder = delivery ? 'Celular obligatorio' : 'Celular (opcional)';
    if (campo('cliente-contacto-requerido')) {
      campo('cliente-contacto-requerido').textContent = delivery ? '(obligatorio)' : '(opcional)';
    }
    if (campo('cliente-acepta-mensajes')) campo('cliente-acepta-mensajes').checked = false;
  };

  // Se llama al guardar el pedido. Lee el telefono y la casilla al instante, antes de que el POS limpie el formulario.
  // `alertar` es el aviso del POS: el mensaje de «sin marcar» se muestra ahi tambien, para que no pase desapercibido.
  const registrar = async (alertar) => {
    const telefono = (campo('delivery-phone')?.value || '').trim();
    if (!telefono) return;
    const acepta = Boolean(campo('cliente-acepta-mensajes')?.checked);
    if (campo('cliente-acepta-mensajes')) campo('cliente-acepta-mensajes').checked = false;
    try {
      const response = await fetch('/api/gastronomia/bi/consentimiento', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
        body: JSON.stringify({celular: telefono, acepta}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const texto = `Último pedido: ${data.mensaje || 'no se pudo registrar la casilla de consentimiento.'}`;
        avisar(texto, false);
        alertar?.(texto, false);
        return;
      }
      const mensaje = MENSAJES[data.estado];
      if (!mensaje) return;
      avisar(mensaje.texto, mensaje.ok);
      if (!mensaje.ok) alertar?.(mensaje.texto, false);
    } catch (error) {
      const texto = 'Último pedido: no se pudo registrar la casilla de consentimiento. Revisá la conexión.';
      avisar(texto, false);
      alertar?.(texto, false);
    }
  };

  window.GastronomiaConsentimiento = {sincronizar, registrar};
})();
