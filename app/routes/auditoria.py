"""
Rutas de consulta de auditoría
"""
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app import db
from app.models import Auditoria, Usuario, Permiso
from app.utils.permisos import requiere_permiso


auditoria_bp = Blueprint('auditoria', __name__)
auditoria_api_bp = Blueprint('auditoria_api', __name__, url_prefix='/api/auditoria')


def _mask_sensitive(value):
    if isinstance(value, dict):
        masked = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(t in key for t in ('password', 'passwd', 'token', 'secret', 'apikey', 'api_key')):
                masked[k] = '***'
            else:
                masked[k] = _mask_sensitive(v)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(v) for v in value]
    return value


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _build_query(args):
    from sqlalchemy.orm import contains_eager
    
    usuario = (args.get('usuario') or '').strip()
    id_usuario = _parse_int(args.get('id_usuario'))
    
    # Si filtramos por nombre de usuario, usamos join + contains_eager
    # para evitar conflictos con joinedload
    if usuario and not id_usuario:
        query = Auditoria.query.join(Usuario, Auditoria.id_usuario == Usuario.id_usuario)
        query = query.options(contains_eager(Auditoria.usuario))
        like = f'%{usuario}%'
        query = query.filter(db.or_(
            Usuario.username.ilike(like),
            Usuario.nombre_completo.ilike(like),
        ))
    else:
        query = Auditoria.query.options(joinedload(Auditoria.usuario))
        if id_usuario:
            query = query.filter(Auditoria.id_usuario == id_usuario)

    desde = _parse_date(args.get('desde'))
    hasta = _parse_date(args.get('hasta'))

    if desde:
        query = query.filter(db.func.date(Auditoria.fecha_accion) >= desde.isoformat())
    if hasta:
        query = query.filter(db.func.date(Auditoria.fecha_accion) <= hasta.isoformat())

    modulo = (args.get('modulo') or '').strip()
    if modulo:
        query = query.filter(Auditoria.modulo == modulo)

    accion = (args.get('accion') or '').strip()
    if accion:
        query = query.filter(Auditoria.accion == accion)

    referencia_tipo = (args.get('referencia_tipo') or '').strip()
    if referencia_tipo:
        query = query.filter(Auditoria.referencia_tipo == referencia_tipo)

    referencia_id = _parse_int(args.get('referencia_id'))
    if referencia_id is not None:
        query = query.filter(Auditoria.referencia_id == referencia_id)

    q = (args.get('q') or '').strip()
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(
            Auditoria.descripcion.ilike(like),
            Auditoria.modulo.ilike(like),
            Auditoria.accion.ilike(like),
            Auditoria.referencia_tipo.ilike(like),
        ))

    return query


