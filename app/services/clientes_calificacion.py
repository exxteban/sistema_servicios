from datetime import datetime, timedelta

from sqlalchemy import case

from app import db
from app.models import (
    Cliente,
    ClienteCalificacionHistorial,
    ClienteCalificacionRegla,
    Configuracion,
    Reparacion,
    Venta,
)


CONFIG_AUTO_ACTIVA = 'clientes_calificacion_auto_activa'
CONFIG_AUTO_INTERVALO_HORAS = 'clientes_calificacion_auto_intervalo_horas'
CONFIG_AUTO_ULTIMA_EJECUCION = 'clientes_calificacion_auto_ultima_ejecucion'

METRICAS = {
    'compras_cantidad': 'Cantidad de compras',
    'compras_monto': 'Monto total en compras',
    'reparaciones_cantidad': 'Cantidad de reparaciones',
    'reparaciones_monto': 'Monto total en reparaciones',
    'total_movimientos': 'Compras + reparaciones',
    'gasto_total': 'Gasto total general',
    'dias_desde_ultima_compra': 'Dias desde ultima compra',
    'dias_desde_ultima_reparacion': 'Dias desde ultima reparacion',
    'antiguedad_dias': 'Antiguedad del cliente',
    'saldo_pendiente': 'Saldo pendiente',
}

METRICAS_CON_PERIODO = {
    'compras_cantidad',
    'compras_monto',
    'reparaciones_cantidad',
    'reparaciones_monto',
    'total_movimientos',
    'gasto_total',
}

OPERADORES = {
    '>=': 'Mayor o igual',
    '>': 'Mayor que',
    '<=': 'Menor o igual',
    '<': 'Menor que',
    '==': 'Igual',
    '!=': 'Distinto',
}

ACCIONES = {
    'asignar': 'Asignar estrellas',
    'sumar': 'Sumar estrellas',
    'restar': 'Restar estrellas',
    'maximo': 'Limitar maximo',
    'minimo': 'Exigir minimo',
}


def estrellas_seguras(valor, default=3):
    try:
        estrellas = int(valor or default)
    except (TypeError, ValueError):
        estrellas = default
    return max(1, min(5, estrellas))


def reglas_activas():
    return ClienteCalificacionRegla.query.filter_by(activa=True).order_by(
        ClienteCalificacionRegla.prioridad.asc(),
        ClienteCalificacionRegla.id_regla.asc(),
    ).all()


def config_auto():
    return {
        'activa': Configuracion.obtener_bool(CONFIG_AUTO_ACTIVA, default=True),
        'intervalo_horas': max(
            1,
            Configuracion.obtener_int(CONFIG_AUTO_INTERVALO_HORAS, default=24),
        ),
        'ultima_ejecucion': Configuracion.obtener(CONFIG_AUTO_ULTIMA_EJECUCION, ''),
    }


def guardar_config_auto(activa, intervalo_horas):
    Configuracion.establecer_bool(
        CONFIG_AUTO_ACTIVA,
        activa,
        'Activa la recalificacion automatica de clientes',
    )
    Configuracion.establecer(
        CONFIG_AUTO_INTERVALO_HORAS,
        str(max(1, int(intervalo_horas or 24))),
        'Horas minimas entre recalificaciones automaticas',
    )


def ejecutar_auto_si_corresponde(id_usuario=None, ahora=None):
    cfg = config_auto()
    if not cfg['activa']:
        return {'ejecutado': False, 'motivo': 'Configuracion automatica inactiva'}

    ahora = ahora or datetime.utcnow()
    ultima = _parse_fecha_iso(cfg.get('ultima_ejecucion'))
    if ultima and ahora - ultima < timedelta(hours=cfg['intervalo_horas']):
        return {'ejecutado': False, 'motivo': 'Aun no vence el intervalo'}

    resultado = aplicar_reglas_a_clientes(id_usuario=id_usuario, ahora=ahora)
    Configuracion.establecer(
        CONFIG_AUTO_ULTIMA_EJECUCION,
        ahora.isoformat(timespec='seconds'),
        'Ultima recalificacion automatica de clientes',
    )
    return {'ejecutado': True, **resultado}


