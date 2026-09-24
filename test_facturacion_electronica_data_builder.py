from types import SimpleNamespace
from datetime import date, datetime

from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.venta import DetalleVenta, MetodoPago, PagoVenta, Venta
from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.data_builder import (
    construir_cliente,
    construir_condicion,
    construir_data_venta,
    construir_entregas,
    construir_items,
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
        subtotal=cantidad * precio - descuento,
    )
    detalle.producto = Producto(codigo=codigo, nombre=nombre, porcentaje_iva=iva, precio_venta=precio)
    return detalle


def test_cliente_con_ruc_es_contribuyente():
    cliente = Cliente(id_cliente=5, nombre='EMPRESA SRL', ruc_ci='80012345-6')
    data = construir_cliente(cliente)
    assert data['contribuyente'] is True
    assert data['ruc'] == '80012345-6'
    assert data['tipoOperacion'] == 1
    # RUC que empieza con 80: persona jurídica (iTiContRec=2).
    assert data['tipoContribuyente'] == 2
    assert data['codigo'] == '005'


def test_la_direccion_suelta_del_receptor_no_viaja():
    """Informar sólo la dirección hace fallar la generación del XML.

    SIFEN la acepta como opcional, pero si viene exige además número de casa,
    departamento, distrito y ciudad con sus códigos oficiales. La ficha de
    cliente guarda una dirección de texto libre y nada más, así que mandarla
    devolvía cuatro errores de validación y la venta se quedaba sin factura.
    """
    cliente = Cliente(id_cliente=5, nombre='alfio oviedo', ruc_ci='4281292',
                      direccion='Paseo Guillermo Gimenez')
    data = construir_cliente(cliente)
    assert 'direccion' not in data
    assert 'numeroCasa' not in data


def test_el_domicilio_completo_del_receptor_si_viaja():
    """El día que la ficha guarde los códigos, el bloque sale entero."""
    cliente = Cliente(id_cliente=5, nombre='alfio oviedo', ruc_ci='4281292',
                      direccion='Paseo Guillermo Gimenez')
    # Todavía no son columnas del modelo: se simulan para fijar el contrato.
    cliente.numero_casa = '125'
    cliente.departamento_codigo = 12
    cliente.distrito_codigo = 153
    cliente.ciudad_codigo = 3568

    data = construir_cliente(cliente)
    assert data['direccion'] == 'Paseo Guillermo Gimenez'
    assert data['numeroCasa'] == '125'
    assert data['departamento'] == 12
    assert data['distrito'] == 153
    assert data['ciudad'] == 3568
    assert data['ciudadDescripcion'] == 'CAPIATA'


def test_redondeo_sedeco_baja_al_multiplo_de_50():
    """`xmlgen` lo aplica siempre en guaraníes; acá se replica su regla.

    El caso real: una venta de 344.343 salió declarada como 344.300 con
    dRedon=43, mientras la entrega de pago seguía diciendo 344.343.
    """
    from facturacion_electronica.services.data_builder import redondeo_sedeco

    assert redondeo_sedeco(344343) == (344300, 43)
    assert redondeo_sedeco(344375) == (344350, 25)
    # Los precios normales del rubro son múltiplos de 50: no hay redondeo.
    assert redondeo_sedeco(344350) == (344350, 0)
    assert redondeo_sedeco(100000) == (100000, 0)
    assert redondeo_sedeco(0) == (0, 0)


def test_la_entrega_cuadra_contra_el_total_redondeado():
    """El DE no puede contradecirse: dMonTiPag tiene que dar dTotGralOpe."""
    venta = Venta(id_cliente=1, subtotal=344343, total=344343, tipo_venta='contado')
    condicion = construir_condicion(venta, [_pago('Efectivo', 344343)])

    assert sum(float(e['monto']) for e in condicion['entregas']) == 344300


def test_cliente_persona_fisica_con_ruc():
    # RUC de persona física (su cédula): iTiContRec=1.
    cliente = Cliente(id_cliente=8, nombre='Juan Pérez', ruc_ci='4123456-7')
    data = construir_cliente(cliente)
    assert data['contribuyente'] is True
    assert data['tipoContribuyente'] == 1


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
    assert contado['entregas'][0]['monto'] == '150000'

    credito = construir_condicion(Venta(tipo_venta='credito', total=150000), [])
    assert credito['tipo'] == 2
    assert 'credito' in credito


def test_condicion_credito_plazo_usa_fecha_vencimiento_real():
    from app.models.venta import CuentaPorCobrar

    venta = Venta(
        tipo_venta='credito',
        total=150000,
        fecha_venta=datetime(2026, 6, 1, 12, 0, 0),
    )
    venta.cuenta_por_cobrar = CuentaPorCobrar(
        monto_total=150000, saldo_pendiente=150000, fecha_vencimiento=date(2026, 7, 16),
    )
    credito = construir_condicion(venta, [])
    assert credito['credito']['plazo'] == '45 días'


