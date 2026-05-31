"""Stock blando por recetas para productos gastronomicos."""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.inventario import MovimientoStock
from app.models.producto import Producto
from app.models.producto_presentacion import ProductoPresentacionStock
from gastronomia.models import (
    GastronomiaGrupoOpciones,
    GastronomiaOpcionProducto,
    GastronomiaPedidoItem,
    GastronomiaProducto,
)
from gastronomia.stock_models import (
    GastronomiaOpcionInsumo,
    GastronomiaPedidoItemConsumo,
    GastronomiaRecetaInsumo,
)


UNIDADES_STOCK = {'unidad', 'g', 'ml', 'mazo'}


def listar_insumos(cliente_id: int) -> list[Producto]:
    return (
        _insumos_query(cliente_id)
        .order_by(Producto.nombre.asc(), Producto.id_producto.asc())
        .all()
    )


def serializar_insumo(insumo: Producto) -> dict:
    return {
        'id_producto': int(insumo.id_producto),
        'codigo': insumo.codigo,
        'nombre': insumo.nombre,
        'stock_actual': int(insumo.stock_actual or 0),
        'stock_minimo': int(insumo.stock_minimo or 0),
        'unidad_stock': _normalizar_unidad(getattr(insumo, 'unidad_stock', None)),
        'presentaciones': [
            item.to_dict()
            for item in insumo.presentaciones_stock
            .filter_by(activo=True)
            .order_by(ProductoPresentacionStock.nombre.asc())
            .all()
        ],
    }


def configurar_insumo(cliente_id: int, insumo_id: int, data: dict) -> Producto:
    insumo = _obtener_insumo(cliente_id, insumo_id)
    insumo.unidad_stock = _normalizar_unidad(data.get('unidad_stock'))
    if 'stock_minimo' in data:
        insumo.stock_minimo = max(0, _parse_int(data.get('stock_minimo'), 'Stock minimo invalido.'))
    db.session.commit()
    return insumo


def guardar_presentacion(cliente_id: int, insumo_id: int, data: dict) -> ProductoPresentacionStock:
    insumo = _obtener_insumo(cliente_id, insumo_id)
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        raise ValueError('El nombre de la presentacion es obligatorio.')
    factor = _parse_int(data.get('factor_unidad_base'), 'La equivalencia debe ser numerica.')
    if factor <= 0:
        raise ValueError('La equivalencia debe ser mayor a cero.')
    presentacion = ProductoPresentacionStock(
        id_producto=int(insumo.id_producto),
        nombre=nombre[:100],
        factor_unidad_base=factor,
    )
    db.session.add(presentacion)
    _commit_duplicate('Ya existe una presentacion con ese nombre.')
    return presentacion


def eliminar_presentacion(cliente_id: int, presentacion_id: int) -> bool:
    presentacion = (
        ProductoPresentacionStock.query
        .join(Producto, Producto.id_producto == ProductoPresentacionStock.id_producto)
        .filter(
            ProductoPresentacionStock.id_presentacion == int(presentacion_id),
            ProductoPresentacionStock.activo.is_(True),
            _filtro_cliente_insumo(cliente_id),
        )
        .first()
    )
    if not presentacion:
        return False
    presentacion.activo = False
    db.session.commit()
    return True


def registrar_entrada(cliente_id: int, usuario_id: int, insumo_id: int, data: dict) -> Producto:
    insumo = _obtener_insumo(cliente_id, insumo_id)
    cantidad = _parse_int(data.get('cantidad'), 'La cantidad de presentaciones debe ser numerica.')
    if cantidad <= 0:
        raise ValueError('La cantidad de presentaciones debe ser mayor a cero.')
    factor = 1
    presentacion_id = data.get('presentacion_id')
    if presentacion_id not in (None, ''):
        presentacion = ProductoPresentacionStock.query.filter_by(
            id_presentacion=int(presentacion_id),
            id_producto=int(insumo.id_producto),
            activo=True,
        ).first()
        if not presentacion:
            raise ValueError('La presentacion no pertenece al insumo.')
        factor = int(presentacion.factor_unidad_base or 1)
    cantidad_base = cantidad * factor
    _mover_stock_central(
        insumo,
        cantidad_base,
        usuario_id=usuario_id,
        referencia_tipo='gastronomia_entrada',
        motivo='Entrada rapida desde inventario gastronomico.',
    )
    db.session.commit()
    return insumo


