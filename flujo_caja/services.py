from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask_login import current_user
from sqlalchemy import exc as sa_exc

from app import db
from flujo_caja import CATEGORIAS_FLUJO_CAJA, ESTADOS_FLUJO_CAJA, TIPOS_FLUJO_CAJA
from flujo_caja.models import FlujoCajaMovimiento, FlujoCajaPlantilla, FlujoCajaSemana


DIAS_SEMANA = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo']


def _usuario_actual():
    try:
        getter = getattr(current_user, '_get_current_object', None)
        return getter() if callable(getter) else current_user
    except Exception:
        return None


def cliente_scope_actual() -> int | None:
    # Este modulo opera de forma global por base de datos (instancia unica).
    return 0


def aplicar_scope_cliente(query, model):
    del model
    return query


def _parse_int(raw_value, default: int = 0) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _semanas_por_inicio(fecha_inicio: date) -> list[FlujoCajaSemana]:
    return aplicar_scope_cliente(FlujoCajaSemana.query, FlujoCajaSemana).filter(
        FlujoCajaSemana.fecha_inicio == fecha_inicio,
    ).order_by(FlujoCajaSemana.id_flujo_semana.asc()).all()


def _consolidar_semanas_duplicadas(semanas: list[FlujoCajaSemana]) -> FlujoCajaSemana:
    principal = semanas[0]
    if len(semanas) == 1:
        return principal

    for duplicada in semanas[1:]:
        if (not principal.notas) and duplicada.notas:
            principal.notas = duplicada.notas
        if (not principal.nombre) and duplicada.nombre:
            principal.nombre = duplicada.nombre
        if principal.saldo_inicial_decimal() == Decimal('0.00') and duplicada.saldo_inicial_decimal() != Decimal('0.00'):
            principal.saldo_inicial_estimado = duplicada.saldo_inicial_estimado
        if principal.estado != 'cerrada' and duplicada.estado == 'cerrada':
            principal.estado = 'cerrada'
        aplicar_scope_cliente(FlujoCajaMovimiento.query, FlujoCajaMovimiento).filter(
            FlujoCajaMovimiento.id_flujo_semana == duplicada.id_flujo_semana,
        ).update({FlujoCajaMovimiento.id_flujo_semana: principal.id_flujo_semana}, synchronize_session=False)
        db.session.delete(duplicada)

    db.session.flush()
    return principal


def parse_decimal(raw_value: str | None, default: Decimal | None = None) -> Decimal | None:
    """Convierte un string de monto a Decimal.

    Reglas de separadores (moneda paraguaya: enteros, sin decimales reales):
    - "1.000.000"  → 1000000  (puntos como separador de miles)
    - "1,000,000"  → 1000000  (comas como separador de miles)
    - "1000000"    → 1000000  (sin separadores)
    - "1500.50"    → 1500.50  (punto decimal — raro en PYG pero se acepta)
    - "1500,50"    → 1500.50  (coma decimal — raro en PYG pero se acepta)

    Heurística: si hay más de un separador del mismo tipo, o si el separador
    aparece en grupos de 3 dígitos, se trata como separador de miles.
    Si hay exactamente un separador con 1 o 2 dígitos después, se trata como decimal.
    """
    texto = (raw_value or '').strip().replace(' ', '')
    if not texto:
        return default

    tiene_punto = '.' in texto
    tiene_coma = ',' in texto

    if tiene_punto and tiene_coma:
        # Ambos presentes: el último es el decimal, el otro es miles.
        if texto.rfind(',') > texto.rfind('.'):
            # Formato europeo: 1.000,50
            texto = texto.replace('.', '').replace(',', '.')
        else:
            # Formato anglosajón: 1,000.50
            texto = texto.replace(',', '')
    elif tiene_punto:
        # Solo puntos: puede ser miles ("1.000.000") o decimal ("1500.50").
        partes = texto.split('.')
        # Si hay más de un punto, o el último grupo tiene exactamente 3 dígitos → miles.
        if len(partes) > 2 or (len(partes) == 2 and len(partes[-1]) == 3 and partes[-1].isdigit()):
            texto = texto.replace('.', '')
        # Si el último grupo tiene 1 o 2 dígitos → decimal (ej: "1500.50").
        # En ese caso no se modifica el texto.
    elif tiene_coma:
        # Solo comas: misma lógica que puntos pero con coma.
        partes = texto.split(',')
        if len(partes) > 2 or (len(partes) == 2 and len(partes[-1]) == 3 and partes[-1].isdigit()):
            texto = texto.replace(',', '')
        else:
            texto = texto.replace(',', '.')

    try:
        return Decimal(texto).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return default


