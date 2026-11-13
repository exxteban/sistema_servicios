"""Tools de escritura del asistente: reutilizan los servicios existentes del modulo."""
from __future__ import annotations

import secrets
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app import db
from app.models.producto import Categoria, Producto
from gastronomia.services.asistente import combinar, resolver
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
        existente = resolver.categoria(cliente_id, data.get('nombre'), exacto=True)
        if existente:
            return {'id_categoria': existente.id_categoria, 'nombre': existente.nombre, 'ya_existia': True}
        cat = guardar_categoria(cliente_id, {'visible': True, **data})
        return {'id_categoria': cat.id_categoria, 'nombre': cat.nombre}
    return _con_resultados(_lote(args, 'categorias'), _uno)


def plato_existente(cliente_id: int, item: dict):
    """Plato a editar: por id (y el nombre, si viene, debe coincidir) o por nombre exacto.

    Evita que un id equivocado de la IA renombre y pise otro plato: renombrar exige nuevo_nombre.
    """
    if item.get('id_producto') not in (None, ''):
        existente = resolver.plato_para_escribir(cliente_id, item['id_producto'])
        if item.get('nombre') and resolver.normalizar(item['nombre']) != resolver.normalizar(existente.nombre):
            raise ValueError(
                f"El id {item['id_producto']} es el plato '{existente.nombre}', no '{item['nombre']}'. "
                'Para renombrar usa nuevo_nombre; si es otro plato, no mandes id_producto.'
            )
        return existente
    return resolver.plato(cliente_id, item.get('nombre'), exacto=True)


def categoria_de_plato(cliente_id: int, item: dict, existente):
    if item.get('categoria'):
        return resolver.categoria_para_escribir(cliente_id, item['categoria'])
    if existente:
        return existente.categoria
    raise ValueError(f"Falta la categoria del plato nuevo '{item.get('nombre')}'.")