def test_condicion_credito_sin_vencimiento_usa_30_dias_por_defecto():
    venta = Venta(tipo_venta='credito', total=150000, fecha_venta=datetime(2026, 6, 1))
    credito = construir_condicion(venta, [])
    assert credito['credito']['plazo'] == '30 días'


def test_entregas_mapean_metodos_de_pago():
    entregas = construir_entregas([
        _pago('Efectivo', 100000),
        _pago('Tarjeta de Crédito', 50000),
        _pago('Transferencia Bancaria', 30000),
        _pago('QR / Billetera Digital', 20000),
    ], total=200000)
    tipos = [e['tipo'] for e in entregas]
    assert tipos == [1, 3, 5, 7]


def test_la_tarjeta_generica_lleva_descripcion_y_medio_de_procesamiento():
    """SIFEN rechazó dos DE reales (`0160 XML malformado`) por mandar la marca
    99 sin `dDesDenTarj` y sin `iForProPa`. Los tres campos van juntos o el XML
    sale con elementos vacíos, que es lo que SIFEN no perdona."""
    entregas = construir_entregas([_pago('Tarjeta de Crédito', 50000)], total=50000)
    tarjeta = entregas[0]['infoTarjeta']
    assert tarjeta['tipo'] == 99
    assert tarjeta['medioPago'] in (1, 2, 9)
    # xmlgen valida la descripción entre 4 y 20 caracteres antes de firmar.
    assert 4 <= len(tarjeta['tipoDescripcion']) <= 20


def test_el_medio_otro_lleva_su_descripcion():
    """`dDesTiPag` es obligatorio con el medio 99 y xmlgen ni siquiera genera el
    documento sin él: un método cuyo nombre no reconocemos caía en 99 y dejaba
    la venta sin poder facturarse."""
    entregas = construir_entregas([_pago('Giros Tigo', 50000)], total=50000)
    assert entregas[0]['tipo'] == 99
    assert 4 <= len(entregas[0]['tipoDescripcion']) <= 30
    # Se usa el nombre real del método: es el único dato de cómo se cobró.
    assert entregas[0]['tipoDescripcion'] == 'Giros Tigo'


def test_un_nombre_de_metodo_demasiado_corto_cae_a_un_generico():
    # 'Uva' no matchea ningún medio conocido, así que cae en 99, pero tiene
    # menos de los 4 caracteres que xmlgen exige para la descripción.
    entregas = construir_entregas([_pago('Uva', 50000)], total=50000)
    assert entregas[0]['tipo'] == 99
    assert len(entregas[0]['tipoDescripcion']) >= 4


def test_cheque_con_referencia_y_banco_lleva_su_bloque():
    pago = _pago('Cheque', 50000)
    pago.referencia = '12345'
    pago.banco = SimpleNamespace(nombre='Banco Continental')
    entregas = construir_entregas([pago], total=50000)
    assert entregas[0]['tipo'] == 2
    assert entregas[0]['infoCheque'] == {'numeroCheque': '00012345', 'banco': 'Banco Continental'}


def test_cheque_sin_datos_se_declara_como_otro_medio_en_vez_de_frenar():
    """Sin número ni banco xmlgen rechaza el documento entero. Cobrar en cheque
    no puede dejar una venta sin poder facturarse nunca."""
    entregas = construir_entregas([_pago('Cheque', 50000)], total=50000)
    assert entregas[0]['tipo'] == 99
    assert 'infoCheque' not in entregas[0]
    assert entregas[0]['tipoDescripcion'] == 'Cheque'


def test_dos_pagos_con_tarjeta_no_comparten_el_mismo_dict():
    """La info de tarjeta es una constante del módulo: si viaja por referencia,
    tocar una entrega pisa la de todas las ventas del proceso."""
    entregas = construir_entregas([
        _pago('Tarjeta de Crédito', 30000),
        _pago('Tarjeta de Débito', 20000),
    ], total=50000)
    assert entregas[0]['infoTarjeta'] is not entregas[1]['infoTarjeta']


def test_credito_tienda_no_es_entrega_de_contado():
    entregas = construir_entregas([_pago('Crédito Tienda', 200000)], total=200000)
    assert entregas == [{'tipo': 1, 'monto': '200000', 'moneda': 'PYG', 'cambio': 0}]


def test_entregas_siempre_cuadran_el_total():
    # Un método omitido (crédito tienda) no debe dejar la suma por debajo del total.
    entregas = construir_entregas([
        _pago('Efectivo', 120000),
        _pago('Crédito Tienda', 80000),
    ], total=200000)
    assert sum(int(e['monto']) for e in entregas) == 200000


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


