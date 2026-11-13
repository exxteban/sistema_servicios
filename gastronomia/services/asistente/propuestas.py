"""Propuestas de cambio del asistente: la IA solo PROPONE; se guarda unicamente si el usuario confirma.

Garantias (del lado del servidor, no dependen de que el modelo "se porte bien"):
- Ninguna tool de escritura se ejecuta durante el chat: solo se arma una vista previa.
- Lo que se ejecuta al confirmar es exactamente lo que se mostro (mismas acciones guardadas).
- La propuesta es de un usuario y local, de un solo uso y vence a los 30 minutos.
- Los permisos del usuario se verifican al proponer Y al confirmar.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from app import db
from gastronomia.asistente_models import GastronomiaAsistentePropuesta as Propuesta
from gastronomia.services.asistente import historial
from gastronomia.services.asistente.ejecutor import ejecutar_tool, errores_de, guardo_algo
from gastronomia.services.asistente.vista_previa import VISTAS, Pendientes
from gastronomia.services.permisos import PERMISO_MENU, PERMISO_SALON, tiene_permiso_gastronomia

logger = logging.getLogger(__name__)
VIGENCIA = timedelta(minutes=30)
MAX_ACCIONES = 40
PERMISO_POR_TOOL = {'crear_mesas': PERMISO_SALON}
NOTA_MODELO = (
    'TODAVIA NO SE GUARDO NADA. El sistema le muestra este resumen al usuario con botones Confirmar / Cancelar '
    'y solo se guarda si toca Confirmar. No digas que ya quedo cargado: deci que revise y confirme.'
)
VENCIDA = 'Esta propuesta ya no esta vigente (ya se confirmo, se cancelo o vencio). Pedile al asistente que la arme de nuevo.'


def permiso_de(tool: str) -> str:
    return PERMISO_POR_TOOL.get(tool, PERMISO_MENU)


def nuevas_pendientes() -> Pendientes:
    return Pendientes()


def preparar(tool: str, args: dict, cliente_id: int, pendientes: Pendientes, acciones: list) -> dict:
    """Valida y arma la vista previa de una escritura. Devuelve lo que ve la IA; no guarda nada."""
    if not tiene_permiso_gastronomia(permiso_de(tool)):
        return {'ok': False, 'error': f'El usuario no tiene permiso para esto ({permiso_de(tool)}). '
                                      'No lo reintentes: explicale que lo habilite un administrador.'}
    if len(acciones) >= MAX_ACCIONES:
        return {'ok': False, 'error': 'Demasiados cambios juntos. Pedi confirmacion de lo propuesto y despues seguimos.'}
    try:
        lineas = VISTAS[tool](cliente_id, args, pendientes)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        db.session.rollback()
        return {'ok': False, 'error': str(exc) or 'Datos invalidos.'}
    except Exception as exc:  # noqa: BLE001 - nunca romper el chat por una vista previa
        db.session.rollback()
        logger.exception('Error en vista previa %s', tool)
        return {'ok': False, 'error': type(exc).__name__}
    acciones.append({'tool': tool, 'args': args, 'resumen': lineas})
    return {'ok': True, 'data': {'pendiente_confirmacion': True, 'resumen': lineas, 'nota': NOTA_MODELO}}


def _query(cliente_id: int, usuario_id: int):
    return Propuesta.query.filter_by(cliente_id=int(cliente_id), usuario_id=int(usuario_id))


def _vigentes(cliente_id: int, usuario_id: int):
    limite = datetime.utcnow() - VIGENCIA
    return _query(cliente_id, usuario_id).filter(Propuesta.estado == 'pendiente', Propuesta.fecha_creacion >= limite)


def _serializar(fila: Propuesta) -> dict:
    acciones = json.loads(fila.acciones_json)
    return {
        'id': fila.id_propuesta,
        'resumen': [linea for accion in acciones for linea in accion['resumen']],
        'vence': (fila.fecha_creacion + VIGENCIA).isoformat() + 'Z',
    }


def descartar_pendientes(cliente_id: int, usuario_id: int, estado: str = 'reemplazada') -> None:
    _query(cliente_id, usuario_id).filter(Propuesta.estado == 'pendiente').update(
        {'estado': estado, 'fecha_resolucion': datetime.utcnow()}, synchronize_session=False)
    db.session.commit()


def crear(cliente_id: int, usuario_id: int, acciones: list) -> dict:
    """Una sola propuesta vigente por usuario: la nueva reemplaza a la anterior sin ejecutarla."""
    descartar_pendientes(cliente_id, usuario_id)
    fila = Propuesta(cliente_id=int(cliente_id), usuario_id=int(usuario_id),
                     acciones_json=json.dumps(acciones, ensure_ascii=False, default=str))
    db.session.add(fila)
    db.session.commit()
    return _serializar(fila)


def vigente(cliente_id: int, usuario_id: int) -> dict | None:
    fila = _vigentes(cliente_id, usuario_id).order_by(Propuesta.id_propuesta.desc()).first()
    return _serializar(fila) if fila else None


def _tomar(cliente_id: int, usuario_id: int, propuesta_id: int, estado: str) -> Propuesta | None:
    """Cambio atomico pendiente -> estado: un doble clic o dos pestanas no ejecutan dos veces."""
    tomadas = _vigentes(cliente_id, usuario_id).filter(Propuesta.id_propuesta == int(propuesta_id)).update(
        {'estado': estado, 'fecha_resolucion': datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    return db.session.get(Propuesta, int(propuesta_id)) if tomadas else None


def confirmar(cliente_id: int, usuario_id: int, propuesta_id: int) -> dict:
    fila = _tomar(cliente_id, usuario_id, propuesta_id, 'ejecutando')
    if not fila:
        return {'ok': False, 'mensaje': VENCIDA}
    detalle, guardado, problemas = [], [], []
    for accion in json.loads(fila.acciones_json):
        if tiene_permiso_gastronomia(permiso_de(accion['tool'])):
            resultado = ejecutar_tool(accion['tool'], accion['args'], cliente_id, usuario_id)
        else:
            resultado = {'ok': False, 'error': 'sin permiso'}
        ok, errores = guardo_algo(resultado), errores_de(resultado)
        detalle.append({'tool': accion['tool'], 'args': accion['args'], 'ok': ok, 'errores': errores})
        if ok:
            guardado.extend(accion['resumen'])
        problemas.extend(errores)
    fila.estado = 'confirmada'
    fila.resultado_json = json.dumps(detalle, ensure_ascii=False, default=str)
    db.session.commit()
    partes = ['Guardado:'] + [f'- {linea}' for linea in guardado] if guardado else ['No se guardo nada.']
    if problemas:
        partes += ['Con problemas (no se guardaron):'] + [f'- {p}' for p in problemas]
    mensaje = '\n'.join(partes)
    historial.agregar(cliente_id, usuario_id, 'assistant', f'[El usuario confirmo los cambios]\n{mensaje}')
    return {'ok': True, 'mensaje': mensaje, 'hubo_cambios': any(d['ok'] for d in detalle), 'detalle': detalle}


def cancelar(cliente_id: int, usuario_id: int, propuesta_id: int) -> dict:
    if not _tomar(cliente_id, usuario_id, propuesta_id, 'cancelada'):
        return {'ok': False, 'mensaje': VENCIDA}
    mensaje = 'Cancelado: no se guardo ningun cambio.'
    historial.agregar(cliente_id, usuario_id, 'assistant', f'[El usuario cancelo la propuesta] {mensaje}')
    return {'ok': True, 'mensaje': mensaje}
