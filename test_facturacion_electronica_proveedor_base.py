"""Andamiaje compartido de las pruebas del proveedor API de FE.

Vive aparte porque las pruebas del switch no entran en un archivo solo sin
pasarse del límite de 600 líneas del repositorio. La clase no empieza con
`Test`, así que pytest no la recoge: sólo la heredan los archivos
`test_facturacion_electronica_proveedor*.py`.
"""
import unittest
from datetime import datetime

from app import create_app, db
from app.models import Venta  # noqa: F401  (registra el mapper que usa DocumentoElectronico)
from facturacion_electronica import ESTADO_FIRMADO
from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.proveedores import api_client


def respuesta_api(estado='PENDING_BATCH', **extra):
    """Documento tal como lo devuelve el alta de la API."""
    base = {
        'id': 'd0c0ffee-0000-4000-8000-000000000001',
        'cdc': '0' * 44,
        'status': estado,
        'status_display': estado.title(),
        'qr_url': 'https://ekuatia.set.gov.py/consultas/qr?x=1',
        'transmits': True,
        'idempotency_key': 'irrelevante',
    }
    base.update(extra)
    return base


class BaseProveedorApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, SesionCaja, Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(admin)
        self.cliente = db.session.get(Cliente, 1)
        self.assertIsNotNone(self.cliente)

        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        self.sesion = sesion

    def tearDown(self):
        from facturacion_electronica.services.proveedores.api import olvidar_perfil

        olvidar_perfil()
        api_client.olvidar_token()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _activar_api(self):
        config = FacturacionElectronicaConfig.obtener()
        config.proveedor = 'api'
        config.api_url = 'https://api.ejemplo.test'
        config.api_client_id = 'cliente-test'
        config.api_credenciales = 'secreto'
        config.establecimiento = '001'
        config.punto_expedicion = '001'
        db.session.commit()
        return config

    def _venta(self):
        venta = Venta(
            id_cliente=self.cliente.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            subtotal=100000,
            total=100000,
            fecha_venta=datetime.utcnow(),
        )
        db.session.add(venta)
        db.session.commit()
        return venta

    def _perfil(self):
        return {
            'ruc': '80012345',
            'sifen_mode': 'test',
            'stamps': [{
                'id': 'aaaaaaaa-0000-4000-8000-000000000001',
                'number': '12345678',
                'establishment': '001',
                'expedition_point': '001',
                'document_type': 1,
                'valid_from': '2026-01-01',
            }],
            'sifen_config': {
                'certificate': {'fingerprint_sha256': 'abc'},
                'csc': 'configured',
            },
        }

    # -- emisión feliz ----------------------------------------------------

    def _documento_en_lote(self, tipo_documento):
        """Documento ya dado de alta en la API y esperando su lote."""
        from facturacion_electronica.models import DocumentoElectronico

        venta = self._venta()
        documento = DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=tipo_documento,
            establecimiento='001',
            punto='001',
            numero='0000001',
            estado=ESTADO_FIRMADO,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
            respuesta_codigo='PENDING_BATCH',
        )
        db.session.add(documento)
        db.session.commit()
        return documento

    def _usar_cliente_identificado(self):
        """Cambia `self.cliente` por uno con cédula, para las pruebas de NC.

        El de la base es el consumidor final (id 1), que viaja innominado, y
        SIFEN rechaza toda nota de crédito con receptor sin identificar.
        """
        from app.models import Cliente

        self.cliente = Cliente(nombre='Alfio Oviedo', ruc_ci='4281292')
        db.session.add(self.cliente)
        db.session.commit()
        return self.cliente

    def _cliente_empresa_sin_dv(self):
        """Empresa cuyo RUC quedó cargado sin dígito verificador."""
        from app.models import Cliente

        cliente = Cliente(nombre='Ferretería SA', ruc_ci='80012345')
        db.session.add(cliente)
        db.session.commit()
        return cliente


__all__ = ['BaseProveedorApi', 'respuesta_api']
