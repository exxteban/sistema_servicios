from decimal import Decimal, InvalidOperation

from flask import flash, redirect, request, url_for
from flask_login import login_required

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from control_de_empleados.models import EmpleadoMovimientoSalario
from control_de_empleados.routes import (
    _aplicar_scope_cliente,
    _cliente_id_para_nuevo_registro,
    _fecha_pertenece_a_periodo,
    _normalizar_pagina,
    _obtener_cliente_scope,
    _obtener_empleado_o_404,
    _parse_decimal,
    _parse_fecha,
    _resolver_denegacion,
    control_empleados_bp,
)
from control_de_empleados.services.tipos_movimiento import (
    formatear_cantidad_movimiento,
    generar_clave_tipo_movimiento,
    guardar_tipos_movimiento_personalizados,
    normalizar_impacto_tipo_movimiento,
    normalizar_modo_calculo_tipo_movimiento,
    normalizar_nombre_tipo_movimiento,
    normalizar_unidad_tipo_movimiento,
    normalizar_valor_unitario_tipo_movimiento,
    MODO_CALCULO_CANTIDAD,
    obtener_tipo_movimiento,
    obtener_tipos_movimiento_personalizados,
    obtener_tipos_validos_movimiento,
)
from control_de_empleados.services.filtros import normalizar_periodo, normalizar_tab


def _url_detalle_movimientos(id_empleado: int, periodo: str) -> str:
    return url_for('control_empleados.detalle', id_empleado=id_empleado, periodo=periodo, tab='resumen')


def _parse_cantidad(raw_value: str | None) -> Decimal | None:
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
    return valor.quantize(Decimal('0.001'))