def parse_fecha(raw_value: str | None) -> date | None:
    texto = (raw_value or '').strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def inicio_semana(value: date | None = None) -> date:
    referencia = value or date.today()
    return referencia - timedelta(days=referencia.weekday())


def rango_semana(raw_value: str | None = None) -> tuple[date, date]:
    parsed = parse_fecha(raw_value)
    inicio = inicio_semana(parsed)
    return inicio, inicio + timedelta(days=6)


def obtener_o_crear_semana(fecha_inicio: date, *, saldo_inicial: Decimal | None = None) -> FlujoCajaSemana:
    cliente_id = cliente_scope_actual()
    semanas = _semanas_por_inicio(fecha_inicio)
    if semanas:
        semana = _consolidar_semanas_duplicadas(semanas)
        if saldo_inicial is not None:
            semana.saldo_inicial_estimado = saldo_inicial
        return semana

    semana = FlujoCajaSemana(
        cliente_id=cliente_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_inicio + timedelta(days=6),
        nombre=f'Semana {fecha_inicio.strftime("%d/%m/%Y")}',
        saldo_inicial_estimado=saldo_inicial or Decimal('0.00'),
    )
    db.session.add(semana)
    try:
        db.session.flush()
    except sa_exc.IntegrityError:
        # Otro request creo la semana concurrentemente; revertimos y reusamos la existente.
        db.session.rollback()
        semanas = _semanas_por_inicio(fecha_inicio)
        if not semanas:
            raise
        semana = _consolidar_semanas_duplicadas(semanas)
        if saldo_inicial is not None:
            semana.saldo_inicial_estimado = saldo_inicial
    return semana


def obtener_semana_actual(raw_semana: str | None = None) -> FlujoCajaSemana:
    fecha_inicio, _fecha_fin = rango_semana(raw_semana)
    semanas = _semanas_por_inicio(fecha_inicio)
    if semanas:
        return _consolidar_semanas_duplicadas(semanas)

    # La semana no existe aun. La dejamos transitoria en la sesion para que la
    # relacion lazy='dynamic' pueda consultar movimientos sin romper el render.
    semana = FlujoCajaSemana(
        cliente_id=cliente_scope_actual(),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_inicio + timedelta(days=6),
        nombre=f'Semana {fecha_inicio.strftime("%d/%m/%Y")}',
        saldo_inicial_estimado=Decimal('0.00'),
    )
    db.session.add(semana)
    # flush asigna el id sin hacer commit; si el request termina sin commit
    # (GET normal) SQLAlchemy hace rollback automatico y la semana no persiste.
    try:
        db.session.flush()
    except sa_exc.IntegrityError:
        db.session.rollback()
        semanas = _semanas_por_inicio(fecha_inicio)
        if not semanas:
            raise
        semana = _consolidar_semanas_duplicadas(semanas)
    return semana


def obtener_movimiento_o_404(id_movimiento: int) -> FlujoCajaMovimiento:
    return aplicar_scope_cliente(FlujoCajaMovimiento.query, FlujoCajaMovimiento).filter(
        FlujoCajaMovimiento.id_flujo_movimiento == id_movimiento,
    ).first_or_404()


def obtener_plantilla_o_404(id_plantilla: int, *, solo_activas: bool = False) -> FlujoCajaPlantilla:
    query = aplicar_scope_cliente(FlujoCajaPlantilla.query, FlujoCajaPlantilla).filter(
        FlujoCajaPlantilla.id_flujo_plantilla == id_plantilla,
    )
    if solo_activas:
        query = query.filter(FlujoCajaPlantilla.activa.is_(True))
    return query.first_or_404()


