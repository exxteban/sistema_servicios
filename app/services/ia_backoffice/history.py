"""
Compactacion simple del historial del asistente IA backoffice.
"""


MAX_RESUMEN_HISTORIAL_CHARS = 2000
MAX_LINEA_RESUMEN_CHARS = 220


def _limpiar_texto(texto: str, max_chars: int = MAX_LINEA_RESUMEN_CHARS) -> str:
    limpio = ' '.join((texto or '').split())
    if len(limpio) <= max_chars:
        return limpio
    return limpio[: max_chars - 3].rstrip() + '...'


def _linea_resumen(item: dict) -> str:
    role = item.get('role')
    contenido = _limpiar_texto(item.get('content') or '')
    if not contenido:
        return ''
    prefijo = 'Usuario' if role == 'user' else 'Asistente'
    return f'{prefijo}: {contenido}'


def compactar_historial(
    resumen_actual: str,
    mensajes_antiguos: list[dict],
    *,
    max_chars: int = MAX_RESUMEN_HISTORIAL_CHARS,
) -> str:
    lineas = []
    actual = _limpiar_texto(resumen_actual or '', max_chars=max_chars)
    if actual:
        lineas.append(actual)
    for item in mensajes_antiguos:
        if not isinstance(item, dict) or item.get('role') not in {'user', 'assistant'}:
            continue
        linea = _linea_resumen(item)
        if linea:
            lineas.append(linea)
    resumen = '\n'.join(lineas)
    if len(resumen) <= max_chars:
        return resumen
    return resumen[-max_chars:].lstrip()
