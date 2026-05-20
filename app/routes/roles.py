"""
Rutas de administración de roles y permisos
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Rol, Permiso
from app.models.rol import rol_permisos
from app.utils.auditoria_utils import registrar_auditoria


roles_bp = Blueprint('roles', __name__)


def _nivel_jerarquia(usuario):
    return usuario.rol.nivel_jerarquia if usuario and usuario.rol else 0


def _roles_editables():
    nivel_actual = _nivel_jerarquia(current_user)
    return Rol.query.filter(
        Rol.activo == True,
        Rol.nivel_jerarquia < nivel_actual
    ).order_by(Rol.nivel_jerarquia.desc()).all()


def _agrupar_permisos(permisos):
    agrupados = {}
    for p in permisos:
        modulo = p.modulo or 'otros'
        agrupados.setdefault(modulo, []).append(p)
    return agrupados


def _url_for(endpoint, **values):
    if request.args.get('partial'):
        values.setdefault('partial', 1)
    return url_for(endpoint, **values)


@roles_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('gestionar_roles'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar roles.', 'danger')
        return redirect(_url_for('main.dashboard'))

    roles = _roles_editables()
    return render_template('roles/listar.html', roles=roles)


@roles_bp.route('/<int:id_rol>/editar', methods=['GET', 'POST'])
@login_required
def editar(id_rol):
    if not current_user.tiene_permiso('gestionar_roles'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar roles.', 'danger')
        return redirect(_url_for('main.dashboard'))

    rol = Rol.query.get_or_404(id_rol)
    nivel_actual = _nivel_jerarquia(current_user)
    if not rol.activo or (rol.nivel_jerarquia or 0) >= nivel_actual:
        flash('No puedes editar un rol de igual o mayor nivel.', 'danger')
        return redirect(_url_for('roles.listar'))

    permisos = Permiso.query.filter_by(activo=True).order_by(Permiso.modulo.asc(), Permiso.nombre.asc()).all()
    permisos_por_modulo = _agrupar_permisos(permisos)
    selected_permiso_ids = {p.id_permiso for p in rol.permisos.filter_by(activo=True).all()}

    if request.method == 'POST':
        nuevos_ids = request.form.getlist('permisos_rol')
        nuevos_ids = sorted({int(x) for x in nuevos_ids if str(x).isdigit()})

        permisos_validos = Permiso.query.filter(
            Permiso.activo == True,
            Permiso.id_permiso.in_(nuevos_ids)
        ).all()
        permisos_validos_ids = {p.id_permiso for p in permisos_validos}

        db.session.execute(
            rol_permisos.delete().where(rol_permisos.c.id_rol == rol.id_rol)
        )
        for id_permiso in sorted(permisos_validos_ids):
            db.session.execute(
                rol_permisos.insert().values(id_rol=rol.id_rol, id_permiso=id_permiso)
            )
        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='editar_rol_permisos',
                    modulo='configuracion',
                    descripcion=f'Editó permisos del rol {rol.nombre}',
                    referencia_tipo='rol',
                    referencia_id=rol.id_rol,
                    datos_anteriores={'permisos': sorted(selected_permiso_ids)},
                    datos_nuevos={'permisos': sorted(permisos_validos_ids)},
                    commit=False
                )
        except Exception:
            pass

        db.session.commit()

        flash('Permisos del rol actualizados.', 'success')
        return redirect(_url_for('roles.listar'))

    return render_template(
        'roles/editar.html',
        rol=rol,
        permisos_por_modulo=permisos_por_modulo,
        selected_permiso_ids=selected_permiso_ids
    )
