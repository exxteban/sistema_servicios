from datetime import datetime, timedelta
from types import SimpleNamespace

from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_GENERADO,
)
from facturacion_electronica.services.emision_service import (
    HORAS_LIMITE_CANCELACION,
    cancelar_documento,
)


def _doc(estado, **kwargs):
    base = dict(estado=estado, cdc='0' * 44, fecha_envio=datetime.utcnow())
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_cancelar_sin_documento():
    _d, error = cancelar_documento(None, 'motivo valido')
    assert error and 'No hay documento' in error


def test_cancelar_ya_cancelado():
    _d, error = cancelar_documento(_doc(ESTADO_CANCELADO), 'motivo valido')
    assert error and 'ya está cancelado' in error


def test_cancelar_solo_aprobado():
    _d, error = cancelar_documento(_doc(ESTADO_GENERADO), 'motivo valido')
    assert error and 'aprobado' in error


def test_cancelar_motivo_corto():
    _d, error = cancelar_documento(_doc(ESTADO_APROBADO), 'abc')
    assert error and 'entre 5 y 500' in error


def test_cancelar_fuera_de_plazo():
    viejo = datetime.utcnow() - timedelta(hours=HORAS_LIMITE_CANCELACION + 1)
    _d, error = cancelar_documento(_doc(ESTADO_APROBADO, fecha_envio=viejo), 'motivo valido')
    assert error and 'nota de crédito' in error


# --------------------------------------------------------------------------
# Lo que sólo se ve con la base y la configuración de verdad: qué se le manda
# al servicio Node y qué queda guardado cuando SIFEN rechaza el evento.
# --------------------------------------------------------------------------

import unittest
from unittest.mock import patch

from app import create_app, db
from app.utils.helpers import now_local


RECHAZO_SIFEN = {
    'ns2:rRetEnviEventoDe': {
        'ns2:dFecProc': '2026-09-20T20:11:26-03:00',
        'ns2:gResProcEVe': {
            'ns2:dEstRes': 'Rechazado',
            'ns2:id': '0',
            'ns2:gResProc': {'ns2:dCodRes': '0100', 'ns2:dMsgRes': 'Error Inesperado'},
        },
    },
}


class TestCancelacionContraElServicio(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, SesionCaja, Usuario, Venta
        from facturacion_electronica.models import (
            DocumentoElectronico,
            FacturacionElectronicaConfig,
        )

        admin = Usuario.query.filter_by(username='admin').first()
        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.flush()
        venta = Venta(
            id_cliente=db.session.get(Cliente, 1).id_cliente,
            id_sesion_caja=sesion.id_sesion,
            subtotal=100000, total=100000,
            fecha_venta=datetime.utcnow(), estado='completada',
        )
        db.session.add(venta)
        db.session.flush()
        self.documento = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=1, estado=ESTADO_APROBADO,
            cdc='0' * 44, numero='0000001', establecimiento='001', punto='001',
        )
        db.session.add(self.documento)

        config = FacturacionElectronicaConfig.obtener()
        config.ruc = '80178105'
        config.dv_ruc = '1'
        config.razon_social = 'Janelipy Group E.A.S.'
        config.timbrado_numero = '80178105'
        config.cert_path = '/fake/cert.p12'
        config.cert_password = 'clave'
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_la_fecha_de_firma_va_en_hora_de_paraguay(self):
        """`dFecFirma` la escribe el Node con la hora de su proceso y sin
        offset: en un servidor en UTC el evento sale firmado tres horas en el
        futuro y SIFEN lo rechaza sin decir por qué."""
        from facturacion_electronica.services import emision_service

        with patch.object(emision_service, 'cancelar_de',
                          return_value=(RECHAZO_SIFEN, '<rEve/>', None)) as mock:
            emision_service.cancelar_documento(self.documento, 'Prueba de cancelacion')

        enviada = mock.call_args.kwargs['fecha_firma']
        self.assertRegex(enviada, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')
        # Sin offset a propósito: `new Date()` del lado Node la lee como hora
        # local y la escribe tal cual. Lo que importa es la hora de Paraguay.
        self.assertEqual(enviada[:13], now_local().strftime('%Y-%m-%dT%H'))

    def test_el_evento_rechazado_queda_guardado(self):
        """Sin esto, un rechazo dejaba el mensaje genérico de SIFEN y nada del
        XML que se firmó, que es lo único que dice qué se mandó."""
        from facturacion_electronica.services import emision_service

        with patch.object(emision_service, 'cancelar_de',
                          return_value=(RECHAZO_SIFEN, '<rEve>firmado</rEve>', None)):
            _doc_, error = emision_service.cancelar_documento(
                self.documento, 'Prueba de cancelacion',
            )

        self.assertIn('no aprobó la cancelación', error)
        self.assertEqual(self.documento.xml_cancelacion, '<rEve>firmado</rEve>')
        self.assertEqual(self.documento.respuesta_codigo, '0100')
        # El documento sigue vigente: SIFEN no lo dio de baja.
        self.assertEqual(self.documento.estado, ESTADO_APROBADO)
        self.assertIsNone(self.documento.fecha_cancelado)
