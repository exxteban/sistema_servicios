from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from control_de_empleados.models import Empleado, EmpleadoAusencia, EmpleadoTipoAusencia
from control_de_empleados.routes import (
    TIPO_AUSENCIA_LLEGADA_TARDIA,
    _aplicar_scope_cliente,
    _armar_resumen_empleado,
    _cliente_id_para_nuevo_registro,
    _fecha_pertenece_a_periodo,
    _normalizar_pagina,
    _obtener_ausencia_en_edicion,
    _obtener_cliente_scope,
    _obtener_empleado_o_404,
    _opciones_tipos_movimiento,
    _opciones_tipos_ausencia_formulario,
    _parse_fecha,
    _resolver_denegacion,
    _tiene_permiso_control,
    control_empleados_bp,
)
from control_de_empleados.services.ausencias import (
    ESTADOS_AUSENCIA_VALIDOS,
    ESTADOS_AUSENCIA_RESERVAN_VACACIONES,
    construir_calendario_feriados,
    construir_panel_ausencias,
    construir_segmentos_vacaciones,
    encontrar_ausencia_solapada,
    normalizar_filtros_ausencias,
    normalizar_filtro_estado,
    normalizar_filtro_tipo,
    opciones_estados_ausencia,
    opciones_tipos_ausencia,
    obtener_saldos_vacaciones_por_anio,
)
from control_de_empleados.services.tipos_ausencia import (
    etiqueta_tipo_ausencia,
    generar_clave_tipo_ausencia,
    normalizar_nombre_tipo_ausencia,
    obtener_tipos_validos_ausencia,
    resolver_scope_tipos_ausencia,
)
from control_de_empleados.services.filtros import normalizar_periodo, normalizar_tab


def _url_detalle_ausencias(id_empleado: int, periodo: str, filtros: dict, edit_id: int | None = None) -> str:
    kwargs = {
        'id_empleado': id_empleado,
        'periodo': periodo,
        'tab': 'vacaciones',
        'anio': filtros['anio'],
    }
    if filtros['tipo']:
        kwargs['tipo_ausencia'] = filtros['tipo']
    if filtros['estado']:
        kwargs['estado_ausencia'] = filtros['estado']
    if filtros.get('page', 1) > 1:
        kwargs['page_ausencias'] = filtros['page']
    if edit_id:
        kwargs['edit_ausencia'] = edit_id
    return url_for('control_empleados.detalle', **kwargs)


def _es_respuesta_parcial() -> bool:
    return request.args.get('partial') == '1' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _responder_detalle_ausencias(
    empleado: Empleado,
    periodo: str,
    filtros: dict,
    ausencia_en_edicion: EmpleadoAusencia | None = None,
):
    edit_id = ausencia_en_edicion.id_ausencia if ausencia_en_edicion else None
    if not _es_respuesta_parcial():
        return redirect(_url_detalle_ausencias(empleado.id_empleado, periodo, filtros, edit_id=edit_id))

    cliente_scope = _obtener_cliente_scope(empleado)
    tipos_ausencia = opciones_tipos_ausencia(cliente_scope)
    return render_template(
        'control_de_empleados/detalle.html',
        empleado=empleado,
        periodo=periodo,
        tab='vacaciones',
        resumen=_armar_resumen_empleado(empleado, periodo),
        resumen_aguinaldo=None,
        panel_ausencias=construir_panel_ausencias(
            empleado,
            filtros,
            cliente_id=cliente_scope,
        ),
        ausencia_en_edicion=ausencia_en_edicion or _obtener_ausencia_en_edicion(empleado, request.form),
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
    )


def _redirect_detalle_resumen(id_empleado: int, periodo: str, page_historial: int = 1) -> str:
    kwargs = {
        'id_empleado': id_empleado,
        'periodo': periodo,
        'tab': 'resumen',
    }
    if page_historial > 1:
        kwargs['page_historial'] = page_historial
    return url_for('control_empleados.detalle', **kwargs)


