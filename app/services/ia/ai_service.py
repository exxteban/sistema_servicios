"""
Servicio de IA - proxy a gpt_service (OpenAI-compatible).
Soporta OpenAI, DeepSeek y cualquier API compatible vía AI_BASE_URL.
"""
from app.services.ia.gpt_service import generar_respuesta, generar_respuesta_con_tool_result

__all__ = ['generar_respuesta', 'generar_respuesta_con_tool_result']
