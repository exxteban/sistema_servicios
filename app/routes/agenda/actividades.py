from datetime import datetime, timedelta, timezone

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import String, and_, cast, or_
from sqlalchemy.orm import joinedload, load_only

from app import db
from app.models import AgendaActividad, Cliente, CrmContacto, Reparacion, Usuario, Venta
from app.routes.agenda import agenda_bp
from app.utils.helpers import get_app_timezone, local_strftime, parse_iso_date, utc_bounds_for_local_dates, utc_naive_to_local

TIPOS_ACTIVIDAD = ('cita', 'llamada', 'entrega', 'cobro', 'seguimiento', 'tarea_interna', 'recordatorio')
ESTADOS_ACTIVIDAD = ('pendiente', 'hecha', 'cancelada')
PRIORIDADES_ACTIVIDAD = ('baja', 'media', 'alta', 'critica')
ALCANCES_DESTINATARIOS = ('solo_responsable', 'todos', 'usuarios_especificos')
TIPOS_ACTIVIDAD_LABELS = {
    'cita': 'Cita',
    'llamada': 'Llamada',
    'entrega': 'Entrega',
    'cobro': 'Cobro',
    'seguimiento': 'Seguimiento',
    'tarea_interna': 'Tarea interna',
    'recordatorio': 'Recordatorio',
}
PRIORIDADES_ACTIVIDAD_LABELS = {
    'baja': 'Baja',
    'media': 'Media',
    'alta': 'Alta',
    'critica': 'Crítica',
}


def _normalizar_alcance_destinatarios(value):
    alcance = (value or '').strip().lower()
    if alcance in ALCANCES_DESTINATARIOS:
        return alcance
    return 'solo_responsable'


def _parse_user_ids_list(values):
    ids = []
    seen = set()
    for value in values or []:
        try:
            parsed = int(value)
        except Exception:
            continue
        if parsed <= 0 or parsed in seen:
            continue
        ids.append(parsed)
        seen.add(parsed)
    return ids


def _filtro_mostrar_agenda_para_usuario(user_id: int):
    return or_(
        AgendaActividad.creado_por_id == user_id,
        AgendaActividad.mostrar_agenda_en == 'todos',
        and_(
            AgendaActividad.mostrar_agenda_en == 'solo_responsable',
            AgendaActividad.usuario_id == user_id,
        ),
        and_(
            AgendaActividad.mostrar_agenda_en == 'usuarios_especificos',
            AgendaActividad.usuarios_agenda.any(Usuario.id_usuario == user_id),
        ),
    )


def _filtro_recordatorio_para_usuario(user_id: int):
    return or_(
        AgendaActividad.recordatorio_a == 'todos',
        and_(
            AgendaActividad.recordatorio_a == 'solo_responsable',
            AgendaActividad.usuario_id == user_id,
        ),
        and_(
            AgendaActividad.recordatorio_a == 'usuarios_especificos',
            AgendaActividad.usuarios_recordatorio.any(Usuario.id_usuario == user_id),
        ),
    )


def _resolver_destinatarios_formulario(data=None, actividad=None):
    if data is not None and hasattr(data, 'getlist'):
        mostrar_agenda_en = _normalizar_alcance_destinatarios(data.get('mostrar_agenda_en'))
        recordatorio_a = _normalizar_alcance_destinatarios(data.get('recordatorio_a'))
        usuarios_agenda_ids = _parse_user_ids_list(data.getlist('visible_usuario_ids'))
        usuarios_recordatorio_ids = _parse_user_ids_list(data.getlist('recordatorio_usuario_ids'))
        return mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids

    if actividad is not None:
        mostrar_agenda_en = _normalizar_alcance_destinatarios(getattr(actividad, 'mostrar_agenda_en', None))
        recordatorio_a = _normalizar_alcance_destinatarios(getattr(actividad, 'recordatorio_a', None))
        usuarios_agenda_ids = [usuario.id_usuario for usuario in (actividad.usuarios_agenda or [])]
        usuarios_recordatorio_ids = [usuario.id_usuario for usuario in (actividad.usuarios_recordatorio or [])]
        return mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids

    return 'solo_responsable', [], 'solo_responsable', []


def _validar_destinatarios(mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids):
    if mostrar_agenda_en == 'usuarios_especificos' and not usuarios_agenda_ids:
        return 'Debes seleccionar al menos un usuario en "Mostrar en agenda de".'
    if recordatorio_a == 'usuarios_especificos' and not usuarios_recordatorio_ids:
        return 'Debes seleccionar al menos un usuario en "Enviar recordatorio a".'
    return None


def _cargar_usuarios_por_ids(ids):
    if not ids:
        return []
    usuarios = (
        Usuario.query
        .filter(Usuario.activo.is_(True), Usuario.id_usuario.in_(ids))
        .order_by(Usuario.nombre_completo.asc())
        .all()
    )
    usuarios_por_id = {usuario.id_usuario: usuario for usuario in usuarios}
    return [usuarios_por_id[user_id] for user_id in ids if user_id in usuarios_por_id]


