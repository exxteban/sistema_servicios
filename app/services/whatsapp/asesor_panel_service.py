from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, or_

from app.models.crm_contacto import CrmContacto
from app.models.crm_nota_interna import CrmNotaInterna
from app.models.whatsapp import (
    WhatsAppConversacion,
    WhatsAppConversacionEvento,
    WhatsAppMensaje,
)


DEFAULT_HISTORY_PAGE_SIZE = 20
MAX_HISTORY_PAGE_SIZE = 50
DEFAULT_TIMELINE_BATCH_SIZE = 80
MAX_TIMELINE_BATCH_SIZE = 120
TIMELINE_CURSOR_SEPARATOR = "|"
TIMELINE_TYPE_ORDER = {
    "mensaje": 0,
    "nota": 1,
    "evento": 2,
}


def serialize_panel_conversation(
    conv: WhatsAppConversacion,
    *,
    estado_asignacion: str | None = None,
    asesor_nombre: str | None = None,
) -> dict:
    contacto = CrmContacto.query.filter_by(telefono=conv.telefono).first()
    ultimo = conv.mensajes.order_by(desc(WhatsAppMensaje.created_at)).first()
    return {
        "id": conv.id,
        "telefono": conv.telefono,
        "nombre": conv.nombre_contacto or (contacto.nombre if contacto else conv.telefono),
        "modo": conv.modo,
        "activa": bool(conv.activa),
        "ultima_actividad": conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
        "ultimo_mensaje": (ultimo.contenido or "")[:100] if ultimo else "",
        "estado_asignacion": estado_asignacion,
        "id_contacto": contacto.id if contacto else None,
        "asesor": asesor_nombre,
        "etiquetas": [e.to_dict() for e in contacto.etiquetas] if contacto else [],
    }


def paginate_store_web_histories(
    *,
    excluded_ids: set[int] | None = None,
    page: int = 1,
    per_page: int = DEFAULT_HISTORY_PAGE_SIZE,
    search: str = "",
    estado: str = "activas",
    periodo: str = "30",
) -> dict:
    per_page = max(1, min(per_page or DEFAULT_HISTORY_PAGE_SIZE, MAX_HISTORY_PAGE_SIZE))
    page = max(1, page or 1)
    query = _build_store_web_history_query(
        excluded_ids=excluded_ids or set(),
        search=search,
        estado=estado,
        periodo=periodo,
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": [serialize_panel_conversation(conv) for conv in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "page": page,
        "per_page": per_page,
        "search": (search or "").strip(),
        "estado": _normalize_history_state(estado),
        "periodo": _normalize_history_period(periodo),
    }


def count_store_web_histories(*, excluded_ids: set[int] | None = None) -> int:
    query = _build_store_web_history_query(
        excluded_ids=excluded_ids or set(),
        search="",
        estado="activas",
        periodo="30",
    )
    return query.count()