def guardar_platos(cliente_id: int, args: dict) -> dict:
    """Crea o edita platos. Si existe uno con el mismo nombre exacto, lo actualiza."""
    def _uno(item):
        existente = plato_existente(cliente_id, item)
        categoria = categoria_de_plato(cliente_id, item, existente)
        nombre = str(item.get('nuevo_nombre') or item.get('nombre') or (existente.nombre if existente else '')).strip()
        if not nombre:
            raise ValueError('El plato necesita nombre.')
        data = {
            'nombre': nombre,
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
    plato = resolver.plato_para_escribir(cliente_id, args.get('plato'))
    data = {k: args[k] for k in ('precio', 'disponible', 'visible', 'publicado_tienda') if k in args}
    if 'precio' in data:
        data['precio'] = _monto(data['precio'])
    actualizar_estado_producto(cliente_id, plato.id_producto, data)
    if 'costo_extra' in args:
        guardar_costo_extra(cliente_id, plato.id_producto, _monto(args['costo_extra']))
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
        existente = resolver.insumo(cliente_id, nombre, exacto=True)
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
    """Agrega/actualiza, quita o reemplaza ingredientes de la receta (cantidad en la unidad del insumo)."""
    plato = resolver.plato_para_escribir(cliente_id, args.get('plato'))
    modo = combinar.modo(args)
    pedido, faltantes, invalidas = {}, [], []
    for fila in _lote(args, 'ingredientes'):
        fila = fila if isinstance(fila, dict) else {'insumo': fila}
        insumo = resolver.insumo(cliente_id, fila.get('insumo'), exacto=True)
        if not insumo:
            faltantes.append(fila.get('insumo'))
            continue
        if modo == 'quitar':
            pedido[insumo.id_producto] = 0
            continue
        try:
            pedido[insumo.id_producto] = combinar.cantidad_receta(fila.get('cantidad'), insumo)
        except ValueError as exc:
            invalidas.append(str(exc))
    if faltantes:
        return {'error': 'Insumos inexistentes, crealos primero con guardar_insumos.', 'faltantes': faltantes}
    if invalidas:
        return {'error': 'Cantidades invalidas, no se guardo nada.', 'detalle': invalidas}
    actual = obtener_receta(cliente_id, plato.id_producto)
    previos = {i['insumo_id']: i['cantidad'] for i in actual['items']}
    final = combinar.combinar(previos, pedido, modo)
    items = [{'insumo_id': k, 'cantidad': v} for k, v in final.items()]
    opciones = [
        {'opcion_id': o['opcion_id'], 'insumo_id': o['insumo_id'], 'cantidad_delta': o['cantidad_delta']}
        for o in actual.get('opciones', [])
    ]
    receta = guardar_receta(cliente_id, plato.id_producto, {'items': items, 'opciones': opciones})
    return {'plato': plato.nombre, 'modo': modo,
            'ingredientes': [(i['insumo_nombre'], i['cantidad'], i['unidad_stock']) for i in receta['items']]}


def _nombre_item(item) -> str:
    return str((item.get('nombre') if isinstance(item, dict) else item) or '').strip()


def configurar_extras_plato(cliente_id: int, args: dict) -> dict:
    plato = resolver.plato_para_escribir(cliente_id, args.get('plato'))
    modo = combinar.modo(args)
    hecho = {'modo': modo}
    if 'adicionales' in args:
        pedido = {
            resolver.normalizar(_nombre_item(a)): (_nombre_item(a), a.get('precio') if isinstance(a, dict) else 0)
            for a in _lote(args, 'adicionales') if _nombre_item(a)
        }
        final = combinar.combinar(combinar.adicionales_actuales(cliente_id, plato.id_producto), pedido, modo)
        lineas = [f'{nombre}|{_monto(precio)}' for nombre, precio in final.values()]
        sincronizar_adicionales_precio(cliente_id, plato.id_producto, lineas)
        hecho['adicionales'] = [nombre for nombre, _ in final.values()]
    if 'quitables' in args:
        actuales = combinar.quitables_actuales(cliente_id, plato.id_producto)
        pedido = {}
        for q in _lote(args, 'quitables'):
            nombre = _nombre_item(q)
            if nombre:
                clave = resolver.normalizar(nombre)
                pedido[clave] = (nombre, actuales.get(clave, (nombre, 0))[1])
        final = combinar.combinar(actuales, pedido, modo)
        sincronizar_ingredientes_removibles(
            cliente_id, plato.id_producto,
            [{'nombre': nombre, 'descuento': _monto(descuento)} for nombre, descuento in final.values()],
        )
        hecho['quitables'] = [nombre for nombre, _ in final.values()]
    return {'plato': plato.nombre, **hecho}


MAX_MESAS = 50


def plan_mesas(cliente_id: int, args: dict) -> tuple[list[tuple[str, int]], int]:
    """[(nombre, orden)] de las mesas a crear y su capacidad; lo usa tambien la vista previa."""
    cantidad = max(1, min(MAX_MESAS, int(args.get('cantidad') or 1)))
    prefijo = str(args.get('prefijo') or 'Mesa').strip()[:20] or 'Mesa'
    capacidad = max(1, min(50, int(args.get('capacidad') or 4)))
    existentes = {m.nombre.lower() for m in listar_mesas(cliente_id, incluir_inactivas=True)}
    plan, numero = [], max(1, int(args.get('desde_numero') or 1))
    while len(plan) < cantidad and numero < 1000:
        nombre = f'{prefijo} {numero}'
        numero += 1
        if nombre.lower() not in existentes:
            plan.append((nombre, numero))
    return plan, capacidad


def crear_mesas(cliente_id: int, args: dict) -> dict:
    plan, capacidad = plan_mesas(cliente_id, args)
    for nombre, orden in plan:
        guardar_mesa(cliente_id, {'nombre': nombre, 'capacidad': capacidad,
                                  'ubicacion': str(args.get('ubicacion') or '')[:80], 'orden': orden})
    return {'creadas': [nombre for nombre, _ in plan]}


TOOLS_ESCRITURA = {
    'crear_categorias': crear_categorias,
    'guardar_platos': guardar_platos,
    'cambiar_estado_plato': cambiar_estado_plato,
    'guardar_insumos': guardar_insumos,
    'guardar_receta_plato': guardar_receta_plato,
    'configurar_extras_plato': configurar_extras_plato,
    'crear_mesas': crear_mesas,
}
