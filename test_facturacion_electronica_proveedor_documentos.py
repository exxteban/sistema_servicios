"""Documentos del proveedor API: lote, notas de crédito y formas de pago.

Continuación de `test_facturacion_electronica_proveedor.py`; comparte su
andamiaje. Acá está lo que pasa **después** del alta: esperar el lote, la NC
de una devolución, el crédito con su plazo, la validación del cliente, el QR
que sólo viaja en el detalle y el bloque obligatorio de cada medio de pago.
"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app import db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_ERROR, ESTADO_FIRMADO

from test_facturacion_electronica_proveedor_base import BaseProveedorApi, respuesta_api


class TestProveedorApiDocumentos(BaseProveedorApi):
    def test_la_nota_de_credito_tambien_espera_a_su_pipeline(self):
        """No se lotea a mano ningun tipo de documento. La NC llegaba antes a
        `POST /sifen/batches/` con el document_type de la factura, y su
        contrato agrupa solo el tipo que se le manda: quedaba en
        PENDING_BATCH para siempre."""
        from facturacion_electronica.services.proveedores.api import ProveedorApi

        self._activar_api()
        documento = self._documento_en_lote(5)
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append((metodo, ruta))
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='PENDING_BATCH', document_type=5), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            error = ProveedorApi().avanzar(documento)

        self.assertIsNone(error)
        self.assertNotIn(('POST', '/sifen/batches/'), rutas)
        self.assertIsNone(documento.api_lote_id)

    def test_issued_at_viaja_con_offset_horario(self):
        """Sin offset, la fecha queda a merced del TIME_ZONE del servidor
        de ellos: hoy coincide con Asuncion, pero un cambio de su lado
        correria el dFeEmiDE sin que nada lo avise."""
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        altas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/electronic-documents/':
                altas.append(kwargs.get('json'))
                return respuesta_api(), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            _documento, error = emitir_para_pos(self._venta())

        self.assertIsNone(error)
        emitido = datetime.fromisoformat(altas[0]['issued_at'])
        self.assertIsNotNone(emitido.utcoffset())

    def test_venta_a_credito_declara_el_plazo(self):
        """El credito se emite desde que su API sumo gPagCred (1.1.0): condicion
        credito, tipo de credito a plazo y el plazo en texto. Sin `entries`: el
        credito con entrega inicial lo rechaza, y esta venta no la tiene."""
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        venta = self._venta()
        venta.tipo_venta = 'credito'
        db.session.commit()
        altas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/electronic-documents/':
                altas.append(kwargs.get('json'))
                return respuesta_api(), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_para_pos(venta)

        self.assertIsNone(error)
        self.assertEqual(documento.numero, '0000001')
        pago = altas[0]['payment']
        self.assertEqual(pago['condition'], 'credito')
        self.assertEqual(pago['credit_type'], 'plazo')
        self.assertTrue(2 <= len(pago['term']) <= 15)
        self.assertNotIn('entries', pago)

    def test_credito_con_entrega_inicial_no_consume_correlativo(self):
        """`entries` junto con condition=credito sigue bloqueado del otro lado,
        y mandarla como credito puro escondería la plata que el cliente
        entrego. Se corta de este lado para no quemar un numero que nunca va a
        salir y para que la pantalla diga por que."""
        from app.models.venta import MetodoPago, PagoVenta
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        venta = self._venta()
        venta.tipo_venta = 'credito'
        metodo = MetodoPago.query.filter(MetodoPago.nombre.like('Efectivo%')).first()
        db.session.add(PagoVenta(
            id_venta=venta.id_venta, id_metodo_pago=metodo.id_metodo_pago, monto=40000,
        ))
        db.session.commit()

        def _solicitar(config, metodo_http, ruta, **kwargs):
            raise AssertionError('no se debe llamar a la API por un credito con entrega')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_para_pos(venta)

        self.assertIn('entrega inicial', (error or '').lower())
        self.assertEqual(documento.estado, ESTADO_ERROR)
        self.assertIsNone(documento.numero)

    @patch('facturacion_electronica.services.proveedores.api.ProveedorApi.emite_notas_credito', False)
    @patch('facturacion_electronica.services.proveedores.api.API_EMITE_NOTAS_CREDITO', False)
    def test_la_nota_de_credito_no_se_intenta_mientras_este_bloqueada(self):
        """Encendida desde el 2026-09-26, pero la bandera sigue siendo la llave
        para apagarla si la API la vuelve a rechazar: apagada, no se quema un
        correlativo de NC contra un 400 y la pantalla no ofrece el botón."""
        from facturacion_electronica import TIPO_FACTURA
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import (
            capacidades,
            emitir_nota_credito,
        )

        config = self._activar_api()
        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000001',
            estado=ESTADO_APROBADO, cdc='0' * 44,
        ))
        db.session.commit()

        devolucion = SimpleNamespace(id_devolucion=7, id_venta=venta.id_venta)
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar') as nunca:
            documento, error = emitir_nota_credito(devolucion, 2)

        nunca.assert_not_called()
        self.assertIsNone(documento)
        self.assertIn('notas de crédito', error)
        # Y la pantalla tampoco ofrece el botón.
        self.assertFalse(capacidades(config)['notas_credito'])

    def test_estado_largo_de_la_api_entra_en_la_columna(self):
        """`CANCELLATION_PENDING` tiene 20 caracteres: en MySQL estricto una
        columna angosta no trunca, corta la emisión con un error de base."""
        from facturacion_electronica.models import DocumentoElectronico

        largo = DocumentoElectronico.__table__.c.respuesta_codigo.type.length
        self.assertGreaterEqual(largo, len('CANCELLATION_PENDING'))

    # -- lo que el job no debe saltearse -----------------------------------

    def _cliente_empresa_sin_dv(self):
        """Empresa cuyo RUC quedó cargado sin dígito verificador."""
        from app.models import Cliente

        cliente = Cliente(nombre='Ferretería SA', ruc_ci='80012345')
        db.session.add(cliente)
        db.session.commit()
        return cliente

    def test_el_job_no_emite_lo_que_la_validacion_del_cliente_freno(self):
        """El documento parado por 'RUC de empresa sin DV' no se emite solo.

        `emitir` frena y lo deja en error, pero el job lo levanta diez minutos
        después: yendo derecho al alta lo emitía igual, con la empresa cargada
        como cédula y sin su crédito de IVA. La validación tiene que correr
        también en el reintento.
        """
        from facturacion_electronica.services.proveedores.fachada import (
            avanzar_documento,
            emitir_para_pos,
        )

        self._activar_api()
        venta = self._venta()
        venta.id_cliente = self._cliente_empresa_sin_dv().id_cliente
        db.session.commit()

        def _nunca(config, metodo, ruta, **kwargs):
            raise AssertionError(f'no se debe llamar a la API: {metodo} {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _nunca):
            documento, error = emitir_para_pos(venta)
            self.assertIn('dígito verificador', error)
            self.assertEqual(documento.estado, ESTADO_ERROR)

            error_job = avanzar_documento(documento)

        self.assertIn('dígito verificador', error_job)
        self.assertEqual(documento.estado, ESTADO_ERROR)
        self.assertIsNone(documento.api_documento_id)

    def test_el_job_reserva_el_numero_si_la_reserva_habia_fallado(self):
        """Sin número, el alta mandaba `document_number: None` y la API
        contestaba un 400 que no explicaba nada."""
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import avanzar_documento

        self._activar_api()
        doc = DocumentoElectronico(
            id_venta=self._venta().id_venta,
            estado=ESTADO_ERROR,
            respuesta_mensaje='Se agotó el rango de numeración del timbrado.',
        )
        db.session.add(doc)
        db.session.commit()

        cuerpos = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/electronic-documents/':
                cuerpos.append(kwargs.get('json'))
                return respuesta_api(), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            error = avanzar_documento(doc)

        self.assertIsNone(error)
        self.assertEqual(cuerpos[0]['document_number'], '0000001')

    # -- el QR que sólo viene en el detalle --------------------------------

    def test_el_alta_recuperada_por_listado_va_a_buscar_el_qr(self):
        """El listado devuelve `ElectronicDocumentRead`, que no trae `qr_url`.

        Sin ir a buscarlo a `by-cdc`, el documento adoptado tras un corte de
        red quedaba sin QR y el KuDE se imprimía sin el código.
        """
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        venta = self._venta()
        estado = {'clave': None}

        def _primera(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.startswith('/sifen/electronic-documents/?'):
                return {'results': []}, None
            estado['clave'] = kwargs['headers']['Idempotency-Key']
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _primera):
            emitir_para_pos(venta)

        del_listado = respuesta_api(idempotency_key=estado['clave'])
        del_listado.pop('qr_url')  # como responde de verdad el listado
        rutas = []

        def _segunda(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.startswith('/sifen/electronic-documents/?'):
                return {'results': [del_listado]}, None
            if ruta.startswith('/sifen/electronic-documents/by-cdc/'):
                return {'qr_url': 'https://ekuatia.set.gov.py/consultas/qr?x=9'}, None
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _segunda):
            documento, error = emitir_para_pos(venta)

        self.assertIsNone(error)
        self.assertEqual(documento.qr_url, 'https://ekuatia.set.gov.py/consultas/qr?x=9')
        self.assertIn('/sifen/electronic-documents/by-cdc/' + '0' * 44 + '/', rutas)

    def test_el_qr_que_ya_tenemos_no_se_vuelve_a_pedir(self):
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import consultar_documento

        self._activar_api()
        doc = DocumentoElectronico(
            id_venta=self._venta().id_venta,
            estado=ESTADO_FIRMADO,
            cdc='0' * 44,
            qr_url='https://ekuatia.set.gov.py/consultas/qr?x=1',
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        )
        db.session.add(doc)
        db.session.commit()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta.startswith('/sifen/electronic-documents/by-cdc/'):
                raise AssertionError('el QR ya estaba; no hay que ir a buscarlo')
            return respuesta_api(), None

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            _respuesta, error = consultar_documento(doc)

        self.assertIsNone(error)

    # -- documento asociado de la NC ------------------------------------------

    def test_el_asociado_electronico_lleva_solo_el_cdc(self):
        """Timbrado, establecimiento, punto, número y fecha son del asociado
        **impreso**. Con uno electrónico SIFEN rechaza: `2419 Número de
        timbrado no requerido para el tipo de documento asociado` (NC de la
        venta #123 de Janelipy, 2026-09-29). La API los pasa al XML tal cual."""
        from facturacion_electronica import TIPO_NOTA_CREDITO
        from facturacion_electronica.services.proveedores.api_payload import (
            construir_nota_credito_api,
        )

        documento = SimpleNamespace(
            numero='0000001', nc_motivo=2, nc_motivo_desc='Devolución',
            tipo_documento=TIPO_NOTA_CREDITO, id_devolucion=7,
        )
        original = SimpleNamespace(
            cdc='0' * 44, timbrado='12345678', establecimiento='001', punto='001',
            numero='0000042', fecha_generado=datetime(2026, 3, 10, 2, 30),
        )
        venta = SimpleNamespace(cliente=self.cliente)

        cuerpo = construir_nota_credito_api(documento, original, venta, [], 'timbrado-uuid')

        self.assertEqual(cuerpo['associated'], {
            'doc_type': 1, 'doc_type_desc': 'Electrónico', 'cdc': '0' * 44,
        })

    # -- descarga del comprobante de la nota de crédito ---------------------

    def test_se_puede_descargar_el_comprobante_de_la_nota_de_credito(self):
        """Las rutas resolvían siempre la factura, así que la NC quedaba sin
        XML ni PDF — y el comprador los necesita igual."""
        from facturacion_electronica import TIPO_NOTA_CREDITO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.routes import _documento_descargable

        venta = self._venta()
        factura = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=1, numero='0000001',
        )
        nota = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO,
            numero='0000001', id_devolucion=7,
        )
        db.session.add_all([factura, nota])
        db.session.commit()

        with self.app.test_request_context('/'):
            self.assertEqual(_documento_descargable(venta.id_venta).id, factura.id)
        with self.app.test_request_context('/?documento=%d' % nota.id):
            self.assertEqual(_documento_descargable(venta.id_venta).id, nota.id)

    def test_no_se_descarga_el_comprobante_de_otra_venta(self):
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.routes import _documento_descargable

        ajena = self._venta()
        documento = DocumentoElectronico(id_venta=ajena.id_venta, tipo_documento=1)
        db.session.add(documento)
        db.session.commit()
        otra = self._venta()

        with self.app.test_request_context('/?documento=%d' % documento.id):
            self.assertIsNone(_documento_descargable(otra.id_venta))

    def test_no_se_emite_nc_de_una_factura_que_se_esta_anulando(self):
        """CANCELLATION_PENDING mapea a 'aprobado' (el DE vale hasta que la baja
        esté firme), así que el chequeo de estado la dejaba pasar. Una factura
        que se está anulando ya tiene su desagravio en camino: sumarle una NC
        acreditaría el mismo IVA dos veces."""
        from facturacion_electronica import TIPO_FACTURA
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import emitir_nota_credito

        self._activar_api()
        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000001',
            estado=ESTADO_APROBADO, respuesta_codigo='CANCELLATION_PENDING', cdc='0' * 44,
        ))
        db.session.commit()

        devolucion = SimpleNamespace(id_devolucion=7, id_venta=venta.id_venta)
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar') as nunca,                 patch('facturacion_electronica.services.proveedores.api.'
                      'API_EMITE_NOTAS_CREDITO', True):
            documento, error = emitir_nota_credito(devolucion, 2)

        nunca.assert_not_called()
        self.assertIsNone(documento)
        self.assertIn('cancelación', error)

    def test_volver_a_facturar_una_cancelada_usa_otra_referencia(self):
        """Visto con la venta #141: la API reserva `external_ref` también para
        los cancelados, y la re-factura con la misma referencia daba 409
        `external_ref_conflict` con el número nuevo ya reservado."""
        from facturacion_electronica import ESTADO_CANCELADO, TIPO_FACTURA
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.api_payload import referencia_externa

        venta = self._venta()
        cancelada = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000052',
            estado=ESTADO_CANCELADO,
        )
        db.session.add(cancelada)
        db.session.commit()
        nueva = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000053',
        )
        db.session.add(nueva)
        db.session.commit()

        self.assertEqual(referencia_externa(cancelada), str(venta.id_venta))
        self.assertEqual(referencia_externa(nueva), f'{venta.id_venta}-2')


