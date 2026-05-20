from datetime import date, datetime
from decimal import Decimal
import unicodedata

from app import db
from app.models import Configuracion, CuentaPorCobrar, MetodoPago, MovimientoCaja, PagoCuentaCobrar, SesionCaja
from cobranzas import CLAVE_VENTAS_CREDITO_METODO_PAGO_ID
from cobranzas.services.cuenta_service import sincronizar_saldos_cuenta
from cobranzas.services.cuotas_service import imputar_pago_a_cuotas, obtener_plan_credito_vigente, sincronizar_plan_credito


def _norm_metodo_nombre(nombre: str) -> str:
    texto = (nombre or '').strip().lower()
    texto = texto.replace('Ã¡', 'a').replace('Ã©', 'e').replace('Ã­', 'i').replace('Ã³', 'o').replace('Ãº', 'u').replace('Ã±', 'n')
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(char for char in texto if not unicodedata.combining(char))
    return ' '.join(texto.split())


def _es_metodo_efectivo(nombre: str) -> bool:
    """Delegado canonico: usa `app.services.caja_metodos.es_metodo_efectivo`."""
    from app.services.caja_metodos import es_metodo_efectivo as _svc_es_efectivo
    return _svc_es_efectivo(nombre)


def es_metodo_credito_tienda(nombre: str) -> bool:
    return _norm_metodo_nombre(nombre) in {'credito tienda', 'venta a credito'}


def _resolver_metodo_credito_tienda(*, solo_activos: bool = True) -> MetodoPago | None:
    metodo_credito_id = Configuracion.obtener_int(CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, default=0)
    if metodo_credito_id > 0:
        metodo = db.session.get(MetodoPago, metodo_credito_id)
        if metodo and (not solo_activos or bool(getattr(metodo, 'activo', False))):
            return metodo

    query = MetodoPago.query
    if solo_activos:
        query = query.filter(MetodoPago.activo == True)
    candidatos = [metodo for metodo in query.all() if es_metodo_credito_tienda(getattr(metodo, 'nombre', ''))]
    if not candidatos:
        return None
    candidatos.sort(key=lambda metodo: (int(getattr(metodo, 'orden_display', 0) or 0), int(getattr(metodo, 'id_metodo_pago', 0) or 0)))
    return candidatos[0]


def _metodo_pago_es_credito_tienda(metodo: MetodoPago | None) -> bool:
    if metodo is None:
        return False
    metodo_credito = _resolver_metodo_credito_tienda(solo_activos=False)
    if metodo_credito is not None:
        try:
            return int(metodo.id_metodo_pago) == int(metodo_credito.id_metodo_pago)
        except Exception:
            return False
    return es_metodo_credito_tienda(getattr(metodo, 'nombre', ''))