def _aplicar_destinatarios_a_actividad(
    actividad: AgendaActividad,
    mostrar_agenda_en,
    usuarios_agenda_ids,
    recordatorio_a,
    usuarios_recordatorio_ids,
):
    actividad.mostrar_agenda_en = _normalizar_alcance_destinatarios(mostrar_agenda_en)
    actividad.recordatorio_a = _normalizar_alcance_destinatarios(recordatorio_a)
    actividad.usuarios_agenda = (
        _cargar_usuarios_por_ids(usuarios_agenda_ids)
        if actividad.mostrar_agenda_en == 'usuarios_especificos'
        else []
    )
    actividad.usuarios_recordatorio = (
        _cargar_usuarios_por_ids(usuarios_recordatorio_ids)
        if actividad.recordatorio_a == 'usuarios_especificos'
        else []
    )


def _limpiar_destinatarios_actividad(actividad: AgendaActividad):
    actividad.usuarios_agenda = []
    actividad.usuarios_recordatorio = []


def _puede_ver_todo() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')


def _query_visible():
    query = AgendaActividad.query
    if _puede_ver_todo():
        return query
    return query.filter(_filtro_mostrar_agenda_para_usuario(current_user.id_usuario))


def _wants_json_response() -> bool:
    if request.path.startswith('/agenda/api/'):
        return True
    if request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)


def _parse_datetime_local(value: str | None):
    if not value:
        return None
    value = value.strip()
    fmt = '%Y-%m-%dT%H:%M' if 'T' in value else '%Y-%m-%d %H:%M'
    try:
        dt_local = datetime.strptime(value, fmt)
    except Exception:
        return None
    tz = get_app_timezone()
    aware = dt_local.replace(tzinfo=tz)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _to_datetime_local_input(value):
    local_dt = utc_naive_to_local(value)
    if not local_dt:
        return ''
    return local_dt.strftime('%Y-%m-%dT%H:%M')


def _parse_optional_int(value):
    try:
        if value in (None, ''):
            return None
        return int(value)
    except Exception:
        return None


def _utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fecha_vencimiento_actividad(actividad: AgendaActividad):
    fecha_inicio = actividad.fecha_inicio
    fecha_fin = actividad.fecha_fin
    if fecha_fin and (not fecha_inicio or fecha_fin >= fecha_inicio):
        return fecha_fin
    return fecha_inicio


def _fecha_referencia_recordatorio_actividad(actividad: AgendaActividad):
    return _fecha_vencimiento_actividad(actividad)


def _label_tipo_actividad(tipo: str | None) -> str:
    normalized = (tipo or '').strip().lower()
    if normalized in TIPOS_ACTIVIDAD_LABELS:
        return TIPOS_ACTIVIDAD_LABELS[normalized]
    if not normalized:
        return 'Actividad'
    return normalized.replace('_', ' ').strip().capitalize()


def _label_prioridad_actividad(prioridad: str | None) -> str:
    normalized = (prioridad or '').strip().lower()
    if normalized in PRIORIDADES_ACTIVIDAD_LABELS:
        return PRIORIDADES_ACTIVIDAD_LABELS[normalized]
    if not normalized:
        return 'Media'
    return normalized.capitalize()


def _label_recordatorio_minutos(recordatorio_minutos: int | None) -> str:
    if recordatorio_minutos is None:
        return 'Sin recordatorio'
    if recordatorio_minutos <= 0:
        return 'Aviso al momento'
    return f'Aviso {recordatorio_minutos} min antes'


def _detalle_alerta_actividad(
    actividad: AgendaActividad,
    estado_alerta: str,
    fecha_inicio_local: str,
    fecha_vencimiento_local: str,
    recordatorio_minutos: int | None,
    now_utc=None,
):
    now_utc = now_utc or _utc_now_naive()
    if estado_alerta == 'overdue':
        if actividad.fecha_fin and (not actividad.fecha_inicio or actividad.fecha_fin >= actividad.fecha_inicio):
            return 'Vencida', f'Venció {fecha_vencimiento_local}'
        return 'Vencida', f'Debía empezar {fecha_inicio_local}'
    if actividad.fecha_fin and (not actividad.fecha_inicio or actividad.fecha_fin >= actividad.fecha_inicio):
        return _label_recordatorio_minutos(recordatorio_minutos), f'Vence {fecha_vencimiento_local}'
    if now_utc >= actividad.fecha_inicio:
        return _label_recordatorio_minutos(recordatorio_minutos), f'Empieza {fecha_inicio_local}'
    return _label_recordatorio_minutos(recordatorio_minutos), f'Empieza {fecha_inicio_local}'


def _validar_temporalidad_actividad(fecha_inicio, fecha_fin, recordatorio_minutos):
    if fecha_fin and fecha_inicio and fecha_fin <= fecha_inicio:
        return 'La fecha fin debe ser posterior a la fecha de inicio.'

    if recordatorio_minutos is None:
        return None

    if recordatorio_minutos < 0:
        return 'El recordatorio no puede ser negativo.'

    if fecha_inicio and fecha_fin:
        duracion_segundos = (fecha_fin - fecha_inicio).total_seconds()
        if duracion_segundos <= 0:
            return 'La fecha fin debe ser posterior a la fecha de inicio.'
        if (recordatorio_minutos * 60) >= duracion_segundos:
            return 'El recordatorio debe ser menor al tiempo entre la fecha de inicio y la fecha fin.'

    return None