@control_empleados_bp.route('/<int:id_empleado>/movimientos', methods=['POST'])
@login_required
def agregar_movimiento(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    tipo = (request.form.get('tipo') or '').strip()
    concepto = (request.form.get('concepto') or '').strip()
    monto = _parse_decimal(request.form.get('monto'))
    fecha_movimiento = _parse_fecha(request.form.get('fecha_movimiento'))
    cliente_scope = _obtener_cliente_scope(empleado)
    tipo_config = obtener_tipo_movimiento(tipo, cliente_scope)
    cantidad_calculo = None
    unidad_calculo = None
    valor_unitario_calculo = None

    if tipo_config and tipo_config.get('modo_calculo') == MODO_CALCULO_CANTIDAD:
        cantidad_calculo = _parse_cantidad(request.form.get('cantidad_movimiento'))
        valor_unitario_calculo = _parse_decimal(str(tipo_config.get('valor_unitario') or '0'))
        unidad_calculo = (tipo_config.get('unidad') or '').strip() or None
        if cantidad_calculo is None or cantidad_calculo <= 0 or valor_unitario_calculo is None or valor_unitario_calculo <= 0:
            flash('Carga una cantidad válida para calcular el monto.', 'warning')
            return redirect(_url_detalle_movimientos(id_empleado, periodo))
        monto = (cantidad_calculo * valor_unitario_calculo).quantize(Decimal('0.01'))
        if not concepto:
            concepto = f'{tipo_config["label"]}: {formatear_cantidad_movimiento(cantidad_calculo)} {unidad_calculo}'

    if tipo not in obtener_tipos_validos_movimiento(cliente_scope) or not concepto or monto is None or monto <= 0:
        flash('Completa tipo, concepto y monto correctamente.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))
    if fecha_movimiento is None:
        flash('La fecha del movimiento es obligatoria.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))
    if not _fecha_pertenece_a_periodo(fecha_movimiento, periodo):
        flash('La fecha del movimiento debe pertenecer al período seleccionado.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))

    movimiento = EmpleadoMovimientoSalario(
        cliente_id=_cliente_id_para_nuevo_registro(empleado),
        id_empleado=empleado.id_empleado,
        periodo=periodo,
        fecha_movimiento=fecha_movimiento,
        tipo=tipo,
        concepto=concepto,
        monto=monto,
        cantidad_calculo=cantidad_calculo,
        unidad_calculo=unidad_calculo,
        valor_unitario_calculo=valor_unitario_calculo,
        incide_aguinaldo=bool(request.form.get('incide_aguinaldo')),
        observaciones=(request.form.get('observaciones') or '').strip() or None,
    )
    db.session.add(movimiento)
    db.session.flush()

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='crear_movimiento_salario',
                modulo='control_empleados',
                descripcion=f'Registró movimiento salarial para "{empleado.nombre_completo}"',
                referencia_tipo='empleado_movimiento',
                referencia_id=movimiento.id_movimiento,
                datos_nuevos={
                    'id_empleado': empleado.id_empleado,
                    'periodo': movimiento.periodo,
                    'tipo': movimiento.tipo,
                    'concepto': movimiento.concepto,
                    'monto': str(movimiento.monto),
                    'cantidad_calculo': str(movimiento.cantidad_calculo) if movimiento.cantidad_calculo else None,
                    'unidad_calculo': movimiento.unidad_calculo,
                    'valor_unitario_calculo': str(movimiento.valor_unitario_calculo) if movimiento.valor_unitario_calculo else None,
                    'incide_aguinaldo': bool(movimiento.incide_aguinaldo),
                },
                commit=False,
            )
    except Exception:
        pass

    db.session.commit()
    flash('Movimiento salarial guardado correctamente.', 'success')
    return redirect(_url_detalle_movimientos(id_empleado, periodo))


@control_empleados_bp.route('/<int:id_empleado>/tipos-movimiento', methods=['POST'])
@login_required
def crear_tipo_movimiento_personalizado(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    cliente_scope = _obtener_cliente_scope(empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    nombre = normalizar_nombre_tipo_movimiento(request.form.get('nombre_tipo_movimiento'))
    impacto = normalizar_impacto_tipo_movimiento(request.form.get('impacto_tipo_movimiento'))
    modo_calculo = normalizar_modo_calculo_tipo_movimiento(request.form.get('modo_calculo_tipo_movimiento'))
    unidad = normalizar_unidad_tipo_movimiento(request.form.get('unidad_tipo_movimiento'))
    valor_unitario = normalizar_valor_unitario_tipo_movimiento(request.form.get('valor_unitario_tipo_movimiento'))

    if not nombre:
        flash('Escribe un nombre para el nuevo tipo de movimiento.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))

    clave = generar_clave_tipo_movimiento(nombre)
    if len(clave) < 3:
        flash('El nombre debe contener al menos 3 caracteres válidos.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))
    if clave in obtener_tipos_validos_movimiento(cliente_scope):
        flash('Ya existe un tipo de movimiento con ese nombre.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))
    if modo_calculo == MODO_CALCULO_CANTIDAD and (not unidad or valor_unitario <= 0):
        flash('Para calcular por cantidad, indica unidad y valor unitario mayor a cero.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))

    tipos = obtener_tipos_movimiento_personalizados(cliente_scope)
    tipos.append({
        'valor': clave,
        'label': nombre,
        'impacto': impacto,
        'modo_calculo': modo_calculo,
        'unidad': unidad,
        'valor_unitario': str(valor_unitario),
        'eliminable': True,
    })
    guardar_tipos_movimiento_personalizados(cliente_scope, tipos)
    flash(f'Tipo de movimiento "{nombre}" agregado correctamente.', 'success')
    return redirect(_url_detalle_movimientos(id_empleado, periodo))


@control_empleados_bp.route('/<int:id_empleado>/tipos-movimiento/<tipo_movimiento>/eliminar', methods=['POST'])
@login_required
def eliminar_tipo_movimiento_personalizado(id_empleado: int, tipo_movimiento: str):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    cliente_scope = _obtener_cliente_scope(empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    clave = (tipo_movimiento or '').strip().lower()
    tipos = obtener_tipos_movimiento_personalizados(cliente_scope)
    tipo = next((item for item in tipos if item['valor'] == clave), None)
    if not tipo:
        flash('Ese tipo de movimiento no existe o no se puede eliminar.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))

    en_uso = EmpleadoMovimientoSalario.query.filter(
        EmpleadoMovimientoSalario.cliente_id == cliente_scope,
        EmpleadoMovimientoSalario.tipo == clave,
    ).first()
    if en_uso:
        flash('No se puede eliminar ese tipo porque ya tiene movimientos registrados.', 'warning')
        return redirect(_url_detalle_movimientos(id_empleado, periodo))

    guardar_tipos_movimiento_personalizados(
        cliente_scope,
        [item for item in tipos if item['valor'] != clave],
    )
    flash(f'Tipo de movimiento "{tipo["label"]}" eliminado correctamente.', 'success')
    return redirect(_url_detalle_movimientos(id_empleado, periodo))


@control_empleados_bp.route('/movimientos/<int:id_movimiento>/eliminar', methods=['POST'])
@login_required
def eliminar_movimiento(id_movimiento: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    movimiento = _aplicar_scope_cliente(
        EmpleadoMovimientoSalario.query,
        EmpleadoMovimientoSalario,
    ).filter(
        EmpleadoMovimientoSalario.id_movimiento == id_movimiento,
    ).first_or_404()

    periodo = normalizar_periodo(request.form.get('periodo') or movimiento.periodo)
    tab = normalizar_tab(request.form.get('tab') or 'resumen')
    page_historial = _normalizar_pagina(request.form.get('page_historial'))
    empleado = movimiento.empleado

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='eliminar_movimiento_salario',
                modulo='control_empleados',
                descripcion=f'Eliminó movimiento salarial de "{empleado.nombre_completo}"',
                referencia_tipo='empleado_movimiento',
                referencia_id=movimiento.id_movimiento,
                datos_anteriores={
                    'id_empleado': movimiento.id_empleado,
                    'periodo': movimiento.periodo,
                    'tipo': movimiento.tipo,
                    'concepto': movimiento.concepto,
                    'monto': str(movimiento.monto),
                    'cantidad_calculo': str(movimiento.cantidad_calculo) if movimiento.cantidad_calculo else None,
                    'unidad_calculo': movimiento.unidad_calculo,
                    'valor_unitario_calculo': str(movimiento.valor_unitario_calculo) if movimiento.valor_unitario_calculo else None,
                    'incide_aguinaldo': bool(movimiento.incide_aguinaldo),
                },
                commit=False,
            )
    except Exception:
        pass

    db.session.delete(movimiento)
    db.session.commit()
    flash('Movimiento eliminado correctamente.', 'success')
    kwargs = {
        'id_empleado': empleado.id_empleado,
        'periodo': periodo,
        'tab': tab,
    }
    if tab == 'resumen' and page_historial > 1:
        kwargs['page_historial'] = page_historial
    return redirect(url_for('control_empleados.detalle', **kwargs))
