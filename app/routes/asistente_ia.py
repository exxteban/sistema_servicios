from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.services.ia_backoffice.audit import (
    buscar_historial_interacciones,
    obtener_historial_interaccion,
    obtener_consumo_tokens,
    obtener_consumo_tokens_por_usuario,
    registrar_interaccion,
)
from app.services.ia_backoffice.acciones import (
    confirmar_accion_asistida,
    preparar_accion_asistida,
    preparar_accion_desde_chat,
)
from app.services.ia_backoffice.history import compactar_historial
from app.services.ia_backoffice.limits import obtener_rangos_presupuesto
from app.services.ia_backoffice.response_engine import generar_respuesta_backoffice
from app.services.ia_backoffice.security import puede_gestionar_asistente_ia, puede_usar_asistente_ia
from app.services.ia_backoffice.settings import obtener_configuracion_asistente


asistente_ia_bp = Blueprint('asistente_ia', __name__, url_prefix='/asistente-ia')
SESSION_HISTORY_KEY = 'ia_backoffice_historial'
SESSION_HISTORY_SUMMARY_KEY = 'ia_backoffice_historial_resumen'
MAX_SESSION_MESSAGES = 12


def _historial() -> list[dict]:
    historial = session.get(SESSION_HISTORY_KEY, [])
    if not isinstance(historial, list):
        return []
    return [item for item in historial if isinstance(item, dict)][-MAX_SESSION_MESSAGES:]


def _guardar_historial(historial: list[dict]) -> None:
    antiguos = historial[:-MAX_SESSION_MESSAGES]
    if antiguos:
        session[SESSION_HISTORY_SUMMARY_KEY] = compactar_historial(
            session.get(SESSION_HISTORY_SUMMARY_KEY, ''),
            antiguos,
        )
    session[SESSION_HISTORY_KEY] = historial[-MAX_SESSION_MESSAGES:]
    session.modified = True


def _resumen_historial() -> str:
    resumen = session.get(SESSION_HISTORY_SUMMARY_KEY, '')
    return resumen if isinstance(resumen, str) else ''


def _bloqueo(mensaje: str, status: int = 403):
    if request.path.startswith('/asistente-ia/api/') or request.is_json:
        return jsonify({'ok': False, 'error': 'sin_permisos', 'mensaje': mensaje}), status
    flash(mensaje, 'danger')
    return redirect(url_for('main.dashboard'))


def _top_n_request(default: int = 10, maximo: int = 100) -> int:
    try:
        top_n = int(request.args.get('per_page') or request.args.get('top_n') or default)
    except Exception:
        top_n = default
    return max(1, min(top_n, maximo))


def _page_request(default: int = 1) -> int:
    try:
        return max(1, int(request.args.get('page') or default))
    except Exception:
        return default


def _consumo_diario_usuario(usuario) -> dict:
    cfg = obtener_configuracion_asistente()
    rangos = obtener_rangos_presupuesto()
    consumo = obtener_consumo_tokens(rangos['dia']['desde'], rangos['dia']['hasta'], usuario=usuario)
    limite = int(cfg.daily_token_budget or 0)
    usado = int(consumo.get('tokens_total') or 0)
    restante = max(limite - usado, 0) if limite else None
    porcentaje = min(round((usado / limite) * 100, 2), 100) if limite else 0
    return {
        'limite': limite,
        'usado': usado,
        'restante': restante,
        'porcentaje': porcentaje,
        'sin_limite': limite == 0,
    }


@asistente_ia_bp.route('/')
@login_required
def chat():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    cfg = obtener_configuracion_asistente()
    return render_template(
        'asistente_ia/chat.html',
        cfg=cfg,
        historial=_historial(),
        puede_gestionar=puede_gestionar_asistente_ia(current_user),
        consumo_diario=_consumo_diario_usuario(current_user),
    )


@asistente_ia_bp.route('/admin')
@login_required
def admin():
    if not puede_gestionar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para gestionar el asistente IA interno.')
    return render_template(
        'asistente_ia/admin.html',
        cfg=obtener_configuracion_asistente(),
    )


@asistente_ia_bp.route('/historial')
@login_required
def historial():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    return render_template('asistente_ia/historial.html')


@asistente_ia_bp.route('/historial/<int:id_audit>')
@login_required
def historial_detalle(id_audit: int):
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    detalle = obtener_historial_interaccion(id_audit)
    if detalle is None:
        flash('Interaccion no encontrada.', 'warning')
        return redirect(url_for('asistente_ia.historial'))
    return render_template('asistente_ia/historial_detalle.html', item=detalle)


