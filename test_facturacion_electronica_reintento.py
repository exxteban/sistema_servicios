"""Botón "Reintentar emisión" con el motor propio.

Con la API, emitir de nuevo ya reenvía. Con el motor propio, `emitir` sólo
regenera, firma y arma el QR, y el envío queda para el job. Al reintentar una
rechazada, el envío tiene que salir en el mismo clic; en una venta nueva, no:
el POS no espera a SIFEN.
"""
import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app, db
from app.models import Cliente, SesionCaja, Usuario, Venta
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_RECHAZADO,
    TIPO_FACTURA,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services import reintento

PROPIO = {'herramientas_propias': True}
API = {'herramientas_propias': False}


class TestReintentoEmision(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        admin = Usuario.query.filter_by(username='admin').first()
        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        self.venta = Venta(
            id_cliente=db.session.get(Cliente, 1).id_cliente,
            id_sesion_caja=sesion.id_sesion,
            subtotal=100000, total=100000, estado='completada',
            fecha_venta=datetime.utcnow(),
        )
        db.session.add(self.venta)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _documento(self, estado):
        documento = DocumentoElectronico(
            id_venta=self.venta.id_venta, tipo_documento=TIPO_FACTURA,
            numero='0000001', estado=estado, cdc='0' * 44,
        )
        db.session.add(documento)
        db.session.commit()
        return documento

    def _emitir(self, caps):
        with patch.object(reintento, 'capacidades', return_value=caps), \
                patch.object(reintento, 'emitir_para_pos') as emitir, \
                patch.object(reintento, 'enviar_documento') as enviar:
            emitir.side_effect = lambda venta: (self._firmado(), None)
            enviar.side_effect = lambda doc: (doc, None)
            reintento.emitir_o_reintentar(self.venta)
        return emitir, enviar

    def _firmado(self):
        documento = reintento.obtener_documento(self.venta.id_venta)
        if documento is not None:
            documento.estado = ESTADO_FIRMADO
        return documento

    def test_rechazada_con_motor_propio_se_reenvia_en_el_mismo_clic(self):
        self._documento(ESTADO_RECHAZADO)

        emitir, enviar = self._emitir(PROPIO)

        emitir.assert_called_once()
        enviar.assert_called_once()

    def test_error_con_motor_propio_tambien_se_reenvia(self):
        self._documento(ESTADO_ERROR)

        _emitir, enviar = self._emitir(PROPIO)

        enviar.assert_called_once()

    def test_venta_nueva_no_se_envia_en_linea(self):
        """Primera emisión: el envío lo hace el job, como en el POS."""
        _emitir, enviar = self._emitir(PROPIO)

        enviar.assert_not_called()

    def test_con_la_api_emitir_ya_es_el_reintento(self):
        self._documento(ESTADO_RECHAZADO)

        emitir, enviar = self._emitir(API)

        emitir.assert_called_once()
        enviar.assert_not_called()

    def test_el_boton_aparece_solo_en_los_fallidos(self):
        self.assertTrue(reintento.puede_reintentar(self._documento(ESTADO_RECHAZADO), self.venta))

    def test_aprobado_no_se_reintenta(self):
        self.assertFalse(reintento.puede_reintentar(self._documento(ESTADO_APROBADO), self.venta))

    def test_venta_anulada_no_se_reintenta(self):
        """El número ya está perdido: lo que corresponde es inutilizarlo."""
        documento = self._documento(ESTADO_RECHAZADO)
        self.venta.estado = 'anulada'
        db.session.commit()

        self.assertFalse(reintento.puede_reintentar(documento, self.venta))

    def _vista_previa(self):
        from app.models import Configuracion
        from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        db.session.commit()
        admin = Usuario.query.filter_by(username='admin').first()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(admin.id_usuario)
            sesion['_fresh'] = True
        respuesta = cliente.get(f'/facturacion-electronica/vista-previa?venta={self.venta.id_venta}')
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.get_data(as_text=True)

    def test_la_vista_previa_del_motor_propio_dibuja_el_boton(self):
        self._documento(ESTADO_RECHAZADO)

        html = self._vista_previa()

        self.assertIn('Reintentar emisión', html)
        self.assertIn(f'/emitir-completo/{self.venta.id_venta}', html)

    def test_la_vista_previa_sin_fallo_no_lo_dibuja(self):
        self._documento(ESTADO_APROBADO)

        self.assertNotIn('Reintentar emisión', self._vista_previa())

    def _vista_previa_api(self):
        capacidades_api = {
            'herramientas_propias': False, 'numeracion_local': True,
            'notas_credito': False, 'inutilizacion': True,
        }
        with patch('facturacion_electronica.routes.capacidades', return_value=capacidades_api):
            return self._vista_previa()

    def test_en_la_api_una_aprobada_no_ofrece_emitir(self):
        """El servicio se negaba igual, pero el botón sólo servía para mostrar un error."""
        self._documento(ESTADO_APROBADO)

        html = self._vista_previa_api()

        self.assertNotIn(f'/emitir-completo/{self.venta.id_venta}', html)

    def test_en_la_api_una_cancelada_ofrece_volver_a_facturar(self):
        """Emite otra factura con número nuevo: el botón lo dice y pide confirmación."""
        self._documento(ESTADO_CANCELADO)

        html = self._vista_previa_api()

        self.assertIn('Volver a facturar', html)
        self.assertIn('otro número', html)

    def test_en_la_api_una_venta_anulada_no_se_vuelve_a_facturar(self):
        self._documento(ESTADO_CANCELADO)
        self.venta.estado = 'anulada'
        db.session.commit()

        self.assertNotIn(f'/emitir-completo/{self.venta.id_venta}', self._vista_previa_api())


if __name__ == '__main__':
    unittest.main()
