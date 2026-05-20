"""
Rutas de administración de usuarios
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Usuario, Rol, Permiso, Configuracion, Cliente
from app.services.usuarios_admin import (
    agrupar_permisos,
    map_permisos_por_rol,
    nivel_jerarquia,
    puede_gestionar_usuario,
    roles_asignables,
    set_permisos_adicionales,
    tiene_otro_admin_activo,
)
from app.services.ia_backoffice.security import puede_gestionar_asistente_ia
from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from app.services.usuarios_branding import guardar_logo_empresa
from app.utils.auditoria_utils import registrar_auditoria


usuarios_bp = Blueprint('usuarios', __name__)
CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS = 'pos_ocultar_selector_vendedor_cajero'
DESC_OCULTAR_SELECTOR_VENDEDOR_POS = 'Muestra selector de vendedor/cajero en POS (desactivado: usa usuario actual)'
CLAVE_CAJA_FLUJO_ENVIADO = 'caja_flujo_enviado_desde_vendedor'
DESC_CAJA_FLUJO_ENVIADO = 'Habilita flujo vendedor -> caja para cobro final'
CLAVE_CAJA_ALERTA_PENDIENTES = 'caja_alerta_pendientes_activa'
DESC_CAJA_ALERTA_PENDIENTES = 'Muestra alerta visual de pendientes de cobro para cajero'
CLAVE_CAJA_EXIGIR_CAJERO = 'caja_exigir_cajero_para_cobro'
DESC_CAJA_EXIGIR_CAJERO = 'Bloquea cobro directo cuando el flujo de caja está activo'
FORM_MODO_COBRO_EXCLUSIVO_CAJERO = 'modo_cobro_exclusivo_cajero'
CLAVE_NOMBRE_EMPRESA_UI = 'nombre_empresa_ui'
DESC_NOMBRE_EMPRESA_UI = 'Nombre visible de la empresa en el encabezado'
CLAVE_LOGO_EMPRESA_UI = 'logo_empresa_ui_path'
DESC_LOGO_EMPRESA_UI = 'Ruta del logo de la empresa para el encabezado'
CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO = 'reparacion_whatsapp_mensaje_link'
DESC_MENSAJE_WHATSAPP_SEGUIMIENTO = 'Plantilla de mensaje WhatsApp para compartir link de seguimiento de reparación'
MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT = 'Hola! Este es su link de {empresa} para ver el estado de reparación de su equipo:\n\n{link}'

def _ocultar_selector_vendedor_pos():
    # Compatibilidad: la clave histórica se reutiliza como flag "mostrar selector".
    # Si está desactivado (0), se oculta el selector y se usa el usuario actual.
    mostrar_selector = Configuracion.obtener_bool(CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS, default=False)
    return not mostrar_selector


def _modo_cobro_exclusivo_cajero_activo():
    return (
        Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False)
        and Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False)
    )


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


@usuarios_bp.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        def _leer_toggle(nombre, default=False):
            valores = request.form.getlist(nombre)
            raw = valores[-1] if valores else None
            return Configuracion.parse_bool(raw, default=default)

        mostrar_selector = _leer_toggle('mostrar_selector_vendedor_pos', default=False)
        valores_modo_cobro_exclusivo = request.form.getlist(FORM_MODO_COBRO_EXCLUSIVO_CAJERO)
        if valores_modo_cobro_exclusivo:
            modo_cobro_exclusivo_cajero = Configuracion.parse_bool(
                valores_modo_cobro_exclusivo[-1],
                default=False
            )
        else:
            modo_cobro_exclusivo_cajero = _modo_cobro_exclusivo_cajero_activo()
        caja_flujo_enviado = modo_cobro_exclusivo_cajero
        valores_alerta_pendientes = request.form.getlist('caja_alerta_pendientes_activa')
        if valores_alerta_pendientes:
            caja_alerta_pendientes = Configuracion.parse_bool(
                valores_alerta_pendientes[-1],
                default=False
            )
        else:
            caja_alerta_pendientes = Configuracion.obtener_bool(CLAVE_CAJA_ALERTA_PENDIENTES, default=False)
        caja_exigir_cajero = modo_cobro_exclusivo_cajero
        nombre_empresa_ui = (request.form.get('nombre_empresa_ui') or '').strip()
        mensaje_whatsapp_seguimiento = (request.form.get('mensaje_whatsapp_seguimiento') or '').strip()
        logo_empresa_archivo = request.files.get('logo_empresa_ui')

        Configuracion.establecer_bool(
            CLAVE_OCULTAR_SELECTOR_VENDEDOR_POS,
            mostrar_selector,
            DESC_OCULTAR_SELECTOR_VENDEDOR_POS
        )
        Configuracion.establecer_bool(
            CLAVE_CAJA_FLUJO_ENVIADO,
            caja_flujo_enviado,
            DESC_CAJA_FLUJO_ENVIADO
        )
        Configuracion.establecer_bool(
            CLAVE_CAJA_ALERTA_PENDIENTES,
            caja_alerta_pendientes,
            DESC_CAJA_ALERTA_PENDIENTES
        )
        Configuracion.establecer_bool(
            CLAVE_CAJA_EXIGIR_CAJERO,
            caja_exigir_cajero,
            DESC_CAJA_EXIGIR_CAJERO
        )
        Configuracion.establecer(
            CLAVE_NOMBRE_EMPRESA_UI,
            nombre_empresa_ui,
            DESC_NOMBRE_EMPRESA_UI
        )
        Configuracion.establecer(
            CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO,
            mensaje_whatsapp_seguimiento,
            DESC_MENSAJE_WHATSAPP_SEGUIMIENTO
        )

        ruta_logo_guardada, error_logo = guardar_logo_empresa(
            logo_empresa_archivo,
            ruta_anterior=(Configuracion.obtener(CLAVE_LOGO_EMPRESA_UI, '') or '').strip(),
        )
        if error_logo:
            flash(error_logo, 'warning')
        elif ruta_logo_guardada:
            Configuracion.establecer(
                CLAVE_LOGO_EMPRESA_UI,
                ruta_logo_guardada,
                DESC_LOGO_EMPRESA_UI
            )

        flash('Configuración actualizada correctamente.', 'success')
        return redirect(url_for('usuarios.configuracion'))

    return render_template(
        'usuarios/configuracion.html',
        active_tab='configuracion',
        mostrar_selector_vendedor_pos=(not _ocultar_selector_vendedor_pos()),
        modo_cobro_exclusivo_cajero=_modo_cobro_exclusivo_cajero_activo(),
        caja_flujo_enviado_activo=Configuracion.obtener_bool(CLAVE_CAJA_FLUJO_ENVIADO, default=False),
        caja_alerta_pendientes_activa=Configuracion.obtener_bool(CLAVE_CAJA_ALERTA_PENDIENTES, default=False),
        caja_exigir_cajero_para_cobro=Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR_CAJERO, default=False),
        nombre_empresa_ui=(Configuracion.obtener(CLAVE_NOMBRE_EMPRESA_UI, '') or '').strip(),
        mensaje_whatsapp_seguimiento=(
            (Configuracion.obtener(CLAVE_MENSAJE_WHATSAPP_SEGUIMIENTO, MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT) or '').strip()
            or MENSAJE_WHATSAPP_SEGUIMIENTO_DEFAULT
        ),
        logo_empresa_ui_path=(Configuracion.obtener(CLAVE_LOGO_EMPRESA_UI, '') or '').strip(),
        logo_tamano_recomendado='280 × 80 px',
        logo_tamano_maximo_mb=2,
        ia_backoffice_config=obtener_configuracion_asistente(),
        ia_backoffice_puede_gestionar=puede_gestionar_asistente_ia(current_user),
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
