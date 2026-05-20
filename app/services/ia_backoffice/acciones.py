"""
Acciones asistidas del asistente IA interno.

Sprint 9 solo prepara y confirma borradores. No ejecuta cambios de negocio.
"""
import unicodedata

from app import db
from app.models import AsistenteIABackofficeAudit
from app.services.ia_backoffice.audit import registrar_interaccion
from app.services.ia_backoffice.security import es_usuario_root
from app.services.ia_backoffice.settings import obtener_configuracion_asistente


TIPOS_ACCION = {
    'borrador_campanha': 'Borrador de campana',
    'lista_clientes_contactar': 'Lista de clientes para contactar',
    'recordatorio_interno': 'Recordatorio interno',
    'reporte_descargable': 'Reporte descargable',
}
MAX_LIST_ITEMS = 20
MAX_TEXT_CHARS = 700
VERBOS_ACCION = (
    'prepara',
    'preparame',
    'generar',
    'generame',
    'crear',
    'creame',
    'armar',
    'armame',
    'hacer',
    'haceme',
)


def acciones_asistidas_disponibles() -> bool:
    cfg = obtener_configuracion_asistente()
    return bool(cfg.assisted_actions_enabled and cfg.readonly_mode)


def _texto(valor, max_chars: int = MAX_TEXT_CHARS) -> str:
    limpio = ' '.join(str(valor or '').split())
    return limpio[:max_chars]


def _lista_texto(valor) -> list[str]:
    if not isinstance(valor, list):
        return []
    salida = []
    for item in valor[:MAX_LIST_ITEMS]:
        limpio = _texto(item, 160)
        if limpio:
            salida.append(limpio)
    return salida


def _normalizar_busqueda(valor: str) -> str:
    texto = unicodedata.normalize('NFKD', valor or '')
    sin_tildes = ''.join(char for char in texto if not unicodedata.combining(char))
    return sin_tildes.lower()


def _tiene_verbo_accion(texto: str) -> bool:
    return any(verbo in texto for verbo in VERBOS_ACCION)


def _inferir_tipo_accion(mensaje: str) -> str:
    texto = _normalizar_busqueda(mensaje)
    if not _tiene_verbo_accion(texto):
        return ''
    if any(palabra in texto for palabra in ('campana', 'campaña', 'promocion', 'whatsapp', 'mensaje')):
        return 'borrador_campanha'
    if 'lista' in texto and any(palabra in texto for palabra in ('cliente', 'contactar', 'recuperar')):
        return 'lista_clientes_contactar'
    if any(palabra in texto for palabra in ('recordatorio', 'recordame', 'tarea')):
        return 'recordatorio_interno'
    if any(palabra in texto for palabra in ('reporte', 'informe', 'descargable')):
        return 'reporte_descargable'
    return ''


def _normalizar_payload(tipo: str, payload: dict | None) -> dict:
    data = payload if isinstance(payload, dict) else {}
    base = {
        'titulo': _texto(data.get('titulo'), 180),
        'objetivo': _texto(data.get('objetivo')),
        'notas': _texto(data.get('notas')),
    }
    if tipo == 'borrador_campanha':
        base.update({
            'canal': _texto(data.get('canal') or 'whatsapp', 40),
            'mensaje_borrador': _texto(data.get('mensaje_borrador') or data.get('mensaje'), 1200),
            'destinatarios': _lista_texto(data.get('destinatarios')),
        })
    elif tipo == 'lista_clientes_contactar':
        base.update({
            'clientes': _lista_texto(data.get('clientes')),
            'motivo_contacto': _texto(data.get('motivo_contacto') or data.get('motivo')),
        })
    elif tipo == 'recordatorio_interno':
        base.update({
            'fecha_sugerida': _texto(data.get('fecha_sugerida') or data.get('fecha'), 40),
            'responsable': _texto(data.get('responsable'), 120),
        })
    elif tipo == 'reporte_descargable':
        base.update({
            'periodo': _texto(data.get('periodo') or 'mes', 40),
            'formato': _texto(data.get('formato') or 'pdf', 20),
            'secciones': _lista_texto(data.get('secciones')),
        })
    return {key: value for key, value in base.items() if value not in ('', [], None)}


