import unittest
from datetime import timedelta

from flask_login import login_user

from app import create_app, db
from app.models import AgendaActividad, Cliente, ClienteServicio, Reparacion, Rol, Servicio, Usuario
from app.services.dashboard_clientes import obtener_resumen_clientes_dashboard
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from app.utils.init_db import inicializar_datos_base


class TestAgendaServiciosForm(unittest.TestCase):
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
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def test_formulario_prioriza_servicios(self):
        response = self.client.get('/agenda/actividades/nueva')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Agendar servicio', html)
        self.assertIn('Buscar servicio...', html)
        self.assertNotIn('Reparacion</label>', html)
        self.assertNotIn('Venta</label>', html)

    def test_busqueda_clientes_omite_inactivos(self):
        cliente_activo = Cliente(nombre='Cliente Agenda Activo', tipo='minorista', activo=True)
        cliente_inactivo = Cliente(nombre='Cliente Agenda Inactivo', tipo='minorista', activo=False)
        db.session.add_all([cliente_activo, cliente_inactivo])
        db.session.commit()

        response = self.client.get('/agenda/api/clientes/buscar?q=Cliente%20Agenda')
        self.assertEqual(response.status_code, 200)
        nombres = {item.get('nombre') for item in (response.get_json() or {}).get('items', [])}

        self.assertIn('Cliente Agenda Activo', nombres)
        self.assertNotIn('Cliente Agenda Inactivo', nombres)

    def test_busqueda_reparaciones_filtra_por_cliente(self):
        cliente_a = Cliente(nombre='Cliente Reparacion A', tipo='minorista', activo=True)
        cliente_b = Cliente(nombre='Cliente Reparacion B', tipo='minorista', activo=True)
        db.session.add_all([cliente_a, cliente_b])
        db.session.flush()
        reparacion_a = Reparacion(
            cliente_id=cliente_a.id_cliente,
            tipo_equipo='Celular',
            marca_modelo='Samsung A10',
            falla_reportada='Pantalla rota',
        )
        reparacion_b = Reparacion(
            cliente_id=cliente_b.id_cliente,
            tipo_equipo='Tablet',
            marca_modelo='Lenovo M10',
            falla_reportada='No carga',
        )
        db.session.add_all([reparacion_a, reparacion_b])
        db.session.commit()

        response = self.client.get(f'/agenda/api/reparaciones/buscar?cliente_id={cliente_a.id_cliente}')
        self.assertEqual(response.status_code, 200)
        items = (response.get_json() or {}).get('items', [])
        ids = {item.get('id_reparacion') for item in items}

        self.assertIn(reparacion_a.id_reparacion, ids)
        self.assertNotIn(reparacion_b.id_reparacion, ids)
        self.assertEqual(items[0].get('cliente_id'), cliente_a.id_cliente)

    def test_agendar_servicio_crea_asignacion_cliente_servicio(self):
        cliente = Cliente(nombre='Cliente Agenda Servicio', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='SERV-AGENDA',
            nombre='Servicio agendable',
            categoria='Salon',
            costo=10000,
            precio=50000,
            duracion_minutos=45,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        response = self.client.post(
            '/agenda/actividades/nueva',
            data={
                'titulo': 'Servicio agendable - Cliente Agenda Servicio',
                'tipo': 'cita',
                'prioridad': 'media',
                'fecha_inicio': '2030-01-10T09:00',
                'fecha_fin': '2030-01-10T09:45',
                'usuario_id': str(self.admin.id_usuario),
                'cliente_id': str(cliente.id_cliente),
                'servicio_catalogo_id': str(servicio.id_servicio),
                'mostrar_agenda_en': 'solo_responsable',
                'recordatorio_a': 'solo_responsable',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        actividad = AgendaActividad.query.filter_by(titulo='Servicio agendable - Cliente Agenda Servicio').first()
        self.assertIsNotNone(actividad)
        self.assertIsNotNone(actividad.cliente_servicio_id)
        asignacion = db.session.get(ClienteServicio, actividad.cliente_servicio_id)
        self.assertEqual(asignacion.id_cliente, cliente.id_cliente)
        self.assertEqual(asignacion.id_servicio, servicio.id_servicio)
        self.assertEqual(asignacion.estado, 'agendado')
        self.assertEqual(float(asignacion.precio_pactado), 50000.0)

    def test_cancelar_actividad_cancela_cliente_servicio_pendiente_de_cobro(self):
        cliente = Cliente(nombre='Cliente Cancelacion Servicio', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='SERV-CANCEL',
            nombre='Servicio cancelable',
            categoria='Salon',
            costo=10000,
            precio=50000,
            duracion_minutos=45,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add_all([cliente, servicio])
        db.session.flush()
        asignacion = ClienteServicio(
            id_cliente=cliente.id_cliente,
            id_servicio=servicio.id_servicio,
            cantidad=1,
            costo_pactado=10000,
            precio_pactado=50000,
            estado='agendado',
            id_usuario_registro=self.admin.id_usuario,
        )
        actividad = AgendaActividad(
            titulo='Servicio cancelable',
            tipo='cita',
            fecha_inicio=utc_bounds_for_local_dates(today_local(), today_local())[0],
            estado='pendiente',
            prioridad='media',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            cliente_id=cliente.id_cliente,
            cliente_servicio=asignacion,
            origen_modulo='agenda',
        )
        db.session.add_all([asignacion, actividad])
        db.session.commit()

        response = self.client.post(f'/agenda/actividades/{actividad.id}/cancelar', follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        db.session.refresh(asignacion)
        self.assertEqual(asignacion.estado, 'cancelado')
        self.assertIsNotNone(asignacion.fecha_cierre)

    def test_reprogramar_actividad_sincroniza_fecha_del_cliente_servicio(self):
        cliente = Cliente(nombre='Cliente Reprogramacion Servicio', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='SERV-REPROG',
            nombre='Servicio reprogramable',
            categoria='Salon',
            costo=10000,
            precio=50000,
            duracion_minutos=45,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add_all([cliente, servicio])
        db.session.flush()
        inicio_original = utc_bounds_for_local_dates(today_local(), today_local())[0]
        asignacion = ClienteServicio(
            id_cliente=cliente.id_cliente,
            id_servicio=servicio.id_servicio,
            cantidad=1,
            costo_pactado=10000,
            precio_pactado=50000,
            estado='cancelado',
            fecha_programada=inicio_original,
            id_usuario_registro=self.admin.id_usuario,
        )
        actividad = AgendaActividad(
            titulo='Servicio reprogramable',
            tipo='cita',
            fecha_inicio=inicio_original,
            estado='cancelada',
            prioridad='media',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            cliente_id=cliente.id_cliente,
            cliente_servicio=asignacion,
            origen_modulo='agenda',
        )
        db.session.add_all([asignacion, actividad])
        db.session.commit()

        response = self.client.post(
            f'/agenda/actividades/{actividad.id}/reprogramar',
            data={'fecha_inicio': '2030-01-11T10:30'},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(actividad)
        db.session.refresh(asignacion)
        self.assertEqual(actividad.estado, 'pendiente')
        self.assertEqual(asignacion.estado, 'agendado')
        self.assertEqual(asignacion.fecha_programada, actividad.fecha_inicio)

    def test_dashboard_clientes_cancelados_respeta_visibilidad_de_agenda(self):
        rol_vendedor = Rol.query.filter_by(nombre='Vendedor').first()
        vendedor = Usuario(username='agenda_vendedor', nombre_completo='Agenda Vendedor', id_rol=rol_vendedor.id_rol)
        vendedor.set_password('test123')
        cliente_visible = Cliente(nombre='Cliente Visible Cancelado', tipo='minorista', activo=True)
        cliente_ajeno = Cliente(nombre='Cliente Ajeno Cancelado', tipo='minorista', activo=True)
        db.session.add_all([vendedor, cliente_visible, cliente_ajeno])
        db.session.flush()
        inicio_hoy = utc_bounds_for_local_dates(today_local(), today_local())[0] + timedelta(hours=1)
        db.session.add_all([
            AgendaActividad(
                titulo='Cancelado visible',
                tipo='cita',
                fecha_inicio=inicio_hoy,
                estado='cancelada',
                prioridad='media',
                usuario_id=vendedor.id_usuario,
                creado_por_id=vendedor.id_usuario,
                cliente_id=cliente_visible.id_cliente,
                origen_modulo='agenda',
            ),
            AgendaActividad(
                titulo='Cancelado ajeno',
                tipo='cita',
                fecha_inicio=inicio_hoy,
                estado='cancelada',
                prioridad='media',
                usuario_id=self.admin.id_usuario,
                creado_por_id=self.admin.id_usuario,
                cliente_id=cliente_ajeno.id_cliente,
                origen_modulo='agenda',
            ),
        ])
        db.session.commit()

        with self.app.test_request_context('/'):
            login_user(vendedor)
            resumen = obtener_resumen_clientes_dashboard(
                today=today_local(),
                can_ver_agenda=True,
                puede_ver_otras_cajas=True,
                sesion_caja_id=None,
            )

        self.assertEqual(resumen['cancelados']['count'], 1)


if __name__ == '__main__':
    unittest.main()
