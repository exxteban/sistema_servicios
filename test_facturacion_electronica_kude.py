from types import SimpleNamespace

from app.models.producto import Producto
from app.models.venta import DetalleVenta
from facturacion_electronica.services.qr import extraer_qr_url, qr_png_data_uri
from facturacion_electronica.services.kude_service import (
    URL_CONSULTA_PRODUCCION,
    URL_CONSULTA_TEST,
    _iva_de_linea,
    _items_desde_venta,
    _liquidacion_iva,
)


def test_extraer_qr_url_desescapa_amp():
    xml = (
        '<rDE><gCamFuFD><dCarQR>'
        'https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&amp;Id=01&amp;cHashQR=abc'
        '</dCarQR></gCamFuFD></rDE>'
    )
    url = extraer_qr_url(xml)
    assert url == 'https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&Id=01&cHashQR=abc'


def test_extraer_qr_url_sin_nodo():
    assert extraer_qr_url('<rDE></rDE>') is None
    assert extraer_qr_url('') is None
    assert extraer_qr_url(None) is None


def test_qr_png_data_uri():
    data_uri = qr_png_data_uri('https://ekuatia.set.gov.py/consultas/qr?x=1')
    assert data_uri.startswith('data:image/png;base64,')
    assert qr_png_data_uri(None) is None


def test_iva_de_linea_iva_incluido():
    # IVA contenido en montos IVA-incluido (PYG sin decimales).
    assert _iva_de_linea(110000, 10) == 10000
    assert _iva_de_linea(105000, 5) == 5000
    assert _iva_de_linea(50000, 0) == 0


def test_liquidacion_iva_agrupa_por_tasa():
    items = [
        {'subtotal': 110000, 'iva_pct': 10},
        {'subtotal': 105000, 'iva_pct': 5},
        {'subtotal': 50000, 'iva_pct': 0},
    ]
    liq = _liquidacion_iva(items)
    assert liq['gravado_10'] == 110000
    assert liq['gravado_5'] == 105000
    assert liq['exentas'] == 50000
    assert liq['iva_10'] == 10000
    assert liq['iva_5'] == 5000
    assert liq['total_iva'] == 15000


def _detalle_kude(codigo, nombre, cantidad, precio, iva):
    detalle = DetalleVenta(
        id_producto=1,
        cantidad=cantidad,
        precio_unitario=precio,
        precio_original=precio,
        porcentaje_iva=iva,
        monto_iva=0,
        descuento_linea=0,
        subtotal=cantidad * precio,
    )
    detalle.producto = Producto(
        codigo=codigo, nombre=nombre, porcentaje_iva=iva, precio_venta=precio,
    )
    return detalle


def test_kude_con_descuento_global_usa_los_importes_del_de():
    """El papel tiene que declarar lo mismo que el XML: líneas que suman el
    total cobrado e IVA sobre ese total, no sobre el subtotal crudo."""
    venta = SimpleNamespace(
        total=90000,
        detalles=[
            _detalle_kude('A-1', 'Uno', 1, 60000, 10),
            _detalle_kude('A-2', 'Dos', 1, 40000, 10),
        ],
    )
    items = _items_desde_venta(venta)
    assert [item['subtotal'] for item in items] == [54000, 36000]
    assert sum(item['subtotal'] for item in items) == 90000
    liq = _liquidacion_iva(items)
    assert liq['gravado_10'] == 90000
    assert liq['iva_10'] == _iva_de_linea(54000, 10) + _iva_de_linea(36000, 10)
    assert liq['iva_10'] != _iva_de_linea(100000, 10)


