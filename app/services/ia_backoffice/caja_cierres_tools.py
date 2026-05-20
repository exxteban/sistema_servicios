from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models import SesionCaja
from app.routes.caja.common import _calcular_informe_cierre_sesion
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _puede_ver_otras_cajas(usuario) -> bool:
    if not usuario:
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(getattr(usuario, 'tiene_permiso', lambda _codigo: False)('ver_otras_cajas'))


def _query_cierres(usuario):
    query = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .filter(SesionCaja.estado == 'cerrada', SesionCaja.fecha_cierre.isnot(None))
    )
    if _puede_ver_otras_cajas(usuario):
        return query
    usuario_id = int(getattr(usuario, 'id_usuario', 0) or 0)
    return query.filter(or_(SesionCaja.id_usuario == usuario_id, SesionCaja.id_usuario_cierre == usuario_id))


def _sesion_payload(sesion) -> dict:
    return {
        'id_sesion': int(sesion.id_sesion),
        'caja': sesion.caja.nombre if sesion.caja else '',
        'usuario_apertura': sesion.usuario.username if sesion.usuario else '',
        'usuario_cierre': sesion.usuario_cierre.username if sesion.usuario_cierre else '',
        'fecha_apertura': sesion.fecha_apertura.isoformat() if sesion.fecha_apertura else None,
        'fecha_cierre': sesion.fecha_cierre.isoformat() if sesion.fecha_cierre else None,
        'monto_inicial': _money(sesion.monto_inicial),
        'monto_sistema': _money(sesion.monto_final_sistema),
        'monto_declarado': _money(sesion.monto_final_declarado),
        'diferencia': _money(sesion.diferencia),
        'estado_diferencia': _estado_diferencia(_money(sesion.diferencia)),
    }


def _estado_diferencia(diferencia: float) -> str:
    if diferencia > 0:
        return 'sobrante'
    if diferencia < 0:
        return 'faltante'
    return 'cuadrado'


def _resolver_sesion(args: dict | None, usuario):
    data = args or {}
    sesion_id = data.get('id_sesion')
    query = _query_cierres(usuario)
    if sesion_id:
        try:
            return query.filter(SesionCaja.id_sesion == int(sesion_id)).first()
        except Exception:
            return None
    return query.order_by(SesionCaja.fecha_cierre.desc(), SesionCaja.id_sesion.desc()).first()


def _informe(args: dict | None, usuario):
    sesion = _resolver_sesion(args, usuario)
    if not sesion:
        return None, None
    return sesion, _calcular_informe_cierre_sesion(sesion)


