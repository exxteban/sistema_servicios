"""
Auditoria del asistente IA interno.
"""
import json
from datetime import datetime, timedelta

from flask import has_request_context, request
from sqlalchemy import func, or_

from app import db
from app.models import AsistenteIABackofficeAudit


def _json_compacto(valor) -> str:
    try:
        return json.dumps(valor or {}, ensure_ascii=False, separators=(',', ':'), default=str)
    except Exception:
        return '{}'


def _json_parseado(texto: str, default):
    try:
        cargado = json.loads(texto or '')
    except Exception:
        return default
    return cargado if cargado is not None else default


def registrar_interaccion(
    usuario,
    pregunta: str,
    respuesta: str,
    *,
    tools_usadas=None,
    argumentos_normalizados=None,
    resultado_resumido: str = '',
    tokens_prompt: int = 0,
    tokens_completion: int = 0,
    modelo: str = '',
    provider: str = '',
    estado: str = 'ok',
    commit: bool = True,
) -> AsistenteIABackofficeAudit:
    ip = ''
    user_agent = ''
    if has_request_context():
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        user_agent = request.headers.get('User-Agent', '')

    audit = AsistenteIABackofficeAudit(
        id_usuario=getattr(usuario, 'id_usuario', None),
        username=getattr(usuario, 'username', ''),
        pregunta=(pregunta or '')[:8000],
        respuesta=(respuesta or '')[:12000],
        tools_usadas=_json_compacto(tools_usadas or []),
        argumentos_normalizados=_json_compacto(argumentos_normalizados or {}),
        resultado_resumido=(resultado_resumido or '')[:8000],
        tokens_prompt=max(0, int(tokens_prompt or 0)),
        tokens_completion=max(0, int(tokens_completion or 0)),
        tokens_total=max(0, int(tokens_prompt or 0)) + max(0, int(tokens_completion or 0)),
        modelo=modelo or '',
        provider=provider or '',
        estado=estado or 'ok',
        ip=ip[:80],
        user_agent=user_agent[:255],
    )
    db.session.add(audit)
    if commit:
        db.session.commit()
    return audit


def _normalizar_rango(desde: datetime | None, hasta: datetime | None) -> tuple[datetime, datetime]:
    fin = hasta or datetime.utcnow()
    inicio = desde or (fin - timedelta(days=1))
    if inicio >= fin:
        inicio = fin - timedelta(days=1)
    return inicio, fin


def obtener_consumo_tokens(desde: datetime | None = None, hasta: datetime | None = None, usuario=None) -> dict:
    inicio, fin = _normalizar_rango(desde, hasta)
    query = AsistenteIABackofficeAudit.query.filter(
        AsistenteIABackofficeAudit.fecha_hora >= inicio,
        AsistenteIABackofficeAudit.fecha_hora < fin,
    )
    id_usuario = getattr(usuario, 'id_usuario', None)
    if id_usuario:
        query = query.filter(AsistenteIABackofficeAudit.id_usuario == id_usuario)

    fila = query.with_entities(
        func.count(AsistenteIABackofficeAudit.id_audit).label('interacciones'),
        func.coalesce(func.sum(AsistenteIABackofficeAudit.tokens_prompt), 0).label('tokens_prompt'),
        func.coalesce(func.sum(AsistenteIABackofficeAudit.tokens_completion), 0).label('tokens_completion'),
        func.coalesce(func.sum(AsistenteIABackofficeAudit.tokens_total), 0).label('tokens_total'),
    ).one()
    return {
        'desde': inicio.isoformat(),
        'hasta': fin.isoformat(),
        'interacciones': int(fila.interacciones or 0),
        'tokens_prompt': int(fila.tokens_prompt or 0),
        'tokens_completion': int(fila.tokens_completion or 0),
        'tokens_total': int(fila.tokens_total or 0),
    }


