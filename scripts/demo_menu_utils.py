"""Piezas comunes de los scripts que cargan menus de demo (heladeria, cafeteria, ...).

Todo pasa por los servicios del menu, asi que se aplican las mismas validaciones
que en la pantalla. Se busca por nombre para poder correr el script varias veces.
"""
import argparse
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def slug(texto: str) -> str:
    plano = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', plano.lower()).strip('_')


def ejecutar(descripcion: str, cargar) -> None:
    """Parsea los argumentos comunes y llama `cargar(cliente_id, imagen)` dentro de la app.

    `imagen(prefijo, nombre, dibujar)` dibuja (salvo --sin-imagenes) y devuelve la URL /static/...
    """
    parser = argparse.ArgumentParser(description=descripcion)
    parser.add_argument('--cliente-id', type=int)
    parser.add_argument('--sin-imagenes', action='store_true', help='No dibuja imagenes (reusa las URLs).')
    args = parser.parse_args()

    from app import create_app
    from gastronomia.services.menu_image_service import GASTRONOMIA_MENU_UPLOAD_ROOT

    app = create_app()
    with app.app_context():
        cliente_id = _resolver_cliente_id(args.cliente_id)

        def imagen(prefijo, nombre, dibujar):
            partes = [*GASTRONOMIA_MENU_UPLOAD_ROOT, str(cliente_id), f'{prefijo}_{slug(nombre)}.webp']
            if not args.sin_imagenes:
                dibujar(os.path.join(app.static_folder, *partes))
            return '/static/' + '/'.join(partes)

        cargar(cliente_id, imagen)


def _resolver_cliente_id(cliente_id):
    from gastronomia.models import GastronomiaClienteConfig

    if cliente_id:
        return int(cliente_id)
    configs = GastronomiaClienteConfig.query.filter_by(gastronomia_activo=True).all()
    if len(configs) != 1:
        ids = ', '.join(str(c.cliente_id) for c in configs) or 'ninguno'
        raise SystemExit(f'Indica --cliente-id (clientes con gastronomia activa: {ids}).')
    return int(configs[0].cliente_id)


def asegurar_categoria(cliente_id, nombre, orden):
    """Reusa la categoria si existe (aunque este borrada); `orden` solo se usa al crearla."""
    from app import db
    from gastronomia.models import GastronomiaCategoria
    from gastronomia.services.menu_service import guardar_categoria

    categoria = GastronomiaCategoria.query.filter(
        GastronomiaCategoria.cliente_id == cliente_id,
        db.func.lower(GastronomiaCategoria.nombre) == nombre.lower(),
    ).first()
    if categoria is None:
        return guardar_categoria(cliente_id, {'nombre': nombre, 'orden': orden, 'visible': True})
    categoria.activo = True
    categoria.visible = True
    db.session.commit()
    return categoria


def guardar_producto_demo(cliente_id, categoria, data, *, conservar_precio=False):
    """Crea o actualiza por nombre. Con `conservar_precio`, un producto existente mantiene su precio."""
    from app import db
    from gastronomia.models import GastronomiaProducto
    from gastronomia.services.menu_service import guardar_producto

    existente = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == cliente_id,
        db.func.lower(GastronomiaProducto.nombre) == data['nombre'].lower(),
    ).first()
    payload = {**data, 'categoria_id': categoria.id_categoria}
    if existente is not None:
        existente.activo = True
        payload['nombre'] = existente.nombre
        if conservar_precio and existente.precio:
            payload['precio'] = existente.precio
    return guardar_producto(cliente_id, payload, producto=existente)


def guardar_grupo_demo(cliente_id, producto, grupo_data, opciones):
    """Grupo de opciones por nombre; `opciones`: dicts con nombre, precio_delta e imagen_url opcional."""
    from gastronomia.models import GastronomiaGrupoOpciones, GastronomiaOpcionProducto
    from gastronomia.services.modificadores_service import guardar_grupo, guardar_opcion

    grupo = GastronomiaGrupoOpciones.query.filter_by(
        cliente_id=cliente_id, producto_id=producto.id_producto, nombre=grupo_data['nombre'],
    ).first()
    if grupo is not None:
        grupo.activo = True
    grupo = guardar_grupo(cliente_id, producto.id_producto, grupo_data, grupo=grupo)
    existentes = {o.nombre: o for o in GastronomiaOpcionProducto.query.filter_by(cliente_id=cliente_id, grupo_id=grupo.id_grupo)}
    for orden, opcion_data in enumerate(opciones):
        opcion = existentes.get(opcion_data['nombre'])
        if opcion is not None:
            opcion.activo = True
        guardar_opcion(cliente_id, grupo.id_grupo, {'precio_delta': 0, **opcion_data, 'orden': orden}, opcion=opcion)
    return grupo