def caja_cierres_recientes(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    cierres = (
        _query_cierres(usuario)
        .filter(SesionCaja.fecha_cierre >= inicio_utc, SesionCaja.fecha_cierre < fin_utc)
        .order_by(SesionCaja.fecha_cierre.desc(), SesionCaja.id_sesion.desc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'cierres': [_sesion_payload(sesion) for sesion in cierres],
    }


def caja_cierre_detalle(args: dict | None = None, usuario=None) -> dict:
    sesion, informe = _informe(args, usuario)
    if not sesion:
        return {'encontrado': False}
    conceptos = [_concepto_payload(item) for item in informe.get('conceptos') or []]
    return {
        'encontrado': True,
        'sesion': _sesion_payload(sesion),
        'total_ingresos': _money(informe.get('total_ingresos')),
        'total_egresos': _money(informe.get('total_egresos')),
        'neto': _money(informe.get('neto')),
        'total_efectivo_sistema': _money(informe.get('total_efectivo_sistema')),
        'ingreso_real_efectivo': _money(informe.get('ingreso_real_efectivo')),
        'conceptos': conceptos,
        'formula': 'monto_sistema = efectivo esperado al cierre; diferencia = monto_declarado - monto_sistema.',
    }


def caja_cierre_diferencia(args: dict | None = None, usuario=None) -> dict:
    sesion, informe = _informe(args, usuario)
    if not sesion:
        return {'encontrado': False}
    diferencia = _money(sesion.diferencia)
    conceptos = sorted(
        [_concepto_payload(item) for item in informe.get('conceptos') or []],
        key=lambda item: (-(item['entrada'] + item['salida']), item['concepto']),
    )
    return {
        'encontrado': True,
        'sesion': _sesion_payload(sesion),
        'estado_diferencia': _estado_diferencia(diferencia),
        'diferencia': diferencia,
        'monto_declarado': _money(sesion.monto_final_declarado),
        'monto_sistema': _money(sesion.monto_final_sistema),
        'principales_componentes': conceptos[:8],
        'lectura': _lectura_diferencia(diferencia),
    }


def _lectura_diferencia(diferencia: float) -> str:
    if diferencia > 0:
        return 'El cierre tuvo sobrante: se declaro mas efectivo que el esperado por el sistema.'
    if diferencia < 0:
        return 'El cierre tuvo faltante: se declaro menos efectivo que el esperado por el sistema.'
    return 'El cierre cuadra: declarado y sistema coinciden.'


def caja_cierre_metodos_pago(args: dict | None = None, usuario=None) -> dict:
    sesion, informe = _informe(args, usuario)
    if not sesion:
        return {'encontrado': False}
    return {
        'encontrado': True,
        'sesion': _sesion_payload(sesion),
        'ventas_por_metodo': _metodos(informe.get('ventas_por_metodo')),
        'creditos_por_metodo': _metodos(informe.get('creditos_por_metodo')),
        'pedidos_por_metodo': _metodos(informe.get('pedidos_por_metodo')),
        'compras_por_metodo': _metodos(informe.get('compras_por_metodo')),
    }


def _metodos(items) -> list[dict]:
    return [
        {
            'id_metodo_pago': item.get('id_metodo_pago'),
            'nombre': item.get('nombre') or '',
            'total': _money(item.get('total')),
            'cantidad': int(item.get('cantidad') or 0),
        }
        for item in (items or [])
        if _money(item.get('total')) or int(item.get('cantidad') or 0)
    ]


def caja_cierre_movimientos(args: dict | None = None, usuario=None) -> dict:
    sesion, informe = _informe(args, usuario)
    if not sesion:
        return {'encontrado': False}
    top_n = normalizar_top_n((args or {}).get('top_n'), default=10)
    detalles = [
        _detalle_payload(item)
        for item in (informe.get('detalles') or [])
        if item.get('tx_tipo') in {'movimiento_caja', 'pago_compra', 'cobro_credito'}
    ]
    detalles.sort(key=lambda item: (item['fecha'] or '', -(item['entrada'] + item['salida'])))
    return {
        'encontrado': True,
        'sesion': _sesion_payload(sesion),
        'top_n': top_n,
        'movimientos': detalles[:top_n],
    }


def caja_cierre_anulaciones(args: dict | None = None, usuario=None) -> dict:
    sesion, informe = _informe(args, usuario)
    if not sesion:
        return {'encontrado': False}
    top_n = normalizar_top_n((args or {}).get('top_n'), default=10)
    anulaciones = [
        _detalle_payload(item)
        for item in (informe.get('detalles') or [])
        if (item.get('concepto') or '').startswith('Anulaci')
    ]
    return {
        'encontrado': True,
        'sesion': _sesion_payload(sesion),
        'cantidad_anulaciones': len(anulaciones),
        'total_anulado': sum(item['salida'] for item in anulaciones),
        'anulaciones': anulaciones[:top_n],
    }


def _concepto_payload(item: dict) -> dict:
    return {
        'concepto': item.get('concepto') or '',
        'entrada': _money(item.get('entrada')),
        'salida': _money(item.get('salida')),
        'key': item.get('key') or '',
        'id_metodo_pago': item.get('metodo_id'),
    }


def _detalle_payload(item: dict) -> dict:
    fecha = item.get('fecha')
    return {
        'fecha': fecha.isoformat() if hasattr(fecha, 'isoformat') else (fecha or None),
        'concepto': item.get('concepto') or '',
        'referencia': item.get('referencia') or '',
        'forma_pago': item.get('forma_pago') or '',
        'entrada': _money(item.get('entrada')),
        'salida': _money(item.get('salida')),
        'detalle': item.get('detalle') or '',
    }