def obtener_consumo_tokens_por_usuario(
    desde: datetime | None = None,
    hasta: datetime | None = None,
    *,
    top_n: int = 20,
) -> list[dict]:
    inicio, fin = _normalizar_rango(desde, hasta)
    try:
        limite_raw = int(top_n or 20)
    except Exception:
        limite_raw = 20
    limite = max(1, min(limite_raw, 100))
    filas = (
        AsistenteIABackofficeAudit.query
        .filter(
            AsistenteIABackofficeAudit.fecha_hora >= inicio,
            AsistenteIABackofficeAudit.fecha_hora < fin,
        )
        .with_entities(
            AsistenteIABackofficeAudit.id_usuario,
            AsistenteIABackofficeAudit.username,
            func.count(AsistenteIABackofficeAudit.id_audit).label('interacciones'),
            func.coalesce(func.sum(AsistenteIABackofficeAudit.tokens_total), 0).label('tokens_total'),
        )
        .group_by(AsistenteIABackofficeAudit.id_usuario, AsistenteIABackofficeAudit.username)
        .order_by(func.coalesce(func.sum(AsistenteIABackofficeAudit.tokens_total), 0).desc())
        .limit(limite)
        .all()
    )
    return [
        {
            'id_usuario': row.id_usuario,
            'username': row.username or '',
            'interacciones': int(row.interacciones or 0),
            'tokens_total': int(row.tokens_total or 0),
        }
        for row in filas
    ]


def buscar_historial_interacciones(
    *,
    page: int = 1,
    per_page: int = 20,
    username: str = '',
    q: str = '',
) -> dict:
    pagina = max(1, int(page or 1))
    limite = max(1, min(int(per_page or 20), 50))
    query = AsistenteIABackofficeAudit.query

    username_norm = (username or '').strip()
    if username_norm:
        query = query.filter(AsistenteIABackofficeAudit.username == username_norm)

    texto = (q or '').strip()
    if texto:
        patron = f'%{texto}%'
        query = query.filter(
            or_(
                AsistenteIABackofficeAudit.username.ilike(patron),
                AsistenteIABackofficeAudit.pregunta.ilike(patron),
                AsistenteIABackofficeAudit.respuesta.ilike(patron),
            )
        )

    total = query.count()
    filas = (
        query.with_entities(
            AsistenteIABackofficeAudit.id_audit,
            AsistenteIABackofficeAudit.username,
            AsistenteIABackofficeAudit.fecha_hora,
            AsistenteIABackofficeAudit.estado,
            AsistenteIABackofficeAudit.tokens_prompt,
            AsistenteIABackofficeAudit.tokens_completion,
            AsistenteIABackofficeAudit.tokens_total,
            AsistenteIABackofficeAudit.tools_usadas,
            AsistenteIABackofficeAudit.pregunta,
        )
        .order_by(AsistenteIABackofficeAudit.fecha_hora.desc(), AsistenteIABackofficeAudit.id_audit.desc())
        .offset((pagina - 1) * limite)
        .limit(limite)
        .all()
    )
    return {
        'page': pagina,
        'per_page': limite,
        'total': int(total or 0),
        'items': [
            {
                'id_audit': row.id_audit,
                'username': row.username or '',
                'fecha_hora': row.fecha_hora.isoformat() if row.fecha_hora else None,
                'estado': row.estado or '',
                'tokens_prompt': int(row.tokens_prompt or 0),
                'tokens_completion': int(row.tokens_completion or 0),
                'tokens_total': int(row.tokens_total or 0),
                'tools_count': len(_json_parseado(row.tools_usadas, [])),
                'pregunta_preview': (row.pregunta or '')[:180],
            }
            for row in filas
        ],
    }


def obtener_historial_interaccion(id_audit: int) -> dict | None:
    try:
        audit_id = int(id_audit or 0)
    except Exception:
        return None
    if audit_id <= 0:
        return None

    audit = db.session.get(AsistenteIABackofficeAudit, audit_id)
    if audit is None:
        return None
    return {
        'id_audit': audit.id_audit,
        'id_usuario': audit.id_usuario,
        'username': audit.username or '',
        'fecha_hora': audit.fecha_hora.isoformat() if audit.fecha_hora else None,
        'pregunta': audit.pregunta or '',
        'respuesta': audit.respuesta or '',
        'tools_usadas': _json_parseado(audit.tools_usadas, []),
        'argumentos_normalizados': _json_parseado(audit.argumentos_normalizados, {}),
        'resultado_resumido': audit.resultado_resumido or '',
        'tokens_prompt': int(audit.tokens_prompt or 0),
        'tokens_completion': int(audit.tokens_completion or 0),
        'tokens_total': int(audit.tokens_total or 0),
        'modelo': audit.modelo or '',
        'provider': audit.provider or '',
        'estado': audit.estado or '',
    }
