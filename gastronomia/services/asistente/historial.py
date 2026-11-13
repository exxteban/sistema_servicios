"""Conversacion del asistente por usuario y local, guardada en base de datos."""
from __future__ import annotations

import json

from app import db
from gastronomia.asistente_models import GastronomiaAsistenteMensaje

MAX_MENSAJES = 16
MAX_GUARDADOS = 40
MAX_CONTENIDO = 12000


def _query(cliente_id: int, usuario_id: int):
    return GastronomiaAsistenteMensaje.query.filter_by(cliente_id=int(cliente_id), usuario_id=int(usuario_id))


def listar(cliente_id: int, usuario_id: int, limite: int = MAX_MENSAJES) -> list[dict]:
    filas = (
        _query(cliente_id, usuario_id)
        .order_by(GastronomiaAsistenteMensaje.id_mensaje.desc())
        .limit(limite)
        .all()
    )
    salida = []
    for fila in reversed(filas):
        item = {'role': fila.rol, 'content': fila.contenido}
        if fila.contexto_json:
            try:
                item['contexto'] = json.loads(fila.contexto_json)
            except ValueError:
                pass
        salida.append(item)
    return salida


def agregar(cliente_id: int, usuario_id: int, rol: str, contenido: str, contexto: dict | None = None) -> None:
    db.session.add(GastronomiaAsistenteMensaje(
        cliente_id=int(cliente_id),
        usuario_id=int(usuario_id),
        rol=rol,
        contenido=(contenido or '')[:MAX_CONTENIDO],
        contexto_json=json.dumps(contexto, ensure_ascii=False) if contexto else None,
    ))
    db.session.flush()
    viejos = [
        fila.id_mensaje
        for fila in _query(cliente_id, usuario_id)
        .order_by(GastronomiaAsistenteMensaje.id_mensaje.desc())
        .offset(MAX_GUARDADOS)
        .all()
    ]
    if viejos:
        GastronomiaAsistenteMensaje.query.filter(
            GastronomiaAsistenteMensaje.id_mensaje.in_(viejos)
        ).delete(synchronize_session=False)
    db.session.commit()


def limpiar(cliente_id: int, usuario_id: int) -> None:
    _query(cliente_id, usuario_id).delete(synchronize_session=False)
    db.session.commit()
