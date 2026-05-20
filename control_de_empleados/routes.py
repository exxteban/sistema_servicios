from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import false

from app import db
from app.models import Cliente, Configuracion
from app.utils.auditoria_utils import registrar_auditoria
from control_de_empleados import (
    CLAVE_EMPRESA_DIRECCION,
    CLAVE_EMPRESA_NOMBRE,
    CLAVE_EMPRESA_RUC,
    CLAVE_LLEGADA_TARDIA_DESCUENTO_DESDE,
    CLAVE_LLEGADA_TARDIA_DESCUENTO_MONTO,
    CLAVE_MODULO_CONTROL_EMPLEADOS,
    DESC_EMPRESA_DIRECCION,
    DESC_EMPRESA_NOMBRE,
    DESC_EMPRESA_RUC,
    DESC_LLEGADA_TARDIA_DESCUENTO_DESDE,
    DESC_LLEGADA_TARDIA_DESCUENTO_MONTO,
)
from control_de_empleados.models import Empleado, EmpleadoAusencia, EmpleadoMovimientoSalario
from control_de_empleados.services.aguinaldo import calcular_resumen_aguinaldo
from control_de_empleados.services.ausencias import (
    ESTADOS_AUSENCIA_CONFIRMADOS,
    construir_panel_ausencias,
    normalizar_filtros_ausencias,
    opciones_estados_ausencia,
    opciones_tipos_ausencia,
)
from control_de_empleados.services.filtros import (
    normalizar_busqueda_empleado,
    normalizar_periodo,
    normalizar_tab,
    resolver_filtros_estado,
)
from control_de_empleados.services.tipos_movimiento import (
    es_tipo_movimiento_negativo,
    etiqueta_tipo_movimiento,
    formatear_cantidad_movimiento,
    opciones_tipos_movimiento,
)

control_empleados_bp = Blueprint(
    'control_empleados',
    __name__,
    template_folder='templates',
)

TIPOS_PAGO = [
    ('mensual', 'Mensual'),
    ('quincenal', 'Quincenal'),
    ('semanal', 'Semanal'),
]

TIPO_AUSENCIA_LLEGADA_TARDIA = 'llegada_tardia'
ESTADOS_LLEGADA_TARDIA_DESCONTABLES = frozenset(ESTADOS_AUSENCIA_CONFIRMADOS)
HISTORIAL_RESUMEN_POR_PAGINA = 10


def _modulo_activo() -> bool:
    return Configuracion.obtener_bool(CLAVE_MODULO_CONTROL_EMPLEADOS, default=False)


def _cliente_scope_actual() -> int | None:
    try:
        cliente_id = int(getattr(current_user, 'id_cliente', 0) or 0)
    except (TypeError, ValueError):
        cliente_id = 0
    if cliente_id > 0:
        return cliente_id
    if current_user.es_admin():
        return None
    cliente_unico = Cliente.query.filter(
        Cliente.activo.is_(True),
        Cliente.id_cliente != 1,
    ).order_by(Cliente.id_cliente.asc()).limit(2).all()
    if len(cliente_unico) == 1:
        return int(cliente_unico[0].id_cliente)
    return None


def _aplicar_scope_cliente(query, model):
    cliente_scope = _cliente_scope_actual()
    if cliente_scope:
        return query.filter(getattr(model, 'cliente_id') == cliente_scope)
    return query if current_user.es_admin() else query.filter(getattr(model, 'cliente_id').is_(None))


def _tiene_permiso_control(permiso: str) -> bool:
    if current_user.es_admin():
        return True
    if current_user.tiene_permiso(permiso):
        return True
    return permiso == 'ver_control_empleados' and current_user.tiene_permiso('gestionar_control_empleados')


def _resolver_denegacion(permiso: str) -> object | None:
    if not _modulo_activo():
        flash('El módulo de control de empleados está desactivado.', 'warning')
        return redirect(url_for('main.dashboard'))
    if _tiene_permiso_control(permiso):
        return None
    flash('No tienes permisos para acceder a control de empleados.', 'danger')
    return redirect(url_for('main.dashboard'))


def _parse_decimal(raw_value: str | None) -> Decimal | None:
    texto = (raw_value or '').strip().replace(' ', '')
    if not texto:
        return None
    if ',' in texto and '.' in texto:
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '').replace(',', '.')
        else:
            texto = texto.replace(',', '')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        valor = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return valor.quantize(Decimal('0.01'))


