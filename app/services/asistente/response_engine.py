"""
Motor de diálogo con tools para el asistente compartido.
"""
import json

from app.services.ia.gpt_service import generar_respuesta_personalizada


def _build_actions(tool_name: str, tool_result: dict) -> list[dict]:
    if tool_name != 'solicitar_handoff_whatsapp':
        return []
    if not isinstance(tool_result, dict) or not tool_result.get('solicitar_handoff'):
        return []
    return [{
        'type': 'handoff_whatsapp',
        'label': 'Seguir por WhatsApp',
        'motivo': tool_result.get('motivo') or 'Continuar por WhatsApp',
    }]


def generar_dialogo_asistente(
    historial: list[dict],
    contexto_ia: dict,
    system_prompt: str,
    tools: list[dict],
    tool_executor,
    max_cycles: int = 3,
) -> dict:
    working_history = list(historial)
    tool_events = []
    actions = []

    for _ in range(max_cycles):
        respuesta = generar_respuesta_personalizada(
            working_history,
            contexto=contexto_ia,
            system_prompt=system_prompt,
            tools=tools,
        )
        if respuesta['tipo'] == 'texto':
            return {
                'texto': respuesta['contenido'],
                'acciones': actions,
                'tool_events': tool_events,
            }

        raw_message = respuesta.get('raw_message')
        if raw_message:
            working_history.append(raw_message)
            tool_events.append({
                'kind': 'assistant_tool_call',
                'raw_message': raw_message,
            })

        for tool_call in respuesta.get('tool_calls', []):
            tool_result = tool_executor(tool_call.get('name'), tool_call.get('arguments') or {})
            actions.extend(_build_actions(tool_call.get('name') or '', tool_result))
            tool_result_message = {
                'role': 'tool',
                'tool_call_id': tool_call['id'],
                'content': json.dumps(tool_result, ensure_ascii=False, default=str),
            }
            working_history.append(tool_result_message)
            tool_events.append({
                'kind': 'tool_result',
                'tool_call_id': tool_call['id'],
                'tool_name': tool_call.get('name'),
                'tool_result': tool_result,
            })

    return {
        'texto': 'Hubo un problema procesando tu consulta. ¿Querés seguir por WhatsApp?',
        'acciones': actions or [{
            'type': 'handoff_whatsapp',
            'label': 'Seguir por WhatsApp',
            'motivo': 'Fallback por demasiados ciclos',
        }],
        'tool_events': tool_events,
    }
