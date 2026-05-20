from collections import Counter
from datetime import timedelta
from math import ceil

from sqlalchemy import distinct

from app import db
from app.models import Categoria, Producto, TiendaLead, TiendaVisitaEvento
from app.utils.helpers import utc_bounds_for_local_dates


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _periodo_anterior(desde, hasta):
    dias = max(1, (hasta - desde).days + 1)
    hasta_anterior = desde - timedelta(days=1)
    desde_anterior = hasta_anterior - timedelta(days=dias - 1)
    return desde_anterior, hasta_anterior


def _resumen_visitas_query(id_cliente: int, start_utc, end_utc, categoria_id: int | None):
    query = (
        db.session.query(TiendaVisitaEvento)
        .join(Producto, Producto.id_producto == TiendaVisitaEvento.id_producto)
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            Producto.activo.is_(True),
        )
    )
    if categoria_id:
        query = query.filter(Producto.id_categoria == categoria_id)
    return query


def _resumen_visitas_stats(id_cliente: int, start_utc, end_utc, categoria_id: int | None) -> tuple[int, int, int]:
    query = (
        db.session.query(
            db.func.count(TiendaVisitaEvento.id_visita).label('total_visitas'),
            db.func.count(distinct(TiendaVisitaEvento.visitante_hash)).label('visitantes_unicos'),
            db.func.count(distinct(TiendaVisitaEvento.id_producto)).label('productos_con_visitas'),
        )
        .select_from(TiendaVisitaEvento)
        .join(Producto, Producto.id_producto == TiendaVisitaEvento.id_producto)
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            Producto.activo.is_(True),
        )
    )
    if categoria_id:
        query = query.filter(Producto.id_categoria == categoria_id)
    fila = query.first()
    return (
        int(getattr(fila, 'total_visitas', 0) or 0),
        int(getattr(fila, 'visitantes_unicos', 0) or 0),
        int(getattr(fila, 'productos_con_visitas', 0) or 0),
    )


def _ranking_base_query(id_cliente: int, start_utc, end_utc, categoria_id: int | None):
    query = (
        db.session.query(
            Producto.id_producto.label('id_producto'),
            Producto.nombre.label('nombre'),
            Producto.codigo.label('codigo'),
            Categoria.nombre.label('categoria_nombre'),
            db.func.count(TiendaVisitaEvento.id_visita).label('total_visitas'),
            db.func.count(distinct(TiendaVisitaEvento.visitante_hash)).label('visitantes_unicos'),
        )
        .select_from(TiendaVisitaEvento)
        .join(Producto, Producto.id_producto == TiendaVisitaEvento.id_producto)
        .outerjoin(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            Producto.activo.is_(True),
        )
        .group_by(
            Producto.id_producto,
            Producto.nombre,
            Producto.codigo,
            Categoria.nombre,
        )
        .order_by(
            db.desc('total_visitas'),
            db.desc('visitantes_unicos'),
            Producto.nombre.asc(),
        )
    )
    if categoria_id:
        query = query.filter(Producto.id_categoria == categoria_id)
    return query


def _leads_por_producto(id_cliente: int, start_utc, end_utc, product_ids: list[int]) -> dict[int, int]:
    if not product_ids:
        return {}

    rows = (
        db.session.query(
            TiendaLead.id_producto,
            db.func.count(TiendaLead.id_lead),
        )
        .filter(
            TiendaLead.id_cliente == id_cliente,
            TiendaLead.fecha_creacion >= start_utc,
            TiendaLead.fecha_creacion < end_utc,
            TiendaLead.id_producto.in_(product_ids),
        )
        .group_by(TiendaLead.id_producto)
        .all()
    )
    return {int(product_id): int(total or 0) for product_id, total in rows if product_id}


