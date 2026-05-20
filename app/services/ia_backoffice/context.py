"""
Contexto minimo para prompts del asistente interno.
"""
from datetime import date

from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS
from app.utils.helpers import get_app_timezone_name, today_local


def _restar_meses(fecha: date, meses: int) -> date:
    mes_total = fecha.month - int(meses or 0)
    anio = fecha.year + (mes_total - 1) // 12
    mes = (mes_total - 1) % 12 + 1
    dias_mes = [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(anio, mes, min(fecha.day, dias_mes[mes - 1]))


def _contexto_temporal() -> dict:
    hoy = today_local()
    return {
        'fecha_actual_local': hoy.isoformat(),
        'anio_actual': hoy.year,
        'mes_actual': hoy.month,
        'zona_horaria': get_app_timezone_name(),
        'rangos_referencia': {
            'ultimos_30_dias': {
                'periodo': '30d',
                'hasta': hoy.isoformat(),
            },
            'ultimos_2_meses_desde_hoy': {
                'periodo': 'custom',
                'desde': _restar_meses(hoy, 2).isoformat(),
                'hasta': hoy.isoformat(),
            },
            'anio_actual_hasta_hoy': {
                'periodo': 'custom',
                'desde': date(hoy.year, 1, 1).isoformat(),
                'hasta': hoy.isoformat(),
            },
        },
    }


def construir_contexto_minimo(usuario) -> dict:
    cfg = obtener_configuracion_asistente()
    return {
        'usuario': {
            'id_usuario': getattr(usuario, 'id_usuario', None),
            'username': getattr(usuario, 'username', ''),
            'rol': getattr(getattr(usuario, 'rol', None), 'nombre', ''),
        },
        'tiempo': _contexto_temporal(),
        'modo': 'solo_lectura' if cfg.readonly_mode else 'acciones_controladas',
        'tools_habilitadas': True,
        'cantidad_tools': len(BACKOFFICE_TOOLS),
        'acciones_asistidas_habilitadas': bool(cfg.assisted_actions_enabled),
        'readonly_mode': bool(cfg.readonly_mode),
        'modelo_avanzado_habilitado': bool(cfg.advanced_model_enabled),
    }