def ajustar_stock(cliente_id: int, usuario_id: int, insumo_id: int, data: dict) -> Producto:
    insumo = _obtener_insumo(cliente_id, insumo_id)
    stock_fisico = _parse_int(data.get('stock_fisico'), 'El stock fisico debe ser numerico.')
    if stock_fisico < 0:
        raise ValueError('El stock fisico no puede ser negativo.')
    stock_anterior = int(insumo.stock_actual or 0)
    diferencia = stock_fisico - stock_anterior
    if diferencia:
        _mover_stock_central(
            insumo,
            diferencia,
            usuario_id=usuario_id,
            referencia_tipo='gastronomia_ajuste',
            motivo=(data.get('motivo') or 'Ajuste fisico desde gastronomia').strip()[:255],
        )
    db.session.commit()
    return insumo


def obtener_receta(cliente_id: int, producto_id: int) -> dict:
    producto = _obtener_producto_menu(cliente_id, producto_id)
    receta = (
        GastronomiaRecetaInsumo.query
        .filter_by(cliente_id=int(cliente_id), producto_id=int(producto.id_producto), activo=True)
        .order_by(GastronomiaRecetaInsumo.id_receta_insumo.asc())
        .all()
    )
    opciones = (
        GastronomiaOpcionInsumo.query
        .join(GastronomiaOpcionProducto, GastronomiaOpcionProducto.id_opcion == GastronomiaOpcionInsumo.opcion_id)
        .join(GastronomiaGrupoOpciones, GastronomiaGrupoOpciones.id_grupo == GastronomiaOpcionProducto.grupo_id)
        .filter(
            GastronomiaOpcionInsumo.cliente_id == int(cliente_id),
            GastronomiaOpcionInsumo.activo.is_(True),
            GastronomiaGrupoOpciones.producto_id == int(producto.id_producto),
        )
        .order_by(GastronomiaOpcionInsumo.id_opcion_insumo.asc())
        .all()
    )
    return {
        'producto_id': int(producto.id_producto),
        'producto_nombre': producto.nombre,
        'items': [item.to_dict() for item in receta],
        'opciones': [item.to_dict() for item in opciones],
    }


def guardar_receta(cliente_id: int, producto_id: int, data: dict) -> dict:
    producto = _obtener_producto_menu(cliente_id, producto_id)
    items = _normalizar_receta(cliente_id, data.get('items') or [])
    opciones = _normalizar_opciones(cliente_id, producto.id_producto, data.get('opciones') or [])
    GastronomiaRecetaInsumo.query.filter_by(
        cliente_id=int(cliente_id),
        producto_id=int(producto.id_producto),
    ).delete(synchronize_session=False)
    _eliminar_opciones_producto(cliente_id, producto.id_producto)
    for insumo_id, cantidad in items.items():
        db.session.add(GastronomiaRecetaInsumo(
            cliente_id=int(cliente_id),
            producto_id=int(producto.id_producto),
            insumo_id=insumo_id,
            cantidad=cantidad,
        ))
    for opcion_id, insumo_id, cantidad_delta in opciones:
        db.session.add(GastronomiaOpcionInsumo(
            cliente_id=int(cliente_id),
            opcion_id=opcion_id,
            insumo_id=insumo_id,
            cantidad_delta=cantidad_delta,
        ))
    db.session.commit()
    return obtener_receta(cliente_id, producto.id_producto)


def consumir_stock_item(item: GastronomiaPedidoItem) -> list[dict]:
    alertas = []
    producto_menu = item.producto or db.session.get(GastronomiaProducto, int(item.producto_id))
    if producto_menu and producto_menu.control_stock_venta:
        consumo = _consumir_producto_menu(item, producto_menu, int(item.cantidad or 0))
        if consumo.faltante:
            alertas.append(consumo.alerta_dict())
    for insumo_id, cantidad in _cantidades_receta_item(item).items():
        insumo = db.session.get(Producto, int(insumo_id))
        if not insumo or cantidad <= 0:
            continue
        stock_anterior = int(insumo.stock_actual or 0)
        _mover_stock_central(
            insumo,
            -cantidad,
            usuario_id=_usuario_item(item),
            referencia_tipo='gastronomia_pedido',
            referencia_id=int(item.pedido_id),
            motivo=f'Consumo de receta por {item.nombre_producto}.',
        )
        consumo = _registrar_consumo(item, insumo, cantidad, stock_anterior)
        if consumo.faltante:
            alertas.append(consumo.alerta_dict())
    db.session.flush()
    return alertas