def preparar_accion_asistida(tipo: str, payload: dict | None, usuario) -> dict:
    tipo_norm = _texto(tipo, 80)
    if tipo_norm not in TIPOS_ACCION:
        return {'ok': False, 'error': 'tipo_accion_no_soportado'}
    cfg = obtener_configuracion_asistente()
    if not cfg.assisted_actions_enabled:
        return {'ok': False, 'error': 'acciones_asistidas_deshabilitadas'}
    if not cfg.readonly_mode:
        return {'ok': False, 'error': 'modo_solo_lectura_requerido'}

    accion = {
        'tipo': tipo_norm,
        'tipo_label': TIPOS_ACCION[tipo_norm],
        'payload': _normalizar_payload(tipo_norm, payload),
        'requiere_confirmacion': True,
        'ejecutada': False,
        'modo': 'solo_borrador',
        'readonly_mode': True,
    }
    audit = registrar_interaccion(
        usuario,
        f'accion_asistida:{tipo_norm}',
        f'Accion asistida preparada: {accion["tipo_label"]}',
        tools_usadas=['accion_asistida_preparar'],
        argumentos_normalizados=accion,
        resultado_resumido='Borrador preparado. Requiere confirmacion explicita.',
        estado='accion_preparada',
    )
    accion['id_accion'] = audit.id_audit
    return {'ok': True, 'accion': accion}


def preparar_accion_desde_chat(mensaje: str, respuesta: str, usuario) -> dict | None:
    if not acciones_asistidas_disponibles():
        return None
    tipo = _inferir_tipo_accion(mensaje)
    if not tipo:
        return None
    payload = {
        'titulo': _texto(mensaje, 180),
        'objetivo': _texto(mensaje),
        'notas': 'Preparado desde el chat del asistente IA. No ejecuta cambios automaticos.',
    }
    if tipo == 'borrador_campanha':
        payload['mensaje_borrador'] = _texto(respuesta, 1200)
    elif tipo == 'lista_clientes_contactar':
        payload['motivo_contacto'] = _texto(mensaje)
    elif tipo == 'reporte_descargable':
        payload['secciones'] = ['Resumen ejecutivo', 'Datos clave', 'Siguiente accion sugerida']
    resultado = preparar_accion_asistida(tipo, payload, usuario)
    return resultado.get('accion') if resultado.get('ok') else None


def confirmar_accion_asistida(id_accion: int, usuario) -> dict:
    cfg = obtener_configuracion_asistente()
    if not cfg.assisted_actions_enabled:
        return {'ok': False, 'error': 'acciones_asistidas_deshabilitadas'}
    if not cfg.readonly_mode:
        return {'ok': False, 'error': 'modo_solo_lectura_requerido'}
    try:
        audit_id = int(id_accion or 0)
    except Exception:
        return {'ok': False, 'error': 'accion_invalida'}
    audit = db.session.get(AsistenteIABackofficeAudit, audit_id)
    if audit is None or audit.estado != 'accion_preparada':
        return {'ok': False, 'error': 'accion_no_encontrada'}
    mismo_usuario = audit.id_usuario == getattr(usuario, 'id_usuario', None)
    if not mismo_usuario and not es_usuario_root(usuario):
        return {'ok': False, 'error': 'sin_permiso_accion'}

    registrar_interaccion(
        usuario,
        f'confirmar_accion_asistida:{audit_id}',
        'Confirmacion registrada. No se ejecuto ningun cambio automatico.',
        tools_usadas=['accion_asistida_confirmar'],
        argumentos_normalizados={'id_accion': audit_id},
        resultado_resumido='Confirmacion auditada en modo solo borrador.',
        estado='accion_confirmada_sin_ejecucion',
    )
    return {
        'ok': True,
        'estado': 'accion_confirmada_sin_ejecucion',
        'mensaje': 'Confirmacion registrada. El MVP no ejecuta cambios automaticos.',
        'readonly_mode': True,
    }
