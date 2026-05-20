
root@testserver2:/home/administrator/sistema_silvio_cel# git status --porcelain
 D app/static/tienda_dist/assets/CatalogoPage-DAWH6CCD.js
 D app/static/tienda_dist/assets/ProductoPage-BZsW7FIv.js
 D app/static/tienda_dist/assets/WebBotStandalonePage-DuXaMuZJ.js
 D app/static/tienda_dist/assets/index-Ba7VygDZ.js
 D app/static/tienda_dist/assets/storeTheme-DHSBYUIM.js
 D app/static/tienda_dist/assets/useTiendaConfig-CI-J6xst.js
 M app/static/tienda_dist/index.html
 M app/static/uploads/branding/logo_empresa_9486e65b216749c8835b51ec3c705f0c.jpg
 M deploy/update_min.sh
?? app/static/tienda_dist/assets/CatalogoPage-BNyb9J1X.js
?? app/static/tienda_dist/assets/ProductoPage-wxLSiCgp.js
?? app/static/tienda_dist/assets/WebBotStandalonePage-DcFhJaAR.js
?? app/static/tienda_dist/assets/index-Caq4_4RU.js
?? app/static/tienda_dist/assets/storeTheme-7rCKRRWi.js
?? app/static/tienda_dist/assets/useTiendaConfig-4IcQf6CF.js
?? libs/
root@testserver2:/home/administrator/sistema_silvio_cel# sed -n '1,120p' cobranzas/routes.py
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from cobranzas import CLAVE_COBRANZAS_ACTIVO
from cobranzas.services import construir_resumen_cobranzas, listar_cuentas_por_cobrar


cobranzas_bp = Blueprint(
    'cobranzas',
    __name__,
    template_folder='templates',
)


def _resolver_denegacion():
    if not Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False):
        flash('El modulo de cobranzas esta desactivado.', 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.es_admin() or current_user.tiene_permiso('ver_cobranzas'):
        return None
    flash('No tienes permisos para acceder a cobranzas.', 'danger')
    return redirect(url_for('main.dashboard'))


@cobranzas_bp.route('/')
@login_required
def index():
    denegacion = _resolver_denegacion()
    if denegacion:
        return denegacion

    listado = listar_cuentas_por_cobrar(
        page=max(request.args.get('page', 1, type=int), 1),
        per_page=20,
        filtro_estado=(request.args.get('estado') or 'abiertas'),
        busqueda=(request.args.get('q') or ''),
    )
    return render_template(
        'cobranzas/index.html',
        resumen=construir_resumen_cobranzas(limit_cuentas=0),
        listado=listado,
    )
root@testserver2:/home/administrator/sistema_silvio_cel# systemctl cat sistema-demo1
# /etc/systemd/system/sistema-demo1.service
[Unit]
Description=Sistema Cliente 2
After=network.target mysql.service mariadb.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/home/administrator/sistema_silvio_cel
EnvironmentFile=/etc/sistema_demo1.env
ExecStart=/home/administrator/sistema_silvio_cel/.venv/bin/python /home/administrator/sistema_silvio_cel/run.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
root@testserver2:/home/administrator/sistema_silvio_cel# 