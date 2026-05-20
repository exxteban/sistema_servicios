from flask import Blueprint

inteligencia_bp = Blueprint('inteligencia', __name__)

from . import dashboard

__all__ = ['inteligencia_bp', 'dashboard']
