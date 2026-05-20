from datetime import datetime

from app import db
from app.models import ColaCobro, CuentaPorCobrar, SesionCaja
from cobranzas.services.cobranza_service import registrar_cobro_credito
from cobranzas.services.cuenta_service import construir_vista_cuenta, sincronizar_saldos_cuenta
from cobranzas.services.cuotas_service import obtener_plan_credito_vigente, sincronizar_plan_credito


def _refrescar_cuenta_para_caja(cuenta: CuentaPorCobrar) -> dict:
    if cuenta is None:
        raise ValueError('Cuenta por cobrar no encontrada')

    plan_credito = obtener_plan_credito_vigente(cuenta)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        sincronizar_plan_credito(plan_credito)
    sincronizar_saldos_cuenta(cuenta)
    db.session.flush()
    return construir_vista_cuenta(cuenta)


def _serializar_proxima_cuota(cuenta_vista: dict) -> dict | None:
    plan_credito = cuenta_vista.get('plan_credito') or {}
    cuota = plan_credito.get('proxima_cuota')
    if not cuota:
        return None
    return {
        'id_cuota_credito': int(getattr(cuota.get('cuota'), 'id_cuota_credito', 0) or 0) or None,
        'numero_cuota': int(cuota.get('numero_cuota') or 0) or None,
        'fecha_vencimiento': cuota['fecha_vencimiento'].isoformat() if cuota.get('fecha_vencimiento') else None,
        'saldo_pendiente': float(cuota.get('saldo_pendiente') or 0),
        'estado': (cuota.get('estado') or '').strip().lower() or None,
    }


def _construir_metadata_pendiente(cuenta: CuentaPorCobrar, cuenta_vista: dict) -> dict:
    cliente = getattr(cuenta, 'cliente', None)
    venta = getattr(cuenta, 'venta', None)
    return {
        'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
        'id_cliente': int(cuenta.id_cliente),
        'cliente_nombre': ((getattr(cliente, 'nombre', None) or '') if cliente else '').strip() or f'Cliente #{int(cuenta.id_cliente)}',
        'id_venta': int(cuenta.id_venta),
        'estado_cuenta': cuenta.estado,
        'saldo_pendiente': float(cuenta.saldo_pendiente or 0),
        'monto_sugerido': float(cuenta_vista.get('monto_sugerido_cobro') or 0),
        'sugerencia_cobro': cuenta_vista.get('sugerencia_cobro') or {},
        'proxima_cuota': _serializar_proxima_cuota(cuenta_vista),
        'fecha_venta': venta.fecha_venta.isoformat() if venta is not None and getattr(venta, 'fecha_venta', None) else None,
    }


def _validar_estado_pendiente_cobro_credito(item: ColaCobro) -> None:
    estado = (getattr(item, 'estado', '') or '').strip().lower()
    if estado == 'cobrado':
        raise ValueError('Este pendiente ya fue cobrado')
    if estado == 'cancelado':
        raise ValueError('Este pendiente fue cancelado')
    if estado == 'pendiente':
        raise ValueError('Debe tomar el pendiente antes de cobrarlo')
    if estado != 'en_proceso':
        raise ValueError('Este pendiente ya no esta disponible')


def obtener_o_crear_pendiente_cobro_credito(cuenta: CuentaPorCobrar, *, id_usuario_origen: int) -> tuple[ColaCobro, bool]:
    cuenta_vista = _refrescar_cuenta_para_caja(cuenta)
    if not cuenta_vista.get('tiene_saldo'):
        raise ValueError('La cuenta ya no tiene saldo pendiente')

    metadata = _construir_metadata_pendiente(cuenta, cuenta_vista)
    pendiente = (
        ColaCobro.query
        .filter(
            ColaCobro.tipo_origen == 'cobro_credito',
            ColaCobro.id_origen == int(cuenta.id_cuenta_cobrar),
            ColaCobro.estado.in_(('pendiente', 'en_proceso')),
        )
        .order_by(ColaCobro.id.desc())
        .first()
    )
    creado = pendiente is None
    if pendiente is None:
        pendiente = ColaCobro(
            tipo_origen='cobro_credito',
            id_origen=int(cuenta.id_cuenta_cobrar),
            id_cliente=int(cuenta.id_cliente),
            monto_total=metadata['monto_sugerido'],
            id_usuario_origen=int(id_usuario_origen),
            estado='pendiente',
        )
        db.session.add(pendiente)
    else:
        pendiente.id_cliente = int(cuenta.id_cliente)
        pendiente.monto_total = metadata['monto_sugerido']
        pendiente.id_usuario_origen = int(id_usuario_origen)
    pendiente.set_metadata(metadata)
    db.session.flush()
    return pendiente, creado


def construir_contexto_cobro_credito_caja(item: ColaCobro) -> dict:
    if item is None or (item.tipo_origen or '').strip().lower() != 'cobro_credito':
        raise ValueError('El pendiente indicado no corresponde a un cobro de crédito')

    metadata = item.get_metadata()
    cuenta_id = metadata.get('id_cuenta_cobrar') or item.id_origen
    cuenta = db.session.get(CuentaPorCobrar, int(cuenta_id or 0))
    cuenta_vista = _refrescar_cuenta_para_caja(cuenta)
    metadata_actualizada = _construir_metadata_pendiente(cuenta, cuenta_vista)
    item.id_cliente = int(cuenta.id_cliente)
    item.monto_total = metadata_actualizada['monto_sugerido']
    item.set_metadata(metadata_actualizada)
    db.session.flush()
    return {
        'item': item,
        'cuenta': cuenta,
        'cuenta_vista': cuenta_vista,
        'metadata': metadata_actualizada,
        'proxima_cuota': metadata_actualizada.get('proxima_cuota'),
    }


def registrar_cobro_credito_desde_cola(
    item: ColaCobro,
    *,
    id_usuario: int,
    id_metodo_pago: int,
    monto,
    referencia: str = '',
    observaciones: str = '',
    sesion: SesionCaja | None = None,
):
    _validar_estado_pendiente_cobro_credito(item)
    contexto = construir_contexto_cobro_credito_caja(item)
    cuenta = contexto['cuenta']
    metadata = dict(contexto['metadata'] or {})
    resultado = registrar_cobro_credito(
        cuenta,
        id_usuario=int(id_usuario),
        id_metodo_pago=int(id_metodo_pago),
        monto=monto,
        referencia=referencia,
        observaciones=observaciones,
        sesion=sesion,
    )
    pago = resultado['pago']
    cuenta_actualizada = resultado['cuenta']

    metadata.update({
        'id_pago_cuenta': int(pago.id_pago_cuenta),
        'numero_cuota_principal': int(pago.numero_cuota_principal or 0) or None,
        'id_cuota_credito_principal': int(pago.id_cuota_credito_principal or 0) or None,
        'monto_cobrado': float(pago.monto or 0),
        'saldo_pendiente_resultante': float(cuenta_actualizada.saldo_pendiente or 0),
        'cerrado_por_usuario': int(id_usuario),
    })
    item.id_origen = int(cuenta_actualizada.id_cuenta_cobrar)
    item.id_cliente = int(cuenta_actualizada.id_cliente)
    item.monto_total = float(pago.monto or 0)
    item.id_usuario_destino = int(id_usuario)
    item.fecha_toma = item.fecha_toma or datetime.utcnow()
    item.fecha_cobro = datetime.utcnow()
    item.estado = 'cobrado'
    item.set_metadata(metadata)

    resultado['cola_cobro'] = item
    resultado['metadata_cola'] = metadata
    return resultado