def _resolver_estado_alerta(actividad: AgendaActividad, now_utc=None):
    if not actividad or actividad.estado != 'pendiente' or not actividad.fecha_inicio:
        return None

    now_utc = now_utc or _utc_now_naive()
    fecha_vencimiento = _fecha_vencimiento_actividad(actividad)
    if fecha_vencimiento and now_utc >= fecha_vencimiento:
        return 'overdue'

    recordatorio_minutos = _parse_optional_int(actividad.recordatorio_minutos)
    if recordatorio_minutos is None or recordatorio_minutos < 0:
        return None

    fecha_referencia = _fecha_referencia_recordatorio_actividad(actividad)
    if not fecha_referencia:
        return None
    recordatorio_at = fecha_referencia - timedelta(minutes=recordatorio_minutos)
    if recordatorio_at <= now_utc < fecha_vencimiento:
        return 'alert'
    return None


def _serializar_alerta_actividad(actividad: AgendaActividad, now_utc=None):
    now_utc = now_utc or _utc_now_naive()
    estado_alerta = _resolver_estado_alerta(actividad, now_utc=now_utc)
    if not estado_alerta:
        return None

    fecha_inicio = actividad.fecha_inicio
    fecha_vencimiento = _fecha_vencimiento_actividad(actividad)
    fecha_referencia = _fecha_referencia_recordatorio_actividad(actividad)
    recordatorio_minutos = _parse_optional_int(actividad.recordatorio_minutos)
    trigger_at = fecha_vencimiento or fecha_inicio
    if (
        estado_alerta == 'alert'
        and fecha_referencia
        and recordatorio_minutos is not None
        and recordatorio_minutos >= 0
    ):
        trigger_at = fecha_referencia - timedelta(minutes=recordatorio_minutos)
    fecha_inicio_local = local_strftime(fecha_inicio)
    fecha_vencimiento_local = local_strftime(fecha_vencimiento) if fecha_vencimiento else fecha_inicio_local
    badge_label, detail_label = _detalle_alerta_actividad(
        actividad,
        estado_alerta,
        fecha_inicio_local,
        fecha_vencimiento_local,
        recordatorio_minutos,
        now_utc=now_utc,
    )

    return {
        'id': actividad.id,
        'titulo': actividad.titulo,
        'tipo': actividad.tipo,
        'tipo_label': _label_tipo_actividad(actividad.tipo),
        'prioridad': actividad.prioridad,
        'prioridad_label': _label_prioridad_actividad(actividad.prioridad),
        'estado': actividad.estado,
        'estado_alerta': estado_alerta,
        'recordatorio_minutos': recordatorio_minutos,
        'recordatorio_label': _label_recordatorio_minutos(recordatorio_minutos),
        'fecha_inicio_utc': f'{fecha_inicio.isoformat()}Z',
        'fecha_inicio_local': fecha_inicio_local,
        'fecha_vencimiento_utc': f'{fecha_vencimiento.isoformat()}Z' if fecha_vencimiento else None,
        'fecha_vencimiento_local': fecha_vencimiento_local,
        'trigger_at_utc': f'{trigger_at.isoformat()}Z',
        'badge_label': badge_label,
        'detail_label': detail_label,
        'alert_key': f'{actividad.id}:{estado_alerta}:{trigger_at.isoformat()}',
    }


def _proximo_cambio_alerta_actividad(actividad: AgendaActividad, now_utc=None):
    if not actividad or actividad.estado != 'pendiente' or not actividad.fecha_inicio:
        return None

    now_utc = now_utc or _utc_now_naive()
    fecha_vencimiento = _fecha_vencimiento_actividad(actividad)
    if fecha_vencimiento and now_utc >= fecha_vencimiento:
        return None

    recordatorio_minutos = _parse_optional_int(actividad.recordatorio_minutos)
    if recordatorio_minutos is not None and recordatorio_minutos >= 0:
        fecha_referencia = _fecha_referencia_recordatorio_actividad(actividad)
        recordatorio_at = (
            fecha_referencia - timedelta(minutes=recordatorio_minutos)
            if fecha_referencia else None
        )
        if recordatorio_at and now_utc < recordatorio_at:
            return recordatorio_at

    if fecha_vencimiento and now_utc < fecha_vencimiento:
        return fecha_vencimiento

    return None


def _serializar_cliente(cliente: Cliente | None):
    if not cliente:
        return None
    return {
        'id_cliente': cliente.id_cliente,
        'nombre': cliente.nombre,
        'ruc_ci': cliente.ruc_ci or '',
        'telefono': cliente.telefono or '',
        'email': cliente.email or '',
    }


def _serializar_venta(venta: Venta | None):
    if not venta:
        return None
    return {
        'id_venta': venta.id_venta,
        'id_cliente': venta.id_cliente,
        'fecha_venta': local_strftime(venta.fecha_venta),
        'total': float(venta.total or 0),
        'estado': venta.estado or '',
        'numero_comprobante': venta.numero_comprobante or '',
        'cliente': _serializar_cliente(getattr(venta, 'cliente', None)),
    }


def _serializar_reparacion(reparacion: Reparacion | None):
    if not reparacion:
        return None
    return {
        'id_reparacion': reparacion.id_reparacion,
        'cliente_id': reparacion.cliente_id,
        'tipo_equipo': reparacion.tipo_equipo or '',
        'marca_modelo': reparacion.marca_modelo or '',
        'estado': reparacion.estado or '',
        'fecha_ingreso': local_strftime(reparacion.fecha_ingreso),
        'cliente': _serializar_cliente(getattr(reparacion, 'cliente', None)),
    }