def _parse_fecha(raw_value: str | None) -> date | None:
    texto = (raw_value or '').strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_entero_no_negativo(raw_value: str | None, default: int) -> int:
    texto = (raw_value or '').strip()
    if not texto:
        return default
    try:
        valor = int(texto)
    except ValueError:
        return default
    return valor if valor >= 0 else default


def _obtener_cliente_scope(empleado: Empleado | None = None) -> int | None:
    if empleado and getattr(empleado, 'cliente_id', None):
        return int(empleado.cliente_id)
    return _cliente_scope_actual()


def _clave_config_control_empleados(clave_base: str, cliente_id: int | None = None) -> str:
    scope = _obtener_cliente_scope() if cliente_id is None else cliente_id
    try:
        scope_int = int(scope or 0)
    except (TypeError, ValueError):
        scope_int = 0
    return f'{clave_base}__cliente_{scope_int}' if scope_int > 0 else clave_base


def _obtener_config_control_empleados(
    clave_base: str,
    default=None,
    cliente_id: int | None = None,
):
    scope = _obtener_cliente_scope() if cliente_id is None else cliente_id
    clave_scoped = _clave_config_control_empleados(clave_base, cliente_id=scope)
    valor = Configuracion.obtener(clave_scoped, None)
    if valor is None and scope:
        valor = Configuracion.obtener(clave_base, default)
    return default if valor is None else valor


def _establecer_config_control_empleados(
    clave_base: str,
    valor,
    descripcion: str | None = None,
    cliente_id: int | None = None,
):
    return Configuracion.establecer(
        _clave_config_control_empleados(clave_base, cliente_id=cliente_id),
        valor,
        descripcion=descripcion,
    )


def _obtener_configuracion_llegada_tardia(cliente_id: int | None = None) -> dict:
    desde = _obtener_config_control_empleados(
        CLAVE_LLEGADA_TARDIA_DESCUENTO_DESDE,
        default='1',
        cliente_id=cliente_id,
    )
    monto = _obtener_config_control_empleados(
        CLAVE_LLEGADA_TARDIA_DESCUENTO_MONTO,
        default='0',
        cliente_id=cliente_id,
    )
    try:
        desde_int = max(int(str(desde).strip() or '1'), 1)
    except (TypeError, ValueError):
        desde_int = 1
    monto_decimal = _parse_decimal(str(monto)) if monto is not None else None
    if monto_decimal is None or monto_decimal < 0:
        monto_decimal = Decimal('0.00')
    return {
        'desde': desde_int,
        'monto': monto_decimal,
    }


def _obtener_configuracion_empresa_rrhh(cliente_id: int | None = None) -> dict:
    return {
        'nombre': _obtener_config_control_empleados(
            CLAVE_EMPRESA_NOMBRE,
            default='',
            cliente_id=cliente_id,
        ),
        'ruc': _obtener_config_control_empleados(
            CLAVE_EMPRESA_RUC,
            default='',
            cliente_id=cliente_id,
        ),
        'direccion': _obtener_config_control_empleados(
            CLAVE_EMPRESA_DIRECCION,
            default='',
            cliente_id=cliente_id,
        ),
    }


def _rango_periodo(periodo: str) -> tuple[date, date]:
    try:
        anio = int(periodo[:4])
        mes = int(periodo[5:7])
        fecha_inicio = date(anio, mes, 1)
    except (TypeError, ValueError):
        hoy = date.today()
        fecha_inicio = date(hoy.year, hoy.month, 1)
    if fecha_inicio.month == 12:
        fecha_fin = date(fecha_inicio.year + 1, 1, 1)
    else:
        fecha_fin = date(fecha_inicio.year, fecha_inicio.month + 1, 1)
    return fecha_inicio, fecha_fin


def _contar_llegadas_tardias_periodo(empleado: Empleado, periodo: str) -> int:
    fecha_inicio, fecha_fin_exclusiva = _rango_periodo(periodo)
    return empleado.ausencias.filter(
        EmpleadoAusencia.tipo == 'llegada_tardia',
        EmpleadoAusencia.estado.in_(tuple(ESTADOS_LLEGADA_TARDIA_DESCONTABLES)),
        EmpleadoAusencia.fecha_desde >= fecha_inicio,
        EmpleadoAusencia.fecha_desde < fecha_fin_exclusiva,
    ).count()


