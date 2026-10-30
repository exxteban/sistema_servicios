"""Administración del sugeridor; conserva autenticación, CSRF y contexto gastronómico."""
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaRegla as Regla,
    GastronomiaSugerenciaExcluido as Excluido, GastronomiaSugerenciaCalculo as Estado,
)
from gastronomia.services.sugerencias import reglas
from gastronomia.services.sugerencias.candidatos import previsualizar
from gastronomia.services.sugerencias.recalculo_manual import solicitar


@gastronomia_bp.route('/sugerencias', methods=['GET', 'POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def sugerencias_config():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('gastronomia.dashboard'))
    if request.method == 'POST':
        try:
            _guardar(cliente_id)
            flash('Cambios guardados.' if request.form.get('accion') != 'recalcular'
                  else 'Recálculo solicitado. Actualizá la página para consultar el estado.', 'success')
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'warning')
        except IntegrityError:
            db.session.rollback()
            flash('Otro usuario modificó estos datos. Actualizá la página e intentá de nuevo.', 'warning')
        return redirect(url_for('gastronomia.sugerencias_config'))
    productos = GastronomiaProducto.query.filter_by(cliente_id=cliente_id).order_by(GastronomiaProducto.nombre).all()
    categorias = GastronomiaCategoria.query.filter_by(cliente_id=cliente_id).order_by(GastronomiaCategoria.nombre).all()
    opciones = {}
    for p in productos:
        estado = (' · inactivo' if not p.activo else ' · no disponible' if not p.disponible
                  else ' · sin stock' if p.control_stock_venta and (p.stock_disponible or 0) <= 0
                  else ' · no visible' if not p.visible else '')
        opciones[f'producto:{p.id_producto}'] = p.nombre + estado
    opciones.update({f'categoria:{c.id_categoria}': 'Categoría: ' + c.nombre for c in categorias})
    filas = Regla.query.filter_by(cliente_id=cliente_id).order_by(Regla.prioridad.desc(), Regla.id.desc()).all()
    busqueda = request.args.get('q', '').strip()[:120]
    if busqueda:
        filas = [r for r in filas if busqueda.casefold() in (
            opciones.get(f'{r.origen_tipo}:{r.origen_id}', 'Cualquier pedido') + ' ' +
            opciones.get(f'{r.destino_tipo}:{r.destino_id}', '')).casefold()]
    editar = Regla.query.filter_by(cliente_id=cliente_id, id=request.args.get('editar', type=int)).first() if request.args.get('editar') else None
    preview = None
    seleccionado = request.args.get('producto', '')
    if seleccionado:
        try:
            tipo, numero = reglas.referencia(cliente_id, seleccionado)
            if tipo != 'producto':
                raise ValueError('Elegí un plato para la vista previa.')
            preview = previsualizar(cliente_id, [numero])
        except ValueError as exc:
            flash(str(exc), 'warning')
    return render_template('gastronomia/sugerencias/index.html',
                           config=Config.query.filter_by(cliente_id=cliente_id).first(),
                           estado=Estado.query.filter_by(cliente_id=cliente_id).first(),
                           reglas=filas, editar=editar, opciones=opciones, busqueda=busqueda,
                           exclusiones=Excluido.query.filter_by(cliente_id=cliente_id).all(),
                           preview=preview, seleccionado=seleccionado)


def _guardar(cliente_id):
    data = request.form
    accion = data.get('accion')
    if accion == 'config':
        reglas.guardar_config(cliente_id, data)
    elif accion == 'regla':
        numero = _numero(data.get('regla_id')) if data.get('regla_id') else None
        reglas.guardar_regla(cliente_id, current_user.id_usuario, data, numero)
    elif accion in ('alternar', 'eliminar'):
        reglas.cambiar_regla(cliente_id, _numero(data.get('regla_id')), accion)
    elif accion == 'excluir':
        reglas.excluir(cliente_id, data.get('destino'))
    elif accion == 'quitar_exclusion':
        reglas.quitar_exclusion(cliente_id, _numero(data.get('exclusion_id')))
    elif accion == 'recalcular':
        if not solicitar(current_app._get_current_object(), cliente_id):
            raise ValueError('Ya hay un recálculo solicitado para este negocio.')
    else:
        raise ValueError('Acción inválida.')


def _numero(valor):
    try:
        numero = int(valor)
        if numero > 0:
            return numero
    except (TypeError, ValueError):
        pass
    raise ValueError('Identificador inválido.')