def _registrar_auditoria_ausencia(empleado: Empleado, ausencia: EmpleadoAusencia) -> None:
    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='crear_ausencia_empleado',
                modulo='control_empleados',
                descripcion=f'Registró ausencia para "{empleado.nombre_completo}"',
                referencia_tipo='empleado_ausencia',
                referencia_id=ausencia.id_ausencia,
                datos_nuevos={
                    'id_empleado': empleado.id_empleado,
                    'tipo': ausencia.tipo,
                    'estado': ausencia.estado,
                    'fecha_desde': ausencia.fecha_desde.isoformat(),
                    'fecha_hasta': ausencia.fecha_hasta.isoformat(),
                    'motivo': ausencia.motivo,
                },
                commit=False,
            )
    except Exception:
        pass


def _registrar_auditoria_edicion_ausencia(
    ausencia: EmpleadoAusencia,
    datos_anteriores: dict,
) -> None:
    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='editar_ausencia_empleado',
                modulo='control_empleados',
                descripcion=f'Editó ausencia de "{ausencia.empleado.nombre_completo}"',
                referencia_tipo='empleado_ausencia',
                referencia_id=ausencia.id_ausencia,
                datos_anteriores=datos_anteriores,
                datos_nuevos={
                    'tipo': ausencia.tipo,
                    'estado': ausencia.estado,
                    'fecha_desde': ausencia.fecha_desde.isoformat(),
                    'fecha_hasta': ausencia.fecha_hasta.isoformat(),
                    'motivo': ausencia.motivo,
                    'observaciones': ausencia.observaciones,
                },
                commit=False,
            )
    except Exception:
        pass