def _calcular_descuento_llegadas_tardias(
    cantidad_llegadas_tardias: int,
    configuracion: dict,
) -> tuple[int, Decimal]:
    desde = max(int(configuracion.get('desde') or 1), 1)
    monto = configuracion.get('monto') or Decimal('0.00')
    if cantidad_llegadas_tardias <= 0 or monto <= 0:
        return 0, Decimal('0.00')
    llegadas_descontadas = max(cantidad_llegadas_tardias - desde + 1, 0)
    descuento = (Decimal(llegadas_descontadas) * monto).quantize(Decimal('0.01'))
    return llegadas_descontadas, descuento


def _cliente_id_para_nuevo_registro(empleado: Empleado | None = None) -> int | None:
    cliente_id = _obtener_cliente_scope(empleado)
    return int(cliente_id) if cliente_id else None


def _fecha_pertenece_a_periodo(fecha: date | None, periodo: str) -> bool:
    return bool(fecha) and fecha.strftime('%Y-%m') == periodo


def _fecha_formulario_periodo(periodo: str) -> str:
    hoy = date.today()
    if hoy.strftime('%Y-%m') == periodo:
        return hoy.isoformat()
    fecha_inicio, _ = _rango_periodo(periodo)
    return fecha_inicio.isoformat()


def _obtener_empleado_o_404(id_empleado: int) -> Empleado:
    return _aplicar_scope_cliente(Empleado.query, Empleado).filter(
        Empleado.id_empleado == id_empleado,
    ).first_or_404()


def _obtener_ausencia_en_edicion(empleado: Empleado, source=None) -> EmpleadoAusencia | None:
    origen = source or request.args
    raw_id = getattr(origen, 'get', lambda *_args, **_kwargs: None)('edit_ausencia')
    try:
        id_ausencia = int(raw_id)
    except (TypeError, ValueError):
        return None
    if id_ausencia <= 0:
        return None
    return empleado.ausencias.filter_by(id_ausencia=id_ausencia).first()


def _sumar_movimientos(movimientos: list[EmpleadoMovimientoSalario]) -> tuple[Decimal, Decimal]:
    extras = Decimal('0.00')
    descuentos = Decimal('0.00')
    for movimiento in movimientos:
        monto = movimiento.monto_decimal()
        if es_tipo_movimiento_negativo(movimiento.tipo, movimiento.cliente_id):
            descuentos += monto
        else:
            extras += monto
    return extras, descuentos


def _normalizar_pagina(raw_value, default: int = 1) -> int:
    try:
        pagina = int(raw_value)
    except (TypeError, ValueError):
        pagina = default
    return max(pagina, 1)


def _obtener_rango_periodo(periodo: str) -> tuple[date, date]:
    anio, mes = periodo.split('-')
    anio_int = int(anio)
    mes_int = int(mes)
    inicio = date(anio_int, mes_int, 1)
    if mes_int == 12:
        siguiente = date(anio_int + 1, 1, 1)
    else:
        siguiente = date(anio_int, mes_int + 1, 1)
    return inicio, siguiente