@asistente_ia_bp.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')

    data = request.get_json(silent=True) or {}
    pregunta = (data.get('mensaje') or data.get('pregunta') or '').strip()
    if not pregunta:
        return jsonify({'ok': False, 'error': 'mensaje_requerido', 'mensaje': 'Escribi una consulta.'}), 400
    if len(pregunta) > 1200:
        return jsonify({'ok': False, 'error': 'mensaje_largo', 'mensaje': 'La consulta es demasiado larga.'}), 400

    historial = _historial()
    historial.append({'role': 'user', 'content': pregunta})
    respuesta = generar_respuesta_backoffice(historial, current_user, resumen_historial=_resumen_historial())
    contenido = (respuesta.get('contenido') or '').strip()
    historial.append({'role': 'assistant', 'content': contenido})
    _guardar_historial(historial)
    accion = preparar_accion_desde_chat(pregunta, contenido, current_user)

    registrar_interaccion(
        current_user,
        pregunta,
        contenido,
        modelo=respuesta.get('modelo') or '',
        provider=respuesta.get('provider') or '',
        estado=respuesta.get('estado') or 'ok',
        tools_usadas=respuesta.get('tools_usadas') or [],
        argumentos_normalizados=respuesta.get('argumentos_normalizados') or {},
        resultado_resumido=respuesta.get('resultado_resumido') or '',
        tokens_prompt=respuesta.get('tokens_prompt') or 0,
        tokens_completion=respuesta.get('tokens_completion') or 0,
    )
    return jsonify({
        'ok': True,
        'mensaje': contenido,
        'estado': respuesta.get('estado') or 'ok',
        'historial': historial[-MAX_SESSION_MESSAGES:],
        'accion': accion,
        'consumo_diario': _consumo_diario_usuario(current_user),
    })


@asistente_ia_bp.route('/api/limpiar', methods=['POST'])
@login_required
def api_limpiar():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    session.pop(SESSION_HISTORY_KEY, None)
    session.pop(SESSION_HISTORY_SUMMARY_KEY, None)
    session.modified = True
    return jsonify({'ok': True})


@asistente_ia_bp.route('/api/consumo')
@login_required
def api_consumo():
    if not puede_gestionar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para gestionar el asistente IA interno.')

    cfg = obtener_configuracion_asistente()
    rangos = obtener_rangos_presupuesto()
    consumo_dia = obtener_consumo_tokens(rangos['dia']['desde'], rangos['dia']['hasta'])
    consumo_mes = obtener_consumo_tokens(rangos['mes']['desde'], rangos['mes']['hasta'])
    usuarios_mes = obtener_consumo_tokens_por_usuario(
        rangos['mes']['desde'],
        rangos['mes']['hasta'],
        top_n=_top_n_request(),
    )
    return jsonify({
        'ok': True,
        'daily_token_budget': cfg.daily_token_budget,
        'monthly_token_budget': cfg.monthly_token_budget,
        'consumo_dia': consumo_dia,
        'consumo_mes': consumo_mes,
        'usuarios_mes': usuarios_mes,
    })


@asistente_ia_bp.route('/api/consumo-usuario')
@login_required
def api_consumo_usuario():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    return jsonify({'ok': True, 'consumo_diario': _consumo_diario_usuario(current_user)})


@asistente_ia_bp.route('/api/historial')
@login_required
def api_historial():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    return jsonify({
        'ok': True,
        **buscar_historial_interacciones(
            page=_page_request(),
            per_page=_top_n_request(default=20, maximo=50),
            username=request.args.get('username') or '',
            q=request.args.get('q') or '',
        ),
    })


@asistente_ia_bp.route('/api/historial/<int:id_audit>')
@login_required
def api_historial_detalle(id_audit: int):
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    detalle = obtener_historial_interaccion(id_audit)
    if detalle is None:
        return jsonify({'ok': False, 'error': 'no_encontrado', 'mensaje': 'Interaccion no encontrada.'}), 404
    return jsonify({'ok': True, 'item': detalle})


@asistente_ia_bp.route('/api/acciones/preparar', methods=['POST'])
@login_required
def api_acciones_preparar():
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    data = request.get_json(silent=True) or {}
    resultado = preparar_accion_asistida(data.get('tipo') or '', data.get('payload') or {}, current_user)
    if not resultado.get('ok'):
        status = 403 if resultado.get('error') in {
            'acciones_asistidas_deshabilitadas',
            'modo_solo_lectura_requerido',
        } else 400
        return jsonify(resultado), status
    return jsonify(resultado)


@asistente_ia_bp.route('/api/acciones/<int:id_accion>/confirmar', methods=['POST'])
@login_required
def api_acciones_confirmar(id_accion: int):
    if not puede_usar_asistente_ia(current_user):
        return _bloqueo('No tienes permiso para usar el asistente IA interno.')
    resultado = confirmar_accion_asistida(id_accion, current_user)
    if not resultado.get('ok'):
        status = 403 if resultado.get('error') in {
            'acciones_asistidas_deshabilitadas',
            'modo_solo_lectura_requerido',
            'sin_permiso_accion',
        } else 404
        return jsonify(resultado), status
    return jsonify(resultado)
