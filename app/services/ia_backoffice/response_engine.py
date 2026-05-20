"""
Engine del asistente IA interno.
"""
import json
import logging
import re
import unicodedata
from types import SimpleNamespace

from openai import OpenAI

from app.services.ia_backoffice.ayuda_tools import buscar_ayuda
from app.services.ia_backoffice.context import construir_contexto_minimo
from app.services.ia_backoffice.dsml_parser import tool_calls_textuales as _tool_calls_textuales
from app.services.ia_backoffice.limits import mensaje_presupuesto_excedido, validar_presupuesto_tokens
from app.services.ia_backoffice.modulos_tools import resolver_modulo_consulta
from app.services.ia_backoffice.prompts import SYSTEM_PROMPT_BACKOFFICE
from app.services.ia_backoffice.response_presenter import respuesta_tool_directa
from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from app.services.ia_backoffice.temporal_args import normalizar_argumentos_temporales
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tool_selector import seleccionar_tools_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS
from app.services.ia.settings_resolver import get_setting


logger = logging.getLogger(__name__)
MAX_HISTORY_MESSAGES = 12
GUARANI_AMOUNT_RE = re.compile(r'(?<![A-Za-z])\$\s*(?=\d)')

def respuesta_no_disponible() -> dict:
    return {
        'tipo': 'texto',
        'contenido': 'El asistente IA interno esta desactivado. Pedile al usuario root que lo habilite.',
        'estado': 'desactivado',
    }


def _resolver_api_key(provider: str) -> tuple[str, str]:
    generic_key, generic_source = get_setting('ia_api_key', 'AI_API_KEY', clean=True)
    openai_key, openai_source = get_setting('ia_openai_api_key', 'OPENAI_API_KEY', clean=True)
    deepseek_key, deepseek_source = get_setting('ia_deepseek_api_key', 'DEEPSEEK_API_KEY', clean=True)
    if provider == 'deepseek':
        if deepseek_key:
            return deepseek_key, deepseek_source
        if generic_key:
            return generic_key, generic_source
        return openai_key, openai_source
    if openai_key:
        return openai_key, openai_source
    if generic_key:
        return generic_key, generic_source
    return deepseek_key, deepseek_source


def _crear_cliente(provider: str, base_url: str) -> tuple[OpenAI | None, str]:
    api_key, key_source = _resolver_api_key(provider)
    if not api_key:
        return None, key_source
    if provider == 'deepseek':
        return OpenAI(api_key=api_key, base_url=base_url), key_source
    return OpenAI(api_key=api_key), key_source


def _ultima_consulta_usuario(historial: list[dict]) -> str:
    for item in reversed(historial or []):
        if item.get('role') == 'user':
            return (item.get('content') or '').strip()
    return ''


def _guia_tools_prioritarias(historial: list[dict]) -> str:
    consulta = _ultima_consulta_usuario(historial).lower()
    if not consulta:
        return ''
    explicacion_modulo = ('modulo' in consulta) and any(
        token in consulta for token in ('como funciona', 'como se usa', 'para que sirve', 'que hace', 'qué hace')
    )

    hints = []
    if any(token in consulta for token in ('que mes', 'qué mes', 'por mes', 'mensual', 'mes vendio', 'mes se vendio', 'mes con mas ventas', 'mes con más ventas')):
        hints.append('- Si la consulta pide ranking o detalle por mes, prioriza ventas_ranking_mensual.')
    if any(token in consulta for token in ('compar', ' versus ', ' vs ', 'contra ', 'periodo anterior', 'mes anterior', 'semana anterior')):
        hints.append('- Si la consulta compara periodos, prioriza comparar_periodos_negocio.')
    if any(token in consulta for token in ('hallazgo', 'hallazgos', 'alerta', 'alertas', 'prioridad', 'prioridades', 'que revisar', 'revisar hoy')):
        hints.append('- Si la consulta pide prioridades operativas, prioriza hallazgos_operativos_priorizados.')
    if any(token in consulta for token in ('factura', 'ticket', 'comprobante', 'documento', 'detalle de venta', 'id_venta', 'id venta')):
        hints.append('- Si la consulta pide un documento de venta puntual, prioriza detalle_venta_documento.')
    if any(token in consulta for token in ('compra', 'compras', 'proveedor', 'proveedores')):
        hints.append('- Si la consulta es sobre compras o proveedores, prioriza compras_resumen_periodo, proveedores_top o proveedor_detalle_360.')
    if any(token in consulta for token in ('devolucion', 'devoluciones', 'devuelto', 'devueltos')):
        hints.append('- Si la consulta es sobre devoluciones comerciales, prioriza devoluciones_resumen, productos_mas_devueltos o motivos_de_devolucion.')
    if any(token in consulta for token in ('usado', 'usados', 'recepcion', 'recepciones')):
        hints.append('- Si la consulta es sobre compra/recepcion de usados, prioriza usados_resumen o usados_pendientes_revision.')
    if any(token in consulta for token in ('presupuesto', 'presupuestos', 'cotizacion')):
        hints.append('- Si la consulta es sobre presupuestos empresariales, prioriza presupuestos_resumen o presupuesto_detalle.')
    if any(token in consulta for token in ('agenda', 'turno', 'turnos', 'atencion', 'atenciones')):
        hints.append('- Si la consulta es sobre agenda, turnos o atenciones, prioriza turnos_resumen, turnos_proximos o atenciones_resumen.')
    if any(token in consulta for token in ('modulo', 'módulo', 'como funciona', 'cómo funciona', 'para que sirve', 'que hace', 'qué hace')):
        hints.append('- Si el usuario pide explicar un modulo del sistema, prioriza modulo_funcionamiento y responde a nivel funcional.')
    if any(token in consulta for token in ('fideliz', 'programa de puntos', 'recompensa', 'canje', 'premio')) and not explicacion_modulo:
        hints.append('- Si la consulta es sobre fidelizacion, puntos, recompensas o canjes, prioriza fidelizacion_resumen.')
    if explicacion_modulo:
        hints.append('- Si la pregunta es funcional de modulo, evita responder con metricas o estado operativo salvo que el usuario lo pida explicitamente.')
    if any(token in consulta for token in ('busca ', 'buscame', 'buscar ', 'encontra', 'encontrar', 'localiza')):
        hints.append('- Si la consulta pide localizar una entidad sin tipo claro, usa buscar_entidad_backoffice.')
    if 'productos' in consulta and any(token in consulta for token in ('hay', 'tenes', 'tienes', 'lista', 'listar', 'mostrar')):
        hints.append('- Si pregunta que productos hay de un rubro o texto, usa buscar_entidad_backoffice con busqueda igual al rubro mencionado.')
    if any(token in consulta for token in ('negocio hoy', 'estado de hoy', 'como estamos hoy', 'dashboard', 'que revisar ahora')):
        hints.append('- Si pide estado ejecutivo de hoy, prioriza dashboard_operativo_hoy.')
    if 'cliente' in consulta or any(token in consulta for token in ('moroso', 'morosa', 'saldo del cliente', 'historial del cliente', 'reactivar cliente')):
        hints.append('- Si la consulta es sobre un cliente puntual, prioriza cliente_detalle_360.')
    if any(token in consulta for token in ('producto', 'articulo', 'sku', 'codigo', 'stock de', 'rotacion', 'margen del producto')):
        hints.append('- Si la consulta es sobre un producto puntual, prioriza producto_detalle_360.')
    if not hints:
        return ''
    hints.append('- Si una tool devuelve candidatos, pedi al usuario que elija un ID o referencia exacta.')
    return 'Prioridades sugeridas para esta consulta:\n' + '\n'.join(dict.fromkeys(hints))


def _mensajes(historial: list[dict], usuario, resumen_historial: str = '') -> list[dict]:
    contexto = construir_contexto_minimo(usuario)
    system_prompt = f"{SYSTEM_PROMPT_BACKOFFICE}\n\nContexto minimo: {contexto}"
    resumen = (resumen_historial or '').strip()
    if resumen:
        system_prompt = f"{system_prompt}\n\nResumen del historial previo: {resumen[:2000]}"
    guia_tools = _guia_tools_prioritarias(historial)
    if guia_tools:
        system_prompt = f"{system_prompt}\n\n{guia_tools}"
    sanitizado = []
    for item in historial[-MAX_HISTORY_MESSAGES:]:
        role = item.get('role')
        content = (item.get('content') or '').strip()
        if role in {'user', 'assistant'} and content:
            sanitizado.append({'role': role, 'content': content[:4000]})
    return [{'role': 'system', 'content': system_prompt}] + sanitizado


def _usage_dict(response) -> dict:
    usage = getattr(response, 'usage', None)
    return {
        'tokens_prompt': int(getattr(usage, 'prompt_tokens', 0) or 0) if usage else 0,
        'tokens_completion': int(getattr(usage, 'completion_tokens', 0) or 0) if usage else 0,
    }


def _normalizar_respuesta_texto(texto: str) -> str:
    normalizado = GUARANI_AMOUNT_RE.sub('Gs. ', texto or '')
    return normalizado.replace('**', '').strip()


def _completion_kwargs(cfg, messages: list[dict], *, tools: list[dict] | None = None) -> dict:
    kwargs = {'model': cfg.model, 'messages': messages}
    if tools:
        kwargs['tools'] = tools
        kwargs['tool_choice'] = 'auto'
    if cfg.provider != 'deepseek' and (cfg.model.startswith('o') or cfg.model.startswith('gpt-5')):
        kwargs['max_completion_tokens'] = cfg.max_tokens
    else:
        kwargs['max_tokens'] = cfg.max_tokens
        kwargs['temperature'] = cfg.temperature
    return kwargs


def _consulta_requiere_modelo_avanzado(historial: list[dict]) -> bool:
    consulta = _ultima_consulta_usuario(historial).lower()
    if not consulta:
        return False
    indicadores = (
        'analiza', 'analisis', 'estrategia', 'diagnostico',
        'rentabilidad', 'margen', 'compar', 'hallazgo', 'hallazgos', 'prioridad',
        'prioridades', 'detalle', 'explicame', 'por que',
    )
    return any(token in consulta for token in indicadores)


def _cfg_con_modelo_resuelto(cfg, historial: list[dict]):
    if not cfg.advanced_model_enabled:
        return cfg
    advanced_model = (getattr(cfg, 'advanced_model', '') or '').strip()
    if not advanced_model or advanced_model == cfg.model:
        return cfg
    if not _consulta_requiere_modelo_avanzado(historial):
        return cfg
    return type(cfg)(
        enabled=cfg.enabled,
        provider=cfg.provider,
        model=advanced_model,
        deepseek_base_url=cfg.deepseek_base_url,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        daily_token_budget=cfg.daily_token_budget,
        monthly_token_budget=cfg.monthly_token_budget,
        readonly_mode=cfg.readonly_mode,
        assisted_actions_enabled=cfg.assisted_actions_enabled,
        advanced_model_enabled=cfg.advanced_model_enabled,
        advanced_model=cfg.advanced_model,
    )


def _tool_call_dicts(message) -> list[dict]:
    salida = []
    for tc in getattr(message, 'tool_calls', None) or []:
        salida.append({
            'id': tc.id,
            'type': 'function',
            'function': {
                'name': tc.function.name,
                'arguments': tc.function.arguments or '{}',
            },
        })
    return salida


def _message_extra_value(message, key: str):
    value = getattr(message, key, None)
    if value:
        return value
    extra = getattr(message, 'model_extra', None) or {}
    return extra.get(key)


def _assistant_tool_message(message) -> dict:
    payload = {
        'role': 'assistant',
        'content': message.content or '',
        'tool_calls': _tool_call_dicts(message),
    }
    reasoning_content = _message_extra_value(message, 'reasoning_content')
    if reasoning_content:
        payload['reasoning_content'] = reasoning_content
    return payload


_respuesta_directa_tool = respuesta_tool_directa

def _respuesta_resumen_tools_textuales(resultados_tool: list[dict]) -> str:
    nombres = [item.get('tool') for item in resultados_tool if isinstance(item, dict) and item.get('tool')]
    if not nombres:
        return ''
    return f"Ejecute consultas internas, pero no pude armar una respuesta final automatica. Tools usadas: {', '.join(nombres[:5])}."


def _ejecutar_tool_calls(message, usuario, consulta: str = '') -> tuple[list[dict], list[str], list[dict]]:
    tool_messages = []
    usadas = []
    resultados = []
    for tc in getattr(message, 'tool_calls', None) or []:
        try:
            argumentos = json.loads(tc.function.arguments or '{}')
        except Exception:
            argumentos = {}
        argumentos = normalizar_argumentos_temporales(argumentos, consulta)
        resultado = ejecutar_tool_backoffice(tc.function.name, argumentos, usuario=usuario)
        usadas.append(tc.function.name)
        resultados.append({
            'tool': tc.function.name,
            'argumentos': argumentos,
            'resultado': resultado,
        })
        tool_messages.append({
            'role': 'tool',
            'tool_call_id': tc.id,
            'content': json.dumps(resultado, ensure_ascii=False, default=str),
        })
    return tool_messages, usadas, resultados


def _termino_busqueda_productos(consulta: str) -> str:
    texto = (consulta or '').strip().lower()
    patrones = (
        r'que\s+(.+?)\s+hay(?:\?|$)',
        r'productos?\s+de\s+(.+?)(?:\?|$)',
        r'(?:tenes|tienes|hay|mostrar|listar|lista)\s+(.+?)(?:\?|$)',
    )
    for patron in patrones:
        match = re.search(patron, texto)
        if match:
            termino = re.sub(r'\b(productos?|articulos?|items?)\b', '', match.group(1)).strip()
            termino = re.sub(r'\b(hay|tenes|tienes|disponibles?)\b$', '', termino).strip()
            return termino.rstrip('?.! ')[:80]
    return ''


def _normalizar_texto_consulta(consulta: str) -> str:
    texto = unicodedata.normalize('NFKD', (consulta or '').lower()).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', texto).strip()


def _ultimo_modulo_mencionado(historial: list[dict]) -> str | None:
    for item in reversed(historial[:-1] if historial else []):
        if not isinstance(item, dict) or item.get('role') != 'user':
            continue
        modulo = resolver_modulo_consulta(item.get('content') or '')
        if modulo:
            return modulo
    return None


def _consulta_pide_explicar_modulo(texto: str) -> bool:
    if not texto:
        return False
    patrones = (
        'como funciona', 'como se usa', 'para que sirve', 'que hace',
        'explicame', 'explica', 'como opera', 'como trabaja',
    )
    return any(patron in texto for patron in patrones)


def _respuesta_directa_ayuda(historial: list[dict]) -> dict | None:
    """Responde preguntas de uso del sistema desde la KB local. Cero tokens."""
    consulta = _ultima_consulta_usuario(historial)
    if not consulta:
        return None
    respuesta = buscar_ayuda(consulta)
    if not respuesta:
        return None
    return {
        'tipo': 'texto',
        'contenido': respuesta,
        'estado': 'ok',
        'tools_usadas': [],
        'argumentos_normalizados': [],
        'resultado_resumido': '',
        'tokens_prompt': 0,
        'tokens_completion': 0,
    }


def _respuesta_directa_modulo(historial: list[dict], usuario) -> dict | None:
    consulta = _ultima_consulta_usuario(historial)
    texto = _normalizar_texto_consulta(consulta)
    explica_modulo = 'modulo' in texto or _consulta_pide_explicar_modulo(texto)
    if not explica_modulo:
        return None
    modulo = resolver_modulo_consulta(consulta)
    if not modulo:
        modulo = _ultimo_modulo_mencionado(historial)
    if not modulo:
        return None
    nombre_tool = 'modulo_funcionamiento'
    args = {'modulo': modulo, 'busqueda': consulta}
    resultado = ejecutar_tool_backoffice(nombre_tool, args, usuario=usuario)
    contenido = _respuesta_directa_tool(nombre_tool, resultado)
    if not contenido:
        return None
    return {
        'tipo': 'texto',
        'contenido': _normalizar_respuesta_texto(contenido),
        'estado': 'ok',
        'tools_usadas': [nombre_tool],
        'argumentos_normalizados': [{'tool': nombre_tool, 'argumentos': args}],
        'resultado_resumido': _resumen_resultados_tool([{
            'tool': nombre_tool,
            'argumentos': args,
            'resultado': resultado,
        }]),
    }


def _respuesta_directa_metricas(historial: list[dict], usuario) -> dict | None:
    consulta = _ultima_consulta_usuario(historial)
    texto = _normalizar_texto_consulta(consulta)
    metricas = ('ganancia neta', 'utilidad neta', 'ganancia bruta', 'utilidad bruta', 'margen bruto', 'resultado de caja', 'resultado caja', 'flujo de caja', 'diferencia de caja', 'cierre de caja')
    if not any(item in texto for item in metricas):
        return None
    if any(item in texto for item in ('diferencia entre', 'vs', 'versus', 'compar', 'distin', 'igual que')) and any(item in texto for item in ('ganancia', 'utilidad', 'resultado de caja', 'caja')):
        nombre_tool = 'metricas_comparacion_negocio'
        args = {'busqueda': consulta}
    elif any(item in texto for item in ('que es', 'q es', 'significa', 'defin', 'explicame', 'explica')):
        nombre_tool = 'metricas_explicacion_negocio'
        args = {'busqueda': consulta}
    elif any(item in texto for item in ('calcula', 'cuanto', 'cuanto fue', 'cual fue', 'resultado', 'resumen', 'como estuvo', 'como fue', 'mostrame', 'mostrar')):
        nombre_tool = 'metricas_resumen_operativo'
        args = normalizar_argumentos_temporales({'periodo': 'mes'}, consulta)
    else:
        nombre_tool = 'metricas_explicacion_negocio'
        args = {'busqueda': consulta}
    resultado = ejecutar_tool_backoffice(nombre_tool, args, usuario=usuario)
    contenido = _respuesta_directa_tool(nombre_tool, resultado)
    if not contenido:
        return None
    return {
        'tipo': 'texto',
        'contenido': _normalizar_respuesta_texto(contenido),
        'estado': 'ok',
        'tools_usadas': [nombre_tool],
        'argumentos_normalizados': [{'tool': nombre_tool, 'argumentos': args}],
        'resultado_resumido': _resumen_resultados_tool([{
            'tool': nombre_tool,
            'argumentos': args,
            'resultado': resultado,
        }]),
    }


def _respuesta_directa_fidelizacion(historial: list[dict], usuario) -> dict | None:
    consulta = _ultima_consulta_usuario(historial)
    texto = _normalizar_texto_consulta(consulta)
    if not any(token in texto for token in ('fideliz', 'programa de puntos', 'recompensa', 'canje', 'premio')):
        return None
    if 'modulo' in texto and _consulta_pide_explicar_modulo(texto):
        return None
    if any(token in texto for token in ('para que sirve', 'que es', 'que hace')):
        return None
    if not any(token in texto for token in ('regla', 'configur', 'activa', 'estado', 'beneficio', 'beneficios', 'saldo', 'vigencia')):
        return None
    nombre_tool = 'fidelizacion_resumen'
    args = {}
    resultado = ejecutar_tool_backoffice(nombre_tool, args, usuario=usuario)
    contenido = _respuesta_directa_tool(nombre_tool, resultado)
    if not contenido:
        return None
    return {
        'tipo': 'texto',
        'contenido': _normalizar_respuesta_texto(contenido),
        'estado': 'ok',
        'tools_usadas': [nombre_tool],
        'argumentos_normalizados': [{'tool': nombre_tool, 'argumentos': args}],
        'resultado_resumido': _resumen_resultados_tool([{
            'tool': nombre_tool,
            'argumentos': args,
            'resultado': resultado,
        }]),
    }


def _respuesta_directa_consulta(historial: list[dict], usuario) -> dict | None:
    consulta = _ultima_consulta_usuario(historial)
    consulta_lower = consulta.lower()
    if 'producto' not in consulta_lower and not any(t in consulta_lower for t in ('celular', 'celulares', 'telefono', 'android', 'accesorio', 'repuesto')):
        return None
    if not any(t in consulta_lower for t in ('que ', 'qué ', 'hay', 'tenes', 'tienes', 'lista', 'listar', 'mostrar')):
        return None
    termino = _termino_busqueda_productos(consulta)
    if not termino:
        return None
    resultado = ejecutar_tool_backoffice(
        'buscar_entidad_backoffice',
        {'busqueda': termino, 'top_n': 10},
        usuario=usuario,
    )
    contenido = _respuesta_directa_tool('buscar_entidad_backoffice', resultado)
    if not contenido:
        return None
    return {
        'tipo': 'texto',
        'contenido': _normalizar_respuesta_texto(contenido),
        'estado': 'ok',
        'tools_usadas': ['buscar_entidad_backoffice'],
        'argumentos_normalizados': [{'tool': 'buscar_entidad_backoffice', 'argumentos': {'busqueda': termino, 'top_n': 10}}],
        'resultado_resumido': _resumen_resultados_tool([{
            'tool': 'buscar_entidad_backoffice',
            'argumentos': {'busqueda': termino, 'top_n': 10},
            'resultado': resultado,
        }]),
    }


def _resumen_resultados_tool(resultados_tool: list[dict]) -> str:
    if not resultados_tool:
        return ''
    resumen = []
    for item in resultados_tool[:5]:
        resultado = item.get('resultado') if isinstance(item, dict) else {}
        data = resultado.get('data') if isinstance(resultado, dict) else None
        if isinstance(data, dict):
            claves = list(data.keys())[:8]
        else:
            claves = []
        resumen.append({
            'tool': item.get('tool'),
            'ok': resultado.get('ok') if isinstance(resultado, dict) else None,
            'error': resultado.get('error') if isinstance(resultado, dict) else None,
            'data_keys': claves,
        })
    return json.dumps(resumen, ensure_ascii=False, separators=(',', ':'), default=str)[:2000]


def _argumentos_tool(resultados_tool: list[dict]) -> list[dict]:
    return [
        {
            'tool': item.get('tool'),
            'argumentos': item.get('argumentos') or {},
        }
        for item in resultados_tool[:5]
        if isinstance(item, dict)
    ]


def generar_respuesta_backoffice(historial: list[dict], usuario, resumen_historial: str = '') -> dict:
    cfg = obtener_configuracion_asistente()
    if not cfg.enabled:
        return respuesta_no_disponible()
    cfg = _cfg_con_modelo_resuelto(cfg, historial)
    permitido, motivo_presupuesto = validar_presupuesto_tokens(cfg.max_tokens, usuario=usuario)
    if not permitido:
        return {
            'tipo': 'texto',
            'contenido': mensaje_presupuesto_excedido(motivo_presupuesto),
            'estado': motivo_presupuesto,
            'modelo': cfg.model,
            'provider': cfg.provider,
        }
    try:
        # Ayuda funcional: respuesta local sin API, cero tokens
        respuesta_directa = _respuesta_directa_ayuda(historial)
        if respuesta_directa:
            respuesta_directa.update({'modelo': 'local', 'provider': 'local'})
            return respuesta_directa

        respuesta_directa = _respuesta_directa_modulo(historial, usuario)
        if respuesta_directa:
            respuesta_directa.update({'modelo': cfg.model, 'provider': cfg.provider})
            return respuesta_directa

        respuesta_directa = _respuesta_directa_fidelizacion(historial, usuario)
        if respuesta_directa:
            respuesta_directa.update({'modelo': cfg.model, 'provider': cfg.provider})
            return respuesta_directa

        respuesta_directa = _respuesta_directa_metricas(historial, usuario)
        if respuesta_directa:
            respuesta_directa.update({'modelo': cfg.model, 'provider': cfg.provider})
            return respuesta_directa

        respuesta_directa = _respuesta_directa_consulta(historial, usuario)
        if respuesta_directa:
            respuesta_directa.update({'modelo': cfg.model, 'provider': cfg.provider})
            return respuesta_directa

        client, key_source = _crear_cliente(cfg.provider, cfg.deepseek_base_url)
        if client is None:
            return {
                'tipo': 'texto',
                'contenido': 'El asistente IA interno no tiene API key configurada todavia.',
                'estado': 'sin_api_key',
            }

        messages = _mensajes(historial, usuario, resumen_historial=resumen_historial)
        tools_modelo = seleccionar_tools_backoffice(historial)
        kwargs = _completion_kwargs(cfg, messages, tools=tools_modelo)

        logger.info(
            "IA backoffice request provider=%s model=%s key_source=%s tools_router=%s/%s",
            cfg.provider,
            cfg.model,
            key_source,
            len(tools_modelo),
            len(BACKOFFICE_TOOLS),
        )
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        usage_total = _usage_dict(response)
        tools_usadas = []

        if getattr(message, 'tool_calls', None):
            tool_messages, tools_usadas, resultados_tool = _ejecutar_tool_calls(message, usuario, _ultima_consulta_usuario(historial))
            argumentos_tool = _argumentos_tool(resultados_tool)
            resultado_resumido = _resumen_resultados_tool(resultados_tool)
            if len(resultados_tool) == 1:
                respuesta_directa = _respuesta_directa_tool(
                    resultados_tool[0]['tool'],
                    resultados_tool[0]['resultado'],
                )
                if respuesta_directa:
                    return {
                        'tipo': 'texto',
                        'contenido': _normalizar_respuesta_texto(respuesta_directa),
                        'estado': 'ok',
                        'modelo': cfg.model,
                        'provider': cfg.provider,
                        'tokens_prompt': usage_total['tokens_prompt'],
                        'tokens_completion': usage_total['tokens_completion'],
                        'tools_usadas': tools_usadas,
                        'argumentos_normalizados': argumentos_tool,
                        'resultado_resumido': resultado_resumido,
                    }
            messages.append(_assistant_tool_message(message))
            messages.extend(tool_messages)
            response = client.chat.completions.create(**_completion_kwargs(cfg, messages))
            message = response.choices[0].message
            usage_segunda = _usage_dict(response)
            usage_total['tokens_prompt'] += usage_segunda['tokens_prompt']
            usage_total['tokens_completion'] += usage_segunda['tokens_completion']
        elif _tool_calls_textuales(message.content or ''):
            text_message = SimpleNamespace(content='', tool_calls=_tool_calls_textuales(message.content or ''))
            _, tools_usadas, resultados_tool = _ejecutar_tool_calls(text_message, usuario, _ultima_consulta_usuario(historial))
            argumentos_tool = _argumentos_tool(resultados_tool)
            resultado_resumido = _resumen_resultados_tool(resultados_tool)
            if len(resultados_tool) == 1:
                respuesta_directa = _respuesta_directa_tool(
                    resultados_tool[0]['tool'],
                    resultados_tool[0]['resultado'],
                )
                if respuesta_directa:
                    return {
                        'tipo': 'texto',
                        'contenido': _normalizar_respuesta_texto(respuesta_directa),
                        'estado': 'ok',
                        'modelo': cfg.model,
                        'provider': cfg.provider,
                        'tokens_prompt': usage_total['tokens_prompt'],
                        'tokens_completion': usage_total['tokens_completion'],
                        'tools_usadas': tools_usadas,
                        'argumentos_normalizados': argumentos_tool,
                        'resultado_resumido': resultado_resumido,
                    }
            message = SimpleNamespace(content=_respuesta_resumen_tools_textuales(resultados_tool))

        contenido = _normalizar_respuesta_texto(message.content or '')
        if not contenido:
            contenido = 'No pude generar una respuesta clara. Proba reformular la pregunta.'
        return {
            'tipo': 'texto',
            'contenido': contenido,
            'estado': 'ok',
            'modelo': cfg.model,
            'provider': cfg.provider,
            'tokens_prompt': usage_total['tokens_prompt'],
            'tokens_completion': usage_total['tokens_completion'],
            'tools_usadas': tools_usadas,
            'argumentos_normalizados': argumentos_tool if tools_usadas else [],
            'resultado_resumido': resultado_resumido if tools_usadas else '',
        }
    except Exception as exc:
        logger.error("Error en IA backoffice (%s): %s", type(exc).__name__, exc, exc_info=True)
        return {
            'tipo': 'texto',
            'contenido': 'Hubo un error procesando la consulta del asistente interno.',
            'estado': 'error',
            'modelo': cfg.model,
            'provider': cfg.provider,
        }
