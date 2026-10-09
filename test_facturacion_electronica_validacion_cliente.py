"""Alerta de RUC de empresa sin dígito verificador.

Sin el DV el DE saldría con el cliente como cédula/innominado y la empresa
receptora perdería su crédito de IVA. La validación avisa y frena la emisión
ANTES de reservar número, para poder corregir la ficha del cliente y reintentar
sin consumir correlativos.
"""
import unittest

from app.models.cliente import Cliente
from facturacion_electronica.services.validacion import validar_cliente


def test_empresa_con_ruc_sin_dv_alerta():
    cliente = Cliente(id_cliente=5, nombre='COMERCIAL DEL ESTE S.A.', ruc_ci='80012345')
    error = validar_cliente(cliente)
    assert error is not None
    assert 'dígito verificador' in error


def test_ruc_80_sin_dv_alerta_aunque_el_nombre_no_delate():
    cliente = Cliente(id_cliente=6, nombre='Distribuidora Norte', ruc_ci='80054321')
    assert validar_cliente(cliente) is not None


def test_nombre_juridico_sin_dv_alerta():
    cliente = Cliente(id_cliente=7, nombre='FERRETERIA CENTRAL SRL', ruc_ci='3456789')
    assert validar_cliente(cliente) is not None


def test_ruc_con_dv_no_alerta():
    cliente = Cliente(id_cliente=5, nombre='COMERCIAL DEL ESTE S.A.', ruc_ci='80012345-6')
    assert validar_cliente(cliente) is None


def test_persona_fisica_con_cedula_no_alerta():
    cliente = Cliente(id_cliente=8, nombre='Juan Pérez', ruc_ci='4123456')
    assert validar_cliente(cliente) is None


def test_cedula_vieja_del_rango_80_no_alerta():
    # Cédulas de 6-7 dígitos que empiezan con 80 no son RUC de empresa.
    cliente = Cliente(id_cliente=9, nombre='María López', ruc_ci='801234')
    assert validar_cliente(cliente) is None


def test_consumidor_final_no_alerta():
    assert validar_cliente(Cliente(id_cliente=1, nombre='Consumidor Final', ruc_ci=None)) is None
    assert validar_cliente(None) is None


def test_empresa_sin_ruc_no_alerta():
    # Sin ningún documento cargado el DE sale innominado, que es válido.
    cliente = Cliente(id_cliente=10, nombre='EMPRESA X S.A.', ruc_ci='')
    assert validar_cliente(cliente) is None


class TestGenerarDocumentoBloqueaClienteSinDV(unittest.TestCase):
    """La emisión se frena antes de reservar número: la corrección no consume correlativos."""

    def setUp(self):
        from app import create_app, db

        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.db = db

        from app.models import SesionCaja, Usuario
        from app.models.venta import Venta

        cliente = Cliente(nombre='COMERCIAL DEL ESTE S.A.', ruc_ci='80012345')
        db.session.add(cliente)
        db.session.commit()
        self.cliente_id = cliente.id_cliente

        admin = Usuario.query.filter_by(username='admin').first()
        sesion = SesionCaja(id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta')
        db.session.add(sesion)
        db.session.commit()
        self.sesion_id = sesion.id_sesion

        venta = Venta(id_cliente=self.cliente_id, id_sesion_caja=self.sesion_id, subtotal=0, total=0)
        db.session.add(venta)
        db.session.commit()
        self.venta = venta

    def tearDown(self):
        from app.models import SesionCaja
        from app.models.venta import Venta
        from facturacion_electronica.models import DocumentoElectronico

        db = self.db
        db.session.rollback()
        DocumentoElectronico.query.filter_by(id_venta=self.venta.id_venta).delete()
        Venta.query.filter_by(id_venta=self.venta.id_venta).delete()
        Cliente.query.filter_by(id_cliente=self.cliente_id).delete()
        SesionCaja.query.filter_by(id_sesion=self.sesion_id).delete()
        db.session.commit()
        self.ctx.pop()

    def test_marca_error_sin_consumir_numero(self):
        from facturacion_electronica import ESTADO_ERROR
        from facturacion_electronica.services.emision_service import generar_documento
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero

        proximo_antes = peek_proximo_numero('001', '001')

        doc, error = generar_documento(self.venta)
        self.assertIsNotNone(error)
        self.assertIn('dígito verificador', error)
        self.assertEqual(doc.estado, ESTADO_ERROR)
        self.assertEqual(doc.respuesta_mensaje, error)
        self.assertIsNone(doc.numero)
        self.assertIsNone(doc.xml)

        self.assertEqual(peek_proximo_numero('001', '001'), proximo_antes)

    def test_venta_anulada_no_genera_ni_reserva_numero(self):
        from facturacion_electronica.services.emision_service import generar_documento
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero

        self.venta.estado = 'anulada'
        self.db.session.commit()
        proximo_antes = peek_proximo_numero('001', '001')

        doc, error = generar_documento(self.venta)
        self.assertIsNone(doc)
        self.assertIn('anulada', (error or '').lower())
        self.assertEqual(peek_proximo_numero('001', '001'), proximo_antes)



if __name__ == '__main__':
    unittest.main()


def test_innominado_desde_siete_millones_se_frena_antes_de_emitir():
    """NT 024 (regla D208c, rechazo 1321): SIFEN no acepta una factura a un
    receptor sin identificar desde 7.000.000 Gs. xmlgen no lo valida, así que
    sin la guarda el número se consumía y SIFEN rechazaba con la venta hecha."""
    from types import SimpleNamespace

    from facturacion_electronica.services.validacion import validar_monto_innominado

    consumidor_final = SimpleNamespace(id_cliente=1, ruc_ci=None, nombre='Consumidor Final')
    error = validar_monto_innominado(consumidor_final, 7_000_000)
    assert error and '7.000.000' in error

    # Justo debajo del tope pasa.
    assert validar_monto_innominado(consumidor_final, 6_999_950) is None
    # Lo que compara SIFEN es el total redondeado: 7.000.049 declara 7.000.000.
    assert validar_monto_innominado(consumidor_final, 7_000_049)
    # 7.000.049 redondea hacia abajo al múltiplo de 50, pero 6.999.999 queda en
    # 6.999.950, debajo del tope.
    assert validar_monto_innominado(consumidor_final, 6_999_999) is None


def test_un_cliente_identificado_no_tiene_tope():
    from types import SimpleNamespace

    from facturacion_electronica.services.validacion import validar_monto_innominado

    con_cedula = SimpleNamespace(id_cliente=7, ruc_ci='4281292', nombre='Alfio')
    assert validar_monto_innominado(con_cedula, 50_000_000) is None


def test_el_mensaje_del_tope_da_una_salida_que_se_pueda_cumplir():
    """A Consumidor Final no se le puede cargar una cédula, y la venta no se
    puede reasignar a otro cliente: el mensaje tiene que decir anular y
    rehacer. A un cliente real, en cambio, se le completa la ficha."""
    from types import SimpleNamespace

    from facturacion_electronica.services.validacion import validar_monto_innominado

    consumidor_final = SimpleNamespace(id_cliente=1, ruc_ci=None, nombre='Consumidor Final')
    error = validar_monto_innominado(consumidor_final, 8_000_000)
    assert 'anular la venta' in error
    assert 'ficha' not in error

    sin_cedula = SimpleNamespace(id_cliente=9, ruc_ci='', nombre='Ana')
    error = validar_monto_innominado(sin_cedula, 8_000_000)
    assert 'ficha' in error
    assert 'anular' not in error
