"""
Gestor de conversaciones WhatsApp.
Pipeline simplificado: webhook → guardar mensaje → verificar estado → IA → respuesta.
"""
import os
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta

from app import db
from app.models.whatsapp import WhatsAppConversacion, WhatsAppMensaje
from app.services.ia.gpt_service import generar_respuesta
from app.services.ia.tool_handlers import ejecutar_tool, obtener_contexto_cliente
from app.services.ia.prompts import (
    MENSAJE_RATE_LIMIT, MENSAJE_BLOQUEADO, MENSAJE_DERIVACION,
    MENSAJE_ASESOR_ASIGNADO, MENSAJE_VOLVER_BOT, MENSAJE_SIN_ASESOR,
)
from app.services.bot_context import load_bot_context
from app.services.web_bot.handoff_service import registrar_respuesta_asesor_en_web
from app.services.whatsapp.auditoria_service import registrar_evento_conversacion
from app.services.whatsapp import client as wa_client
from app.utils.phone_utils import normalizar_telefono

logger = logging.getLogger(__name__)

# Máximo de ciclos de tool_call para evitar loops infinitos
MAX_TOOL_CYCLES = 3


# ─── Helpers de configuración ────────────────────────────────────────────────

def _sesion_horas() -> int:
    return int(os.environ.get('WHATSAPP_SESION_HORAS', '24'))


def _rate_limit_por_telefono() -> int:
    return int(os.environ.get('WHATSAPP_RATE_LIMIT_PER_PHONE', '20'))


def _is_truthy_env(name: str, default: str = '0') -> bool:
    raw = os.environ.get(name, default)
    return (raw or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'si', 'sí'}


def _telefono_sin_plus(telefono: str) -> str:
    return (telefono or '').lstrip('+')


def _is_bot_globally_enabled() -> bool:
    from app.models.whatsapp import WhatsAppConfiguracion
    c = WhatsAppConfiguracion.query.filter_by(clave='bot_global_enabled').first()
    if not c or not c.valor:
        return True
    try:
        return bool(json.loads(c.valor))
    except Exception:
        return True


# ─── Conversación ────────────────────────────────────────────────────────────

def obtener_o_crear_conversacion(telefono: str, nombre_contacto: str = None) -> WhatsAppConversacion:
    """Obtiene la conversación activa o crea una nueva."""
    tel_norm = normalizar_telefono(telefono) or telefono
    ahora = datetime.utcnow()
    limite_sesion = ahora - timedelta(hours=_sesion_horas())

    conv = WhatsAppConversacion.query.filter(
        WhatsAppConversacion.telefono == tel_norm,
        WhatsAppConversacion.activa == True,
        WhatsAppConversacion.ultima_actividad >= limite_sesion
    ).first()

    if conv:
        conv.ultima_actividad = ahora
        if nombre_contacto and not conv.nombre_contacto:
            conv.nombre_contacto = nombre_contacto
        db.session.commit()
        return conv

    # Cerrar conversaciones anteriores expiradas
    WhatsAppConversacion.query.filter(
        WhatsAppConversacion.telefono == tel_norm,
        WhatsAppConversacion.activa == True
    ).update({'activa': False, 'fin_sesion': ahora})

    conv = WhatsAppConversacion(
        telefono=tel_norm,
        nombre_contacto=nombre_contacto,
        modo='bot',
        activa=True,
        inicio_sesion=ahora,
        ultima_actividad=ahora,
        contexto=json.dumps({}),
    )
    db.session.add(conv)
    db.session.commit()
    logger.info(f"Nueva conversación: id={conv.id} tel={tel_norm}")
    return conv


def _verificar_rate_limit(conv: WhatsAppConversacion) -> bool:
    """Retorna True si el rate limit fue excedido."""
    if _is_truthy_env('WHATSAPP_DISABLE_RATE_LIMIT', '0'):
        return False

    limite = _rate_limit_por_telefono()
    if limite <= 0:
        return False

    ahora = datetime.utcnow()
    if not conv.ultimo_reset_rate:
        conv.ultimo_reset_rate = ahora
        conv.mensajes_hora = 0
    if (ahora - conv.ultimo_reset_rate).total_seconds() >= 3600:
        conv.mensajes_hora = 0
        conv.ultimo_reset_rate = ahora

    conv.mensajes_hora = (conv.mensajes_hora or 0) + 1
    return conv.mensajes_hora > limite


def _verificar_bloqueo(conv: WhatsAppConversacion) -> bool:
    return bool(conv.bloqueado_hasta and conv.bloqueado_hasta > datetime.utcnow())


def _get_contexto(conv: WhatsAppConversacion) -> dict:
    try:
        return json.loads(conv.contexto or '{}')
    except (json.JSONDecodeError, TypeError):
        return {}


def _set_contexto(conv: WhatsAppConversacion, contexto: dict):
    conv.contexto = json.dumps(contexto, ensure_ascii=False, default=str)


def _guardar_mensaje(conv: WhatsAppConversacion, direccion: str, remitente: str,
                     contenido: str, tipo_mensaje: str = 'text',
                     wa_message_id: str = None, id_asesor: int = None,
                     tool_call: dict = None, media_url: str = None) -> WhatsAppMensaje:
    msg = WhatsAppMensaje(
        id_conversacion=conv.id,
        direccion=direccion,
        remitente=remitente,
        tipo_mensaje=tipo_mensaje,
        contenido=contenido,
        media_url=media_url,
        wa_message_id=wa_message_id,
        id_asesor=id_asesor,
        tool_call=json.dumps(tool_call, ensure_ascii=False, default=str) if tool_call else None,
        created_at=datetime.utcnow(),
    )
    db.session.add(msg)
    return msg


