import json
import unittest
from datetime import datetime, timedelta

from app import create_app, db
from app.models import (
    Categoria,
    Cliente,
    Producto,
    TiendaConfig,
    TiendaPromocion,
    TiendaPromocionProducto,
    Usuario,
)
from app.models.whatsapp import WhatsAppConfiguracion
from app.services.asistente.context_builder import build_store_assistant_context
from app.services.bot_context import BOT_CONTEXT_CONFIG_KEY, load_bot_context
from app.services.ia.tool_handlers import _handle_obtener_faq


def _login_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def _save_bot_context(payload: dict):
    config = WhatsAppConfiguracion.query.filter_by(clave=BOT_CONTEXT_CONFIG_KEY).first()
    if config is None:
        config = WhatsAppConfiguracion(
            clave=BOT_CONTEXT_CONFIG_KEY,
            valor='{}',
            descripcion='Contexto de prueba',
            categoria='general',
        )
        db.session.add(config)
    config.valor = json.dumps(payload, ensure_ascii=False)
    db.session.commit()


def _ensure_store(slug='bot-context-store'):
    config = TiendaConfig.query.filter_by(slug=slug).first()
    if config:
        return config

    cliente = Cliente.query.filter_by(nombre=f'Cliente {slug}').first()
    if cliente is None:
        cliente = Cliente(nombre=f'Cliente {slug}', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.commit()

    config = TiendaConfig(
        id_cliente=cliente.id_cliente,
        slug=slug,
        nombre_tienda='Tienda Base',
        activa=True,
        telefono_whatsapp='595981000000',
    )
    db.session.add(config)
    db.session.commit()
    return config


def _ensure_categoria(nombre='Categoria Bot Context'):
    categoria = Categoria.query.filter_by(nombre=nombre).first()
    if categoria:
        return categoria
    categoria = Categoria(nombre=nombre, activo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _ensure_producto(config, codigo='CTX-001', nombre='Producto Contexto'):
    producto = Producto.query.filter_by(codigo=codigo).first()
    if producto:
        return producto
    producto = Producto(
        codigo=codigo,
        nombre=nombre,
        descripcion='Producto de prueba para contexto.',
        id_categoria=_ensure_categoria().id_categoria,
        id_cliente=config.id_cliente,
        precio_compra=10000,
        precio_venta=25000,
        porcentaje_iva=10,
        stock_actual=10,
        stock_minimo=1,
        activo=True,
        publicado_tienda=True,
        es_servicio=False,
    )
    db.session.add(producto)
    db.session.commit()
    return producto


def _ensure_promocion(config, producto, nombre='Promo Contexto Bot'):
    promocion = TiendaPromocion.query.filter_by(
        id_cliente=config.id_cliente,
        nombre=nombre,
    ).first()
    now = datetime.utcnow()
    if promocion is None:
        promocion = TiendaPromocion(
            id_cliente=config.id_cliente,
            nombre=nombre,
            tipo='porcentaje',
            valor=15,
            fecha_inicio=now - timedelta(hours=1),
            fecha_fin=now + timedelta(days=1),
            activa=True,
        )
        db.session.add(promocion)

    promocion.descripcion_corta = 'Descuento especial visible para el bot.'
    promocion.tipo = 'porcentaje'
    promocion.valor = 15
    promocion.fecha_inicio = now - timedelta(hours=1)
    promocion.fecha_fin = now + timedelta(days=1)
    promocion.activa = True
    promocion.productos_rel[:] = [
        TiendaPromocionProducto(id_producto=producto.id_producto),
    ]
    db.session.commit()
    return promocion


class TestCrmBotContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def setUp(self):
        self.client = self.app.test_client()

    def test_api_bot_contexto_guarda_campos_minimos(self):
        _login_admin(self.client, self.app)

        payload = {
            'nombre_negocio': 'Silvio Cell',
            'descripcion_negocio': 'Reparacion y venta de celulares.',
            'direccion': 'Av. Siempre Viva 123',
            'telefonos_contacto': '0981 111111',
            'horarios_atencion': 'Lunes a sabados de 8:00 a 18:00',
            'formas_de_pago': 'Efectivo y transferencia',
            'zonas_de_entrega': 'Asuncion y San Lorenzo',
            'politica_cambios': 'Cambios dentro de 48 hs con ticket.',
            'cuando_derivar_a_humano': 'Reclamos o pagos no registrados.',
            'tono_respuesta': 'Amable, breve y claro.',
            'contexto_extra': 'No prometer entregas en el dia sin confirmacion humana.',
        }

        response = self.client.put('/crm/api/admin/bot_contexto', json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['contexto']['nombre_negocio'], 'Silvio Cell')
        self.assertEqual(data['contexto']['politica_cambios'], 'Cambios dentro de 48 hs con ticket.')

        contexto = load_bot_context()
        self.assertEqual(contexto['horarios_atencion'], 'Lunes a sabados de 8:00 a 18:00')
        self.assertEqual(contexto['cuando_derivar_a_humano'], 'Reclamos o pagos no registrados.')

    def test_context_builder_incluye_contexto_bot_y_faq(self):
        _save_bot_context({
            'nombre_negocio': 'Silvio Cell',
            'direccion': 'Av. Siempre Viva 123',
            'telefonos_contacto': '0981 111111',
            'horarios_atencion': 'Lunes a sabados de 8:00 a 18:00',
            'formas_de_pago': 'Efectivo y transferencia',
            'zonas_de_entrega': 'Asuncion y San Lorenzo',
            'politica_cambios': 'Cambios dentro de 48 hs con ticket.',
            'descripcion_negocio': '',
            'cuando_derivar_a_humano': '',
            'tono_respuesta': '',
            'contexto_extra': '',
        })
        config = _ensure_store()

        assistant_context = build_store_assistant_context(config)

        self.assertEqual(assistant_context['tienda']['nombre'], 'Silvio Cell')
        self.assertEqual(assistant_context['contexto_bot']['direccion'], 'Av. Siempre Viva 123')
        self.assertEqual(assistant_context['faq']['horarios'], 'Lunes a sabados de 8:00 a 18:00')
        self.assertEqual(assistant_context['faq']['contacto'], '0981 111111')
        self.assertEqual(assistant_context['faq']['politica_cambios'], 'Cambios dentro de 48 hs con ticket.')

    def test_obtener_faq_usa_nuevos_campos_del_contexto_bot(self):
        _save_bot_context({
            'nombre_negocio': '',
            'descripcion_negocio': '',
            'direccion': 'Av. Siempre Viva 123',
            'telefonos_contacto': '0981 111111 / 021 222222',
            'horarios_atencion': 'Lunes a viernes de 9:00 a 18:00',
            'formas_de_pago': 'Efectivo, transferencia y QR',
            'zonas_de_entrega': 'Asuncion, Luque y San Lorenzo',
            'politica_cambios': 'Cambios con ticket dentro de 72 hs.',
            'cuando_derivar_a_humano': '',
            'tono_respuesta': '',
            'contexto_extra': '',
        })

        respuesta_contacto = _handle_obtener_faq({'tema': 'contacto'}, {})
        respuesta_todos = _handle_obtener_faq({'tema': 'todos'}, {})

        self.assertEqual(respuesta_contacto['faq']['contacto'], '0981 111111 / 021 222222')
        self.assertEqual(respuesta_todos['faq']['zonas_de_entrega'], 'Asuncion, Luque y San Lorenzo')
        self.assertEqual(respuesta_todos['faq']['politica_cambios'], 'Cambios con ticket dentro de 72 hs.')

    def test_context_builder_incluye_promociones_activas(self):
        config = _ensure_store(slug='bot-context-promo')
        producto = _ensure_producto(config, codigo='CTX-PROMO-1', nombre='Soporte magnético')
        _ensure_promocion(config, producto, nombre='Promo Bot Contexto')

        assistant_context = build_store_assistant_context(config)

        self.assertEqual(len(assistant_context['promociones_activas']), 1)
        promocion = assistant_context['promociones_activas'][0]
        self.assertEqual(promocion['nombre'], 'Promo Bot Contexto')
        self.assertEqual(promocion['productos'][0]['nombre'], 'Soporte magnético')


if __name__ == '__main__':
    unittest.main()