def test_kude_usa_ambiente_y_timbrado_del_documento():
    """Una reimpresión no lee la config actual: la factura de prueba tiene que
    seguir diciendo que no vale fiscalmente, con el timbrado de entonces."""
    from unittest.mock import patch

    from facturacion_electronica import AMBIENTE_PRODUCCION, AMBIENTE_TEST
    from facturacion_electronica.services.kude_service import construir_contexto_kude

    venta = SimpleNamespace(
        total=90000,
        tipo_venta='contado',
        cliente=SimpleNamespace(nombre='Ana', ruc_ci='123'),
        fecha_venta=None,
        detalles=[
            _detalle_kude('A-1', 'Uno', 1, 60000, 10),
            _detalle_kude('A-2', 'Dos', 1, 40000, 10),
        ],
    )
    documento = SimpleNamespace(
        establecimiento='001', punto='001', numero='0000001',
        ambiente=AMBIENTE_TEST, timbrado='12345678', qr_url=None,
    )
    config = SimpleNamespace(
        ambiente=AMBIENTE_PRODUCCION, timbrado_numero='99999999',
        timbrado_fecha_inicio=None,
    )
    with patch(
        'facturacion_electronica.services.kude_service.obtener_configuracion',
        return_value=config,
    ):
        ctx = construir_contexto_kude(venta, documento)
    assert ctx['es_produccion'] is False
    assert ctx['timbrado_numero'] == '12345678'
    # El pie manda a consultar el CDC: tiene que ser el consultor del ambiente
    # del documento, no el de producción por defecto.
    assert ctx['url_consulta'] == URL_CONSULTA_TEST

    documento.ambiente = AMBIENTE_PRODUCCION
    with patch(
        'facturacion_electronica.services.kude_service.obtener_configuracion',
        return_value=config,
    ):
        ctx = construir_contexto_kude(venta, documento)
    assert ctx['url_consulta'] == URL_CONSULTA_PRODUCCION


def test_el_kude_muestra_el_redondeo_en_vez_de_esconderlo():
    """El papel no puede decir un total distinto al del documento.

    `xmlgen` baja el total al múltiplo de 50 y declara la diferencia en
    dRedon. El KuDE imprimía el total crudo de la venta, así que el
    comprobante del cliente y el DE de SIFEN decían cifras distintas.
    """
    from unittest.mock import patch

    from facturacion_electronica import AMBIENTE_TEST
    from facturacion_electronica.services.kude_service import construir_contexto_kude

    venta = SimpleNamespace(
        total=344343,
        tipo_venta='contado',
        cliente=SimpleNamespace(nombre='alfio oviedo', ruc_ci='4281292'),
        fecha_venta=None,
        detalles=[_detalle_kude('lifepod', 'wd', 1, 344343, 10)],
    )
    documento = SimpleNamespace(
        establecimiento='001', punto='001', numero='0000004',
        ambiente=AMBIENTE_TEST, timbrado='19128252', qr_url=None,
    )
    config = SimpleNamespace(
        ambiente=AMBIENTE_TEST, timbrado_numero='19128252', timbrado_fecha_inicio=None,
    )
    with patch(
        'facturacion_electronica.services.kude_service.obtener_configuracion',
        return_value=config,
    ):
        ctx = construir_contexto_kude(venta, documento)

    assert ctx['subtotal'] == 344343
    assert ctx['redondeo'] == 43
    assert ctx['total'] == 344300


def test_kude_imprime_fecha_en_hora_local():
    """fecha_venta es UTC naive; issued_at viaja con offset local. El papel
    tiene que decir la misma fecha que SIFEN, no tres horas más tarde."""
    from datetime import datetime
    from flask import render_template
    from unittest.mock import patch

    from app import create_app, db
    from facturacion_electronica import AMBIENTE_TEST
    from facturacion_electronica.services.kude_service import construir_contexto_kude

    app = create_app('testing')
    ctx_app = app.app_context()
    ctx_app.push()
    try:
        venta = SimpleNamespace(
            total=100000,
            tipo_venta='contado',
            cliente=SimpleNamespace(nombre='Ana', ruc_ci='123'),
            fecha_venta=datetime(2026, 9, 20, 1, 30),
            detalles=[],
        )
        documento = SimpleNamespace(
            establecimiento='001', punto='001', numero='0000001',
            ambiente=AMBIENTE_TEST, timbrado='12345678', qr_url=None,
            cdc_formateado='0000',
        )
        config = SimpleNamespace(
            ambiente='produccion', timbrado_numero='99999999',
            timbrado_fecha_inicio=None, razon_social='Ejemplo SA',
            nombre_fantasia=None, actividad_economica_desc=None,
            direccion=None, numero_casa=None, ciudad_desc=None,
            telefono=None, ruc='80012345', dv_ruc='6',
        )
        with patch(
            'facturacion_electronica.services.kude_service.obtener_configuracion',
            return_value=config,
        ):
            contexto = construir_contexto_kude(venta, documento)
        contexto['preview'] = True
        html = render_template('facturacion_electronica/kude.html', **contexto)
    finally:
        db.session.remove()
        db.drop_all()
        ctx_app.pop()

    assert '19/09/2026 22:30' in html
    assert '20/09/2026 01:30' not in html
    assert 'SIN VALIDEZ FISCAL' in html
    assert '12345678' in html
    assert '99999999' not in html



