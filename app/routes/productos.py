"""
Rutas de gestión de productos
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import DataError, IntegrityError
from app import db
from app.models import Producto, Categoria, ProductoPrecioOpcion, MovimientoStock, AjusteInventario, DetalleAjusteInventario, DetalleCompra, Compra, Proveedor
from app.utils.permisos import validar_autorizacion
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.productos_errors import mensaje_codigo_duplicado, mensaje_error_producto, validar_longitudes_producto

productos_bp = Blueprint('productos', __name__)

def _campos_texto_producto_desde_form(form):
    return {
        'codigo': form.get('codigo', '').strip(),
        'codigo_barras': form.get('codigo_barras', '').strip(),
        'nombre': form.get('nombre', '').strip(),
        'marca': form.get('marca', ''),
        'modelo': form.get('modelo', ''),
        'color': form.get('color', ''),
        'capacidad': form.get('capacidad', ''),
    }

def _producto_auditoria_data(producto):
    precios_opciones = []
    try:
        precios_opciones = [
            {
                'id': int(o.id_opcion_precio),
                'etiqueta': (o.etiqueta or '').strip() or None,
                'precio': float(o.precio or 0),
                'orden': int(o.orden or 0),
                'activo': bool(o.activo),
            }
            for o in (
                producto.precios_opciones.filter_by(activo=True)
                .order_by(ProductoPrecioOpcion.orden.asc(), ProductoPrecioOpcion.id_opcion_precio.asc())
                .all()
            )
        ]
    except Exception:
        precios_opciones = []
    return {
        'id_producto': producto.id_producto,
        'codigo': (producto.codigo or '').strip(),
        'codigo_barras': (producto.codigo_barras or '').strip(),
        'nombre': (producto.nombre or '').strip(),
        'id_categoria': producto.id_categoria,
        'precio_compra': float(producto.precio_compra or 0),
        'precio_venta': float(producto.precio_venta or 0),
        'precio_mayorista': float(producto.precio_mayorista or 0) if producto.precio_mayorista is not None else None,
        'porcentaje_iva': int(producto.porcentaje_iva or 0),
        'stock_actual': int(producto.stock_actual or 0),
        'stock_minimo': int(producto.stock_minimo or 0),
        'stock_maximo': int(producto.stock_maximo) if producto.stock_maximo is not None else None,
        'es_kit': bool(producto.es_kit),
        'kit_stock_propio': bool(producto.kit_stock_propio),
        'es_servicio': bool(producto.es_servicio),
        'activo': bool(producto.activo),
        'precios_opciones': precios_opciones,
    }

def _obtener_o_crear_categoria(id_categoria, nombre, descripcion):
    if id_categoria:
        return id_categoria

    nombre = (nombre or '').strip()
    if not nombre:
        return None

    descripcion = (descripcion or '').strip() or None

    categoria = Categoria.query.filter(db.func.lower(Categoria.nombre) == nombre.lower()).first()
    if categoria:
        if not categoria.activo:
            categoria.activo = True
        if descripcion and not (categoria.descripcion or '').strip():
            categoria.descripcion = descripcion
        db.session.add(categoria)
        db.session.flush()
        return categoria.id_categoria

    categoria = Categoria(nombre=nombre, descripcion=descripcion, activo=True)
    db.session.add(categoria)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        categoria = Categoria.query.filter(db.func.lower(Categoria.nombre) == nombre.lower()).first()
        if categoria:
            if not categoria.activo:
                categoria.activo = True
            if descripcion and not (categoria.descripcion or '').strip():
                categoria.descripcion = descripcion
            db.session.add(categoria)
            db.session.flush()
            return categoria.id_categoria
        raise
    return categoria.id_categoria

def _parsear_precios_opciones(raw: str):
    raw = (raw or '').strip()
    if not raw:
        return []

    partes = re.split(r'[\n,;]+', raw)
    precios = []
    vistos = set()

    for parte in partes:
        s = (parte or '').strip()
        if not s:
            continue
        s = s.replace('₲', '').strip()
        s = re.sub(r'[^\d.,-]', '', s)
        if not s:
            continue
        s = s.replace('.', '')
        if s.count(',') == 1 and s.count('.') == 0:
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
        try:
            valor = Decimal(s)
        except Exception:
            continue
        if valor <= 0:
            continue
        key = str(valor.normalize())
        if key in vistos:
            continue
        vistos.add(key)
        precios.append(valor)

    return precios


def _decimal_to_str(value) -> str:
    try:
        d = Decimal(str(value))
    except Exception:
        return str(value)
    s = format(d, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def _es_reenvio_creacion_reciente(producto: Producto, user_id: int, nombre: str, codigo_barras: str | None) -> bool:
    try:
        if not producto:
            return False
        if int(producto.id_usuario_modificacion or 0) != int(user_id or 0):
            return False
        if not producto.fecha_creacion:
            return False
        if producto.fecha_creacion < (datetime.utcnow() - timedelta(minutes=2)):
            return False
        nombre_norm = (nombre or '').strip().lower()
        prod_nombre_norm = (producto.nombre or '').strip().lower()
        if nombre_norm and prod_nombre_norm != nombre_norm:
            return False
        if codigo_barras:
            cb_norm = (codigo_barras or '').strip().lower()
            prod_cb_norm = (producto.codigo_barras or '').strip().lower()
            if prod_cb_norm != cb_norm:
                return False
        return True
    except Exception:
        return False


def _actualizar_precios_opciones(producto: Producto, form):
    usar = bool(form.get('usa_precios_opciones'))
    raw = form.get('precios_opciones', '')
    precios = _parsear_precios_opciones(raw) if usar else []

    existentes = producto.precios_opciones.all()
    for opt in existentes:
        db.session.delete(opt)

    if not precios:
        return

    for idx, precio in enumerate(precios):
        opt = ProductoPrecioOpcion(
            id_producto=producto.id_producto,
            etiqueta=_decimal_to_str(precio),
            precio=precio,
            orden=idx,
            activo=True
        )
        db.session.add(opt)


@productos_bp.route('/')
@login_required
def listar():
    """Lista de productos"""
    if not current_user.tiene_permiso('ver_inventario'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver productos.', 'danger')
        return redirect(url_for('main.dashboard'))

    page = request.args.get('page', 1, type=int)
    buscar = request.args.get('buscar', '')
    categoria_id = request.args.get('categoria', 0, type=int)
    tipo = (request.args.get('tipo') or '').strip().lower()
    if tipo not in ('producto', 'servicio'):
        tipo = ''
    sort_key = (request.args.get('sort') or 'stock').strip().lower()
    sort_dir = (request.args.get('dir') or 'asc').strip().lower()
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    
    query = Producto.query.filter_by(activo=True)
    
    joined_categoria = False
    if buscar:
        query = query.join(Categoria, Producto.id_categoria == Categoria.id_categoria)
        joined_categoria = True
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(f'%{buscar}%'),
                Producto.codigo.ilike(f'%{buscar}%'),
                Producto.codigo_barras.ilike(f'%{buscar}%'),
                Producto.codigo_proveedor.ilike(f'%{buscar}%'),
                Categoria.nombre.ilike(f'%{buscar}%')
            )
        )
    
    if categoria_id:
        query = query.filter_by(id_categoria=categoria_id)

    if tipo == 'servicio':
        query = query.filter(Producto.es_servicio.is_(True))
    elif tipo == 'producto':
        query = query.filter(Producto.es_servicio.isnot(True))
    
    sort_columns = {
        'codigo': Producto.codigo,
        'producto': Producto.nombre,
        'nombre': Producto.nombre,
        'categoria': Categoria.nombre,
        'precio': Producto.precio_venta,
        'stock': Producto.stock_actual,
    }
    sort_column = sort_columns.get(sort_key, Producto.stock_actual)

    if sort_key == 'categoria' and not joined_categoria:
        query = query.join(Categoria, Producto.id_categoria == Categoria.id_categoria)

    primary_order = db.desc(sort_column) if sort_dir == 'desc' else db.asc(sort_column)
    order_by = [primary_order]
    if sort_key not in ('producto', 'nombre'):
        order_by.append(db.asc(Producto.nombre))
    order_by.append(db.asc(Producto.id_producto))

    productos = query.order_by(*order_by).paginate(
        page=page, per_page=20, error_out=False
    )
    
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    
    return render_template('productos/listar.html',
        productos=productos,
        categorias=categorias,
        buscar=buscar,
        categoria_id=categoria_id,
        tipo=tipo,
        sort=sort_key,
        dir=sort_dir
    )


@productos_bp.route('/crear_rapido', methods=['POST'])
@login_required
def crear_rapido():
    """Crear producto rápido desde compras"""
    try:
        if not current_user.tiene_permiso('crear_producto'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos para crear productos', 'modo_demo': False}), 403

        data = request.get_json() or {}
        codigo = (data.get('codigo') or '').strip()
        codigo_barras = (data.get('codigo_barras') or '').strip() or None
        nombre = (data.get('nombre') or '').strip()
        id_categoria_seleccionada = data.get('id_categoria')
        nueva_categoria_nombre = (data.get('nueva_categoria') or '').strip()
        precio_compra = data.get('precio_compra', 0)
        precio_venta = data.get('precio_venta', 0)
        precio_mayorista = data.get('precio_mayorista', None)
        porcentaje_iva = data.get('porcentaje_iva', 10)
        stock_minimo = data.get('stock_minimo', 5)
        es_servicio = bool(data.get('es_servicio'))
        usar_precios_opciones = bool(data.get('usa_precios_opciones'))
        raw_precios_opciones = (data.get('precios_opciones') or '').strip()
        precios_opciones = _parsear_precios_opciones(raw_precios_opciones) if usar_precios_opciones else []

        error_longitudes = validar_longitudes_producto({
            'codigo': codigo,
            'codigo_barras': codigo_barras,
            'nombre': nombre,
        })
        if error_longitudes:
            return jsonify({'error': error_longitudes}), 400

        # Validaciones
        if not codigo:
            return jsonify({'error': 'El código es obligatorio'}), 400
        
        if not nombre:
            return jsonify({'error': 'El nombre es obligatorio'}), 400
        
        # La base exige código único global, incluso si el producto anterior está inactivo.
        producto_existente = (
            Producto.query
            .filter(db.func.lower(Producto.codigo) == codigo.lower())
            .first()
        )
        if producto_existente:
            return jsonify({'error': mensaje_codigo_duplicado(codigo)}), 400

        if codigo_barras:
            producto_existente = (
                Producto.query
                .filter(Producto.activo.is_(True), db.func.lower(Producto.codigo_barras) == codigo_barras.lower())
                .first()
            )
            if producto_existente:
                return jsonify({'error': f'Ya existe un producto activo con el código de barras "{codigo_barras}"'}), 400
        
        # Validar precio de venta
        try:
            precio_venta = float(precio_venta)
        except (ValueError, TypeError):
            precio_venta = 0
            
        if precio_venta <= 0:
            return jsonify({'error': 'El precio de venta debe ser mayor a 0'}), 400
        
        # Validar precio de compra
        try:
            precio_compra = float(precio_compra)
        except (ValueError, TypeError):
            precio_compra = 0

        # Validar precio mayorista (opcional)
        try:
            precio_mayorista = float(precio_mayorista) if precio_mayorista not in (None, '') else None
        except (ValueError, TypeError):
            precio_mayorista = None

        if precio_mayorista is not None and precio_mayorista <= 0:
            precio_mayorista = None

        try:
            stock_minimo = int(stock_minimo)
        except (ValueError, TypeError):
            stock_minimo = 5
        if stock_minimo < 0:
            stock_minimo = 0
        if es_servicio:
            stock_minimo = 0

        if usar_precios_opciones and not precios_opciones:
            return jsonify({'error': 'Debe cargar al menos un precio en precios opcionales'}), 400
        
        # Obtener o crear categoría
        id_categoria = _obtener_o_crear_categoria(
            id_categoria_seleccionada,
            nueva_categoria_nombre,
            None
        )
        
        if not id_categoria:
            return jsonify({'error': 'Debe seleccionar o crear una categoría'}), 400
        
        # Crear producto
        producto = Producto(
            codigo=codigo,
            codigo_barras=codigo_barras,
            nombre=nombre,
            id_categoria=id_categoria,
            precio_compra=precio_compra,
            precio_venta=precio_venta,
            precio_mayorista=precio_mayorista,
            porcentaje_iva=porcentaje_iva,
            stock_actual=0,
            stock_minimo=stock_minimo,
            es_servicio=es_servicio,
            id_usuario_modificacion=current_user.id_usuario,
            activo=True
        )
        
        db.session.add(producto)
        db.session.flush()

        if precios_opciones:
            for idx, precio in enumerate(precios_opciones):
                opt = ProductoPrecioOpcion(
                    id_producto=producto.id_producto,
                    etiqueta=_decimal_to_str(precio),
                    precio=precio,
                    orden=idx,
                    activo=True
                )
                db.session.add(opt)

        # Auditoría
        registrar_auditoria(
            accion='crear_producto',
            modulo='productos',
            descripcion=f'Creó producto rápido "{producto.nombre}" ({producto.codigo}) desde compras',
            referencia_tipo='producto',
            referencia_id=producto.id_producto,
            datos_nuevos=_producto_auditoria_data(producto),
            commit=False
        )

        db.session.commit()

        return jsonify({
            'success': True,
            'producto': {
                'id': producto.id_producto,
                'codigo': producto.codigo,
                'nombre': producto.nombre,
                'precio_compra': float(producto.precio_compra or 0),
                'precio_venta': float(producto.precio_venta or 0),
                'precio_mayorista': float(producto.precio_mayorista or 0) if producto.precio_mayorista is not None else None,
                'stock_minimo': int(producto.stock_minimo or 0),
                'es_servicio': bool(producto.es_servicio),
            }
        })

    except (IntegrityError, DataError) as exc:
        db.session.rollback()
        return jsonify({'error': mensaje_error_producto(exc, codigo=codigo, codigo_barras=codigo_barras)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@productos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crear nuevo producto"""
    if not current_user.tiene_permiso('crear_producto'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para crear productos.', 'danger')
        return redirect(url_for('productos.listar'))

    if request.method == 'POST':
        campos_texto = _campos_texto_producto_desde_form(request.form)
        codigo = campos_texto['codigo']
        codigo_barras = campos_texto['codigo_barras'] or None
        nombre = campos_texto['nombre']
        id_categoria_seleccionada = request.form.get('id_categoria', type=int)
        nueva_categoria_nombre = request.form.get('nueva_categoria_nombre', '').strip()
        nueva_categoria_descripcion = request.form.get('nueva_categoria_descripcion', '')
        precio_compra = request.form.get('precio_compra', 0, type=float)
        precio_venta = request.form.get('precio_venta', 0, type=float)
        porcentaje_iva = request.form.get('porcentaje_iva', 10, type=int)
        stock_actual = request.form.get('stock_actual', 0, type=int)
        stock_minimo = request.form.get('stock_minimo', 5, type=int)
        es_servicio = bool(request.form.get('es_servicio'))
        publicado_tienda = bool(request.form.get('publicado_tienda'))
        descripcion_tienda = request.form.get('descripcion_tienda', '').strip() or None
        if es_servicio:
            stock_actual = 0
            stock_minimo = 0

        error_longitudes = validar_longitudes_producto(campos_texto)
        if error_longitudes:
            flash(error_longitudes, 'danger')
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text=precios_opciones_text)
        
        # Validaciones
        if not codigo or not nombre or (not id_categoria_seleccionada and not nueva_categoria_nombre):
            flash('Código, nombre y categoría son obligatorios.', 'warning')
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text=precios_opciones_text)
        
        producto_existente = (
            Producto.query
            .filter(db.func.lower(Producto.codigo) == codigo.lower())
            .first()
        )
        if producto_existente:
            if _es_reenvio_creacion_reciente(producto_existente, current_user.id_usuario, nombre, codigo_barras):
                flash(f'Producto "{producto_existente.nombre}" ya quedó guardado.', 'success')
                if current_user.tiene_permiso('editar_producto'):
                    return redirect(url_for('productos.editar', id=producto_existente.id_producto))
                return redirect(url_for('productos.listar'))
            flash(mensaje_codigo_duplicado(codigo), 'danger')
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text=precios_opciones_text)

        if codigo_barras:
            producto_existente = (
                Producto.query
                .filter(Producto.activo.is_(True), db.func.lower(Producto.codigo_barras) == codigo_barras.lower())
                .first()
            )
            if producto_existente:
                if _es_reenvio_creacion_reciente(producto_existente, current_user.id_usuario, nombre, codigo_barras):
                    flash(f'Producto "{producto_existente.nombre}" ya quedó guardado.', 'success')
                    if current_user.tiene_permiso('editar_producto'):
                        return redirect(url_for('productos.editar', id=producto_existente.id_producto))
                    return redirect(url_for('productos.listar'))
                flash('Ya existe un producto activo con ese código de barras.', 'danger')
                categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
                precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
                return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text=precios_opciones_text)

        id_categoria = _obtener_o_crear_categoria(
            id_categoria_seleccionada,
            nueva_categoria_nombre,
            nueva_categoria_descripcion
        )
        if not id_categoria:
            flash('Debe seleccionar una categoría o crear una nueva.', 'warning')
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text=precios_opciones_text)
        
        producto = Producto(
            codigo=codigo,
            codigo_barras=codigo_barras,
            nombre=nombre,
            descripcion=request.form.get('descripcion', ''),
            id_categoria=id_categoria,
            marca=campos_texto['marca'],
            modelo=campos_texto['modelo'],
            color=campos_texto['color'],
            capacidad=campos_texto['capacidad'],
            precio_compra=precio_compra,
            precio_venta=precio_venta,
            precio_mayorista=request.form.get('precio_mayorista', type=float),
            porcentaje_iva=porcentaje_iva,
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
            es_servicio=es_servicio,
            publicado_tienda=publicado_tienda,
            descripcion_tienda=descripcion_tienda,
            id_usuario_modificacion=current_user.id_usuario
        )
        
        try:
            db.session.add(producto)
            db.session.flush()
            _actualizar_precios_opciones(producto, request.form)

            registrar_auditoria(
                accion='crear_producto',
                modulo='productos',
                descripcion=f'Creó producto "{producto.nombre}" ({producto.codigo})',
                referencia_tipo='producto',
                referencia_id=producto.id_producto,
                datos_nuevos=_producto_auditoria_data(producto),
                commit=False
            )
            db.session.commit()
            entidad = 'Servicio' if es_servicio else 'Producto'
            flash(f'{entidad} "{nombre}" creado correctamente.', 'success')
            return redirect(url_for('productos.listar', tipo='servicio') if es_servicio else url_for('productos.listar'))
        except (IntegrityError, DataError) as exc:
            db.session.rollback()
            flash(mensaje_error_producto(exc, codigo=codigo, codigo_barras=codigo_barras), 'danger')
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text=precios_opciones_text)
    
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    return render_template('productos/form.html', categorias=categorias, producto=None, precios_opciones_text='')