def aplicar_reglas_a_clientes(id_usuario=None, ahora=None):
    reglas = reglas_activas()
    if not reglas:
        return {'evaluados': 0, 'actualizados': 0, 'historial': []}

    ahora = ahora or datetime.utcnow()
    clientes = Cliente.query.filter(
        Cliente.activo.is_(True),
        Cliente.id_cliente != 1,
    ).all()
    cambios = []

    for cliente in clientes:
        resultado = evaluar_cliente(cliente, reglas=reglas, ahora=ahora)
        if not resultado['cambio']:
            continue
        cliente.nivel_estrellas = resultado['estrellas_nuevas']
        historial = ClienteCalificacionHistorial(
            id_cliente=cliente.id_cliente,
            id_regla=resultado['id_regla'],
            id_usuario=id_usuario,
            estrellas_anteriores=resultado['estrellas_anteriores'],
            estrellas_nuevas=resultado['estrellas_nuevas'],
            motivo=resultado['motivo'],
            fecha_cambio=ahora,
        )
        db.session.add(historial)
        cambios.append(historial)

    db.session.commit()
    return {
        'evaluados': len(clientes),
        'actualizados': len(cambios),
        'historial': cambios,
    }


def evaluar_cliente(cliente, reglas=None, ahora=None):
    reglas = reglas if reglas is not None else reglas_activas()
    ahora = ahora or datetime.utcnow()
    inicial = estrellas_seguras(cliente.nivel_estrellas)
    estrellas = inicial
    regla_cambio = None
    motivos = []

    for regla in reglas:
        valor_metrica = calcular_metrica(cliente, regla, ahora=ahora)
        if not cumple_condicion(valor_metrica, regla.operador, float(regla.valor or 0)):
            continue
        if _debe_omitir_por_reaplicacion(cliente, regla, ahora):
            continue
        nuevo = aplicar_accion(estrellas, regla)
        if nuevo == estrellas:
            continue
        estrellas = nuevo
        regla_cambio = regla
        motivos.append(_motivo_regla(regla, valor_metrica))

    return {
        'cambio': estrellas != inicial,
        'id_regla': regla_cambio.id_regla if regla_cambio else None,
        'estrellas_anteriores': inicial,
        'estrellas_nuevas': estrellas,
        'motivo': ' | '.join(motivos[-3:]) if motivos else '',
    }


def calcular_metrica(cliente, regla, ahora=None):
    ahora = ahora or datetime.utcnow()
    metrica = regla.metrica
    inicio = _inicio_periodo(regla, ahora)

    if metrica == 'compras_cantidad':
        return _ventas_query(cliente.id_cliente, inicio).count()
    if metrica == 'compras_monto':
        return float(_ventas_query(cliente.id_cliente, inicio).with_entities(
            db.func.coalesce(db.func.sum(Venta.total), 0)
        ).scalar() or 0)
    if metrica == 'reparaciones_cantidad':
        return _reparaciones_query(cliente.id_cliente, inicio).count()
    if metrica == 'reparaciones_monto':
        return float(_reparaciones_monto(cliente.id_cliente, inicio) or 0)
    if metrica == 'total_movimientos':
        return (
            _ventas_query(cliente.id_cliente, inicio).count()
            + _reparaciones_query(cliente.id_cliente, inicio).count()
        )
    if metrica == 'gasto_total':
        compras = _ventas_query(cliente.id_cliente, inicio).with_entities(
            db.func.coalesce(db.func.sum(Venta.total), 0)
        ).scalar() or 0
        return float(compras) + float(_reparaciones_monto(cliente.id_cliente, inicio) or 0)
    if metrica == 'dias_desde_ultima_compra':
        return _dias_desde(_ultima_fecha_venta(cliente.id_cliente), ahora)
    if metrica == 'dias_desde_ultima_reparacion':
        return _dias_desde(_ultima_fecha_reparacion(cliente.id_cliente), ahora)
    if metrica == 'antiguedad_dias':
        return _dias_desde(cliente.fecha_creacion, ahora, sin_fecha=0)
    if metrica == 'saldo_pendiente':
        return float(cliente.saldo_pendiente or 0)
    return 0