def _visitas_previas_por_producto(id_cliente: int, start_utc, end_utc, product_ids: list[int]) -> dict[int, int]:
    if not product_ids:
        return {}

    rows = (
        db.session.query(
            TiendaVisitaEvento.id_producto,
            db.func.count(TiendaVisitaEvento.id_visita),
        )
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            TiendaVisitaEvento.id_producto.in_(product_ids),
        )
        .group_by(TiendaVisitaEvento.id_producto)
        .all()
    )
    return {int(product_id): int(total or 0) for product_id, total in rows if product_id}


def _serializar_tendencia(actual: int, previo: int) -> tuple[str, float | None]:
    if actual > previo:
        direccion = 'up'
    elif actual < previo:
        direccion = 'down'
    else:
        direccion = 'flat'

    if previo == 0:
        porcentaje = 100.0 if actual > 0 else 0.0
    else:
        porcentaje = round(((actual - previo) / previo) * 100, 2)
    return direccion, porcentaje


def _clasificar_dispositivo(user_agent: str | None) -> str:
    user_agent_normalized = (user_agent or '').lower()
    if not user_agent_normalized:
        return 'Desconocido'
    if any(token in user_agent_normalized for token in ('bot', 'crawler', 'spider', 'preview')):
        return 'Bot'
    if 'ipad' in user_agent_normalized or 'tablet' in user_agent_normalized:
        return 'Tablet'
    if any(token in user_agent_normalized for token in ('iphone', 'android', 'mobile')):
        return 'Móvil'
    if any(token in user_agent_normalized for token in ('windows', 'macintosh', 'linux', 'x11')):
        return 'Desktop'
    return 'Otros'


def _clasificar_navegador(user_agent: str | None) -> str:
    user_agent_normalized = (user_agent or '').lower()
    if not user_agent_normalized:
        return 'Desconocido'
    if 'edg/' in user_agent_normalized:
        return 'Edge'
    if 'opr/' in user_agent_normalized or 'opera' in user_agent_normalized:
        return 'Opera'
    if 'samsungbrowser' in user_agent_normalized:
        return 'Samsung Internet'
    if 'firefox' in user_agent_normalized:
        return 'Firefox'
    if 'chrome' in user_agent_normalized and 'chromium' not in user_agent_normalized:
        return 'Chrome'
    if 'safari' in user_agent_normalized:
        return 'Safari'
    return 'Otros'


def _top_items_counter(counter: Counter, limit: int = 5) -> list[dict]:
    return [
        {'label': label, 'value': int(total)}
        for label, total in counter.most_common(limit)
    ]


def _distribucion_user_agents(visitas_base) -> tuple[list[dict], list[dict]]:
    rows = visitas_base.with_entities(TiendaVisitaEvento.user_agent).all()
    dispositivos = Counter()
    navegadores = Counter()
    for (user_agent,) in rows:
        dispositivos[_clasificar_dispositivo(user_agent)] += 1
        navegadores[_clasificar_navegador(user_agent)] += 1
    return _top_items_counter(dispositivos), _top_items_counter(navegadores)


def _horarios_pico(id_cliente: int, start_utc, end_utc, categoria_id: int | None, limit: int = 6) -> list[dict]:
    hora = db.extract('hour', TiendaVisitaEvento.fecha_evento)
    query = (
        db.session.query(
            hora.label('hora'),
            db.func.count(TiendaVisitaEvento.id_visita).label('total_visitas'),
        )
        .select_from(TiendaVisitaEvento)
        .join(Producto, Producto.id_producto == TiendaVisitaEvento.id_producto)
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            Producto.activo.is_(True),
        )
        .group_by(hora)
        .order_by(db.desc('total_visitas'))
        .limit(limit)
    )
    if categoria_id:
        query = query.filter(Producto.id_categoria == categoria_id)
    rows = query.all()
    return [
        {'hora': f"{int(row.hora or 0):02d}:00", 'total_visitas': int(row.total_visitas or 0)}
        for row in rows
    ]


