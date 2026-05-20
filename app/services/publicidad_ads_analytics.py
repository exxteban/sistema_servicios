import hashlib
import json
from datetime import timedelta
from urllib.parse import urlparse

from flask import request
from sqlalchemy import case

from app import db
from app.models.publicidad_ads import PublicidadAdsEvento
from app.utils.helpers import today_local, utc_bounds_for_local_dates


LANDING_KEY = 'publicidad_ads'
ALLOWED_EVENT_TYPES = {
    'page_view',
    'cta_click',
    'section_view',
    'lightbox_open',
    'scroll_depth',
}


def _clean_str(value, max_len: int) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    return text[:max_len]


def _clean_path(value) -> str | None:
    raw = _clean_str(value, 255)
    if not raw:
        return None
    parsed = urlparse(raw)
    path = (parsed.path or raw).strip()
    if not path.startswith('/'):
        path = f'/{path.lstrip("/")}'
    return path[:255]


def _client_ip() -> str | None:
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    return _clean_str(ip, 64)


def _visitor_hash(ip_address: str | None, user_agent: str | None) -> str:
    base = f'{ip_address or "-"}|{(user_agent or "").strip().lower()}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def _clean_payload(payload) -> str | None:
    if not isinstance(payload, dict) or not payload:
        return None
    compact = {}
    for key, value in payload.items():
        key_text = _clean_str(key, 40)
        if not key_text:
            continue
        if isinstance(value, (dict, list)):
            continue
        value_text = _clean_str(value, 200)
        if value_text is not None:
            compact[key_text] = value_text
    if not compact:
        return None
    return json.dumps(compact, ensure_ascii=False)


def registrar_evento_publicidad_ads(data: dict) -> PublicidadAdsEvento:
    tipo_evento = _clean_str(data.get('event_type'), 40)
    if tipo_evento not in ALLOWED_EVENT_TYPES:
        raise ValueError('tipo_evento_invalido')

    user_agent = _clean_str(request.headers.get('User-Agent'), 255)
    ip_address = _client_ip()
    evento = PublicidadAdsEvento(
        landing_key=LANDING_KEY,
        tipo_evento=tipo_evento,
        etiqueta=_clean_str(data.get('label'), 120),
        section_id=_clean_str(data.get('section_id'), 80),
        path_url=_clean_path(data.get('path') or request.path),
        session_hash=_clean_str(data.get('session_id'), 80),
        visitante_hash=_visitor_hash(ip_address, user_agent),
        utm_source=_clean_str(data.get('utm_source'), 120),
        utm_medium=_clean_str(data.get('utm_medium'), 120),
        utm_campaign=_clean_str(data.get('utm_campaign'), 120),
        utm_term=_clean_str(data.get('utm_term'), 120),
        utm_content=_clean_str(data.get('utm_content'), 120),
        referer_url=_clean_str(request.headers.get('Referer') or data.get('referer'), 500),
        ip_address=ip_address,
        user_agent=user_agent,
        payload_json=_clean_payload(data.get('meta')),
    )
    db.session.add(evento)
    db.session.commit()
    return evento


def _daily_rows(start_utc, end_utc):
    return (
        db.session.query(
            db.func.date(PublicidadAdsEvento.fecha_evento).label('fecha'),
            db.func.sum(case((PublicidadAdsEvento.tipo_evento == 'page_view', 1), else_=0)).label('page_views'),
            db.func.sum(case((PublicidadAdsEvento.tipo_evento == 'cta_click', 1), else_=0)).label('cta_clicks'),
        )
        .filter(
            PublicidadAdsEvento.landing_key == LANDING_KEY,
            PublicidadAdsEvento.fecha_evento >= start_utc,
            PublicidadAdsEvento.fecha_evento < end_utc,
        )
        .group_by(db.func.date(PublicidadAdsEvento.fecha_evento))
        .order_by(db.func.date(PublicidadAdsEvento.fecha_evento))
        .all()
    )


def _daily_series(days: int) -> list[dict]:
    hasta = today_local()
    desde = hasta - timedelta(days=max(0, days - 1))
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    rows = {
        str(row.fecha): {
            'page_views': int(row.page_views or 0),
            'cta_clicks': int(row.cta_clicks or 0),
        }
        for row in _daily_rows(start_utc, end_utc)
    }
    series = []
    current = desde
    while current <= hasta:
        key = current.isoformat()
        values = rows.get(key, {'page_views': 0, 'cta_clicks': 0})
        series.append({
            'fecha': key,
            'label': current.strftime('%d/%m'),
            'page_views': values['page_views'],
            'cta_clicks': values['cta_clicks'],
        })
        current += timedelta(days=1)
    return series


