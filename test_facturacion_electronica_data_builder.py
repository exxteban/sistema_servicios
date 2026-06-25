from datetime import datetime

from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.servicio import Servicio
from app.models.venta import DetalleVenta, MetodoPago, PagoVenta, Venta
from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.data_builder import (
    construir_cliente,
    construir_condicion,
    construir_data_venta,
    construir_entregas,
    construir_items,
    numero_documento,
)


def _pago(nombre, monto):
    pago = PagoVenta(monto=monto)
    pago.metodo = MetodoPago(nombre=nombre)
    return pago


def _config():
    return FacturacionElectronicaConfig(id=1, establecimiento='002', punto_expedicion='005')


def _detalle(codigo, nombre, cantidad, precio, iva, descuento=0):
    detalle = DetalleVenta(
        id_producto=1,
        cantidad=cantidad,
        precio_unitario=precio,
        precio_original=precio,
        porcentaje_iva=iva,
        monto_iva=0,
        descuento_linea=descuento,
        subtotal=cantidad * precio,
    )
    detalle.producto = Producto(codigo=codigo, nombre=nombre, porcentaje_iva=iva, precio_venta=precio)
    return detalle


def _detalle_servicio(codigo, nombre, cantidad, precio, iva):
    detalle = DetalleVenta(
        id_servicio=3,
        cantidad=cantidad,
        precio_unitario=precio,
        precio_original=precio,
        porcentaje_iva=iva,
        monto_iva=0,
        descuento_linea=0,
        subtotal=cantidad * precio,
    )
    detalle.servicio = Servicio(codigo=codigo, nombre=nombre, porcentaje_iva=iva, precio=precio)
    return detalle


def test_cliente_con_ruc_es_contribuyente():
    cliente = Cliente(id_cliente=5, nombre='EMPRESA SRL', ruc_ci='80012345-6')
    data = construir_cliente(cliente)
    assert data['contribuyente'] is True
    assert data['ruc'] == '80012345-6'
    assert data['tipoOperacion'] == 1
    assert data['codigo'] == '005'


def test_consumidor_final_es_innominado():
    cliente = Cliente(id_cliente=1, nombre='Consumidor Final', ruc_ci=None)
    data = construir_cliente(cliente)
    assert data['contribuyente'] is False
    assert data['tipoOperacion'] == 2
    assert data['documentoTipo'] == 5
    assert data['documentoNumero'] == '0'


def test_documento_todo_ceros_es_innominado():
    cliente = Cliente(id_cliente=1, nombre='CONSUMIDOR FINAL', ruc_ci='000000000')
    data = construir_cliente(cliente)
    assert data['documentoTipo'] == 5
    assert data['documentoNumero'] == '0'


def test_cliente_con_ci_sin_dv_no_es_contribuyente():
    cliente = Cliente(id_cliente=7, nombre='Juan Pérez', ruc_ci='1234567')
    data = construir_cliente(cliente)
    assert data['contribuyente'] is False
    assert data['documentoNumero'] == '1234567'


def test_condicion_contado_y_credito():
    contado = construir_condicion(Venta(tipo_venta='contado', total=150000), [])
    assert contado['tipo'] == 1
    assert contado['entregas'][0]['monto'] == '150000.0'

    credito = construir_condicion(Venta(tipo_venta='credito', total=150000), [])
    assert credito['tipo'] == 2
    assert 'credito' in credito


def test_entregas_mapean_metodos_de_pago():
    entregas = construir_entregas([
        _pago('Efectivo', 100000),
        _pago('Tarjeta de Crédito', 50000),
        _pago('Transferencia Bancaria', 30000),
        _pago('QR / Billetera Digital', 20000),
    ], total=200000)
    tipos = [e['tipo'] for e in entregas]
    assert tipos == [1, 3, 5, 7]
    assert entregas[1]['infoTarjeta'] == {'tipo': 99}


def test_credito_tienda_no_es_entrega_de_contado():
    entregas = construir_entregas([_pago('Crédito Tienda', 200000)], total=200000)
    assert entregas == [{'tipo': 1, 'monto': '200000.0', 'moneda': 'PYG', 'cambio': 0}]


def test_unidad_medida_segun_producto():
    kg = _detalle('K-1', 'Por kilo', 2, 5000, 10)
    kg.producto.unidad_venta = 'kg'
    litro = _detalle('L-1', 'Por litro', 1, 3000, 10)
    litro.producto.unidad_venta = 'litro'
    items = construir_items([kg, litro])
    assert items[0]['unidadMedida'] == 83
    assert items[1]['unidadMedida'] == 89


def test_items_mapea_iva_gravado_y_exento():
    items = construir_items([
        _detalle('A-1', 'Gravado 10', 2, 11000, 10),
        _detalle('A-2', 'Exento', 1, 5000, 0),
    ])
    assert items[0]['ivaTipo'] == 1
    assert items[0]['iva'] == 10
    assert items[0]['ivaProporcion'] == 100
    assert items[1]['ivaTipo'] == 3
    assert items[1]['iva'] == 0


def test_item_descuento_se_reparte_por_unidad():
    item = construir_items([_detalle('A-3', 'Con desc', 2, 10000, 10, descuento=2000)])[0]
    assert item['descuento'] == 1000


def test_numero_documento_extrae_siete_digitos():
    assert numero_documento(Venta(id_venta=9, numero_comprobante='002-005-0000123')) == '0000123'
    assert numero_documento(Venta(id_venta=42, numero_comprobante=None)) == '0000042'


def test_item_servicio_usa_codigo_y_nombre_del_servicio():
    item = construir_items([_detalle_servicio('SRV-01', 'Consulta', 1, 80000, 10)])[0]
    assert item['codigo'] == 'SRV-01'
    assert item['descripcion'] == 'Consulta'
    assert item['unidadMedida'] == 77


def test_data_venta_completo():
    cliente = Cliente(id_cliente=5, nombre='EMPRESA SRL', ruc_ci='80012345-6')
    venta = Venta(
        id_venta=10,
        numero_comprobante='0000777',
        tipo_venta='contado',
        total=22000,
        fecha_venta=datetime(2026, 6, 24, 9, 30, 0),
    )
    venta.cliente = cliente
    detalles = [_detalle('A-1', 'Producto', 2, 11000, 10)]

    data = construir_data_venta(venta, _config(), detalles=detalles, pagos=[], codigo_seguridad='123456789')

    assert data['tipoDocumento'] == 1
    assert data['establecimiento'] == '002'
    assert data['punto'] == '005'
    assert data['numero'] == '0000777'
    assert data['codigoSeguridadAleatorio'] == '123456789'
    assert data['fecha'] == '2026-06-24T09:30:00'
    assert data['moneda'] == 'PYG'
    assert data['factura'] == {'presencia': 1}
    assert data['cliente']['ruc'] == '80012345-6'
    assert len(data['items']) == 1