def _paginar_historial(items: list[dict], page: int, per_page: int = HISTORIAL_RESUMEN_POR_PAGINA) -> dict:
    total = len(items)
    pages = max((total + per_page - 1) // per_page, 1)
    page_actual = min(max(page, 1), pages)
    inicio = (page_actual - 1) * per_page
    fin = inicio + per_page
    return {
        'items': items[inicio:fin],
        'page': page_actual,
        'pages': pages,
        'per_page': per_page,
        'total': total,
        'has_prev': page_actual > 1,
        'has_next': page_actual < pages,
        'prev_num': page_actual - 1,
        'next_num': page_actual + 1,
    }


def _construir_historial_resumen(
    empleado: Empleado,
    periodo: str,
    movimientos: list[EmpleadoMovimientoSalario],
    config_llegadas_tardias: dict,
    page_historial: int,
) -> dict:
    inicio_periodo, fin_periodo = _obtener_rango_periodo(periodo)
    llegadas_tardias = empleado.ausencias.filter(
        EmpleadoAusencia.tipo == TIPO_AUSENCIA_LLEGADA_TARDIA,
        EmpleadoAusencia.fecha_desde >= inicio_periodo,
        EmpleadoAusencia.fecha_desde < fin_periodo,
    ).order_by(
        EmpleadoAusencia.fecha_desde.asc(),
        EmpleadoAusencia.id_ausencia.asc(),
    ).all()

    items_historial: list[dict] = []
    monto_tardia = Decimal(config_llegadas_tardias.get('monto') or 0)
    desde_tardia = int(config_llegadas_tardias.get('desde') or 1)
    numero_tardia = 0

    for tardia in llegadas_tardias:
        computable = tardia.estado in ESTADOS_LLEGADA_TARDIA_DESCONTABLES
        descuento_aplicado = Decimal('0.00')
        numero_computable = None
        if computable:
            numero_tardia += 1
            numero_computable = numero_tardia
            if numero_tardia >= desde_tardia and monto_tardia > 0:
                descuento_aplicado = monto_tardia
        items_historial.append(
            {
                'origen': 'llegada_tardia',
                'id': tardia.id_ausencia,
                'fecha': tardia.fecha_desde,
                'tipo': tardia.tipo,
                'tipo_label': 'Llegada tardía',
                'concepto': tardia.motivo,
                'observaciones': tardia.observaciones,
                'calculo_detalle': None,
                'estado': tardia.estado,
                'computable': computable,
                'numero_computable': numero_computable,
                'incide_aguinaldo': None,
                'monto': descuento_aplicado,
                'es_descuento': descuento_aplicado > 0,
            }
        )

    for movimiento in movimientos:
        items_historial.append(
            {
                'origen': 'movimiento',
                'id': movimiento.id_movimiento,
                'fecha': movimiento.fecha_movimiento,
                'tipo': movimiento.tipo,
                'tipo_label': etiqueta_tipo_movimiento(movimiento.tipo, movimiento.cliente_id),
                'concepto': movimiento.concepto,
                'observaciones': movimiento.observaciones,
                'calculo_detalle': (
                    f'{formatear_cantidad_movimiento(Decimal(movimiento.cantidad_calculo))} {movimiento.unidad_calculo} '
                    f'x Gs. {Decimal(movimiento.valor_unitario_calculo):,.0f}'.replace(',', '.')
                    if movimiento.cantidad_calculo and movimiento.unidad_calculo and movimiento.valor_unitario_calculo
                    else None
                ),
                'estado': None,
                'computable': None,
                'numero_computable': None,
                'incide_aguinaldo': bool(movimiento.incide_aguinaldo),
                'monto': movimiento.monto_decimal(),
                'es_descuento': es_tipo_movimiento_negativo(movimiento.tipo, movimiento.cliente_id),
            }
        )

    items_historial.sort(
        key=lambda item: (
            item['fecha'],
            item['id'],
            1 if item['origen'] == 'movimiento' else 0,
        ),
        reverse=True,
    )
    paginacion = _paginar_historial(items_historial, page_historial)
    return {
        'items': paginacion['items'],
        'paginacion': paginacion,
        'total': paginacion['total'],
        'movimientos_manual_count': len(movimientos),
        'llegadas_tardias_count': len(llegadas_tardias),
    }


def _armar_resumen_empleado(empleado: Empleado, periodo: str, page_historial: int = 1) -> dict:
    movimientos = empleado.movimientos.filter_by(periodo=periodo).order_by(
        EmpleadoMovimientoSalario.fecha_movimiento.desc(),
        EmpleadoMovimientoSalario.id_movimiento.desc(),
    ).all()
    salario_base = empleado.salario_base_decimal()
    extras, descuentos = _sumar_movimientos(movimientos)
    config_llegadas_tardias = _obtener_configuracion_llegada_tardia(
        cliente_id=_obtener_cliente_scope(empleado),
    )
    llegadas_tardias_mes = _contar_llegadas_tardias_periodo(empleado, periodo)
    llegadas_tardias_descontadas, descuento_llegadas_tardias = _calcular_descuento_llegadas_tardias(
        llegadas_tardias_mes,
        config_llegadas_tardias,
    )

    # Descuento automático por asistencia (días ausentes / medio día)
    from control_de_empleados.services.asistencia import calcular_descuento_asistencia
    descuento_asistencia = calcular_descuento_asistencia(
        empleado.id_empleado, periodo, salario_base,
    )

    descuentos_manual = descuentos
    descuentos = (descuentos + descuento_llegadas_tardias + descuento_asistencia).quantize(Decimal('0.01'))
    total_estimado = (salario_base + extras - descuentos).quantize(Decimal('0.01'))
    historial = _construir_historial_resumen(
        empleado,
        periodo,
        movimientos,
        config_llegadas_tardias,
        page_historial=page_historial,
    )

    # Verificar si ya está pagado en este periodo
    pago_registrado = empleado.pagos.filter_by(periodo=periodo).first()

    return {
        'empleado': empleado,
        'movimientos': movimientos,
        'historial_items': historial['items'],
        'historial_paginacion': historial['paginacion'],
        'historial_total': historial['total'],
        'movimientos_manual_count': historial['movimientos_manual_count'],
        'historial_llegadas_tardias_count': historial['llegadas_tardias_count'],
        'salario_base': salario_base,
        'extras': extras,
        'descuentos_manual': descuentos_manual,
        'descuentos': descuentos,
        'descuento_llegadas_tardias': descuento_llegadas_tardias,
        'descuento_asistencia': descuento_asistencia,
        'llegadas_tardias_mes': llegadas_tardias_mes,
        'llegadas_tardias_descontadas': llegadas_tardias_descontadas,
        'config_llegadas_tardias': config_llegadas_tardias,
        'total_estimado': total_estimado,
        'pago': pago_registrado,
        'esta_pagado': pago_registrado is not None,
    }


def _opciones_tipos_pago() -> list[dict]:
    return [{'valor': valor, 'label': label} for valor, label in TIPOS_PAGO]


def _opciones_tipos_movimiento(cliente_id: int | None = None) -> list[dict]:
    scope = _cliente_scope_actual() if cliente_id is None else cliente_id
    return opciones_tipos_movimiento(scope)


def _opciones_tipos_ausencia_formulario(tipos_ausencia: list[dict]) -> list[dict]:
    return [
        tipo
        for tipo in tipos_ausencia
        if tipo.get('valor') != TIPO_AUSENCIA_LLEGADA_TARDIA
    ]


@control_empleados_bp.route('/')
@login_required
def index():
    denegacion = _resolver_denegacion('ver_control_empleados')
    if denegacion:
        return denegacion

    periodo = normalizar_periodo(request.args.get('periodo'))
    busqueda = normalizar_busqueda_empleado(request.args.get('q'))
    mostrar_activos, mostrar_inactivos = resolver_filtros_estado(
        request.args.get('estado'),
        request.args.get('mostrar_activos'),
        request.args.get('mostrar_inactivos'),
    )
    empleados_query = _aplicar_scope_cliente(Empleado.query, Empleado)
    if busqueda:
        empleados_query = empleados_query.filter(Empleado.nombre_completo.ilike(f'%{busqueda}%'))
    if not mostrar_activos and not mostrar_inactivos:
        empleados_query = empleados_query.filter(false())
    elif mostrar_activos and not mostrar_inactivos:
        empleados_query = empleados_query.filter(Empleado.activo.is_(True))
    elif mostrar_inactivos and not mostrar_activos:
        empleados_query = empleados_query.filter(Empleado.activo.is_(False))
    empleados = empleados_query.order_by(
        Empleado.activo.desc(),
        Empleado.nombre_completo.asc(),
    ).all()
    resumenes = [_armar_resumen_empleado(empleado, periodo) for empleado in empleados]
    total_nomina = sum((item['total_estimado'] for item in resumenes), Decimal('0.00'))
    total_extras = sum((item['extras'] for item in resumenes), Decimal('0.00'))
    total_descuentos = sum((item['descuentos'] for item in resumenes), Decimal('0.00'))
    return render_template(
        'control_de_empleados/index.html',
        periodo=periodo,
        empleados=empleados,
        resumenes=resumenes,
        total_nomina=total_nomina,
        total_extras=total_extras,
        total_descuentos=total_descuentos,
        total_activos=sum(1 for empleado in empleados if empleado.activo),
        busqueda=busqueda,
        mostrar_activos=mostrar_activos,
        mostrar_inactivos=mostrar_inactivos,
        puede_gestionar=_tiene_permiso_control('gestionar_control_empleados'),
    )


@control_empleados_bp.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    cliente_scope = _obtener_cliente_scope()

    if request.method == 'POST':
        nombre = (request.form.get('empresa_nombre') or '').strip()
        ruc = (request.form.get('empresa_ruc') or '').strip()
        direccion = (request.form.get('empresa_direccion') or '').strip()
        llegada_tardia_descuento_desde = max(
            _parse_entero_no_negativo(
                request.form.get('llegada_tardia_descuento_desde'),
                default=1,
            ),
            1,
        )
        llegada_tardia_descuento_monto = _parse_decimal(
            request.form.get('llegada_tardia_descuento_monto')
        ) or Decimal('0.00')

        _establecer_config_control_empleados(
            CLAVE_EMPRESA_NOMBRE,
            nombre,
            DESC_EMPRESA_NOMBRE,
            cliente_id=cliente_scope,
        )
        _establecer_config_control_empleados(
            CLAVE_EMPRESA_RUC,
            ruc,
            DESC_EMPRESA_RUC,
            cliente_id=cliente_scope,
        )
        _establecer_config_control_empleados(
            CLAVE_EMPRESA_DIRECCION,
            direccion,
            DESC_EMPRESA_DIRECCION,
            cliente_id=cliente_scope,
        )
        _establecer_config_control_empleados(
            CLAVE_LLEGADA_TARDIA_DESCUENTO_DESDE,
            str(llegada_tardia_descuento_desde),
            DESC_LLEGADA_TARDIA_DESCUENTO_DESDE,
            cliente_id=cliente_scope,
        )
        _establecer_config_control_empleados(
            CLAVE_LLEGADA_TARDIA_DESCUENTO_MONTO,
            str(llegada_tardia_descuento_monto),
            DESC_LLEGADA_TARDIA_DESCUENTO_MONTO,
            cliente_id=cliente_scope,
        )

        flash('Configuración de recibos actualizada correctamente.', 'success')
        return redirect(url_for('control_empleados.configuracion'))

    config = _obtener_configuracion_empresa_rrhh(cliente_scope)
    config['llegadas_tardias'] = _obtener_configuracion_llegada_tardia(cliente_scope)

    return render_template(
        'control_de_empleados/configuracion.html',
        config=config
    )

@control_empleados_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    if request.method == 'POST':
        nombre_completo = (request.form.get('nombre_completo') or '').strip()
        salario_base = _parse_decimal(request.form.get('salario_base'))
        if not nombre_completo or salario_base is None:
            flash('Nombre y sueldo base son obligatorios.', 'warning')
            return render_template(
                'control_de_empleados/form.html',
                empleado=None,
                tipos_pago=_opciones_tipos_pago(),
            )
        dias_vacaciones_anuales = _parse_entero_no_negativo(
            request.form.get('dias_vacaciones_anuales'),
            default=12,
        )

        empleado = Empleado(
            cliente_id=_cliente_id_para_nuevo_registro(),
            nombre_completo=nombre_completo,
            documento=(request.form.get('documento') or '').strip() or None,
            telefono=(request.form.get('telefono') or '').strip() or None,
            cargo=(request.form.get('cargo') or '').strip() or None,
            area=(request.form.get('area') or '').strip() or None,
            salario_base=salario_base,
            dias_vacaciones_anuales=dias_vacaciones_anuales,
            salario_incluye_ips=bool(request.form.get('salario_incluye_ips')),
            tipo_pago=(request.form.get('tipo_pago') or 'mensual').strip() or 'mensual',
            fecha_ingreso=_parse_fecha(request.form.get('fecha_ingreso')),
            fecha_egreso=_parse_fecha(request.form.get('fecha_egreso')),
            activo=bool(request.form.get('activo')),
            notas=(request.form.get('notas') or '').strip() or None,
        )
        if empleado.activo:
            empleado.fecha_egreso = None
        db.session.add(empleado)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_empleado',
                    modulo='control_empleados',
                    descripcion=f'Creó empleado "{empleado.nombre_completo}"',
                    referencia_tipo='empleado',
                    referencia_id=empleado.id_empleado,
                    datos_nuevos={
                        'nombre_completo': empleado.nombre_completo,
                        'cargo': empleado.cargo,
                        'area': empleado.area,
                        'salario_base': str(empleado.salario_base),
                        'dias_vacaciones_anuales': empleado.dias_vacaciones_anuales_int(),
                        'salario_incluye_ips': bool(empleado.salario_incluye_ips),
                        'tipo_pago': empleado.tipo_pago,
                        'activo': bool(empleado.activo),
                    },
                    commit=False,
                )
        except Exception:
            pass

        db.session.commit()
        flash('Empleado creado correctamente.', 'success')
        return redirect(url_for('control_empleados.detalle', id_empleado=empleado.id_empleado))

    return render_template(
        'control_de_empleados/form.html',
        empleado=None,
        tipos_pago=_opciones_tipos_pago(),
    )


