"""Pre-chequeo de factura electronica en el POS, antes de registrar la venta."""
from decimal import Decimal, InvalidOperation

from flask import jsonify, request
from flask_login import current_user, login_required

from app import db
from app.models.cliente import Cliente
from app.services.fe_pos import contexto_factura_electronica_pos, validar_factura_antes_de_cobrar

from .parte1 import ventas_bp


@ventas_bp.route('/pos/factura-electronica/validar', methods=['POST'])
@login_required
def validar_factura_electronica_pos():
    """Dice si la factura saldria con el cliente y total actuales del POS.

    La emision corre despues de cobrar; si el receptor no sirve, conviene
    saberlo ahora, mientras todavia se puede cambiar el cliente.
    """
    if not current_user.tiene_permiso('crear_venta'):
        return jsonify({'ok': False, 'mensaje': 'Sin permisos para cobrar.'}), 403
    if not contexto_factura_electronica_pos()['lista']:
        return jsonify({
            'ok': False,
            'mensaje': 'La facturacion electronica no esta activa o su configuracion esta incompleta.',
        }), 400
    data = request.get_json(silent=True) or {}
    try:
        total = Decimal(str(data.get('total') or 0))
        cliente_id = int(data.get('id_cliente') or 1)
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({'ok': False, 'mensaje': 'Datos de la venta invalidos.'}), 400
    cliente = None
    if cliente_id != 1:
        cliente = db.session.get(Cliente, cliente_id)
        if cliente is None or not cliente.activo:
            return jsonify({'ok': False, 'mensaje': 'El cliente de la factura no existe o esta inactivo.'}), 400
    try:
        validar_factura_antes_de_cobrar(cliente, total)
    except ValueError as exc:
        return jsonify({'ok': False, 'mensaje': str(exc)}), 400
    return jsonify({'ok': True})