def _obtener_relaciones_iniciales(data=None, actividad=None):
    cliente_id = _parse_optional_int(data.get('cliente_id') if data else None)
    reparacion_id = _parse_optional_int(data.get('reparacion_id') if data else None)
    venta_id = _parse_optional_int(data.get('venta_id') if data else None)

    if cliente_id is None and actividad:
        cliente_id = actividad.cliente_id
    if reparacion_id is None and actividad:
        reparacion_id = actividad.reparacion_id
    if venta_id is None and actividad:
        venta_id = actividad.venta_id

    cliente = None
    reparacion = None
    venta = None
    if cliente_id:
        cliente = (
            Cliente.query.options(
                load_only(
                    Cliente.id_cliente,
                    Cliente.nombre,
                    Cliente.ruc_ci,
                    Cliente.telefono,
                    Cliente.email,
                )
            )
            .filter(Cliente.id_cliente == cliente_id)
            .first()
        )
    if reparacion_id:
        reparacion = (
            Reparacion.query.options(
                load_only(
                    Reparacion.id_reparacion,
                    Reparacion.cliente_id,
                    Reparacion.tipo_equipo,
                    Reparacion.marca_modelo,
                    Reparacion.estado,
                    Reparacion.fecha_ingreso,
                ),
                joinedload(Reparacion.cliente).load_only(
                    Cliente.id_cliente,
                    Cliente.nombre,
                    Cliente.ruc_ci,
                    Cliente.telefono,
                    Cliente.email,
                ),
            )
            .filter(Reparacion.id_reparacion == reparacion_id)
            .first()
        )
    if venta_id:
        venta = (
            Venta.query.options(
                load_only(
                    Venta.id_venta,
                    Venta.id_cliente,
                    Venta.fecha_venta,
                    Venta.total,
                    Venta.estado,
                    Venta.numero_comprobante,
                ),
                joinedload(Venta.cliente).load_only(
                    Cliente.id_cliente,
                    Cliente.nombre,
                    Cliente.ruc_ci,
                    Cliente.telefono,
                    Cliente.email,
                ),
            )
            .filter(Venta.id_venta == venta_id)
            .first()
        )
    return _serializar_cliente(cliente), _serializar_reparacion(reparacion), _serializar_venta(venta)


def _obtener_opciones_formulario():
    usuarios = Usuario.query.filter_by(activo=True).order_by(Usuario.nombre_completo.asc()).all()
    contactos = CrmContacto.query.order_by(CrmContacto.id.desc()).limit(120).all()
    return usuarios, contactos


def _render_formulario_actividad(
    modo,
    actividad,
    data,
    usuarios,
    contactos,
    cliente_inicial,
    reparacion_inicial,
    venta_inicial,
):
    mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids = _resolver_destinatarios_formulario(
        data=data,
        actividad=actividad,
    )
    return render_template(
        'agenda/form.html',
        modo=modo,
        actividad=actividad,
        data=data or {},
        usuarios=usuarios,
        contactos=contactos,
        tipos_actividad=TIPOS_ACTIVIDAD,
        prioridades_actividad=PRIORIDADES_ACTIVIDAD,
        alcances_destinatarios=ALCANCES_DESTINATARIOS,
        mostrar_agenda_en=mostrar_agenda_en,
        usuarios_agenda_ids=usuarios_agenda_ids,
        recordatorio_a=recordatorio_a,
        usuarios_recordatorio_ids=usuarios_recordatorio_ids,
        cliente_inicial=cliente_inicial,
        reparacion_inicial=reparacion_inicial,
        venta_inicial=venta_inicial,
        to_datetime_local_input=_to_datetime_local_input,
    )


def _cargar_actividad_visible_o_404(id_actividad: int):
    return _query_visible().filter(AgendaActividad.id == id_actividad).first_or_404()


def _resolver_filtros_lista_actividades(args=None):
    args = args or request.args
    return {
        'page': max(args.get('page', 1, type=int), 1),
        'estado': (args.get('estado') or '').strip().lower(),
        'tipo': (args.get('tipo') or '').strip().lower(),
        'prioridad': (args.get('prioridad') or '').strip().lower(),
        'sort_by': (args.get('sort') or 'estado').strip().lower(),
        'sort_dir': (args.get('dir') or 'asc').strip().lower(),
        'responsable_id': args.get('responsable_id', type=int),
        'desde': parse_iso_date(args.get('desde')),
        'hasta': parse_iso_date(args.get('hasta')),
    }