def _construir_historial_ia(conv: WhatsAppConversacion) -> list[dict]:
    """
    Construye el historial de mensajes en formato OpenAI.
    Solo incluye mensajes recientes y relevantes.
    Cuando hay imágenes, inyecta el análisis de visión como descripción
    para que DeepSeek pueda razonar sobre el producto identificado.
    """
    # Mensajes de error/sistema que NO deben ir al historial de la IA
    _MSGS_ERROR = {
        'el asistente no está disponible en este momento. por favor intentá más tarde.',
        'el asistente no esta disponible en este momento. por favor intenta mas tarde.',
        'hubo un error procesando tu consulta. ¿querés que te comunique con un asesor?',
        'hubo un error procesando tu consulta. queres que te comunique con un asesor?',
        'no entendí bien tu consulta. ¿podés decirme con más detalle qué necesitás?',
        '[tool_call]',
        '[tool_result]',
    }

    # IMPORTANTE: Usar query directa en lugar de la relación dinámica para evitar
    # el bug de SQLAlchemy donde order_by() apila sobre el orden existente de la relación.
    # La relación tiene order_by='created_at' (ASC), y sobrescribir con .desc() no funciona.
    mensajes = WhatsAppMensaje.query.filter_by(
        id_conversacion=conv.id
    ).order_by(WhatsAppMensaje.created_at.asc(), WhatsAppMensaje.id.asc()).all()

    # Tomar los últimos 40 mensajes (más recientes)
    if len(mensajes) > 40:
        mensajes = mensajes[-40:]

    # Precargar el contexto para acceder al análisis de visión de imágenes
    contexto_conv = _get_contexto(conv)

    historial = []
    for msg in mensajes:
        if msg.remitente == 'cliente':
            contenido_usuario = msg.contenido or ''

            # Si el mensaje es una imagen, enriquecer con el análisis de visión
            if msg.tipo_mensaje == 'image':
                contenido_usuario = _enriquecer_mensaje_imagen(contenido_usuario, msg, contexto_conv)

            historial.append({'role': 'user', 'content': contenido_usuario})

        elif msg.remitente == 'bot':
            if msg.tool_call:
                try:
                    tc_data = json.loads(msg.tool_call)
                    if tc_data.get('raw_message'):
                        historial.append(tc_data['raw_message'])
                    elif tc_data.get('tool_result') is not None:
                        tool_call_id = tc_data.get('tool_call_id', '')
                        if tool_call_id:
                            historial.append({
                                'role': 'tool',
                                'tool_call_id': tool_call_id,
                                'content': json.dumps(tc_data['tool_result'], ensure_ascii=False, default=str),
                            })
                except (json.JSONDecodeError, TypeError):
                    pass
            else:
                contenido = (msg.contenido or '').strip()
                # Excluir mensajes de error/sistema que contaminan el contexto
                contenido_lower = contenido.lower()
                is_system_msg = False
                if contenido_lower in _MSGS_ERROR:
                    is_system_msg = True
                elif 'tu consulta está en cola' in contenido_lower or 'tu consulta esta en cola' in contenido_lower:
                    is_system_msg = True
                elif 'te voy a comunicar con un asesor' in contenido_lower:
                    is_system_msg = True
                elif 'en este momento no hay asesores disponibles' in contenido_lower:
                    is_system_msg = True
                elif 'ya puede escribirte' in contenido_lower and 'te atiende' in contenido_lower:
                    is_system_msg = True
                elif 'el asesor cerró la conversación' in contenido_lower or 'el asesor cerro la conversacion' in contenido_lower:
                    is_system_msg = True

                if contenido and not is_system_msg:
                    historial.append({'role': 'assistant', 'content': contenido})

    # Limitar a los últimos 20 intercambios
    if len(historial) > 20:
        historial = historial[-20:]

    return historial


