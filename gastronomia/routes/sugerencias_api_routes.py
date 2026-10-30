"""Consulta opcional del POS: solo asociaciones preparadas, nunca escribe pedidos."""
from time import monotonic

from flask import current_app, jsonify, request
from flask_login import login_required

from app import db
from gastronomia.routes.api_routes import gastronomia_api_bp
from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.channel_price_service import normalizar_canal_precio
from gastronomia.services.permisos import PERMISO_POS, requiere_permiso_gastronomia
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.candidatos import previsualizar
from gastronomia.services.sugerencias.pos import config_para_pos


def _ids(texto):
    ids = []
    for parte in (texto or '')[:4096].split(',')[:C.MAX_PRODUCTOS_CARRITO]:
        if parte.strip().isascii() and parte.strip().isdigit():
            numero = int(parte)
            if 0 < numero <= 2147483647:
                ids.append(numero)
    return ids


@gastronomia_api_bp.route('/sugerencias')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def sugerencias_pos():
    plazo = monotonic() + C.PRESUPUESTO_POS_SEGUNDOS
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'error': 'gastronomia_no_activa'}), 403
    sugerencias, maximo = [], 0
    try:
        config = config_para_pos(cliente_id)
        if config['activo']:
            maximo = config['max']
            canal = normalizar_canal_precio(request.args.get('canal_precio'))
            ids = _ids(request.args.get('productos'))
            resultado = previsualizar(cliente_id, ids, canal_precio=canal, plazo=plazo) if ids else {'sugerencias': []}
            if monotonic() < plazo:
                sugerencias = [{k: fila[k] for k in ('id_producto', 'motivo', 'fuente', 'id_origen')}
                               for fila in resultado['sugerencias']]
    except (TimeoutError, ValueError):
        db.session.rollback()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('[gastronomia] Falló la consulta opcional de sugerencias del POS')
    respuesta = jsonify({'ok': True, 'sugerencias': sugerencias, 'max': maximo})
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta
