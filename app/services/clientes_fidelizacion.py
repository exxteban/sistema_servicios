from decimal import Decimal

from app import db
from app.models import Cliente, ClienteFidelizacionMovimiento, Configuracion
from app.services.clientes_fidelizacion_actualizacion import actualizar_beneficios_activos_a_config
from app.services.clientes_fidelizacion_support import (
    CONFIG_FIDELIZACION_BENEFICIO_VIGENCIA_DIAS,
    CONFIG_FIDELIZACION_COMPRAS_VENTANA_DIAS,
    agrupar_resumenes,
    calcular_fecha_vencimiento_beneficio,
    compras_ventana_dias_config,
    decimal_config,
    decimal_safe,
    formatear_decimal,
    formatear_monto,
    sincronizar_beneficios_vencidos,
    vigencia_dias_config,
)
from app.services.clientes_fidelizacion_politica import (
    CONFIG_FIDELIZACION_MAX_BENEFICIOS_ACTIVOS,
    CONFIG_FIDELIZACION_MAX_BENEFICIOS_VENTANA,
    CONFIG_FIDELIZACION_MODO_GENERACION,
    MODOS_GENERACION,
    MODO_UNA_VEZ_VENTANA,
    normalizar_modo_generacion,
    obtener_tope_config,
    resolver_cantidad_beneficios_a_otorgar,
)


CONFIG_FIDELIZACION_ACTIVA = 'clientes_fidelizacion_activa'
CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS = 'clientes_fidelizacion_compras_requeridas'
CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO = 'clientes_fidelizacion_premios_por_objetivo'
CONFIG_FIDELIZACION_BENEFICIO_TIPO = 'clientes_fidelizacion_beneficio_tipo'
CONFIG_FIDELIZACION_BENEFICIO_VALOR = 'clientes_fidelizacion_beneficio_valor'
CONFIG_FIDELIZACION_BENEFICIO_DESCRIPCION = 'clientes_fidelizacion_beneficio_descripcion'

BENEFICIO_TIPOS = {
    'consumo_libre': 'Consumo o servicio libre',
    'descuento_porcentaje': 'Descuento porcentual',
    'descuento_monto': 'Descuento fijo',
    'saldo_favor': 'Saldo a favor',
}

BENEFICIO_TIPOS_POS_APLICABLES = {
    'descuento_porcentaje',
    'descuento_monto',
    'saldo_favor',
}


def fidelizacion_config():
    tipo = (Configuracion.obtener(CONFIG_FIDELIZACION_BENEFICIO_TIPO, 'consumo_libre') or 'consumo_libre').strip()
    if tipo not in BENEFICIO_TIPOS:
        tipo = 'consumo_libre'
    premios_default = Configuracion.obtener_int('clientes_fidelizacion_consumos_premio', default=1)
    return {
        'activa': Configuracion.obtener_bool(CONFIG_FIDELIZACION_ACTIVA, default=False),
        'compras_requeridas': max(1, Configuracion.obtener_int(CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS, default=5)),
        'premios_por_objetivo': max(
            1,
            Configuracion.obtener_int(CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO, default=premios_default),
        ),
        'beneficio_tipo': tipo,
        'beneficio_valor': decimal_config(CONFIG_FIDELIZACION_BENEFICIO_VALOR, default='0'),
        'beneficio_descripcion': (Configuracion.obtener(CONFIG_FIDELIZACION_BENEFICIO_DESCRIPCION, '') or '').strip(),
        'beneficio_vigencia_dias': vigencia_dias_config(),
        'compras_ventana_dias': compras_ventana_dias_config(),
        'modo_generacion': normalizar_modo_generacion(Configuracion.obtener(CONFIG_FIDELIZACION_MODO_GENERACION, '')),
        'max_beneficios_activos': obtener_tope_config(CONFIG_FIDELIZACION_MAX_BENEFICIOS_ACTIVOS),
        'max_beneficios_ventana': obtener_tope_config(CONFIG_FIDELIZACION_MAX_BENEFICIOS_VENTANA),
    }


