"""
Rutas auxiliares para gestión de categorías de productos.
"""
from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Categoria, Producto
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.permisos import validar_autorizacion


def _categoria_auditoria_data(categoria: Categoria, productos_activos: int, subcategorias_activas: int) -> dict:
    return {
        'id_categoria': int(categoria.id_categoria),
        'nombre': (categoria.nombre or '').strip(),
        'descripcion': (categoria.descripcion or '').strip() or None,
        'activo': bool(categoria.activo),
        'productos_activos': int(productos_activos),
        'subcategorias_activas': int(subcategorias_activas),
    }


def _redirect_destino() -> str:
    destino = (request.form.get('next') or request.referrer or '').strip()
    if destino.startswith('/'):
        return destino
    return url_for('productos.listar')


def register_categoria_routes(productos_bp):
    @productos_bp.route('/categorias/<int:id_categoria>/eliminar', methods=['POST'])
    @login_required
    def eliminar_categoria(id_categoria: int):
        if not current_user.tiene_permiso('eliminar_producto'):
            if getattr(current_user, 'modo_demo', False):
                flash('Modo demo: esta acción está deshabilitada.', 'warning')
            else:
                flash('No tienes permisos para eliminar categorías.', 'danger')
            return redirect(_redirect_destino())

        ok, autorizacion = validar_autorizacion(
            request.form.get('id_autorizacion', type=int),
            'eliminar_producto'
        )
        if not ok:
            flash('Se requiere autorización de administrador para eliminar categorías.', 'danger')
            return redirect(_redirect_destino())

        categoria = Categoria.query.get_or_404(id_categoria)
        productos_activos = Producto.query.filter_by(
            id_categoria=categoria.id_categoria,
            activo=True,
        ).count()
        subcategorias_activas = Categoria.query.filter_by(
            categoria_padre=categoria.id_categoria,
            activo=True,
        ).count()

        if productos_activos > 0:
            flash(
                f'No se puede eliminar la categoría "{categoria.nombre}" porque tiene {productos_activos} producto(s) activo(s).',
                'warning'
            )
            return redirect(_redirect_destino())

        if subcategorias_activas > 0:
            flash(
                f'No se puede eliminar la categoría "{categoria.nombre}" porque tiene subcategorías activas.',
                'warning'
            )
            return redirect(_redirect_destino())

        if not categoria.activo:
            flash(f'La categoría "{categoria.nombre}" ya estaba desactivada.', 'info')
            return redirect(_redirect_destino())

        datos_anteriores = _categoria_auditoria_data(categoria, productos_activos, subcategorias_activas)
        categoria.activo = False
        db.session.add(categoria)

        registrar_auditoria(
            accion='eliminar_categoria',
            modulo='productos',
            descripcion=f'Desactivó categoría "{categoria.nombre}"',
            referencia_tipo='categoria',
            referencia_id=categoria.id_categoria,
            datos_anteriores=datos_anteriores,
            datos_nuevos=_categoria_auditoria_data(categoria, 0, 0),
            id_autorizacion=autorizacion.id_autorizacion if autorizacion else None,
            commit=False
        )
        db.session.commit()
        flash(f'Categoría "{categoria.nombre}" eliminada.', 'success')
        return redirect(_redirect_destino())
