from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app import db
from app.models import Categoria, Producto, TiendaConfig, WebBotSesion
from app.services.ia_backoffice.security import es_usuario_root
from app.services.tienda_context import resolver_cliente_tienda
from app.services.tienda_presupuesto import tienda_es_gastronomia
from app.services.tienda_promociones import list_admin_promotions, serialize_admin_promotion
from app.services.web_bot.admin_service import (
    build_web_bot_sessions_query,
    serialize_web_bot_session_detail,
    serialize_web_bot_session_row,
    unlock_web_bot_session,
)
from gastronomia.services.modo_operacion import gastronomia_activa_para_cliente

tienda_admin_bp = Blueprint('tienda_admin', __name__)


def _can_manage_store() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')


def _current_client_scope() -> int | None:
    return resolver_cliente_tienda()


@tienda_admin_bp.route('/tienda-admin')
@login_required
def panel():
    if not _can_manage_store():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para administrar la tienda online.', 'danger')
        return redirect(url_for('main.dashboard'))

    q = (request.args.get('q') or '').strip()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(80, max(10, request.args.get('per_page', 20, type=int)))

    client_scope = _current_client_scope()
    config_query = TiendaConfig.query
    if client_scope:
        config_query = config_query.filter(TiendaConfig.id_cliente == client_scope)
    config = config_query.order_by(TiendaConfig.id_config.asc()).first()
    es_gastronomia_tienda = bool(
        (config and tienda_es_gastronomia(config))
        or (client_scope and gastronomia_activa_para_cliente(client_scope))
    )

    if es_gastronomia_tienda:
        from gastronomia.models import GastronomiaProducto

        query = GastronomiaProducto.query.filter(
            GastronomiaProducto.cliente_id == int(config.id_cliente if config else client_scope),
            GastronomiaProducto.activo.is_(True),
        )
        if q:
            like = f'%{q}%'
            query = query.filter(
                GastronomiaProducto.nombre.ilike(like) |
                GastronomiaProducto.descripcion.ilike(like)
            )
        productos = query.order_by(
            GastronomiaProducto.visible.desc(),
            GastronomiaProducto.disponible.desc(),
            GastronomiaProducto.orden.asc(),
            GastronomiaProducto.nombre.asc(),
        ).paginate(page=page, per_page=per_page, error_out=False)
    else:
        query = Producto.query.filter(Producto.activo.is_(True))
        if client_scope:
            query = query.filter((Producto.id_cliente == client_scope) | (Producto.id_cliente.is_(None)))
        if q:
            like = f'%{q}%'
            query = query.filter(
                Producto.nombre.ilike(like) |
                Producto.codigo.ilike(like) |
                Producto.marca.ilike(like) |
                Producto.modelo.ilike(like)
            )

        productos = query.order_by(
            Producto.publicado_tienda.desc(),
            Producto.orden_tienda.asc(),
            Producto.nombre.asc()
        ).paginate(page=page, per_page=per_page, error_out=False)

    es_solicitud_parcial = (
        request.args.get('fragment') == 'productos' and
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )

    if es_solicitud_parcial:
        return render_template(
            'tienda_admin/_panel_productos_gastronomia.html' if es_gastronomia_tienda else 'tienda_admin/_panel_productos.html',
            productos=productos,
            q=q,
            tienda_config=config,
        )

    categorias = Categoria.query.order_by(Categoria.nombre.asc()).all()
    promociones = []
    if config and config.id_cliente:
        promociones = [
            serialize_admin_promotion(item)
            for item in list_admin_promotions(int(config.id_cliente))
        ]
    return render_template(
        'tienda_admin/panel.html',
        productos=productos,
        tienda_config=config,
        es_gastronomia_tienda=es_gastronomia_tienda,
        productos_template='tienda_admin/_panel_productos_gastronomia.html' if es_gastronomia_tienda else 'tienda_admin/_panel_productos.html',
        categorias=categorias,
        promociones=promociones,
        q=q,
        show_publicidad_ads_analytics=es_usuario_root(current_user),
    )


@tienda_admin_bp.route('/tienda-admin/bot/conversaciones')
@login_required
def bot_conversaciones():
    if not _can_manage_store():
        abort(403)
    client_scope = None if current_user.es_admin() else _current_client_scope()
    if not current_user.es_admin() and not client_scope:
        abort(403)

    q = (request.args.get('q') or '').strip()
    estado = (request.args.get('estado') or '').strip().lower()
    slug = (request.args.get('slug') or '').strip().lower()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(50, max(10, request.args.get('per_page', 20, type=int)))

    pagination = build_web_bot_sessions_query(
        client_id=client_scope,
        q=q,
        estado=estado,
        slug=slug,
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'tienda_admin/bot_conversaciones.html',
        sesiones=[serialize_web_bot_session_row(item) for item in pagination.items],
        pagination=pagination,
        q=q,
        estado=estado,
        slug=slug,
    )


@tienda_admin_bp.route('/tienda-admin/bot/conversaciones/<int:id_sesion>')
@login_required
def bot_conversacion_detalle(id_sesion: int):
    if not _can_manage_store():
        abort(403)

    session = WebBotSesion.query.get_or_404(id_sesion)
    client_scope = None if current_user.es_admin() else _current_client_scope()
    if not current_user.es_admin() and not client_scope:
        abort(403)
    if client_scope and session.id_cliente != client_scope:
        abort(404)

    detail = serialize_web_bot_session_detail(session)
    return render_template(
        'tienda_admin/bot_conversacion_detalle.html',
        detalle=detail,
    )


@tienda_admin_bp.route('/tienda-admin/bot/conversaciones/<int:id_sesion>/unlock', methods=['POST'])
@login_required
def bot_conversacion_unlock(id_sesion: int):
    if not _can_manage_store():
        abort(403)

    session = WebBotSesion.query.get_or_404(id_sesion)
    client_scope = None if current_user.es_admin() else _current_client_scope()
    if not current_user.es_admin() and not client_scope:
        abort(403)
    if client_scope and session.id_cliente != client_scope:
        abort(404)

    actor_label = (
        getattr(current_user, 'username', None)
        or getattr(current_user, 'email', None)
        or getattr(current_user, 'nombre', None)
        or f'usuario#{getattr(current_user, "id_usuario", "")}'
    )
    unlock_web_bot_session(session, actor_label=str(actor_label))
    db.session.commit()
    flash('La sesión del bot fue desbloqueada manualmente.', 'success')
    return redirect(url_for('tienda_admin.bot_conversacion_detalle', id_sesion=id_sesion))