def _enriquecer_mensaje_imagen(caption: str, msg: 'WhatsAppMensaje', contexto_conv: dict) -> str:
    """
    Dado un mensaje de imagen, retorna el texto enriquecido con el análisis de visión
    para que DeepSeek pueda usarlo como contexto al generar la respuesta.
    Busca el análisis en el contexto de la conversación (ultimo_media.vision).
    """
    ultimo_media = contexto_conv.get('ultimo_media') or {}
    vision = ultimo_media.get('vision') or {}

    # Verificar que el análisis guardado corresponde a ESTE mensaje (por media_id)
    media_id_guardado = ultimo_media.get('media_id') or ''
    media_id_msg = (msg.media_url or '').replace('media_id:', '').strip()
    if media_id_guardado and media_id_msg and media_id_guardado != media_id_msg:
        # Este mensaje de imagen no tiene análisis (es uno anterior)
        return caption or '[El cliente envió una imagen]'

    # Solo inyectar si el análisis fue exitoso y tiene datos del item
    if not isinstance(vision, dict) or not vision.get('ok'):
        texto = caption or '[El cliente envió una imagen]'
        return texto

    item = vision.get('item') if isinstance(vision.get('item'), dict) else {}
    categoria = (item.get('categoria') or '').strip()
    marca = (item.get('marca') or '').strip()
    modelo = (item.get('modelo') or '').strip()
    nombre_comercial = (item.get('nombre_comercial') or '').strip()
    texto_en_imagen = (vision.get('texto_en_imagen') or '').strip()
    atributos = vision.get('atributos') if isinstance(vision.get('atributos'), dict) else {}
    color = (atributos.get('color') or '').strip()
    material = (atributos.get('material') or '').strip()
    palabras = vision.get('palabras_clave_busqueda') or []
    alternativas = vision.get('alternativas') or []
    notas = (vision.get('notas') or '').strip()

    conf = vision.get('confianza') if isinstance(vision.get('confianza'), dict) else {}
    conf_global = conf.get('global', 0)
    try:
        conf_global = float(conf_global)
    except Exception:
        conf_global = 0.0

    # Construir descripción del objeto identificado
    piezas_objeto = []
    if categoria:
        piezas_objeto.append(categoria)
    if marca:
        piezas_objeto.append(marca)
    if modelo:
        piezas_objeto.append(modelo)
    if nombre_comercial and nombre_comercial not in piezas_objeto:
        piezas_objeto.append(nombre_comercial)
    objeto_desc = ' '.join(piezas_objeto).strip() or 'objeto no identificado'

    # Construir línea de atributos
    attrs = []
    if color:
        attrs.append(f'color: {color}')
    if material:
        attrs.append(f'material: {material}')
    if texto_en_imagen:
        attrs.append(f'texto visible: "{texto_en_imagen}"')
    attrs_str = (', '.join(attrs) + '.') if attrs else ''

    # Construir texto de alternativas
    alt_str = ''
    if alternativas:
        alt_parts = []
        for alt in alternativas[:2]:
            if isinstance(alt, dict) and alt.get('posible'):
                alt_parts.append(alt['posible'])
        if alt_parts:
            alt_str = f' Posibles alternativas: {", ".join(alt_parts)}.'

    # Palabras clave
    kw_str = ''
    if palabras:
        kw_str = f' Términos de búsqueda sugeridos: {", ".join(str(k) for k in palabras[:6])}.'

    # Nivel de confianza
    if conf_global >= 0.7:
        confianza_txt = 'con alta confianza'
    elif conf_global >= 0.4:
        confianza_txt = 'con confianza moderada'
    else:
        confianza_txt = 'con baja confianza'

    caption_txt = f' El cliente dice: "{caption}".' if caption else ''

    descripcion_vision = (
        f'[ANÁLISIS DE IMAGEN - identificado {confianza_txt}]: '
        f'El objeto en la imagen es un/a {objeto_desc}{(". " + attrs_str) if attrs_str else "."}'
        f'{alt_str}{kw_str}'
        f'{(". Notas: " + notas) if notas else ""}'
        f'{caption_txt}'
        f' Usá esta información para buscar el producto en el catálogo y responder al cliente.'
    )

    return descripcion_vision


def _es_primera_interaccion(conv: WhatsAppConversacion) -> bool:
    """Verifica si es el primer mensaje entrante de esta sesión."""
    count = conv.mensajes.filter_by(direccion='entrante').count()
    return count <= 1  # El mensaje actual ya fue guardado


def _cliente_pide_asesor(texto: str) -> bool:
    """Detección rápida de pedido de asesor humano."""
    t = (texto or '').strip().lower()
    
    # Prevenir falsos positivos
    negaciones = ('no quiero', 'no necesito', 'no me pases', 'no hace falta', 'no ')
    if any(n in t for n in negaciones) and 'asesor' in t:
        return False
        
    keywords = ('asesor', 'humano', 'persona', 'operador', 'representante',
                'hablar con alguien', 'hablar con una persona', 'pasame', 'pásame')
    return any(k in t for k in keywords)


def _normalizar_texto_simple(texto: str) -> str:
    t = (texto or '').strip().lower()
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r'\s+', ' ', t)
    return t


def _cliente_confirma_derivacion(texto: str) -> bool:
    t = _normalizar_texto_simple(texto)
    if not t:
        return False

    if t in {'s', 'si', 'sí', 'ok', 'okay', 'dale', 'de una', 'claro', 'listo', 'por favor', 'confirmo'}:
        return True

    if t.startswith('si '):
        return True
    if t.startswith('sí '):
        return True
    if t.startswith('ok '):
        return True
    if t.startswith('dale '):
        return True

    return False


def _cliente_rechaza_derivacion(texto: str) -> bool:
    t = _normalizar_texto_simple(texto)
    if not t:
        return False

    if t in {'no', 'no gracias', 'nop', 'nah'}:
        return True

    if t.startswith('no '):
        return True

    return False


def _bot_pregunto_derivacion(conv: WhatsAppConversacion) -> bool:
    last_bot = WhatsAppMensaje.query.filter_by(
        id_conversacion=conv.id,
        direccion='saliente',
        remitente='bot',
    ).order_by(WhatsAppMensaje.created_at.desc(), WhatsAppMensaje.id.desc()).first()

    if not last_bot or not last_bot.contenido:
        return False

    t = _normalizar_texto_simple(last_bot.contenido)
    return (
        'queres que te comunique con un asesor' in t
        or 'queres que te comunique con un asesor?' in t
        or 'queres que te comunique con un asesor' in t
        or 'queres que te comunique con una persona' in t
        or 'queres hablar con un asesor' in t
        or 'queres hablar con alguien' in t
    )


def _marcar_pendiente_derivacion(conv: WhatsAppConversacion, contexto: dict):
    contexto['pendiente_derivacion'] = True
    contexto['pendiente_derivacion_at'] = datetime.utcnow().isoformat()
    _set_contexto(conv, contexto)


