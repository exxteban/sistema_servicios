"""
Rutas de proveedores
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import Proveedor
from app.utils.permisos import validar_autorizacion

proveedores_bp = Blueprint('proveedores', __name__)


@proveedores_bp.route('/')
@login_required
def listar():
    """Listar todos los proveedores activos"""
    if not current_user.tiene_permiso('ver_proveedores'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver proveedores.', 'danger')
        return redirect(url_for('main.dashboard'))

    busqueda = request.args.get('q', '').strip()
    
    query = Proveedor.query.filter_by(activo=True)
    
    if busqueda:
        query = query.filter(
            db.or_(
                Proveedor.nombre.ilike(f'%{busqueda}%'),
                Proveedor.ruc.ilike(f'%{busqueda}%')
            )
        )
    
    proveedores = query.order_by(Proveedor.nombre).all()
    
    return render_template('proveedores/listar.html',
        proveedores=proveedores,
        busqueda=busqueda
    )


@proveedores_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crear nuevo proveedor"""
    if not current_user.tiene_permiso('crear_proveedor'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para crear proveedores.', 'danger')
        return redirect(url_for('proveedores.listar'))

    if request.method == 'POST':
        try:
            proveedor = Proveedor(
                nombre=request.form['nombre'].strip(),
                ruc=request.form.get('ruc', '').strip() or None,
                telefono=request.form.get('telefono', '').strip(),
                email=request.form.get('email', '').strip(),
                direccion=request.form.get('direccion', '').strip(),
                contacto_nombre=request.form.get('contacto_nombre', '').strip(),
                contacto_telefono=request.form.get('contacto_telefono', '').strip(),
                dias_credito=int(request.form.get('dias_credito', 0)),
                notas=request.form.get('notas', '').strip()
            )
            
            db.session.add(proveedor)
            db.session.commit()
            
            flash('Proveedor creado exitosamente', 'success')
            return redirect(url_for('proveedores.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear proveedor: {str(e)}', 'error')
    
    return render_template('proveedores/formulario.html', proveedor=None)


@proveedores_bp.route('/crear_rapido', methods=['POST'])
@login_required
def crear_rapido():
    """Crear proveedor rápido (desde compras)"""
    if not current_user.tiene_permiso('crear_proveedor'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'success': False, 'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'success': False, 'error': 'Sin permisos para crear proveedores', 'modo_demo': False}), 403

    data = request.get_json() or {}
    nombre = (data.get('nombre') or '').strip()
    ruc = (data.get('ruc') or '').strip() or None
    telefono = (data.get('telefono') or '').strip()
    email = (data.get('email') or '').strip()
    direccion = (data.get('direccion') or '').strip()
    contacto_nombre = (data.get('contacto_nombre') or '').strip()
    contacto_telefono = (data.get('contacto_telefono') or '').strip()
    notas = (data.get('notas') or '').strip()

    if not nombre:
        return jsonify({'success': False, 'error': 'El nombre es obligatorio'}), 400

    try:
        proveedor = Proveedor(
            nombre=nombre,
            ruc=ruc,
            telefono=telefono,
            email=email,
            direccion=direccion,
            contacto_nombre=contacto_nombre,
            contacto_telefono=contacto_telefono,
            dias_credito=0,
            notas=notas,
            activo=True
        )
        db.session.add(proveedor)
        db.session.commit()

        return jsonify({
            'success': True,
            'proveedor': {
                'id_proveedor': proveedor.id_proveedor,
                'nombre': proveedor.nombre
            }
        })
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'RUC ya registrado'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@proveedores_bp.route('/<int:id_proveedor>/editar', methods=['GET', 'POST'])
@login_required
def editar(id_proveedor):
    """Editar proveedor existente"""
    if not current_user.tiene_permiso('editar_proveedor'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar proveedores.', 'danger')
        return redirect(url_for('proveedores.listar'))

    proveedor = Proveedor.query.get_or_404(id_proveedor)
    
    if request.method == 'POST':
        try:
            proveedor.nombre = request.form['nombre'].strip()
            proveedor.ruc = request.form.get('ruc', '').strip() or None
            proveedor.telefono = request.form.get('telefono', '').strip()
            proveedor.email = request.form.get('email', '').strip()
            proveedor.direccion = request.form.get('direccion', '').strip()
            proveedor.contacto_nombre = request.form.get('contacto_nombre', '').strip()
            proveedor.contacto_telefono = request.form.get('contacto_telefono', '').strip()
            proveedor.dias_credito = int(request.form.get('dias_credito', 0))
            proveedor.notas = request.form.get('notas', '').strip()
            
            db.session.commit()
            
            flash('Proveedor actualizado exitosamente', 'success')
            return redirect(url_for('proveedores.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar proveedor: {str(e)}', 'error')
    
    return render_template('proveedores/formulario.html', proveedor=proveedor)


@proveedores_bp.route('/<int:id_proveedor>/eliminar', methods=['POST'])
@login_required
def eliminar(id_proveedor):
    """Desactivar proveedor"""
    if not current_user.tiene_permiso('eliminar_proveedor'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para eliminar proveedores.', 'danger')
        return redirect(url_for('proveedores.listar'))

    ok, _autorizacion = validar_autorizacion(
        request.form.get('id_autorizacion', type=int),
        'eliminar_proveedor'
    )
    if not ok:
        flash('Se requiere autorización de administrador para eliminar proveedores.', 'danger')
        return redirect(url_for('proveedores.listar'))

    proveedor = Proveedor.query.get_or_404(id_proveedor)
    
    try:
        proveedor.activo = False
        db.session.commit()
        flash('Proveedor desactivado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al desactivar proveedor: {str(e)}', 'error')
    
    return redirect(url_for('proveedores.listar'))


@proveedores_bp.route('/api/buscar')
@login_required
def api_buscar():
    """API para buscar proveedores (para autocomplete)"""
    if not current_user.tiene_permiso('ver_proveedores'):
        modo_demo = bool(getattr(current_user, 'modo_demo', False))
        payload = {'items': [], 'modo_demo': modo_demo}
        if modo_demo:
            payload['mensaje'] = 'Modo demo: esta acción está deshabilitada'
        else:
            payload['mensaje'] = 'Sin permisos'
        return jsonify(payload), 403

    q = request.args.get('q', '').strip()
    
    if not q or len(q) < 2:
        return jsonify([])
    
    proveedores = Proveedor.query.filter(
        Proveedor.activo == True,
        db.or_(
            Proveedor.nombre.ilike(f'%{q}%'),
            Proveedor.ruc.ilike(f'%{q}%')
        )
    ).limit(10).all()
    
    return jsonify([{
        'id': p.id_proveedor,
        'nombre': p.nombre,
        'ruc': p.ruc,
        'telefono': p.telefono
    } for p in proveedores])