def guardar_fidelizacion_config(
    activa,
    compras_requeridas,
    premios_por_objetivo,
    compras_ventana_dias,
    modo_generacion,
    max_beneficios_activos,
    max_beneficios_ventana,
    beneficio_tipo,
    beneficio_valor,
    beneficio_vigencia_dias,
    beneficio_descripcion,
):
    beneficio_tipo = (beneficio_tipo or 'consumo_libre').strip()
    if beneficio_tipo not in BENEFICIO_TIPOS:
        beneficio_tipo = 'consumo_libre'
    valor = decimal_safe(beneficio_valor, default=Decimal('0'))

    Configuracion.establecer_bool(CONFIG_FIDELIZACION_ACTIVA, activa, 'Activa la fidelizacion por compras de clientes')
    Configuracion.establecer(
        CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS,
        str(max(1, int(compras_requeridas or 1))),
        'Cantidad de compras necesarias para liberar un premio',
    )
    Configuracion.establecer(
        CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO,
        str(max(1, int(premios_por_objetivo or 1))),
        'Cantidad de beneficios liberados al cumplir el objetivo',
    )
    Configuracion.establecer(
        CONFIG_FIDELIZACION_COMPRAS_VENTANA_DIAS,
        str(max(1, int(compras_ventana_dias or 1))),
        'Ventana de dias hacia atras para compras validas de fidelizacion',
    )
    Configuracion.establecer(CONFIG_FIDELIZACION_MODO_GENERACION, normalizar_modo_generacion(modo_generacion), 'Modo de generacion de beneficios')
    Configuracion.establecer(CONFIG_FIDELIZACION_MAX_BENEFICIOS_ACTIVOS, str(max(0, int(max_beneficios_activos or 0))), 'Tope de beneficios activos por cliente')
    Configuracion.establecer(CONFIG_FIDELIZACION_MAX_BENEFICIOS_VENTANA, str(max(0, int(max_beneficios_ventana or 0))), 'Tope de beneficios generados por ventana')
    Configuracion.establecer(CONFIG_FIDELIZACION_BENEFICIO_TIPO, beneficio_tipo, 'Tipo de beneficio de fidelizacion')
    Configuracion.establecer(CONFIG_FIDELIZACION_BENEFICIO_VALOR, str(valor), 'Valor del beneficio de fidelizacion')
    Configuracion.establecer(
        CONFIG_FIDELIZACION_BENEFICIO_VIGENCIA_DIAS,
        str(max(1, int(beneficio_vigencia_dias or 1))),
        'Duracion en dias de cada beneficio de fidelizacion',
    )
    Configuracion.establecer(
        CONFIG_FIDELIZACION_BENEFICIO_DESCRIPCION,
        (beneficio_descripcion or '').strip()[:255],
        'Descripcion visible del beneficio de fidelizacion',
    )
    actualizar_beneficios_activos_a_config(beneficio_tipo, valor, beneficio_descripcion)