def get_paginated_conversation_timeline(
    id_conversacion: int,
    *,
    limit: int = DEFAULT_TIMELINE_BATCH_SIZE,
    cursor: str = "",
) -> dict:
    limit = max(1, min(limit or DEFAULT_TIMELINE_BATCH_SIZE, MAX_TIMELINE_BATCH_SIZE))
    cursor_info = _parse_timeline_cursor(cursor)
    per_source_limit = (limit * 2) + 5

    mensajes_q = WhatsAppMensaje.query.filter_by(id_conversacion=id_conversacion)
    eventos_q = WhatsAppConversacionEvento.query.filter_by(id_conversacion=id_conversacion)
    notas_q = CrmNotaInterna.query.filter_by(id_conversacion=id_conversacion)

    cursor_dt = cursor_info["created_at_dt"] if cursor_info else None
    if cursor_dt is not None:
        mensajes_q = mensajes_q.filter(WhatsAppMensaje.created_at <= cursor_dt)
        eventos_q = eventos_q.filter(WhatsAppConversacionEvento.created_at <= cursor_dt)
        notas_q = notas_q.filter(CrmNotaInterna.created_at <= cursor_dt)

    mensajes = mensajes_q.order_by(WhatsAppMensaje.created_at.desc(), WhatsAppMensaje.id.desc()).limit(per_source_limit).all()
    eventos = eventos_q.order_by(WhatsAppConversacionEvento.created_at.desc(), WhatsAppConversacionEvento.id.desc()).limit(per_source_limit).all()
    notas = notas_q.order_by(CrmNotaInterna.created_at.desc(), CrmNotaInterna.id.desc()).limit(per_source_limit).all()

    items = [
        *_serialize_timeline_messages(mensajes),
        *_serialize_timeline_notes(notas),
        *_serialize_timeline_events(eventos),
    ]
    if cursor_info:
        cursor_key = _timeline_sort_key(cursor_info)
        items = [item for item in items if _timeline_sort_key(item) < cursor_key]

    items.sort(key=_timeline_sort_key, reverse=True)
    has_more = len(items) > limit
    page_items = items[:limit]
    next_cursor = _encode_timeline_cursor(page_items[-1]) if has_more and page_items else None
    page_items.reverse()

    return {
        "items": [
            {
                "id": item["frontend_id"],
                "tipo_item": item["kind"],
                "es_nota": item["es_nota"],
                "es_evento": item["es_evento"],
                "direccion": item["direccion"],
                "remitente": item.get("remitente"),
                "contenido": item["contenido"],
                "tipo": item.get("tipo"),
                "created_at": item["created_at"],
                "asesor": item.get("asesor"),
                "autor": item.get("autor"),
                "detalle": item.get("detalle"),
            }
            for item in page_items
        ],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _build_store_web_history_query(
    *,
    excluded_ids: set[int],
    search: str,
    estado: str,
    periodo: str,
):
    query = WhatsAppConversacion.query.filter(
        WhatsAppConversacion.modo == "bot",
        WhatsAppConversacion.contexto.contains('"id_sesion_web"'),
    )
    if excluded_ids:
        query = query.filter(~WhatsAppConversacion.id.in_(excluded_ids))

    estado_norm = _normalize_history_state(estado)
    if estado_norm == "activas":
        query = query.filter(WhatsAppConversacion.activa.is_(True))
    elif estado_norm == "cerradas":
        query = query.filter(WhatsAppConversacion.activa.is_(False))

    cutoff = _history_cutoff_for_period(periodo)
    if cutoff is not None:
        query = query.filter(WhatsAppConversacion.ultima_actividad >= cutoff)

    search_term = (search or "").strip()
    if search_term:
        like = f"%{search_term}%"
        query = query.filter(
            or_(
                WhatsAppConversacion.telefono.ilike(like),
                WhatsAppConversacion.nombre_contacto.ilike(like),
            )
        )

    return query.order_by(
        WhatsAppConversacion.ultima_actividad.desc(),
        WhatsAppConversacion.id.desc(),
    )


def _normalize_history_state(value: str | None) -> str:
    value = (value or "activas").strip().lower()
    if value in {"activas", "cerradas", "todas"}:
        return value
    return "activas"


def _normalize_history_period(value: str | None) -> str:
    value = (value or "30").strip().lower()
    if value in {"7", "30", "90", "all"}:
        return value
    return "30"


def _history_cutoff_for_period(value: str | None) -> datetime | None:
    normalized = _normalize_history_period(value)
    if normalized == "all":
        return None
    return datetime.utcnow() - timedelta(days=int(normalized))


def _serialize_timeline_messages(items: list[WhatsAppMensaje]) -> list[dict]:
    return [
        {
            "frontend_id": f"msg-{item.id}",
            "kind": "mensaje",
            "kind_id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "es_nota": False,
            "es_evento": False,
            "direccion": item.direccion,
            "remitente": item.remitente,
            "contenido": item.contenido,
            "tipo": item.tipo_mensaje,
            "asesor": item.asesor.nombre_completo if item.asesor else None,
        }
        for item in items
    ]


def _serialize_timeline_notes(items: list[CrmNotaInterna]) -> list[dict]:
    return [
        {
            "frontend_id": f"nota-{item.id}",
            "kind": "nota",
            "kind_id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "es_nota": True,
            "es_evento": False,
            "direccion": "saliente",
            "contenido": item.contenido,
            "autor": item.usuario.nombre_completo if item.usuario else "Sistema",
        }
        for item in items
    ]


def _serialize_timeline_events(items: list[WhatsAppConversacionEvento]) -> list[dict]:
    return [
        {
            "frontend_id": f"evento-{item.id}",
            "kind": "evento",
            "kind_id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "es_nota": False,
            "es_evento": True,
            "direccion": "centro",
            "contenido": item.tipo,
            "detalle": item.detalle,
            "autor": item.usuario.nombre_completo if item.usuario else "",
        }
        for item in items
    ]


def _timeline_sort_key(item: dict):
    return (
        item.get("created_at") or "",
        TIMELINE_TYPE_ORDER.get(item.get("kind"), 99),
        int(item.get("kind_id") or 0),
    )


def _encode_timeline_cursor(item: dict) -> str:
    return TIMELINE_CURSOR_SEPARATOR.join(
        [
            item.get("created_at") or "",
            item.get("kind") or "",
            str(item.get("kind_id") or 0),
        ]
    )


def _parse_timeline_cursor(raw: str | None) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    parts = raw.split(TIMELINE_CURSOR_SEPARATOR)
    if len(parts) != 3:
        return None
    try:
        created_at = datetime.fromisoformat(parts[0])
        kind_id = int(parts[2])
    except (TypeError, ValueError):
        return None
    return {
        "created_at": created_at.isoformat(),
        "created_at_dt": created_at,
        "kind": parts[1],
        "kind_id": kind_id,
    }