def _limpiar_pendiente_derivacion(conv: WhatsAppConversacion, contexto: dict):
    if 'pendiente_derivacion' in contexto:
        contexto.pop('pendiente_derivacion', None)
    if 'pendiente_derivacion_at' in contexto:
        contexto.pop('pendiente_derivacion_at', None)
    _set_contexto(conv, contexto)


# ─── Punto de entrada principal ──────────────────────────────────────────────

def procesar_mensaje_entrante(telefono: str, texto: str, nombre_contacto: str = None,
                               wa_message_id: str = None, tipo_mensaje: str = 'text',
                               media_id: str | None = None, media_mime_type: str | None = None) -> str | None:
    """
    Procesa un mensaje entrante de WhatsApp.
    Retorna el texto de respuesta (o None si no debe responder).
    """
    conv = obtener_o_crear_conversacion(telefono, nombre_contacto)
    tel_envio = _telefono_sin_plus(conv.telefono)

    # Marcar como leído
    if wa_message_id:
        wa_client.marcar_leido(wa_message_id)

    # Guardar mensaje entrante
    msg_entrante = _guardar_mensaje(
        conv,
        'entrante',
        'cliente',
        texto,
        tipo_mensaje,
        wa_message_id,
        media_url=(f'media_id:{media_id}' if media_id else None),
    )
    db.session.commit()

    try:
        from app.services.web_bot.handoff_service import consumir_handoff_desde_whatsapp
        handoff = consumir_handoff_desde_whatsapp(conv, texto)
        if handoff:
            registrar_evento_conversacion(conv, 'handoff_web_consumido', detalle=handoff)
        db.session.commit()
    except Exception as exc:
        logger.warning("No se pudo vincular handoff web->WhatsApp para conv=%s: %s", conv.id, exc)

    # Auto-crear/actualizar contacto CRM
    _sincronizar_contacto_crm(conv)

    # Verificar toggle global del bot
    if not _is_bot_globally_enabled():
        logger.info(f"Bot global desactivado. Mensaje de conv={conv.id} va a bandeja sin respuesta.")
        if conv.modo == 'bot':
            conv.modo = 'derivacion'
            db.session.commit()
        return None

    # Verificar bloqueo
    if _verificar_bloqueo(conv):
        minutos = int((conv.bloqueado_hasta - datetime.utcnow()).total_seconds() / 60) + 1
        respuesta = MENSAJE_BLOQUEADO.format(minutos=minutos)
        _guardar_mensaje(conv, 'saliente', 'bot', respuesta)
        db.session.commit()
        wa_client.enviar_texto(tel_envio, respuesta)
        return respuesta

    # Verificar rate limit
    if _verificar_rate_limit(conv):
        db.session.commit()
        _guardar_mensaje(conv, 'saliente', 'bot', MENSAJE_RATE_LIMIT)
        db.session.commit()
        wa_client.enviar_texto(tel_envio, MENSAJE_RATE_LIMIT)
        return MENSAJE_RATE_LIMIT

    db.session.commit()

    contexto_confirm = _get_contexto(conv)
    pendiente = bool(contexto_confirm.get('pendiente_derivacion'))
    if pendiente:
        try:
            at_raw = contexto_confirm.get('pendiente_derivacion_at')
            if at_raw:
                at = datetime.fromisoformat(at_raw)
                if (datetime.utcnow() - at).total_seconds() > 15 * 60:
                    pendiente = False
                    _limpiar_pendiente_derivacion(conv, contexto_confirm)
                    db.session.commit()
        except Exception:
            pendiente = False
            _limpiar_pendiente_derivacion(conv, contexto_confirm)
            db.session.commit()

    if conv.modo == 'bot' and (pendiente or _bot_pregunto_derivacion(conv)):
        if _cliente_confirma_derivacion(texto):
            _limpiar_pendiente_derivacion(conv, contexto_confirm)
            db.session.commit()

            from app.services.whatsapp.asignacion_service import asignar_conversacion
            resultado = asignar_conversacion(conv.id, 'Confirmación del cliente', 'normal')
            respuesta = (resultado.get('mensaje') or MENSAJE_DERIVACION).strip()
            _guardar_mensaje(conv, 'saliente', 'bot', respuesta)
            db.session.commit()
            wa_client.enviar_texto(tel_envio, respuesta)
            return respuesta

        if _cliente_rechaza_derivacion(texto):
            _limpiar_pendiente_derivacion(conv, contexto_confirm)
            db.session.commit()
            respuesta = 'Perfecto. Contame qué necesitás y te ayudo por acá.'
            _guardar_mensaje(conv, 'saliente', 'bot', respuesta)
            db.session.commit()
            wa_client.enviar_texto(tel_envio, respuesta)
            return respuesta

    # Modo asesor: el asesor responde desde el panel, el bot no interviene
    if conv.modo == 'asesor':
        logger.info(f"Mensaje en modo asesor, bot no responde: conv={conv.id}")
        return None

    # Modo derivación: en espera de asesor
    if conv.modo == 'derivacion':
        respuesta = "Tu consulta está en cola. Un asesor te va a atender en breve. ⏳"
        _guardar_mensaje(conv, 'saliente', 'bot', respuesta)
        db.session.commit()
        wa_client.enviar_texto(tel_envio, respuesta)
        return respuesta

    # Modo bot: verificar si el cliente pide asesor explícitamente
    if conv.modo == 'bot' and _cliente_pide_asesor(texto):
        from app.services.whatsapp.asignacion_service import asignar_conversacion
        resultado = asignar_conversacion(conv.id, 'Solicitud del cliente', 'normal')
        respuesta = (resultado.get('mensaje') or MENSAJE_DERIVACION).strip()
        _guardar_mensaje(conv, 'saliente', 'bot', respuesta)
        db.session.commit()
        wa_client.enviar_texto(tel_envio, respuesta)
        return respuesta

    # Modo bot: procesar con IA
    if tipo_mensaje == 'image' and media_id:
        try:
            analisis = _preparar_contexto_imagen(conv, msg_entrante, media_id, media_mime_type, texto)
            respuesta_img = _intentar_respuesta_directa_imagen(conv, analisis, texto)
            if respuesta_img:
                _guardar_mensaje(conv, 'saliente', 'bot', respuesta_img)
                db.session.commit()
                wa_client.enviar_texto(tel_envio, respuesta_img)
                return respuesta_img
        except Exception as e:
            logger.warning(f"Error preparando contexto de imagen: {e}", exc_info=True)
    return _procesar_con_ia(conv)