def _obtener_cuenta_bloqueada(cuenta: CuentaPorCobrar) -> CuentaPorCobrar:
    cuenta_id = int(getattr(cuenta, 'id_cuenta_cobrar', 0) or 0)
    if cuenta_id <= 0:
        raise ValueError('Cuenta por cobrar no encontrada')
    cuenta_bloqueada = (
        db.session.query(CuentaPorCobrar)
        .filter(CuentaPorCobrar.id_cuenta_cobrar == cuenta_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if cuenta_bloqueada is None:
        raise ValueError('Cuenta por cobrar no encontrada')
    return cuenta_bloqueada


def _obtener_pago_bloqueado(pago: PagoCuentaCobrar) -> PagoCuentaCobrar:
    pago_id = int(getattr(pago, 'id_pago_cuenta', 0) or 0)
    if pago_id <= 0:
        raise ValueError('Pago de credito no encontrado')
    pago_bloqueado = (
        db.session.query(PagoCuentaCobrar)
        .filter(PagoCuentaCobrar.id_pago_cuenta == pago_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if pago_bloqueado is None:
        raise ValueError('Pago de credito no encontrado')
    return pago_bloqueado


def _serializar_aplicaciones_pago(cuenta: CuentaPorCobrar, pago: PagoCuentaCobrar, aplicaciones: list) -> dict:
    cliente = getattr(cuenta, 'cliente', None)
    cliente_nombre = ((getattr(cliente, 'nombre', None) or '') if cliente else '').strip() or f'Cliente #{int(cuenta.id_cliente)}'
    cuotas_aplicadas = []
    for aplicacion in aplicaciones or []:
        cuota = getattr(aplicacion, 'cuota', None)
        numero_cuota = int(getattr(cuota, 'numero_cuota', 0) or 0) if cuota is not None else None
        cuotas_aplicadas.append({
            'id_aplicacion': int(getattr(aplicacion, 'id_aplicacion', 0) or 0) or None,
            'id_cuota_credito': int(getattr(aplicacion, 'id_cuota_credito', 0) or 0) or None,
            'numero_cuota': numero_cuota,
            'fecha_vencimiento': cuota.fecha_vencimiento.isoformat() if cuota is not None and getattr(cuota, 'fecha_vencimiento', None) else None,
            'monto_aplicado': float(getattr(aplicacion, 'monto_aplicado', 0) or 0),
        })

    cuota_principal = cuotas_aplicadas[0] if cuotas_aplicadas else None
    return {
        'id_pago_cuenta': int(getattr(pago, 'id_pago_cuenta', 0) or 0) or None,
        'id_cuenta_cobrar': int(getattr(cuenta, 'id_cuenta_cobrar', 0) or 0) or None,
        'id_cliente': int(getattr(cuenta, 'id_cliente', 0) or 0) or None,
        'cliente_nombre': cliente_nombre,
        'id_venta': int(getattr(cuenta, 'id_venta', 0) or 0) or None,
        'cuota_principal': cuota_principal,
        'cuotas_aplicadas': cuotas_aplicadas,
    }


def registrar_cobro_credito(
    cuenta: CuentaPorCobrar,
    *,
    id_usuario: int,
    id_metodo_pago: int,
    monto,
    referencia: str = '',
    observaciones: str = '',
    sesion: SesionCaja | None = None,
):
    if cuenta is None:
        raise ValueError('Cuenta por cobrar no encontrada')
    cuenta = _obtener_cuenta_bloqueada(cuenta)
    plan_credito = obtener_plan_credito_vigente(cuenta, for_update=True)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        sincronizar_plan_credito(plan_credito)
        sincronizar_saldos_cuenta(cuenta)

    venta = getattr(cuenta, 'venta', None)
    if venta is not None and (venta.estado or '').strip().lower() == 'anulada':
        raise ValueError('La venta asociada esta anulada')
    if (cuenta.estado or '').strip().lower() == 'anulada':
        raise ValueError('La cuenta por cobrar esta anulada')

    try:
        monto = Decimal(str(monto or 0))
    except Exception as exc:
        raise ValueError('Monto invalido') from exc
    if monto <= 0:
        raise ValueError('El monto debe ser mayor a cero')

    saldo_actual = Decimal(str(cuenta.saldo_pendiente or 0))
    if saldo_actual <= 0:
        raise ValueError('La cuenta ya no tiene saldo pendiente')
    if monto > saldo_actual:
        raise ValueError('El monto no puede superar el saldo pendiente')

    try:
        id_metodo_pago = int(id_metodo_pago)
    except Exception as exc:
        raise ValueError('Metodo de pago invalido') from exc

    metodo = db.session.get(MetodoPago, id_metodo_pago)
    if not metodo or not bool(metodo.activo):
        raise ValueError('Metodo de pago invalido')
    if _metodo_pago_es_credito_tienda(metodo):
        raise ValueError('No se puede registrar un cobro usando Credito Tienda')
    referencia_limpia = (referencia or '').strip()
    observaciones_limpias = (observaciones or '').strip()
    if bool(getattr(metodo, 'requiere_referencia', False)) and not referencia_limpia:
        raise ValueError(f'El metodo de pago {metodo.nombre} requiere referencia')

    sesion_abierta = sesion
    if sesion_abierta is None:
        sesion_abierta = SesionCaja.query.filter_by(id_usuario=id_usuario, estado='abierta').first()
    if sesion_abierta is None:
        raise ValueError('No hay caja abierta')

    pago = PagoCuentaCobrar(
        id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar),
        id_sesion_caja=int(sesion_abierta.id_sesion),
        id_usuario=int(id_usuario),
        monto=monto,
        id_metodo_pago=int(metodo.id_metodo_pago),
        referencia=referencia_limpia or None,
        observaciones=observaciones_limpias or None,
        estado='activo',
    )
    db.session.add(pago)
    db.session.flush()

    movimiento = None
    if _es_metodo_efectivo(metodo.nombre):
        movimiento = MovimientoCaja(
            id_sesion_caja=int(sesion_abierta.id_sesion),
            id_usuario=int(id_usuario),
            tipo='ingreso',
            monto=monto,
            motivo=f'Cobro Credito Cuenta #{cuenta.id_cuenta_cobrar}',
            referencia_tipo='cobro_credito',
            referencia_id=int(pago.id_pago_cuenta),
            fecha_movimiento=pago.fecha_pago,
        )
        db.session.add(movimiento)

    aplicaciones = imputar_pago_a_cuotas(cuenta, pago)
    detalle_aplicacion = _serializar_aplicaciones_pago(cuenta, pago, aplicaciones)
    cuota_principal = detalle_aplicacion.get('cuota_principal') or {}
    pago.cliente_nombre_snapshot = detalle_aplicacion.get('cliente_nombre')
    pago.id_cuota_credito_principal = cuota_principal.get('id_cuota_credito')
    pago.numero_cuota_principal = cuota_principal.get('numero_cuota')
    plan_credito = obtener_plan_credito_vigente(cuenta, for_update=True)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        sincronizar_plan_credito(plan_credito, fecha=(pago.fecha_pago.date() if pago.fecha_pago else None))
        cuenta.monto_cobrado = Decimal(str(plan_credito.monto_cobrado or 0))
    else:
        cuenta.monto_cobrado = Decimal(str(cuenta.monto_cobrado or 0)) + monto
    sincronizar_saldos_cuenta(cuenta)
    detalle_aplicacion['saldo_cuenta_antes'] = float(saldo_actual)
    detalle_aplicacion['saldo_cuenta_despues'] = float(cuenta.saldo_pendiente or 0)
    pago.set_detalle_aplicacion(detalle_aplicacion)
    if movimiento is not None:
        motivo = f'Cobro Credito Cuenta #{cuenta.id_cuenta_cobrar}'
        cliente_nombre = (detalle_aplicacion.get('cliente_nombre') or '').strip()
        if cliente_nombre:
            motivo = f'{motivo} - {cliente_nombre}'
        numero_cuota = cuota_principal.get('numero_cuota')
        if numero_cuota:
            motivo = f'{motivo} - Cuota #{int(numero_cuota)}'
        movimiento.motivo = motivo

    return {
        'pago': pago,
        'cuenta': cuenta,
        'metodo': metodo,
        'sesion': sesion_abierta,
        'movimiento_caja': movimiento,
        'aplicaciones': aplicaciones,
        'plan_credito': plan_credito,
        'saldo_anterior': saldo_actual,
        'saldo_nuevo': Decimal(str(cuenta.saldo_pendiente or 0)),
    }


def anular_cobro_credito(
    pago: PagoCuentaCobrar,
    *,
    id_usuario: int,
    motivo_anulacion: str = '',
    sesion: SesionCaja | None = None,
):
    if pago is None:
        raise ValueError('Pago de credito no encontrado')
    pago = _obtener_pago_bloqueado(pago)
    if pago.esta_anulado():
        raise ValueError('El cobro ya fue anulado')

    cuenta = _obtener_cuenta_bloqueada(db.session.get(CuentaPorCobrar, int(pago.id_cuenta_cobrar or 0)))
    if (cuenta.estado or '').strip().lower() == 'anulada':
        raise ValueError('La cuenta por cobrar esta anulada')

    monto_pago = Decimal(str(pago.monto or 0))
    if monto_pago <= 0:
        raise ValueError('El pago no tiene un monto valido para revertir')

    sesion_abierta = sesion
    movimiento_reversa = None
    if pago.metodo and _es_metodo_efectivo(pago.metodo.nombre):
        if sesion_abierta is None:
            sesion_abierta = SesionCaja.query.filter_by(id_usuario=id_usuario, estado='abierta').first()
        if sesion_abierta is None:
            raise ValueError('No hay caja abierta para revertir un cobro en efectivo')
        movimiento_reversa = MovimientoCaja(
            id_sesion_caja=int(sesion_abierta.id_sesion),
            id_usuario=int(id_usuario),
            tipo='egreso',
            monto=monto_pago,
            motivo=f'Reversa cobro credito #{pago.id_pago_cuenta}',
            referencia_tipo='anulacion_cobro_credito',
            referencia_id=int(pago.id_pago_cuenta),
            fecha_movimiento=datetime.utcnow(),
        )
        db.session.add(movimiento_reversa)
        db.session.flush()

    saldo_anterior = Decimal(str(cuenta.saldo_pendiente or 0))
    pago.estado = 'anulado'
    pago.fecha_anulacion = datetime.utcnow()
    pago.id_usuario_anulacion = int(id_usuario)
    pago.motivo_anulacion = (motivo_anulacion or '').strip() or None
    pago.id_movimiento_reversa = int(movimiento_reversa.id_movimiento_caja) if movimiento_reversa else None

    plan_credito = obtener_plan_credito_vigente(cuenta, for_update=True)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        sincronizar_plan_credito(plan_credito, fecha=date.today())
        cuenta.monto_cobrado = Decimal(str(plan_credito.monto_cobrado or 0))
    else:
        cuenta.monto_cobrado = Decimal(str(cuenta.monto_cobrado or 0)) - monto_pago
        if cuenta.monto_cobrado < 0:
            cuenta.monto_cobrado = Decimal('0')
    sincronizar_saldos_cuenta(cuenta)

    return {
        'pago': pago,
        'cuenta': cuenta,
        'movimiento_caja': movimiento_reversa,
        'plan_credito': plan_credito,
        'saldo_anterior': saldo_anterior,
        'saldo_nuevo': Decimal(str(cuenta.saldo_pendiente or 0)),
    }