def registrar_compra_fidelizacion_por_venta(venta, id_usuario=None):
    config = fidelizacion_config()
    if not config['activa'] or not venta or int(getattr(venta, 'id_cliente', 0) or 0) <= 1:
        return _resultado_cliente(None)

    existente = ClienteFidelizacionMovimiento.query.filter_by(
        tipo_movimiento='compra_venta',
        referencia_tipo='venta',
        referencia_id=int(venta.id_venta),
        id_movimiento_origen=None,
    ).first()
    if existente:
        cliente = db.session.get(Cliente, int(venta.id_cliente))
        return _resultado_cliente(cliente)

    cliente = _bloquear_cliente(int(venta.id_cliente))
    if not cliente or cliente.es_consumidor_final or not bool(cliente.activo):
        return _resultado_cliente(cliente)

    _aplicar_estado(cliente, compras=1)
    db.session.add(_movimiento(
        cliente=cliente,
        id_usuario=id_usuario,
        tipo_movimiento='compra_venta',
        delta_compras=1,
        referencia_tipo='venta',
        referencia_id=int(venta.id_venta),
        descripcion=f'Compra acumulada por venta #{venta.id_venta}',
    ))

    beneficio = _snapshot_beneficio(config)
    beneficios_generados = 0
    while cliente.fidelizacion_compras_acumuladas_seguras >= config['compras_requeridas']:
        beneficios_a_otorgar = resolver_cantidad_beneficios_a_otorgar(cliente, config)
        if beneficios_a_otorgar <= 0:
            break
        _aplicar_estado(
            cliente,
            compras=-config['compras_requeridas'],
            disponibles=beneficios_a_otorgar,
        )
        beneficios_generados += beneficios_a_otorgar
        db.session.add(_movimiento(
            cliente=cliente,
            id_usuario=id_usuario,
            tipo_movimiento='premio_meta',
            delta_compras=-config['compras_requeridas'],
            referencia_tipo='venta',
            referencia_id=int(venta.id_venta),
            descripcion=(
                f'Objetivo cumplido por venta #{venta.id_venta}: '
                f'{beneficios_a_otorgar} beneficio(s)'
            ),
        ))
        for _ in range(beneficios_a_otorgar):
            db.session.add(_movimiento(
                cliente=cliente,
                id_usuario=id_usuario,
                tipo_movimiento='beneficio_otorgado',
                delta_consumos_disponibles=1,
                referencia_tipo='venta',
                referencia_id=int(venta.id_venta),
                beneficio_tipo=beneficio['tipo'],
                beneficio_valor=beneficio['valor'],
                beneficio_descripcion=beneficio['descripcion'],
                beneficio_fecha_vencimiento=calcular_fecha_vencimiento_beneficio(
                    config['beneficio_vigencia_dias'],
                    getattr(venta, 'fecha_venta', None),
                ),
                descripcion=(
                    f'Beneficio ganado por venta #{venta.id_venta}: '
                    f'{beneficio_resumen_snapshot(beneficio)}'
                ),
            ))
        if config.get('modo_generacion') == MODO_UNA_VEZ_VENTANA:
            break

    return _resultado_cliente(cliente, beneficios_generados=beneficios_generados)


def revertir_fidelizacion_por_anulacion_venta(venta, id_usuario=None):
    if not venta or int(getattr(venta, 'id_cliente', 0) or 0) <= 1:
        return _resultado_cliente(None)

    originales = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(venta.id_cliente),
        ClienteFidelizacionMovimiento.referencia_tipo == 'venta',
        ClienteFidelizacionMovimiento.referencia_id == int(venta.id_venta),
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento.in_(('compra_venta', 'premio_meta', 'beneficio_otorgado')),
    ).order_by(ClienteFidelizacionMovimiento.id_movimiento.asc()).all()

    canjes_venta = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(venta.id_cliente),
        ClienteFidelizacionMovimiento.referencia_tipo == 'venta',
        ClienteFidelizacionMovimiento.referencia_id == int(venta.id_venta),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'canje_venta',
    ).order_by(ClienteFidelizacionMovimiento.id_movimiento.asc()).all()

    if not originales and not canjes_venta:
        cliente = db.session.get(Cliente, int(venta.id_cliente))
        return _resultado_cliente(cliente)

    cliente = _bloquear_cliente(int(venta.id_cliente))
    if not cliente:
        return _resultado_cliente(None)

    for original in originales:
        if _tiene_hijo(int(original.id_movimiento), {'reversion_venta'}):
            continue
        compras = -int(original.delta_compras_acumuladas or 0)
        disponibles = -int(original.delta_consumos_disponibles or 0)
        canjeados = -int(original.delta_consumos_canjeados or 0)
        _aplicar_estado(cliente, compras=compras, disponibles=disponibles, canjeados=canjeados)
        db.session.add(_movimiento(
            cliente=cliente,
            id_usuario=id_usuario,
            tipo_movimiento='reversion_venta',
            delta_compras=compras,
            delta_consumos_disponibles=disponibles,
            delta_consumos_canjeados=canjeados,
            referencia_tipo='venta',
            referencia_id=int(venta.id_venta),
            id_movimiento_origen=int(original.id_movimiento),
            beneficio_tipo=original.beneficio_tipo,
            beneficio_valor=original.beneficio_valor,
            beneficio_descripcion=original.beneficio_descripcion,
            beneficio_fecha_vencimiento=original.beneficio_fecha_vencimiento,
            descripcion=f'Reversion de fidelizacion por anulacion de venta #{venta.id_venta}',
        ))

    for canje in canjes_venta:
        if _tiene_hijo(int(canje.id_movimiento), {'reversion_venta'}):
            continue
        compras = -int(canje.delta_compras_acumuladas or 0)
        disponibles = -int(canje.delta_consumos_disponibles or 0)
        canjeados = -int(canje.delta_consumos_canjeados or 0)
        _aplicar_estado(cliente, compras=compras, disponibles=disponibles, canjeados=canjeados)
        db.session.add(_movimiento(
            cliente=cliente,
            id_usuario=id_usuario,
            tipo_movimiento='reversion_venta',
            delta_compras=compras,
            delta_consumos_disponibles=disponibles,
            delta_consumos_canjeados=canjeados,
            referencia_tipo='venta',
            referencia_id=int(venta.id_venta),
            id_movimiento_origen=int(canje.id_movimiento),
            beneficio_tipo=canje.beneficio_tipo,
            beneficio_valor=canje.beneficio_valor,
            beneficio_descripcion=canje.beneficio_descripcion,
            beneficio_fecha_vencimiento=canje.beneficio_fecha_vencimiento,
            descripcion=f'Reversion de beneficio aplicado por anulacion de venta #{venta.id_venta}',
        ))

    return _resultado_cliente(cliente)


