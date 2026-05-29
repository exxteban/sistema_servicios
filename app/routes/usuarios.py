"""
Rutas de administración de usuarios
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Usuario, Rol, Permiso, Cliente
from app.services.usuarios_admin import (
    agrupar_permisos,
    map_permisos_por_rol,
    nivel_jerarquia,
    puede_gestionar_usuario,
    roles_asignables,
    set_permisos_adicionales,
    tiene_otro_admin_activo,
)
from app.utils.auditoria_utils import registrar_auditoria


usuarios_bp = Blueprint('usuarios', __name__)


def _clientes_asignables():
    return Cliente.query.filter(
        Cliente.activo == True,
        Cliente.id_cliente != 1,
    ).order_by(Cliente.nombre.asc(), Cliente.id_cliente.asc()).all()


@usuarios_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    buscar = request.args.get('buscar', '').strip()
    rol_id = request.args.get('rol', 0, type=int)
    estado = request.args.get('estado', '').strip()

    nivel_actual = nivel_jerarquia(current_user)

    query = Usuario.query.join(Rol, Usuario.id_rol == Rol.id_rol)

    if buscar:
        query = query.filter(
            db.or_(
                Usuario.username.ilike(f'%{buscar}%'),
                Usuario.nombre_completo.ilike(f'%{buscar}%')
            )
        )

    if rol_id:
        query = query.filter(Usuario.id_rol == rol_id)

    estado = estado if estado in {'activos', 'inactivos'} else 'activos'
    if estado == 'activos':
        query = query.filter(Usuario.activo == True)
    else:
        query = query.filter(Usuario.activo == False)

    query = query.filter(
        db.or_(
            Usuario.id_usuario == current_user.id_usuario,
            Rol.nivel_jerarquia < nivel_actual
        )
    )

    usuarios = query.order_by(Usuario.username.asc()).paginate(
        page=page, per_page=20, error_out=False
    )

    roles_filtro = Rol.query.filter(
        Rol.activo == True,
        Rol.nivel_jerarquia <= nivel_actual
    ).order_by(Rol.nivel_jerarquia.desc()).all()

    return render_template(
        'usuarios/listar.html',
        usuarios=usuarios,
        roles=roles_filtro,
        buscar=buscar,
        rol_id=rol_id,
        estado=estado,
        active_tab='usuarios'
    )


@usuarios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    roles = roles_asignables(current_user)
    clientes_disponibles = _clientes_asignables()
    clientes_disponibles_ids = {cliente.id_cliente for cliente in clientes_disponibles}
    permisos_por_rol = map_permisos_por_rol(roles)
    permisos = Permiso.query.filter_by(activo=True).order_by(Permiso.modulo.asc(), Permiso.nombre.asc()).all()
    permisos_por_modulo = agrupar_permisos(permisos)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        nombre_completo = request.form.get('nombre_completo', '').strip()
        password = request.form.get('password', '')
        id_rol = request.form.get('id_rol', type=int)
        id_cliente = request.form.get('id_cliente', type=int) or None
        activo = bool(request.form.get('activo'))
        modo_demo = bool(request.form.get('modo_demo'))
        ids_permiso_extra = request.form.getlist('permisos_extra')

        if not username or not nombre_completo or not password or not id_rol:
            flash('Username, nombre, contraseña y rol son obligatorios.', 'warning')
            return render_template(
                'usuarios/nuevo.html',
                roles=roles,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=id_cliente,
                selected_permiso_ids=set(int(x) for x in ids_permiso_extra if str(x).isdigit()),
                modo_demo=modo_demo,
                error_field='required'
            )

        if len(password) < 4:
            flash('La contraseña debe tener al menos 4 caracteres.', 'warning')
            return render_template(
                'usuarios/nuevo.html',
                roles=roles,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=id_cliente,
                selected_permiso_ids=set(int(x) for x in ids_permiso_extra if str(x).isdigit()),
                modo_demo=modo_demo,
                error_field='password'
            )

        if Usuario.query.filter_by(username=username).first():
            flash('Ya existe un usuario con ese username.', 'danger')
            return render_template(
                'usuarios/nuevo.html',
                roles=roles,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=id_cliente,
                selected_permiso_ids=set(int(x) for x in ids_permiso_extra if str(x).isdigit()),
                modo_demo=modo_demo,
                error_field='username',
                form_data={'username': username, 'nombre_completo': nombre_completo}
            )

        if id_rol not in {r.id_rol for r in roles}:
            flash('No puedes asignar ese rol.', 'danger')
            return render_template(
                'usuarios/nuevo.html',
                roles=roles,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=id_cliente,
                selected_permiso_ids=set(int(x) for x in ids_permiso_extra if str(x).isdigit()),
                modo_demo=modo_demo,
                error_field='id_rol'
            )

        if id_cliente is not None and id_cliente not in clientes_disponibles_ids:
            flash('Debes seleccionar un cliente activo válido.', 'danger')
            return render_template(
                'usuarios/nuevo.html',
                roles=roles,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=id_cliente,
                selected_permiso_ids=set(int(x) for x in ids_permiso_extra if str(x).isdigit()),
                modo_demo=modo_demo,
                error_field='id_cliente'
            )

        usuario = Usuario(
            id_cliente=id_cliente,
            username=username,
            nombre_completo=nombre_completo,
            id_rol=id_rol,
            activo=activo
        )
        usuario.set_password(password)

        db.session.add(usuario)
        db.session.flush()
        usuario.set_preferencia('modo_demo', '1' if modo_demo else '0')
        set_permisos_adicionales(usuario.id_usuario, ids_permiso_extra, current_user.id_usuario)
        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_usuario',
                    modulo='configuracion',
                    descripcion=f'Creó usuario {usuario.username}',
                    referencia_tipo='usuario',
                    referencia_id=usuario.id_usuario,
                    datos_nuevos={
                        'id_usuario': usuario.id_usuario,
                        'username': usuario.username,
                        'nombre_completo': usuario.nombre_completo,
                        'id_cliente': usuario.id_cliente,
                        'id_rol': usuario.id_rol,
                        'activo': bool(usuario.activo),
                        'modo_demo': bool(usuario.modo_demo),
                    },
                    commit=False
                )
        except Exception:
            pass
        db.session.commit()

        flash('Usuario creado correctamente.', 'success')
        return redirect(url_for('usuarios.listar'))

    return render_template(
        'usuarios/nuevo.html',
        roles=roles,
        permisos_por_rol=permisos_por_rol,
        permisos_por_modulo=permisos_por_modulo,
        clientes_disponibles=clientes_disponibles,
        selected_cliente_id=None,
        modo_demo=False,
        selected_permiso_ids=set()
    )


@usuarios_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    usuario = Usuario.query.get_or_404(id)
    if not puede_gestionar_usuario(current_user, usuario):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para administrar este usuario.', 'danger')
        return redirect(url_for('usuarios.listar'))

    es_mi_usuario = usuario.id_usuario == current_user.id_usuario
    puede_editar_rol_permisos = (
        (not es_mi_usuario)
        and current_user.tiene_permiso('gestionar_roles')
        and usuario.rol is not None
        and nivel_jerarquia(current_user) > (usuario.rol.nivel_jerarquia or 0)
    )
    roles_disponibles = roles_asignables(current_user)
    roles_select = roles_disponibles[:]
    clientes_disponibles = _clientes_asignables()
    clientes_disponibles_ids = {cliente.id_cliente for cliente in clientes_disponibles}
    if usuario.rol and usuario.rol not in roles_select:
        roles_select.append(usuario.rol)
        roles_select.sort(key=lambda r: r.nivel_jerarquia or 0, reverse=True)

    permisos_por_rol = map_permisos_por_rol(roles_select)
    permisos = Permiso.query.filter_by(activo=True).order_by(Permiso.modulo.asc(), Permiso.nombre.asc()).all()
    permisos_por_modulo = agrupar_permisos(permisos)
    selected_permiso_ids = {p.id_permiso for p in usuario.permisos_adicionales.all()}

    if request.method == 'POST':
        datos_anteriores = {
            'username': usuario.username,
            'nombre_completo': usuario.nombre_completo,
            'id_rol': usuario.id_rol,
            'id_cliente': usuario.id_cliente,
            'activo': bool(usuario.activo),
            'permisos_adicionales': sorted(selected_permiso_ids),
            'modo_demo': bool(usuario.modo_demo),
        }

        username = request.form.get('username', '').strip()
        nombre_completo = request.form.get('nombre_completo', '').strip()
        password = request.form.get('password', '')
        selected_cliente_id = request.form.get('id_cliente', type=int) or None

        if not username or not nombre_completo:
            flash('Username y nombre son obligatorios.', 'warning')
            return render_template(
                'usuarios/editar.html',
                usuario=usuario,
                roles=roles_select,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=selected_cliente_id,
                selected_permiso_ids=selected_permiso_ids,
                es_mi_usuario=es_mi_usuario,
                puede_editar_rol_permisos=puede_editar_rol_permisos
            )

        otro = Usuario.query.filter(Usuario.username == username, Usuario.id_usuario != usuario.id_usuario).first()
        if otro:
            flash('Ya existe un usuario con ese username.', 'danger')
            return render_template(
                'usuarios/editar.html',
                usuario=usuario,
                roles=roles_select,
                permisos_por_rol=permisos_por_rol,
                permisos_por_modulo=permisos_por_modulo,
                clientes_disponibles=clientes_disponibles,
                selected_cliente_id=selected_cliente_id,
                selected_permiso_ids=selected_permiso_ids,
                es_mi_usuario=es_mi_usuario,
                puede_editar_rol_permisos=puede_editar_rol_permisos
            )

        usuario.username = username
        usuario.nombre_completo = nombre_completo

        if password:
            if len(password) < 4:
                flash('La contraseña debe tener al menos 4 caracteres.', 'warning')
                return render_template(
                    'usuarios/editar.html',
                    usuario=usuario,
                    roles=roles_select,
                    permisos_por_rol=permisos_por_rol,
                    permisos_por_modulo=permisos_por_modulo,
                    clientes_disponibles=clientes_disponibles,
                    selected_cliente_id=selected_cliente_id,
                    selected_permiso_ids=selected_permiso_ids,
                    es_mi_usuario=es_mi_usuario,
                    puede_editar_rol_permisos=puede_editar_rol_permisos
                )
            usuario.set_password(password)

        if not es_mi_usuario:
            id_rol = request.form.get('id_rol', type=int)
            activo = bool(request.form.get('activo'))
            modo_demo = bool(request.form.get('modo_demo'))
            ids_permiso_extra = request.form.getlist('permisos_extra')

            if id_rol not in {r.id_rol for r in roles_disponibles}:
                flash('No puedes asignar ese rol.', 'danger')
                return render_template(
                    'usuarios/editar.html',
                    usuario=usuario,
                    roles=roles_select,
                    permisos_por_rol=permisos_por_rol,
                    permisos_por_modulo=permisos_por_modulo,
                    clientes_disponibles=clientes_disponibles,
                    selected_cliente_id=selected_cliente_id,
                    selected_permiso_ids=selected_permiso_ids,
                    es_mi_usuario=es_mi_usuario,
                    puede_editar_rol_permisos=puede_editar_rol_permisos
                )

            if selected_cliente_id is not None and selected_cliente_id not in clientes_disponibles_ids:
                flash('Debes seleccionar un cliente activo válido.', 'danger')
                return render_template(
                    'usuarios/editar.html',
                    usuario=usuario,
                    roles=roles_select,
                    permisos_por_rol=permisos_por_rol,
                    permisos_por_modulo=permisos_por_modulo,
                    clientes_disponibles=clientes_disponibles,
                    selected_cliente_id=selected_cliente_id,
                    selected_permiso_ids=selected_permiso_ids,
                    es_mi_usuario=es_mi_usuario,
                    puede_editar_rol_permisos=puede_editar_rol_permisos
                )

            usuario.id_rol = id_rol
            usuario.id_cliente = selected_cliente_id
            usuario.activo = activo
            usuario.set_preferencia('modo_demo', '1' if modo_demo else '0')
            set_permisos_adicionales(usuario.id_usuario, ids_permiso_extra, current_user.id_usuario)
            selected_permiso_ids = set(int(x) for x in ids_permiso_extra if str(x).isdigit())

        datos_nuevos = {
            'username': usuario.username,
            'nombre_completo': usuario.nombre_completo,
            'id_rol': usuario.id_rol,
            'id_cliente': usuario.id_cliente,
            'activo': bool(usuario.activo),
            'permisos_adicionales': sorted(selected_permiso_ids),
            'modo_demo': bool(usuario.modo_demo),
        }
        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='editar_usuario',
                    modulo='configuracion',
                    descripcion=f'Editó usuario {usuario.username}',
                    referencia_tipo='usuario',
                    referencia_id=usuario.id_usuario,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=datos_nuevos,
                    commit=False
                )
        except Exception:
            pass

        db.session.commit()

        flash('Usuario actualizado.', 'success')
        return redirect(url_for('usuarios.listar'))

    return render_template(
        'usuarios/editar.html',
        usuario=usuario,
        roles=roles_select,
        permisos_por_rol=permisos_por_rol,
        permisos_por_modulo=permisos_por_modulo,
        clientes_disponibles=clientes_disponibles,
        selected_cliente_id=usuario.id_cliente,
        selected_permiso_ids=selected_permiso_ids,
        es_mi_usuario=es_mi_usuario,
        puede_editar_rol_permisos=puede_editar_rol_permisos
    )


@usuarios_bp.route('/<int:id>/toggle-activo', methods=['POST'])
@login_required
def toggle_activo(id):
    if not current_user.tiene_permiso('gestionar_usuarios'):
        flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    usuario = Usuario.query.get_or_404(id)
    if not puede_gestionar_usuario(current_user, usuario):
        flash('No tienes permisos para administrar este usuario.', 'danger')
        return redirect(url_for('usuarios.listar'))

    if usuario.id_usuario == current_user.id_usuario:
        flash('No puedes desactivar tu propio usuario.', 'warning')
        return redirect(request.form.get('next') or url_for('usuarios.listar'))

    nuevo_estado = not bool(usuario.activo)
    if (not nuevo_estado) and usuario.es_admin() and not tiene_otro_admin_activo(usuario.id_usuario):
        flash('No puedes desactivar el último administrador activo.', 'warning')
        return redirect(request.form.get('next') or url_for('usuarios.listar'))

    datos_anteriores = {'activo': bool(usuario.activo)}
    usuario.activo = nuevo_estado
    datos_nuevos = {'activo': bool(usuario.activo)}
    accion = 'activar_usuario' if nuevo_estado else 'desactivar_usuario'
    descripcion = f'{"Activó" if nuevo_estado else "Desactivó"} usuario {usuario.username}'
    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion=accion,
                modulo='configuracion',
                descripcion=descripcion,
                referencia_tipo='usuario',
                referencia_id=usuario.id_usuario,
                datos_anteriores=datos_anteriores,
                datos_nuevos=datos_nuevos,
                commit=False
            )
    except Exception:
        pass

    db.session.commit()
    flash(f'Usuario {"activado" if nuevo_estado else "desactivado"} correctamente.', 'success')
    return redirect(request.form.get('next') or url_for('usuarios.listar'))