def restaurar_stock_items(items: list[GastronomiaPedidoItem]) -> None:
    item_ids = [int(item.id_item) for item in items if item.id_item]
    if not item_ids:
        return
    consumos = GastronomiaPedidoItemConsumo.query.filter(
        GastronomiaPedidoItemConsumo.item_id.in_(item_ids),
        GastronomiaPedidoItemConsumo.restaurado.is_(False),
    ).all()
    items_por_id = {int(item.id_item): item for item in items}
    for consumo in consumos:
        item = items_por_id.get(int(consumo.item_id))
        if consumo.tipo_origen == 'producto_menu':
            producto = item.producto if item else None
            if producto:
                producto.stock_disponible = int(producto.stock_disponible or 0) + int(consumo.cantidad or 0)
        elif consumo.insumo:
            _mover_stock_central(
                consumo.insumo,
                int(consumo.cantidad or 0),
                usuario_id=_usuario_item(item),
                referencia_tipo='gastronomia_restaura',
                referencia_id=int(item.pedido_id) if item else None,
                motivo=f'Restauracion por cancelacion o edicion de {consumo.nombre_stock}.',
            )
        consumo.restaurado = True
        consumo.fecha_restauracion = datetime.utcnow()
    db.session.flush()


def alertas_stock_pedido(pedido_id: int) -> list[dict]:
    return [
        consumo.alerta_dict()
        for consumo in (
            GastronomiaPedidoItemConsumo.query
            .join(GastronomiaPedidoItem, GastronomiaPedidoItem.id_item == GastronomiaPedidoItemConsumo.item_id)
            .filter(
                GastronomiaPedidoItem.pedido_id == int(pedido_id),
                GastronomiaPedidoItemConsumo.restaurado.is_(False),
                GastronomiaPedidoItemConsumo.faltante > 0,
            )
            .order_by(GastronomiaPedidoItemConsumo.id_consumo.asc())
            .all()
        )
    ]


def _cantidades_receta_item(item: GastronomiaPedidoItem) -> Counter:
    cantidad_items = max(0, int(item.cantidad or 0))
    cantidades = Counter()
    for receta in GastronomiaRecetaInsumo.query.filter_by(
        cliente_id=int(item.cliente_id),
        producto_id=int(item.producto_id),
        activo=True,
    ).all():
        cantidades[int(receta.insumo_id)] += int(receta.cantidad or 0) * cantidad_items
    opcion_ids = [int(mod.opcion_id) for mod in item.modificadores.all()]
    if opcion_ids:
        for ajuste in GastronomiaOpcionInsumo.query.filter(
            GastronomiaOpcionInsumo.cliente_id == int(item.cliente_id),
            GastronomiaOpcionInsumo.opcion_id.in_(opcion_ids),
            GastronomiaOpcionInsumo.activo.is_(True),
        ).all():
            cantidades[int(ajuste.insumo_id)] += int(ajuste.cantidad_delta or 0) * cantidad_items
    return Counter({insumo_id: cantidad for insumo_id, cantidad in cantidades.items() if cantidad > 0})


def _consumir_producto_menu(item, producto: GastronomiaProducto, cantidad: int):
    stock_anterior = int(producto.stock_disponible or 0)
    producto.stock_disponible = stock_anterior - max(0, cantidad)
    return _registrar_consumo(item, None, cantidad, stock_anterior, producto.nombre)


def _registrar_consumo(item, insumo, cantidad: int, stock_anterior: int, nombre: str | None = None):
    stock_nuevo = stock_anterior - int(cantidad or 0)
    consumo = GastronomiaPedidoItemConsumo(
        cliente_id=int(item.cliente_id),
        item_id=int(item.id_item),
        insumo_id=int(insumo.id_producto) if insumo else None,
        tipo_origen='receta' if insumo else 'producto_menu',
        nombre_stock=(insumo.nombre if insumo else nombre) or 'Stock',
        unidad_stock=_normalizar_unidad(getattr(insumo, 'unidad_stock', None)),
        cantidad=int(cantidad or 0),
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        faltante=max(0, -stock_nuevo),
    )
    db.session.add(consumo)
    return consumo


