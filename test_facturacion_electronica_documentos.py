"""Pantalla "Facturas electrónicas": el listado de documentos emitidos.

Pedido de Janelipy (2026-09-25): ver en un solo lugar todas las facturas, su
estado y si se aprobaron, y llegar desde ahí a la venta (KuDE, XML, cancelar,
inutilizar). También la usa el contador, que tiene `ver_reportes` pero no
permiso de configuración.
"""
import unittest
from datetime import datetime, timedelta

from app import db
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_FIRMADO,
    ESTADO_RECHAZADO,
    TIPO_FACTURA,
)
from facturacion_electronica.models import DocumentoElectronico

from test_facturacion_electronica_proveedor_base import BaseProveedorApi


def _periodo():
    """Unos días alrededor de hoy: con "el mes en curso" la prueba fallaría de
    noche el día 1 (la venta en UTC ya es del día siguiente en Asunción)."""
    from app.utils.helpers import today_local

    hoy = today_local()
    return f'desde={(hoy - timedelta(days=3)).isoformat()}&hasta={(hoy + timedelta(days=1)).isoformat()}'


class TestListadoDocumentos(BaseProveedorApi):
    def _modulo(self, activo=True):
        from app.models import Configuracion
        from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true' if activo else 'false')
        db.session.commit()

    def _logueado(self, usuario=None):
        from app.models import Usuario

        usuario = usuario or Usuario.query.filter_by(username='admin').first()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(usuario.id_usuario)
            sesion['_fresh'] = True
        return cliente

    def _documento(self, numero, estado, total=100000, hace_dias=0, mensaje=None):
        venta = self._venta()
        venta.total = total
        venta.fecha_venta = datetime.utcnow() - timedelta(days=hace_dias)
        documento = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, establecimiento='001',
            punto='001', numero=numero, estado=estado, ambiente='test',
            respuesta_mensaje=mensaje,
        )
        db.session.add(documento)
        db.session.commit()
        return documento

    def test_lista_resume_y_marca_lo_que_necesita_atencion(self):
        self._modulo()
        self._documento('0000031', ESTADO_APROBADO, total=313200)
        self._documento('0000032', ESTADO_APROBADO, total=100000)
        self._documento('0000033', ESTADO_FIRMADO)
        rechazada = self._documento('0000034', ESTADO_RECHAZADO,
                                    mensaje='Rechazado por SIFEN: 1311 - DV del receptor inválido')

        html = self._logueado().get(f'/facturacion-electronica/documentos?{_periodo()}').get_data(as_text=True)

        for numero in ('001-001-0000031', '001-001-0000032', '001-001-0000033', '001-001-0000034'):
            self.assertIn(numero, html)
        self.assertIn('₲ 413.200', html)          # facturado aprobado
        self.assertIn('1311 - DV del receptor inválido', html)
        self.assertIn(f'/ventas/{rechazada.id_venta}', html)

    def test_filtra_por_estado_y_por_fecha(self):
        self._modulo()
        self._documento('0000031', ESTADO_APROBADO)
        self._documento('0000034', ESTADO_RECHAZADO)
        self._documento('0000020', ESTADO_APROBADO, hace_dias=40)

        cliente = self._logueado()
        rechazados = cliente.get(f'/facturacion-electronica/documentos?estado=rechazado&{_periodo()}').get_data(as_text=True)
        self.assertIn('001-001-0000034', rechazados)
        self.assertNotIn('001-001-0000031', rechazados)

        # El período por defecto es el mes en curso: la de hace 40 días no entra.
        self.assertNotIn('001-001-0000020',
                         cliente.get('/facturacion-electronica/documentos').get_data(as_text=True))

    def test_exporta_csv_para_el_contador(self):
        self._modulo()
        self._documento('0000031', ESTADO_APROBADO, total=313200)

        respuesta = self._logueado().get(f'/facturacion-electronica/documentos.csv?{_periodo()}')

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('attachment', respuesta.headers['Content-Disposition'])
        texto = respuesta.get_data(as_text=True)
        self.assertTrue(texto.startswith('﻿'))
        self.assertIn('001-001-0000031;', texto)
        self.assertIn(';313200;aprobado;', texto)

    def test_sin_el_modulo_no_entra(self):
        self._modulo(activo=False)

        respuesta = self._logueado().get('/facturacion-electronica/documentos')

        self.assertEqual(respuesta.status_code, 302)


if __name__ == '__main__':
    unittest.main()
