"""
Auditoría operativa de conversaciones WhatsApp.
"""
import json

from app import db
from app.models.whatsapp import WhatsAppConversacionEvento


def registrar_evento_conversacion(
    conversacion,
    tipo: str,
    *,
    actor: str = 'sistema',
    id_usuario: int | None = None,
    detalle=None,
    created_at=None,
):
    id_conversacion = int(getattr(conversacion, 'id', conversacion))
    evento = WhatsAppConversacionEvento(
        id_conversacion=id_conversacion,
        tipo=(tipo or '').strip() or 'evento',
        actor=(actor or 'sistema').strip() or 'sistema',
        id_usuario=id_usuario,
        detalle=json.dumps(detalle, ensure_ascii=False, default=str) if detalle is not None else None,
        created_at=created_at,
    )
    db.session.add(evento)
    return evento


def serializar_evento(evento: WhatsAppConversacionEvento) -> dict:
    detalle = None
    if evento.detalle:
        try:
            detalle = json.loads(evento.detalle)
        except Exception:
            detalle = {'raw': evento.detalle}
    return {
        'id': evento.id,
        'tipo': evento.tipo,
        'actor': evento.actor,
        'id_usuario': evento.id_usuario,
        'usuario': evento.usuario.nombre_completo if evento.usuario else None,
        'detalle': detalle,
        'created_at': evento.created_at.isoformat() if evento.created_at else None,
    }