def _preparar_contexto_imagen(conv: WhatsAppConversacion, msg_entrante: WhatsAppMensaje,
                              media_id: str, media_mime_type: str | None, caption: str):
    logger.info(
        "Procesando imagen: conv=%s media_id=%s mime=%s caption=%r",
        conv.id,
        media_id,
        media_mime_type or "",
        (caption or "")[:80],
    )
    resultado_descarga = wa_client.descargar_media(media_id)
    contexto = _get_contexto(conv)

    if not resultado_descarga:
        logger.warning("No se pudo descargar media_id=%s (conv=%s)", media_id, conv.id)
        contexto['ultimo_media'] = {
            'tipo': 'image',
            'media_id': media_id,
            'mime_type': media_mime_type,
            'caption': caption,
            'error': 'No se pudo descargar la imagen desde WhatsApp',
        }
        _set_contexto(conv, contexto)
        db.session.commit()
        return None

    data, info = resultado_descarga
    mime_type = (info.get('mime_type') or media_mime_type or '').strip() or 'image/jpeg'
    url = (info.get('url') or '').strip()
    if url:
        msg_entrante.media_url = url
        db.session.commit()

    from app.services.ia.gpt_service import analizar_imagen_producto

    analisis = analizar_imagen_producto(
        image_bytes=data,
        mime_type=mime_type,
        caption=caption,
    )
    logger.info(
        "Visión resultado: conv=%s media_id=%s ok=%s",
        conv.id,
        media_id,
        bool((analisis or {}).get('ok')),
    )

    contexto['ultimo_media'] = {
        'tipo': 'image',
        'media_id': media_id,
        'mime_type': mime_type,
        'caption': caption,
        'vision': analisis,
    }
    _set_contexto(conv, contexto)
    db.session.commit()
    return analisis


def _intentar_respuesta_directa_imagen(conv: WhatsAppConversacion, analisis: dict | None, caption: str) -> str | None:
    if not analisis or not isinstance(analisis, dict) or not analisis.get('ok'):
        return None

    item = analisis.get('item') if isinstance(analisis.get('item'), dict) else {}
    categoria = (item.get('categoria') or '').strip()
    marca = (item.get('marca') or '').strip()
    modelo = (item.get('modelo') or '').strip()
    nombre_comercial = (item.get('nombre_comercial') or '').strip()

    conf = analisis.get('confianza') if isinstance(analisis.get('confianza'), dict) else {}
    conf_global = conf.get('global')
    try:
        conf_global_num = float(conf_global) if conf_global is not None else 0.0
    except Exception:
        conf_global_num = 0.0

    palabras = analisis.get('palabras_clave_busqueda')
    if not isinstance(palabras, list):
        palabras = []

    descripcion = (nombre_comercial or '').strip()
    if not descripcion:
        piezas = [p for p in (categoria, marca, modelo) if p]
        descripcion = ' '.join(piezas).strip()

    if not descripcion or conf_global_num < 0.45:
        return None

    from app.services.ia.tool_handlers import ejecutar_tool
    try:
        contexto = _get_contexto(conv)
        terminos: list[str] = []
        if categoria:
            terminos.append(categoria)
        if marca:
            terminos.append(marca)
        if modelo:
            terminos.append(modelo)
        for kw in palabras:
            if not isinstance(kw, str):
                continue
            kw = kw.strip()
            if not kw:
                continue
            if len(terminos) >= 4:
                break
            if kw.lower() not in {t.lower() for t in terminos}:
                terminos.append(kw)

        busqueda = ' '.join(terminos).strip() or descripcion
        resultado_str = ejecutar_tool('buscar_productos', {'busqueda': busqueda}, contexto)
        try:
            resultado = json.loads(resultado_str) if isinstance(resultado_str, str) else {}
        except Exception:
            resultado = {}

        productos = resultado.get('productos') if isinstance(resultado, dict) else None
        if isinstance(productos, list) and productos:
            top = productos[:3]
            resumen = '; '.join(
                f'{p.get("nombre", "")} ({p.get("precio", "Consultar")})'.strip()
                for p in top
                if isinstance(p, dict) and p.get('nombre')
            ).strip('; ').strip()
            if resumen:
                return f'Parece {descripcion}. Lo más parecido que tenemos ahora es: {resumen}.'

        return f'Parece {descripcion}, pero no me aparece nada igual en el catálogo ahora. ¿Buscás exactamente eso o algo parecido (ej: tamaño/capacidad o marca)?'
    except Exception:
        return None


# ─── Procesamiento con IA ────────────────────────────────────────────────────

