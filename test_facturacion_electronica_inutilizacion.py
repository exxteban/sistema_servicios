"""Inutilización de números quemados: el evento que cierra el hueco del timbrado.

Un número se quema cuando el DE reservó correlativo y nunca llegó a SIFEN. No
se puede cancelar —cancelar necesita un CDC aprobado del otro lado—, así que
sin este evento el timbrado queda con un salto que nadie puede explicar.
"""
from datetime import datetime
from types import SimpleNamespace

from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_INUTILIZADO,
    TIPO_FACTURA,
)
from facturacion_electronica.services.emision_service import inutilizar_documento


def _doc(estado, **kwargs):
    base = dict(
        estado=estado, numero='0000007', establecimiento='001', punto='001',
        timbrado='80178105', tipo_documento=TIPO_FACTURA,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_inutilizar_sin_documento():
    _d, error = inutilizar_documento(None, 'motivo valido')
    assert error and 'No hay documento' in error


def test_inutilizar_ya_inutilizado():
    _d, error = inutilizar_documento(_doc(ESTADO_INUTILIZADO), 'motivo valido')
    assert error and 'ya está inutilizado' in error


def test_no_se_inutiliza_un_numero_que_sifen_ya_tiene():
    """El caso peligroso: inutilizar un número usado le diría a SIFEN que un
    documento que sí existe no existe."""
    for estado in (ESTADO_ENVIADO, ESTADO_APROBADO, ESTADO_CANCELADO):
        _d, error = inutilizar_documento(_doc(estado), 'motivo valido')
        assert error and 'ya salió hacia SIFEN' in error, estado


def test_inutilizar_motivo_corto():
    _d, error = inutilizar_documento(_doc(ESTADO_GENERADO), 'abc')
    assert error and 'entre 5 y 500' in error


def test_sin_numero_no_hay_nada_que_inutilizar():
    """Un DE que falló antes de reservar correlativo no quemó ningún número."""
    _d, error = inutilizar_documento(_doc(ESTADO_ERROR, numero=None), 'motivo valido')
    assert error and 'no llegó a reservar un número' in error


# --------------------------------------------------------------------------
# Lo que sólo se ve con la base y la configuración de verdad.
# --------------------------------------------------------------------------

import unittest
from unittest.mock import patch

from app import create_app, db


APROBACION_SIFEN = {
    'ns2:rRetEnviEventoDe': {
        'ns2:gResProcEVe': {
            'ns2:dEstRes': 'Aprobado',
            'ns2:gResProc': {'ns2:dCodRes': '0600', 'ns2:dMsgRes': 'Evento registrado'},
        },
    },
}

RECHAZO_SIFEN = {
    'ns2:rRetEnviEventoDe': {
        'ns2:gResProcEVe': {
            'ns2:dEstRes': 'Rechazado',
            'ns2:gResProc': {'ns2:dCodRes': '0100', 'ns2:dMsgRes': 'Error Inesperado'},
        },
    },
}


class TestInutilizacionContraElServicio(unittest.TestCase):
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
        self.venta = Venta(
            id_cliente=db.session.get(Cliente, 1).id_cliente,
            id_sesion_caja=sesion.id_sesion,
            subtotal=100000, total=100000,
            fecha_venta=datetime.utcnow(), estado='completada',
        )
        db.session.add(self.venta)
        db.session.flush()
        # El caso real: se generó y se firmó, y nunca se transmitió.
        self.documento = DocumentoElectronico(
            id_venta=self.venta.id_venta, tipo_documento=TIPO_FACTURA,
            estado=ESTADO_FIRMADO, numero='0000007', establecimiento='001',
            punto='001', timbrado='80178105',
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

    def test_se_informa_un_solo_numero_y_con_su_propio_timbrado(self):
        """El rango es de uno: los huecos no son contiguos salvo por
        casualidad, y un rango que abarque un número emitido al medio lo
        inutilizaría sin que nadie lo pida. El timbrado es el del documento,
        no el de hoy: un timbrado nuevo no puede inutilizar números del viejo.
        """
        from facturacion_electronica.services import emision_service, eventos_service

        self.documento.timbrado = '19128252'
        db.session.commit()

        with patch.object(eventos_service, 'inutilizar_de',
                          return_value=(APROBACION_SIFEN, '<rEve/>', None)) as mock:
            _doc_, error = emision_service.inutilizar_documento(
                self.documento, 'Corte de energia antes de transmitir',
            )

        self.assertIsNone(error)
        data = mock.call_args.args[1]
        self.assertEqual(data['desde'], 7)
        self.assertEqual(data['hasta'], 7)
        self.assertEqual(data['timbrado'], '19128252')
        self.assertEqual(data['establecimiento'], '001')
        self.assertEqual(data['punto'], '001')
        self.assertEqual(data['tipoDocumento'], TIPO_FACTURA)

    def test_la_fecha_de_firma_va_en_hora_de_paraguay(self):
        """Mismo problema de zona horaria que la cancelación: el Node escribe
        `dFecFirma` con la hora de su proceso y sin offset."""
        from facturacion_electronica.services import emision_service, eventos_service
        from app.utils.helpers import now_local

        with patch.object(eventos_service, 'inutilizar_de',
                          return_value=(APROBACION_SIFEN, '<rEve/>', None)) as mock:
            emision_service.inutilizar_documento(self.documento, 'Numero quemado')

        enviada = mock.call_args.kwargs['fecha_firma']
        self.assertRegex(enviada, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')
        self.assertEqual(enviada[:13], now_local().strftime('%Y-%m-%dT%H'))

    def test_timbrado_invalido_se_frena_antes_de_llamar(self):
        """xmlgen exige 8 caracteres y tira un Error genérico; el emisor tiene
        que leer cuál es el problema."""
        from facturacion_electronica.services import emision_service, eventos_service

        self.documento.timbrado = '123'
        db.session.commit()

        with patch.object(eventos_service, 'inutilizar_de') as mock:
            _doc_, error = emision_service.inutilizar_documento(
                self.documento, 'Numero quemado',
            )

        self.assertIn('8 dígitos', error)
        mock.assert_not_called()

    def test_el_rechazo_no_marca_el_numero_como_inutilizado(self):
        from facturacion_electronica.services import emision_service, eventos_service

        with patch.object(eventos_service, 'inutilizar_de',
                          return_value=(RECHAZO_SIFEN, '<rEve>firmado</rEve>', None)):
            _doc_, error = emision_service.inutilizar_documento(
                self.documento, 'Numero quemado',
            )

        self.assertIn('no aprobó la inutilización', error)
        self.assertEqual(self.documento.estado, ESTADO_FIRMADO)
        self.assertEqual(self.documento.respuesta_codigo, '0100')
        # El XML del evento se guarda igual: es lo único que dice qué se mandó.
        self.assertEqual(self.documento.xml_cancelacion, '<rEve>firmado</rEve>')

    def test_aprobada_la_venta_se_puede_volver_a_facturar(self):
        """El número viejo queda inutilizado como historial y la venta arranca
        un DE nuevo. Sin esto la venta quedaba trabada para siempre, porque
        `inutilizado` es un estado no regenerable."""
        from facturacion_electronica.services import emision_service, eventos_service, generacion_service

        with patch.object(eventos_service, 'inutilizar_de',
                          return_value=(APROBACION_SIFEN, '<rEve/>', None)):
            _doc_, error = emision_service.inutilizar_documento(
                self.documento, 'Corte de energia antes de transmitir',
            )

        self.assertIsNone(error)
        self.assertEqual(self.documento.estado, ESTADO_INUTILIZADO)
        self.assertIsNotNone(self.documento.fecha_cancelado)

        with patch.object(generacion_service, 'generar_xml',
                          return_value=('<DE Id="01801781050010010000008"/>', None)):
            nuevo, error = emision_service.generar_documento(self.venta)

        self.assertIsNone(error)
        self.assertNotEqual(nuevo.id, self.documento.id)
        # Número nuevo: el quemado no se reusa.
        self.assertNotEqual(nuevo.numero, '0000007')
