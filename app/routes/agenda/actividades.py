from datetime import datetime, timedelta, timezone

from flask import render_template, request
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, load_only

from app import db
from app.models import (
    AgendaActividad,
    Usuario,
)
from app.routes.agenda import agenda_bp
from app.routes.agenda.visibilidad import (
    filtro_mostrar_agenda_para_usuario,
    obtener_root_user_id_sistema,
    query_usuarios_agenda_visibles,
    usuarios_agenda_visibles_para,
)
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
    return filtro_mostrar_agenda_para_usuario(user_id)


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
        query_usuarios_agenda_visibles()
        .filter(Usuario.id_usuario.in_(ids))
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
        visible_query = query
    else:
        visible_query = query.filter(_filtro_mostrar_agenda_para_usuario(current_user.id_usuario))
    root_id = obtener_root_user_id_sistema()
    if root_id:
        visible_query = visible_query.filter(AgendaActividad.usuario_id != root_id)
    return visible_query


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


def _parse_positive_int(value):
    parsed = _parse_optional_int(value)
    return parsed if parsed and parsed > 0 else None


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

    responsables = usuarios_agenda_visibles_para(current_user, _puede_ver_todo())
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
