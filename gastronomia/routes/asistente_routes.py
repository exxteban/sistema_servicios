"""Asistente IA para configurar el local gastronomico (menu, insumos, recetas, mesas)."""
from flask import jsonify, redirect, request, session, url_for
from flask_login import current_user, login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia

# Clave vieja: el historial vivia en la cookie de sesion (limite ~4 KB). Se limpia si quedo.
SESSION_KEY_LEGADO = 'gastro_asistente_historial'
MAX_MENSAJE = 6000
ESTADOS_CON_RESPUESTA = {'ok', 'limite_rondas'}


@gastronomia_bp.app_template_global('gastro_asistente_visible')
def gastro_asistente_visible() -> bool:
    """Panel global: instalacion de gastronomia y usuario con permiso de Menu (el mismo que piden sus APIs)."""
    from gastronomia.services.modo_operacion import gastronomia_activa
    from gastronomia.services.permisos import tiene_permiso_gastronomia

    try:
        return bool(gastronomia_activa() and tiene_permiso_gastronomia(PERMISO_MENU))
    except Exception:  # noqa: BLE001 - nunca romper el layout por el asistente
        return False


@gastronomia_bp.app_template_global('asistente_ia_gestion')
def asistente_ia_gestion() -> bool:
    """Consumo, historial y panel de la IA: solo root."""
    from app.services.ia_backoffice.security import puede_gestionar_asistente_ia

    return puede_gestionar_asistente_ia(current_user)


def _usuario_id() -> int:
    return int(current_user.id_usuario)


def _limpiar_legado() -> None:
    if SESSION_KEY_LEGADO in session:
        session.pop(SESSION_KEY_LEGADO, None)
        session.modified = True


@gastronomia_bp.route('/asistente')
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def asistente_config():
    """El asistente vive como panel lateral del Menu; esta URL lo abre directamente."""
    return redirect(url_for('gastronomia.menu_config', asistente=1))


@gastronomia_bp.route('/asistente/api/historial', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def asistente_api_historial():
    from app.services.ia_backoffice.settings import obtener_configuracion_asistente
    from gastronomia.services.asistente import historial as historial_db

    from gastronomia.services.asistente import propuestas

    _limpiar_legado()
    cliente_id = cliente_id_actual_gastronomia()
    mensajes = historial_db.listar(cliente_id, _usuario_id()) if cliente_id else []
    return jsonify({
        'ok': True,
        'historial': [{'role': m['role'], 'content': m['content']} for m in mensajes],
        'ia_habilitada': bool(obtener_configuracion_asistente().enabled),
        'propuesta': propuestas.vigente(cliente_id, _usuario_id()) if cliente_id else None,
    })


@gastronomia_bp.route('/asistente/api/chat', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def asistente_api_chat():
    # Import diferido: el motor depende de app.models (evita import circular al cargar el paquete).
    from app.services.ia_backoffice.audit import registrar_interaccion
    from gastronomia.services.asistente.motor import generar_respuesta

    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'ok': False, 'mensaje': 'Gastronomia no esta activa.'}), 403
    data = request.get_json(silent=True) or {}
    pregunta = (data.get('mensaje') or '').strip()
    if not pregunta:
        return jsonify({'ok': False, 'mensaje': 'Escribi un mensaje.'}), 400
    if len(pregunta) > MAX_MENSAJE:
        return jsonify({'ok': False, 'mensaje': 'El mensaje es muy largo; mandalo en partes.'}), 400

    from gastronomia.services.asistente import historial as historial_db
    from gastronomia.services.asistente.contexto_pantalla import sanitizar_contexto

    _limpiar_legado()
    contexto = sanitizar_contexto(data.get('contexto'))
    historial = historial_db.listar(cliente_id, _usuario_id())
    historial.append({'role': 'user', 'content': pregunta, 'contexto': contexto})
    from gastronomia.services.asistente import propuestas

    respuesta = generar_respuesta(historial, int(cliente_id), current_user)
    contenido = respuesta.get('contenido') or ''
    acciones = respuesta.get('acciones') or []
    propuesta = None
    # Solo se guarda si la IA respondio de verdad: avisos de "desactivado"/error no son conversacion.
    if respuesta.get('estado') in ESTADOS_CON_RESPUESTA:
        historial_db.agregar(cliente_id, _usuario_id(), 'user', pregunta, contexto)
        historial_db.agregar(cliente_id, _usuario_id(), 'assistant', contenido)
        # Nada se guarda todavia: queda como propuesta hasta que el usuario toque Confirmar.
        if acciones:
            propuesta = propuestas.crear(cliente_id, _usuario_id(), acciones)

    registrar_interaccion(
        current_user,
        f'[gastronomia_config] {pregunta}',
        contenido,
        tools_usadas=respuesta.get('tools_usadas') or [],
        argumentos_normalizados={'propuesta': propuesta['id'] if propuesta else None,
                                 'acciones_propuestas': [{'tool': a['tool'], 'args': a['args']} for a in acciones]},
        tokens_prompt=respuesta.get('tokens_prompt') or 0,
        tokens_completion=respuesta.get('tokens_completion') or 0,
        modelo=respuesta.get('modelo') or '',
        provider=respuesta.get('provider') or '',
        estado=respuesta.get('estado') or 'ok',
    )
    return jsonify({
        'ok': True,
        'mensaje': contenido,
        'estado': respuesta.get('estado'),
        'hubo_cambios': False,
        'propuesta': propuesta,
    })


def _resolver_propuesta(propuesta_id: int, accion: str):
    from app.services.ia_backoffice.audit import registrar_interaccion
    from gastronomia.services.asistente import propuestas

    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'ok': False, 'mensaje': 'Gastronomia no esta activa.'}), 403
    if accion == 'confirmar':
        resultado = propuestas.confirmar(cliente_id, _usuario_id(), propuesta_id)
    else:
        resultado = propuestas.cancelar(cliente_id, _usuario_id(), propuesta_id)
    registrar_interaccion(
        current_user,
        f'[gastronomia_config] {accion} propuesta #{propuesta_id}',
        resultado.get('mensaje') or '',
        tools_usadas=[d['tool'] for d in resultado.get('detalle') or []],
        argumentos_normalizados={'propuesta': propuesta_id, 'acciones': resultado.get('detalle') or []},
        estado=accion if resultado.get('ok') else 'propuesta_no_vigente',
    )
    status = 200 if resultado.get('ok') else 409
    return jsonify({k: v for k, v in resultado.items() if k != 'detalle'}), status


@gastronomia_bp.route('/asistente/api/propuesta/<int:propuesta_id>/confirmar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def asistente_api_confirmar(propuesta_id: int):
    """Unico camino por el que el asistente guarda cambios: el usuario toca Confirmar."""
    return _resolver_propuesta(propuesta_id, 'confirmar')


@gastronomia_bp.route('/asistente/api/propuesta/<int:propuesta_id>/cancelar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def asistente_api_cancelar(propuesta_id: int):
    return _resolver_propuesta(propuesta_id, 'cancelar')


@gastronomia_bp.route('/asistente/api/limpiar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def asistente_api_limpiar():
    """Olvida toda la conversacion: el modelo solo recibe lo guardado en este historial."""
    from gastronomia.services.asistente import historial as historial_db

    _limpiar_legado()
    cliente_id = cliente_id_actual_gastronomia()
    if cliente_id:
        from gastronomia.services.asistente import propuestas

        historial_db.limpiar(cliente_id, _usuario_id())
        propuestas.descartar_pendientes(cliente_id, _usuario_id(), estado='cancelada')
    return jsonify({'ok': True, 'historial': []})
