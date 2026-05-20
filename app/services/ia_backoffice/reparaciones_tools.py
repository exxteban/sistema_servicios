from sqlalchemy import case, func

from app import db
from app.models import Cliente, Reparacion, Usuario
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates


ESTADOS_REPARACION_CERRADOS = {'entregado', 'cancelado', 'antiguos'}


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _base_periodo(args: dict | None):
    rango = resolver_rango(args)
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    return rango, Reparacion.query.filter(Reparacion.fecha_ingreso >= inicio_utc, Reparacion.fecha_ingreso < fin_utc)


def reparaciones_resumen(args: dict | None = None, usuario=None) -> dict:
    rango, base = _base_periodo(args)
    por_estado = _agrupar(base, Reparacion.estado)
    abiertas = Reparacion.query.filter(~Reparacion.estado.in_(tuple(ESTADOS_REPARACION_CERRADOS))).count()
    listas = Reparacion.query.filter(Reparacion.estado == 'listo').count()
    total_estimado = base.with_entities(func.coalesce(func.sum(Reparacion.costo_estimado), 0)).scalar()
    total_final = base.with_entities(func.coalesce(func.sum(Reparacion.costo_final), 0)).scalar()
    return {
        'periodo_label': rango['periodo_label'],
        'total_ingresadas': int(base.count()),
        'abiertas_actuales': int(abiertas or 0),
        'listas_para_entrega': int(listas or 0),
        'por_estado': por_estado,
        'costo_estimado_periodo': _money(total_estimado),
        'costo_final_periodo': _money(total_final),
    }


def _agrupar(query, columna) -> list[dict]:
    filas = (
        query.with_entities(columna.label('clave'), func.count(Reparacion.id_reparacion).label('cantidad'))
        .group_by(columna)
        .order_by(func.count(Reparacion.id_reparacion).desc(), columna.asc())
        .all()
    )
    return [{'clave': row.clave or '', 'cantidad': int(row.cantidad or 0)} for row in filas]


def reparaciones_atrasadas(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    referencia = rango['hasta']
    filas = (
        Reparacion.query
        .join(Cliente, Cliente.id_cliente == Reparacion.cliente_id)
        .outerjoin(Usuario, Usuario.id_usuario == Reparacion.id_usuario_tecnico)
        .filter(
            ~Reparacion.estado.in_(tuple(ESTADOS_REPARACION_CERRADOS)),
            Reparacion.fecha_estimada.isnot(None),
            func.date(Reparacion.fecha_estimada) < referencia,
        )
        .with_entities(
            Reparacion.id_reparacion,
            Cliente.nombre.label('cliente'),
            Reparacion.tipo_equipo,
            Reparacion.marca_modelo,
            Reparacion.estado,
            Reparacion.prioridad,
            Reparacion.fecha_ingreso,
            Reparacion.fecha_estimada,
            Usuario.nombre_completo.label('tecnico'),
        )
        .order_by(Reparacion.fecha_estimada.asc(), Reparacion.id_reparacion.asc())
        .limit(top_n)
        .all()
    )
    return {
        'fecha_referencia': referencia.isoformat(),
        'top_n': top_n,
        'reparaciones': [_reparacion_atrasada_payload(row, referencia) for row in filas],
    }


def _reparacion_atrasada_payload(row, referencia) -> dict:
    fecha_estimada = row.fecha_estimada.date() if row.fecha_estimada else None
    dias_atraso = (referencia - fecha_estimada).days if fecha_estimada else 0
    return {
        'id_reparacion': row.id_reparacion,
        'cliente': row.cliente,
        'equipo': f'{row.tipo_equipo} {row.marca_modelo}'.strip(),
        'estado': row.estado or '',
        'prioridad': row.prioridad or 'normal',
        'tecnico': row.tecnico or 'Sin tecnico',
        'fecha_ingreso': row.fecha_ingreso.isoformat() if row.fecha_ingreso else None,
        'fecha_estimada': row.fecha_estimada.isoformat() if row.fecha_estimada else None,
        'dias_atraso': max(dias_atraso, 0),
    }


def reparaciones_por_tecnico(args: dict | None = None, usuario=None) -> dict:
    rango, base = _base_periodo(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    filas = (
        base.outerjoin(Usuario, Usuario.id_usuario == Reparacion.id_usuario_tecnico)
        .with_entities(
            Reparacion.id_usuario_tecnico,
            Usuario.nombre_completo.label('tecnico'),
            func.count(Reparacion.id_reparacion).label('cantidad'),
            func.sum(case((~Reparacion.estado.in_(tuple(ESTADOS_REPARACION_CERRADOS)), 1), else_=0)).label('abiertas'),
            func.sum(case((Reparacion.estado == 'listo', 1), else_=0)).label('listas'),
            func.coalesce(func.sum(Reparacion.costo_final), 0).label('total_final'),
        )
        .group_by(Reparacion.id_usuario_tecnico, Usuario.nombre_completo)
        .order_by(func.count(Reparacion.id_reparacion).desc(), Usuario.nombre_completo.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'tecnicos': [
            {
                'id_usuario_tecnico': row.id_usuario_tecnico,
                'tecnico': row.tecnico or 'Sin tecnico',
                'cantidad': int(row.cantidad or 0),
                'abiertas': int(row.abiertas or 0),
                'listas': int(row.listas or 0),
                'costo_final_total': _money(row.total_final),
            }
            for row in filas
        ],
    }


def reparaciones_fallas_frecuentes(args: dict | None = None, usuario=None) -> dict:
    rango, base = _base_periodo(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    filas = (
        base.with_entities(
            Reparacion.falla_reportada,
            func.count(Reparacion.id_reparacion).label('cantidad'),
        )
        .filter(Reparacion.falla_reportada.isnot(None))
        .group_by(Reparacion.falla_reportada)
        .order_by(func.count(Reparacion.id_reparacion).desc(), Reparacion.falla_reportada.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'fallas': [
            {
                'falla': (row.falla_reportada or '').strip(),
                'cantidad': int(row.cantidad or 0),
            }
            for row in filas
        ],
    }
