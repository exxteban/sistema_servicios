"""Loop de conversacion con tools (multi-ronda) del asistente gastronomico.

Las tools de escritura NO se ejecutan aca: se convierten en una propuesta que el usuario
confirma con un boton (ver propuestas.py). Reutiliza la configuracion, el cliente DeepSeek/OpenAI, el presupuesto de tokens
y la auditoria del asistente IA interno (app.services.ia_backoffice).
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace

from app.services.ia_backoffice.limits import mensaje_presupuesto_excedido, validar_presupuesto_tokens
from app.services.ia_backoffice.response_engine import (
    _assistant_tool_message,
    _completion_kwargs,
    _crear_cliente,
    _usage_dict,
)
from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from gastronomia.services.asistente import consultas_negocio, propuestas
from gastronomia.services.asistente.contexto_pantalla import etiqueta_contexto
from gastronomia.services.asistente.definiciones import TOOLS
from gastronomia.services.asistente.ejecutor import ejecutar_tool, guardo_algo as _guardo_algo  # noqa: F401
from gastronomia.services.asistente.prompt import SYSTEM_PROMPT
from gastronomia.services.asistente.tools_escritura import TOOLS_ESCRITURA

logger = logging.getLogger(__name__)
MAX_RONDAS = 8
MAX_HISTORIAL = 16
MIN_MAX_TOKENS = 4000
MAX_RESULTADO_CHARS = 12000


def _contenido(mensaje: dict) -> str:
    texto = (mensaje.get('content') or '')[:6000]
    if mensaje.get('role') != 'user':
        return texto
    etiqueta = etiqueta_contexto(mensaje.get('contexto'))
    return f'{etiqueta}\n{texto}' if etiqueta else texto


def _mensajes(historial: list[dict]) -> list[dict]:
    limpio = [
        {'role': m['role'], 'content': _contenido(m)}
        for m in historial[-MAX_HISTORIAL:]
        if m.get('role') in {'user', 'assistant'} and (m.get('content') or '').strip()
    ]
    return [{'role': 'system', 'content': SYSTEM_PROMPT}] + limpio


def _respuesta(contenido: str, estado: str, cfg=None, **extra) -> dict:
    return {
        'contenido': contenido,
        'estado': estado,
        'modelo': getattr(cfg, 'model', '') if cfg else '',
        'provider': getattr(cfg, 'provider', '') if cfg else '',
        **extra,
    }


def generar_respuesta(historial: list[dict], cliente_id: int, usuario) -> dict:
    cfg = obtener_configuracion_asistente()
    if not cfg.enabled:
        return _respuesta('El asistente IA esta desactivado. Pedile al usuario root que lo habilite en Configuracion IA.', 'desactivado')
    cfg = replace(cfg, max_tokens=max(int(cfg.max_tokens or 0), MIN_MAX_TOKENS))
    permitido, motivo = validar_presupuesto_tokens(cfg.max_tokens, usuario=usuario)
    if not permitido:
        return _respuesta(mensaje_presupuesto_excedido(motivo), motivo, cfg)
    client, _ = _crear_cliente(cfg.provider, cfg.deepseek_base_url)
    if client is None:
        return _respuesta('El asistente IA no tiene API key configurada todavia.', 'sin_api_key', cfg)

    usage = {'tokens_prompt': 0, 'tokens_completion': 0}
    tools_usadas, acciones = [], []
    pendientes = propuestas.nuevas_pendientes()
    usuario_id = getattr(usuario, 'id_usuario', None)
    # Consultas de negocio del Asistente IA del topbar (solo lectura), elegidas por lo que pide el usuario.
    tools_negocio, nombres_negocio = consultas_negocio.tools_para(historial, usuario)
    tools_modelo = TOOLS + tools_negocio
    messages = _mensajes(historial)
    if tools_negocio:
        messages[0]['content'] += consultas_negocio.prompt_extra()
    consulta = next((m.get('content') or '' for m in reversed(historial) if m.get('role') == 'user'), '')
    try:
        for _ in range(MAX_RONDAS):
            response = client.chat.completions.create(**_completion_kwargs(cfg, messages, tools=tools_modelo))
            for clave, valor in _usage_dict(response).items():
                usage[clave] += valor
            message = response.choices[0].message
            if not getattr(message, 'tool_calls', None):
                contenido = (message.content or '').replace('**', '').strip()
                return _respuesta(contenido or 'Listo.', 'ok', cfg, tools_usadas=tools_usadas, acciones=acciones, **usage)
            messages.append(_assistant_tool_message(message))
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or '{}')
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                if tc.function.name in TOOLS_ESCRITURA:
                    resultado = propuestas.preparar(tc.function.name, args, cliente_id, pendientes, acciones)
                elif tc.function.name in nombres_negocio:
                    resultado = consultas_negocio.ejecutar(tc.function.name, args, usuario, consulta, cliente_id)
                else:
                    resultado = ejecutar_tool(tc.function.name, args, cliente_id, usuario_id)
                tools_usadas.append(tc.function.name)
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.id,
                    'content': json.dumps(resultado, ensure_ascii=False, default=str)[:MAX_RESULTADO_CHARS],
                })
        return _respuesta('Hice varios pasos y corte para no gastar de mas. Decime "segui" para continuar.',
                          'limite_rondas', cfg, tools_usadas=tools_usadas, acciones=acciones, **usage)
    except Exception as exc:  # noqa: BLE001
        logger.error('Error asistente gastronomia (%s): %s', type(exc).__name__, exc, exc_info=True)
        return _respuesta('Hubo un error hablando con la IA. Proba de nuevo en un momento.', 'error', cfg,
                          tools_usadas=tools_usadas, acciones=acciones, **usage)