def test_referencia_externa_distingue_factura_de_nota_de_credito():
    """La búsqueda del alta perdida filtra por `external_ref`: si no es la
    misma que mandó el alta, el documento existe en la API y no lo encontramos."""
    from facturacion_electronica.services.proveedores.api_payload import referencia_externa

    factura = SimpleNamespace(tipo_documento=1, id_venta=42, id_devolucion=None)
    nota = SimpleNamespace(tipo_documento=5, id_venta=42, id_devolucion=7)
    assert referencia_externa(factura) == '42'
    assert referencia_externa(nota) == 'devolucion-7'


# ------------------------------------------------- formas de pago de la API
# Desde su 1.1.0 cada medio trae su bloque obligatorio: tarjeta (3 y 4) y
# cheque (2) lo exigen, y el 99 ("otro") exige la descripción del medio. Un
# bloque de más, o de menos, es un 400 y la venta se queda sin factura.


def _pago_de(nombre, monto, referencia=None, banco=None):
    return SimpleNamespace(
        monto=monto,
        referencia=referencia,
        metodo=SimpleNamespace(nombre=nombre),
        banco=SimpleNamespace(nombre=banco) if banco else None,
    )


def _venta_contado(total):
    return SimpleNamespace(tipo_venta='contado', total=total)


