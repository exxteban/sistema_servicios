from app import create_app, db
from app.models import Categoria, Producto, ProductoPrecioOpcion, Servicio, Usuario


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def test_pos_catalogo_bootstrap_expone_productos_servicios_y_opciones():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        categoria = Categoria(nombre='POS Offline', activo=True)
        db.session.add(categoria)
        db.session.flush()

        producto = Producto(
            codigo='OFF-001',
            nombre='Producto Offline',
            id_categoria=categoria.id_categoria,
            precio_compra=1000,
            precio_venta=2500,
            porcentaje_iva=10,
            stock_actual=7,
            stock_minimo=2,
            activo=True,
        )
        db.session.add(producto)
        db.session.flush()
        db.session.add(ProductoPrecioOpcion(
            id_producto=producto.id_producto,
            etiqueta='Promo',
            precio=2200,
            orden=1,
            activo=True,
        ))

        servicio = Servicio(
            codigo='SRV-OFF',
            nombre='Servicio Offline',
            categoria='POS Offline',
            precio=5000,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.commit()

    response = client.get('/ventas/catalogo/bootstrap')

    assert response.status_code == 200
    data = response.get_json() or {}
    assert data.get('success') is True
    items = data.get('items') or []
    producto_item = next(item for item in items if item.get('codigo') == 'OFF-001')
    servicio_item = next(item for item in items if item.get('codigo') == 'SRV-OFF')

    assert producto_item['tipo'] == 'producto'
    assert producto_item['precio'] == 2500.0
    assert producto_item['stock'] == 7
    assert producto_item['precios_opciones'][0]['etiqueta'] == 'Promo'
    assert servicio_item['tipo'] == 'servicio'
    assert servicio_item['es_servicio'] is True


def _script_pos_renderizado():
    import re

    from test_ventas_pos_credito_ui import _abrir_caja_admin

    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)
    with app.app_context():
        _abrir_caja_admin()
    response = client.get('/ventas/pos')
    assert response.status_code == 200
    for script in re.findall(r'<script>(.*?)</script>', response.get_data(as_text=True), re.S):
        if 'function posApp()' in script and 'POSOfflineColaDB' in script:
            return script
    raise AssertionError('No se encontro el script principal del POS')


_SANDBOX_JS = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(0, 'utf8');
const enviados = [];
let respuestas = [];
const sandbox = {
  window: {},
  document: {},
  navigator: { onLine: true },
  sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  performance: { now() { return 0; } },
  console: { ...console, warn() {} },
  AbortController,
  fetch: async (url, init) => {
    enviados.push({ url: String(url), body: init && init.body ? JSON.parse(init.body) : null });
    const r = respuestas.shift();
    if (r instanceof Error) throw r;
    return { ok: true, status: 200, json: async () => r };
  },
  mostrarNotificacion() {},
  setTimeout() { return 0; },
  clearTimeout() {},
  setInterval() { return 0; },
  clearInterval() {},
  requestAnimationFrame() { return 0; },
  cancelAnimationFrame() {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const app = sandbox.window.posApp();
"""


def _correr_js(script_pos, cuerpo):
    import json
    import subprocess

    result = subprocess.run(
        ['node', '-e', _SANDBOX_JS + cuerpo],
        input=script_pos,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
    )
    return json.loads(result.stdout)


def test_venta_cortada_por_timeout_se_encola_con_el_mismo_client_request_id():
    resultado = _correr_js(_script_pos_renderizado(), r"""
const encoladas = [];
app._validarVendedorSeleccionado = () => true;
app._validarVueltoAntesDeProcesar = () => true;
app.feSolicitada = () => false;
app.isOnline = true;
app.construirPayloadVenta = (id) => ({ items: [{ id_producto: 1, cantidad: 1, precio: 100 }], pagos: [{ monto: 100 }], client_request_id: id });
app.guardarVentaPendiente = (payload, id) => encoladas.push({ id, payloadId: payload.client_request_id });
respuestas = [Object.assign(new Error('timeout'), { name: 'AbortError' })];
(async () => {
  await app.ejecutarVenta();
  process.stdout.write(JSON.stringify({ enviados, encoladas }));
})();
""")

    enviado = [e for e in resultado['enviados'] if '/ventas/procesar' in e['url']]
    assert len(enviado) == 1
    assert len(resultado['encoladas']) == 1
    id_enviado = enviado[0]['body']['client_request_id']
    assert resultado['encoladas'][0]['id'] == id_enviado
    assert resultado['encoladas'][0]['payloadId'] == id_enviado


def test_venta_confirmada_no_se_encola_si_falla_algo_despues():
    resultado = _correr_js(_script_pos_renderizado(), r"""
const encoladas = [];
app._validarVendedorSeleccionado = () => true;
app._validarVueltoAntesDeProcesar = () => true;
app.feSolicitada = () => false;
app.isOnline = true;
app.construirPayloadVenta = (id) => ({ items: [{ id_producto: 1, cantidad: 1, precio: 100 }], pagos: [{ monto: 100 }], client_request_id: id });
app.guardarVentaPendiente = (payload, id) => encoladas.push(id);
app.imprimirTicketVenta = async () => { throw new Error('impresora'); };
respuestas = [{ success: true, id_venta: 10 }];
(async () => {
  await app.ejecutarVenta();
  process.stdout.write(JSON.stringify({ encoladas, procesando: app.procesando }));
})();
""")

    assert resultado['encoladas'] == []
    assert resultado['procesando'] is False


def test_reintento_de_enviar_a_caja_sin_respuesta_reusa_el_client_request_id():
    resultado = _correr_js(_script_pos_renderizado(), r"""
app.carrito = [{ tipo: 'producto', id_producto: 1, cantidad: 2, precio: 100, nombre: 'Cafe', codigo: 'C1' }];
app.cajaFlujoEnviadoActivo = true;
app.puedeEnviarCajaVenta = true;
app.reparacionId = null;
app.isOnline = true;
app._validarVendedorSeleccionado = () => true;
respuestas = [
  new TypeError('Failed to fetch'),
  { success: false, error: 'rechazado' },
  { success: false, error: 'rechazado' },
];
(async () => {
  await app.enviarVentaACaja();
  await app.enviarVentaACaja();
  await app.enviarVentaACaja();
  const ids = enviados.filter(e => e.url.includes('/ventas/enviar-a-caja')).map(e => e.body.client_request_id);
  process.stdout.write(JSON.stringify({ ids }));
})();
""")

    ids = resultado['ids']
    assert len(ids) == 3
    # El reintento tras un envío sin respuesta reusa el id (el servidor deduplica).
    assert ids[1] == ids[0]
    # Una vez que hubo respuesta, el siguiente envío es nuevo.
    assert ids[2] != ids[1]
