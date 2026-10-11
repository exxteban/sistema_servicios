// Pantalla de progreso en la ventana que la caja abre al cobrar con factura.
// La ventana se abre en el click (para que el navegador no la bloquee) y queda
// en blanco mientras se cobra y se emite; aca se le escribe que esta pasando.
(function () {
  const ETAPAS = [
    ['cobro', 'Registrando el cobro'],
    ['factura', 'Generando y firmando la factura electronica'],
    ['imprimir', 'Abriendo el comprobante para imprimir'],
  ];
  const ICONOS = {pendiente: '○', activa: '', ok: '✓', error: '✕'};

  const pagina = () => `<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Generando factura...</title>
<style>
  body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f3f4f6;color:#111827;
       display:flex;align-items:center;justify-content:center;min-height:100vh}
  .card{background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(15,23,42,.12);padding:28px 32px;width:min(420px,90vw)}
  h1{font-size:18px;margin:0 0 4px} .sub{color:#6b7280;font-size:13px;margin:0 0 20px}
  ol{list-style:none;padding:0;margin:0} li{display:flex;gap:12px;align-items:flex-start;padding:8px 0;font-size:14px;color:#9ca3af}
  li .ico{width:20px;height:20px;flex:0 0 20px;display:inline-flex;align-items:center;justify-content:center;font-weight:700}
  li.activa{color:#111827;font-weight:600} li.ok{color:#047857} li.error{color:#be123c}
  .spin{width:16px;height:16px;border:2px solid #a7f3d0;border-top-color:#059669;border-radius:50%;animation:g 0.8s linear infinite}
  @keyframes g{to{transform:rotate(360deg)}}
  .det{display:block;font-weight:400;font-size:12px;margin-top:2px}
  .foot{margin-top:18px;font-size:12px;color:#6b7280}
</style></head><body><div class="card">
  <h1 id="titulo">Generando factura electronica</h1>
  <p class="sub">No cierre esta ventana. Tiempo transcurrido: <strong id="seg">0</strong> s</p>
  <ol>${ETAPAS.map(([key, label]) => `<li id="et-${key}" class="pendiente"><span class="ico">${ICONOS.pendiente}</span><span>${label}<span class="det"></span></span></li>`).join('')}</ol>
  <p class="foot" id="foot">Puede tardar unos segundos mientras se firma el documento.</p>
</div></body></html>`;

  const segundos = new WeakMap();

  const abrir = (win) => {
    if (!win || win.closed) return;
    try {
      win.document.open();
      win.document.write(pagina());
      win.document.close();
      const inicio = Date.now();
      const timer = setInterval(() => {
        if (win.closed) return clearInterval(timer);
        const el = win.document.getElementById('seg');
        if (!el) return clearInterval(timer);
        el.textContent = String(Math.floor((Date.now() - inicio) / 1000));
      }, 500);
      segundos.set(win, timer);
    } catch (error) {
      // ventana de otro origen o cerrada: se sigue sin progreso
    }
  };

  const etapa = (win, key, estado, detalle = '') => {
    try {
      const li = win && !win.closed ? win.document.getElementById(`et-${key}`) : null;
      if (!li) return;
      li.className = estado;
      li.querySelector('.ico').innerHTML = estado === 'activa' ? '<span class="spin"></span>' : ICONOS[estado];
      li.querySelector('.det').textContent = detalle;
      if (estado === 'error') {
        win.document.getElementById('titulo').textContent = 'No se pudo emitir la factura';
        win.document.getElementById('foot').textContent = 'El cobro quedo registrado. Se imprime el ticket normal y la factura se reintenta sola.';
      }
    } catch (error) {
      // idem
    }
  };

  const terminar = (win) => {
    const timer = segundos.get(win);
    if (timer) clearInterval(timer);
  };

  window.GastroCajaProgreso = {abrir, etapa, terminar};
}());