def _procesar_con_ia(conv: WhatsAppConversacion) -> str:
    """Procesa el mensaje con la IA y maneja el ciclo de tool calls."""
    tel_envio = _telefono_sin_plus(conv.telefono)

    # Construir contexto para la IA
    contexto = _get_contexto(conv)
    contexto['telefono'] = conv.telefono
    contexto['id_conversacion'] = conv.id

    # Fecha y hora actual (para que la IA pueda razonar sobre fechas de entrega, etc.)
    from datetime import timezone, timedelta
    tz_py = timezone(timedelta(hours=-3))  # America/Asuncion (UTC-3 en horario de verano)
    ahora_local = datetime.now(tz_py)
    contexto['fecha_hora_actual'] = ahora_local.strftime('%Y-%m-%d %H:%M')
    contexto['zona_horaria'] = 'America/Asuncion (UTC-3)'
    contexto['contexto_bot'] = load_bot_context()

    # Conteo de mensajes previos (antes del mensaje actual)
    # Sirve para que la IA sepa claramente si hay conversación previa
    mensajes_entrantes = conv.mensajes.filter_by(direccion='entrante').count()
    es_primera = mensajes_entrantes <= 1  # El mensaje actual ya fue guardado
    contexto['es_primera_interaccion'] = es_primera
    contexto['mensajes_previos'] = mensajes_entrantes - 1  # Sin contar el actual

    # Inyectar datos del cliente (reparaciones activas, nombre, etc.)
    try:
        ctx_cliente = obtener_contexto_cliente(conv.telefono)
        if ctx_cliente:
            contexto['info_cliente'] = ctx_cliente
    except Exception as e:
        logger.warning(f"Error obteniendo contexto cliente: {e}")

    _set_contexto(conv, contexto)

    historial = _construir_historial_ia(conv)

    # Ciclo de tool calls
    for ciclo in range(MAX_TOOL_CYCLES):
        respuesta_ia = generar_respuesta(historial, contexto)

        if respuesta_ia['tipo'] == 'texto':
            texto = respuesta_ia['contenido']
            try:
                t_norm = _normalizar_texto_simple(texto)
                if 'queres que te comunique con un asesor' in t_norm:
                    _marcar_pendiente_derivacion(conv, contexto)
            except Exception:
                pass
            _guardar_mensaje(conv, 'saliente', 'bot', texto)
            db.session.commit()
            wa_client.enviar_texto(tel_envio, texto)
            return texto

        if respuesta_ia['tipo'] == 'tool_call':
            raw_msg = respuesta_ia.get('raw_message')
            if raw_msg:
                historial.append(raw_msg)
                _guardar_mensaje(conv, 'saliente', 'bot', '[tool_call]', tool_call={
                    'raw_message': raw_msg,
                })

            for tc in respuesta_ia['tool_calls']:
                # Guardrail: bloquear derivación no solicitada
                if tc.get('name') == 'derivar_a_asesor':
                    ultimo_user = next(
                        (m.get('content', '') for m in reversed(historial) if m.get('role') == 'user'),
                        ''
                    )
                    if not _cliente_pide_asesor(ultimo_user):
                        logger.info("Derivación bloqueada: el cliente no la solicitó")
                        tool_result_msg = {
                            'role': 'tool',
                            'tool_call_id': tc['id'],
                            'content': json.dumps({
                                'bloqueado': True,
                                'motivo': 'El cliente no solicitó derivación. Respondé directamente.',
                            }, ensure_ascii=False),
                        }
                        historial.append(tool_result_msg)
                        continue

                # Ejecutar tool
                resultado = ejecutar_tool(tc['name'], tc['arguments'], contexto)

                # Actualizar contexto post-tool
                _actualizar_contexto_post_tool(conv, contexto, tc['name'], tc['arguments'], resultado)

                tool_result_msg = {
                    'role': 'tool',
                    'tool_call_id': tc['id'],
                    'content': resultado,
                }
                historial.append(tool_result_msg)

                _guardar_mensaje(conv, 'saliente', 'bot', '[tool_result]', tool_call={
                    'tool_call_id': tc['id'],
                    'tool_name': tc['name'],
                    'tool_result': json.loads(resultado) if isinstance(resultado, str) else resultado,
                })

            db.session.commit()
            continue  # Siguiente ciclo: la IA genera respuesta con los resultados

    # Demasiados ciclos
    logger.warning(f"Demasiados ciclos de tool calls para conv={conv.id}")
    texto = "Hubo un problema procesando tu consulta. ¿Querés que te comunique con un asesor?"
    try:
        _marcar_pendiente_derivacion(conv, _get_contexto(conv))
    except Exception:
        pass
    _guardar_mensaje(conv, 'saliente', 'bot', texto)
    db.session.commit()
    wa_client.enviar_texto(tel_envio, texto)
    return texto


def _actualizar_contexto_post_tool(conv: WhatsAppConversacion, contexto: dict,
                                    tool_name: str, args: dict, resultado_str: str):
    """Actualiza el contexto de la conversación después de ejecutar un tool."""
    try:
        resultado = json.loads(resultado_str) if isinstance(resultado_str, str) else resultado_str
    except (json.JSONDecodeError, TypeError):
        return

    if tool_name == 'verificar_codigo' and resultado.get('verificado'):
        contexto['verificado'] = True
        if resultado.get('id_reparacion'):
            contexto['reparacion_verificada'] = resultado['id_reparacion']
            contexto['reparacion_seleccionada'] = resultado['id_reparacion']

    elif tool_name == 'listar_reparaciones_cliente':
        reps = resultado.get('reparaciones', [])
        if len(reps) == 1:
            contexto['reparacion_seleccionada'] = reps[0]['id_reparacion']

    elif tool_name == 'consultar_estado_reparacion':
        if not resultado.get('error'):
            contexto['reparacion_seleccionada'] = args.get('id_reparacion')

    elif tool_name == 'derivar_a_asesor':
        if resultado.get('asignado'):
            conv.modo = 'derivacion'

    _set_contexto(conv, contexto)