@control_empleados_bp.route('/<int:id_empleado>/editar', methods=['GET', 'POST'])
@login_required
def editar(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    if request.method == 'POST':
        nombre_completo = (request.form.get('nombre_completo') or '').strip()
        salario_base = _parse_decimal(request.form.get('salario_base'))
        if not nombre_completo or salario_base is None:
            flash('Nombre y sueldo base son obligatorios.', 'warning')
            return render_template(
                'control_de_empleados/form.html',
                empleado=empleado,
                tipos_pago=_opciones_tipos_pago(),
            )
        dias_vacaciones_anuales = _parse_entero_no_negativo(
            request.form.get('dias_vacaciones_anuales'),
            default=12,
        )

        if empleado.cliente_id is None:
            empleado.cliente_id = _cliente_id_para_nuevo_registro(empleado)
        datos_anteriores = {
            'nombre_completo': empleado.nombre_completo,
            'cargo': empleado.cargo,
            'area': empleado.area,
            'salario_base': str(empleado.salario_base),
            'dias_vacaciones_anuales': empleado.dias_vacaciones_anuales_int(),
            'salario_incluye_ips': bool(empleado.salario_incluye_ips),
            'tipo_pago': empleado.tipo_pago,
            'activo': bool(empleado.activo),
        }
        empleado.nombre_completo = nombre_completo
        empleado.documento = (request.form.get('documento') or '').strip() or None
        empleado.telefono = (request.form.get('telefono') or '').strip() or None
        empleado.cargo = (request.form.get('cargo') or '').strip() or None
        empleado.area = (request.form.get('area') or '').strip() or None
        empleado.salario_base = salario_base
        empleado.dias_vacaciones_anuales = dias_vacaciones_anuales
        empleado.salario_incluye_ips = bool(request.form.get('salario_incluye_ips'))
        empleado.tipo_pago = (request.form.get('tipo_pago') or 'mensual').strip() or 'mensual'
        empleado.fecha_ingreso = _parse_fecha(request.form.get('fecha_ingreso'))
        empleado.fecha_egreso = _parse_fecha(request.form.get('fecha_egreso'))
        empleado.activo = bool(request.form.get('activo'))
        empleado.notas = (request.form.get('notas') or '').strip() or None
        if empleado.activo:
            empleado.fecha_egreso = None

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='editar_empleado',
                    modulo='control_empleados',
                    descripcion=f'Editó empleado "{empleado.nombre_completo}"',
                    referencia_tipo='empleado',
                    referencia_id=empleado.id_empleado,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos={
                        'nombre_completo': empleado.nombre_completo,
                        'cargo': empleado.cargo,
                        'area': empleado.area,
                        'salario_base': str(empleado.salario_base),
                        'dias_vacaciones_anuales': empleado.dias_vacaciones_anuales_int(),
                        'salario_incluye_ips': bool(empleado.salario_incluye_ips),
                        'tipo_pago': empleado.tipo_pago,
                        'activo': bool(empleado.activo),
                    },
                    commit=False,
                )
        except Exception:
            pass

        db.session.commit()
        flash('Empleado actualizado correctamente.', 'success')
        return redirect(url_for('control_empleados.detalle', id_empleado=empleado.id_empleado))

    return render_template(
        'control_de_empleados/form.html',
        empleado=empleado,
        tipos_pago=_opciones_tipos_pago(),
    )