def crear_movimiento(semana: FlujoCajaSemana, payload: dict) -> FlujoCajaMovimiento:
    tipo = (payload.get('tipo') or '').strip().lower()
    estado = (payload.get('estado') or 'estimado').strip().lower()
    categoria = (payload.get('categoria') or 'otros').strip().lower() or 'otros'
    fecha = payload.get('fecha') or semana.fecha_inicio
    movimiento = FlujoCajaMovimiento(
        cliente_id=cliente_scope_actual(),
        id_flujo_semana=semana.id_flujo_semana,
        fecha=max(semana.fecha_inicio, min(fecha, semana.fecha_fin)),
        tipo=tipo if tipo in {'ingreso', 'egreso'} else 'egreso',
        categoria=categoria,
        concepto=(payload.get('concepto') or '').strip()[:160],
        monto_estimado=payload.get('monto_estimado') or Decimal('0.00'),
        monto_real=payload.get('monto_real'),
        estado=estado if estado in dict(ESTADOS_FLUJO_CAJA) else 'estimado',
        origen=(payload.get('origen') or 'manual').strip()[:40] or 'manual',
        notas=(payload.get('notas') or '').strip() or None,
        id_usuario=getattr(current_user, 'id_usuario', None),
    )
    db.session.add(movimiento)
    return movimiento


def crear_plantilla(payload: dict) -> FlujoCajaPlantilla:
    dia_semana = _parse_int(payload.get('dia_semana'), 0)
    plantilla = FlujoCajaPlantilla(
        cliente_id=cliente_scope_actual(),
        nombre=(payload.get('nombre') or '').strip()[:120],
        tipo=(payload.get('tipo') or 'egreso').strip().lower(),
        categoria=(payload.get('categoria') or 'otros').strip().lower() or 'otros',
        concepto=(payload.get('concepto') or '').strip()[:160],
        monto_estimado=payload.get('monto_estimado') or Decimal('0.00'),
        dia_semana=max(0, min(dia_semana, 6)),
        activa=True,
    )
    if plantilla.tipo not in {'ingreso', 'egreso'}:
        plantilla.tipo = 'egreso'
    db.session.add(plantilla)
    return plantilla


def aplicar_plantilla(semana: FlujoCajaSemana, plantilla: FlujoCajaPlantilla) -> FlujoCajaMovimiento:
    return crear_movimiento(
        semana,
        {
            'fecha': semana.fecha_inicio + timedelta(days=int(plantilla.dia_semana or 0)),
            'tipo': plantilla.tipo,
            'categoria': plantilla.categoria,
            'concepto': plantilla.concepto,
            'monto_estimado': plantilla.monto_estimado_decimal(),
            'estado': 'estimado',
            'origen': f'plantilla:{plantilla.id_flujo_plantilla}',
        },
    )


def construir_contexto(raw_semana: str | None = None) -> dict:
    semana = obtener_semana_actual(raw_semana)
    movimientos = semana.movimientos.all()
    dias = _construir_dias(semana, movimientos)
    resumen = _calcular_resumen(semana, movimientos, dias)
    return {
        'semana': semana,
        'semana_anterior': semana.fecha_inicio - timedelta(days=7),
        'semana_siguiente': semana.fecha_inicio + timedelta(days=7),
        'movimientos': movimientos,
        'dias': dias,
        'resumen': resumen,
        'historial': _construir_historial(semana.fecha_inicio),
        'calendario': _construir_calendario(semana.fecha_inicio),
        'plantillas': _plantillas_activas(),
        'categorias': [{'valor': k, 'label': v} for k, v in CATEGORIAS_FLUJO_CAJA],
        'estados': [{'valor': k, 'label': v} for k, v in ESTADOS_FLUJO_CAJA],
        'tipos': [{'valor': k, 'label': v} for k, v in TIPOS_FLUJO_CAJA],
        'dias_semana': [{'valor': idx, 'label': label} for idx, label in enumerate(DIAS_SEMANA)],
    }