# ─── Envío de mensajes del asesor ────────────────────────────────────────────

def enviar_mensaje_asesor(id_conversacion: int, texto: str, id_asesor: int) -> dict:
    """Envía un mensaje del asesor al cliente vía WhatsApp."""
    conv = WhatsAppConversacion.query.get(id_conversacion)
    if not conv:
        return {'ok': False, 'error': 'Conversación no encontrada'}

    if conv.modo != 'asesor':
        return {'ok': False, 'error': 'La conversación no está en modo asesor'}

    tel_envio = _telefono_sin_plus(conv.telefono)
    _guardar_mensaje(conv, 'saliente', 'asesor', texto, id_asesor=id_asesor)
    ahora = datetime.utcnow()
    conv.ultima_actividad = ahora

    # Actualizar timestamp de última respuesta para la Política B (sin respuesta)
    from app.models.whatsapp import WhatsAppAsignacionConversacion
    asig = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=id_conversacion
    ).filter(WhatsAppAsignacionConversacion.estado == 'activa').first()
    if asig:
        asig.ultima_respuesta_asesor_at = ahora

    if registrar_respuesta_asesor_en_web(conv, texto):
        db.session.commit()
        return {'ok': True, 'canal': 'web'}

    db.session.commit()

    resultado = wa_client.enviar_texto(tel_envio, texto)
    if resultado:
        return {'ok': True}
    return {'ok': False, 'error': 'Error enviando mensaje por WhatsApp'}


# ─── Sincronización CRM ───────────────────────────────────────────────────────

def _sincronizar_contacto_crm(conv: WhatsAppConversacion):
    """Crea o actualiza el CrmContacto asociado a esta conversación."""
    try:
        from app.models.crm_contacto import CrmContacto
        contacto = CrmContacto.query.filter_by(telefono=conv.telefono).first()
        ahora = datetime.utcnow()
        if contacto is None:
            contacto = CrmContacto(
                telefono=conv.telefono,
                nombre=conv.nombre_contacto,
                primer_contacto=ahora,
                ultimo_contacto=ahora,
                total_conversaciones=1,
            )
            db.session.add(contacto)
            logger.info(f"CrmContacto creado: tel={conv.telefono}")
        else:
            contacto.ultimo_contacto = ahora
            if conv.nombre_contacto and not contacto.nombre:
                contacto.nombre = conv.nombre_contacto
            # Actualizar total de conversaciones
            from app.models.whatsapp import WhatsAppConversacion as WC
            contacto.total_conversaciones = WC.query.filter_by(telefono=conv.telefono).count()
        db.session.commit()
    except Exception as e:
        logger.warning(f"Error sincronizando CrmContacto para {conv.telefono}: {e}")


def _tiene_intencion_reparacion(texto: str) -> bool:
    from app.services.whatsapp.conversacion.intenciones import _tiene_intencion_reparacion as fn
    return fn(texto)


def _tiene_intencion_tiempo_reparacion(texto: str) -> bool:
    from app.services.whatsapp.conversacion.intenciones import _tiene_intencion_tiempo_reparacion as fn
    return fn(texto)


def _es_saludo_simple(texto: str) -> bool:
    from app.services.whatsapp.conversacion.intenciones import _es_saludo_simple as fn
    return fn(texto)


def _es_confirmacion_corta(texto: str) -> bool:
    from app.services.whatsapp.conversacion.intenciones import _es_confirmacion_corta as fn
    return fn(texto)


def _pide_mas_detalle_reparacion(texto: str) -> bool:
    from app.services.whatsapp.conversacion.intenciones import _pide_mas_detalle_reparacion as fn
    return fn(texto)


def _es_agradecimiento_o_cierre(texto: str) -> bool:
    from app.services.whatsapp.conversacion.intenciones import _es_agradecimiento_o_cierre as fn
    return fn(texto)


def _cliente_menciona_equipo_no_registrado(texto: str, contexto: dict) -> str | None:
    from app.services.whatsapp.conversacion.reparaciones import _cliente_menciona_equipo_no_registrado as fn
    return fn(texto, contexto)


def _respuesta_directa_reparacion_desde_contexto(
    contexto: dict,
    texto: str,
    forzar_intencion_tiempo: bool = False,
    es_followup: bool = False,
) -> str | None:
    from app.services.whatsapp.conversacion.reparaciones import _respuesta_directa_reparacion_desde_contexto as fn
    return fn(contexto, texto, forzar_intencion_tiempo=forzar_intencion_tiempo, es_followup=es_followup)


def _respuesta_detalle_etapa_desde_contexto(contexto: dict) -> str | None:
    from app.services.whatsapp.conversacion.reparaciones import _respuesta_detalle_etapa_desde_contexto as fn
    return fn(contexto)


