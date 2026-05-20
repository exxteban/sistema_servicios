from uuid import uuid4

from app import create_app, db
from app.models import Categoria, Producto, Usuario
from app.services.ia_backoffice.response_engine import generar_respuesta_backoffice
from app.services.ia_backoffice.settings import CLAVE_ENABLED
from app.services.ia_backoffice.tool_cache import limpiar_tool_cache
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.models import Configuracion


def _crear_producto(nombre: str, categoria_nombre: str, stock: int = 3) -> Producto:
    suffix = uuid4().hex[:8]
    categoria = Categoria(nombre=f'{categoria_nombre} {suffix}', activo=True)
    db.session.add(categoria)
    db.session.flush()
    producto = Producto(
        codigo=f'IA-PROD-{suffix}',
        nombre=f'{nombre} {suffix}',
        id_categoria=categoria.id_categoria,
        precio_compra=100000,
        precio_venta=150000,
        stock_actual=stock,
        activo=True,
    )
    db.session.add(producto)
    db.session.commit()
    return producto


def test_busqueda_productos_entiende_categoria_plural():
    app = create_app('testing')

    with app.app_context():
        limpiar_tool_cache()
        admin = Usuario.query.filter_by(username='admin').first()
        producto = _crear_producto('Equipo Libre', 'Celulares')

        respuesta = ejecutar_tool_backoffice(
            'buscar_entidad_backoffice',
            {'busqueda': 'celulares', 'top_n': 10},
            usuario=admin,
        )

        codigos = {item['codigo'] for item in respuesta['data']['resultados']['productos']}
        assert producto.codigo in codigos


def test_busqueda_productos_telefonos_android_usa_sinonimos_moviles():
    app = create_app('testing')

    with app.app_context():
        limpiar_tool_cache()
        admin = Usuario.query.filter_by(username='admin').first()
        producto = _crear_producto('SAMSUNG A15 128GB', 'Equipos')

        respuesta = ejecutar_tool_backoffice(
            'buscar_entidad_backoffice',
            {'busqueda': 'telefonos android', 'top_n': 10},
            usuario=admin,
        )

        codigos = {item['codigo'] for item in respuesta['data']['resultados']['productos']}
        assert producto.codigo in codigos


def test_asistente_responde_telefonos_android_sin_api_key():
    app = create_app('testing')

    with app.app_context():
        limpiar_tool_cache()
        admin = Usuario.query.filter_by(username='admin').first()
        producto = _crear_producto('SAMSUNG A25 ANDROID', 'Equipos')
        Configuracion.establecer_bool(CLAVE_ENABLED, True)

        respuesta = generar_respuesta_backoffice(
            [{'role': 'user', 'content': 'que telefonos android hay?'}],
            admin,
        )

        assert respuesta['estado'] == 'ok'
        assert producto.codigo in respuesta['contenido']
        assert 'sin_api_key' != respuesta['estado']
