"""
Servicio de IA unificado (OpenAI-compatible).
Funciona con OpenAI, DeepSeek, o cualquier API compatible.
Configurar via variables de entorno:
  AI_PROVIDER=openai|deepseek
  AI_API_KEY=...
  AI_BASE_URL=https://api.openai.com/v1  (opcional, para providers alternativos)
  AI_MODEL=gpt-4o-mini
  AI_MAX_TOKENS=320
  AI_TEMPERATURE=0.7
  AI_ENABLED=1
"""
import os
import json
import logging
import base64
from openai import OpenAI

from app.services.ia.tools import WHATSAPP_TOOLS
from app.services.ia.prompts import SYSTEM_PROMPT_BOT
from app.services.ia.settings_resolver import clean_env_value, compact_prompt_context, get_setting, get_setting_bool, normalize_model_for_provider, safe_float, safe_int

logger = logging.getLogger(__name__)

DEFAULT_TEXT_MAX_TOKENS = 320
DEFAULT_VISION_MAX_TOKENS = 500
MAX_HISTORY_MESSAGES = 16


def _get_client_and_meta() -> tuple[OpenAI | None, dict]:
    ai_enabled, ai_enabled_raw, ai_enabled_source = get_setting_bool('ia_enabled', 'AI_ENABLED', default=False)
    provider, provider_source = get_setting('ia_provider', 'AI_PROVIDER', default='openai', clean=True)
    provider = provider.lower()
    if provider not in ('openai', 'deepseek'):
        provider = 'openai'

    ai_api_key, ai_api_key_source = get_setting('ia_api_key', 'AI_API_KEY', clean=True)
    openai_api_key, openai_api_key_source = get_setting('ia_openai_api_key', 'OPENAI_API_KEY', clean=True)
    deepseek_api_key, deepseek_api_key_source = get_setting('ia_deepseek_api_key', 'DEEPSEEK_API_KEY', clean=True)
    ai_base_url, ai_base_url_source_raw = get_setting('ia_base_url', 'AI_BASE_URL', clean=True)
    deepseek_base_url, deepseek_base_url_source_raw = get_setting(
        'ia_deepseek_base_url',
        'DEEPSEEK_BASE_URL',
        clean=True,
    )

    key_source = 'missing'
    api_key = ''
    if provider == 'deepseek':
        if deepseek_api_key:
            key_source = deepseek_api_key_source
            api_key = deepseek_api_key
        elif ai_api_key:
            key_source = ai_api_key_source
            api_key = ai_api_key
        elif openai_api_key:
            key_source = openai_api_key_source
            api_key = openai_api_key
    else:
        if openai_api_key:
            key_source = openai_api_key_source
            api_key = openai_api_key
        elif ai_api_key:
            key_source = ai_api_key_source
            api_key = ai_api_key
        elif deepseek_api_key:
            key_source = deepseek_api_key_source
            api_key = deepseek_api_key

    base_url_source = 'missing'
    base_url = ''
    if provider == 'deepseek':
        if deepseek_base_url:
            base_url_source = deepseek_base_url_source_raw
            base_url = deepseek_base_url
        elif ai_base_url:
            base_url_source = ai_base_url_source_raw
            base_url = ai_base_url
        else:
            base_url_source = 'provider_default'
            base_url = 'https://api.deepseek.com/v1'
    else:
        if ai_base_url:
            base_url_source = ai_base_url_source_raw
            base_url = ai_base_url
        elif deepseek_base_url:
            base_url_source = deepseek_base_url_source_raw
            base_url = deepseek_base_url

    if base_url:
        base_url = clean_env_value(base_url).rstrip('/')

    meta = {
        'ai_enabled_raw': ai_enabled_raw,
        'ai_enabled_source': ai_enabled_source,
        'provider': provider,
        'provider_source': provider_source,
        'base_url': base_url,
        'base_url_source': base_url_source,
        'key_source': key_source,
    }

    if not ai_enabled:
        return None, meta
    if not api_key:
        return None, meta

    try:
        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url), meta
        return OpenAI(api_key=api_key), meta
    except Exception as e:
        logger.error(
            "Error creando cliente IA (%s): %s (provider=%s, base_url=%s)",
            type(e).__name__,
            e,
            provider,
            base_url or "",
            exc_info=True,
        )
        return None, meta


