from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app import csrf
from app.services.ia_backoffice.security import es_usuario_root
from app.services.publicidad_ads_analytics import LANDING_KEY, obtener_dashboard_publicidad_ads, registrar_evento_publicidad_ads


publicidad_ads_bp = Blueprint('publicidad_ads', __name__)


def _landing_dir() -> Path:
    return Path(current_app.root_path).resolve().parent / 'publicidad_ads'


def _require_root():
    if not es_usuario_root(current_user):
        abort(403)


@publicidad_ads_bp.route('/publicidad-ads')
def landing_publicidad_ads_redirect():
    return redirect(url_for('publicidad_ads.landing_publicidad_ads'), code=302)


@publicidad_ads_bp.route('/publicidad-ads/')
def landing_publicidad_ads():
    return send_from_directory(str(_landing_dir()), 'index.html')


@publicidad_ads_bp.route('/publicidad-ads/admin')
@login_required
def admin_publicidad_ads():
    _require_root()
    dashboard = obtener_dashboard_publicidad_ads()
    return render_template(
        'publicidad_ads/admin.html',
        landing_key=LANDING_KEY,
        dashboard=dashboard,
        landing_public_url=request.url_root.rstrip('/') + '/publicidad-ads/',
    )


@publicidad_ads_bp.route('/api/publicidad-ads/evento', methods=['POST'])
@csrf.exempt
def registrar_evento():
    data = request.get_json(silent=True) or {}
    if (data.get('landing') or LANDING_KEY) != LANDING_KEY:
        return jsonify({'error': 'landing_invalida'}), 400
    try:
        evento = registrar_evento_publicidad_ads(data)
    except ValueError:
        return jsonify({'error': 'evento_invalido'}), 400
    return jsonify({'ok': True, 'id_evento': evento.id_evento}), 202


@publicidad_ads_bp.route('/publicidad-ads/<path:asset_path>')
def asset_publicidad_ads(asset_path: str):
    directory = _landing_dir()
    return send_from_directory(str(directory), asset_path)