def canjear_beneficios_cliente(id_cliente, cantidad, id_usuario=None, descripcion=''):
    sincronizar_beneficios_vencidos(id_cliente=int(id_cliente), resumen_builder=beneficio_resumen_snapshot)
    cliente = _bloquear_cliente(int(id_cliente))
    if not cliente or cliente.es_consumidor_final:
        raise ValueError('Cliente no valido para fidelizacion.')

    cantidad = max(1, int(cantidad or 1))
    beneficios = beneficios_disponibles_cliente(int(cliente.id_cliente))
    if len(beneficios) < cantidad:
        raise ValueError('El cliente no tiene suficientes beneficios disponibles.')

    _aplicar_estado(cliente, disponibles=-cantidad, canjeados=cantidad)
    consumidos = []
    for beneficio in beneficios[:cantidad]:
        consumidos.append(_snapshot_desde_movimiento(beneficio))
        db.session.add(_movimiento(
            cliente=cliente,
            id_usuario=id_usuario,
            tipo_movimiento='canje_manual',
            delta_consumos_disponibles=-1,
            delta_consumos_canjeados=1,
            referencia_tipo='cliente',
            referencia_id=int(cliente.id_cliente),
            id_movimiento_origen=int(beneficio.id_movimiento),
            beneficio_tipo=beneficio.beneficio_tipo,
            beneficio_valor=beneficio.beneficio_valor,
            beneficio_descripcion=beneficio.beneficio_descripcion,
            beneficio_fecha_vencimiento=beneficio.beneficio_fecha_vencimiento,
            descripcion=(descripcion or '').strip()[:255] or (
                f'Canje manual de beneficio: {beneficio_resumen_movimiento(beneficio)}'
            ),
        ))

    return _resultado_cliente(
        cliente,
        beneficios_canjeados=cantidad,
        beneficios_canjeados_resumen=agrupar_resumenes(consumidos, beneficio_resumen_snapshot),
    )


def obtener_resumen_beneficios_cliente(id_cliente):
    sincronizar_beneficios_vencidos(id_cliente=int(id_cliente), resumen_builder=beneficio_resumen_snapshot)
    beneficios = beneficios_disponibles_cliente(int(id_cliente))
    return {
        'cantidad': len(beneficios),
        'items': agrupar_resumenes([_snapshot_desde_movimiento(item) for item in beneficios], beneficio_resumen_snapshot),
    }