def _categorias_populares(id_cliente: int, start_utc, end_utc, categoria_id: int | None, limit: int = 5) -> list[dict]:
    query = (
        db.session.query(
            Categoria.nombre.label('categoria_nombre'),
            db.func.count(TiendaVisitaEvento.id_visita).label('total_visitas'),
        )
        .select_from(TiendaVisitaEvento)
        .join(Producto, Producto.id_producto == TiendaVisitaEvento.id_producto)
        .outerjoin(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            Producto.activo.is_(True),
        )
        .group_by(Categoria.nombre)
        .order_by(db.desc('total_visitas'))
        .limit(limit)
    )
    if categoria_id:
        query = query.filter(Producto.id_categoria == categoria_id)
    return [
        {
            'categoria': row.categoria_nombre or 'Sin categoría',
            'total_visitas': int(row.total_visitas or 0),
        }
        for row in query.all()
    ]


def _series_por_fecha(rows, desde, hasta, value_getter) -> tuple[list[str], list[int | float]]:
    acumulado = {}
    for row in rows:
        fecha = row.fecha
        if hasattr(fecha, 'isoformat'):
            key = fecha.isoformat()
        else:
            key = str(fecha)
        acumulado[key] = value_getter(row)

    labels = []
    values = []
    cursor = desde
    while cursor <= hasta:
        key = cursor.isoformat()
        labels.append(key)
        values.append(acumulado.get(key, 0))
        cursor += timedelta(days=1)
    return labels, values


def _evolucion_visitas_consultas(id_cliente: int, start_utc, end_utc, categoria_id: int | None, desde, hasta) -> dict:
    visitas_query = (
        db.session.query(
            db.func.date(TiendaVisitaEvento.fecha_evento).label('fecha'),
            db.func.count(TiendaVisitaEvento.id_visita).label('total_visitas'),
        )
        .select_from(TiendaVisitaEvento)
        .join(Producto, Producto.id_producto == TiendaVisitaEvento.id_producto)
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
            Producto.activo.is_(True),
        )
        .group_by(db.func.date(TiendaVisitaEvento.fecha_evento))
        .order_by(db.func.date(TiendaVisitaEvento.fecha_evento))
    )
    if categoria_id:
        visitas_query = visitas_query.filter(Producto.id_categoria == categoria_id)

    consultas_query = (
        db.session.query(
            db.func.date(TiendaLead.fecha_creacion).label('fecha'),
            db.func.count(TiendaLead.id_lead).label('consultas'),
        )
        .select_from(TiendaLead)
        .join(Producto, Producto.id_producto == TiendaLead.id_producto)
        .filter(
            TiendaLead.id_cliente == id_cliente,
            TiendaLead.fecha_creacion >= start_utc,
            TiendaLead.fecha_creacion < end_utc,
            Producto.activo.is_(True),
        )
        .group_by(db.func.date(TiendaLead.fecha_creacion))
        .order_by(db.func.date(TiendaLead.fecha_creacion))
    )
    if categoria_id:
        consultas_query = consultas_query.filter(Producto.id_categoria == categoria_id)

    labels, visitas = _series_por_fecha(
        visitas_query.all(),
        desde,
        hasta,
        lambda row: int(row.total_visitas or 0),
    )
    _, consultas = _series_por_fecha(
        consultas_query.all(),
        desde,
        hasta,
        lambda row: int(row.consultas or 0),
    )
    return {
        'labels': labels,
        'visitas': visitas,
        'consultas': consultas,
    }