def test_la_tarjeta_viaja_con_su_bloque():
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(_venta_contado(50000), [_pago_de('Tarjeta de Débito', 50000)])

    entrada = pago['entries'][0]
    assert entrada['means'] == 4
    # La marca no la guarda el POS: va la genérica (99) con su descripción.
    assert entrada['card'] == {
        'brand': 99, 'brand_description': 'Tarjeta de Débito', 'processing': 1,
    }
    assert 'means_description' not in entrada


def test_el_cheque_viaja_con_numero_y_banco():
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(
        _venta_contado(80000),
        [_pago_de('Cheque', 80000, referencia='12345', banco='Banco Continental')],
    )

    entrada = pago['entries'][0]
    assert entrada['means'] == 2
    # dNumCheq son exactamente 8 dígitos y la API no rellena por nosotros.
    assert entrada['cheque'] == {'number': '00012345', 'bank': 'Banco Continental'}


def test_un_cheque_sin_datos_se_declara_como_otro_medio():
    """Sin número ni banco no hay `gPagCheq` que mandar, y los dos campos son
    obligatorios: se declara "otro medio" con su descripción antes que dejar la
    venta sin factura."""
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(_venta_contado(80000), [_pago_de('Cheque', 80000)])

    entrada = pago['entries'][0]
    assert entrada['means'] == 99
    assert entrada['means_description'] == 'Cheque'
    assert 'cheque' not in entrada


def test_el_medio_99_siempre_lleva_descripcion():
    """`_tipo_pago` cae en 99 con cualquier método que el sistema no tipifique,
    y con 99 la descripción es obligatoria."""
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(_venta_contado(30000), [_pago_de('Canje de puntos', 30000)])

    entrada = pago['entries'][0]
    assert entrada['means'] == 99
    assert entrada['means_description'] == 'Canje de puntos'


def test_las_entregas_suman_exacto_el_total():
    """Desde la 1.1.0 la suma de las entregas tiene que dar exactamente el
    total del documento, o devuelve 400 `invalid_payment`. El método que no es
    entrega de contado (crédito tienda) no puede dejar la suma corta."""
    from facturacion_electronica.services.proveedores.api_payload import construir_pago

    pago = construir_pago(
        _venta_contado(200000),
        [_pago_de('Efectivo', 120000), _pago_de('Crédito Tienda', 80000)],
    )

    assert sum(int(e['amount']) for e in pago['entries']) == 200000


if __name__ == '__main__':
    unittest.main()


if __name__ == '__main__':
    unittest.main()