def obtener_beneficios_pos_cliente(id_cliente):
    sincronizar_beneficios_vencidos(id_cliente=int(id_cliente), resumen_builder=beneficio_resumen_snapshot)
    beneficios = beneficios_disponibles_cliente(int(id_cliente))
    items = []
    for item in beneficios:
        snapshot = _snapshot_desde_movimiento(item)
        items.append({
            'id_movimiento': int(item.id_movimiento),
            'tipo': snapshot['tipo'],
            'valor': float(decimal_safe(snapshot['valor'], default=Decimal('0'))),
            'descripcion': snapshot['descripcion'],
            'resumen': beneficio_resumen_snapshot(snapshot),
            'pos_aplicable': beneficio_es_pos_aplicable(snapshot),
            'fecha_vencimiento': snapshot['fecha_vencimiento'].isoformat() if snapshot['fecha_vencimiento'] else None,
            'fecha_vencimiento_texto': snapshot['fecha_vencimiento_texto'],
        })
    return {
        'cantidad': len(items),
        'items': items,
    }


def obtener_beneficios_aplicados_venta(id_venta):
    movimientos = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.referencia_tipo == 'venta',
        ClienteFidelizacionMovimiento.referencia_id == int(id_venta),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'canje_venta',
    ).order_by(
        ClienteFidelizacionMovimiento.fecha_movimiento.asc(),
        ClienteFidelizacionMovimiento.id_movimiento.asc(),
    ).all()
    items = []
    for mov in movimientos:
        snapshot = _snapshot_desde_movimiento(mov)
        items.append({
            'tipo': snapshot['tipo'],
            'valor': float(decimal_safe(snapshot['valor'], default=Decimal('0'))),
            'descripcion': snapshot['descripcion'],
            'resumen': beneficio_resumen_snapshot(snapshot),
        })
    return items


def resolver_descuento_beneficio_pos(id_cliente, id_movimiento_beneficio, subtotal, descuento_manual=0):
    if id_movimiento_beneficio in (None, '', 0, '0'):
        return {
            'descuento_adicional': Decimal('0'),
            'beneficio_movimiento': None,
            'beneficio_resumen': '',
        }

    try:
        id_movimiento_beneficio = int(id_movimiento_beneficio)
    except (TypeError, ValueError):
        raise ValueError('El beneficio seleccionado no es válido.')

    sincronizar_beneficios_vencidos(id_cliente=int(id_cliente), resumen_builder=beneficio_resumen_snapshot)
    _bloquear_cliente(int(id_cliente))
    beneficio = _buscar_beneficio_disponible(int(id_cliente), id_movimiento_beneficio)
    if not beneficio:
        raise ValueError('El beneficio seleccionado ya no está disponible.')

    snapshot = _snapshot_desde_movimiento(beneficio)
    if not beneficio_es_pos_aplicable(snapshot):
        raise ValueError('El beneficio seleccionado no se puede aplicar automáticamente en POS.')

    base = decimal_safe(subtotal, default=Decimal('0')) - decimal_safe(descuento_manual, default=Decimal('0'))
    if base <= 0:
        raise ValueError('No hay saldo suficiente para aplicar el beneficio seleccionado.')

    descuento = calcular_descuento_beneficio_pos(snapshot, base)
    if descuento <= 0:
        raise ValueError('El beneficio seleccionado no genera descuento en esta venta.')
    if descuento >= base:
        raise ValueError('El beneficio seleccionado supera el total restante. Ajuste el descuento manual o quite el beneficio.')

    return {
        'descuento_adicional': descuento,
        'beneficio_movimiento': beneficio,
        'beneficio_resumen': beneficio_resumen_snapshot(snapshot),
    }


def registrar_canje_beneficio_en_venta(id_cliente, id_movimiento_beneficio, id_venta, id_usuario=None):
    if id_movimiento_beneficio in (None, '', 0, '0'):
        return None

    try:
        id_movimiento_beneficio = int(id_movimiento_beneficio)
    except (TypeError, ValueError):
        raise ValueError('El beneficio seleccionado no es válido.')

    sincronizar_beneficios_vencidos(id_cliente=int(id_cliente), resumen_builder=beneficio_resumen_snapshot)
    cliente = _bloquear_cliente(int(id_cliente))
    if not cliente or cliente.es_consumidor_final:
        raise ValueError('Cliente no válido para aplicar beneficios.')

    beneficio = _buscar_beneficio_disponible(int(id_cliente), id_movimiento_beneficio)
    if not beneficio:
        raise ValueError('El beneficio seleccionado ya no está disponible.')

    _aplicar_estado(cliente, disponibles=-1, canjeados=1)
    db.session.add(_movimiento(
        cliente=cliente,
        id_usuario=id_usuario,
        tipo_movimiento='canje_venta',
        delta_consumos_disponibles=-1,
        delta_consumos_canjeados=1,
        referencia_tipo='venta',
        referencia_id=int(id_venta),
        id_movimiento_origen=int(beneficio.id_movimiento),
        beneficio_tipo=beneficio.beneficio_tipo,
        beneficio_valor=beneficio.beneficio_valor,
        beneficio_descripcion=beneficio.beneficio_descripcion,
        beneficio_fecha_vencimiento=beneficio.beneficio_fecha_vencimiento,
        descripcion=f'Beneficio aplicado en venta #{id_venta}: {beneficio_resumen_movimiento(beneficio)}',
    ))
    return _snapshot_desde_movimiento(beneficio)


