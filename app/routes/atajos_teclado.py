"""Guardar las teclas rapidas del usuario (ver app/services/atajos_teclado)."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app import db
from app.services.atajos_teclado import contexto_atajos, set_atajos

atajos_teclado_bp = Blueprint('atajos_teclado', __name__)


@atajos_teclado_bp.route('/api/atajos-teclado', methods=['GET'])
@login_required
def obtener():
    return jsonify({'ok': True, 'atajos': contexto_atajos(current_user)})


@atajos_teclado_bp.route('/api/atajos-teclado', methods=['POST'])
@login_required
def guardar():
    data = request.get_json(silent=True) or {}
    atajos = data.get('atajos')
    if not isinstance(atajos, dict):
        return jsonify({'ok': False, 'mensaje': 'Las teclas recibidas no son válidas.'}), 400
    set_atajos(current_user, atajos)
    db.session.commit()
    return jsonify({'ok': True, 'atajos': contexto_atajos(current_user)})