def cumple_condicion(actual, operador, esperado):
    if operador == '>=':
        return actual >= esperado
    if operador == '>':
        return actual > esperado
    if operador == '<=':
        return actual <= esperado
    if operador == '<':
        return actual < esperado
    if operador == '==':
        return actual == esperado
    if operador == '!=':
        return actual != esperado
    return False


def aplicar_accion(estrellas_actuales, regla):
    cantidad = regla.estrellas_seguras
    if regla.accion == 'asignar':
        return cantidad
    if regla.accion == 'sumar':
        return estrellas_seguras(estrellas_actuales + cantidad, default=estrellas_actuales)
    if regla.accion == 'restar':
        return estrellas_seguras(estrellas_actuales - cantidad, default=estrellas_actuales)
    if regla.accion == 'maximo':
        return min(estrellas_actuales, cantidad)
    if regla.accion == 'minimo':
        return max(estrellas_actuales, cantidad)
    return estrellas_actuales


def _ventas_query(id_cliente, inicio=None):
    query = Venta.query.filter_by(id_cliente=id_cliente, estado='completada')
    if inicio:
        query = query.filter(Venta.fecha_venta >= inicio)
    return query


def _reparaciones_query(id_cliente, inicio=None):
    query = Reparacion.query.filter_by(cliente_id=id_cliente)
    if inicio:
        query = query.filter(Reparacion.fecha_ingreso >= inicio)
    return query


def _reparaciones_monto(id_cliente, inicio=None):
    monto_expr = case(
        (Reparacion.costo_final > 0, Reparacion.costo_final),
        else_=Reparacion.costo_estimado,
    )
    return _reparaciones_query(id_cliente, inicio).with_entities(
        db.func.coalesce(db.func.sum(monto_expr), 0)
    ).scalar()


def _ultima_fecha_venta(id_cliente):
    return Venta.query.filter_by(id_cliente=id_cliente, estado='completada').with_entities(
        db.func.max(Venta.fecha_venta)
    ).scalar()


def _ultima_fecha_reparacion(id_cliente):
    return Reparacion.query.filter_by(cliente_id=id_cliente).with_entities(
        db.func.max(Reparacion.fecha_ingreso)
    ).scalar()


def _inicio_periodo(regla, ahora):
    if regla.metrica not in METRICAS_CON_PERIODO:
        return None
    dias = regla.periodo_dias_seguro
    if dias <= 0:
        return None
    return ahora - timedelta(days=dias)


def _dias_desde(fecha, ahora, sin_fecha=9999):
    if not fecha:
        return sin_fecha
    delta = ahora - fecha
    return max(0, int(delta.days))


def _debe_omitir_por_reaplicacion(cliente, regla, ahora):
    dias = regla.reaplicar_cada_dias_seguro
    if dias <= 0:
        return False
    ultimo = ClienteCalificacionHistorial.query.filter_by(
        id_cliente=cliente.id_cliente,
        id_regla=regla.id_regla,
    ).order_by(ClienteCalificacionHistorial.fecha_cambio.desc()).first()
    if not ultimo:
        return False
    return ahora - ultimo.fecha_cambio < timedelta(days=dias)


def _motivo_regla(regla, valor_metrica):
    valor = float(regla.valor or 0)
    valor_txt = f'{valor:,.0f}'.replace(',', '.')
    actual_txt = f'{float(valor_metrica or 0):,.0f}'.replace(',', '.')
    periodo = f' en ultimos {regla.periodo_dias_seguro} dias' if regla.periodo_dias_seguro else ''
    return (
        f'{regla.nombre}: {METRICAS.get(regla.metrica, regla.metrica)}'
        f'{periodo} fue {actual_txt} ({regla.operador} {valor_txt})'
    )


def _parse_fecha_iso(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
