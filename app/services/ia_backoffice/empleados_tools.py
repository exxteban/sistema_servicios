from sqlalchemy import func

from control_de_empleados.models import Empleado, EmpleadoAusencia, EmpleadoMovimientoSalario, EmpleadoPago
from control_de_empleados.services.aguinaldo import calcular_resumen_aguinaldo
from app import db
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _periodo_nomina(args: dict | None) -> str:
    rango = resolver_rango(args)
    return rango['hasta'].strftime('%Y-%m')


def empleados_resumen(args: dict | None = None, usuario=None) -> dict:
    periodo = _periodo_nomina(args)
    activos = Empleado.query.filter(Empleado.activo.is_(True)).count()
    inactivos = Empleado.query.filter(Empleado.activo.is_(False)).count()
    salarios = (
        db.session.query(func.coalesce(func.sum(Empleado.salario_base), 0))
        .filter(Empleado.activo.is_(True))
        .scalar()
    )
    pagos = _pagos_periodo_query(periodo)
    movimientos = _movimientos_periodo_query(periodo)
    return {
        'periodo': periodo,
        'empleados_activos': int(activos or 0),
        'empleados_inactivos': int(inactivos or 0),
        'salario_base_activo_total': _money(salarios),
        'pagos_periodo': int(pagos.count()),
        'total_pagado_periodo': _money(pagos.with_entities(func.coalesce(func.sum(EmpleadoPago.total_pagado), 0)).scalar()),
        'extras_periodo': _money(movimientos.filter(EmpleadoMovimientoSalario.tipo == 'extra').with_entities(func.coalesce(func.sum(EmpleadoMovimientoSalario.monto), 0)).scalar()),
        'descuentos_periodo': _money(movimientos.filter(EmpleadoMovimientoSalario.tipo == 'descuento').with_entities(func.coalesce(func.sum(EmpleadoMovimientoSalario.monto), 0)).scalar()),
    }


def _pagos_periodo_query(periodo: str):
    return EmpleadoPago.query.filter(EmpleadoPago.periodo == periodo)


def _movimientos_periodo_query(periodo: str):
    return EmpleadoMovimientoSalario.query.filter(EmpleadoMovimientoSalario.periodo == periodo)


def empleados_ausencias_periodo(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    base = (
        EmpleadoAusencia.query
        .join(Empleado, Empleado.id_empleado == EmpleadoAusencia.id_empleado)
        .filter(
            EmpleadoAusencia.fecha_desde <= rango['hasta'],
            EmpleadoAusencia.fecha_hasta >= rango['desde'],
        )
    )
    por_tipo = _agrupar_ausencias(base, EmpleadoAusencia.tipo)
    por_estado = _agrupar_ausencias(base, EmpleadoAusencia.estado)
    empleados = (
        base.with_entities(
            Empleado.id_empleado,
            Empleado.nombre_completo,
            func.count(EmpleadoAusencia.id_ausencia).label('cantidad'),
        )
        .group_by(Empleado.id_empleado, Empleado.nombre_completo)
        .order_by(func.count(EmpleadoAusencia.id_ausencia).desc(), Empleado.nombre_completo.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'total_ausencias': int(base.count()),
        'por_tipo': por_tipo,
        'por_estado': por_estado,
        'empleados_con_mas_ausencias': [
            {'id_empleado': row.id_empleado, 'nombre': row.nombre_completo, 'cantidad': int(row.cantidad or 0)}
            for row in empleados
        ],
    }


def _agrupar_ausencias(query, columna) -> list[dict]:
    filas = (
        query.with_entities(columna.label('clave'), func.count(EmpleadoAusencia.id_ausencia).label('cantidad'))
        .group_by(columna)
        .order_by(func.count(EmpleadoAusencia.id_ausencia).desc(), columna.asc())
        .all()
    )
    return [{'clave': row.clave or '', 'cantidad': int(row.cantidad or 0)} for row in filas]


def empleados_pagos_periodo(args: dict | None = None, usuario=None) -> dict:
    periodo = _periodo_nomina(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    pagos = _pagos_periodo_query(periodo)
    empleados_activos = Empleado.query.filter(Empleado.activo.is_(True)).count()
    empleados_pagados = pagos.with_entities(func.count(func.distinct(EmpleadoPago.id_empleado))).scalar()
    filas = (
        pagos.join(Empleado, Empleado.id_empleado == EmpleadoPago.id_empleado)
        .with_entities(
            EmpleadoPago.id_pago,
            EmpleadoPago.id_empleado,
            Empleado.nombre_completo,
            EmpleadoPago.salario_base,
            EmpleadoPago.total_extras,
            EmpleadoPago.total_descuentos,
            EmpleadoPago.total_pagado,
            EmpleadoPago.fecha_pago,
        )
        .order_by(EmpleadoPago.total_pagado.desc(), Empleado.nombre_completo.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo': periodo,
        'empleados_activos': int(empleados_activos or 0),
        'empleados_pagados': int(empleados_pagados or 0),
        'empleados_pendientes_estimados': max(int(empleados_activos or 0) - int(empleados_pagados or 0), 0),
        'total_pagado': _money(pagos.with_entities(func.coalesce(func.sum(EmpleadoPago.total_pagado), 0)).scalar()),
        'pagos': [_pago_payload(row) for row in filas],
    }


def _pago_payload(row) -> dict:
    return {
        'id_pago': row.id_pago,
        'id_empleado': row.id_empleado,
        'empleado': row.nombre_completo,
        'salario_base': _money(row.salario_base),
        'extras': _money(row.total_extras),
        'descuentos': _money(row.total_descuentos),
        'total_pagado': _money(row.total_pagado),
        'fecha_pago': row.fecha_pago.isoformat() if row.fecha_pago else None,
    }


def empleados_aguinaldo_resumen(args: dict | None = None, usuario=None) -> dict:
    periodo = _periodo_nomina(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    empleados = Empleado.query.filter(Empleado.activo.is_(True)).order_by(Empleado.nombre_completo.asc()).all()
    calculos = []
    total_acumulado = 0.0
    total_proyectado = 0.0
    for empleado in empleados:
        resumen = calcular_resumen_aguinaldo(empleado, periodo)
        acumulado = _money(resumen.get('aguinaldo_acumulado'))
        proyectado = _money(resumen.get('aguinaldo_proyectado'))
        total_acumulado += acumulado
        total_proyectado += proyectado
        calculos.append({
            'id_empleado': empleado.id_empleado,
            'empleado': empleado.nombre_completo,
            'aguinaldo_acumulado': acumulado,
            'aguinaldo_proyectado': proyectado,
            'remuneracion_acumulada': _money(resumen.get('remuneracion_acumulada')),
            'remuneracion_proyectada': _money(resumen.get('remuneracion_proyectada')),
        })
    calculos.sort(key=lambda item: (-item['aguinaldo_proyectado'], item['empleado']))
    return {
        'periodo': periodo,
        'empleados_activos': len(empleados),
        'aguinaldo_acumulado_total': round(total_acumulado, 2),
        'aguinaldo_proyectado_total': round(total_proyectado, 2),
        'top_n': top_n,
        'empleados': calculos[:top_n],
        'metodo_calculo': 'Usa el calculador existente de aguinaldo con pagos y movimientos remunerativos.',
    }
