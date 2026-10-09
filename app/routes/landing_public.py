from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory, url_for


landing_public_bp = Blueprint('landing_public', __name__)


def _project_root() -> Path:
    return Path(current_app.root_path).resolve().parent


@landing_public_bp.route('/landing')
def landing_redirect():
    return redirect(url_for('landing_public.landing_page'), code=302)


@landing_public_bp.route('/landing.html')
def landing_page():
    return send_from_directory(str(_project_root()), 'landing.html')


@landing_public_bp.route('/landing_assets/<path:asset_path>')
def landing_asset(asset_path: str):
    return send_from_directory(str(_project_root() / 'landing_assets'), asset_path)