def _construir_query_lista_actividades(filtros, include_options=True, include_sort=True):
    query = _query_visible()
    if include_options:
        query = query.options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.titulo,
                AgendaActividad.tipo,
                AgendaActividad.fecha_inicio,
                AgendaActividad.fecha_fin,
                AgendaActividad.estado,
                AgendaActividad.prioridad,
                AgendaActividad.recordatorio_minutos,
                AgendaActividad.usuario_id,
                AgendaActividad.updated_at,
            ),
            joinedload(AgendaActividad.usuario).load_only(
                Usuario.id_usuario,
                Usuario.nombre_completo,
                Usuario.username,
            ),
        )

    estado = filtros['estado']
    tipo = filtros['tipo']
    prioridad = filtros['prioridad']
    responsable_id = filtros['responsable_id']
    desde = filtros['desde']
    hasta = filtros['hasta']

    if estado in ESTADOS_ACTIVIDAD:
        query = query.filter(AgendaActividad.estado == estado)
    if tipo in TIPOS_ACTIVIDAD:
        query = query.filter(AgendaActividad.tipo == tipo)
    if prioridad in PRIORIDADES_ACTIVIDAD:
        query = query.filter(AgendaActividad.prioridad == prioridad)
    if responsable_id and _puede_ver_todo():
        query = query.filter(AgendaActividad.usuario_id == responsable_id)

    if desde or hasta:
        if desde and not hasta:
            hasta = desde
        if hasta and not desde:
            desde = hasta
        start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
        query = query.filter(AgendaActividad.fecha_inicio >= start_utc, AgendaActividad.fecha_inicio < end_utc)

    if not include_sort:
        return query

    sort_by = filtros['sort_by']
    sort_dir = filtros['sort_dir']
    sort_columns = {
        'actividad': AgendaActividad.titulo,
        'fecha_inicio': AgendaActividad.fecha_inicio,
        'responsable': Usuario.nombre_completo,
        'estado': AgendaActividad.estado,
        'prioridad': AgendaActividad.prioridad,
    }
    if sort_by not in sort_columns:
        sort_by = 'estado'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'

    if sort_by == 'responsable':
        query = query.join(Usuario, AgendaActividad.usuario_id == Usuario.id_usuario)

    sort_column = sort_columns[sort_by]
    primary_order = db.desc(sort_column) if sort_dir == 'desc' else db.asc(sort_column)
    secondary_order = db.desc(AgendaActividad.id) if sort_dir == 'desc' else db.asc(AgendaActividad.id)
    return query.order_by(primary_order, secondary_order)


@agenda_bp.route('/actividades', methods=['GET'])
@login_required
def lista_actividades():
    filtros = _resolver_filtros_lista_actividades()
    page = filtros['page']
    estado = filtros['estado']
    tipo = filtros['tipo']
    prioridad = filtros['prioridad']
    sort_by = filtros['sort_by']
    sort_dir = filtros['sort_dir']
    responsable_id = filtros['responsable_id']
    desde = filtros['desde']
    hasta = filtros['hasta']

    actividades = _construir_query_lista_actividades(filtros).paginate(page=page, per_page=25, error_out=False)

    responsables = (
        Usuario.query.filter_by(activo=True).order_by(Usuario.nombre_completo.asc()).all()
        if _puede_ver_todo()
        else [current_user]
    )
    now_utc = _utc_now_naive()
    alert_states = {actividad.id: _resolver_estado_alerta(actividad, now_utc=now_utc) for actividad in actividades.items}

    return render_template(
        'agenda/lista.html',
        actividades=actividades,
        alert_states=alert_states,
        estado=estado,
        tipo=tipo,
        prioridad=prioridad,
        sort=sort_by,
        dir=sort_dir,
        responsable_id=responsable_id,
        desde=desde.isoformat() if desde else '',
        hasta=hasta.isoformat() if hasta else '',
        responsables=responsables,
        tipos_actividad=TIPOS_ACTIVIDAD,
        estados_actividad=ESTADOS_ACTIVIDAD,
        prioridades_actividad=PRIORIDADES_ACTIVIDAD,
        puede_ver_todo=_puede_ver_todo(),
    )


@agenda_bp.route('/api/alertas/resumen', methods=['GET'])
@login_required
def resumen_alertas():
    now_utc = _utc_now_naive()
    limit = min(max(request.args.get('limit', 50, type=int), 1), 200)

    actividades = (
        AgendaActividad.query
        .options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.titulo,
                AgendaActividad.tipo,
                AgendaActividad.prioridad,
                AgendaActividad.estado,
                AgendaActividad.fecha_inicio,
                AgendaActividad.fecha_fin,
                AgendaActividad.recordatorio_minutos,
            )
        )
        .filter(AgendaActividad.estado == 'pendiente')
        .filter(_filtro_recordatorio_para_usuario(current_user.id_usuario))
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.desc())
        .all()
    )

    alert_items = []
    total_count = 0
    overdue_count = 0
    alert_count = 0
    next_check_at = None
    for actividad in actividades:
        next_change_at = _proximo_cambio_alerta_actividad(actividad, now_utc=now_utc)
        if next_change_at and (next_check_at is None or next_change_at < next_check_at):
            next_check_at = next_change_at

        item = _serializar_alerta_actividad(actividad, now_utc=now_utc)
        if not item:
            continue
        total_count += 1
        if item['estado_alerta'] == 'overdue':
            overdue_count += 1
        elif item['estado_alerta'] == 'alert':
            alert_count += 1
        alert_items.append(item)

    alert_items.sort(
        key=lambda item: (
            0 if item.get('estado_alerta') == 'overdue' else 1,
            item.get('trigger_at_utc') or item.get('fecha_inicio_utc') or '',
            str(item.get('titulo') or '').lower(),
            item.get('id') or 0,
        )
    )
    items = alert_items[:limit]

    return jsonify(
        {
            'count': total_count,
            'has_alerts': total_count > 0,
            'overdue_count': overdue_count,
            'alert_count': alert_count,
            'server_time_utc': f'{now_utc.isoformat()}Z',
            'next_check_at_utc': f'{next_check_at.isoformat()}Z' if next_check_at else None,
            'items': items,
        }
    )