def obtener_resumen_estadisticas_tienda(
    id_cliente: int,
    desde,
    hasta,
    categoria_id: int | None = None,
    page: int = 1,
    per_page: int = 10,
) -> dict:
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    desde_anterior, hasta_anterior = _periodo_anterior(desde, hasta)
    start_prev_utc, end_prev_utc = utc_bounds_for_local_dates(desde_anterior, hasta_anterior)

    visitas_base = _resumen_visitas_query(id_cliente, start_utc, end_utc, categoria_id)
    total_visitas, visitantes_unicos, productos_con_visitas = _resumen_visitas_stats(
        id_cliente,
        start_utc,
        end_utc,
        categoria_id,
    )

    leads_query = TiendaLead.query.filter(
        TiendaLead.id_cliente == id_cliente,
        TiendaLead.fecha_creacion >= start_utc,
        TiendaLead.fecha_creacion < end_utc,
    )
    if categoria_id:
        leads_query = leads_query.join(Producto, Producto.id_producto == TiendaLead.id_producto).filter(
            Producto.id_categoria == categoria_id
        )
    leads_generados = leads_query.count()
    conversion_global = round((leads_generados / total_visitas) * 100, 2) if total_visitas else 0

    ranking_base = _ranking_base_query(id_cliente, start_utc, end_utc, categoria_id)
    ranking_subquery = ranking_base.subquery()
    total_items = db.session.query(db.func.count()).select_from(ranking_subquery).scalar() or 0
    total_pages = max(1, ceil(total_items / per_page)) if total_items else 1
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * per_page

    page_rows = (
        db.session.query(ranking_subquery)
        .offset(offset)
        .limit(per_page)
        .all()
    )
    chart_rows = ranking_base.limit(10).all()
    product_ids = [int(row.id_producto) for row in page_rows]

    leads_map = _leads_por_producto(id_cliente, start_utc, end_utc, product_ids)
    prev_visits_map = _visitas_previas_por_producto(id_cliente, start_prev_utc, end_prev_utc, product_ids)
    horarios_pico = _horarios_pico(id_cliente, start_utc, end_utc, categoria_id)
    categorias_populares = _categorias_populares(id_cliente, start_utc, end_utc, categoria_id)
    dispositivos, navegadores = _distribucion_user_agents(visitas_base)
    evolucion_visitas_consultas = _evolucion_visitas_consultas(id_cliente, start_utc, end_utc, categoria_id, desde, hasta)

    ranking_items = []
    for row in page_rows:
        total_producto = int(row.total_visitas or 0)
        previo = int(prev_visits_map.get(int(row.id_producto), 0))
        direccion, porcentaje = _serializar_tendencia(total_producto, previo)
        leads_producto = int(leads_map.get(int(row.id_producto), 0))
        ranking_items.append({
            'id_producto': int(row.id_producto),
            'nombre': row.nombre,
            'codigo': row.codigo,
            'categoria': row.categoria_nombre or 'Sin categoría',
            'total_visitas': total_producto,
            'visitantes_unicos': int(row.visitantes_unicos or 0),
            'leads_generados': leads_producto,
            'conversion_leads': round((leads_producto / total_producto) * 100, 2) if total_producto else 0,
            'visitas_periodo_anterior': previo,
            'tendencia_direccion': direccion,
            'tendencia_porcentaje': porcentaje,
        })

    return {
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'periodo_anterior': {
            'desde': desde_anterior.isoformat(),
            'hasta': hasta_anterior.isoformat(),
        },
        'summary': {
            'total_visitas': int(total_visitas),
            'visitantes_unicos': int(visitantes_unicos),
            'leads_generados': int(leads_generados),
            'productos_con_visitas': int(productos_con_visitas),
            'conversion_global': conversion_global,
        },
        'ranking': ranking_items,
        'chart': {
            'labels': [row.nombre for row in chart_rows],
            'values': [int(row.total_visitas or 0) for row in chart_rows],
        },
        'insights': {
            'horarios_pico': horarios_pico,
            'categorias_populares': categorias_populares,
            'dispositivos': dispositivos,
            'navegadores': navegadores,
        },
        'evolution': evolucion_visitas_consultas,
        'pagination': {
            'page': current_page,
            'per_page': per_page,
            'total_items': int(total_items),
            'total_pages': total_pages,
            'has_prev': current_page > 1,
            'has_next': current_page < total_pages,
        },
    }
