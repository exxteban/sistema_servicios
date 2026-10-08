"""Listas en cascada de departamento → distrito → ciudad de la configuración.

Vive aparte de `routes.py` por tamaño y se cuelga del mismo blueprint. Cada
modo de emisión tiene su propia tabla (ver `services/geo.py`), y la pantalla
manda el proveedor elegido en el formulario: al cambiarlo, las listas tienen
que ser las del modo nuevo aunque todavía no se haya guardado.
"""
from flask import jsonify, request
from flask_login import login_required

from facturacion_electronica.routes import facturacion_electronica_bp
from facturacion_electronica.services import geo
from facturacion_electronica.services.config_service import obtener_configuracion


def _proveedor():
    return request.args.get('proveedor') or obtener_configuracion().proveedor


@facturacion_electronica_bp.route('/geo/distritos')
@login_required
def geo_distritos():
    return jsonify(geo.distritos_de(request.args.get('departamento'), _proveedor()))


@facturacion_electronica_bp.route('/geo/ciudades')
@login_required
def geo_ciudades():
    return jsonify(geo.ciudades_de(request.args.get('distrito'), _proveedor()))