@control_empleados_bp.route('/<int:id_empleado>/toggle-activo', methods=['POST'])
@login_required
def toggle_activo(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    datos_anteriores = {'activo': bool(empleado.activo)}
    empleado.activo = not bool(empleado.activo)
    if empleado.activo:
        empleado.fecha_egreso = None
    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='activar_empleado' if empleado.activo else 'desactivar_empleado',
                modulo='control_empleados',
                descripcion=f'{"Activó" if empleado.activo else "Desactivó"} empleado "{empleado.nombre_completo}"',
                referencia_tipo='empleado',
                referencia_id=empleado.id_empleado,
                datos_anteriores=datos_anteriores,
                datos_nuevos={'activo': bool(empleado.activo)},
                commit=False,
            )
    except Exception:
        pass
    db.session.commit()
    flash(f'Empleado {"activado" if empleado.activo else "desactivado"} correctamente.', 'success')
    return redirect(request.form.get('next') or url_for('control_empleados.index'))


@control_empleados_bp.route('/<int:id_empleado>')
@login_required
def detalle(id_empleado: int):
    denegacion = _resolver_denegacion('ver_control_empleados')
    if denegacion:
        return denegacion

    periodo = normalizar_periodo(request.args.get('periodo'))
    tab = normalizar_tab(request.args.get('tab'))
    page_historial = _normalizar_pagina(request.args.get('page_historial'))
    empleado = _obtener_empleado_o_404(id_empleado)
    cliente_scope = _obtener_cliente_scope(empleado)
    tipos_ausencia = opciones_tipos_ausencia(cliente_scope)
    resumen = _armar_resumen_empleado(empleado, periodo, page_historial=page_historial)
    resumen_aguinaldo = calcular_resumen_aguinaldo(empleado, periodo) if tab == 'aguinaldo' else None
    panel_ausencias = (
        construir_panel_ausencias(
            empleado,
            normalizar_filtros_ausencias(request.args, periodo, cliente_id=cliente_scope),
            cliente_id=cliente_scope,
        )
        if tab == 'vacaciones'
        else None
    )

    panel_asistencia = None
    if tab == 'asistencia':
        from control_de_empleados.services.asistencia import construir_panel_asistencia
        panel_asistencia = construir_panel_asistencia(empleado, periodo)

    return render_template(
        'control_de_empleados/detalle.html',
        empleado=empleado,
        periodo=periodo,
        tab=tab,
        resumen=resumen,
        resumen_aguinaldo=resumen_aguinaldo,
        panel_ausencias=panel_ausencias,
        panel_asistencia=panel_asistencia,
        ausencia_en_edicion=_obtener_ausencia_en_edicion(empleado) if tab == 'vacaciones' else None,
        tipos_movimiento=_opciones_tipos_movimiento(cliente_scope),
        tipos_movimiento_personalizados=[tipo for tipo in _opciones_tipos_movimiento(cliente_scope) if tipo.get('eliminable')],
        tipos_ausencia=tipos_ausencia,
        tipos_ausencia_formulario=_opciones_tipos_ausencia_formulario(tipos_ausencia),
        tipos_ausencia_excedente=[
            tipo
            for tipo in tipos_ausencia
            if tipo['valor'] not in {'vacaciones', TIPO_AUSENCIA_LLEGADA_TARDIA}
        ],
        tipos_ausencia_personalizados=[tipo for tipo in tipos_ausencia if tipo.get('eliminable')],
        labels_tipos_ausencia={tipo['valor']: tipo['label'] for tipo in tipos_ausencia},
        estados_ausencia=opciones_estados_ausencia(),
        puede_gestionar=_tiene_permiso_control('gestionar_control_empleados'),
        puede_gestionar_tipos_ausencia=_tiene_permiso_control('gestionar_control_empleados'),
        fecha_hoy=date.today().isoformat(),
        fecha_periodo=_fecha_formulario_periodo(periodo),
    )