def _get_client() -> OpenAI | None:
    client, _meta = _get_client_and_meta()
    if client is None:
        ai_enabled_raw = _meta.get('ai_enabled_raw')
        if (ai_enabled_raw or '').strip().lower() not in ('1', 'true', 'yes'):
            logger.warning(
                "IA deshabilitada por AI_ENABLED=%r (source=%s)",
                ai_enabled_raw,
                _meta.get('ai_enabled_source', 'unknown'),
            )
        else:
            logger.warning("IA sin API key (key_source=%s)", _meta.get('key_source', 'missing'))
    return client


def _get_model_config() -> dict:
    provider, _provider_source = get_setting('ia_provider', 'AI_PROVIDER', default='deepseek', clean=True)
    model_raw, _model_source = get_setting('ia_model', 'AI_MODEL', default='')
    max_tokens_raw, _max_tokens_source = get_setting(
        'ia_max_tokens',
        'AI_MAX_TOKENS',
        default=str(DEFAULT_TEXT_MAX_TOKENS),
    )
    temperature_raw, _temperature_source = get_setting('ia_temperature', 'AI_TEMPERATURE', default='0.7')
    model = normalize_model_for_provider(provider, model_raw)
    return {
        'model': model,
        'max_tokens': safe_int(max_tokens_raw, DEFAULT_TEXT_MAX_TOKENS),
        'temperature': safe_float(temperature_raw, 0.7),
    }


def _get_vision_client_and_meta() -> tuple[OpenAI | None, dict]:
    ai_enabled, ai_enabled_raw, ai_enabled_source = get_setting_bool('ia_enabled', 'AI_ENABLED', default=False)
    vision_enabled_raw = (os.environ.get('AI_VISION_ENABLED', '1') or '').strip().lower()

    openai_api_key, openai_api_key_source = get_setting('ia_openai_api_key', 'OPENAI_API_KEY', clean=True)
    deepseek_api_key, deepseek_api_key_source = get_setting('ia_deepseek_api_key', 'DEEPSEEK_API_KEY', clean=True)
    generic_api_key, generic_api_key_source = get_setting('ia_api_key', 'AI_API_KEY', clean=True)
    vision_api_key = clean_env_value(os.environ.get('AI_VISION_API_KEY'))

    openai_base_url, openai_base_url_source_raw = get_setting('ia_base_url', 'OPENAI_BASE_URL', clean=True)
    vision_base_url = clean_env_value(os.environ.get('AI_VISION_BASE_URL'))

    key_source = 'missing'
    api_key = ''
    if vision_api_key:
        key_source = 'AI_VISION_API_KEY'
        api_key = vision_api_key
    elif openai_api_key:
        key_source = openai_api_key_source
        api_key = openai_api_key
    elif deepseek_api_key:
        key_source = deepseek_api_key_source
        api_key = deepseek_api_key
    elif generic_api_key:
        key_source = generic_api_key_source
        api_key = generic_api_key

    base_url_source = 'default'
    base_url = ''
    if vision_base_url:
        base_url_source = 'AI_VISION_BASE_URL'
        base_url = vision_base_url
    elif openai_base_url:
        base_url_source = openai_base_url_source_raw
        base_url = openai_base_url

    if base_url:
        base_url = base_url.rstrip('/')

    meta = {
        'ai_enabled_raw': ai_enabled_raw,
        'ai_enabled_source': ai_enabled_source,
        'vision_enabled_raw': vision_enabled_raw,
        'base_url': base_url,
        'base_url_source': base_url_source,
        'key_source': key_source,
    }

    if not ai_enabled:
        return None, meta
    if vision_enabled_raw not in ('1', 'true', 'yes'):
        return None, meta
    if not api_key:
        return None, meta

    try:
        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url), meta
        return OpenAI(api_key=api_key), meta
    except Exception as e:
        logger.error(
            "Error creando cliente IA visión (%s): %s (base_url=%s)",
            type(e).__name__,
            e,
            base_url or "",
            exc_info=True,
        )
        return None, meta


def _get_vision_model_config() -> dict:
    return {
        'model': os.environ.get('AI_VISION_MODEL', 'gpt-5-mini'),
        'max_tokens': int(
            os.environ.get(
                'AI_VISION_MAX_TOKENS',
                os.environ.get('AI_MAX_TOKENS', str(DEFAULT_VISION_MAX_TOKENS)),
            )
        ),
    }


