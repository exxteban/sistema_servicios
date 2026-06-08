"""Cliente final automatico para pedidos gastronomicos desde tienda."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import secrets
from urllib.parse import quote

from app import db
from app.models.rol import Rol
from app.models.usuario import Usuario
from app.utils.phone_utils import normalizar_telefono
from app.utils.public_url import build_public_url
from gastronomia.customer_models import (
    GastronomiaClienteDireccion,
    GastronomiaClienteFavorito,
    GastronomiaClienteFinal,
)
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem
from gastronomia.services.pedido_service import crear_pedido


def perfil_cliente_publico(cliente_id: int, telefono: str, token: str | None = None) -> dict:
    telefono_normalizado = normalizar_telefono(telefono or '')
    if not telefono_normalizado:
        raise ValueError('Telefono invalido.')
    cliente = _buscar_cliente_final(cliente_id, telefono_normalizado)
    if not cliente or not _token_valido(cliente, token):
        return {'encontrado': False}
    return _perfil_dict(cliente)


def crear_pedido_publico_gastronomia(cliente_id: int, data: dict) -> dict:
    nombre = (data.get('nombre') or data.get('nombre_cliente') or '').strip()[:120]
    celular = (data.get('celular') or data.get('celular_cliente') or '').strip()[:40]
    telefono_normalizado = normalizar_telefono(celular)
    if not nombre:
        raise ValueError('El nombre es obligatorio.')
    if not telefono_normalizado:
        raise ValueError('El WhatsApp es obligatorio.')

    tipo_pedido = (data.get('tipo_pedido') or 'delivery').strip().lower()
    if tipo_pedido not in {'delivery', 'retiro'}:
        raise ValueError('Tipo de pedido invalido.')
    direccion = (data.get('direccion_entrega') or data.get('direccion') or '').strip()[:240]
    if tipo_pedido == 'delivery' and not direccion:
        raise ValueError('La direccion es obligatoria para delivery.')

    cliente_final = _obtener_o_crear_cliente_final(cliente_id, telefono_normalizado, nombre, celular)
    usuario_id = _usuario_receptor_pedido(cliente_id)
    pedido_payload = {
        'tipo_pedido': tipo_pedido,
        'nombre_cliente': nombre,
        'celular_cliente': celular,
        'direccion_entrega': direccion if tipo_pedido == 'delivery' else None,
        'referencia_entrega': (data.get('referencia_entrega') or '').strip()[:80] or None,
        'ubicacion_entrega_url': (data.get('ubicacion_entrega_url') or '').strip()[:500] or None,
        'destino_latitud': data.get('destino_latitud'),
        'destino_longitud': data.get('destino_longitud'),
        'notas': (data.get('notas') or '').strip()[:1000] or None,
        'cliente_final_id': cliente_final.id_cliente_final,
        'origen_pedido': 'tienda_online',
        'items': _normalizar_items_carrito(data.get('items') or []),
    }
    pedido = crear_pedido(cliente_id, usuario_id, pedido_payload)
    _registrar_actividad_cliente(cliente_final, pedido, data)
    return {
        'pedido': _pedido_publico_dict(pedido),
        'cliente': cliente_final.to_public_dict(),
        'token_cliente': cliente_final.token_publico,
        'perfil': _perfil_dict(cliente_final),
    }


def _buscar_cliente_final(cliente_id: int, telefono_normalizado: str) -> GastronomiaClienteFinal | None:
    return GastronomiaClienteFinal.query.filter_by(
        cliente_id=int(cliente_id),
        telefono_normalizado=telefono_normalizado,
    ).first()


def _obtener_o_crear_cliente_final(cliente_id: int, telefono_normalizado: str, nombre: str, celular: str) -> GastronomiaClienteFinal:
    cliente = _buscar_cliente_final(cliente_id, telefono_normalizado)
    if not cliente:
        cliente = GastronomiaClienteFinal(
            cliente_id=int(cliente_id),
            telefono_normalizado=telefono_normalizado,
            nombre=nombre,
            celular=celular,
            token_publico=secrets.token_urlsafe(24),
        )
    cliente.nombre = nombre or cliente.nombre
    cliente.celular = celular or cliente.celular
    if not cliente.token_publico:
        cliente.token_publico = secrets.token_urlsafe(24)
    db.session.add(cliente)
    db.session.flush()
    return cliente


def _usuario_receptor_pedido(cliente_id: int) -> int:
    usuario = (
        Usuario.query
        .filter(Usuario.id_cliente == int(cliente_id), Usuario.activo.is_(True))
        .order_by(Usuario.id_rol.asc(), Usuario.id_usuario.asc())
        .first()
    )
    if not usuario:
        usuario = (
            Usuario.query
            .join(Rol, Rol.id_rol == Usuario.id_rol)
            .filter(
                Usuario.activo.is_(True),
                db.func.lower(Usuario.username).notin_(['root', 'superusuario']),
                db.func.lower(Rol.nombre).in_(['administrador', 'admin']),
            )
            .order_by(Usuario.id_rol.asc(), Usuario.id_usuario.asc())
            .first()
        )
    if not usuario:
        raise ValueError('La tienda no tiene un usuario administrador activo para recibir pedidos.')
    return int(usuario.id_usuario)


def _normalizar_items_carrito(items: list[dict]) -> list[dict]:
    normalizados = []
    for item in items:
        if not isinstance(item, dict):
            continue
        producto_id = item.get('producto_id') or item.get('id_producto') or item.get('id')
        cantidad = _parse_int(item.get('cantidad') or item.get('quantity'), 1)
        opciones = []
        for modifier in item.get('modifiers') or item.get('modificadores') or []:
            if not isinstance(modifier, dict):
                continue
            opcion_id = _parse_int(modifier.get('id_opcion') or modifier.get('opcion_id'), 0)
            repeticiones = _parse_int(modifier.get('cantidad'), 1)
            if opcion_id > 0:
                opciones.extend([opcion_id] * max(1, min(20, repeticiones)))
        if _parse_int(producto_id, 0) > 0 and cantidad > 0:
            normalizados.append({
                'producto_id': int(producto_id),
                'cantidad': max(1, min(99, cantidad)),
                'opciones': opciones,
                'notas': (item.get('notas') or '').strip()[:500] or None,
            })
    if not normalizados:
        raise ValueError('El pedido debe tener al menos un producto.')
    return normalizados


def _registrar_actividad_cliente(cliente: GastronomiaClienteFinal, pedido: GastronomiaPedido, data: dict) -> None:
    ahora = datetime.utcnow()
    cliente.total_pedidos = int(cliente.total_pedidos or 0) + 1
    cliente.ultima_visita = ahora
    _guardar_direccion(cliente, pedido, data, ahora)
    _actualizar_favoritos(cliente, pedido, ahora)
    db.session.commit()


def _guardar_direccion(cliente: GastronomiaClienteFinal, pedido: GastronomiaPedido, data: dict, ahora: datetime) -> None:
    if pedido.tipo_pedido != 'delivery' or not pedido.direccion_entrega:
        return
    direccion_normalizada = pedido.direccion_entrega.strip().lower()
    direccion = (
        GastronomiaClienteDireccion.query
        .filter_by(cliente_id=cliente.cliente_id, cliente_final_id=cliente.id_cliente_final)
        .filter(db.func.lower(GastronomiaClienteDireccion.direccion) == direccion_normalizada)
        .first()
    )
    if not direccion:
        direccion = GastronomiaClienteDireccion(
            cliente_id=cliente.cliente_id,
            cliente_final_id=cliente.id_cliente_final,
            direccion=pedido.direccion_entrega,
        )
    direccion.referencia = (data.get('referencia_entrega') or direccion.referencia or '').strip()[:120] or None
    direccion.ubicacion_url = pedido.ubicacion_entrega_url
    direccion.latitud = pedido.destino_latitud
    direccion.longitud = pedido.destino_longitud
    direccion.principal = True
    direccion.uso_count = int(direccion.uso_count or 0) + 1
    direccion.fecha_ultimo_uso = ahora
    db.session.add(direccion)


def _actualizar_favoritos(cliente: GastronomiaClienteFinal, pedido: GastronomiaPedido, ahora: datetime) -> None:
    acumulado = defaultdict(lambda: {'nombre': '', 'cantidad': 0})
    for item in pedido.items.all():
        key = int(item.producto_id)
        acumulado[key]['nombre'] = item.nombre_producto or f'Producto {key}'
        acumulado[key]['cantidad'] += int(item.cantidad or 0)
    for producto_id, data in acumulado.items():
        favorito = GastronomiaClienteFavorito.query.filter_by(
            cliente_id=cliente.cliente_id,
            cliente_final_id=cliente.id_cliente_final,
            producto_id=producto_id,
        ).first()
        if not favorito:
            favorito = GastronomiaClienteFavorito(
                cliente_id=cliente.cliente_id,
                cliente_final_id=cliente.id_cliente_final,
                producto_id=producto_id,
                nombre_producto=data['nombre'],
            )
        favorito.nombre_producto = data['nombre']
        favorito.cantidad_pedida = int(favorito.cantidad_pedida or 0) + data['cantidad']
        favorito.veces_pedido = int(favorito.veces_pedido or 0) + 1
        favorito.fecha_ultima_compra = ahora
        db.session.add(favorito)


def _perfil_dict(cliente: GastronomiaClienteFinal) -> dict:
    direcciones = (
        cliente.direcciones
        .order_by(GastronomiaClienteDireccion.fecha_ultimo_uso.desc(), GastronomiaClienteDireccion.id_direccion.desc())
        .limit(5)
        .all()
    )
    favoritos = (
        GastronomiaClienteFavorito.query
        .filter_by(cliente_id=cliente.cliente_id, cliente_final_id=cliente.id_cliente_final)
        .order_by(GastronomiaClienteFavorito.veces_pedido.desc(), GastronomiaClienteFavorito.fecha_ultima_compra.desc())
        .limit(6)
        .all()
    )
    return {
        'encontrado': True,
        'cliente': cliente.to_public_dict(),
        'direcciones': [direccion.to_public_dict() for direccion in direcciones],
        'favoritos': [favorito.to_public_dict() for favorito in favoritos],
        'ultimo_pedido': _ultimo_pedido_dict(cliente),
    }


def _ultimo_pedido_dict(cliente: GastronomiaClienteFinal) -> dict | None:
    pedido = (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente.cliente_id),
            GastronomiaPedido.cliente_final_id == int(cliente.id_cliente_final),
            GastronomiaPedido.estado != 'cancelado',
        )
        .order_by(GastronomiaPedido.fecha_creacion.desc(), GastronomiaPedido.id_pedido.desc())
        .first()
    )
    if not pedido:
        return None
    return {
        'id_pedido': pedido.id_pedido,
        'tipo_pedido': pedido.tipo_pedido,
        'total': float(pedido.total or 0),
        'fecha_creacion': pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None,
        'items': [_item_para_repetir(item) for item in pedido.items.order_by(GastronomiaPedidoItem.id_item.asc()).all()],
    }


def _item_para_repetir(item: GastronomiaPedidoItem) -> dict:
    modifiers = []
    grouped = {}
    for modifier in item.modificadores.all():
        current = grouped.setdefault(int(modifier.opcion_id), {
            'id_opcion': int(modifier.opcion_id),
            'nombre': modifier.nombre_opcion,
            'cantidad': 0,
            'precio_delta': float(modifier.precio_delta or 0),
            'nombre_grupo': modifier.nombre_grupo,
            'tipo_grupo': modifier.tipo_grupo,
        })
        current['cantidad'] += 1
    modifiers.extend(grouped.values())
    return {
        'id': int(item.producto_id),
        'nombre': item.nombre_producto,
        'precio': float(item.precio_original or item.precio_unitario or 0),
        'basePrice': float(item.precio_original or item.precio_unitario or 0),
        'quantity': int(item.cantidad or 1),
        'subtotal': float(item.subtotal or 0),
        'modifiers': modifiers,
        'customized': bool(modifiers),
    }


def _pedido_publico_dict(pedido: GastronomiaPedido) -> dict:
    seguimiento = build_public_url('gastronomia.seguimiento_pedido_publico', codigo_publico=pedido.codigo_publico)
    return {
        'id_pedido': pedido.id_pedido,
        'codigo_entrega': pedido.codigo_entrega,
        'codigo_publico': pedido.codigo_publico,
        'estado': pedido.estado,
        'tipo_pedido': pedido.tipo_pedido,
        'total': float(pedido.total or 0),
        'url_seguimiento': f'/gastronomia/pedido/{pedido.codigo_publico}' if pedido.codigo_publico else None,
        'url_seguimiento_publica': seguimiento,
    }


def whatsapp_pedido_url(telefono: str | None, pedido: dict, nombre_tienda: str | None = None) -> str | None:
    digits = ''.join(ch for ch in str(telefono or '') if ch.isdigit())
    if not digits:
        return None
    tienda = f" en {nombre_tienda}" if nombre_tienda else ''
    mensaje = f"Hola, acabo de hacer el pedido {pedido.get('codigo_entrega')}{tienda}. Total: {pedido.get('total')}"
    return f'https://wa.me/{digits}?text={quote(mensaje)}'


def _token_valido(cliente: GastronomiaClienteFinal, token: str | None) -> bool:
    return bool(token and cliente.token_publico and secrets.compare_digest(str(token), str(cliente.token_publico)))


def _parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