def _summary_for_days(days: int) -> dict:
    hasta = today_local()
    desde = hasta - timedelta(days=max(0, days - 1))
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    query = PublicidadAdsEvento.query.filter(
        PublicidadAdsEvento.landing_key == LANDING_KEY,
        PublicidadAdsEvento.fecha_evento >= start_utc,
        PublicidadAdsEvento.fecha_evento < end_utc,
    )
    page_views = query.filter(PublicidadAdsEvento.tipo_evento == 'page_view').count()
    cta_clicks = query.filter(PublicidadAdsEvento.tipo_evento == 'cta_click').count()
    visitantes_unicos = (
        query.with_entities(db.func.count(db.distinct(PublicidadAdsEvento.visitante_hash))).scalar() or 0
    )
    sesiones_unicas = (
        query.with_entities(db.func.count(db.distinct(PublicidadAdsEvento.session_hash))).filter(
            PublicidadAdsEvento.session_hash.isnot(None)
        ).scalar() or 0
    )
    return {
        'days': days,
        'page_views': int(page_views),
        'cta_clicks': int(cta_clicks),
        'visitantes_unicos': int(visitantes_unicos),
        'sesiones_unicas': int(sesiones_unicas),
        'cta_rate': round((cta_clicks / page_views) * 100, 2) if page_views else 0,
    }


def _top_ctas(limit: int = 6) -> list[dict]:
    rows = (
        db.session.query(
            PublicidadAdsEvento.etiqueta,
            db.func.count(PublicidadAdsEvento.id_evento).label('total'),
        )
        .filter(
            PublicidadAdsEvento.landing_key == LANDING_KEY,
            PublicidadAdsEvento.tipo_evento == 'cta_click',
            PublicidadAdsEvento.etiqueta.isnot(None),
        )
        .group_by(PublicidadAdsEvento.etiqueta)
        .order_by(db.desc('total'), PublicidadAdsEvento.etiqueta.asc())
        .limit(limit)
        .all()
    )
    return [{'label': row.etiqueta or 'sin_etiqueta', 'total': int(row.total or 0)} for row in rows]


def _top_sections(limit: int = 6) -> list[dict]:
    rows = (
        db.session.query(
            PublicidadAdsEvento.section_id,
            db.func.count(PublicidadAdsEvento.id_evento).label('total'),
        )
        .filter(
            PublicidadAdsEvento.landing_key == LANDING_KEY,
            PublicidadAdsEvento.tipo_evento == 'section_view',
            PublicidadAdsEvento.section_id.isnot(None),
        )
        .group_by(PublicidadAdsEvento.section_id)
        .order_by(db.desc('total'), PublicidadAdsEvento.section_id.asc())
        .limit(limit)
        .all()
    )
    return [{'section_id': row.section_id or 'sin_id', 'total': int(row.total or 0)} for row in rows]


def _campaigns(limit: int = 8) -> list[dict]:
    rows = (
        db.session.query(
            PublicidadAdsEvento.utm_source,
            PublicidadAdsEvento.utm_medium,
            PublicidadAdsEvento.utm_campaign,
            db.func.sum(case((PublicidadAdsEvento.tipo_evento == 'page_view', 1), else_=0)).label('page_views'),
            db.func.sum(case((PublicidadAdsEvento.tipo_evento == 'cta_click', 1), else_=0)).label('cta_clicks'),
        )
        .filter(
            PublicidadAdsEvento.landing_key == LANDING_KEY,
            db.or_(
                PublicidadAdsEvento.utm_source.isnot(None),
                PublicidadAdsEvento.utm_medium.isnot(None),
                PublicidadAdsEvento.utm_campaign.isnot(None),
            ),
        )
        .group_by(
            PublicidadAdsEvento.utm_source,
            PublicidadAdsEvento.utm_medium,
            PublicidadAdsEvento.utm_campaign,
        )
        .order_by(db.desc('page_views'), db.desc('cta_clicks'))
        .limit(limit)
        .all()
    )
    data = []
    for row in rows:
        page_views = int(row.page_views or 0)
        cta_clicks = int(row.cta_clicks or 0)
        data.append({
            'source': row.utm_source or '-',
            'medium': row.utm_medium or '-',
            'campaign': row.utm_campaign or '-',
            'page_views': page_views,
            'cta_clicks': cta_clicks,
            'cta_rate': round((cta_clicks / page_views) * 100, 2) if page_views else 0,
        })
    return data


def _recent_events(limit: int = 20) -> list[dict]:
    rows = (
        PublicidadAdsEvento.query
        .filter_by(landing_key=LANDING_KEY)
        .order_by(PublicidadAdsEvento.fecha_evento.desc(), PublicidadAdsEvento.id_evento.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            'fecha_evento': row.fecha_evento,
            'tipo_evento': row.tipo_evento,
            'etiqueta': row.etiqueta or '-',
            'section_id': row.section_id or '-',
            'path_url': row.path_url or '-',
            'utm_source': row.utm_source or '-',
            'utm_campaign': row.utm_campaign or '-',
        }
        for row in rows
    ]


def obtener_dashboard_publicidad_ads() -> dict:
    return {
        'summary_7d': _summary_for_days(7),
        'summary_30d': _summary_for_days(30),
        'daily_series': _daily_series(14),
        'top_ctas': _top_ctas(),
        'top_sections': _top_sections(),
        'campaigns': _campaigns(),
        'recent_events': _recent_events(),
    }