@productos_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar producto existente"""
    if not current_user.tiene_permiso('editar_producto'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar productos.', 'danger')
        return redirect(url_for('productos.listar'))

    producto = Producto.query.get_or_404(id)
    
    if request.method == 'POST':
        datos_anteriores = _producto_auditoria_data(producto)
        es_servicio_nuevo = bool(request.form.get('es_servicio'))
        stock_anterior = int(producto.stock_actual or 0)
        campos_texto = _campos_texto_producto_desde_form(request.form)
        error_longitudes = validar_longitudes_producto(campos_texto)
        if error_longitudes:
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            flash(error_longitudes, 'danger')
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=producto, precios_opciones_text=precios_opciones_text)

        producto.codigo = campos_texto['codigo']
        codigo_barras = campos_texto['codigo_barras'] or None
        producto.nombre = campos_texto['nombre']
        producto.descripcion = request.form.get('descripcion', '')
        id_categoria = _obtener_o_crear_categoria(
            request.form.get('id_categoria', type=int),
            request.form.get('nueva_categoria_nombre', ''),
            request.form.get('nueva_categoria_descripcion', '')
        )
        if not id_categoria:
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            flash('Debe seleccionar una categoría o crear una nueva.', 'warning')
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=producto, precios_opciones_text=precios_opciones_text)
        producto.id_categoria = id_categoria
        producto_existente = (
            Producto.query
            .filter(
                Producto.id_producto != producto.id_producto,
                db.func.lower(Producto.codigo) == producto.codigo.lower(),
            )
            .first()
        )
        if producto_existente:
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            flash(mensaje_codigo_duplicado(producto.codigo), 'danger')
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=producto, precios_opciones_text=precios_opciones_text)
        if codigo_barras:
            producto_existente = (
                Producto.query
                .filter(
                    Producto.activo.is_(True),
                    Producto.id_producto != producto.id_producto,
                    db.func.lower(Producto.codigo_barras) == codigo_barras.lower(),
                )
                .first()
            )
            if producto_existente:
                categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
                flash('Ya existe un producto activo con ese código de barras.', 'danger')
                precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
                return render_template('productos/form.html', categorias=categorias, producto=producto, precios_opciones_text=precios_opciones_text)
        producto.codigo_barras = codigo_barras
        producto.marca = campos_texto['marca']
        producto.modelo = campos_texto['modelo']
        producto.color = campos_texto['color']
        producto.capacidad = campos_texto['capacidad']
        producto.precio_compra = request.form.get('precio_compra', 0, type=float)
        producto.precio_venta = request.form.get('precio_venta', 0, type=float)
        producto.precio_mayorista = request.form.get('precio_mayorista', type=float)
        producto.porcentaje_iva = request.form.get('porcentaje_iva', 10, type=int)
        producto.es_servicio = es_servicio_nuevo
        producto.publicado_tienda = bool(request.form.get('publicado_tienda'))
        producto.descripcion_tienda = request.form.get('descripcion_tienda', '').strip() or None
        if es_servicio_nuevo:
            producto.stock_minimo = 0
            if stock_anterior != 0:
                producto.stock_actual = 0
                tipo_movimiento = 'ajuste_positivo' if 0 > stock_anterior else 'ajuste_negativo'
                movimiento = MovimientoStock(
                    id_producto=producto.id_producto,
                    id_usuario=current_user.id_usuario,
                    tipo_movimiento=tipo_movimiento,
                    cantidad=abs(stock_anterior),
                    stock_anterior=stock_anterior,
                    stock_nuevo=0,
                    referencia_tipo='marcar_servicio',
                    referencia_id=producto.id_producto,
                    motivo='Producto marcado como servicio'
                )
                db.session.add(movimiento)
        else:
            producto.stock_minimo = request.form.get('stock_minimo', 5, type=int)
        producto.id_usuario_modificacion = current_user.id_usuario
        _actualizar_precios_opciones(producto, request.form)

        datos_nuevos = _producto_auditoria_data(producto)
        registrar_auditoria(
            accion='editar_producto',
            modulo='productos',
            descripcion=f'Editó producto "{producto.nombre}" ({producto.codigo})',
            referencia_tipo='producto',
            referencia_id=producto.id_producto,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            commit=False
        )
        try:
            db.session.commit()
            entidad = 'Servicio' if producto.es_servicio else 'Producto'
            flash(f'{entidad} "{producto.nombre}" actualizado.', 'success')
            return redirect(url_for('productos.listar', tipo='servicio') if producto.es_servicio else url_for('productos.listar'))
        except (IntegrityError, DataError) as exc:
            db.session.rollback()
            flash(mensaje_error_producto(exc, codigo=producto.codigo, codigo_barras=codigo_barras), 'danger')
            producto = Producto.query.get_or_404(id)
            categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
            precios_opciones_text = request.form.get('precios_opciones', '') if request.form.get('usa_precios_opciones') else ''
            return render_template('productos/form.html', categorias=categorias, producto=producto, precios_opciones_text=precios_opciones_text)
    
    categorias = Categoria.query.filter_by(activo=True).order_by(Categoria.nombre).all()
    opciones = (
        producto.precios_opciones.filter_by(activo=True)
        .order_by(ProductoPrecioOpcion.orden.asc(), ProductoPrecioOpcion.id_opcion_precio.asc())
        .all()
    )
    precios_opciones_text = '\n'.join([_decimal_to_str(o.precio) for o in opciones])
    return render_template('productos/form.html', categorias=categorias, producto=producto, precios_opciones_text=precios_opciones_text)


@productos_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar (desactivar) producto"""
    if not current_user.tiene_permiso('eliminar_producto'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para eliminar productos.', 'danger')
        return redirect(url_for('productos.listar'))

    ok, _autorizacion = validar_autorizacion(
        request.form.get('id_autorizacion', type=int),
        'eliminar_producto'
    )
    if not ok:
        flash('Se requiere autorización de administrador para eliminar productos.', 'danger')
        return redirect(url_for('productos.listar'))

    producto = Producto.query.get_or_404(id)
    datos_anteriores = _producto_auditoria_data(producto)
    producto.activo = False
    producto.id_usuario_modificacion = current_user.id_usuario

    datos_nuevos = _producto_auditoria_data(producto)
    registrar_auditoria(
        accion='eliminar_producto',
        modulo='productos',
        descripcion=f'Desactivó producto "{producto.nombre}" ({producto.codigo})',
        referencia_tipo='producto',
        referencia_id=producto.id_producto,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        id_autorizacion=_autorizacion.id_autorizacion if _autorizacion else None,
        commit=False
    )
    db.session.commit()
    flash(f'Producto "{producto.nombre}" eliminado.', 'success')
    return redirect(url_for('productos.listar'))


@productos_bp.route('/buscar')
@login_required
def buscar_api():
    """API para búsqueda de productos (usado en POS)"""
    if not (current_user.tiene_permiso('crear_venta') or current_user.tiene_permiso('ver_inventario')):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    q = (request.args.get('q', '') or '').strip()
    if len(q) < 2:
        return jsonify([])
    
    productos = (
        Producto.query.join(Categoria, Producto.id_categoria == Categoria.id_categoria)
        .filter(
            Producto.activo.is_(True),
            db.or_(
                Producto.nombre.ilike(f'%{q}%'),
                Producto.codigo.ilike(f'%{q}%'),
                Producto.codigo_barras.ilike(f'%{q}%'),
                Producto.codigo_proveedor.ilike(f'%{q}%'),
                Categoria.nombre.ilike(f'%{q}%')
            )
        )
        .limit(10)
        .all()
    )

    productos_ids = [p.id_producto for p in productos]
    opciones_por_producto = {}
    if productos_ids:
        opciones = (
            ProductoPrecioOpcion.query
            .filter(
                ProductoPrecioOpcion.activo.is_(True),
                ProductoPrecioOpcion.id_producto.in_(productos_ids),
            )
            .order_by(
                ProductoPrecioOpcion.id_producto.asc(),
                ProductoPrecioOpcion.orden.asc(),
                ProductoPrecioOpcion.id_opcion_precio.asc(),
            )
            .all()
        )
        for opt in opciones:
            opciones_por_producto.setdefault(int(opt.id_producto), []).append(opt)
    
    return jsonify([{
        'id': p.id_producto,
        'codigo': p.codigo,
        'nombre': p.nombre,
        'precio': float(p.precio_venta),
        'precio_mayorista': float(p.precio_mayorista) if p.precio_mayorista else None,
        'precios_opciones': [
            {
                'id': int(o.id_opcion_precio),
                'etiqueta': (o.etiqueta or '').strip() or None,
                'precio': float(o.precio or 0),
            }
            for o in opciones_por_producto.get(int(p.id_producto), [])
        ],
        'stock': p.stock_actual,
        'stock_minimo': p.stock_minimo,
        'es_servicio': bool(p.es_servicio),
        'iva': p.porcentaje_iva
    } for p in productos])


@productos_bp.route('/buscar_exacto')
@login_required
def buscar_exacto_api():
    if not (current_user.tiene_permiso('crear_venta') or current_user.tiene_permiso('ver_inventario')):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    q = (request.args.get('q', '') or '').strip()
    if not q:
        return jsonify({})

    q_lower = q.lower()
    producto = (
        Producto.query
        .filter(
            Producto.activo.is_(True),
            db.or_(
                db.func.lower(Producto.codigo) == q_lower,
                db.func.lower(Producto.codigo_barras) == q_lower,
                db.func.lower(Producto.codigo_proveedor) == q_lower,
            )
        )
        .first()
    )

    if not producto:
        return jsonify({})

    opciones = (
        ProductoPrecioOpcion.query
        .filter(
            ProductoPrecioOpcion.activo.is_(True),
            ProductoPrecioOpcion.id_producto == producto.id_producto,
        )
        .order_by(
            ProductoPrecioOpcion.orden.asc(),
            ProductoPrecioOpcion.id_opcion_precio.asc(),
        )
        .all()
    )

    return jsonify({
        'id': producto.id_producto,
        'codigo': producto.codigo,
        'nombre': producto.nombre,
        'precio': float(producto.precio_venta),
        'precio_mayorista': float(producto.precio_mayorista) if producto.precio_mayorista else None,
        'precios_opciones': [
            {
                'id': int(o.id_opcion_precio),
                'etiqueta': (o.etiqueta or '').strip() or None,
                'precio': float(o.precio or 0),
            }
            for o in opciones
        ],
        'stock': producto.stock_actual,
        'stock_minimo': producto.stock_minimo,
        'es_servicio': bool(producto.es_servicio),
        'iva': producto.porcentaje_iva
    })


@productos_bp.route('/<int:id>/historial_compras')
@login_required
def historial_compras(id):
    """API para obtener historial de compras de un producto"""
    if not current_user.tiene_permiso('ver_inventario'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    producto = Producto.query.get_or_404(id)
    
    # Obtener todos los detalles de compra de este producto
    detalles = db.session.query(
        DetalleCompra,
        Compra,
        Proveedor
    ).join(
        Compra, DetalleCompra.id_compra == Compra.id_compra
    ).join(
        Proveedor, Compra.id_proveedor == Proveedor.id_proveedor
    ).filter(
        DetalleCompra.id_producto == id
    ).order_by(
        Compra.fecha_compra.desc()
    ).limit(50).all()
    
    historial = []
    for detalle, compra, proveedor in detalles:
        historial.append({
            'id_compra': compra.id_compra,
            'fecha': compra.fecha_compra.strftime('%d/%m/%Y') if compra.fecha_compra else '',
            'proveedor': proveedor.nombre,
            'factura': compra.numero_factura or '-',
            'cantidad': detalle.cantidad,
            'precio_unitario': float(detalle.precio_unitario),
            'subtotal': float(detalle.subtotal)
        })
    
    return jsonify({
        'producto': {
            'id': producto.id_producto,
            'codigo': producto.codigo,
            'nombre': producto.nombre
        },
        'historial': historial
    })

@productos_bp.route('/<int:id>/ajustar_stock', methods=['POST'])
@login_required
def ajustar_stock(id):
    """Registrar ajuste de stock para un producto"""
    try:
        if not current_user.tiene_permiso('editar_stock'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

        data = request.get_json() or {}
        stock_fisico = data.get('stock_fisico', None)
        motivo = (data.get('motivo') or '').strip()
        observaciones = data.get('observaciones', '')
        id_autorizacion = data.get('id_autorizacion')
        if id_autorizacion in (None, ''):
            id_autorizacion = None
        else:
            id_autorizacion = int(id_autorizacion)

        if stock_fisico is None:
            return jsonify({'error': 'Debe indicar stock_fisico'}), 400
        stock_fisico = int(stock_fisico)
        if stock_fisico < 0:
            return jsonify({'error': 'stock_fisico no puede ser negativo'}), 400
        if not motivo:
            return jsonify({'error': 'Debe indicar el motivo del ajuste'}), 400

        ok, autorizacion = validar_autorizacion(id_autorizacion, 'editar_stock')
        if not ok:
            return jsonify({'error': 'Se requiere autorización para ajustar stock'}), 403

        producto = Producto.query.get_or_404(id)
        if producto.es_servicio:
            return jsonify({'error': 'No se ajusta stock para servicios'}), 400

        stock_sistema = int(producto.stock_actual or 0)
        diferencia = stock_fisico - stock_sistema

        ajuste = AjusteInventario(
            id_usuario=current_user.id_usuario,
            motivo=motivo,
            observaciones=observaciones,
            estado='completado'
        )
        db.session.add(ajuste)
        db.session.flush()

        detalle = DetalleAjusteInventario(
            id_ajuste=ajuste.id_ajuste,
            id_producto=producto.id_producto,
            stock_sistema=stock_sistema,
            stock_fisico=stock_fisico,
            diferencia=diferencia
        )
        db.session.add(detalle)

        datos_anteriores = {
            'id_producto': producto.id_producto,
            'codigo': producto.codigo,
            'nombre': producto.nombre,
            'stock_sistema': stock_sistema,
        }

        if diferencia != 0:
            producto.stock_actual = stock_fisico
            tipo_movimiento = 'ajuste_positivo' if diferencia > 0 else 'ajuste_negativo'
            movimiento = MovimientoStock(
                id_producto=producto.id_producto,
                id_usuario=current_user.id_usuario,
                tipo_movimiento=tipo_movimiento,
                cantidad=abs(diferencia),
                stock_anterior=stock_sistema,
                stock_nuevo=stock_fisico,
                referencia_tipo='ajuste_inventario',
                referencia_id=ajuste.id_ajuste,
                motivo=f'Ajuste inventario #{ajuste.id_ajuste}: {motivo}'
            )
            db.session.add(movimiento)

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='ajuste_inventario',
                    modulo='inventario',
                    descripcion=f'Ajuste de stock para producto "{producto.nombre}" ({producto.codigo})',
                    referencia_tipo='ajuste_inventario',
                    referencia_id=ajuste.id_ajuste,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos={
                        'id_ajuste': ajuste.id_ajuste,
                        'id_producto': producto.id_producto,
                        'stock_fisico': stock_fisico,
                        'diferencia': diferencia,
                        'motivo': motivo,
                        'observaciones': observaciones,
                    },
                    id_autorizacion=autorizacion.id_autorizacion if autorizacion else None,
                    commit=False
                )
        except Exception:
            pass

        db.session.commit()
        return jsonify({
            'success': True,
            'id_ajuste': ajuste.id_ajuste,
            'id_producto': producto.id_producto,
            'stock_sistema': stock_sistema,
            'stock_fisico': stock_fisico,
            'diferencia': diferencia
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@productos_bp.route('/<int:id>/ajuste_rapido', methods=['POST'])
@login_required
def ajuste_rapido(id):
    """Ajuste rápido de stock (+/-)"""
    try:
        if not current_user.tiene_permiso('ajuste_rapido_stock'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos para ajuste rápido de stock', 'modo_demo': False}), 403

        data = request.get_json() or {}
        tipo = data.get('tipo', '').strip()  # 'entrada' o 'salida'
        cantidad = data.get('cantidad', 0)
        motivo = (data.get('motivo') or '').strip()
        observaciones = data.get('observaciones', '').strip()

        # Validaciones
        if tipo not in ['entrada', 'salida']:
            return jsonify({'error': 'Tipo debe ser "entrada" o "salida"'}), 400
        
        try:
            cantidad = int(cantidad)
        except (ValueError, TypeError):
            return jsonify({'error': 'Cantidad inválida'}), 400
            
        if cantidad <= 0:
            return jsonify({'error': 'Cantidad debe ser mayor a 0'}), 400
        
        if not motivo:
            return jsonify({'error': 'Debe indicar el motivo del ajuste'}), 400

        producto = Producto.query.get_or_404(id)
        
        if producto.es_servicio:
            return jsonify({'error': 'No se ajusta stock para servicios'}), 400

        stock_anterior = int(producto.stock_actual or 0)
        
        # Calcular nuevo stock
        if tipo == 'entrada':
            stock_nuevo = stock_anterior + cantidad
        else:  # salida
            if stock_anterior < cantidad:
                return jsonify({'error': f'Stock insuficiente. Actual: {stock_anterior}'}), 400
            stock_nuevo = stock_anterior - cantidad

        # Actualizar stock
        producto.stock_actual = stock_nuevo
        producto.id_usuario_modificacion = current_user.id_usuario

        # Registrar movimiento
        tipo_movimiento = 'entrada' if tipo == 'entrada' else 'salida'
        motivo_completo = f'Ajuste rápido: {motivo}'
        if observaciones:
            motivo_completo += f' - {observaciones}'
            
        movimiento = MovimientoStock(
            id_producto=producto.id_producto,
            id_usuario=current_user.id_usuario,
            tipo_movimiento=tipo_movimiento,
            cantidad=cantidad,
            stock_anterior=stock_anterior,
            stock_nuevo=stock_nuevo,
            referencia_tipo='ajuste_rapido',
            referencia_id=None,
            motivo=motivo_completo
        )
        db.session.add(movimiento)

        # Auditoría
        registrar_auditoria(
            accion='ajuste_rapido_stock',
            modulo='inventario',
            descripcion=f'Ajuste rápido de stock para "{producto.nombre}" ({producto.codigo})',
            referencia_tipo='producto',
            referencia_id=producto.id_producto,
            datos_anteriores={
                'id_producto': producto.id_producto,
                'codigo': producto.codigo,
                'nombre': producto.nombre,
                'stock_anterior': stock_anterior,
            },
            datos_nuevos={
                'stock_nuevo': stock_nuevo,
                'tipo': tipo,
                'cantidad': cantidad,
                'motivo': motivo,
                'observaciones': observaciones,
            },
            commit=False
        )

        db.session.commit()
        
        return jsonify({
            'success': True,
            'id_producto': producto.id_producto,
            'stock_anterior': stock_anterior,
            'stock_nuevo': stock_nuevo,
            'cantidad': cantidad,
            'tipo': tipo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


from app.routes.productos_categorias import register_categoria_routes
from app.routes.productos_codigos import register_codigo_routes

register_categoria_routes(productos_bp)
register_codigo_routes(productos_bp)