@agenda_bp.route('/api/actividades/estado', methods=['GET'])
@login_required
def estado_actividades_lista():
    filtros = _resolver_filtros_lista_actividades()
    page = filtros['page']
    ids = _parse_user_ids_list(request.args.getlist('ids'))
    now_utc = _utc_now_naive()
    query_base = _construir_query_lista_actividades(filtros, include_options=False, include_sort=False)
    actividades_pagina = (
        _construir_query_lista_actividades(filtros, include_options=False)
        .options(load_only(AgendaActividad.id))
        .paginate(page=page, per_page=25, error_out=False)
    )
    page_ids = [actividad.id for actividad in actividades_pagina.items]
    query_ids = ids if ids else page_ids

    if not query_ids:
        return jsonify(
            {
                'items': [],
                'missing_ids': [],
                'page_ids': page_ids,
                'page': actividades_pagina.page,
                'pages': actividades_pagina.pages,
                'total': actividades_pagina.total,
                'server_time_utc': f'{now_utc.isoformat()}Z',
            }
        )

    actividades = (
        query_base
        .options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.estado,
                AgendaActividad.fecha_inicio,
                AgendaActividad.fecha_fin,
                AgendaActividad.recordatorio_minutos,
                AgendaActividad.updated_at,
            )
        )
        .filter(AgendaActividad.id.in_(query_ids))
        .all()
    )
    items = []
    visibles = set()
    for actividad in actividades:
        visibles.add(actividad.id)
        items.append(
            {
                'id': actividad.id,
                'estado': actividad.estado,
                'estado_alerta': _resolver_estado_alerta(actividad, now_utc=now_utc),
                'updated_at_utc': f'{actividad.updated_at.isoformat()}Z' if actividad.updated_at else None,
            }
        )
    missing_ids = [actividad_id for actividad_id in query_ids if actividad_id not in visibles]
    return jsonify(
        {
            'items': items,
            'missing_ids': missing_ids,
            'page_ids': page_ids,
            'page': actividades_pagina.page,
            'pages': actividades_pagina.pages,
            'total': actividades_pagina.total,
            'server_time_utc': f'{now_utc.isoformat()}Z',
        }
    )


@agenda_bp.route('/api/clientes/buscar', methods=['GET'])
@login_required
def buscar_clientes_relacion():
    q = (request.args.get('q') or '').strip()
    query = Cliente.query.options(
        load_only(
            Cliente.id_cliente,
            Cliente.nombre,
            Cliente.ruc_ci,
            Cliente.telefono,
            Cliente.email,
        )
    ).filter(Cliente.activo.is_(True))

    if q:
        query = query.filter(
            or_(
                Cliente.nombre.ilike(f'%{q}%'),
                Cliente.ruc_ci.ilike(f'%{q}%'),
                Cliente.telefono.ilike(f'%{q}%'),
            )
        )

    clientes = query.order_by(Cliente.nombre.asc()).limit(10).all()
    return jsonify({'items': [_serializar_cliente(cliente) for cliente in clientes]})


@agenda_bp.route('/api/ventas/buscar', methods=['GET'])
@login_required
def buscar_ventas_relacion():
    q = (request.args.get('q') or '').strip()
    cliente_id = request.args.get('cliente_id', type=int)

    query = (
        Venta.query.join(Cliente, Venta.id_cliente == Cliente.id_cliente)
        .options(
            load_only(
                Venta.id_venta,
                Venta.id_cliente,
                Venta.fecha_venta,
                Venta.total,
                Venta.estado,
                Venta.numero_comprobante,
            ),
            joinedload(Venta.cliente).load_only(
                Cliente.id_cliente,
                Cliente.nombre,
                Cliente.ruc_ci,
                Cliente.telefono,
                Cliente.email,
            ),
        )
        .filter(Cliente.activo.is_(True))
    )

    if cliente_id:
        query = query.filter(Venta.id_cliente == cliente_id)

    if q:
        condiciones = [
            cast(Venta.id_venta, String).ilike(f'%{q}%'),
            Cliente.nombre.ilike(f'%{q}%'),
            Cliente.ruc_ci.ilike(f'%{q}%'),
        ]
        if q.isdigit():
            condiciones.append(Venta.id_venta == int(q))
        if q:
            condiciones.append(Venta.numero_comprobante.ilike(f'%{q}%'))
        query = query.filter(or_(*condiciones))

    # Sin búsqueda explícita, devolvemos las ventas más recientes para usar como sugerencias iniciales.
    ventas = query.order_by(Venta.fecha_venta.desc(), Venta.id_venta.desc()).limit(10).all()
    return jsonify({'items': [_serializar_venta(venta) for venta in ventas]})


