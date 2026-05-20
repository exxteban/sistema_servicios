import json
import re
import subprocess
from datetime import date, timedelta
from decimal import Decimal

from app import create_app, db
from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO, CLAVE_VENTAS_CREDITO_METODO_PAGO_ID
from cobranzas.services.cuotas_service import estimar_resumen_plan_credito


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def _abrir_caja_admin():
    admin = Usuario.query.filter_by(username='admin').first()
    assert admin is not None
    sesion = SesionCaja(
        id_caja=1,
        id_usuario=admin.id_usuario,
        monto_inicial=250000,
        estado='abierta',
    )
    db.session.add(sesion)
    db.session.commit()


def _extraer_script_pos(html):
    scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
    for script in scripts:
        if 'function posApp()' in script and 'resumenCreditoCuotas()' in script:
            return script
    raise AssertionError('No se encontro el script principal del POS')


def _evaluar_resumen_credito_cuotas_js(script_pos, casos):
    runner = r"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(0, 'utf8');
const casos = JSON.parse(process.argv[1]);
const sandbox = {
  window: {},
  document: {},
  navigator: { onLine: true },
  sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  performance: { now() { return 0; } },
  console,
  fetch: async () => ({ ok: true, json: async () => ({}) }),
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
app.esVentaCredito = () => true;
const resultados = casos.map((caso) => {
  app.creditoModo = 'cuotas';
  app.creditoCuotas = caso.cuotas;
  app.creditoTasaInteresPct = caso.tasa;
  app.montoFinanciadoActual = () => caso.monto;
  return app.resumenCreditoCuotas();
});
process.stdout.write(JSON.stringify(resultados));
"""
    result = subprocess.run(
        ['node', '-e', runner, json.dumps(casos)],
        input=script_pos,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
    )
    return json.loads(result.stdout)


def _evaluar_rebalanceo_pagos_js(script_pos):
    runner = r"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(0, 'utf8');
const sandbox = {
  window: {},
  document: {},
  navigator: { onLine: true },
  sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  performance: { now() { return 0; } },
  console,
  fetch: async () => ({ ok: true, json: async () => ({}) }),
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
app.total = 65;
app.saldoPendiente = 65;
app.carrito = [{ id_producto: 1, cantidad: 1, precio: 65 }];
app.pagos = [];
app.creditoMetodoPagoId = null;
app.condicionVenta = 'contado';
app.agregarPago(1, 'Efectivo');
app.agregarPago(2, 'Tarjeta de Crédito');
app.pagos[1].monto = 15;
app.pagos[1].auto = false;
app.recalcularPagosTrasEditarMonto();
process.stdout.write(JSON.stringify({
  pagos: app.pagos,
  totalPagado: app.totalPagado,
  saldoPendiente: app.saldoPendiente,
  vuelto: app.vuelto,
}));
"""
    result = subprocess.run(
        ['node', '-e', runner],
        input=script_pos,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
    )
    return json.loads(result.stdout)


def _evaluar_limite_pago_mixto_js(script_pos):
    runner = r"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(0, 'utf8');
const notificaciones = [];
const sandbox = {
  window: {},
  document: {},
  navigator: { onLine: true },
  sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  performance: { now() { return 0; } },
  console,
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  mostrarNotificacion(mensaje, tipo) { notificaciones.push({ mensaje, tipo }); },
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
app.total = 65;
app.saldoPendiente = 65;
app.carrito = [{ id_producto: 1, cantidad: 1, precio: 65 }];
app.pagos = [];
app.creditoMetodoPagoId = null;
app.condicionVenta = 'contado';
app.agregarPago(1, 'Efectivo');
app.agregarPago(2, 'Tarjeta de Crédito');
app.pagos[1].monto = 80;
app.manejarInputMontoPago(1);
const trasExceso = app.pagos.map(pago => ({ nombre: pago.nombre, monto: pago.monto, auto: pago.auto === true }));
app.pagos[1].monto = 0;
app.manejarInputMontoPago(1);
const trasBorrar = app.pagos.map(pago => ({ nombre: pago.nombre, monto: pago.monto, auto: pago.auto === true }));
process.stdout.write(JSON.stringify({
  trasExceso,
  trasBorrar,
  totalPagado: app.totalPagado,
  saldoPendiente: app.saldoPendiente,
  vuelto: app.vuelto,
  notificaciones,
}));
"""
    result = subprocess.run(
        ['node', '-e', runner],
        input=script_pos,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
    )
    return json.loads(result.stdout)


def test_pos_oculta_panel_credito_si_flag_esta_apagado():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Condicion de venta' not in html
    assert 'Cuenta corriente' not in html
    assert 'Cobrar saldo' not in html


def test_pos_muestra_panel_credito_simple_si_flag_esta_activo():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Condicion de venta' in html
    assert 'Cuenta corriente' in html
    assert 'Cuotas' in html
    assert 'Cantidad de cuotas' in html
    assert 'Consultando deuda del cliente' in html
    assert 'Cobrar saldo' in html


def test_pos_script_persiste_y_restaura_credito_en_cuotas():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'creditoCuotas: this.creditoCuotas' in html
    assert 'creditoFrecuenciaDias: this.creditoFrecuenciaDias' in html
    assert 'creditoPrimerVencimiento: this.creditoPrimerVencimiento' in html
    assert 'creditoTasaInteresPct: this.creditoTasaInteresPct' in html
    assert "estado.creditoModo === 'cuenta_corriente' || estado.creditoModo === 'cuotas'" in html
    assert 'formatearFechaLocalInput(fecha)' in html
    assert 'Interes por cuota (%)' in html
    assert 'Interes total' in html
    assert 'Total en cuotas' in html
    assert 'montoComprometidoCreditoActual()' in html
    assert 'clientePuedeCubrirCompromisoCredito()' in html
    assert 'mensajeCreditoInsuficienteActual()' in html
    assert 'Saldo financiado' in html
    assert 'Limite de credito' in html
    assert 'Credito disponible' in html
    assert 'Editar limite de credito' in html
    assert 'guardarLimiteCreditoCliente()' in html
    assert '/clientes/${clienteId}/limite_credito_json' in html
    assert 'async refrescarResumenCreditoCliente(clienteId)' in html
    assert 'await this.refrescarResumenCreditoCliente(clienteVentaId);' in html
    assert 'esVentaCreditoPendiente(payload = null)' in html
    assert 'Las ventas a credito requieren conexion estable. Reintente cuando el POS vuelva a estar online.' in html
    assert 'redondearDecimalCredito(valor, decimales = 2)' in html
    assert 'construirCalendarioCreditoCuotas(montoFinanciado, cantidadCuotas, tasaInteresPct)' in html


def test_pos_resumen_credito_cuotas_replica_redondeo_backend():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    script_pos = _extraer_script_pos(response.get_data(as_text=True))
    casos = [
        {'monto': 90000, 'cuotas': 3, 'tasa': 0},
        {'monto': 100000, 'cuotas': 12, 'tasa': 3.5},
        {'monto': 1000000, 'cuotas': 60, 'tasa': 2.75},
        {'monto': 123456, 'cuotas': 36, 'tasa': 1.99},
    ]
    resultados_js = _evaluar_resumen_credito_cuotas_js(script_pos, casos)

    for caso, resumen_js in zip(casos, resultados_js):
        resumen_backend = estimar_resumen_plan_credito(
            Decimal(str(caso['monto'])),
            cantidad_cuotas=int(caso['cuotas']),
            fecha_primer_vencimiento=date.today() + timedelta(days=30),
            frecuencia_dias=30,
            tasa_interes_pct=Decimal(str(caso['tasa'])),
            sistema_amortizacion='frances',
        )
        cuota_inicial = resumen_backend['calendario_cuotas'][0]['monto_programado']

        assert round(float(resumen_js['totalConInteres']), 2) == round(float(resumen_backend['monto_total_con_interes']), 2)
        assert round(float(resumen_js['interesTotal']), 2) == round(float(resumen_backend['monto_total_interes']), 2)
        assert round(float(resumen_js['cuotaEstimada']), 2) == round(float(cuota_inicial), 2)


def test_pos_recalcula_precios_al_restaurar_cliente_mayorista():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'window.posApp = function patchedPosApp()' in html
    assert 'restaurarEstadoConPrecioSincronizado' in html


def test_pos_rebalancea_pago_automatico_al_editar_pago_mixto():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    script_pos = _extraer_script_pos(response.get_data(as_text=True))
    resultado = _evaluar_rebalanceo_pagos_js(script_pos)

    assert round(float(resultado['totalPagado']), 2) == 65.0
    assert round(float(resultado['saldoPendiente']), 2) == 0.0
    assert round(float(resultado['vuelto']), 2) == 0.0
    assert len(resultado['pagos']) == 2

    pagos = {pago['nombre']: round(float(pago['monto']), 2) for pago in resultado['pagos']}
    assert pagos['Efectivo'] == 50.0
    assert pagos['Tarjeta de Crédito'] == 15.0


def test_pos_limita_monto_en_pago_mixto_y_conserva_filas_al_borrar():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    script_pos = _extraer_script_pos(response.get_data(as_text=True))
    resultado = _evaluar_limite_pago_mixto_js(script_pos)

    pagos_exceso = {pago['nombre']: round(float(pago['monto']), 2) for pago in resultado['trasExceso']}
    assert pagos_exceso['Tarjeta de Crédito'] == 65.0
    assert pagos_exceso['Efectivo'] == 0.0
    assert len(resultado['trasExceso']) == 2

    pagos_borrar = {pago['nombre']: round(float(pago['monto']), 2) for pago in resultado['trasBorrar']}
    assert pagos_borrar['Tarjeta de Crédito'] == 0.0
    assert pagos_borrar['Efectivo'] == 65.0
    assert len(resultado['trasBorrar']) == 2

    assert round(float(resultado['totalPagado']), 2) == 65.0
    assert round(float(resultado['saldoPendiente']), 2) == 0.0
    assert round(float(resultado['vuelto']), 2) == 0.0
    assert any('supera lo pendiente' in (item['mensaje'] or '').lower() for item in resultado['notificaciones'])


def test_pos_mantiene_credito_si_metodo_fue_renombrado_pero_sigue_configurado_por_id():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        _abrir_caja_admin()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Crédito Tienda%')).first()
        assert metodo_credito is not None
        metodo_credito_id = int(metodo_credito.id_metodo_pago)
        Configuracion.establecer(CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, str(metodo_credito_id))
        metodo_credito.nombre = 'Financiacion Interna POS'
        db.session.commit()

    response = client.get('/ventas/pos')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Condicion de venta' in html
    assert 'Cuenta corriente' in html
    assert f'"id_metodo_pago": {metodo_credito_id}' in html
    assert 'Financiacion Interna POS' in html


def test_limite_credito_json_actualiza_solo_el_limite():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        cliente = Cliente(
            nombre='Cliente Limite Puntual',
            ruc_ci='1234567-8',
            telefono='099100200',
            direccion='Direccion Original',
            email='cliente@example.com',
            tipo='mayorista',
            notas='No tocar',
            limite_credito=100000,
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()
        cliente_id = int(cliente.id_cliente)

    response = client.post(
        f'/clientes/{cliente_id}/limite_credito_json',
        json={'limite_credito': 250000},
    )

    assert response.status_code == 200
    data = response.get_json() or {}
    assert data.get('success') is True

    with app.app_context():
        cliente_db = db.session.get(Cliente, cliente_id)
        assert cliente_db is not None
        assert float(cliente_db.limite_credito or 0) == 250000.0
        assert cliente_db.telefono == '099100200'
        assert cliente_db.direccion == 'Direccion Original'
        assert cliente_db.email == 'cliente@example.com'
        assert cliente_db.tipo == 'mayorista'
        assert cliente_db.notas == 'No tocar'
