"""
Rutas de autenticacion.
"""
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf

from app import db
from app.models import SesionCaja, Usuario
from app.services.demo_session_guard import (
    clear_expired_demo_block,
    demo_block_message,
    is_demo_blocked,
    is_demo_user,
    start_demo_session_if_needed,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pagina de login."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        if not username or not password:
            flash('Por favor complete todos los campos.', 'warning')
            return render_template('auth/login.html')

        usuario = Usuario.query.filter_by(username=username).first()

        if usuario is None or not usuario.check_password(password):
            ip = request.headers.get('X-Forwarded-For', request.remote_addr) or '-'
            current_app.logger.warning(f'AUTH LOGIN FAIL ip={ip} user={username or "-"}')
            flash('Usuario o contrasena incorrectos.', 'danger')
            return render_template('auth/login.html')

        if not usuario.activo:
            ip = request.headers.get('X-Forwarded-For', request.remote_addr) or '-'
            current_app.logger.warning(f'AUTH LOGIN INACTIVE ip={ip} user={username or "-"}')
            flash('Su cuenta esta desactivada. Contacte al administrador.', 'danger')
            return render_template('auth/login.html')

        clear_expired_demo_block(usuario)
        blocked, blocked_until = is_demo_blocked(usuario)
        if blocked:
            ip = request.headers.get('X-Forwarded-For', request.remote_addr) or '-'
            current_app.logger.warning(f'AUTH LOGIN DEMO BLOCKED ip={ip} user={username or "-"}')
            flash(demo_block_message(blocked_until), 'warning')
            return render_template('auth/login.html')

        login_user(usuario, remember=remember)
        start_demo_session_if_needed(usuario)
        usuario.ultimo_acceso = datetime.utcnow()
        db.session.commit()

        next_page = request.args.get('next')
        return redirect(next_page or url_for('main.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """Cerrar sesion."""
    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta',
    ).first()

    if request.method == 'GET':
        return render_template('auth/logout_confirm.html', sesion=sesion)

    force = request.form.get('force', '').strip() in ('1', 'true', 'yes')
    if sesion and not force:
        return render_template('auth/logout_confirm.html', sesion=sesion)

    logout_user()
    flash('Sesion cerrada correctamente.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    """Cambiar contrasena del usuario actual."""
    if is_demo_user(current_user):
        flash('Modo demo: no se permite cambiar la contrasena.', 'warning')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        password_actual = request.form.get('password_actual', '')
        password_nueva = request.form.get('password_nueva', '')
        password_confirmar = request.form.get('password_confirmar', '')

        if not current_user.check_password(password_actual):
            flash('La contrasena actual es incorrecta.', 'danger')
            return render_template('auth/cambiar_password.html')

        if len(password_nueva) < 4:
            flash('La contrasena nueva debe tener al menos 4 caracteres.', 'warning')
            return render_template('auth/cambiar_password.html')

        if password_nueva != password_confirmar:
            flash('Las contrasenas nuevas no coinciden.', 'warning')
            return render_template('auth/cambiar_password.html')

        current_user.set_password(password_nueva)
        db.session.commit()
        flash('Contrasena actualizada correctamente.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/cambiar_password.html')


@auth_bp.route('/csrf', methods=['GET'])
@login_required
def csrf_token():
    return jsonify({'csrf_token': generate_csrf()})
