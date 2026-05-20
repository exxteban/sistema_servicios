"""
Insights diarios del backoffice basados en tools reales.
"""
import json
import logging

from app.utils.helpers import today_local
from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.response_engine import _crear_cliente


logger = logging.getLogger(__name__)

INSIGHT_TOOLS = (
    ('ventas_top_productos', {'periodo': '7d', 'top_n': 3}),
    ('inventario_productos_baja_rotacion', {'periodo': '30d', 'top_n': 3}),
    ('clientes_top_valor', {'periodo': '30d', 'top_n': 3}),
    ('reparaciones_fallas_frecuentes', {'periodo': '30d', 'top_n': 3}),
    ('inventario_productos_reponer', {'top_n': 3}),
)


def _money(value) -> str:
    try:
        monto = float(value or 0)
    except Exception:
        monto = 0
    return f"Gs. {monto:,.0f}".replace(',', '.')


def _payload(tool_name: str, args: dict, result: dict) -> dict:
    data = result.get('data') if isinstance(result, dict) else {}
    return {
        'tool': tool_name,
        'argumentos': args,
        'data': data if isinstance(data, dict) else {},
    }


def _insight(
    kind: str,
    title: str,
    body: str,
    action: str,
    source: dict,
    priority: int,
) -> dict:
    return {
        'tipo': kind,
        'titulo': title,
        'texto': body,
        'accion_sugerida': action,
        'prioridad': priority,
        'source_tool': source.get('tool'),
        'source_payload': source,
        'generado_por': 'tools',
    }


def _from_top_productos(source: dict) -> list[dict]:
    productos = source.get('data', {}).get('productos') or []
    if not productos:
        return []
    top = productos[0]
    nombre = top.get('nombre') or 'Producto sin nombre'
    unidades = int(top.get('unidades') or 0)
    ingreso = _money(top.get('ingreso'))
    return [_insight(
        'ventas_top_producto',
        'Producto que viene empujando ventas',
        f'{nombre} lidera los ultimos 7 dias con {unidades} unidades y {ingreso} vendidos.',
        'Revisar stock y margen antes de que se corte la rotacion.',
        source,
        90,
    )]


def _from_clientes_fieles(source: dict) -> list[dict]:
    clientes = source.get('data', {}).get('clientes') or []
    if not clientes:
        return []
    top = clientes[0]
    nombre = top.get('nombre') or 'Cliente sin nombre'
    compras = int(top.get('cantidad_compras') or 0)
    total = _money(top.get('total_gastado'))
    return [_insight(
        'cliente_fiel',
        'Cliente fiel detectado',
        f'{nombre} fue el cliente de mayor valor en 30 dias: {compras} compras por {total}.',
        'Mirar si conviene agradecer, ofrecer preventa o guardar preferencia.',
        source,
        80,
    )]


def _from_fallas(source: dict) -> list[dict]:
    fallas = source.get('data', {}).get('fallas') or []
    if not fallas:
        return []
    top = fallas[0]
    falla = (top.get('falla') or '').strip()
    if not falla:
        return []
    cantidad = int(top.get('cantidad') or 0)
    return [_insight(
        'reparacion_frecuente',
        'Falla frecuente en taller',
        f'La falla mas repetida en 30 dias fue "{falla}", con {cantidad} ingreso(s).',
        'Verificar repuestos, tiempos de diagnostico y precio del servicio.',
        source,
        70,
    )]


def _from_stock(source: dict) -> list[dict]:
    productos = source.get('data', {}).get('productos') or []
    if not productos:
        return []
    top = productos[0]
    nombre = top.get('nombre') or 'Producto sin nombre'
    actual = int(top.get('stock_actual') or 0)
    minimo = int(top.get('stock_minimo') or 0)
    sugeridas = int(top.get('unidades_sugeridas') or max(minimo - actual, 0))
    return [_insight(
        'stock_bajo',
        'Stock para revisar',
        f'{nombre} esta en {actual} unidades, con minimo configurado de {minimo}.',
        f'Reponer al menos {sugeridas} unidad(es) o ajustar el stock minimo si ya no aplica.',
        source,
        85,
    )]


def _clasificacion_label(value: str) -> str:
    labels = {
        'producto_muerto': 'producto sin movimiento',
        'producto_lento': 'producto lento',
        'exceso_stock': 'exceso de stock',
    }
    return labels.get(value or '', 'baja rotacion')