def _render_system_prompt(contexto: dict | None = None, system_prompt_template: str | None = None) -> str:
    contexto_compacto = compact_prompt_context(contexto or {})
    contexto_str = json.dumps(contexto_compacto, ensure_ascii=False, separators=(',', ':'), default=str)
    system_prompt_source = system_prompt_template or SYSTEM_PROMPT_BOT
    try:
        return system_prompt_source.replace('{contexto}', contexto_str)
    except Exception:
        return system_prompt_source.replace('{contexto}', str(contexto_compacto))


def _construir_mensajes(
    historial: list[dict],
    contexto: dict | None = None,
    system_prompt_template: str | None = None,
) -> list[dict]:
    """
    Construye la lista de mensajes para la API.
    Sanitiza el historial para garantizar que los tool_calls y tool_results
    estén correctamente emparejados (requisito de la API de OpenAI).
    """
    system_prompt = _render_system_prompt(contexto, system_prompt_template)

    def _str(value) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    # Sanitizar historial: garantizar que cada assistant con tool_calls
    # tenga sus tool_results correspondientes, y eliminar pares incompletos.
    sanitizado: list[dict] = []
    i = 0
    msgs = [m for m in historial if isinstance(m, dict) and m.get('role') != 'system']

    while i < len(msgs):
        msg = msgs[i]
        role = msg.get('role')

        if role == 'user':
            sanitizado.append({'role': 'user', 'content': _str(msg.get('content'))})
            i += 1

        elif role == 'assistant':
            tool_calls = msg.get('tool_calls')
            if not tool_calls:
                # Respuesta de texto normal
                sanitizado.append({'role': 'assistant', 'content': _str(msg.get('content'))})
                i += 1
            else:
                # Recolectar los tool_results que siguen
                needed_ids = {tc.get('id') for tc in tool_calls if tc.get('id')}
                tool_results = []
                j = i + 1
                while j < len(msgs) and msgs[j].get('role') == 'tool':
                    tr = msgs[j]
                    tc_id = tr.get('tool_call_id', '')
                    if tc_id in needed_ids:
                        tool_results.append({
                            'role': 'tool',
                            'tool_call_id': tc_id,
                            'content': _str(tr.get('content')),
                        })
                    j += 1

                seen_ids = {tr['tool_call_id'] for tr in tool_results}
                if needed_ids and needed_ids.issubset(seen_ids):
                    # Par completo: incluir assistant + tool_results
                    out_msg = {
                        'role': 'assistant',
                        'content': _str(msg.get('content')),
                        'tool_calls': tool_calls,
                    }
                    sanitizado.append(out_msg)
                    sanitizado.extend(tool_results)
                # Si el par está incompleto, descartarlo (evita errores de API)
                i = j  # Saltar los tool_results ya procesados

        elif role == 'tool':
            # Tool result sin assistant previo: descartar
            i += 1

        else:
            i += 1

    if len(sanitizado) > MAX_HISTORY_MESSAGES:
        sanitizado = sanitizado[-MAX_HISTORY_MESSAGES:]

    return [{'role': 'system', 'content': system_prompt}] + sanitizado