@agenda_bp.route('/api/reparaciones/buscar', methods=['GET'])
@login_required
def buscar_reparaciones_relacion():
    q = (request.args.get('q') or '').strip()
    cliente_id = request.args.get('cliente_id', type=int)

    query = (
        Reparacion.query.join(Cliente, Reparacion.cliente_id == Cliente.id_cliente)
        .options(
            load_only(
                Reparacion.id_reparacion,
                Reparacion.cliente_id,
                Reparacion.tipo_equipo,
                Reparacion.marca_modelo,
                Reparacion.estado,
                Reparacion.fecha_ingreso,
            ),
            joinedload(Reparacion.cliente).load_only(
                Cliente.id_cliente,
                Cliente.nombre,
                Cliente.ruc_ci,
                Cliente.telefono,
                Cliente.email,
            ),
        )
        .filter(Cliente.activo.is_(True))
    )

    if cliente_id:
        query = query.filter(Reparacion.cliente_id == cliente_id)

    if q:
        condiciones = [
            cast(Reparacion.id_reparacion, String).ilike(f'%{q}%'),
            Reparacion.tipo_equipo.ilike(f'%{q}%'),
            Reparacion.marca_modelo.ilike(f'%{q}%'),
            Cliente.nombre.ilike(f'%{q}%'),
        ]
        if q.isdigit():
            condiciones.append(Reparacion.id_reparacion == int(q))
        query = query.filter(or_(*condiciones))

    reparaciones = query.order_by(Reparacion.fecha_ingreso.desc(), Reparacion.id_reparacion.desc()).limit(10).all()
    return jsonify({'items': [_serializar_reparacion(reparacion) for reparacion in reparaciones]})


