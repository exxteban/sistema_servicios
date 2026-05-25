import unittest

from app import create_app, db
from app.models import AgendaActividad, Cliente, ClienteServicio, Configuracion, Servicio, Usuario
from app.services.dashboard_preferences import get_dashboard_service_cards, set_dashboard_service_cards
from app.utils.helpers import today_local, utc_naive_to_local
from app.utils.init_db import inicializar_datos_base


class TestAgendaPeluqueriaSolapamientos(unittest.TestCase):
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
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def test_no_permite_turno_solapado_para_mismo_profesional(self):
        cliente = Cliente(nombre='Cliente Solape', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-SOLAPE-001',
            nombre='Corte solape',
            categoria='Salon',
            costo=10000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        base_data = {
            'usuario_id': str(self.admin.id_usuario),
            'cliente_id': str(cliente.id_cliente),
            'duracion': '30',
            'servicio_turno_id': 'corte',
            'servicio_turno_nombre': 'Corte',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        }

        primero = self.client.post('/agenda/turnos/peluqueria/crear', data={
            **base_data,
            'titulo': 'Corte 09:00',
            'fecha_inicio': '2030-01-10T09:00',
            'fecha_fin': '2030-01-10T09:30',
        }, follow_redirects=True)
        self.assertEqual(primero.status_code, 200)

        solapado = self.client.post('/agenda/turnos/peluqueria/crear', data={
            **base_data,
            'titulo': 'Corte 09:15',
            'fecha_inicio': '2030-01-10T09:15',
            'fecha_fin': '2030-01-10T09:45',
        }, follow_redirects=True)

        self.assertEqual(solapado.status_code, 200)
        self.assertIn('Ese profesional ya tiene un turno en ese horario', solapado.get_data(as_text=True))
        self.assertEqual(AgendaActividad.query.filter(AgendaActividad.titulo.like('Corte 09:%')).count(), 1)

    def test_crea_cliente_rapido_desde_turno(self):
        servicio = Servicio(
            codigo='TURNO-CLIENTE-RAPIDO-001',
            nombre='Barba rapida',
            categoria='Salon',
            costo=10000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='barba',
        )
        db.session.add(servicio)
        db.session.commit()

        response = self.client.post('/agenda/turnos/peluqueria/crear', data={
            'titulo': 'Barba rapida - Cliente Nuevo Rapido',
            'usuario_id': str(self.admin.id_usuario),
            'cliente_nuevo_nombre': 'Cliente Nuevo Rapido',
            'cliente_nuevo_telefono': '0981000000',
            'duracion': '20',
            'fecha_inicio': '2030-01-10T10:00',
            'fecha_fin': '2030-01-10T10:20',
            'servicio_turno_id': 'barba',
            'servicio_turno_nombre': 'Barba',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        cliente = Cliente.query.filter_by(nombre='Cliente Nuevo Rapido').first()
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente.telefono, '0981000000')

        actividad = AgendaActividad.query.filter_by(titulo='Barba rapida - Cliente Nuevo Rapido').first()
        self.assertIsNotNone(actividad)
        self.assertEqual(int(actividad.cliente_id), int(cliente.id_cliente))

    def test_gestionar_turno_reprograma_y_respeta_solapamiento(self):
        cliente = Cliente(nombre='Cliente Gestion', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-GESTION-001',
            nombre='Corte gestion',
            categoria='Salon',
            costo=10000,
            precio=30000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        base_data = {
            'usuario_id': str(self.admin.id_usuario),
            'cliente_id': str(cliente.id_cliente),
            'duracion': '30',
            'servicio_turno_id': 'corte',
            'servicio_turno_nombre': 'Corte',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        }
        self.client.post('/agenda/turnos/peluqueria/crear', data={
            **base_data,
            'titulo': 'Corte Gestion 09',
            'fecha_inicio': '2030-01-10T09:00',
            'fecha_fin': '2030-01-10T09:30',
        })
        self.client.post('/agenda/turnos/peluqueria/crear', data={
            **base_data,
            'titulo': 'Corte Gestion 10',
            'fecha_inicio': '2030-01-10T10:00',
            'fecha_fin': '2030-01-10T10:30',
        })

        actividad = AgendaActividad.query.filter_by(titulo='Corte Gestion 09').first()
        self.assertIsNotNone(actividad)

        solapado = self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'reprogramar', 'fecha': '2030-01-10', 'hora': '10:15', 'duracion': '30'},
            follow_redirects=True,
        )
        self.assertEqual(solapado.status_code, 200)
        self.assertIn('Ese profesional ya tiene otro turno en ese horario', solapado.get_data(as_text=True))

        ok = self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'reprogramar', 'fecha': '2030-01-10', 'hora': '11:00', 'duracion': '45'},
            follow_redirects=True,
        )
        self.assertEqual(ok.status_code, 200)
        db.session.refresh(actividad)
        self.assertEqual(utc_naive_to_local(actividad.fecha_inicio).strftime('%H:%M'), '11:00')
        self.assertEqual(utc_naive_to_local(actividad.fecha_fin).strftime('%H:%M'), '11:45')

    def test_gestionar_turno_registra_sena_y_cancela(self):
        cliente = Cliente(nombre='Cliente Sena', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-SENA-001',
            nombre='Color sena',
            categoria='Salon',
            costo=20000,
            precio=80000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='color',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        self.client.post('/agenda/turnos/peluqueria/crear', data={
            'titulo': 'Color Sena',
            'usuario_id': str(self.admin.id_usuario),
            'cliente_id': str(cliente.id_cliente),
            'duracion': '90',
            'fecha_inicio': '2030-01-10T12:00',
            'fecha_fin': '2030-01-10T13:30',
            'servicio_turno_id': 'color',
            'servicio_turno_nombre': 'Color',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        })
        actividad = AgendaActividad.query.filter_by(titulo='Color Sena').first()
        self.assertIsNotNone(actividad)

        sena = self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'sena', 'monto_sena': '20000', 'nota_sena': 'transferencia'},
            follow_redirects=True,
        )
        self.assertEqual(sena.status_code, 200)
        db.session.refresh(actividad)
        self.assertIn('Seña registrada: Gs. 20.000 - transferencia', actividad.observaciones or '')

        cancelar = self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'cancelar', 'motivo': 'Aviso previo'},
            follow_redirects=True,
        )
        self.assertEqual(cancelar.status_code, 200)
        db.session.refresh(actividad)
        asignacion = db.session.get(ClienteServicio, int(actividad.cliente_servicio_id))
        self.assertEqual(actividad.estado, 'cancelada')
        self.assertEqual(asignacion.estado, 'cancelado')
        self.assertIn('Cancelado desde peluquería/barbería: Aviso previo', actividad.observaciones or '')

    def test_gestionar_turno_marca_no_show(self):
        cliente = Cliente(nombre='Cliente No Show', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-NOSHOW-001',
            nombre='Peinado no show',
            categoria='Salon',
            costo=15000,
            precio=45000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='peinado',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        self.client.post('/agenda/turnos/peluqueria/crear', data={
            'titulo': 'Peinado No Show',
            'usuario_id': str(self.admin.id_usuario),
            'cliente_id': str(cliente.id_cliente),
            'duracion': '45',
            'fecha_inicio': '2030-01-10T15:00',
            'fecha_fin': '2030-01-10T15:45',
            'servicio_turno_id': 'peinado',
            'servicio_turno_nombre': 'Peinado',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        })
        actividad = AgendaActividad.query.filter_by(titulo='Peinado No Show').first()
        self.assertIsNotNone(actividad)

        response = self.client.post(
            f'/agenda/turnos/peluqueria/{actividad.id}/gestionar',
            data={'accion': 'no_show', 'motivo': 'No asistio'},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(actividad)
        self.assertEqual(actividad.estado, 'cancelada')
        self.assertIn('No-show desde peluquería/barbería: No asistio', actividad.observaciones or '')

    def test_dashboard_muestra_turnero_visual_peluqueria(self):
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        fecha_hoy = today_local().isoformat()
        cliente = Cliente(nombre='Cliente Turnero Visual', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-VISUAL-001',
            nombre='Corte visual',
            categoria='Salon',
            costo=10000,
            precio=35000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='corte',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        self.client.post('/agenda/turnos/peluqueria/crear', data={
            'titulo': 'Corte visual - Cliente Turnero Visual',
            'usuario_id': str(self.admin.id_usuario),
            'cliente_id': str(cliente.id_cliente),
            'duracion': '30',
            'fecha_inicio': f'{fecha_hoy}T09:00',
            'fecha_fin': f'{fecha_hoy}T09:30',
            'servicio_turno_id': 'corte',
            'servicio_turno_nombre': 'Corte',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        })

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Turnero visual', html)
        self.assertIn('Mapa del día', html)
        self.assertIn('Cliente Turnero Visual', html)

    def test_dashboard_permita_ocultar_turnero_visual(self):
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')
        fecha_hoy = today_local().isoformat()
        cliente = Cliente(nombre='Cliente Turnero Oculto', tipo='minorista', activo=True)
        servicio = Servicio(
            codigo='TURNO-VISUAL-002',
            nombre='Barba visual',
            categoria='Salon',
            costo=10000,
            precio=28000,
            porcentaje_iva=10,
            activo=True,
            turno_rapido_tipo='barba',
        )
        db.session.add_all([cliente, servicio])
        db.session.commit()

        self.client.post('/agenda/turnos/peluqueria/crear', data={
            'titulo': 'Barba visual - Cliente Turnero Oculto',
            'usuario_id': str(self.admin.id_usuario),
            'cliente_id': str(cliente.id_cliente),
            'duracion': '30',
            'fecha_inicio': f'{fecha_hoy}T10:00',
            'fecha_fin': f'{fecha_hoy}T10:30',
            'servicio_turno_id': 'barba',
            'servicio_turno_nombre': 'Barba',
            'servicio_catalogo_id': str(servicio.id_servicio),
            'accion': 'crear',
        })

        set_dashboard_service_cards(self.admin, [
            'kpi_turnos_hoy',
            'kpi_en_atencion',
            'kpi_profesionales',
            'kpi_cobrado_hoy',
            'kpi_caja',
            'agenda_hoy',
            'profesionales_hoy',
            'caja_dia',
            'cobros_pendientes',
            'servicios_realizados',
            'clientes_panel',
            'insumos_criticos',
            'comisiones_dia',
        ])
        db.session.commit()
        _, selected_cards, _ = get_dashboard_service_cards(self.admin)

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('turnero_visual', selected_cards)
        self.assertIn(":class=\"{ 'hidden': !isCardVisible('turnero_visual') }\"", html)
        self.assertIn('class="hidden"', html)
        self.assertIn('Agenda de hoy', html)


if __name__ == '__main__':
    unittest.main()