def beneficios_disponibles_cliente(id_cliente):
    sincronizar_beneficios_vencidos(id_cliente=int(id_cliente), resumen_builder=beneficio_resumen_snapshot)
    originales = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(id_cliente),
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'beneficio_otorgado',
        ClienteFidelizacionMovimiento.delta_consumos_disponibles > 0,
    ).order_by(
        ClienteFidelizacionMovimiento.fecha_movimiento.asc(),
        ClienteFidelizacionMovimiento.id_movimiento.asc(),
    ).all()
    return [
        item for item in originales
        if not _tiene_hijo(int(item.id_movimiento), {'canje_manual', 'canje_venta', 'reversion_venta', 'beneficio_vencido'})
    ]


def beneficio_resumen_config(config):
    return beneficio_resumen_snapshot(_snapshot_beneficio(config))


def beneficio_resumen_movimiento(movimiento):
    return beneficio_resumen_snapshot(_snapshot_desde_movimiento(movimiento))


def beneficio_resumen_snapshot(snapshot):
    tipo = (snapshot.get('tipo') or 'consumo_libre').strip()
    valor = decimal_safe(snapshot.get('valor'), default=Decimal('0'))
    descripcion = (snapshot.get('descripcion') or '').strip()
    if tipo == 'descuento_porcentaje':
        texto = f'{formatear_decimal(valor)}% de descuento'
        return f'{texto} · {descripcion}' if descripcion else texto
    if tipo == 'descuento_monto':
        texto = f'Gs. {formatear_monto(valor)} de descuento'
        return f'{texto} · {descripcion}' if descripcion else texto
    if tipo == 'saldo_favor':
        texto = f'Gs. {formatear_monto(valor)} de saldo a favor'
        return f'{texto} · {descripcion}' if descripcion else texto
    if descripcion:
        return descripcion
    return '1 consumo o servicio libre'


def beneficio_es_pos_aplicable(snapshot):
    return ((snapshot.get('tipo') or '').strip() in BENEFICIO_TIPOS_POS_APLICABLES)


def calcular_descuento_beneficio_pos(snapshot, base):
    base = decimal_safe(base, default=Decimal('0'))
    if base <= 0:
        return Decimal('0')
    tipo = (snapshot.get('tipo') or '').strip()
    valor = decimal_safe(snapshot.get('valor'), default=Decimal('0'))
    if tipo == 'descuento_porcentaje':
        return (base * valor / Decimal('100')).quantize(Decimal('0.01'))
    if tipo in {'descuento_monto', 'saldo_favor'}:
        return min(base, valor)
    return Decimal('0')


def _bloquear_cliente(id_cliente):
    return Cliente.query.filter(Cliente.id_cliente == int(id_cliente)).with_for_update().first()


def _aplicar_estado(cliente, compras=0, disponibles=0, canjeados=0):
    cliente.fidelizacion_compras_acumuladas = cliente.fidelizacion_compras_acumuladas_seguras + int(compras or 0)
    cliente.fidelizacion_consumos_disponibles = cliente.fidelizacion_consumos_disponibles_seguro + int(disponibles or 0)
    cliente.fidelizacion_consumos_canjeados = cliente.fidelizacion_consumos_canjeados_seguro + int(canjeados or 0)


