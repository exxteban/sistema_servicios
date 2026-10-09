"""Cada documento lo sigue sólo el proveedor que lo transmitió.

Caso real (2026-10-03, Janelipy en test): con el proveedor pasado de la API
al motor propio, "Consultar estado" sobre la factura 0000203 —emitida por la
API, con su lote todavía en proceso— la consultó por CDC directo a SIFEN,
recibió `0420` y la marcó rechazada sin serlo.
"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import db
from facturacion_electronica import ESTADO_ENVIADO, ESTADO_FIRMADO, ESTADO_GENERADO
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.proveedores import PROVEEDOR_API, PROVEEDOR_PROPIO
from facturacion_electronica.services.proveedores.pertenencia import (
    error_de_otro_proveedor,
    filtro_documentos_del_proveedor,
)
from test_facturacion_electronica_proveedor_base import BaseProveedorApi


def _doc(**extra):
    datos = dict(api_documento_id=None, xml_firmado=None, estado=ESTADO_GENERADO,
                 fecha_envio=None, api_lote_id=None)
    datos.update(extra)
    return SimpleNamespace(**datos)


DE_LA_API = dict(api_documento_id='1c7e748c', estado=ESTADO_ENVIADO)
DEL_PROPIO_EN_LOTE = dict(xml_firmado='<rDE/>', estado=ESTADO_ENVIADO, api_lote_id='81111631107047170',
                          fecha_envio=datetime(2026, 10, 3, 14, 40))
# Generado y firmado por el motor propio, pero nunca salió: no ata a nadie.
DEL_PROPIO_SIN_SALIR = dict(xml_firmado='<rDE/>', estado=ESTADO_FIRMADO)


class TestDeQuienEs(unittest.TestCase):
    def test_el_motor_propio_no_toca_una_factura_de_la_api(self):
        error = error_de_otro_proveedor(_doc(**DE_LA_API), PROVEEDOR_PROPIO)
        self.assertIn('API externa', error)

    def test_la_api_no_toca_una_factura_que_el_propio_ya_mando(self):
        error = error_de_otro_proveedor(_doc(**DEL_PROPIO_EN_LOTE), PROVEEDOR_API)
        self.assertIn('motor propio', error)

    def test_cada_uno_sigue_las_suyas(self):
        self.assertIsNone(error_de_otro_proveedor(_doc(**DE_LA_API), PROVEEDOR_API))
        self.assertIsNone(error_de_otro_proveedor(_doc(**DEL_PROPIO_EN_LOTE), PROVEEDOR_PROPIO))

    def test_lo_que_nunca_salio_lo_puede_emitir_la_api(self):
        self.assertIsNone(error_de_otro_proveedor(_doc(**DEL_PROPIO_SIN_SALIR), PROVEEDOR_API))

    def test_consultar_con_el_proveedor_cambiado_no_llama_a_sifen(self):
        from facturacion_electronica.services.proveedores import fachada

        config = SimpleNamespace(proveedor=PROVEEDOR_PROPIO)
        proveedor = MagicMock()
        with patch('facturacion_electronica.services.config_service.obtener_configuracion',
                   return_value=config), \
                patch.object(fachada, 'obtener_proveedor', return_value=proveedor):
            respuesta, error = fachada.consultar_documento(_doc(**DE_LA_API))

        self.assertIsNone(respuesta)
        self.assertIn('API externa', error)
        proveedor.consultar.assert_not_called()


class TestFiltroDelJob(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        venta = self._venta()
        for i, datos in enumerate((DE_LA_API, DEL_PROPIO_EN_LOTE, DEL_PROPIO_SIN_SALIR), start=1):
            db.session.add(DocumentoElectronico(id=i, id_venta=venta.id_venta, **datos))
        db.session.commit()

    def _ids(self, proveedor):
        return sorted(d.id for d in DocumentoElectronico.query.filter(
            filtro_documentos_del_proveedor(proveedor)))

    def test_el_job_de_cada_proveedor_toma_solo_lo_suyo(self):
        self.assertEqual(self._ids(PROVEEDOR_PROPIO), [2, 3])
        self.assertEqual(self._ids(PROVEEDOR_API), [1, 3])


class TestReintentarConElProveedorCambiado(BaseProveedorApi):
    """Caso real (2026-10-05): la 0000204 del motor propio quedó rechazada con
    su lote vencido; con la API activa, "Reintentar emisión" se la dio a la API
    como una factura nueva y la API contestó 500. Si contestaba bien, el mismo
    número salía por los dos proveedores."""

    def test_la_api_no_reemite_una_factura_rechazada_del_motor_propio(self):
        from facturacion_electronica import ESTADO_RECHAZADO
        from facturacion_electronica.services.proveedores import fachada

        self._activar_api()
        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, **dict(DEL_PROPIO_EN_LOTE, estado=ESTADO_RECHAZADO)))
        db.session.commit()

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar') as solicitar:
            documento, error = fachada.emitir_para_pos(venta)
            _doc, error_generar = fachada.generar_documento(venta)

        self.assertIn('motor propio', error)
        self.assertIn('motor propio', error_generar)
        self.assertEqual(documento.estado, ESTADO_RECHAZADO)
        solicitar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