def _construir_dias(semana: FlujoCajaSemana, movimientos: list[FlujoCajaMovimiento]) -> list[dict]:
    saldo = semana.saldo_inicial_decimal()
    dias = []
    for idx in range(7):
        fecha = semana.fecha_inicio + timedelta(days=idx)
        items = [mov for mov in movimientos if mov.fecha == fecha and mov.estado != 'cancelado']
        ingresos = sum((mov.monto_operativo_decimal() for mov in items if mov.tipo == 'ingreso'), Decimal('0.00'))
        egresos = sum((mov.monto_operativo_decimal() for mov in items if mov.tipo == 'egreso'), Decimal('0.00'))
        estimado_realizados = sum((
            mov.monto_estimado_decimal() if mov.tipo == 'ingreso' else -mov.monto_estimado_decimal()
            for mov in items if mov.estado == 'realizado'
        ), Decimal('0.00'))
        real_realizados = sum((
            mov.monto_operativo_decimal() if mov.tipo == 'ingreso' else -mov.monto_operativo_decimal()
            for mov in items if mov.estado == 'realizado'
        ), Decimal('0.00'))
        saldo += ingresos - egresos
        dias.append({
            'fecha': fecha,
            'label': DIAS_SEMANA[idx],
            'ingresos': ingresos,
            'egresos': egresos,
            'neto': ingresos - egresos,
            'diferencia_real_estimado': real_realizados - estimado_realizados,
            'saldo': saldo,
            'items': items,
            'riesgo': saldo < 0,
        })
    return dias


def _calcular_resumen(semana: FlujoCajaSemana, movimientos: list[FlujoCajaMovimiento], dias: list[dict]) -> dict:
    activos = [mov for mov in movimientos if mov.estado != 'cancelado']

    # FIX #1: usar monto_operativo en todos los totales para que los KPIs del
    # panel superior sean coherentes con el saldo acumulado diario (que también
    # usa monto_operativo). De esta forma saldo_inicial + resultado == saldo_final.
    ingresos = sum((mov.monto_operativo_decimal() for mov in activos if mov.tipo == 'ingreso'), Decimal('0.00'))
    egresos = sum((mov.monto_operativo_decimal() for mov in activos if mov.tipo == 'egreso'), Decimal('0.00'))

    # Totales estimados puros: útiles para el tab comparativo.
    ingresos_estimados = sum((mov.monto_estimado_decimal() for mov in activos if mov.tipo == 'ingreso'), Decimal('0.00'))
    egresos_estimados = sum((mov.monto_estimado_decimal() for mov in activos if mov.tipo == 'egreso'), Decimal('0.00'))

    ingresos_real = sum((mov.monto_operativo_decimal() for mov in activos if mov.tipo == 'ingreso' and mov.estado == 'realizado'), Decimal('0.00'))
    egresos_real = sum((mov.monto_operativo_decimal() for mov in activos if mov.tipo == 'egreso' and mov.estado == 'realizado'), Decimal('0.00'))
    ingresos_estimados_realizados = sum((
        mov.monto_estimado_decimal() for mov in activos if mov.tipo == 'ingreso' and mov.estado == 'realizado'
    ), Decimal('0.00'))
    egresos_estimados_realizados = sum((
        mov.monto_estimado_decimal() for mov in activos if mov.tipo == 'egreso' and mov.estado == 'realizado'
    ), Decimal('0.00'))

    primer_riesgo = next((dia for dia in dias if dia['riesgo']), None)
    resultado = ingresos - egresos
    faltante = abs(primer_riesgo['saldo']) if primer_riesgo else Decimal('0.00')
    resultado_realizado = ingresos_real - egresos_real
    resultado_estimado_realizado = ingresos_estimados_realizados - egresos_estimados_realizados

    if primer_riesgo:
        estado, tono = 'rojo', 'danger'
        mensaje = f'El {primer_riesgo["label"]} la caja queda en -Gs. {_fmt(faltante)}.'
    elif resultado < 0:
        estado, tono = 'amarillo', 'warning'
        mensaje = f'La semana cierra con saldo negativo por Gs. {_fmt(abs(resultado))}.'
    else:
        estado, tono = 'verde', 'success'
        mensaje = 'Con los movimientos cargados, la semana queda cubierta.'

    recomendacion = _recomendacion(
        estado,
        faltante or abs(resultado),
        primer_riesgo,
        dias[-1]['saldo'] if dias else semana.saldo_inicial_decimal(),
    )
    return {
        'total_ingresos': ingresos,
        'total_egresos': egresos,
        'total_ingresos_estimados': ingresos_estimados,
        'total_egresos_estimados': egresos_estimados,
        'resultado': resultado,
        'saldo_inicial': semana.saldo_inicial_decimal(),
        'saldo_final': dias[-1]['saldo'] if dias else semana.saldo_inicial_decimal(),
        'ingresos_realizados': ingresos_real,
        'egresos_realizados': egresos_real,
        'ingresos_estimados_realizados': ingresos_estimados_realizados,
        'egresos_estimados_realizados': egresos_estimados_realizados,
        'resultado_realizado': resultado_realizado,
        'resultado_estimado_realizado': resultado_estimado_realizado,
        'diferencia_real_vs_estimado': resultado_realizado - resultado_estimado_realizado,
        'primer_riesgo': primer_riesgo,
        'semaforo_estado': estado,
        'semaforo_tono': tono,
        'semaforo_mensaje': mensaje,
        'recomendacion': recomendacion,
        'cantidad_movimientos': len(activos),
    }


