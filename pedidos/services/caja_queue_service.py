from datetime import datetime

from app import db
from app.models import ColaCobro, MetodoPago, SesionCaja
from pedidos.models import PedidoCliente
from pedidos.services.pago_service import (
    TIPO_PAGO_TOTAL,
    TIPOS_PAGO_PEDIDO,
    _es_metodo_credito_tienda,
    registrar_pago_pedido,
)
from pedidos.services.pedido_service import _clean_text, _to_decimal, recalcular_totales_pedido


def _validar_pedido_cobrable(pedido: PedidoCliente):
    if pedido is None:
        raise ValueError('Pedido no encontrado')
    if (pedido.estado or '').strip().lower() == 'cancelado':
        raise ValueError('El pedido esta cancelado y no puede enviarse a caja')
    recalcular_totales_pedido(pedido)
    if float(pedido.saldo_pendiente or 0) <= 0:
        raise ValueError('El pedido ya no tiene saldo pendiente')
    cliente = getattr(pedido, 'cliente', None)
    if cliente is None or not bool(getattr(cliente, 'activo', False)):
        raise ValueError('Cliente no encontrado o inactivo')
    return pedido


def _construir_metadata_pendiente(pedido: PedidoCliente) -> dict:
    cliente = getattr(pedido, 'cliente', None)
    return {
        'id_pedido': int(pedido.id_pedido),
        'numero_pedido': pedido.numero_pedido_display,
        'id_cliente': int(pedido.id_cliente),
        'cliente_nombre': ((getattr(cliente, 'nombre', None) or '') if cliente else '').strip() or f'Cliente #{int(pedido.id_cliente)}',
        'estado_pedido': (pedido.estado or '').strip(),
        'subtotal': float(pedido.subtotal or 0),
        'total': float(pedido.total or 0),
        'total_pagado': float(pedido.total_pagado or 0),
        'saldo_pendiente': float(pedido.saldo_pendiente or 0),
        'monto_sugerido': float(pedido.saldo_pendiente or 0),
    }


def _normalizar_cobro_sugerido(pedido: PedidoCliente, datos_cobro: dict | None = None) -> dict:
    datos_cobro = datos_cobro or {}
    saldo = _to_decimal(pedido.saldo_pendiente)
    monto_raw = datos_cobro.get('monto')
    monto = saldo if monto_raw in (None, '') else _to_decimal(monto_raw)
    if monto <= 0:
        raise ValueError('El monto a enviar a caja debe ser mayor a cero')
    if monto > saldo:
        raise ValueError('El monto a enviar a caja no puede superar el saldo pendiente')

    tipo_pago = _clean_text(datos_cobro.get('tipo_pago'))
    if not tipo_pago:
        tipo_pago = TIPO_PAGO_TOTAL if monto == saldo else 'pago_parcial'
    if tipo_pago not in TIPOS_PAGO_PEDIDO:
        raise ValueError('Tipo de pago invalido')
    if tipo_pago == TIPO_PAGO_TOTAL and monto != saldo:
        raise ValueError('El pago total debe coincidir con el saldo pendiente')

    id_metodo_pago = None
    metodo_nombre = ''
    id_metodo_raw = datos_cobro.get('id_metodo_pago')
    if id_metodo_raw not in (None, ''):
        try:
            id_metodo_pago = int(id_metodo_raw)
        except (TypeError, ValueError):
            raise ValueError('Debe seleccionar un metodo de pago valido')
        metodo = MetodoPago.query.filter_by(id_metodo_pago=id_metodo_pago, activo=True).first()
        if metodo is None or _es_metodo_credito_tienda(getattr(metodo, 'nombre', '')):
            raise ValueError('Debe seleccionar un metodo de pago valido')
        metodo_nombre = (metodo.nombre or '').strip()

    return {
        'tipo_pago': tipo_pago,
        'id_metodo_pago': id_metodo_pago,
        'metodo_nombre': metodo_nombre,
        'monto': float(monto.quantize(_to_decimal('0.01'))),
        'referencia': _clean_text(datos_cobro.get('referencia'), 100),
        'observaciones': _clean_text(datos_cobro.get('observaciones'), 250),
    }


def _metadata_pendiente_con_cobro(pedido: PedidoCliente, datos_cobro: dict | None = None) -> dict:
    metadata = _construir_metadata_pendiente(pedido)
    cobro_sugerido = _normalizar_cobro_sugerido(pedido, datos_cobro)
    metadata['monto_sugerido'] = cobro_sugerido['monto']
    metadata['cobro_sugerido'] = cobro_sugerido
    return metadata


def obtener_pendiente_activo_pedido(id_pedido: int):
    return (
        ColaCobro.query
        .filter(
            ColaCobro.tipo_origen == 'pedido',
            ColaCobro.id_origen == int(id_pedido),
            ColaCobro.estado.in_(('pendiente', 'en_proceso')),
        )
        .order_by(ColaCobro.id.desc())
        .first()
    )