@control_empleados_bp.route('/movimientos/<int:id_movimiento>/aguinaldo', methods=['POST'])
@login_required
def actualizar_movimiento_aguinaldo(id_movimiento: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    movimiento = _aplicar_scope_cliente(
        EmpleadoMovimientoSalario.query,
        EmpleadoMovimientoSalario,
    ).filter(
        EmpleadoMovimientoSalario.id_movimiento == id_movimiento,
    ).first_or_404()
    movimiento.incide_aguinaldo = bool(request.form.get('incide_aguinaldo'))
    db.session.commit()

    periodo = normalizar_periodo(request.form.get('periodo') or movimiento.periodo)
    tab = normalizar_tab(request.form.get('tab'))
    page_historial = _normalizar_pagina(request.form.get('page_historial'))
    flash('Criterio de aguinaldo actualizado.', 'success')
    kwargs = {
        'id_empleado': movimiento.id_empleado,
        'periodo': periodo,
        'tab': tab,
    }
    if tab == 'resumen' and page_historial > 1:
        kwargs['page_historial'] = page_historial
    return redirect(
        url_for(
            'control_empleados.detalle',
            **kwargs,
        )
    )


from control_de_empleados import routes_ausencias as _routes_ausencias, routes_feriados as _routes_feriados, routes_movimientos as _routes_movimientos, routes_pagos as _routes_pagos, routes_asistencia as _routes_asistencia  # noqa: F401,E402