def _recomendacion(estado: str, monto: Decimal, primer_riesgo: dict | None, saldo_final: Decimal) -> str:
    if estado == 'verde':
        return 'Segui actualizando cobros y pagos para ver la caja real de cada dia.'
    if primer_riesgo:
        if saldo_final >= 0:
            return (
                'La semana termina con saldo positivo, pero ese ingreso entra despues. '
                f'Necesitas cobrar o mover pagos por Gs. {_fmt(monto)} antes de ese dia.'
            )
        return f'Necesitas cobrar o mover pagos por Gs. {_fmt(monto)} antes de ese dia.'
    return f'Necesitas sumar ingresos o reprogramar pagos por Gs. {_fmt(monto)} antes del cierre semanal.'


def _construir_historial(fecha_actual: date) -> list[dict]:
    semanas = aplicar_scope_cliente(FlujoCajaSemana.query, FlujoCajaSemana).filter(
        FlujoCajaSemana.fecha_inicio < fecha_actual,
    ).order_by(FlujoCajaSemana.fecha_inicio.desc()).limit(10).all()
    return _resumenes_semanas_bulk(semanas)


def _construir_calendario(fecha_actual: date) -> list[dict]:
    inicio = fecha_actual - timedelta(days=14)
    finales = fecha_actual + timedelta(days=28)
    semanas = aplicar_scope_cliente(FlujoCajaSemana.query, FlujoCajaSemana).filter(
        FlujoCajaSemana.fecha_inicio >= inicio,
        FlujoCajaSemana.fecha_inicio <= finales,
    ).order_by(FlujoCajaSemana.fecha_inicio.asc()).all()
    return _resumenes_semanas_bulk(semanas)


def _resumenes_semanas_bulk(semanas: list[FlujoCajaSemana]) -> list[dict]:
    """Carga todos los movimientos de las semanas dadas en una sola query
    para evitar el problema N+1 de llamar semana.movimientos.all() por cada semana.
    """
    if not semanas:
        return []
    ids = [s.id_flujo_semana for s in semanas]
    # FIX #5: aplicar scope de cliente en la query de movimientos para garantizar
    # aislamiento multi-tenant incluso si los ids de semana fueran correctos.
    todos_movimientos = (
        aplicar_scope_cliente(FlujoCajaMovimiento.query, FlujoCajaMovimiento)
        .filter(FlujoCajaMovimiento.id_flujo_semana.in_(ids))
        .order_by(FlujoCajaMovimiento.fecha.asc(), FlujoCajaMovimiento.id_flujo_movimiento.asc())
        .all()
    )
    # Agrupar movimientos por semana
    movs_por_semana: dict[int, list[FlujoCajaMovimiento]] = {s.id_flujo_semana: [] for s in semanas}
    for mov in todos_movimientos:
        movs_por_semana[mov.id_flujo_semana].append(mov)

    resultado = []
    for semana in semanas:
        movimientos = movs_por_semana.get(semana.id_flujo_semana, [])
        dias = _construir_dias(semana, movimientos)
        resumen = _calcular_resumen(semana, movimientos, dias)
        resultado.append({'semana': semana, 'resumen': resumen})
    return resultado


def _plantillas_activas() -> list[FlujoCajaPlantilla]:
    return aplicar_scope_cliente(FlujoCajaPlantilla.query, FlujoCajaPlantilla).filter(
        FlujoCajaPlantilla.activa.is_(True),
    ).order_by(FlujoCajaPlantilla.dia_semana.asc(), FlujoCajaPlantilla.nombre.asc()).all()


def _fmt(value: Decimal) -> str:
    return f'{float(value or 0):,.0f}'.replace(',', '.')