def _mover_stock_central(insumo, diferencia: int, *, usuario_id, referencia_tipo, motivo, referencia_id=None):
    stock_anterior = int(insumo.stock_actual or 0)
    insumo.stock_actual = stock_anterior + int(diferencia or 0)
    db.session.add(MovimientoStock(
        id_producto=int(insumo.id_producto),
        id_usuario=int(usuario_id) if usuario_id else None,
        tipo_movimiento='entrada' if diferencia > 0 else 'salida',
        cantidad=abs(int(diferencia or 0)),
        stock_anterior=stock_anterior,
        stock_nuevo=int(insumo.stock_actual),
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        motivo=motivo,
    ))


def _normalizar_receta(cliente_id: int, items: list[dict]) -> Counter:
    cantidades = Counter()
    for item in items:
        insumo_id = _parse_int(item.get('insumo_id'), 'Insumo invalido.')
        cantidad = _parse_int(item.get('cantidad'), 'Cantidad de receta invalida.')
        if cantidad <= 0:
            raise ValueError('La cantidad de receta debe ser mayor a cero.')
        _obtener_insumo(cliente_id, insumo_id)
        cantidades[insumo_id] += cantidad
    return cantidades


def _normalizar_opciones(cliente_id: int, producto_id: int, items: list[dict]) -> list[tuple[int, int, int]]:
    resultado = []
    for item in items:
        opcion_id = _parse_int(item.get('opcion_id'), 'Opcion invalida.')
        insumo_id = _parse_int(item.get('insumo_id'), 'Insumo invalido.')
        delta = _parse_int(item.get('cantidad_delta'), 'Ajuste de opcion invalido.')
        if not delta:
            continue
        _obtener_insumo(cliente_id, insumo_id)
        opcion = (
            GastronomiaOpcionProducto.query
            .join(GastronomiaGrupoOpciones, GastronomiaGrupoOpciones.id_grupo == GastronomiaOpcionProducto.grupo_id)
            .filter(
                GastronomiaOpcionProducto.id_opcion == opcion_id,
                GastronomiaOpcionProducto.cliente_id == int(cliente_id),
                GastronomiaGrupoOpciones.producto_id == int(producto_id),
            )
            .first()
        )
        if not opcion:
            raise ValueError('La opcion no pertenece al producto gastronomico.')
        resultado.append((opcion_id, insumo_id, delta))
    return resultado


def _eliminar_opciones_producto(cliente_id: int, producto_id: int) -> None:
    opcion_ids = [
        row[0]
        for row in (
            db.session.query(GastronomiaOpcionProducto.id_opcion)
            .join(GastronomiaGrupoOpciones, GastronomiaGrupoOpciones.id_grupo == GastronomiaOpcionProducto.grupo_id)
            .filter(
                GastronomiaGrupoOpciones.cliente_id == int(cliente_id),
                GastronomiaGrupoOpciones.producto_id == int(producto_id),
            )
            .all()
        )
    ]
    if opcion_ids:
        GastronomiaOpcionInsumo.query.filter(
            GastronomiaOpcionInsumo.cliente_id == int(cliente_id),
            GastronomiaOpcionInsumo.opcion_id.in_(opcion_ids),
        ).delete(synchronize_session=False)


def _insumos_query(cliente_id: int):
    return Producto.query.filter(
        Producto.activo.is_(True),
        Producto.es_servicio.isnot(True),
        _filtro_cliente_insumo(cliente_id),
    )


def _filtro_cliente_insumo(cliente_id: int):
    return or_(Producto.id_cliente == int(cliente_id), Producto.id_cliente.is_(None))


def _obtener_insumo(cliente_id: int, insumo_id: int) -> Producto:
    insumo = _insumos_query(cliente_id).filter(Producto.id_producto == int(insumo_id)).first()
    if not insumo:
        raise ValueError('Insumo no encontrado para este cliente.')
    return insumo


def _obtener_producto_menu(cliente_id: int, producto_id: int) -> GastronomiaProducto:
    producto = GastronomiaProducto.query.filter_by(
        cliente_id=int(cliente_id),
        id_producto=int(producto_id),
        activo=True,
    ).first()
    if not producto:
        raise ValueError('Producto gastronomico no encontrado.')
    return producto


def _usuario_item(item) -> int | None:
    pedido = getattr(item, 'pedido', None)
    return int(pedido.usuario_id) if pedido and pedido.usuario_id else None


def _normalizar_unidad(value) -> str:
    unidad = (value or 'unidad').strip().lower()
    return unidad if unidad in UNIDADES_STOCK else 'unidad'


def _parse_int(value, message: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc


def _commit_duplicate(message: str) -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValueError(message) from exc
