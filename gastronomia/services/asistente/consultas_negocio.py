"""Consultas de negocio (ventas, caja, cobranzas, stock...) dentro del panel del asistente gastronomico.

Adaptador delgado sobre el Asistente IA interno (app.services.ia_backoffice): reutiliza sus tools de SOLO
LECTURA, su selector por intencion y sus chequeos de permiso por tool. No toca el motor del backoffice.
"""
from __future__ import annotations

import logging

from app.services.ia_backoffice.security import puede_usar_asistente_ia
from app.services.ia_backoffice.temporal_args import normalizar_argumentos_temporales
from app.services.ia_backoffice.tool_handlers import _puede_consultar_ventas, ejecutar_tool_backoffice
from app.services.ia_backoffice.tool_selector import DEFAULT_TOOLS, TOOL_INDEX, nombres_tools_relevantes
from gastronomia.services.asistente.definiciones import TOOLS as TOOLS_PANEL
from gastronomia.services.asistente.tools_ventas_local import (
    TOOLS_BACKOFFICE_REEMPLAZADAS,
    TOOLS_VENTAS_LOCAL,
    TOOLS_VENTAS_LOCAL_FN,
)

logger = logging.getLogger(__name__)

MAX_TOOLS_NEGOCIO = 16
MENSAJES_USUARIO_RUTEO = 2
# Si el selector no reconoce intencion devuelve sus tools por defecto (tablero, ventas, caja...). En el
# backoffice eso responde cosas como "cuanto vendi"; aca solo se usan si el mensaje habla del negocio,
# para que una charla de configuracion ("ponele 150 g de carne") quede igual que antes.
PISTAS_NEGOCIO = ('vend', 'gane', 'gano', 'recaud', 'plata', 'deuda', 'debe', 'cobr', 'pague', 'balance', 'resultado')
_NOMBRES_PANEL = {t['function']['name'] for t in TOOLS_PANEL}
# Para "donde esta / como hago" el panel ya tiene donde_esta con rutas reales de gastronomia.
_SOLO_SI_DICE_MODULO = {'modulo_funcionamiento'}


def habilitadas(usuario) -> bool:
    """Mismo permiso que el Asistente IA del topbar: sin el, el panel sigue solo con configuracion."""
    try:
        return puede_usar_asistente_ia(usuario)
    except Exception:  # noqa: BLE001 - un fallo de permisos nunca debe romper el chat de configuracion
        logger.exception('No se pudo validar el permiso del asistente IA')
        return False


def _ultimos_mensajes_usuario(historial: list[dict]) -> list[dict]:
    """Rutea solo por lo que escribio el usuario: las respuestas del asistente hablan de 'categorias'
    y 'productos' todo el tiempo y cargarian tools de ventas/stock sin que nadie las pida."""
    usuario = [m for m in historial or [] if m.get('role') == 'user' and (m.get('content') or '').strip()]
    return [{'role': 'user', 'content': m['content']} for m in usuario[-MENSAJES_USUARIO_RUTEO:]]


def nombres_seleccionados(historial: list[dict]) -> list[str]:
    recientes = _ultimos_mensajes_usuario(historial)
    if not recientes:
        return []
    nombres = nombres_tools_relevantes(recientes, max_tools=MAX_TOOLS_NEGOCIO)
    texto = ' '.join(m['content'] for m in recientes).lower()
    if nombres == [n for n in DEFAULT_TOOLS if n in TOOL_INDEX][:len(nombres)] and not any(p in texto for p in PISTAS_NEGOCIO):
        nombres = []
    dice_modulo = 'modulo' in recientes[-1]['content'].lower()
    salida = [
        n for n in nombres
        if n in TOOL_INDEX and n not in _NOMBRES_PANEL and n not in TOOLS_BACKOFFICE_REEMPLAZADAS
        and (dice_modulo or n not in _SOLO_SI_DICE_MODULO)
    ]
    # Si se habla de ventas/ganancia, van las versiones de gastronomia (por plato, con costo de recetas).
    if any(n.startswith(('ventas_', 'metricas_')) or n in TOOLS_BACKOFFICE_REEMPLAZADAS for n in nombres):
        salida += list(TOOLS_VENTAS_LOCAL_FN)
    return salida


_INDEX_LOCAL = {t['function']['name']: t for t in TOOLS_VENTAS_LOCAL}


def tools_para(historial: list[dict], usuario) -> tuple[list[dict], set[str]]:
    """Tools de negocio a sumar en esta ronda y el set de nombres para rutear su ejecucion."""
    if not habilitadas(usuario):
        return [], set()
    nombres = nombres_seleccionados(historial)
    return [_INDEX_LOCAL.get(n) or TOOL_INDEX[n] for n in nombres], set(nombres)


def ejecutar(nombre: str, args: dict, usuario, consulta: str = '', cliente_id: int | None = None) -> dict:
    try:
        args = normalizar_argumentos_temporales(args, consulta)
        if nombre in TOOLS_VENTAS_LOCAL_FN:
            if not _puede_consultar_ventas(usuario):
                return {'ok': False, 'error': 'sin_permiso_ventas', 'tool': nombre}
            return {'ok': True, 'data': TOOLS_VENTAS_LOCAL_FN[nombre](int(cliente_id), args)}
        return ejecutar_tool_backoffice(nombre, args, usuario=usuario)
    except Exception as exc:  # noqa: BLE001 - nunca romper el chat por una consulta
        logger.exception('Error en consulta de negocio %s desde el asistente gastronomia', nombre)
        return {'ok': False, 'error': type(exc).__name__, 'tool': nombre}


PROMPT_NEGOCIO = """

Consultas del negocio (ventas, caja, cobranzas, stock, gastos, clientes, pedidos, empleados):
- Ademas de configurar, en esta charla tenes tools de SOLO LECTURA del Asistente IA del sistema
  (nombres como ventas_*, caja_*, cobranzas_*, inventario_*, gastos_*, clientes_*, dashboard_operativo_hoy).
- Usalas solo cuando el usuario pregunte por resultados o el estado del negocio (cuanto vendi, como esta la caja,
  que tengo que reponer, quien me debe). Para cargar o revisar el menu, insumos, recetas y mesas segui usando
  las tools del local (ver_menu, ver_insumos, ver_plato, estado_configuracion, guardar_*).
- La fecha de hoy es {fecha}: usala para interpretar hoy, ayer, esta semana, este mes.
- Montos en guaranies: escribi "Gs." y separador de miles (ej. Gs. 1.250.000), nunca "$".
- Para platos mas vendidos usa platos_mas_vendidos; para ganancia, margen o rentabilidad usa ganancia_del_local
  (sale de los pedidos cobrados y el costo de las recetas). Si un dato no aparece en las tools, decilo; no inventes la causa.
- Si una consulta devuelve sin_permiso_*, deci que ese usuario no tiene acceso a esos datos; no adivines numeros.
- Estas consultas no modifican nada: no digas que cobraste, anulaste ni cambiaste datos."""


def prompt_extra() -> str:
    from app.utils.helpers import today_local

    return PROMPT_NEGOCIO.format(fecha=today_local().isoformat())
