"""Tools de escritura del asistente: reutilizan los servicios existentes del modulo."""
from __future__ import annotations

import secrets
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app import db
from app.models.producto import Categoria, Producto
from gastronomia.services.asistente import resolver
from gastronomia.services.costos_service import guardar_costo_extra, guardar_precio_compra_insumo
from gastronomia.services.menu_service import (
    actualizar_estado_producto,
    guardar_categoria,
    guardar_producto,
    parse_price,
)
from gastronomia.services.modificadores_service import (
    sincronizar_adicionales_precio,
    sincronizar_ingredientes_removibles,
)
from gastronomia.services.salon_service import guardar_mesa, listar_mesas
from gastronomia.services.stock_service import UNIDADES_STOCK, guardar_receta, obtener_receta, registrar_entrada
from gastronomia.stock_models import GastronomiaOpcionInsumo, GastronomiaRecetaInsumo

CATEGORIA_INSUMOS = 'Insumos gastronomia'
MAX_LOTE = 60


def _monto(valor, defecto=0) -> str:
    """Numero de la IA -> texto seguro para parse_price.

    parse_price toma '1.125' como separador de miles (1125). La IA manda numeros JSON
    (0.125 = 0,125), asi que se fijan a 2 decimales antes: '0.13' ya no es ambiguo.
    """
    if valor is None or valor == '':
        valor = defecto
    if isinstance(valor, bool):
        raise ValueError('Monto invalido.')
    if isinstance(valor, (int, float, Decimal)):
        try:
            return str(Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        except InvalidOperation as exc:
            raise ValueError('Monto invalido.') from exc
    return str(valor)


def _lote(args: dict, clave: str) -> list:
    items = args.get(clave)
    if isinstance(items, dict):
        items = [items]
    return list(items or [])[:MAX_LOTE]


def _con_resultados(items, fn) -> dict:
    """Ejecuta fn por item; un error no corta el resto del lote."""
    ok, errores = [], []
    for item in items:
        try:
            ok.append(fn(item))
        except (ValueError, TypeError, AttributeError) as exc:
            db.session.rollback()
            mensaje = str(exc) if isinstance(exc, ValueError) else 'Formato invalido para este elemento.'
            errores.append({'item': item.get('nombre') if isinstance(item, dict) else item, 'error': mensaje})
    return {'hechos': ok, 'errores': errores}


def crear_categorias(cliente_id: int, args: dict) -> dict:
    def _uno(item):
        data = item if isinstance(item, dict) else {'nombre': item}
        existente = resolver.categoria(cliente_id, data.get('nombre'))
        if existente and resolver.normalizar(existente.nombre) == resolver.normalizar(data.get('nombre')):
            return {'id_categoria': existente.id_categoria, 'nombre': existente.nombre, 'ya_existia': True}
        cat = guardar_categoria(cliente_id, {'visible': True, **data})
        return {'id_categoria': cat.id_categoria, 'nombre': cat.nombre}
    return _con_resultados(_lote(args, 'categorias'), _uno)


def guardar_platos(cliente_id: int, args: dict) -> dict:
    """Crea o edita platos. Si existe uno con el mismo nombre, lo actualiza."""
    def _uno(item):
        categoria = resolver.categoria(cliente_id, item.get('categoria'))
        if item.get('categoria') and not categoria:
            raise ValueError(f"Categoria '{item.get('categoria')}' no existe. Creala primero.")
        existente = resolver.plato(cliente_id, item.get('id_producto') or item.get('nombre'))
        if existente and item.get('id_producto') is None and resolver.normalizar(existente.nombre) != resolver.normalizar(item.get('nombre')):
            existente = None
        if not categoria and existente:
            categoria = existente.categoria
        if not categoria:
            raise ValueError(f"Categoria '{item.get('categoria')}' no existe. Creala primero.")
        data = {
            'nombre': item.get('nombre') or (existente.nombre if existente else ''),
            'categoria_id': categoria.id_categoria,
            'descripcion': item.get('descripcion', existente.descripcion if existente else ''),
            'precio': _monto(item.get('precio'), existente.precio if existente else 0),
            'disponible': item.get('disponible', existente.disponible if existente else True),
            'visible': existente.visible if existente else True,
            'imagen_url': existente.imagen_url if existente else '',
            'orden': existente.orden if existente else 0,
        }
        if existente:
            data['control_stock_venta'] = existente.control_stock_venta
            data['stock_disponible'] = existente.stock_disponible
        plato = guardar_producto(cliente_id, data, existente)
        return {'id_producto': plato.id_producto, 'nombre': plato.nombre, 'precio': float(plato.precio),
                'actualizado': bool(existente)}
    return _con_resultados(_lote(args, 'platos'), _uno)


def cambiar_estado_plato(cliente_id: int, args: dict) -> dict:
    plato = resolver.plato(cliente_id, args.get('plato'))
    if not plato:
        return {'error': 'Plato no encontrado.'}
    data = {k: args[k] for k in ('precio', 'disponible', 'visible', 'publicado_tienda') if k in args}
    if 'precio' in data:
        data['precio'] = _monto(data['precio'])
    actualizar_estado_producto(cliente_id, plato.id_producto, data)
    if 'costo_extra' in args:
        guardar_costo_extra(cliente_id, plato.id_producto, args['costo_extra'])
    return {'id_producto': plato.id_producto, 'nombre': plato.nombre, 'cambios': list(data) + (['costo_extra'] if 'costo_extra' in args else [])}


def _categoria_insumos() -> Categoria:
    cat = Categoria.query.filter_by(nombre=CATEGORIA_INSUMOS).first()
    if not cat:
        cat = Categoria(nombre=CATEGORIA_INSUMOS, descripcion='Creada por el asistente IA', activo=True)
        db.session.add(cat)
        db.session.flush()
    return cat


def _codigo_insumo() -> str:
    while True:
        codigo = f'INS-{secrets.token_hex(3).upper()}'
        if not Producto.query.filter_by(codigo=codigo).first():
            return codigo


def _insumo_en_uso(cliente_id: int, insumo) -> bool:
    if int(insumo.stock_actual or 0):
        return True
    filtro = {'cliente_id': int(cliente_id), 'insumo_id': int(insumo.id_producto), 'activo': True}
    return bool(
        GastronomiaRecetaInsumo.query.filter_by(**filtro).first()
        or GastronomiaOpcionInsumo.query.filter_by(**filtro).first()
    )


def guardar_insumos(cliente_id: int, args: dict, usuario_id: int | None = None) -> dict:
    """Crea insumos (productos de stock) o actualiza unidad/minimo/precio de compra."""
    def _uno(item):
        nombre = str(item.get('nombre') or '').strip()[:200]
        if not nombre:
            raise ValueError('El insumo necesita nombre.')
        unidad = str(item.get('unidad') or 'unidad').strip().lower()
        if unidad not in UNIDADES_STOCK:
            raise ValueError(f"Unidad '{unidad}' invalida. Usa: {', '.join(sorted(UNIDADES_STOCK))}.")
        existente = resolver.insumo(cliente_id, nombre)
        if existente and resolver.normalizar(existente.nombre) != resolver.normalizar(nombre):
            existente = None
        if existente:
            if item.get('unidad') and unidad != (existente.unidad_stock or 'unidad'):
                if _insumo_en_uso(cliente_id, existente):
                    raise ValueError(
                        f"'{existente.nombre}' ya se usa en recetas o tiene stock en '{existente.unidad_stock}'. "
                        'Cambiar la unidad cambiaria las cantidades: hacelo a mano o crea otro insumo.'
                    )
                existente.unidad_stock = unidad
            if item.get('stock_minimo') is not None:
                existente.stock_minimo = max(0, int(item['stock_minimo']))
            db.session.commit()
            if item.get('precio_compra') is not None:
                guardar_precio_compra_insumo(cliente_id, existente.id_producto, _monto(item['precio_compra']))
            return {'id_insumo': existente.id_producto, 'nombre': existente.nombre, 'actualizado': True}
        insumo = Producto(
            codigo=_codigo_insumo(),
            nombre=nombre,
            id_categoria=_categoria_insumos().id_categoria,
            id_cliente=int(cliente_id),
            precio_compra=parse_price(_monto(item.get('precio_compra'))),
            precio_venta=Decimal('0'),
            stock_actual=0,
            stock_minimo=max(0, int(item.get('stock_minimo') or 0)),
            unidad_stock=unidad,
            es_servicio=False,
            activo=True,
            id_usuario_modificacion=usuario_id,
        )
        db.session.add(insumo)
        db.session.commit()
        inicial = max(0, int(item.get('stock_inicial') or 0))
        if inicial:
            # Como entrada de stock: queda el movimiento en el historial de inventario.
            registrar_entrada(cliente_id, usuario_id, insumo.id_producto, {'cantidad': inicial})
        return {'id_insumo': insumo.id_producto, 'nombre': insumo.nombre, 'unidad': unidad, 'stock_inicial': inicial}
    return _con_resultados(_lote(args, 'insumos'), _uno)


def guardar_receta_plato(cliente_id: int, args: dict) -> dict:
    """Reemplaza la receta completa del plato (insumo + cantidad en su unidad)."""
    plato = resolver.plato(cliente_id, args.get('plato'))
    if not plato:
        return {'error': 'Plato no encontrado.'}
    items, faltantes = [], []
    for fila in _lote(args, 'ingredientes'):
        insumo = resolver.insumo(cliente_id, fila.get('insumo'))
        if not insumo:
            faltantes.append(fila.get('insumo'))
            continue
        items.append({'insumo_id': insumo.id_producto, 'cantidad': int(round(float(fila.get('cantidad') or 0)))})
    if faltantes:
        return {'error': 'Insumos inexistentes, crealos primero con guardar_insumos.', 'faltantes': faltantes}
    actual = obtener_receta(cliente_id, plato.id_producto)
    opciones = [
        {'opcion_id': o['opcion_id'], 'insumo_id': o['insumo_id'], 'cantidad_delta': o['cantidad_delta']}
        for o in actual.get('opciones', [])
    ]
    receta = guardar_receta(cliente_id, plato.id_producto, {'items': items, 'opciones': opciones})
    return {'plato': plato.nombre, 'ingredientes': [(i['insumo_nombre'], i['cantidad'], i['unidad_stock']) for i in receta['items']]}


def configurar_extras_plato(cliente_id: int, args: dict) -> dict:
    plato = resolver.plato(cliente_id, args.get('plato'))
    if not plato:
        return {'error': 'Plato no encontrado.'}
    hecho = {}
    if 'adicionales' in args:
        lineas = [f"{a.get('nombre')}|{_monto(a.get('precio'))}" for a in _lote(args, 'adicionales') if isinstance(a, dict)]
        sincronizar_adicionales_precio(cliente_id, plato.id_producto, lineas)
        hecho['adicionales'] = len(lineas)
    if 'quitables' in args:
        nombres = [str(n) for n in _lote(args, 'quitables')]
        sincronizar_ingredientes_removibles(cliente_id, plato.id_producto, nombres)
        hecho['quitables'] = len(nombres)
    return {'plato': plato.nombre, **hecho}


def crear_mesas(cliente_id: int, args: dict) -> dict:
    cantidad = max(1, min(100, int(args.get('cantidad') or 1)))
    prefijo = str(args.get('prefijo') or 'Mesa').strip()[:20]
    capacidad = int(args.get('capacidad') or 4)
    existentes = {m.nombre.lower() for m in listar_mesas(cliente_id, incluir_inactivas=True)}
    creadas, numero = [], int(args.get('desde_numero') or 1)
    while len(creadas) < cantidad and numero < 1000:
        nombre = f'{prefijo} {numero}'
        numero += 1
        if nombre.lower() in existentes:
            continue
        guardar_mesa(cliente_id, {'nombre': nombre, 'capacidad': capacidad,
                                  'ubicacion': args.get('ubicacion') or '', 'orden': numero})
        creadas.append(nombre)
    return {'creadas': creadas}


TOOLS_ESCRITURA = {
    'crear_categorias': crear_categorias,
    'guardar_platos': guardar_platos,
    'cambiar_estado_plato': cambiar_estado_plato,
    'guardar_insumos': guardar_insumos,
    'guardar_receta_plato': guardar_receta_plato,
    'configurar_extras_plato': configurar_extras_plato,
    'crear_mesas': crear_mesas,
}