def obtener_o_crear_pendiente_cobro_pedido(
    pedido: PedidoCliente,
    *,
    id_usuario_origen: int,
    datos_cobro: dict | None = None,
):
    pedido = _validar_pedido_cobrable(pedido)
    metadata = _metadata_pendiente_con_cobro(pedido, datos_cobro)
    pendiente = obtener_pendiente_activo_pedido(int(pedido.id_pedido))
    creado = pendiente is None
    if pendiente is None:
        pendiente = ColaCobro(
            tipo_origen='pedido',
            id_origen=int(pedido.id_pedido),
            id_cliente=int(pedido.id_cliente),
            monto_total=metadata['monto_sugerido'],
            id_usuario_origen=int(id_usuario_origen),
            estado='pendiente',
        )
        db.session.add(pendiente)
    else:
        pendiente.id_cliente = int(pedido.id_cliente)
        pendiente.monto_total = metadata['monto_sugerido']
        pendiente.id_usuario_origen = int(id_usuario_origen)
    pendiente.set_metadata(metadata)
    db.session.flush()
    return pendiente, creado


def _validar_estado_pendiente_pedido(item: ColaCobro):
    estado = (getattr(item, 'estado', '') or '').strip().lower()
    if estado == 'cobrado':
        raise ValueError('Este pendiente ya fue cobrado')
    if estado == 'cancelado':
        raise ValueError('Este pendiente fue cancelado')
    if estado == 'pendiente':
        raise ValueError('Debe tomar el pendiente antes de cobrarlo')
    if estado != 'en_proceso':
        raise ValueError('Este pendiente ya no esta disponible')


def construir_contexto_cobro_pedido_caja(item: ColaCobro) -> dict:
    if item is None or (item.tipo_origen or '').strip().lower() != 'pedido':
        raise ValueError('El pendiente indicado no corresponde a un pedido')

    metadata = item.get_metadata()
    pedido_id = metadata.get('id_pedido') or item.id_origen
    pedido = db.session.get(PedidoCliente, int(pedido_id or 0))
    pedido = _validar_pedido_cobrable(pedido)
    datos_cobro = metadata.get('cobro_sugerido') if isinstance(metadata.get('cobro_sugerido'), dict) else None
    metadata_actualizada = _metadata_pendiente_con_cobro(pedido, datos_cobro)
    item.id_origen = int(pedido.id_pedido)
    item.id_cliente = int(pedido.id_cliente)
    item.monto_total = metadata_actualizada['monto_sugerido']
    item.set_metadata(metadata_actualizada)
    db.session.flush()
    return {
        'item': item,
        'pedido': pedido,
        'metadata': metadata_actualizada,
    }


def registrar_cobro_pedido_desde_cola(
    item: ColaCobro,
    *,
    id_usuario: int,
    id_metodo_pago: int,
    monto,
    tipo_pago: str,
    referencia: str = '',
    observaciones: str = '',
    sesion: SesionCaja | None = None,
):
    _validar_estado_pendiente_pedido(item)
    contexto = construir_contexto_cobro_pedido_caja(item)
    pedido = contexto['pedido']
    metadata = dict(contexto['metadata'] or {})
    resultado = registrar_pago_pedido(
        pedido,
        id_metodo_pago=int(id_metodo_pago),
        monto=monto,
        tipo_pago=tipo_pago,
        referencia=referencia,
        observaciones=observaciones,
        id_usuario=int(id_usuario),
        sesion=sesion,
    )
    pago = resultado['pago']
    pedido_actualizado = resultado['pedido']
    movimiento = resultado['movimiento_caja']

    metadata.update({
        'id_pago_pedido': int(pago.id_pago_pedido),
        'tipo_pago': (pago.tipo_pago or '').strip(),
        'monto_cobrado': float(pago.monto or 0),
        'saldo_pendiente_resultante': float(pedido_actualizado.saldo_pendiente or 0),
        'total_pagado_resultante': float(pedido_actualizado.total_pagado or 0),
        'estado_pedido_resultante': (pedido_actualizado.estado or '').strip(),
        'cerrado_por_usuario': int(id_usuario),
        'id_movimiento_caja': int(movimiento.id_movimiento_caja) if movimiento and movimiento.id_movimiento_caja else None,
    })
    item.id_origen = int(pedido_actualizado.id_pedido)
    item.id_cliente = int(pedido_actualizado.id_cliente)
    item.monto_total = float(pago.monto or 0)
    item.id_usuario_destino = int(id_usuario)
    item.fecha_toma = item.fecha_toma or datetime.utcnow()
    item.fecha_cobro = datetime.utcnow()
    item.estado = 'cobrado'
    item.set_metadata(metadata)

    resultado['cola_cobro'] = item
    resultado['metadata_cola'] = metadata
    return resultado