def clasificar_intencion(texto: str, contexto: dict | None = None) -> dict:
    from app.services.whatsapp.conversacion.intenciones import (
        _cliente_pide_asesor,
        _cliente_pregunta_por_su_reparacion,
        _tiene_intencion_reparacion,
        _tiene_intencion_tiempo_reparacion,
        _es_agradecimiento_o_cierre,
    )

    t = (texto or '').strip()
    if not t:
        return {"intent": "otro", "confidence": 0.0, "needs_clarification": False}

    if _es_agradecimiento_o_cierre(t):
        return {"intent": "agradecimiento", "confidence": 0.9, "needs_clarification": False}

    if _cliente_pide_asesor(t):
        return {"intent": "pedir_asesor", "confidence": 0.95, "needs_clarification": False}

    if _tiene_intencion_tiempo_reparacion(t):
        return {"intent": "reparacion_tiempo", "confidence": 0.85, "needs_clarification": False}

    if _cliente_pregunta_por_su_reparacion(t) or _tiene_intencion_reparacion(t):
        return {"intent": "reparacion_estado", "confidence": 0.8, "needs_clarification": False}

    return {"intent": "otro", "confidence": 0.5, "needs_clarification": True}


def _generar_respuesta_agradecimiento(contexto: dict | None = None) -> str:
    last_intent = ((contexto or {}).get("last_intent") or "").strip().lower()
    if last_intent in {"reparacion_estado", "reparacion_tiempo"}:
        return "De nada! Cualquier cosa me decis y lo vemos 👍"
    if last_intent in {"saludo", "otro"}:
        return "De nada! En que mas te puedo ayudar? 👍"
    return "De nada! 👍"


def _decidir_respuesta_por_intencion(texto: str, contexto: dict | None = None) -> dict:
    from app.services.whatsapp.conversacion.reparaciones import (
        _generar_instruccion_detalle_reparacion,
        _generar_instruccion_estado_reparacion,
        _generar_instruccion_tiempo_reparacion,
    )

    contexto = contexto or {}

    if _es_agradecimiento_o_cierre(texto):
        return {
            "intent": "agradecimiento",
            "resolution": "agradecimiento_deterministico",
            "respuesta": _generar_respuesta_agradecimiento(contexto),
            "usar_ia": False,
            "instruccion_ia": None,
            "set_followup_tiempo": False,
            "set_followup_etapa": False,
        }

    mismatch = _cliente_menciona_equipo_no_registrado(texto, contexto)
    if mismatch:
        return {
            "intent": "reparacion_estado",
            "resolution": "equipo_no_registrado",
            "respuesta": mismatch,
            "usar_ia": False,
            "instruccion_ia": None,
            "set_followup_tiempo": False,
            "set_followup_etapa": False,
        }

    if _pide_mas_detalle_reparacion(texto):
        instruccion = _generar_instruccion_detalle_reparacion(contexto)
        if instruccion:
            return {
                "intent": "reparacion_estado",
                "resolution": "reparacion_detalle_ia",
                "respuesta": None,
                "usar_ia": True,
                "instruccion_ia": instruccion,
                "set_followup_tiempo": False,
                "set_followup_etapa": True,
            }

    analisis = clasificar_intencion(texto, contexto)
    intent = (analisis.get("intent") or "otro").strip().lower()
    confidence = float(analisis.get("confidence") or 0.0)
    needs_clarification = bool(analisis.get("needs_clarification"))

    if intent == "reparacion_tiempo":
        if not _tiene_intencion_tiempo_reparacion(texto) and (contexto.get("last_intent") or "") != "reparacion_tiempo":
            return {
                "intent": intent,
                "resolution": "pasar_a_ia",
                "respuesta": None,
                "usar_ia": False,
                "instruccion_ia": None,
                "set_followup_tiempo": False,
                "set_followup_etapa": False,
            }

        instruccion = _generar_instruccion_tiempo_reparacion(contexto, texto, es_followup=False)
        if instruccion:
            return {
                "intent": intent,
                "resolution": "reparacion_tiempo_ia",
                "respuesta": None,
                "usar_ia": True,
                "instruccion_ia": instruccion,
                "set_followup_tiempo": False,
                "set_followup_etapa": False,
            }

        if needs_clarification and confidence >= 0.7:
            return {
                "intent": intent,
                "resolution": "pasar_a_ia",
                "respuesta": None,
                "usar_ia": False,
                "instruccion_ia": None,
                "set_followup_tiempo": False,
                "set_followup_etapa": False,
            }

        return {
            "intent": intent,
            "resolution": "pasar_a_ia",
            "respuesta": None,
            "usar_ia": False,
            "instruccion_ia": None,
            "set_followup_tiempo": False,
            "set_followup_etapa": False,
        }

    if intent == "reparacion_estado":
        instruccion = _generar_instruccion_estado_reparacion(contexto)
        if instruccion:
            return {
                "intent": intent,
                "resolution": "reparacion_estado_ia",
                "respuesta": None,
                "usar_ia": True,
                "instruccion_ia": instruccion,
                "set_followup_tiempo": True,
                "set_followup_etapa": False,
            }
        return {
            "intent": intent,
            "resolution": "pasar_a_ia",
            "respuesta": None,
            "usar_ia": False,
            "instruccion_ia": None,
            "set_followup_tiempo": True,
            "set_followup_etapa": False,
        }

    if needs_clarification and confidence >= 0.6:
        return {
            "intent": intent,
            "resolution": "pasar_a_ia",
            "respuesta": None,
            "usar_ia": False,
            "instruccion_ia": None,
            "set_followup_tiempo": False,
            "set_followup_etapa": False,
        }

    return {
        "intent": intent,
        "resolution": "pasar_a_ia",
        "respuesta": None,
        "usar_ia": False,
        "instruccion_ia": None,
        "set_followup_tiempo": False,
        "set_followup_etapa": False,
    }