@control_empleados_bp.route('/<int:id_empleado>/llegadas-tardias', methods=['POST'])
@login_required
def crear_llegada_tardia(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    page_historial = _normalizar_pagina(request.form.get('page_historial'))
    fecha_movimiento = _parse_fecha(request.form.get('fecha_movimiento'))
    motivo = (request.form.get('motivo') or '').strip()
    observaciones = (request.form.get('observaciones') or '').strip() or None

    if fecha_movimiento is None or not motivo:
        flash('Completa la fecha y el motivo de la llegada tardía.', 'warning')
        return redirect(_redirect_detalle_resumen(id_empleado, periodo, page_historial=page_historial))
    if not _fecha_pertenece_a_periodo(fecha_movimiento, periodo):
        flash('La fecha de la llegada tardía debe pertenecer al período seleccionado.', 'warning')
        return redirect(_redirect_detalle_resumen(id_empleado, periodo, page_historial=page_historial))

    llegada_existente = empleado.ausencias.filter(
        EmpleadoAusencia.tipo == TIPO_AUSENCIA_LLEGADA_TARDIA,
        EmpleadoAusencia.fecha_desde == fecha_movimiento,
        EmpleadoAusencia.fecha_hasta == fecha_movimiento,
    ).first()
    if llegada_existente:
        flash('Ya hay una llegada tardía registrada para esa fecha.', 'warning')
        return redirect(_redirect_detalle_resumen(id_empleado, periodo, page_historial=page_historial))

    ausencia = EmpleadoAusencia(
        cliente_id=_cliente_id_para_nuevo_registro(empleado),
        id_empleado=empleado.id_empleado,
        tipo=TIPO_AUSENCIA_LLEGADA_TARDIA,
        estado='tomado',
        fecha_desde=fecha_movimiento,
        fecha_hasta=fecha_movimiento,
        motivo=motivo,
        observaciones=observaciones,
        fecha_respuesta=date.today(),
    )
    db.session.add(ausencia)
    db.session.flush()
    _registrar_auditoria_ausencia(empleado, ausencia)
    db.session.commit()
    flash('Llegada tardía registrada. Ya impacta en el resumen salarial del mes.', 'success')
    return redirect(_redirect_detalle_resumen(id_empleado, periodo, page_historial=page_historial))


@control_empleados_bp.route('/<int:id_empleado>/ausencias', methods=['POST'])
@login_required
def crear_ausencia(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    cliente_scope = _obtener_cliente_scope(empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    filtros = normalizar_filtros_ausencias(request.form, periodo, cliente_id=cliente_scope)
    fecha_desde = _parse_fecha(request.form.get('fecha_desde'))
    fecha_hasta = _parse_fecha(request.form.get('fecha_hasta'))
    tipo = normalizar_filtro_tipo(request.form.get('tipo'), cliente_id=cliente_scope)
    estado = normalizar_filtro_estado(request.form.get('estado')) or 'pendiente'
    motivo = (request.form.get('motivo') or '').strip()
    observaciones = (request.form.get('observaciones') or '').strip() or None
    tipos_validos = obtener_tipos_validos_ausencia(cliente_scope)
    tipo_excedente = normalizar_filtro_tipo(request.form.get('tipo_excedente'), cliente_id=cliente_scope)
    if tipo_excedente == 'vacaciones':
        tipo_excedente = ''

    if tipo == '':
        flash('Selecciona un tipo de ausencia válido.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)
    if estado not in ESTADOS_AUSENCIA_VALIDOS:
        flash('Selecciona un estado válido para la ausencia.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)
    if not motivo or fecha_desde is None or fecha_hasta is None:
        flash('Completa motivo, fecha desde y fecha hasta.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)
    if fecha_hasta < fecha_desde:
        flash('La fecha hasta no puede ser anterior a la fecha desde.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)

    ausencia_solapada = encontrar_ausencia_solapada(empleado, fecha_desde, fecha_hasta)
    if estado != 'rechazado' and ausencia_solapada:
        flash(
            f'Ya existe una ausencia que se cruza con ese rango: {etiqueta_tipo_ausencia(ausencia_solapada.tipo, cliente_scope)} '
            f'del {ausencia_solapada.fecha_desde.strftime("%d/%m/%Y")} al {ausencia_solapada.fecha_hasta.strftime("%d/%m/%Y")}.',
            'warning',
        )
        return _responder_detalle_ausencias(empleado, periodo, filtros)

    ausencias_creadas: list[EmpleadoAusencia] = []
    if tipo == 'vacaciones' and estado in ESTADOS_AUSENCIA_RESERVAN_VACACIONES:
        anios = list(range(fecha_desde.year, fecha_hasta.year + 1))
        saldos = obtener_saldos_vacaciones_por_anio(empleado, anios, cliente_id=cliente_scope)
        disponibles_por_anio = {anio: item['disponibles'] for anio, item in saldos.items()}
        feriados_por_anio = construir_calendario_feriados(anios, cliente_id=cliente_scope)
        segmentos, overflow = construir_segmentos_vacaciones(
            fecha_desde,
            fecha_hasta,
            disponibles_por_anio,
            feriados_por_anio=feriados_por_anio,
            tipo_excedente=tipo_excedente or None,
        )
        if overflow > 0 and not tipo_excedente:
            detalle_saldos = ', '.join(
                f'{anio}: {item["disponibles"]} días'
                for anio, item in sorted(saldos.items())
            )
            flash(
                f'No hay saldo suficiente para cargar todo como vacaciones. Disponible por año: {detalle_saldos}. '
                'Si quieres registrar el excedente, elige un tipo alternativo.',
                'warning',
            )
            return _responder_detalle_ausencias(empleado, periodo, filtros)
        if tipo_excedente and tipo_excedente not in (tipos_validos - {'vacaciones'}):
            flash('El tipo alternativo para el excedente no es válido.', 'warning')
            return _responder_detalle_ausencias(empleado, periodo, filtros)

        for segmento in segmentos:
            ausencia = EmpleadoAusencia(
                cliente_id=_cliente_id_para_nuevo_registro(empleado),
                id_empleado=empleado.id_empleado,
                tipo=segmento['tipo'],
                estado=estado,
                fecha_desde=segmento['fecha_desde'],
                fecha_hasta=segmento['fecha_hasta'],
                motivo=motivo,
                observaciones=observaciones if segmento['tipo'] == 'vacaciones' else (
                    (observaciones + ' | ' if observaciones else '') + 'Segmentado automáticamente por excedente de vacaciones.'
                ),
                fecha_respuesta=date.today() if estado != 'pendiente' else None,
            )
            db.session.add(ausencia)
            db.session.flush()
            ausencias_creadas.append(ausencia)
            _registrar_auditoria_ausencia(empleado, ausencia)
    else:
        ausencia = EmpleadoAusencia(
            cliente_id=_cliente_id_para_nuevo_registro(empleado),
            id_empleado=empleado.id_empleado,
            tipo=tipo,
            estado=estado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            motivo=motivo,
            observaciones=observaciones,
            fecha_respuesta=date.today() if estado != 'pendiente' else None,
        )
        db.session.add(ausencia)
        db.session.flush()
        ausencias_creadas.append(ausencia)
        _registrar_auditoria_ausencia(empleado, ausencia)

    db.session.commit()
    if len(ausencias_creadas) > 1:
        flash('Ausencia registrada y segmentada automáticamente según el saldo de vacaciones disponible.', 'success')
    else:
        flash('Ausencia registrada correctamente.', 'success')
    return _responder_detalle_ausencias(empleado, periodo, filtros)


@control_empleados_bp.route('/ausencias/<int:id_ausencia>/estado', methods=['POST'])
@login_required
def actualizar_estado_ausencia(id_ausencia: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    ausencia = _aplicar_scope_cliente(
        EmpleadoAusencia.query,
        EmpleadoAusencia,
    ).filter(
        EmpleadoAusencia.id_ausencia == id_ausencia,
    ).first_or_404()
    periodo = normalizar_periodo(request.form.get('periodo'))
    filtros = normalizar_filtros_ausencias(
        request.form,
        periodo,
        cliente_id=_obtener_cliente_scope(ausencia.empleado),
    )
    nuevo_estado = normalizar_filtro_estado(request.form.get('estado'))
    if nuevo_estado not in ESTADOS_AUSENCIA_VALIDOS:
        flash('Selecciona un estado válido.', 'warning')
        return _responder_detalle_ausencias(ausencia.empleado, periodo, filtros)

    if nuevo_estado != 'rechazado':
        ausencia_solapada = encontrar_ausencia_solapada(
            ausencia.empleado,
            ausencia.fecha_desde,
            ausencia.fecha_hasta,
            excluir_id=ausencia.id_ausencia,
        )
        if ausencia_solapada:
            flash('No se pudo cambiar el estado porque el rango se superpone con otra ausencia activa.', 'warning')
            return _responder_detalle_ausencias(ausencia.empleado, periodo, filtros)
        if ausencia.tipo == 'vacaciones':
            cliente_scope = _obtener_cliente_scope(ausencia.empleado)
            saldos = obtener_saldos_vacaciones_por_anio(
                ausencia.empleado,
                list(range(ausencia.fecha_desde.year, ausencia.fecha_hasta.year + 1)),
                cliente_id=cliente_scope,
                excluir_id=ausencia.id_ausencia,
            )
            disponibles_por_anio = {anio: item['disponibles'] for anio, item in saldos.items()}
            feriados_por_anio = construir_calendario_feriados(
                list(range(ausencia.fecha_desde.year, ausencia.fecha_hasta.year + 1)),
                cliente_id=cliente_scope,
            )
            _, overflow = construir_segmentos_vacaciones(
                ausencia.fecha_desde,
                ausencia.fecha_hasta,
                disponibles_por_anio,
                feriados_por_anio=feriados_por_anio,
                tipo_excedente=None,
            )
            if overflow > 0:
                flash('No se pudo cambiar el estado porque ya no hay saldo suficiente de vacaciones para ese rango.', 'warning')
                return _responder_detalle_ausencias(ausencia.empleado, periodo, filtros)

    estado_anterior = ausencia.estado
    ausencia.estado = nuevo_estado
    ausencia.fecha_respuesta = date.today() if nuevo_estado != 'pendiente' else None

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='actualizar_estado_ausencia_empleado',
                modulo='control_empleados',
                descripcion=f'Actualizó el estado de ausencia de "{ausencia.empleado.nombre_completo}"',
                referencia_tipo='empleado_ausencia',
                referencia_id=ausencia.id_ausencia,
                datos_anteriores={'estado': estado_anterior},
                datos_nuevos={'estado': ausencia.estado},
                commit=False,
            )
    except Exception:
        pass

    db.session.commit()
    flash('Estado de la ausencia actualizado.', 'success')
    return _responder_detalle_ausencias(ausencia.empleado, periodo, filtros)


@control_empleados_bp.route('/ausencias/<int:id_ausencia>/editar', methods=['POST'])
@login_required
def editar_ausencia(id_ausencia: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    ausencia = _aplicar_scope_cliente(
        EmpleadoAusencia.query,
        EmpleadoAusencia,
    ).filter(
        EmpleadoAusencia.id_ausencia == id_ausencia,
    ).first_or_404()
    empleado = ausencia.empleado
    cliente_scope = _obtener_cliente_scope(empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    filtros = normalizar_filtros_ausencias(request.form, periodo, cliente_id=cliente_scope)
    fecha_desde = _parse_fecha(request.form.get('fecha_desde'))
    fecha_hasta = _parse_fecha(request.form.get('fecha_hasta'))
    tipo = normalizar_filtro_tipo(request.form.get('tipo'), cliente_id=cliente_scope)
    motivo = (request.form.get('motivo') or '').strip()
    observaciones = (request.form.get('observaciones') or '').strip() or None

    if tipo == '':
        flash('Selecciona un tipo de ausencia válido.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros, ausencia_en_edicion=ausencia)
    if not motivo or fecha_desde is None or fecha_hasta is None:
        flash('Completa motivo, fecha desde y fecha hasta.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros, ausencia_en_edicion=ausencia)
    if fecha_hasta < fecha_desde:
        flash('La fecha hasta no puede ser anterior a la fecha desde.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros, ausencia_en_edicion=ausencia)

    if ausencia.estado != 'rechazado':
        ausencia_solapada = encontrar_ausencia_solapada(
            empleado,
            fecha_desde,
            fecha_hasta,
            excluir_id=ausencia.id_ausencia,
        )
        if ausencia_solapada:
            flash(
                f'Ya existe una ausencia que se cruza con ese rango: {etiqueta_tipo_ausencia(ausencia_solapada.tipo, cliente_scope)} '
                f'del {ausencia_solapada.fecha_desde.strftime("%d/%m/%Y")} al {ausencia_solapada.fecha_hasta.strftime("%d/%m/%Y")}.',
                'warning',
            )
            return _responder_detalle_ausencias(empleado, periodo, filtros, ausencia_en_edicion=ausencia)

    if tipo == 'vacaciones' and ausencia.estado in ESTADOS_AUSENCIA_RESERVAN_VACACIONES:
        anios = list(range(fecha_desde.year, fecha_hasta.year + 1))
        saldos = obtener_saldos_vacaciones_por_anio(
            empleado,
            anios,
            cliente_id=cliente_scope,
            excluir_id=ausencia.id_ausencia,
        )
        disponibles_por_anio = {anio: item['disponibles'] for anio, item in saldos.items()}
        feriados_por_anio = construir_calendario_feriados(anios, cliente_id=cliente_scope)
        _, overflow = construir_segmentos_vacaciones(
            fecha_desde,
            fecha_hasta,
            disponibles_por_anio,
            feriados_por_anio=feriados_por_anio,
            tipo_excedente=None,
        )
        if overflow > 0:
            detalle_saldos = ', '.join(
                f'{anio}: {item["disponibles"]} días'
                for anio, item in sorted(saldos.items())
            )
            flash(
                f'No hay saldo suficiente para guardar ese rango como vacaciones. Disponible por año: {detalle_saldos}.',
                'warning',
            )
            return _responder_detalle_ausencias(empleado, periodo, filtros, ausencia_en_edicion=ausencia)

    datos_anteriores = {
        'tipo': ausencia.tipo,
        'estado': ausencia.estado,
        'fecha_desde': ausencia.fecha_desde.isoformat(),
        'fecha_hasta': ausencia.fecha_hasta.isoformat(),
        'motivo': ausencia.motivo,
        'observaciones': ausencia.observaciones,
    }
    ausencia.tipo = tipo
    ausencia.fecha_desde = fecha_desde
    ausencia.fecha_hasta = fecha_hasta
    ausencia.motivo = motivo
    ausencia.observaciones = observaciones
    if ausencia.estado != 'pendiente' and ausencia.fecha_respuesta is None:
        ausencia.fecha_respuesta = date.today()

    _registrar_auditoria_edicion_ausencia(ausencia, datos_anteriores)
    db.session.commit()
    flash('Ausencia actualizada correctamente.', 'success')
    return _responder_detalle_ausencias(empleado, periodo, filtros)


@control_empleados_bp.route('/ausencias/<int:id_ausencia>/eliminar', methods=['POST'])
@login_required
def eliminar_ausencia(id_ausencia: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    ausencia = _aplicar_scope_cliente(
        EmpleadoAusencia.query,
        EmpleadoAusencia,
    ).filter(
        EmpleadoAusencia.id_ausencia == id_ausencia,
    ).first_or_404()
    empleado = ausencia.empleado
    periodo = normalizar_periodo(request.form.get('periodo'))
    tab = normalizar_tab(request.form.get('tab'))
    page_historial = _normalizar_pagina(request.form.get('page_historial'))
    filtros = normalizar_filtros_ausencias(
        request.form,
        periodo,
        cliente_id=_obtener_cliente_scope(empleado),
    )

    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='eliminar_ausencia_empleado',
                modulo='control_empleados',
                descripcion=f'Eliminó ausencia de "{empleado.nombre_completo}"',
                referencia_tipo='empleado_ausencia',
                referencia_id=ausencia.id_ausencia,
                datos_anteriores={
                    'tipo': ausencia.tipo,
                    'estado': ausencia.estado,
                    'fecha_desde': ausencia.fecha_desde.isoformat(),
                    'fecha_hasta': ausencia.fecha_hasta.isoformat(),
                    'motivo': ausencia.motivo,
                },
                commit=False,
            )
    except Exception:
        pass

    db.session.delete(ausencia)
    db.session.commit()
    flash('Ausencia eliminada correctamente.', 'success')
    if tab == 'resumen':
        return redirect(
            _redirect_detalle_resumen(
                empleado.id_empleado,
                periodo,
                page_historial=page_historial,
            )
        )
    return _responder_detalle_ausencias(empleado, periodo, filtros)


@control_empleados_bp.route('/<int:id_empleado>/tipos-ausencia', methods=['POST'])
@login_required
def crear_tipo_ausencia_personalizado(id_empleado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    cliente_scope = _obtener_cliente_scope(empleado)
    scope_tipos = resolver_scope_tipos_ausencia(cliente_scope)
    periodo = normalizar_periodo(request.form.get('periodo'))
    filtros = normalizar_filtros_ausencias(request.form, periodo, cliente_id=cliente_scope)

    nombre = normalizar_nombre_tipo_ausencia(request.form.get('nombre_tipo_ausencia'))
    if not nombre:
        flash('Escribe un nombre para el nuevo tipo.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)

    clave = generar_clave_tipo_ausencia(nombre)
    if len(clave) < 3:
        flash('El nombre debe contener al menos 3 caracteres válidos.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)
    if clave in obtener_tipos_validos_ausencia(cliente_scope):
        flash('Ya existe un tipo con ese nombre para este cliente.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)

    db.session.add(
        EmpleadoTipoAusencia(
            cliente_id=scope_tipos,
            clave=clave,
            nombre=nombre,
        )
    )
    db.session.commit()
    flash(f'Tipo "{nombre}" agregado correctamente.', 'success')
    return _responder_detalle_ausencias(empleado, periodo, filtros)


@control_empleados_bp.route('/<int:id_empleado>/tipos-ausencia/<int:id_tipo_ausencia>/eliminar', methods=['POST'])
@login_required
def eliminar_tipo_ausencia_personalizado(id_empleado: int, id_tipo_ausencia: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    cliente_scope = _obtener_cliente_scope(empleado)
    scope_tipos = resolver_scope_tipos_ausencia(cliente_scope)
    periodo = normalizar_periodo(request.form.get('periodo'))
    filtros = normalizar_filtros_ausencias(request.form, periodo, cliente_id=cliente_scope)

    tipo = EmpleadoTipoAusencia.query.filter(
        EmpleadoTipoAusencia.id_tipo_ausencia == id_tipo_ausencia,
        EmpleadoTipoAusencia.cliente_id == scope_tipos,
    ).first_or_404()

    en_uso = EmpleadoAusencia.query.filter(
        EmpleadoAusencia.cliente_id == cliente_scope,
        EmpleadoAusencia.tipo == tipo.clave,
    ).first()
    if en_uso:
        flash('No se puede eliminar ese tipo porque ya tiene ausencias registradas.', 'warning')
        return _responder_detalle_ausencias(empleado, periodo, filtros)

    db.session.delete(tipo)
    db.session.commit()
    flash(f'Tipo "{tipo.nombre}" eliminado correctamente.', 'success')
    return _responder_detalle_ausencias(empleado, periodo, filtros)