def generar_respuesta_personalizada(
    historial: list[dict],
    contexto: dict | None = None,
    system_prompt: str | None = None,
    tools: list[dict] | None = None,
) -> dict:
    """
    Genera una respuesta usando la IA con function calling.

    Retorna:
    {
        'tipo': 'texto' | 'tool_call',
        'contenido': str,           # Si tipo='texto'
        'tool_calls': [...],        # Si tipo='tool_call'
        'raw_message': dict,        # Si tipo='tool_call' (para agregar al historial)
    }
    """
    client, meta = _get_client_and_meta()
    if client is None:
        logger.warning(
            "IA no disponible (AI_ENABLED=%s, provider=%s, base_url=%s, base_url_source=%s, key_source=%s)",
            meta.get('ai_enabled_raw', ''),
            meta.get('provider', ''),
            meta.get('base_url', ''),
            meta.get('base_url_source', ''),
            meta.get('key_source', ''),
        )
        return {
            'tipo': 'texto',
            'contenido': 'El asistente no está disponible en este momento. Por favor intentá más tarde.',
        }

    cfg = _get_model_config()
    messages = _construir_mensajes(historial, contexto, system_prompt_template=system_prompt)

    try:
        model = cfg['model']
        provider = (meta.get('provider', '') or '').strip().lower()
        last_user = ''
        for m in reversed(messages):
            if m.get('role') == 'user':
                last_user = (m.get('content') or '').strip()
                break
        logger.info(
            "IA request (provider=%s, base_url=%s, model=%s, key_source=%s, msgs=%s, last_user=%r)",
            meta.get('provider', ''),
            meta.get('base_url', ''),
            model,
            meta.get('key_source', ''),
            len(messages),
            (last_user[:80] + '…') if len(last_user) > 80 else last_user,
        )
        kwargs: dict = {
            'model': model,
            'messages': messages,
        }
        if tools:
            kwargs['tools'] = tools

        # Parámetros según el modelo
        if provider != 'deepseek' and (model.startswith('o') or model.startswith('gpt-5')):
            # Modelos de razonamiento (o1, o3, gpt-5, etc.)
            kwargs['max_completion_tokens'] = cfg['max_tokens']
        else:
            kwargs['max_tokens'] = cfg['max_tokens']
            kwargs['temperature'] = cfg['temperature']

        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        usage = getattr(response, 'usage', None)
        if usage:
            logger.info(
                "IA usage: prompt=%s completion=%s total=%s",
                getattr(usage, 'prompt_tokens', '?'),
                getattr(usage, 'completion_tokens', '?'),
                getattr(usage, 'total_tokens', '?'),
            )

        # La IA quiere llamar tools
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    'id': tc.id,
                    'name': tc.function.name,
                    'arguments': args,
                })
            logger.info(f"IA solicita tools: {[t['name'] for t in tool_calls]}")
            return {
                'tipo': 'tool_call',
                'tool_calls': tool_calls,
                'raw_message': {
                    'role': 'assistant',
                    'content': message.content,
                    'tool_calls': [
                        {
                            'id': tc.id,
                            'type': 'function',
                            'function': {
                                'name': tc.function.name,
                                'arguments': tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                },
            }

        # Respuesta de texto
        contenido = (message.content or '').strip()
        if not contenido:
            logger.warning("IA retornó contenido vacío")
            contenido = 'No entendí bien tu consulta. ¿Podés decirme con más detalle qué necesitás?'

        logger.info(f"IA respuesta: {contenido[:120]}")
        return {'tipo': 'texto', 'contenido': contenido}

    except Exception as e:
        logger.error(f"Error en IA ({type(e).__name__}): {e}", exc_info=True)
        return {
            'tipo': 'texto',
            'contenido': 'Hubo un error procesando tu consulta. ¿Querés que te comunique con un asesor?',
        }


def generar_respuesta(historial: list[dict], contexto: dict | None = None) -> dict:
    return generar_respuesta_personalizada(
        historial,
        contexto=contexto,
        system_prompt=SYSTEM_PROMPT_BOT,
        tools=WHATSAPP_TOOLS,
    )


def generar_respuesta_con_tool_result(historial: list[dict], contexto: dict | None = None) -> dict:
    """Alias para compatibilidad. El historial ya incluye los tool_results."""
    return generar_respuesta(historial, contexto)


def analizar_imagen_producto(image_bytes: bytes, mime_type: str = 'image/jpeg', caption: str = '') -> dict:
    client, meta = _get_vision_client_and_meta()
    if client is None:
        return {
            'ok': False,
            'error': 'IA visión no disponible',
            'meta': meta,
        }

    cfg = _get_vision_model_config()
    model = cfg['model']
    max_tokens = cfg['max_tokens']

    b64 = base64.b64encode(image_bytes or b'').decode('ascii')
    data_url = f'data:{mime_type};base64,{b64}'

    prompt = (
        "Analizá la imagen y devolvé SOLO un JSON válido (sin texto extra).\n"
        "Objetivo: decir qué objeto/producto se ve y generar términos de búsqueda útiles para el catálogo.\n\n"
        "Campos del JSON:\n"
        "{\n"
        '  "item": {"categoria": "", "marca": "", "modelo": "", "nombre_comercial": ""},\n'
        '  "atributos": {"color": "", "material": "", "tamano": "", "compatibilidad": []},\n'
        '  "texto_en_imagen": "",\n'
        '  "palabras_clave_busqueda": [],\n'
        '  "alternativas": [{"posible": "", "por_que": ""}],\n'
        '  "confianza": {"global": 0, "marca": 0, "modelo": 0},\n'
        '  "notas": ""\n'
        "}\n\n"
        "Reglas importantes:\n"
        "- Primero identificá el objeto por su forma/uso en `item.categoria` (ej: 'termo', 'botella térmica', 'funda', 'cargador', 'celular').\n"
        "- Solo completes `marca`/`modelo` si se ven con claridad (texto/logos). Si no, dejalos vacíos.\n"
        "- Si NO es un producto de electrónica (por ejemplo termo/botella/vaso), NO inventes marcas/modelos de celulares.\n"
        "- `palabras_clave_busqueda` debe ser una lista corta (3-8) de términos en español para buscar en un inventario.\n"
        "- `confianza`: números 0 a 1 (0 = nada seguro, 1 = totalmente seguro).\n"
    )

    if caption:
        prompt += f'\nCaption del usuario (puede ayudar): {caption}\n'

    # Modelos de fallback si el principal falla o devuelve vacío
    _FALLBACK_VISION_MODELS = ['gpt-4o-mini']

    def _llamar_vision(vision_client: OpenAI, vision_model: str, vision_max_tokens: int) -> str:
        """Hace la llamada al modelo de visión y retorna el contenido de texto."""
        kw: dict = {
            'model': vision_model,
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {'url': data_url}},
                    ],
                }
            ],
        }
        # gpt-5-mini y gpt-5: usan reasoning_effort (no max_tokens ni max_completion_tokens)
        if vision_model.startswith('gpt-5'):
            kw['reasoning_effort'] = os.environ.get('AI_VISION_REASONING_EFFORT', 'low')
        elif vision_model.startswith('o'):
            kw['max_completion_tokens'] = vision_max_tokens
        else:
            kw['max_tokens'] = vision_max_tokens
        resp = vision_client.chat.completions.create(**kw)
        return (resp.choices[0].message.content or '').strip()

    def _parsear_contenido(contenido: str) -> dict | None:
        """Intenta parsear el JSON de la respuesta de visión."""
        if not contenido:
            return None
        json_str = contenido
        if '```' in contenido:
            import re
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', contenido)
            if m:
                json_str = m.group(1).strip()
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    try:
        content = _llamar_vision(client, model, max_tokens)
    except Exception as e:
        logger.error(f"Error en modelo visión principal {model} ({type(e).__name__}): {e}")
        content = ''

    data = _parsear_contenido(content)

    # Si el modelo principal falló o devolvió vacío → intentar modelos de fallback
    if not data:
        if content:
            logger.warning("Vision: no se pudo parsear JSON de la respuesta (modelo=%s). raw=%r", model, content[:200])
        else:
            logger.warning("Vision: modelo %s devolvió respuesta vacía. Intentando fallback.", model)

        for fb_model in _FALLBACK_VISION_MODELS:
            if fb_model == model:
                continue
            try:
                logger.info("Vision: intentando fallback con modelo=%s", fb_model)
                fb_content = _llamar_vision(client, fb_model, max_tokens)
                fb_data = _parsear_contenido(fb_content)
                if fb_data:
                    fb_data['ok'] = True
                    fb_data['_vision_model_usado'] = fb_model
                    logger.info(
                        "Vision OK (fallback=%s): categoria=%r marca=%r modelo=%r confianza=%r palabras=%r",
                        fb_model,
                        (fb_data.get('item') or {}).get('categoria', ''),
                        (fb_data.get('item') or {}).get('marca', ''),
                        (fb_data.get('item') or {}).get('modelo', ''),
                        (fb_data.get('confianza') or {}).get('global', '?'),
                        (fb_data.get('palabras_clave_busqueda') or [])[:4],
                    )
                    return fb_data
                elif fb_content:
                    logger.warning("Vision fallback %s: no se pudo parsear JSON. raw=%r", fb_model, fb_content[:200])
                else:
                    logger.warning("Vision fallback %s: respuesta vacía.", fb_model)
            except Exception as fe:
                logger.warning("Vision fallback %s falló (%s): %s", fb_model, type(fe).__name__, fe)

        # Todos los modelos fallaron
        return {
            'ok': False,
            'error': 'El modelo de visión no pudo analizar la imagen (respuesta vacía o inválida)',
        }

    data['ok'] = True
    data['_vision_model_usado'] = model
    logger.info(
        "Vision OK (modelo=%s): categoria=%r marca=%r modelo=%r confianza=%r palabras=%r",
        model,
        (data.get('item') or {}).get('categoria', ''),
        (data.get('item') or {}).get('marca', ''),
        (data.get('item') or {}).get('modelo', ''),
        (data.get('confianza') or {}).get('global', '?'),
        (data.get('palabras_clave_busqueda') or [])[:4],
    )
    return data
