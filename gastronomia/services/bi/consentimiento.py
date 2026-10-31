"""Casilla de consentimiento para recibir mensajes, registrada desde el POS por telefono (BI-04).

- Solo entra en la cola de envio asistido un telefono con consentimiento registrado (estado 'acepta').
- Cada vez que se guarda un pedido con celular, el POS informa el resultado de la casilla.
  Si la casilla no estaba marcada y el telefono no tiene consentimiento, queda como 'sin_marcar':
  pendiente y visible en el tablero, para que no pase desapercibido.
- Desmarcar la casilla nunca quita un consentimiento ya registrado.
- El telefono se normaliza con la misma regla que la identidad del BI, asi la cola lo reconoce.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app import db
from gastronomia.bi_models import GastronomiaBiConsentimiento
from gastronomia.services.bi.identidad import telefono_normalizado

ACEPTA = 'acepta'
SIN_MARCAR = 'sin_marcar'

RESULTADO_REGISTRADO = 'registrado'
RESULTADO_YA_REGISTRADO = 'ya_registrado'
RESULTADO_SIN_MARCAR = 'sin_marcar'

MSG_TELEFONO_INVALIDO = 'El celular no es válido. No se registró la casilla de consentimiento.'


def registrar_casilla(cliente_id: int, celular: str | None, acepta: bool) -> str:
    """Registra la casilla de un pedido y devuelve el resultado: registrado, ya_registrado o sin_marcar."""
    telefono = telefono_normalizado(celular)
    if not telefono:
        raise ValueError(MSG_TELEFONO_INVALIDO)
    cliente_id = int(cliente_id)
    fila = GastronomiaBiConsentimiento.query.filter_by(cliente_id=cliente_id, telefono_normalizado=telefono).first()
    if fila and fila.estado == ACEPTA:
        # Ya aceptó antes: una casilla sin marcar en otro pedido no lo revoca.
        return RESULTADO_YA_REGISTRADO
    if acepta:
        resultado, estado = RESULTADO_REGISTRADO, ACEPTA
    else:
        resultado, estado = RESULTADO_SIN_MARCAR, SIN_MARCAR
    if fila:
        fila.estado = estado
        fila.fecha_estado = datetime.utcnow()
    else:
        db.session.add(GastronomiaBiConsentimiento(cliente_id=cliente_id, telefono_normalizado=telefono, estado=estado))
    try:
        db.session.commit()
    except IntegrityError:
        # Otra solicitud guardo el mismo telefono entre la consulta y el alta: el estado ya queda registrado.
        db.session.rollback()
    return resultado


def telefonos_con_consentimiento(cliente_id: int) -> set[str]:
    filas = (
        GastronomiaBiConsentimiento.query
        .with_entities(GastronomiaBiConsentimiento.telefono_normalizado)
        .filter_by(cliente_id=int(cliente_id), estado=ACEPTA)
        .all()
    )
    return {fila[0] for fila in filas}


def contar_sin_marcar(cliente_id: int) -> int:
    return GastronomiaBiConsentimiento.query.filter_by(cliente_id=int(cliente_id), estado=SIN_MARCAR).count()