def _parse_json(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _collect_ids(value, buckets):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ('permisos', 'permisos_adicionales') and isinstance(v, list):
                for item in v:
                    if isinstance(item, int):
                        buckets['permiso'].add(item)
            elif k in ('id_permiso',) and isinstance(v, int):
                buckets['permiso'].add(v)
            elif k in ('id_rol',) and isinstance(v, int):
                buckets['rol'].add(v)
            elif k in (
                'id_usuario',
                'id_usuario_cierre',
                'id_usuario_emision',
                'id_usuario_modificacion',
                'id_usuario_solicitante',
                'id_usuario_autorizador',
                'concedido_por',
            ) and isinstance(v, int):
                buckets['usuario'].add(v)
            elif k in ('id_producto', 'id_producto_kit', 'id_producto_componente', 'id_producto_principal', 'id_producto_repuesto') and isinstance(v, int):
                buckets['producto'].add(v)
            elif k in ('id_metodo_pago',) and isinstance(v, int):
                buckets['metodo_pago'].add(v)
            elif k in ('id_cliente',) and isinstance(v, int):
                buckets['cliente'].add(v)
            elif k in ('id_proveedor', 'id_proveedor_principal') and isinstance(v, int):
                buckets['proveedor'].add(v)
            elif k in ('id_categoria',) and isinstance(v, int):
                buckets['categoria'].add(v)
            elif k in ('id_caja',) and isinstance(v, int):
                buckets['caja'].add(v)
            _collect_ids(v, buckets)
        return
    if isinstance(value, list):
        for item in value:
            _collect_ids(item, buckets)


def _build_labels(buckets):
    labels = {
        'permiso': {},
        'rol': {},
        'usuario': {},
        'producto': {},
        'metodo_pago': {},
        'cliente': {},
        'proveedor': {},
        'categoria': {},
        'caja': {},
    }

    if buckets.get('permiso'):
        from app.models import Permiso

        rows = Permiso.query.filter(Permiso.id_permiso.in_(sorted(buckets['permiso']))).all()
        for p in rows:
            labels['permiso'][p.id_permiso] = f'{p.id_permiso} ({p.codigo} - {p.nombre})'

    if buckets.get('rol'):
        from app.models import Rol

        rows = Rol.query.filter(Rol.id_rol.in_(sorted(buckets['rol']))).all()
        for r in rows:
            labels['rol'][r.id_rol] = f'{r.id_rol} ({r.nombre})'

    if buckets.get('usuario'):
        rows = Usuario.query.filter(Usuario.id_usuario.in_(sorted(buckets['usuario']))).all()
        for u in rows:
            nombre = (u.nombre_completo or '').strip()
            username = (u.username or '').strip()
            detalle = ' - '.join([x for x in (username, nombre) if x])
            labels['usuario'][u.id_usuario] = f'{u.id_usuario} ({detalle})' if detalle else str(u.id_usuario)

    if buckets.get('producto'):
        from app.models import Producto

        rows = Producto.query.filter(Producto.id_producto.in_(sorted(buckets['producto']))).all()
        for p in rows:
            codigo = (p.codigo or '').strip()
            nombre = (p.nombre or '').strip()
            detalle = ' - '.join([x for x in (codigo, nombre) if x])
            labels['producto'][p.id_producto] = f'{p.id_producto} ({detalle})' if detalle else str(p.id_producto)

    if buckets.get('metodo_pago'):
        from app.models import MetodoPago

        rows = MetodoPago.query.filter(MetodoPago.id_metodo_pago.in_(sorted(buckets['metodo_pago']))).all()
        for m in rows:
            nombre = (m.nombre or '').strip()
            labels['metodo_pago'][m.id_metodo_pago] = f'{m.id_metodo_pago} ({nombre})' if nombre else str(m.id_metodo_pago)

    if buckets.get('cliente'):
        from app.models import Cliente

        rows = Cliente.query.filter(Cliente.id_cliente.in_(sorted(buckets['cliente']))).all()
        for c in rows:
            nombre = (c.nombre or '').strip()
            ruc = (c.ruc_ci or '').strip()
            detalle = ' - '.join([x for x in (nombre, ruc) if x])
            labels['cliente'][c.id_cliente] = f'{c.id_cliente} ({detalle})' if detalle else str(c.id_cliente)

    if buckets.get('proveedor'):
        from app.models import Proveedor

        rows = Proveedor.query.filter(Proveedor.id_proveedor.in_(sorted(buckets['proveedor']))).all()
        for p in rows:
            nombre = (p.nombre or '').strip()
            ruc = (p.ruc or '').strip()
            detalle = ' - '.join([x for x in (nombre, ruc) if x])
            labels['proveedor'][p.id_proveedor] = f'{p.id_proveedor} ({detalle})' if detalle else str(p.id_proveedor)

    if buckets.get('categoria'):
        from app.models import Categoria

        rows = Categoria.query.filter(Categoria.id_categoria.in_(sorted(buckets['categoria']))).all()
        for c in rows:
            nombre = (c.nombre or '').strip()
            labels['categoria'][c.id_categoria] = f'{c.id_categoria} ({nombre})' if nombre else str(c.id_categoria)

    if buckets.get('caja'):
        from app.models import Caja

        rows = Caja.query.filter(Caja.id_caja.in_(sorted(buckets['caja']))).all()
        for c in rows:
            nombre = (c.nombre or '').strip()
            labels['caja'][c.id_caja] = f'{c.id_caja} ({nombre})' if nombre else str(c.id_caja)

    return labels


def _enrich_audit_data(value):
    if not value:
        return value

    buckets = {
        'permiso': set(),
        'rol': set(),
        'usuario': set(),
        'producto': set(),
        'metodo_pago': set(),
        'cliente': set(),
        'proveedor': set(),
        'categoria': set(),
        'caja': set(),
    }
    _collect_ids(value, buckets)
    labels = _build_labels(buckets)

    def transform(val):
        if isinstance(val, dict):
            out = {}
            for k, v in val.items():
                if k in ('permisos', 'permisos_adicionales') and isinstance(v, list):
                    out[k] = [labels['permiso'].get(item, item) if isinstance(item, int) else item for item in v]
                    continue
                if k == 'id_permiso' and isinstance(v, int):
                    out[k] = labels['permiso'].get(v, v)
                    continue
                if k == 'id_rol' and isinstance(v, int):
                    out[k] = labels['rol'].get(v, v)
                    continue
                if k in (
                    'id_usuario',
                    'id_usuario_cierre',
                    'id_usuario_emision',
                    'id_usuario_modificacion',
                    'id_usuario_solicitante',
                    'id_usuario_autorizador',
                    'concedido_por',
                ) and isinstance(v, int):
                    out[k] = labels['usuario'].get(v, v)
                    continue
                if k in ('id_producto', 'id_producto_kit', 'id_producto_componente', 'id_producto_principal', 'id_producto_repuesto') and isinstance(v, int):
                    out[k] = labels['producto'].get(v, v)
                    continue
                if k == 'id_metodo_pago' and isinstance(v, int):
                    out[k] = labels['metodo_pago'].get(v, v)
                    continue
                if k == 'id_cliente' and isinstance(v, int):
                    out[k] = labels['cliente'].get(v, v)
                    continue
                if k in ('id_proveedor', 'id_proveedor_principal') and isinstance(v, int):
                    out[k] = labels['proveedor'].get(v, v)
                    continue
                if k == 'id_categoria' and isinstance(v, int):
                    out[k] = labels['categoria'].get(v, v)
                    continue
                if k == 'id_caja' and isinstance(v, int):
                    out[k] = labels['caja'].get(v, v)
                    continue
                out[k] = transform(v)
            return out
        if isinstance(val, list):
            return [transform(x) for x in val]
        return val

    return transform(value)


def _format_referencia(referencia_tipo, referencia_id):
    if not referencia_tipo:
        return None
    if referencia_id is None:
        return str(referencia_tipo)

    tipo = str(referencia_tipo).strip().lower()
    try:
        if tipo == 'rol':
            from app.models import Rol

            r = Rol.query.get(int(referencia_id))
            if r:
                return f'rol #{referencia_id} ({r.nombre})'
        if tipo == 'usuario':
            u = Usuario.query.get(int(referencia_id))
            if u:
                detalle = ' - '.join([x for x in ((u.username or '').strip(), (u.nombre_completo or '').strip()) if x])
                return f'usuario #{referencia_id} ({detalle})' if detalle else f'usuario #{referencia_id}'
        if tipo == 'producto':
            from app.models import Producto

            p = Producto.query.get(int(referencia_id))
            if p:
                detalle = ' - '.join([x for x in ((p.codigo or '').strip(), (p.nombre or '').strip()) if x])
                return f'producto #{referencia_id} ({detalle})' if detalle else f'producto #{referencia_id}'
        if tipo == 'caja':
            from app.models import Caja

            c = Caja.query.get(int(referencia_id))
            if c:
                return f'caja #{referencia_id} ({c.nombre})'
        if tipo == 'sesion_caja':
            return f'sesión_caja #{referencia_id}'
        if tipo == 'venta':
            return f'venta #{referencia_id}'
        if tipo == 'compra':
            return f'compra #{referencia_id}'
    except Exception:
        pass
    return f'{referencia_tipo} #{referencia_id}'


@auditoria_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('ver_auditoria'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver auditoría.', 'danger')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = max(5, min(per_page, 100))

    if not request.args.get('desde') and not request.args.get('hasta'):
        desde_default = (date.today() - timedelta(days=7)).isoformat()
    else:
        desde_default = request.args.get('desde')

    query_args = dict(request.args)
    query_args.setdefault('desde', desde_default)

    query = _build_query(query_args)
    auditorias = query.order_by(Auditoria.fecha_accion.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    usuarios = Usuario.query.order_by(Usuario.username.asc()).all()

    modulos = set()
    try:
        rows = db.session.query(Permiso.modulo).filter(Permiso.activo == True).distinct().all()
        for (m,) in rows:
            if m:
                modulos.add(m)
    except Exception:
        pass

    try:
        rows = db.session.query(Auditoria.modulo).filter(Auditoria.modulo.isnot(None)).distinct().all()
        for (m,) in rows:
            if m:
                modulos.add(m)
    except Exception:
        pass

    return render_template(
        'auditoria/listar.html',
        auditorias=auditorias,
        usuarios=usuarios,
        modulos_auditables=sorted(modulos),
        filtros={
            'desde': query_args.get('desde') or '',
            'hasta': query_args.get('hasta') or '',
            'id_usuario': query_args.get('id_usuario') or '',
            'usuario': query_args.get('usuario') or '',
            'modulo': query_args.get('modulo') or '',
            'accion': query_args.get('accion') or '',
            'referencia_tipo': query_args.get('referencia_tipo') or '',
            'referencia_id': query_args.get('referencia_id') or '',
            'q': query_args.get('q') or '',
            'per_page': per_page,
        }
    )


@auditoria_bp.route('/<int:id_auditoria>')
@login_required
def detalle(id_auditoria):
    if not current_user.tiene_permiso('ver_auditoria'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver auditoría.', 'danger')
        return redirect(url_for('main.dashboard'))

    registro = Auditoria.query.get_or_404(id_auditoria)
    datos_anteriores = _enrich_audit_data(_mask_sensitive(_parse_json(registro.datos_anteriores)))
    datos_nuevos = _enrich_audit_data(_mask_sensitive(_parse_json(registro.datos_nuevos)))
    referencia_display = _format_referencia(registro.referencia_tipo, registro.referencia_id)

    return render_template(
        'auditoria/detalle.html',
        registro=registro,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        referencia_display=referencia_display,
    )


@auditoria_api_bp.route('', methods=['GET'])
@login_required
@requiere_permiso('ver_auditoria')
def api_listar():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = max(5, min(per_page, 100))

    query = _build_query(request.args)
    pag = query.order_by(Auditoria.fecha_accion.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    items = []
    for a in pag.items:
        items.append({
            'id_auditoria': a.id_auditoria,
            'fecha_accion': a.fecha_accion.isoformat() if a.fecha_accion else None,
            'usuario': {
                'id_usuario': a.usuario.id_usuario if a.usuario else None,
                'username': a.usuario.username if a.usuario else None,
                'nombre_completo': a.usuario.nombre_completo if a.usuario else None,
            },
            'accion': a.accion,
            'modulo': a.modulo,
            'descripcion': a.descripcion,
            'referencia_tipo': a.referencia_tipo,
            'referencia_id': a.referencia_id,
            'id_autorizacion': a.id_autorizacion,
        })

    return jsonify({
        'page': pag.page,
        'per_page': pag.per_page,
        'pages': pag.pages,
        'total': pag.total,
        'items': items,
    })


@auditoria_api_bp.route('/<int:id_auditoria>', methods=['GET'])
@login_required
@requiere_permiso('ver_auditoria')
def api_detalle(id_auditoria):
    a = Auditoria.query.get_or_404(id_auditoria)
    datos_anteriores_raw = _mask_sensitive(_parse_json(a.datos_anteriores))
    datos_nuevos_raw = _mask_sensitive(_parse_json(a.datos_nuevos))
    return jsonify({
        'id_auditoria': a.id_auditoria,
        'fecha_accion': a.fecha_accion.isoformat() if a.fecha_accion else None,
        'usuario': {
            'id_usuario': a.usuario.id_usuario if a.usuario else None,
            'username': a.usuario.username if a.usuario else None,
            'nombre_completo': a.usuario.nombre_completo if a.usuario else None,
        },
        'accion': a.accion,
        'modulo': a.modulo,
        'descripcion': a.descripcion,
        'referencia_tipo': a.referencia_tipo,
        'referencia_id': a.referencia_id,
        'id_autorizacion': a.id_autorizacion,
        'ip_address': a.ip_address,
        'user_agent': a.user_agent,
        'datos_anteriores': _enrich_audit_data(datos_anteriores_raw),
        'datos_nuevos': _enrich_audit_data(datos_nuevos_raw),
        'datos_anteriores_raw': datos_anteriores_raw,
        'datos_nuevos_raw': datos_nuevos_raw,
    })
