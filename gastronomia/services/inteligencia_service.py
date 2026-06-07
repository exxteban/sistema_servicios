"""Inteligencia accionable para el modulo Gastronomia."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func

from app import db
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaPedidoItemModificador,
    GastronomiaPedidoPago,
    GastronomiaProducto,
)
from gastronomia.services.inteligencia_promos import promociones_horario_bajo
from gastronomia.services.inteligencia_stock import alertas_stock_menu


def obtener_inteligencia_gastronomia(periodo_actual: dict, periodo_anterior: dict, cliente_id: int | None = None) -> dict:
    cliente_id_resuelto = _resolver_cliente_id(cliente_id)
    if not cliente_id_resuelto:
        return _panel_vacio(periodo_actual)

    resumen_actual = _resumen_periodo(cliente_id_resuelto, periodo_actual)
    resumen_anterior = _resumen_periodo(cliente_id_resuelto, periodo_anterior)
    productos = _productos_top(cliente_id_resuelto, periodo_actual, periodo_anterior)
    categorias = _categorias_top(cliente_id_resuelto, periodo_actual)
    canales = _canales(cliente_id_resuelto, periodo_actual)
    modificadores = _modificadores_top(cliente_id_resuelto, periodo_actual)
    horarios = _horarios_pico(cliente_id_resuelto, periodo_actual)
    stock_menu = alertas_stock_menu(cliente_id_resuelto, periodo_actual)
    promos_horario_bajo = promociones_horario_bajo(cliente_id_resuelto, periodo_actual, productos)
    insights = _construir_insights(resumen_actual, resumen_anterior, productos, canales, horarios)

    return {
        'activo': True,
        'cliente_id': cliente_id_resuelto,
        'periodo_label': _formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': _serializar_resumen(resumen_actual, resumen_anterior),
        'productos_top': productos,
        'categorias_top': categorias,
        'canales': canales,
        'modificadores_top': modificadores,
        'horarios_pico': horarios,
        'stock_menu_alertas': stock_menu,
        'promos_horario_bajo': promos_horario_bajo,
        'insights': insights,
    }


def _resolver_cliente_id(cliente_id: int | None) -> int | None:
    if cliente_id:
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=int(cliente_id)).first()
        if config and bool(config.gastronomia_activo):
            return int(cliente_id)

    configs = (
        GastronomiaClienteConfig.query
        .filter(GastronomiaClienteConfig.gastronomia_activo.is_(True))
        .limit(2)
        .all()
    )
    if len(configs) == 1:
        return int(configs[0].cliente_id)
    return None


def _resumen_periodo(cliente_id: int, periodo: dict) -> dict:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    fila = (
        db.session.query(
            func.coalesce(func.sum(GastronomiaPedidoPago.total_cobrado), 0).label('ventas_total'),
            func.count(GastronomiaPedidoPago.id_pago).label('pedidos_cobrados'),
            func.coalesce(func.sum(GastronomiaPedidoPago.descuento_monto), 0).label('descuentos_total'),
        )
        .filter(
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .first()
    )
    ventas_total = float(getattr(fila, 'ventas_total', 0) or 0)
    pedidos_cobrados = int(getattr(fila, 'pedidos_cobrados', 0) or 0)
    return {
        'ventas_total': ventas_total,
        'pedidos_cobrados': pedidos_cobrados,
        'descuentos_total': float(getattr(fila, 'descuentos_total', 0) or 0),
        'ticket_promedio': ventas_total / pedidos_cobrados if pedidos_cobrados else 0,
        'tiempo_preparacion_min': _tiempo_preparacion_promedio(cliente_id, inicio, fin),
        'pedidos_cancelados': _pedidos_cancelados(cliente_id, inicio, fin),
    }


def _serializar_resumen(actual: dict, anterior: dict) -> dict:
    ventas_variacion = _calcular_variacion(actual['ventas_total'], anterior['ventas_total'])
    ticket_variacion = _calcular_variacion(actual['ticket_promedio'], anterior['ticket_promedio'])
    return {
        **actual,
        'ventas_total_label': _formatear_moneda(actual['ventas_total']),
        'ticket_promedio_label': _formatear_moneda(actual['ticket_promedio']),
        'ventas_variacion_label': ventas_variacion['label'],
        'ventas_direccion': ventas_variacion['direccion'],
        'ticket_variacion_label': ticket_variacion['label'],
        'ticket_direccion': ticket_variacion['direccion'],
    }


def _productos_top(cliente_id: int, periodo_actual: dict, periodo_anterior: dict, limite: int = 8) -> list[dict]:
    actuales = _productos_periodo(cliente_id, periodo_actual, limite=limite)
    anteriores = {item['producto_id']: item for item in _productos_periodo(cliente_id, periodo_anterior, limite=50)}
    total_periodo = sum(item['total'] for item in actuales)
    resultado = []
    for item in actuales:
        anterior = anteriores.get(item['producto_id'], {})
        variacion = _calcular_variacion(item['cantidad'], anterior.get('cantidad', 0))
        participacion = (item['total'] / total_periodo * 100) if total_periodo > 0 else 0
        resultado.append({
            **item,
            'total_label': _formatear_moneda(item['total']),
            'participacion_label': f'{participacion:.1f}%',
            'variacion_label': variacion['label'],
            'direccion': variacion['direccion'],
            'accion': _accion_producto_top(item, variacion['direccion']),
        })
    return resultado


def _productos_periodo(cliente_id: int, periodo: dict, limite: int) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    filas = (
        db.session.query(
            GastronomiaPedidoItem.producto_id,
            GastronomiaPedidoItem.nombre_producto,
            func.coalesce(func.sum(GastronomiaPedidoItem.cantidad), 0).label('cantidad'),
            func.coalesce(func.sum(GastronomiaPedidoItem.subtotal), 0).label('total'),
        )
        .join(GastronomiaPedido, GastronomiaPedido.id_pedido == GastronomiaPedidoItem.pedido_id)
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaPedidoItem.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .group_by(GastronomiaPedidoItem.producto_id, GastronomiaPedidoItem.nombre_producto)
        .order_by(func.sum(GastronomiaPedidoItem.cantidad).desc(), func.sum(GastronomiaPedidoItem.subtotal).desc())
        .limit(max(1, min(50, int(limite or 8))))
        .all()
    )
    return [{
        'producto_id': int(producto_id or 0),
        'nombre': nombre,
        'cantidad': int(cantidad or 0),
        'total': float(total or 0),
    } for producto_id, nombre, cantidad, total in filas]


def _categorias_top(cliente_id: int, periodo: dict, limite: int = 6) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    filas = (
        db.session.query(
            GastronomiaCategoria.nombre,
            func.coalesce(func.sum(GastronomiaPedidoItem.cantidad), 0).label('cantidad'),
            func.coalesce(func.sum(GastronomiaPedidoItem.subtotal), 0).label('total'),
        )
        .join(GastronomiaProducto, GastronomiaProducto.categoria_id == GastronomiaCategoria.id_categoria)
        .join(GastronomiaPedidoItem, GastronomiaPedidoItem.producto_id == GastronomiaProducto.id_producto)
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedidoItem.pedido_id)
        .filter(
            GastronomiaCategoria.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .group_by(GastronomiaCategoria.id_categoria, GastronomiaCategoria.nombre)
        .order_by(func.sum(GastronomiaPedidoItem.subtotal).desc())
        .limit(max(1, min(20, int(limite or 6))))
        .all()
    )
    total_general = sum(float(total or 0) for _nombre, _cantidad, total in filas)
    return [{
        'nombre': nombre or 'Sin categoria',
        'cantidad': int(cantidad or 0),
        'total': float(total or 0),
        'total_label': _formatear_moneda(float(total or 0)),
        'participacion_label': f'{(float(total or 0) / total_general * 100):.1f}%' if total_general else '0.0%',
    } for nombre, cantidad, total in filas]


def _canales(cliente_id: int, periodo: dict) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    filas = (
        db.session.query(
            GastronomiaPedido.tipo_pedido,
            func.count(GastronomiaPedidoPago.id_pago).label('pedidos'),
            func.coalesce(func.sum(GastronomiaPedidoPago.total_cobrado), 0).label('total'),
        )
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .group_by(GastronomiaPedido.tipo_pedido)
        .order_by(func.sum(GastronomiaPedidoPago.total_cobrado).desc())
        .all()
    )
    total_general = sum(float(total or 0) for _canal, _pedidos, total in filas)
    return [{
        'canal': canal or 'mostrador',
        'canal_label': _canal_label(canal),
        'pedidos': int(pedidos or 0),
        'total': float(total or 0),
        'total_label': _formatear_moneda(float(total or 0)),
        'participacion_label': f'{(float(total or 0) / total_general * 100):.1f}%' if total_general else '0.0%',
    } for canal, pedidos, total in filas]


def _modificadores_top(cliente_id: int, periodo: dict, limite: int = 6) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    filas = (
        db.session.query(
            GastronomiaPedidoItemModificador.nombre_opcion,
            GastronomiaPedidoItemModificador.tipo_grupo,
            func.count(GastronomiaPedidoItemModificador.id_modificador).label('cantidad'),
            func.coalesce(func.sum(GastronomiaPedidoItemModificador.precio_delta), 0).label('delta_total'),
        )
        .join(GastronomiaPedidoItem, GastronomiaPedidoItem.id_item == GastronomiaPedidoItemModificador.item_id)
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedidoItem.pedido_id)
        .filter(
            GastronomiaPedidoItemModificador.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .group_by(GastronomiaPedidoItemModificador.nombre_opcion, GastronomiaPedidoItemModificador.tipo_grupo)
        .order_by(func.count(GastronomiaPedidoItemModificador.id_modificador).desc())
        .limit(max(1, min(20, int(limite or 6))))
        .all()
    )
    return [{
        'nombre': _modificador_label(nombre, tipo),
        'tipo': tipo,
        'cantidad': int(cantidad or 0),
        'delta_total': float(delta_total or 0),
        'delta_total_label': _formatear_moneda(float(delta_total or 0)),
    } for nombre, tipo, cantidad, delta_total in filas]


def _horarios_pico(cliente_id: int, periodo: dict, limite: int = 5) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    pagos = (
        GastronomiaPedidoPago.query
        .filter(
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .all()
    )
    por_hora: dict[int, dict] = {}
    for pago in pagos:
        fecha_local = utc_naive_to_local(pago.fecha_pago)
        if not fecha_local:
            continue
        item = por_hora.setdefault(fecha_local.hour, {'hora': fecha_local.hour, 'pedidos': 0, 'total': 0.0})
        item['pedidos'] += 1
        item['total'] += float(pago.total_cobrado or 0)
    items = sorted(por_hora.values(), key=lambda item: (-item['pedidos'], -item['total'], item['hora']))[:limite]
    return [{
        **item,
        'hora_label': f"{item['hora']:02d}:00",
        'total_label': _formatear_moneda(item['total']),
    } for item in items]


def _tiempo_preparacion_promedio(cliente_id: int, inicio, fin) -> float:
    pedidos = (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.fecha_listo >= inicio,
            GastronomiaPedido.fecha_listo < fin,
            GastronomiaPedido.fecha_envio_cocina.isnot(None),
            GastronomiaPedido.fecha_listo.isnot(None),
        )
        .all()
    )
    minutos = [
        max(0, (pedido.fecha_listo - pedido.fecha_envio_cocina).total_seconds() / 60)
        for pedido in pedidos
    ]
    return round(sum(minutos) / len(minutos), 1) if minutos else 0


def _pedidos_cancelados(cliente_id: int, inicio, fin) -> int:
    return (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.estado == 'cancelado',
            GastronomiaPedido.fecha_creacion >= inicio,
            GastronomiaPedido.fecha_creacion < fin,
        )
        .count()
    )


def _construir_insights(actual: dict, anterior: dict, productos: list[dict], canales: list[dict], horarios: list[dict]) -> list[dict]:
    insights = []
    ventas_variacion = _calcular_variacion(actual['ventas_total'], anterior['ventas_total'])
    ticket_variacion = _calcular_variacion(actual['ticket_promedio'], anterior['ticket_promedio'])

    if productos:
        lider = productos[0]
        insights.append({
            'prioridad': 'media' if lider['direccion'] == 'down' else 'baja',
            'titulo': f"{lider['nombre']} lidera el menu",
            'detalle': f"Vendio {lider['cantidad']} unidades y aporto {lider['participacion_label']} del ingreso gastronomico.",
            'accion': lider['accion'],
        })
    if ventas_variacion['direccion'] == 'down':
        insights.append({
            'prioridad': 'alta',
            'titulo': 'La venta gastronomica bajo frente al periodo anterior',
            'detalle': f"La facturacion se mueve {ventas_variacion['label']} con {actual['pedidos_cobrados']} pedidos cobrados.",
            'accion': 'Revisar productos lideres, horarios flojos y empujar combos de alto ticket.',
        })
    if ticket_variacion['direccion'] == 'down':
        insights.append({
            'prioridad': 'media',
            'titulo': 'El ticket promedio gastronomico se achico',
            'detalle': f"El ticket marca {ticket_variacion['label']} contra el periodo anterior.",
            'accion': 'Ofrecer extras, bebidas o combos antes de cerrar el pedido.',
        })
    if canales:
        canal = canales[0]
        insights.append({
            'prioridad': 'baja',
            'titulo': f"{canal['canal_label']} es el canal mas fuerte",
            'detalle': f"Concentra {canal['participacion_label']} de la venta del periodo.",
            'accion': 'Cuidar disponibilidad y velocidad en ese canal antes de abrir nuevas promociones.',
        })
    if horarios:
        horario = horarios[0]
        insights.append({
            'prioridad': 'media',
            'titulo': f"Pico operativo a las {horario['hora_label']}",
            'detalle': f"Registra {horario['pedidos']} pedidos y {horario['total_label']} cobrados.",
            'accion': 'Ajustar personal, mise en place y delivery alrededor de esa franja.',
        })
    if actual['tiempo_preparacion_min'] >= 25:
        insights.append({
            'prioridad': 'media',
            'titulo': 'La cocina esta tardando mas de lo ideal',
            'detalle': f"Preparacion promedio: {actual['tiempo_preparacion_min']} min.",
            'accion': 'Revisar productos lentos, capacidad por horario y organizacion de comandas.',
        })
    if not insights:
        insights.append({
            'prioridad': 'baja',
            'titulo': 'Todavia no hay senales gastronomicas fuertes',
            'detalle': 'El periodo no tiene suficiente volumen para detectar oportunidades claras.',
            'accion': 'Seguir acumulando pedidos y revisar de nuevo con mas datos.',
        })

    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    insights.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))
    return insights[:4]


def _accion_producto_top(producto: dict, direccion: str) -> str:
    if direccion == 'down':
        return 'Revisar precio, disponibilidad o visibilidad porque perdio ritmo.'
    if producto['cantidad'] >= 5:
        return 'Usarlo como ancla para combo, upsell o promo de horario pico.'
    return 'Mantenerlo visible y medir si puede escalar con una oferta simple.'


def _canal_label(canal: str | None) -> str:
    labels = {
        'mesa': 'Salon',
        'salon': 'Salon',
        'mostrador': 'Mostrador',
        'retiro': 'Retiro',
        'delivery': 'Delivery',
    }
    return labels.get((canal or '').strip().lower(), (canal or 'Mostrador').title())


def _modificador_label(nombre: str | None, tipo: str | None) -> str:
    if (tipo or '').strip().lower() == 'ingrediente_removible':
        return f"Sin {nombre or 'opcion'}"
    return nombre or 'Opcion'


def _panel_vacio(periodo_actual: dict) -> dict:
    return {
        'activo': False,
        'cliente_id': None,
        'periodo_label': _formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': {
            'ventas_total': 0,
            'ventas_total_label': _formatear_moneda(0),
            'pedidos_cobrados': 0,
            'ticket_promedio': 0,
            'ticket_promedio_label': _formatear_moneda(0),
            'tiempo_preparacion_min': 0,
            'pedidos_cancelados': 0,
            'ventas_variacion_label': 'Sin cambios',
            'ventas_direccion': 'flat',
            'ticket_variacion_label': 'Sin cambios',
            'ticket_direccion': 'flat',
        },
        'productos_top': [],
        'categorias_top': [],
        'canales': [],
        'modificadores_top': [],
        'horarios_pico': [],
        'stock_menu_alertas': [],
        'promos_horario_bajo': [],
        'insights': [{
            'prioridad': 'baja',
            'titulo': 'Gastronomia no esta activa para este contexto',
            'detalle': 'El radar gastronomico se habilita cuando hay un cliente con el modulo activo.',
            'accion': 'Activar Gastronomia o ingresar con el cliente operativo correspondiente.',
        }],
    }


def _calcular_variacion(actual: float | int, anterior: float | int) -> dict:
    actual_num = float(actual or 0)
    anterior_num = float(anterior or 0)
    if anterior_num <= 0:
        if actual_num <= 0:
            return {'direccion': 'flat', 'label': 'Sin cambios'}
        return {'direccion': 'up', 'label': 'Sin base previa'}
    variacion = ((actual_num - anterior_num) / anterior_num) * 100
    if variacion > 0.1:
        return {'direccion': 'up', 'label': f'+{variacion:.1f}%'}
    if variacion < -0.1:
        return {'direccion': 'down', 'label': f'{variacion:.1f}%'}
    return {'direccion': 'flat', 'label': f'{variacion:.1f}%'}


def _formatear_moneda(valor: float) -> str:
    return f'₲ {float(valor or 0):,.0f}'.replace(',', '.')


def _formatear_rango(desde: date, hasta: date) -> str:
    return f'{desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'
