"""
Rutas de edicion segura de compras.
"""
from datetime import date, datetime

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Compra, Proveedor
from app.routes.compras import compras_bp
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.compra_facturas import (
    eliminar_factura_compra,
    extension_permitida,
    guardar_factura_compra,
)


def _puede_editar_compra() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('crear_compra')


def _parse_fecha(valor: str):
    valor = (valor or '').strip()
    if not valor:
        return date.today()
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_hora(valor: str):
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%H:%M').time()
    except ValueError:
        return None


def _obtener_proveedor_respaldo():
    proveedor = Proveedor.query.filter_by(nombre='SIN PROVEEDOR').first()
    if proveedor:
        return proveedor

    proveedor = Proveedor(nombre='SIN PROVEEDOR', ruc='00000000-0', activo=True)
    db.session.add(proveedor)
    db.session.flush()
    return proveedor


def _compra_auditoria_data(compra: Compra) -> dict:
    return {
        'id_compra': compra.id_compra,
        'id_proveedor': compra.id_proveedor,
        'proveedor': compra.proveedor.nombre if compra.proveedor else None,
        'numero_factura': compra.numero_factura,
        'fecha_compra': compra.fecha_compra.isoformat() if compra.fecha_compra else None,
        'hora_compra': compra.hora_compra.strftime('%H:%M') if compra.hora_compra else None,
        'factura_imagen_url': compra.factura_imagen_url,
        'observaciones': compra.observaciones,
        'tipo_compra': compra.tipo_compra,
        'pagada': bool(compra.pagada),
        'total': float(compra.total or 0),
    }


@compras_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar solo datos no sensibles de una compra."""
    if not _puede_editar_compra():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta accion esta deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar compras.', 'danger')
        return redirect(url_for('compras.detalle', id=id))

    compra = Compra.query.get_or_404(id)

    if request.method == 'POST':
        numero_factura = request.form.get('numero_factura', '').strip() or None
        observaciones = request.form.get('observaciones', '').strip() or None
        quitar_factura = request.form.get('quitar_factura') in ('1', 'true', 'on', 'si')
        factura_imagen = request.files.get('factura_imagen')
        fecha_compra = _parse_fecha(request.form.get('fecha_compra'))
        hora_compra = _parse_hora(request.form.get('hora_compra'))
        id_proveedor = request.form.get('id_proveedor', type=int)

        if fecha_compra is None:
            flash('La fecha de compra no es valida.', 'warning')
        elif (request.form.get('hora_compra') or '').strip() and hora_compra is None:
            flash('La hora de compra no es valida.', 'warning')
        elif factura_imagen and factura_imagen.filename and not extension_permitida(factura_imagen.filename):
            flash('La foto de factura debe ser PNG, JPG, JPEG, WEBP o GIF.', 'warning')
        else:
            factura_anterior = compra.factura_imagen_url
            datos_anteriores = _compra_auditoria_data(compra)

            try:
                proveedor = Proveedor.query.get(id_proveedor) if id_proveedor else _obtener_proveedor_respaldo()
                if not proveedor or not proveedor.activo:
                    flash('Debe seleccionar un proveedor valido.', 'warning')
                else:
                    compra.id_proveedor = proveedor.id_proveedor
                    compra.numero_factura = numero_factura
                    compra.fecha_compra = fecha_compra
                    compra.hora_compra = hora_compra
                    compra.observaciones = observaciones

                    if factura_imagen and factura_imagen.filename:
                        compra.factura_imagen_url = guardar_factura_compra(
                            factura_imagen,
                            current_app.static_folder,
                            fecha_compra,
                            compra.id_compra,
                        )
                    elif quitar_factura:
                        compra.factura_imagen_url = None

                    registrar_auditoria(
                        accion='editar_compra',
                        modulo='compras',
                        descripcion=f'Edito compra #{compra.id_compra}',
                        referencia_tipo='compra',
                        referencia_id=compra.id_compra,
                        datos_anteriores=datos_anteriores,
                        datos_nuevos=_compra_auditoria_data(compra),
                        commit=False,
                    )

                    db.session.commit()

                    if factura_anterior and factura_anterior != compra.factura_imagen_url:
                        try:
                            eliminar_factura_compra(factura_anterior, current_app.static_folder)
                        except OSError:
                            current_app.logger.warning(
                                'No se pudo eliminar la factura anterior de la compra %s',
                                compra.id_compra,
                            )

                    flash(f'Compra #{compra.id_compra} actualizada correctamente.', 'success')
                    return redirect(url_for('compras.detalle', id=compra.id_compra))
            except PermissionError:
                db.session.rollback()
                current_app.logger.exception('Sin permisos para actualizar factura de compra')
                flash('No hay permisos para guardar la foto de la factura.', 'danger')
            except ValueError:
                db.session.rollback()
                current_app.logger.exception('Factura de compra invalida al editar')
                flash('La foto de la factura no se pudo procesar.', 'warning')
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Error al editar compra %s', compra.id_compra)
                flash('Ocurrio un error al actualizar la compra. Intente nuevamente.', 'danger')

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('compras/editar.html', compra=compra, proveedores=proveedores)