@agenda_bp.route('/actividades/nueva', methods=['GET', 'POST'])
@login_required
def nueva_actividad():
    if not current_user.tiene_permiso('agenda_crear'):
        flash('No tienes permiso para crear actividades.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    usuarios, contactos = _obtener_opciones_formulario()
    cliente_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales()
    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        tipo = (request.form.get('tipo') or '').strip().lower() or 'tarea_interna'
        prioridad = (request.form.get('prioridad') or '').strip().lower() or 'media'
        fecha_inicio = _parse_datetime_local(request.form.get('fecha_inicio'))
        fecha_fin = _parse_datetime_local(request.form.get('fecha_fin'))
        recordatorio_minutos = _parse_optional_int(request.form.get('recordatorio_minutos'))
        cliente_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales(data=request.form)
        mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids = _resolver_destinatarios_formulario(data=request.form)
        error_destinatarios = _validar_destinatarios(
            mostrar_agenda_en,
            usuarios_agenda_ids,
            recordatorio_a,
            usuarios_recordatorio_ids,
        )
        error_temporalidad = _validar_temporalidad_actividad(fecha_inicio, fecha_fin, recordatorio_minutos)

        if not titulo or not fecha_inicio or error_destinatarios or error_temporalidad:
            if error_destinatarios:
                flash(error_destinatarios, 'warning')
            elif error_temporalidad:
                flash(error_temporalidad, 'warning')
            else:
                flash('Título y fecha de inicio son obligatorios.', 'warning')
            return _render_formulario_actividad(
                modo='crear',
                actividad=None,
                data=request.form,
                usuarios=usuarios,
                contactos=contactos,
                cliente_inicial=cliente_inicial,
                reparacion_inicial=reparacion_inicial,
                venta_inicial=venta_inicial,
            )

        usuario_id = request.form.get('usuario_id', type=int) or current_user.id_usuario
        if not _puede_ver_todo():
            usuario_id = current_user.id_usuario

        actividad = AgendaActividad(
            titulo=titulo,
            tipo=tipo if tipo in TIPOS_ACTIVIDAD else 'tarea_interna',
            descripcion=(request.form.get('descripcion') or '').strip() or None,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado='pendiente',
            prioridad=prioridad if prioridad in PRIORIDADES_ACTIVIDAD else 'media',
            usuario_id=usuario_id,
            creado_por_id=current_user.id_usuario,
            cliente_id=_parse_optional_int(request.form.get('cliente_id')),
            reparacion_id=_parse_optional_int(request.form.get('reparacion_id')),
            venta_id=_parse_optional_int(request.form.get('venta_id')),
            crm_contacto_id=_parse_optional_int(request.form.get('crm_contacto_id')),
            origen_modulo='agenda',
            recordatorio_minutos=recordatorio_minutos,
            es_todo_el_dia=bool(request.form.get('es_todo_el_dia')),
            observaciones=(request.form.get('observaciones') or '').strip() or None,
        )
        _aplicar_destinatarios_a_actividad(
            actividad,
            mostrar_agenda_en,
            usuarios_agenda_ids,
            recordatorio_a,
            usuarios_recordatorio_ids,
        )
        db.session.add(actividad)
        db.session.commit()
        flash('Actividad creada correctamente.', 'success')
        return redirect(url_for('agenda.lista_actividades'))

    return _render_formulario_actividad(
        modo='crear',
        actividad=None,
        data={},
        usuarios=usuarios,
        contactos=contactos,
        cliente_inicial=cliente_inicial,
        reparacion_inicial=reparacion_inicial,
        venta_inicial=venta_inicial,
    )


@agenda_bp.route('/actividades/<int:id_actividad>/editar', methods=['GET', 'POST'])
@login_required
def editar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_editar'):
        flash('No tienes permiso para editar actividades.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    actividad = _cargar_actividad_visible_o_404(id_actividad)
    usuarios, contactos = _obtener_opciones_formulario()
    cliente_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales(actividad=actividad)

    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        fecha_inicio = _parse_datetime_local(request.form.get('fecha_inicio'))
        fecha_fin = _parse_datetime_local(request.form.get('fecha_fin'))
        recordatorio_minutos = _parse_optional_int(request.form.get('recordatorio_minutos'))
        cliente_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales(data=request.form, actividad=actividad)
        mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids = _resolver_destinatarios_formulario(data=request.form)
        error_destinatarios = _validar_destinatarios(
            mostrar_agenda_en,
            usuarios_agenda_ids,
            recordatorio_a,
            usuarios_recordatorio_ids,
        )
        error_temporalidad = _validar_temporalidad_actividad(fecha_inicio, fecha_fin, recordatorio_minutos)
        if not titulo or not fecha_inicio or error_destinatarios or error_temporalidad:
            if error_destinatarios:
                flash(error_destinatarios, 'warning')
            elif error_temporalidad:
                flash(error_temporalidad, 'warning')
            else:
                flash('Título y fecha de inicio son obligatorios.', 'warning')
            return _render_formulario_actividad(
                modo='editar',
                actividad=actividad,
                data=request.form,
                usuarios=usuarios,
                contactos=contactos,
                cliente_inicial=cliente_inicial,
                reparacion_inicial=reparacion_inicial,
                venta_inicial=venta_inicial,
            )

        actividad.titulo = titulo
        actividad.tipo = (request.form.get('tipo') or '').strip().lower() or actividad.tipo
        if actividad.tipo not in TIPOS_ACTIVIDAD:
            actividad.tipo = 'tarea_interna'
        actividad.descripcion = (request.form.get('descripcion') or '').strip() or None
        actividad.fecha_inicio = fecha_inicio
        actividad.fecha_fin = fecha_fin
        actividad.prioridad = (request.form.get('prioridad') or '').strip().lower() or actividad.prioridad
        if actividad.prioridad not in PRIORIDADES_ACTIVIDAD:
            actividad.prioridad = 'media'
        if _puede_ver_todo():
            actividad.usuario_id = request.form.get('usuario_id', type=int) or actividad.usuario_id
        actividad.cliente_id = _parse_optional_int(request.form.get('cliente_id'))
        actividad.reparacion_id = _parse_optional_int(request.form.get('reparacion_id'))
        actividad.venta_id = _parse_optional_int(request.form.get('venta_id'))
        actividad.crm_contacto_id = _parse_optional_int(request.form.get('crm_contacto_id'))
        actividad.recordatorio_minutos = recordatorio_minutos
        actividad.es_todo_el_dia = bool(request.form.get('es_todo_el_dia'))
        actividad.observaciones = (request.form.get('observaciones') or '').strip() or None
        _aplicar_destinatarios_a_actividad(
            actividad,
            mostrar_agenda_en,
            usuarios_agenda_ids,
            recordatorio_a,
            usuarios_recordatorio_ids,
        )
        db.session.commit()
        flash('Actividad actualizada correctamente.', 'success')
        return redirect(url_for('agenda.lista_actividades'))

    return _render_formulario_actividad(
        modo='editar',
        actividad=actividad,
        data={},
        usuarios=usuarios,
        contactos=contactos,
        cliente_inicial=cliente_inicial,
        reparacion_inicial=reparacion_inicial,
        venta_inicial=venta_inicial,
    )


@agenda_bp.post('/actividades/<int:id_actividad>/completar')
@login_required
def completar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_completar'):
        mensaje = 'No tienes permiso para completar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(url_for('agenda.lista_actividades'))
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    estado_alerta = _resolver_estado_alerta(actividad)
    actividad.estado = 'hecha'
    db.session.commit()
    mensaje = 'Actividad marcada como hecha.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad.id, 'estado_alerta': estado_alerta, 'estado': actividad.estado})
    flash(mensaje, 'success')
    return redirect(url_for('agenda.lista_actividades'))


@agenda_bp.post('/actividades/<int:id_actividad>/cancelar')
@login_required
def cancelar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_cancelar'):
        mensaje = 'No tienes permiso para cancelar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(url_for('agenda.lista_actividades'))
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    estado_alerta = _resolver_estado_alerta(actividad)
    actividad.estado = 'cancelada'
    db.session.commit()
    mensaje = 'Actividad cancelada.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad.id, 'estado_alerta': estado_alerta, 'estado': actividad.estado})
    flash(mensaje, 'success')
    return redirect(url_for('agenda.lista_actividades'))


@agenda_bp.post('/actividades/<int:id_actividad>/eliminar')
@login_required
def eliminar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_cancelar'):
        mensaje = 'No tienes permiso para eliminar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(url_for('agenda.lista_actividades'))
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    estado_alerta = _resolver_estado_alerta(actividad)
    actividad_id = actividad.id
    _limpiar_destinatarios_actividad(actividad)
    db.session.flush()
    db.session.delete(actividad)
    db.session.commit()
    mensaje = 'Actividad eliminada.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad_id, 'estado_alerta': estado_alerta, 'estado': 'eliminada', 'eliminada': True})
    flash(mensaje, 'success')
    return redirect(url_for('agenda.lista_actividades'))


@agenda_bp.post('/actividades/<int:id_actividad>/reprogramar')
@login_required
def reprogramar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_editar'):
        flash('No tienes permiso para reprogramar actividades.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    fecha_inicio = _parse_datetime_local(request.form.get('fecha_inicio'))
    if not fecha_inicio:
        flash('La nueva fecha de inicio es obligatoria.', 'warning')
        return redirect(url_for('agenda.lista_actividades'))
    actividad.fecha_inicio = fecha_inicio
    actividad.estado = 'pendiente'
    db.session.commit()
    flash('Actividad reprogramada.', 'success')
    return redirect(url_for('agenda.lista_actividades'))
