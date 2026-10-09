"""Facturar una venta que se cobró sin factura.

El caso de mostrador: "llevame esto" y al rato "¿me la podés facturar?". El
circuito ya existía (`emitir_completo` nunca preguntó si la venta es de hoy),
pero el único botón vivía en Facturación electrónica → Vista previa, a la que
no llegaba ningún enlace desde la venta: había que conocer la URL.

Lo que se prueba es cuándo aparece el botón, que es donde está la regla: la
factura declara la fecha de la **venta** y SIFEN sólo acepta transmitirla
dentro de las 72h.
"""
import unittest
from datetime import datetime, timedelta

from app import create_app, db
from app.models import Cliente, SesionCaja, Usuario, Venta
from facturacion_electronica import ESTADO_APROBADO, ESTADO_CANCELADO, TIPO_FACTURA
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.acciones import acciones_para_venta


class TestFacturarDespues(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        admin = Usuario.query.filter_by(username='admin').first()
        self.cliente = db.session.get(Cliente, 1)
        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        self.sesion = sesion

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _venta(self, hace_horas=0, estado='completada'):
        venta = Venta(
            id_cliente=self.cliente.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            subtotal=100000,
            total=100000,
            estado=estado,
            fecha_venta=datetime.utcnow() - timedelta(hours=hace_horas),
        )
        db.session.add(venta)
        db.session.commit()
        return venta

    def test_la_venta_sin_factura_ofrece_emitirla(self):
        """Lo que faltaba: desde la venta no había ningún camino."""
        acciones = acciones_para_venta(self._venta(hace_horas=5), puede_operar=True)

        self.assertIsNotNone(acciones)
        self.assertTrue(acciones['puede_emitir'])
        self.assertIsNone(acciones['documento'])

    def test_pasadas_las_72h_no_se_ofrece(self):
        """La factura declara la fecha de la venta (`dFeEmiDE`), no la de hoy:
        SIFEN la rechaza por fecha vencida. Mejor no mostrar el botón que
        mostrarlo y fallar después de quemar un número."""
        self.assertIsNone(acciones_para_venta(self._venta(hace_horas=80), puede_operar=True))

    def test_una_venta_anulada_no_se_factura(self):
        self.assertIsNone(
            acciones_para_venta(self._venta(estado='anulada'), puede_operar=True)
        )

    def test_sin_permiso_no_se_dibuja_el_panel(self):
        """Con documento el panel muestra el estado aunque no haya permiso;
        sin documento no hay estado que mostrar."""
        self.assertIsNone(acciones_para_venta(self._venta(), puede_operar=False))

    def test_la_venta_ya_facturada_no_ofrece_emitir_de_nuevo(self):
        """Reintentar es otra cosa y la maneja el job o la vista previa."""
        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000001',
            estado=ESTADO_APROBADO, cdc='0' * 44,
        ))
        db.session.commit()

        acciones = acciones_para_venta(venta, puede_operar=True)

        self.assertFalse(acciones['puede_emitir'])
        self.assertIsNotNone(acciones['documento'])

    def _venta_con_documento(self, estado):
        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000001',
            estado=estado, cdc='0' * 44, qr_url='https://ekuatia.set.gov.py/consultas-test/qr',
        ))
        db.session.commit()
        return venta

    def test_la_factura_vigente_se_puede_reimprimir(self):
        """El historial ofrecía sólo el ticket: el cliente que pide otra copia
        de su factura se llevaba un papel sin valor fiscal."""
        acciones = acciones_para_venta(self._venta_con_documento(ESTADO_APROBADO), puede_operar=True)

        self.assertTrue(acciones['puede_reimprimir_kude'])

    def test_cancelada_y_venta_anulada_no_ofrece_inutilizar(self):
        """Visto en la #136: la factura se aprobó, se canceló y después se anuló
        la venta. La pantalla decía "nunca llegó a SIFEN" y ofrecía inutilizar
        un número que SIFEN ya tiene registrado."""
        venta = self._venta_con_documento(ESTADO_CANCELADO)
        venta.estado = 'anulada'
        db.session.commit()

        acciones = acciones_para_venta(venta, puede_operar=True)

        self.assertFalse(acciones['puede_inutilizar'])

    def test_la_factura_cancelada_no_se_reimprime(self):
        acciones = acciones_para_venta(self._venta_con_documento(ESTADO_CANCELADO), puede_operar=True)

        self.assertFalse(acciones['puede_reimprimir_kude'])


if __name__ == '__main__':
    unittest.main()