def _movimiento(
    *,
    cliente,
    id_usuario,
    tipo_movimiento,
    delta_compras=0,
    delta_consumos_disponibles=0,
    delta_consumos_canjeados=0,
    referencia_tipo=None,
    referencia_id=None,
    id_movimiento_origen=None,
    beneficio_tipo=None,
    beneficio_valor=None,
    beneficio_descripcion='',
    beneficio_fecha_vencimiento=None,
    descripcion='',
):
    return ClienteFidelizacionMovimiento(
        id_cliente=int(cliente.id_cliente),
        id_usuario=id_usuario,
        tipo_movimiento=tipo_movimiento,
        delta_compras_acumuladas=int(delta_compras or 0),
        delta_consumos_disponibles=int(delta_consumos_disponibles or 0),
        delta_consumos_canjeados=int(delta_consumos_canjeados or 0),
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        id_movimiento_origen=id_movimiento_origen,
        beneficio_tipo=(beneficio_tipo or '').strip() or None,
        beneficio_valor=decimal_safe(beneficio_valor, default=None),
        beneficio_descripcion=(beneficio_descripcion or '').strip()[:255],
        beneficio_fecha_vencimiento=beneficio_fecha_vencimiento,
        descripcion=(descripcion or '').strip()[:255],
    )


def _resultado_cliente(
    cliente,
    beneficios_generados=0,
    beneficios_canjeados=0,
    beneficios_canjeados_resumen=None,
):
    resumen = obtener_resumen_beneficios_cliente(int(cliente.id_cliente)) if cliente else {'cantidad': 0, 'items': []}
    return {
        'cliente_id': int(getattr(cliente, 'id_cliente', 0) or 0) if cliente else None,
        'compras_acumuladas': int(getattr(cliente, 'fidelizacion_compras_acumuladas_seguras', 0) or 0) if cliente else 0,
        'beneficios_disponibles': int(resumen['cantidad'] or 0),
        'beneficios_canjeados_total': int(getattr(cliente, 'fidelizacion_consumos_canjeados_seguro', 0) or 0) if cliente else 0,
        'beneficios_generados': int(beneficios_generados or 0),
        'beneficios_canjeados': int(beneficios_canjeados or 0),
        'beneficios_disponibles_resumen': resumen['items'],
        'beneficios_canjeados_resumen': beneficios_canjeados_resumen or [],
    }


def _tiene_hijo(id_movimiento_origen, tipos):
    tipos = tuple(sorted(set(tipos or [])))
    if not tipos:
        return False
    return ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_movimiento_origen == int(id_movimiento_origen),
        ClienteFidelizacionMovimiento.tipo_movimiento.in_(tipos),
    ).first() is not None


def _snapshot_beneficio(config):
    return {
        'tipo': config.get('beneficio_tipo') or 'consumo_libre',
        'valor': decimal_safe(config.get('beneficio_valor'), default=Decimal('0')),
        'descripcion': (config.get('beneficio_descripcion') or '').strip(),
    }


def _snapshot_desde_movimiento(movimiento):
    return {
        'tipo': (getattr(movimiento, 'beneficio_tipo', '') or 'consumo_libre').strip(),
        'valor': decimal_safe(getattr(movimiento, 'beneficio_valor', 0), default=Decimal('0')),
        'descripcion': (getattr(movimiento, 'beneficio_descripcion', '') or '').strip(),
        'fecha_vencimiento': getattr(movimiento, 'beneficio_fecha_vencimiento', None),
        'fecha_vencimiento_texto': (
            getattr(movimiento, 'beneficio_fecha_vencimiento', None).strftime('%d/%m/%Y')
            if getattr(movimiento, 'beneficio_fecha_vencimiento', None)
            else ''
        ),
    }


def _buscar_beneficio_disponible(id_cliente, id_movimiento):
    beneficio = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(id_cliente),
        ClienteFidelizacionMovimiento.id_movimiento == int(id_movimiento),
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'beneficio_otorgado',
        ClienteFidelizacionMovimiento.delta_consumos_disponibles > 0,
    ).first()
    if not beneficio:
        return None
    if _tiene_hijo(int(beneficio.id_movimiento), {'canje_manual', 'canje_venta', 'reversion_venta', 'beneficio_vencido'}):
        return None
    return beneficio
