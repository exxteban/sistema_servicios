"""Configuración de lectura tolerante a fallos; no crea filas al abrir el POS."""
from flask import current_app

from app import db
from gastronomia.sugerencias_models import GastronomiaSugerenciaConfig


def config_para_pos(cliente_id):
    fila = GastronomiaSugerenciaConfig.query.filter_by(cliente_id=cliente_id).first()
    activo = bool(fila and fila.activo and fila.mostrar_en_pos)
    return {'activo': activo, 'max': min(3, max(1, fila.max_franja)) if activo else 0}


def config_segura(cliente_id):
    try:
        return config_para_pos(cliente_id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('[gastronomia] No se pudo leer la configuración de sugerencias')
        return {'activo': False, 'max': 0}