def _render_kude(paper_width_mm, detalles):
    """Renderiza el KuDE en una app de prueba con el ancho de papel dado."""
    from datetime import datetime
    from flask import render_template
    from unittest.mock import patch

    from app import create_app, db
    from facturacion_electronica import AMBIENTE_TEST
    from facturacion_electronica.services.kude_service import construir_contexto_kude

    app = create_app('testing')
    ctx_app = app.app_context()
    ctx_app.push()
    try:
        venta = SimpleNamespace(
            total=sum(d.subtotal for d in detalles), tipo_venta='contado',
            cliente=SimpleNamespace(nombre='Ana', ruc_ci='123'),
            fecha_venta=datetime(2026, 10, 5, 15, 0), detalles=detalles,
        )
        documento = SimpleNamespace(
            establecimiento='001', punto='001', numero='0000001',
            ambiente=AMBIENTE_TEST, timbrado='12345678', qr_url=None,
            cdc_formateado='0000',
        )
        config = SimpleNamespace(
            ambiente=AMBIENTE_TEST, timbrado_numero='12345678',
            timbrado_fecha_inicio=None, razon_social='Ejemplo SA',
            nombre_fantasia=None, actividad_economica_desc=None,
            direccion=None, numero_casa=None, ciudad_desc=None,
            telefono=None, ruc='80012345', dv_ruc='6',
        )
        with patch(
            'facturacion_electronica.services.kude_service.obtener_configuracion',
            return_value=config,
        ):
            contexto = construir_contexto_kude(venta, documento, paper_width_mm)
        contexto['preview'] = True
        return render_template('facturacion_electronica/kude.html', **contexto)
    finally:
        db.session.remove()
        db.drop_all()
        ctx_app.pop()


def test_kude_en_58mm_pone_cada_item_en_dos_renglones():
    """En 58mm las cuatro columnas no entran: el total se partía o se cortaba."""
    detalles = [_detalle_kude('A-1', 'Cartera de cuero', 2, 625000, 10)]
    html = _render_kude(58, detalles)
    assert 'size: 58mm auto' in html
    assert 'class="item-monto"' in html
    assert '2 x 625.000 · IVA 10%' in html
    assert '1.250.000' in html
    assert 'class="col-iva"' not in html


def test_kude_en_80mm_conserva_las_cuatro_columnas():
    detalles = [_detalle_kude('A-1', 'Cartera de cuero', 2, 625000, 10)]
    html = _render_kude(80, detalles)
    assert 'size: 80mm auto' in html
    assert '<td class="col-iva">10%</td>' in html
    assert 'class="item-monto"' not in html


def test_ancho_papel_kude_sigue_al_del_ticket():
    from app import create_app, db
    from app.models import Configuracion
    from facturacion_electronica.services.kude_service import ancho_papel_kude

    app = create_app('testing')
    with app.app_context():
        try:
            db.create_all()
            assert ancho_papel_kude() == 58
            Configuracion.establecer('ticket_paper_width_mm', '80')
            assert ancho_papel_kude() == 80
            Configuracion.establecer('ticket_paper_width_mm', '72')
            assert ancho_papel_kude() == 58
        finally:
            db.session.remove()
            db.drop_all()
