import unittest
from datetime import date, datetime

from flask import render_template
from flask_login import login_user

from app import create_app, db
from app.models import (
    Categoria,
    Cliente,
    CrmPlantilla,
    DetalleVenta,
    Producto,
    Servicio,
    SesionCaja,
    TiendaLead,
    TiendaVisitaEvento,
    Usuario,
    Venta,
)
from app.services.inteligencia import (
    obtener_panel_inteligencia_comercial,
    obtener_resumen_dashboard_inteligencia,
)
from app.utils.init_db import inicializar_datos_base


class TestInteligenciaComercial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        cls.ctx.pop()

    def setUp(self):
        db.session.remove()
        db.drop_all()
        db.create_all()
        inicializar_datos_base(config_name='testing')

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.client = self.app.test_client()
        self._login(self.client, self.admin)
        self.fecha_corte = date(2026, 3, 20)

    def tearDown(self):
        db.session.remove()

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id_usuario)
            sess['_fresh'] = True

    def _obtener_o_crear_categoria(self, nombre: str) -> Categoria:
        categoria = Categoria.query.filter_by(nombre=nombre).first()
        if categoria is None:
            categoria = Categoria(nombre=nombre, activo=True)
            db.session.add(categoria)
            db.session.flush()
        return categoria

    def _crear_producto(
        self,
        codigo: str,
        nombre: str,
        stock_actual: int,
        stock_minimo: int,
        precio: int = 100000,
        categoria_nombre: str = 'Termos',
    ) -> Producto:
        categoria = self._obtener_o_crear_categoria(categoria_nombre)
        producto = Producto(
            codigo=codigo,
            nombre=nombre,
            id_categoria=categoria.id_categoria,
            precio_compra=precio / 2,
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
            es_servicio=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.flush()
        return producto

    def _crear_servicio(
        self,
        codigo: str,
        nombre: str,
        precio: int,
        categoria: str = 'General',
    ) -> Servicio:
        servicio = Servicio(
            codigo=codigo,
            nombre=nombre,
            categoria=categoria,
            costo=precio / 2,
            precio=precio,
            duracion_minutos=30,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.flush()
        return servicio

    def _crear_venta(self, cliente: Cliente, sesion: SesionCaja, producto: Producto, fecha_venta: datetime, total: int) -> Venta:
        venta = Venta(
            id_cliente=cliente.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            fecha_venta=fecha_venta,
            subtotal=total,
            total=total,
            total_iva_10=round(total / 11, 2),
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
        )
        db.session.add(venta)
        db.session.flush()

        detalle = DetalleVenta(
            id_venta=venta.id_venta,
            id_producto=producto.id_producto,
            cantidad=1,
            precio_unitario=total,
            precio_original=total,
            porcentaje_iva=10,
            monto_iva=round(total / 11, 2),
            subtotal=total,
        )
        db.session.add(detalle)
        db.session.flush()
        return venta

    def _crear_venta_servicio(
        self,
        cliente: Cliente,
        sesion: SesionCaja,
        servicio: Servicio,
        fecha_venta: datetime,
        total: int,
    ) -> Venta:
        venta = Venta(
            id_cliente=cliente.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            fecha_venta=fecha_venta,
            subtotal=total,
            total=total,
            total_iva_10=round(total / 11, 2),
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
        )
        db.session.add(venta)
        db.session.flush()

        detalle = DetalleVenta(
            id_venta=venta.id_venta,
            id_servicio=servicio.id_servicio,
            cantidad=1,
            precio_unitario=total,
            precio_original=total,
            porcentaje_iva=10,
            monto_iva=round(total / 11, 2),
            subtotal=total,
        )
        db.session.add(detalle)
        db.session.flush()
        return venta

    def _registrar_visita_tienda(
        self,
        id_cliente_tienda: int,
        producto: Producto,
        fecha_evento: datetime,
        visitante_hash: str,
        user_agent: str = 'Mozilla/5.0 (Linux; Android 14; Mobile)',
    ) -> TiendaVisitaEvento:
        visita = TiendaVisitaEvento(
            id_cliente=id_cliente_tienda,
            id_producto=producto.id_producto,
            visitante_hash=visitante_hash,
            user_agent=user_agent,
            fecha_evento=fecha_evento,
        )
        db.session.add(visita)
        db.session.flush()
        return visita

    def _registrar_lead_tienda(
        self,
        id_cliente_tienda: int,
        producto: Producto,
        fecha_creacion: datetime,
        nombre_contacto: str,
    ) -> TiendaLead:
        lead = TiendaLead(
            id_cliente=id_cliente_tienda,
            id_producto=producto.id_producto,
            nombre_contacto=nombre_contacto,
            telefono_contacto='0991000000',
            mensaje='Consulta desde test',
            fecha_creacion=fecha_creacion,
        )
        db.session.add(lead)
        db.session.flush()
        return lead

    def _crear_plantilla(self, titulo: str, contenido: str, categoria: str = 'general', orden: int = 0) -> CrmPlantilla:
        plantilla = CrmPlantilla(
            titulo=titulo,
            contenido=contenido,
            categoria=categoria,
            orden=orden,
            activa=True,
            id_usuario_creador=self.admin.id_usuario,
        )
        db.session.add(plantilla)
        db.session.flush()
        return plantilla

    def _preparar_escenario_base(self):
        cliente_dormido = Cliente(nombre='Cliente Dormido Premium', telefono='0981123456', tipo='minorista', activo=True)
        cliente_activo = Cliente(nombre='Cliente Activo', tipo='minorista', activo=True)
        db.session.add_all([cliente_dormido, cliente_activo])
        db.session.flush()

        sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta')
        db.session.add(sesion)
        db.session.flush()

        producto_vendido = self._crear_producto('INT-SOLD-001', 'Producto con salida', stock_actual=8, stock_minimo=2, precio=120000)
        self._crear_producto('INT-RISK-001', 'Producto en riesgo', stock_actual=0, stock_minimo=2, precio=90000)
        self._crear_producto('INT-IDLE-001', 'Producto inmovilizado', stock_actual=5, stock_minimo=1, precio=70000)

        self._crear_venta(cliente_dormido, sesion, producto_vendido, datetime(2026, 1, 5, 15, 0, 0), 210000)
        self._crear_venta(cliente_dormido, sesion, producto_vendido, datetime(2026, 1, 10, 15, 0, 0), 220000)
        self._crear_venta(cliente_dormido, sesion, producto_vendido, datetime(2026, 1, 15, 15, 0, 0), 230000)
        self._crear_venta(cliente_activo, sesion, producto_vendido, datetime(2026, 2, 15, 15, 0, 0), 80000)
        self._crear_venta(cliente_activo, sesion, producto_vendido, datetime(2026, 3, 15, 15, 0, 0), 120000)

        db.session.commit()

    def _preparar_escenario_ventas(self):
        self._obtener_o_crear_categoria('Accesorios')
        self._obtener_o_crear_categoria('Audio')

        cliente = Cliente(nombre='Cliente Tendencia', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()

        sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta')
        db.session.add(sesion)
        db.session.flush()

        producto_termo = self._crear_producto('VENT-TERM-001', 'Termo premium', stock_actual=10, stock_minimo=2, precio=200000)
        producto_accesorio = self._crear_producto(
            'VENT-ACC-001',
            'Accesorio destacado',
            stock_actual=12,
            stock_minimo=2,
            precio=180000,
            categoria_nombre='Accesorios',
        )
        producto_audio = self._crear_producto(
            'VENT-AUD-001',
            'Parlante compacto',
            stock_actual=6,
            stock_minimo=1,
            precio=90000,
            categoria_nombre='Audio',
        )

        self._crear_venta(cliente, sesion, producto_termo, datetime(2026, 2, 12, 10, 0, 0), 250000)
        self._crear_venta(cliente, sesion, producto_termo, datetime(2026, 2, 20, 16, 0, 0), 250000)
        self._crear_venta(cliente, sesion, producto_audio, datetime(2026, 2, 24, 11, 0, 0), 90000)

        self._crear_venta(cliente, sesion, producto_accesorio, datetime(2026, 3, 3, 11, 0, 0), 180000)
        self._crear_venta(cliente, sesion, producto_accesorio, datetime(2026, 3, 10, 12, 0, 0), 180000)
        self._crear_venta(cliente, sesion, producto_accesorio, datetime(2026, 3, 18, 17, 0, 0), 180000)
        self._crear_venta(cliente, sesion, producto_termo, datetime(2026, 3, 15, 14, 0, 0), 200000)

        db.session.commit()

    def _preparar_escenario_tienda(self) -> int:
        cliente_tienda = Cliente(nombre='Tenant Tienda', tipo='minorista', activo=True)
        db.session.add(cliente_tienda)
        db.session.flush()

        producto_top = self._crear_producto(
            'SHOP-TOP-001',
            'Mate premium',
            stock_actual=9,
            stock_minimo=2,
            precio=150000,
            categoria_nombre='Accesorios',
        )
        producto_sano = self._crear_producto(
            'SHOP-OK-001',
            'Botella térmica',
            stock_actual=7,
            stock_minimo=2,
            precio=130000,
            categoria_nombre='Termos',
        )

        for idx in range(1, 7):
            self._registrar_visita_tienda(
                cliente_tienda.id_cliente,
                producto_top,
                datetime(2026, 3, 10, 15, idx, 0),
                visitante_hash=f'top-{idx}',
            )

        self._registrar_visita_tienda(
            cliente_tienda.id_cliente,
            producto_sano,
            datetime(2026, 3, 12, 20, 0, 0),
            visitante_hash='ok-1',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        )
        self._registrar_visita_tienda(
            cliente_tienda.id_cliente,
            producto_sano,
            datetime(2026, 3, 12, 20, 5, 0),
            visitante_hash='ok-2',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        )

        self._registrar_lead_tienda(
            cliente_tienda.id_cliente,
            producto_sano,
            datetime(2026, 3, 12, 20, 10, 0),
            'Lead Botella',
        )

        db.session.commit()
        return cliente_tienda.id_cliente

    def _preparar_escenario_inventario(self) -> int:
        cliente_tienda = Cliente(nombre='Tenant Inventario', tipo='minorista', activo=True)
        cliente_compra = Cliente(nombre='Cliente Inventario', tipo='minorista', activo=True)
        db.session.add_all([cliente_tienda, cliente_compra])
        db.session.flush()

        sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta')
        db.session.add(sesion)
        db.session.flush()

        producto_quiebre = self._crear_producto(
            'INV-RUN-001',
            'Termo explosivo',
            stock_actual=2,
            stock_minimo=1,
            precio=95000,
            categoria_nombre='Termos',
        )
        producto_inmovilizado = self._crear_producto(
            'INV-IDLE-001',
            'Mate encajonado',
            stock_actual=9,
            stock_minimo=2,
            precio=85000,
            categoria_nombre='Mates',
        )
        producto_atencion = self._crear_producto(
            'INV-LOOK-001',
            'Bombilla curiosa',
            stock_actual=6,
            stock_minimo=1,
            precio=40000,
            categoria_nombre='Accesorios',
        )

        for fecha in (
            datetime(2026, 3, 2, 10, 0, 0),
            datetime(2026, 3, 6, 11, 0, 0),
            datetime(2026, 3, 11, 15, 0, 0),
            datetime(2026, 3, 18, 18, 0, 0),
        ):
            self._crear_venta(cliente_compra, sesion, producto_quiebre, fecha, 95000)

        self._crear_venta(cliente_compra, sesion, producto_atencion, datetime(2026, 2, 15, 14, 0, 0), 40000)

        for idx in range(1, 7):
            self._registrar_visita_tienda(
                cliente_tienda.id_cliente,
                producto_atencion,
                datetime(2026, 3, 8, 16, idx, 0),
                visitante_hash=f'look-{idx}',
            )

        db.session.commit()
        return cliente_tienda.id_cliente

    def test_servicio_panel_detecta_clientes_y_stock(self):
        self._preparar_escenario_base()

        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)

        self.assertEqual(panel['stock']['riesgo_count'], 1)
        self.assertEqual(panel['stock']['inmovilizado_count'], 1)
        self.assertEqual(panel['stock']['riesgo_detalle'][0]['nombre'], 'Producto en riesgo')
        self.assertEqual(panel['stock']['inmovilizado_detalle'][0]['nombre'], 'Producto inmovilizado')
        self.assertEqual(panel['clientes']['total_para_activar'], 1)
        self.assertEqual(panel['clientes']['segmentos']['dormidos'], 1)
        self.assertEqual(panel['clientes']['segmentos']['frecuentes'], 1)
        self.assertEqual(panel['clientes']['segmentos']['alto_valor'], 1)
        self.assertEqual(panel['clientes']['clientes_para_activar'][0]['nombre'], 'Cliente Dormido Premium')
        self.assertEqual(panel['clientes']['para_activar_detalle'][0]['accion'], 'Llamar hoy')
        self.assertEqual(panel['clientes']['segmentos_detalle']['para_activar'][0]['telefono_enlace'], 'tel:595981123456')
        self.assertEqual(panel['clientes']['clientes_para_activar'][0]['telefono_label'], '0981 123 456')
        self.assertEqual(
            panel['clientes']['segmentos_detalle']['valiosos_dormidos'][0]['whatsapp_url'],
            'https://wa.me/595981123456',
        )
        self.assertEqual(panel['clientes_activos']['actual'], 1)
        self.assertIn('series', panel['clientes_activos'])
        self.assertGreaterEqual(len(panel['clientes_activos']['series']['actual']), 1)
        self.assertEqual(
            len(panel['clientes_activos']['series']['actual']),
            len(panel['clientes_activos']['series']['anterior']),
        )
        self.assertEqual(panel['facturacion']['actual_label'], '₲ 120.000')
        self.assertEqual(panel['ventas']['categorias'][0]['nombre'], 'Termos')
        self.assertEqual(panel['ventas']['cantidad_ventas']['actual'], 1)
        self.assertTrue(any('cliente' in accion['titulo'].lower() for accion in panel['acciones_hoy']))
        self.assertEqual(panel['acciones_hoy'][0]['modal']['clave'], 'valiosos_dormidos')

    def test_dashboard_renderiza_modal_de_clientes(self):
        self._preparar_escenario_base()
        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)

        with self.app.test_request_context('/inteligencia'):
            login_user(self.admin)
            html = render_template('inteligencia/dashboard.html', panel=panel, vista_activa='resumen')

        self.assertIn('data-inteligencia-modal-clave="para_activar"', html)
        self.assertIn('data-inteligencia-modal-clave="valiosos_dormidos"', html)
        self.assertIn('data-inteligencia-clientes', html)
        self.assertIn('data-inteligencia-stock', html)
        self.assertIn('data-inteligencia-modal-stock="riesgo"', html)
        self.assertIn('data-inteligencia-modal-stock="inmovilizado"', html)
        self.assertIn('data-inteligencia-kpi-clientes', html)
        self.assertIn('data-inteligencia-kpi-clientes-series', html)
        self.assertIn('data-inteligencia-charts-json', html)
        self.assertIn('data-kpi-actual-periodo=', html)
        self.assertIn('data-kpi-anterior-periodo=', html)
        self.assertIn('id="inteligenciaClientesSparkline"', html)
        self.assertIn('id="inteligenciaActivacionChart"', html)
        self.assertIn('"activacion_clientes"', html)
        self.assertIn('id="inteligenciaVentasTrendChart"', html)
        self.assertIn('id="inteligenciaCategoriasChart"', html)
        self.assertIn('name="periodo"', html)
        self.assertIn('id="inteligencia-periodo"', html)
        self.assertIn('Activo: Este mes', html)
        self.assertIn('Embudo de visitas a consultas', html)
        self.assertIn('Cliente Dormido Premium', html)
        self.assertIn('"para_activar_detalle"', html)
        self.assertIn('"segmentos_detalle"', html)
        self.assertIn('data-inteligencia-modal-items=', html)
        self.assertIn('https://wa.me/595981123456', html)

    def test_panel_clientes_sin_resultados_expone_clave_para_activar(self):
        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)

        self.assertEqual(panel['clientes']['total_para_activar'], 0)
        self.assertIn('para_activar', panel['clientes']['segmentos_detalle'])
        self.assertEqual(panel['clientes']['segmentos_detalle']['para_activar'], [])

    def test_inteligencia_ventas_detecta_categorias_y_tendencia(self):
        self._preparar_escenario_ventas()

        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)

        self.assertEqual(panel['ventas']['cantidad_ventas']['actual'], 4)
        self.assertEqual(panel['ventas']['cantidad_ventas']['anterior_label'], '3')
        self.assertEqual(panel['ventas']['categorias'][0]['nombre'], 'Accesorios')
        self.assertEqual(panel['ventas']['categorias'][0]['facturacion_label'], '₲ 540.000')
        self.assertEqual(panel['ventas']['categorias'][0]['variacion_label'], 'Sin base previa')
        self.assertEqual(len(panel['ventas']['tendencia']), 6)
        self.assertTrue(any('Accesorios' in insight['titulo'] for insight in panel['ventas']['insights']))

    def test_inteligencia_ventas_incluye_categorias_de_servicios(self):
        self._preparar_escenario_ventas()
        cliente = Cliente(nombre='Cliente Servicio Ventas', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        sesion = SesionCaja.query.filter_by(estado='abierta').first()
        self.assertIsNotNone(sesion)
        servicio = self._crear_servicio('SRV-CAT-001', 'Corte premium', 400000, categoria='Spa')
        self._crear_venta_servicio(
            cliente,
            sesion,
            servicio,
            datetime(2026, 3, 19, 13, 0, 0),
            400000,
        )
        db.session.commit()

        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)
        categorias = panel['ventas']['categorias']
        categoria_spa = next((item for item in categorias if item['nombre'] == 'Spa'), None)

        self.assertIsNotNone(categoria_spa)
        self.assertAlmostEqual(float(categoria_spa['facturacion']), 400000.0)
        self.assertEqual(int(categoria_spa['unidades']), 1)

    def test_inteligencia_soporta_periodos_estables_en_servicio_y_ruta(self):
        self._preparar_escenario_ventas()

        panel_mes = obtener_panel_inteligencia_comercial(self.fecha_corte, periodo='mes')
        panel_30d = obtener_panel_inteligencia_comercial(self.fecha_corte, periodo='30d')
        panel_trimestre = obtener_panel_inteligencia_comercial(self.fecha_corte, periodo='trimestre')
        panel_todo = obtener_panel_inteligencia_comercial(self.fecha_corte, periodo='todo')

        self.assertEqual(panel_mes['periodo_clave'], 'mes')
        self.assertEqual(panel_mes['periodo_label'], 'Este mes')
        self.assertEqual(panel_30d['periodo_clave'], '30d')
        self.assertEqual(panel_30d['periodo_label'], 'Últimos 30 días')
        self.assertEqual(panel_trimestre['periodo_clave'], 'trimestre')
        self.assertEqual(panel_trimestre['periodo_label'], 'Este trimestre')
        self.assertEqual(panel_todo['periodo_clave'], 'todo')
        self.assertEqual(panel_todo['periodo_label'], 'Todo período')
        self.assertNotEqual(panel_mes['periodo_actual_label'], panel_30d['periodo_actual_label'])
        self.assertNotEqual(panel_mes['facturacion']['actual'], panel_30d['facturacion']['actual'])
        self.assertGreater(panel_trimestre['facturacion']['actual'], panel_mes['facturacion']['actual'])
        self.assertGreaterEqual(panel_todo['facturacion']['actual'], panel_trimestre['facturacion']['actual'])

        respuesta = self.client.get('/inteligencia?vista=comercial&periodo=30d')

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b'option value="30d" selected', respuesta.data)
        self.assertIn(b'Activo: \xc3\x9altimos 30 d\xc3\xadas', respuesta.data)
        self.assertIn(b'/inteligencia?vista=resumen&amp;periodo=30d', respuesta.data)
        self.assertIn(b'/inteligencia?vista=operacion&amp;periodo=30d', respuesta.data)

        respuesta_todo = self.client.get('/inteligencia?vista=comercial&periodo=todo')

        self.assertEqual(respuesta_todo.status_code, 200)
        self.assertIn(b'option value="todo" selected', respuesta_todo.data)
        self.assertIn(b'Activo: Todo per\xc3\xadodo', respuesta_todo.data)

    def test_inteligencia_tienda_detecta_productos_y_horarios(self):
        id_cliente_tienda = self._preparar_escenario_tienda()

        panel = obtener_panel_inteligencia_comercial(
            self.fecha_corte,
            id_cliente_tienda=id_cliente_tienda,
        )

        self.assertEqual(panel['tienda']['resumen']['total_visitas'], 8)
        self.assertEqual(panel['tienda']['resumen']['consultas_iniciadas'], 1)
        self.assertEqual(panel['tienda']['resumen']['conversion_global_label'], '12.5%')
        self.assertEqual(panel['tienda']['productos_atencion'][0]['nombre'], 'Mate premium')
        self.assertEqual(panel['tienda']['productos_atencion'][0]['leads_generados'], 0)
        self.assertEqual(panel['tienda']['horarios_pico'][0]['hora'], '15:00')
        self.assertTrue(any('Mate premium' in accion['titulo'] for accion in panel['acciones_hoy']))

    def test_inteligencia_tienda_no_filtra_otro_tenant_sin_cliente_explicito(self):
        self._preparar_escenario_tienda()

        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)

        self.assertIsNone(panel['tienda']['cliente_id'])
        self.assertFalse(panel['tienda']['hay_datos'])
        self.assertEqual(panel['tienda']['resumen']['total_visitas'], 0)
        self.assertEqual(panel['tienda']['productos_atencion'], [])

    def test_estadisticas_tienda_admin_exigen_cliente_explicito(self):
        self._preparar_escenario_tienda()

        respuesta = self.client.get('/api/tienda/admin/estadisticas/productos-mas-vistos')

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.get_json()['error'], 'cliente_no_encontrado')

    def test_inteligencia_inventario_detecta_rotacion_quiebre_y_atencion(self):
        id_cliente_tienda = self._preparar_escenario_inventario()

        panel = obtener_panel_inteligencia_comercial(
            self.fecha_corte,
            id_cliente_tienda=id_cliente_tienda,
        )

        self.assertEqual(panel['inventario']['resumen']['riesgo_quiebre'], 1)
        self.assertEqual(panel['inventario']['resumen']['rotacion_rapida'], 1)
        self.assertEqual(panel['inventario']['resumen']['stock_inmovilizado'], 1)
        self.assertEqual(panel['inventario']['resumen']['atencion_sin_rotacion'], 1)
        self.assertEqual(panel['inventario']['riesgo_quiebre'][0]['nombre'], 'Termo explosivo')
        self.assertEqual(panel['inventario']['rotacion_rapida'][0]['nombre'], 'Termo explosivo')
        self.assertEqual(panel['inventario']['stock_inmovilizado'][0]['nombre'], 'Mate encajonado')
        self.assertEqual(panel['inventario']['atencion_sin_rotacion'][0]['nombre'], 'Bombilla curiosa')
        self.assertEqual(panel['inventario']['riesgo_quiebre'][0]['codigo'], 'INV-RUN-001')
        self.assertEqual(panel['inventario']['stock_inmovilizado'][0]['codigo'], 'INV-IDLE-001')
        self.assertTrue(any('quebrar' in insight['titulo'].lower() or 'miradas' in insight['titulo'].lower() for insight in panel['inventario']['insights']))

    def test_inteligencia_inventario_ignora_ventas_solo_servicio(self):
        id_cliente_tienda = self._preparar_escenario_inventario()
        cliente_servicio = Cliente(nombre='Cliente Servicio', tipo='minorista', activo=True)
        db.session.add(cliente_servicio)
        db.session.flush()
        sesion = SesionCaja.query.filter_by(estado='abierta').first()
        self.assertIsNotNone(sesion)
        servicio = self._crear_servicio('SRV-ONLY-001', 'Servicio técnico', 60000)
        self._crear_venta_servicio(
            cliente_servicio,
            sesion,
            servicio,
            datetime(2026, 3, 19, 9, 0, 0),
            60000,
        )
        db.session.commit()

        panel = obtener_panel_inteligencia_comercial(
            self.fecha_corte,
            id_cliente_tienda=id_cliente_tienda,
        )
        resumen = obtener_resumen_dashboard_inteligencia(
            self.fecha_corte,
            id_cliente_tienda=id_cliente_tienda,
        )

        self.assertIsNotNone(panel)
        self.assertIsNotNone(resumen)
        self.assertIn('inventario', panel)
        self.assertEqual(panel['inventario']['resumen']['riesgo_quiebre'], 1)
        self.assertEqual(panel['inventario']['riesgo_quiebre'][0]['codigo'], 'INV-RUN-001')

    def test_campanas_sugiere_segmentos_y_reutiliza_plantillas(self):
        self._preparar_escenario_base()
        self._crear_plantilla(
            'Beneficio VIP',
            'Hola, tenemos un beneficio especial para agradecer tus compras y ayudarte a volver.',
            categoria='beneficio',
            orden=1,
        )
        self._crear_plantilla(
            'Reactivación simple',
            'Hace un tiempo no comprás con nosotros. Si querés, te ayudamos a repetir tu compra.',
            categoria='reactivacion',
            orden=2,
        )

        panel = obtener_panel_inteligencia_comercial(self.fecha_corte)

        self.assertGreaterEqual(panel['campanas']['resumen']['campanas_activables'], 2)
        self.assertGreaterEqual(panel['campanas']['resumen']['automatizaciones_sugeridas'], 1)
        self.assertEqual(panel['campanas']['campanas'][0]['titulo'], 'Reactivar clientes valiosos dormidos')
        self.assertEqual(panel['campanas']['campanas'][0]['plantilla_titulo'], 'Beneficio VIP')
        self.assertTrue(any('cola diaria' in item['titulo'].lower() for item in panel['campanas']['automatizaciones']))
        self.assertTrue(any('campaña' in accion['titulo'].lower() or 'reactivar clientes valiosos' in accion['titulo'].lower() for accion in panel['acciones_hoy']))

    def test_resumen_y_rutas_muestran_acceso_inteligencia(self):
        self._preparar_escenario_base()

        resumen = obtener_resumen_dashboard_inteligencia(self.fecha_corte)
        self.assertEqual(resumen['clientes_para_activar'], 1)
        self.assertEqual(resumen['riesgo_stock'], 1)
        self.assertEqual(resumen['stock_inmovilizado'], 1)
        self.assertGreaterEqual(resumen['campanas_sugeridas'], 1)

        respuesta_dashboard = self.client.get('/')
        self.assertEqual(respuesta_dashboard.status_code, 200)
        self.assertIn(b'Inteligencia', respuesta_dashboard.data)
        self.assertIn(b'/inteligencia', respuesta_dashboard.data)
        self.assertIn(b'data-bi-alertas="', respuesta_dashboard.data)

        respuesta_modulo = self.client.get('/inteligencia')
        self.assertEqual(respuesta_modulo.status_code, 200)
        self.assertIn(b'Centro de Inteligencia Comercial', respuesta_modulo.data)
        self.assertIn(b'Cliente Dormido Premium', respuesta_modulo.data)
        self.assertIn(b'Campa\xc3\xb1as sugeridas', respuesta_modulo.data)
        self.assertIn(b'Categor\xc3\xadas que sostienen ingresos', respuesta_modulo.data)
        self.assertIn(b'Rotaci\xc3\xb3n e inteligencia de stock', respuesta_modulo.data)

    def test_inteligencia_agrega_deep_links_a_productos(self):
        self._preparar_escenario_inventario()
        producto_inmovilizado = Producto.query.filter_by(codigo='INV-IDLE-001').first()

        respuesta = self.client.get('/inteligencia?vista=operacion')

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNotNone(producto_inmovilizado)
        self.assertIn(f'/productos/{producto_inmovilizado.id_producto}/editar'.encode(), respuesta.data)
        self.assertIn(b'data-tab-title="Producto"', respuesta.data)


if __name__ == '__main__':
    unittest.main()