def _from_baja_rotacion(source: dict) -> list[dict]:
    productos = source.get('data', {}).get('productos') or []
    if not productos:
        return []
    top = productos[0]
    nombre = top.get('nombre') or 'Producto sin nombre'
    stock = int(top.get('stock_actual') or 0)
    unidades = int(top.get('unidades_periodo') or 0)
    valor = _money(top.get('valor_stock_costo'))
    periodo = source.get('data', {}).get('periodo_label') or 'el periodo analizado'
    clasificacion = _clasificacion_label(top.get('clasificacion'))
    accion = top.get('accion_recomendada') or 'Revisar precio, visibilidad y reposicion.'
    return [_insight(
        'producto_baja_rotacion',
        'Producto para ofertar o rematar',
        f'{nombre} figura como {clasificacion}: quedan {stock} unidad(es), vendio {unidades} en {periodo} y retiene {valor} a costo.',
        accion,
        source,
        88,
    )]


BUILDERS = {
    'ventas_top_productos': _from_top_productos,
    'inventario_productos_baja_rotacion': _from_baja_rotacion,
    'clientes_top_valor': _from_clientes_fieles,
    'reparaciones_fallas_frecuentes': _from_fallas,
    'inventario_productos_reponer': _from_stock,
}


def _fallback_insights(sources: list[dict]) -> list[dict]:
    return [_insight(
        'sin_datos_suficientes',
        'Todavia no hay un patron fuerte',
        'Las tools consultadas no encontraron datos suficientes para destacar ventas, clientes o reparaciones.',
        'Registrar ventas, clientes y reparaciones con detalle mejora los proximos insights.',
        {'tool': 'daily_insights_tools', 'data': {'sources': sources}},
        10,
    )]


def _build_candidates(sources: list[dict]) -> list[dict]:
    insights = []
    for source in sources:
        builder = BUILDERS.get(source.get('tool'))
        if not builder:
            continue
        insights.extend(builder(source))
    insights.sort(key=lambda item: int(item.get('prioridad') or 0), reverse=True)
    return insights[:4] or _fallback_insights(sources)


def _priorizar_con_ia(candidates: list[dict], usuario) -> list[dict]:
    cfg = obtener_configuracion_asistente()
    if not cfg.enabled:
        return candidates
    client, _key_source = _crear_cliente(cfg.provider, cfg.deepseek_base_url)
    if client is None:
        return candidates
    facts = json.dumps([
        {
            'source_tool': item.get('source_tool'),
            'tipo': item.get('tipo'),
            'titulo': item.get('titulo'),
            'prioridad': item.get('prioridad'),
        }
        for item in candidates
    ], ensure_ascii=False, default=str)
    messages = [
        {
            'role': 'system',
            'content': (
                'Prioriza insights diarios en JSON. No redactes hechos nuevos ni agregues datos. '
                'Devuelve solo {"orden":["source_tool", "..."]} usando source_tool existentes.'
            ),
        },
        {'role': 'user', 'content': facts[:9000]},
    ]
    kwargs = {'model': cfg.model, 'messages': messages}
    if cfg.provider != 'deepseek' and (cfg.model.startswith('o') or cfg.model.startswith('gpt-5')):
        kwargs['max_completion_tokens'] = min(cfg.max_tokens, 900)
    else:
        kwargs['max_tokens'] = min(cfg.max_tokens, 900)
        kwargs['temperature'] = min(cfg.temperature, 0.2)
    try:
        response = client.chat.completions.create(**kwargs)
        raw = (response.choices[0].message.content or '').strip()
        parsed = json.loads(raw)
        orden = parsed.get('orden') if isinstance(parsed, dict) else None
        if not isinstance(orden, list):
            return candidates
    except Exception as exc:
        logger.info("No se pudo priorizar insight diario con IA: %s", type(exc).__name__)
        return candidates
    by_tool = {item.get('source_tool'): item for item in candidates}
    priorizados = []
    for tool_name in orden:
        item = by_tool.get(str(tool_name))
        if item and item not in priorizados:
            priorizados.append({**item, 'generado_por': 'ia_tools'})
    for item in candidates:
        if item not in priorizados:
            priorizados.append(item)
    return priorizados[:len(candidates)]


def generar_insights_diarios(usuario, *, usar_ia: bool = True) -> dict:
    sources = []
    tools_usadas = []
    for tool_name, args in INSIGHT_TOOLS:
        result = ejecutar_tool_backoffice(tool_name, dict(args), usuario=usuario)
        if result.get('ok'):
            sources.append(_payload(tool_name, args, result))
            tools_usadas.append(tool_name)
    candidates = _build_candidates(sources)
    insights = _priorizar_con_ia(candidates, usuario) if usar_ia else candidates
    return {
        'fecha': today_local().isoformat(),
        'insights': insights,
        'tools_usadas': tools_usadas,
        'generado_por': 'ia_tools' if any(i.get('generado_por') == 'ia_tools' for i in insights) else 'tools',
    }
