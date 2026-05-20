import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app, db
from app.models import Categoria, Cliente, Producto, TiendaConfig
from app.services.asistente.context_builder import build_store_assistant_context
from app.services.asistente.prompt_builder import build_web_bot_prompt
from app.services.ia.gpt_service import MAX_HISTORY_MESSAGES, _construir_mensajes
from app.services.asistente.tools_adapter import execute_web_tool


def _ensure_cliente(nombre='Cliente Truth'):
    cliente = Cliente.query.filter_by(nombre=nombre).first()
    if cliente:
        return cliente
    cliente = Cliente(nombre=nombre, tipo='minorista', activo=True)
    db.session.add(cliente)
    db.session.commit()
    return cliente


def _ensure_categoria(nombre='Accesorios Truth'):
    categoria = Categoria.query.filter_by(nombre=nombre).first()
    if categoria:
        return categoria
    categoria = Categoria(nombre=nombre, activo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _ensure_store(slug='truth-demo'):
    config = TiendaConfig.query.filter_by(slug=slug).first()
    if config:
        return config
    cliente = _ensure_cliente(nombre=f'Cliente {slug}')
    config = TiendaConfig(
        id_cliente=cliente.id_cliente,
        slug=slug,
        nombre_tienda='Tienda Verdad',
        activa=True,
        telefono_whatsapp='595981111111',
        email_contacto='demo@tienda.test',
        sitio_web='https://demo.tienda.test',
        instagram_url='https://instagram.com/demo',
        facebook_url='https://facebook.com/demo',
        mostrar_horarios=True,
        texto_horarios='Lunes a domingo de 6:00 a 23:00',
        mostrar_envios=True,
        texto_envios='Hacemos envíos dentro del día en Asunción y Central.',
        mostrar_retiro_local=True,
        texto_retiro_local='Podés retirar en el local con coordinación previa.',
        mostrar_garantia=True,
        texto_garantia='Garantía de 30 días por fallas de fábrica.',
        mostrar_cobertura=True,
        texto_cobertura='Cobertura en Asunción, San Lorenzo y Luque.',
    )
    db.session.add(config)
    db.session.commit()
    return config


def _ensure_producto(config, codigo='TRUTH-001', nombre='Auricular Truth', stock=7, precio=150):
    producto = Producto.query.filter_by(codigo=codigo).first()
    if producto:
        return producto
    categoria = _ensure_categoria()
    producto = Producto(
        codigo=codigo,
        nombre=nombre,
        descripcion='Producto para tools de verdad.',
        id_categoria=categoria.id_categoria,
        id_cliente=config.id_cliente,
        precio_compra=100,
        precio_venta=precio,
        porcentaje_iva=10,
        stock_actual=stock,
        stock_minimo=2,
        activo=True,
        publicado_tienda=True,
        es_servicio=False,
        marca='Demo',
        modelo='T1',
    )
    db.session.add(producto)
    db.session.commit()
    return producto


class TestStoreTruthTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app.config['TIMEZONE'] = 'America/Asuncion'
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        cls.ctx.pop()

    def _contexto(self, config):
        assistant_context = build_store_assistant_context(config, metadata={})
        assistant_context['contexto_bot'].update({
            'telefonos_contacto': '0981 111111 / 021 222222',
            'direccion': 'Av. Demo 1234, Asunción',
            'formas_de_pago': 'Efectivo, transferencia, tarjeta y QR',
            'zonas_de_entrega': 'Asunción y Central',
            'politica_cambios': 'Cambios dentro de 48 hs con ticket.',
        })
        assistant_context['faq'].update({
            'contacto': '0981 111111 / 021 222222',
            'ubicacion': 'Av. Demo 1234, Asunción',
            'metodos_pago': 'Efectivo, transferencia, tarjeta y QR',
            'zonas_de_entrega': 'Asunción y Central',
            'politica_cambios': 'Cambios dentro de 48 hs con ticket.',
        })
        return {
            'config': config,
            'slug': config.slug,
            'assistant_context': assistant_context,
        }

    def test_obtener_fecha_hora_actual_devuelve_fecha_real(self):
        config = _ensure_store('truth-time')
        contexto = self._contexto(config)
        fixed_now = datetime(2026, 4, 4, 22, 33, tzinfo=ZoneInfo('America/Asuncion'))

        with patch('app.services.asistente.store_truth_tools._now_local', return_value=fixed_now):
            result = execute_web_tool('obtener_fecha_hora_actual', {}, contexto)

        self.assertEqual(result['fecha'], '2026-04-04')
        self.assertEqual(result['hora'], '22:33')
        self.assertEqual(result['dia_semana'], 'sábado')
        self.assertEqual(result['fecha_larga'], '4 de abril de 2026')

    def test_obtener_estado_tienda_actual_evalua_abierta_y_manana(self):
        config = _ensure_store('truth-hours')
        contexto = self._contexto(config)
        fixed_now = datetime(2026, 4, 4, 22, 33, tzinfo=ZoneInfo('America/Asuncion'))

        with patch('app.services.asistente.store_truth_tools._now_local', return_value=fixed_now):
            actual = execute_web_tool('obtener_estado_tienda_actual', {'referencia': 'ahora'}, contexto)
            manana = execute_web_tool('obtener_estado_tienda_actual', {'referencia': 'mañana'}, contexto)

        self.assertTrue(actual['abierta'])
        self.assertEqual(actual['abre'], '06:00')
        self.assertEqual(actual['cierra'], '23:00')
        self.assertIsNone(manana['abierta'])
        self.assertTrue(manana['aplica_ese_dia'])
        self.assertEqual(manana['dia_semana'], 'domingo')

    def test_tools_precisas_de_precio_y_stock(self):
        config = _ensure_store('truth-products')
        _ensure_producto(config, codigo='TRUTH-PROD', nombre='Cargador Turbo Demo', stock=9, precio=199)
        contexto = self._contexto(config)

        precio = execute_web_tool('obtener_precio_preciso_producto', {'busqueda': 'cargador turbo'}, contexto)
        stock = execute_web_tool('obtener_stock_preciso_producto', {'busqueda': 'cargador turbo'}, contexto)

        self.assertEqual(precio['total'], 1)
        self.assertEqual(precio['productos'][0]['precio'], 199.0)
        self.assertEqual(stock['productos'][0]['stock_actual'], 9)
        self.assertTrue(stock['productos'][0]['disponible'])

    def test_tools_contacto_envio_y_politicas(self):
        config = _ensure_store('truth-contact')
        contexto = self._contexto(config)

        contacto = execute_web_tool('obtener_info_contacto_actual', {'canal': 'todos'}, contexto)
        pagos = execute_web_tool('obtener_metodos_pago_vigentes', {}, contexto)
        envio = execute_web_tool('obtener_envio_estimado', {'zona': 'Luque'}, contexto)
        politicas = execute_web_tool('obtener_politicas_publicas', {'tema': 'todos'}, contexto)

        self.assertEqual(contacto['whatsapp'], '595981111111')
        self.assertIn('0981 111111', contacto['telefono'])
        self.assertIn('transferencia', pagos['metodos_pago'].lower())
        self.assertIn('central', envio['zonas_de_entrega'].lower())
        self.assertIn('garantía', politicas['garantia'].lower())

    def test_prompt_obliga_tools_temporales(self):
        config = _ensure_store('truth-prompt')
        prompt = build_web_bot_prompt(build_store_assistant_context(config, metadata={}))

        self.assertIn('obtener_fecha_hora_actual', prompt)
        self.assertIn('obtener_estado_tienda_actual', prompt)
        self.assertIn('No inventes fechas, horas', prompt)

    def test_prompt_compacta_contexto_sin_campos_ruidosos(self):
        config = _ensure_store('truth-prompt-compact')
        contexto = build_store_assistant_context(config, metadata={
            'visitante': {'nombre': '   Ana    Pérez   '},
            'tags': ['uno', 'dos', 'tres', 'cuatro', 'cinco'],
        })
        contexto['contexto_bot']['descripcion_negocio'] = '  Tienda    con   accesorios   premium  '
        contexto['beneficios_producto'] = [' Envío rápido ', 'Garantía extendida', '', 'Soporte', 'Instalación']

        prompt = build_web_bot_prompt(contexto)

        self.assertIn('"descripcion_negocio":"Tienda con accesorios premium"', prompt)
        self.assertNotIn('\n  "', prompt)
        self.assertNotIn('metadata_sesion', prompt)
        self.assertNotIn('color_primario', prompt)
        self.assertIn('"beneficios_producto":["Envío rápido","Garantía extendida","Soporte"]', prompt)

    def test_construir_mensajes_limita_historial_reciente(self):
        historial = []
        for indice in range(MAX_HISTORY_MESSAGES + 6):
            historial.append({'role': 'user', 'content': f'cliente {indice}'})
            historial.append({'role': 'assistant', 'content': f'bot {indice}'})

        mensajes = _construir_mensajes(historial, {'negocio': 'demo'})

        self.assertEqual(len(mensajes), MAX_HISTORY_MESSAGES + 1)
        self.assertEqual(mensajes[1]['content'], 'cliente 14')
        self.assertEqual(mensajes[-1]['content'], f'bot {MAX_HISTORY_MESSAGES + 5}')


if __name__ == '__main__':
    unittest.main()