def test_el_descuento_global_se_reparte_sobre_las_lineas():
    """El descuento de la venta (manual o de fidelización) no está en ninguna
    línea: sin repartirlo, el documento sale por más plata de la que se cobró y
    las entregas de pago no cuadran contra el total."""
    items = construir_items(
        [_detalle('A-1', 'Uno', 1, 60000, 10), _detalle('A-2', 'Dos', 1, 40000, 10)],
        total_objetivo=90000,
    )
    netos = [i['cantidad'] * (i['precioUnitario'] - i['descuento']) for i in items]
    # 10.000 de descuento repartidos en proporción: 60/40.
    assert netos == [54000, 36000]
    assert sum(netos) == 90000


def test_el_reparto_cierra_el_total_al_guarani():
    """Tres líneas iguales contra un total que no divide exacto: el guaraní
    suelto tiene que quedar en alguna línea, no perderse."""
    items = construir_items(
        [_detalle(f'A-{n}', f'Item {n}', 1, 10000, 10) for n in range(3)],
        total_objetivo=25000,
    )
    netos = [round(i['cantidad'] * (i['precioUnitario'] - i['descuento'])) for i in items]
    assert sum(netos) == 25000


def test_sin_descuento_global_los_precios_no_se_tocan():
    items = construir_items(
        [_detalle('A-1', 'Uno', 2, 50000, 10)], total_objetivo=100000,
    )
    assert items[0]['descuento'] == 0


def test_numero_usa_el_parametro_no_la_factura_externa():
    venta = Venta(id_venta=9, tipo_venta='contado', total=0)
    venta.cliente = Cliente(id_cliente=1, nombre='Consumidor')
    # El número del DE viene por parámetro, no de la venta.
    sin_numero = construir_data_venta(venta, _config(), detalles=[], pagos=[])
    assert sin_numero['numero'] == '0000000'
    con_numero = construir_data_venta(venta, _config(), detalles=[], pagos=[], numero='0000045')
    assert con_numero['numero'] == '0000045'


def test_data_venta_completo():
    cliente = Cliente(id_cliente=5, nombre='EMPRESA SRL', ruc_ci='80012345-6')
    venta = Venta(
        id_venta=10,
        tipo_venta='contado',
        total=22000,
        fecha_venta=datetime(2026, 6, 24, 9, 30, 0),
    )
    venta.cliente = cliente
    detalles = [_detalle('A-1', 'Producto', 2, 11000, 10)]

    data = construir_data_venta(
        venta, _config(), detalles=detalles, pagos=[], codigo_seguridad='123456789', numero='0000777'
    )

    assert data['tipoDocumento'] == 1
    assert data['establecimiento'] == '002'
    assert data['punto'] == '005'
    assert data['numero'] == '0000777'
    assert data['codigoSeguridadAleatorio'] == '123456789'
    # fecha_venta se guarda en UTC; dFeEmiDE va en hora local de Paraguay (UTC-3).
    assert data['fecha'] == '2026-06-24T06:30:00'
    assert data['moneda'] == 'PYG'
    assert data['factura'] == {'presencia': 1}
    assert data['cliente']['ruc'] == '80012345-6'
    assert len(data['items']) == 1


def test_la_fecha_de_firma_va_en_hora_de_paraguay():
    """`dFecFirma` la escribe xmlgen con `new Date()` formateado con la hora
    local **del proceso Node** y sin offset: en un servidor en UTC toda factura
    saldría firmada tres horas en el futuro, dentro de un documento firmado.
    Se manda resuelta desde acá, igual que `dFeEmiDE`."""
    from datetime import timezone

    from app.utils.helpers import now_local
    from facturacion_electronica.services.data_builder import fecha_firma_digital

    cliente = Cliente(id_cliente=5, nombre='EMPRESA SRL', ruc_ci='80012345-6')
    venta = Venta(id_venta=10, tipo_venta='contado', total=11000,
                  fecha_venta=datetime(2026, 6, 24, 9, 30, 0))
    venta.cliente = cliente

    data = construir_data_venta(
        venta, _config(), detalles=[_detalle('A-1', 'Producto', 1, 11000, 10)], pagos=[],
    )

    firma = data['fechaFirmaDigital']
    # Sin offset a propósito: del lado Node `new Date()` la lee como hora local
    # y la escribe tal cual, sea cual sea la zona del servidor.
    assert '+' not in firma and 'Z' not in firma
    assert firma[:13] == now_local().strftime('%Y-%m-%dT%H')
    # Y no es la hora UTC, que es de donde venía el problema.
    hora_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H')
    assert firma[:13] != hora_utc or now_local().utcoffset().total_seconds() == 0

    assert fecha_firma_digital()[:13] == now_local().strftime('%Y-%m-%dT%H')
