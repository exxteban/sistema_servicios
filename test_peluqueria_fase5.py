"""Fase 5 del plan de peluquería: equipo y presentación."""
import unittest

from app import db
from app.models import Configuracion, Usuario
from app.services.marca_rubro import construir_marca_rubro
from gastronomia.services.modo_operacion import MODO_SERVICIOS, establecer_modo_operacion
from test_peluqueria_fase1 import PeluqueriaTestBase


class Fase5TestBase(PeluqueriaTestBase):
    def setUp(self):
        super().setUp()
        establecer_modo_operacion(MODO_SERVICIOS, usuario_id=self.admin.id_usuario)
        db.session.commit()
        self._limpiar_cache_config()

    @staticmethod
    def _limpiar_cache_config():
        # El runtime guarda la configuración de la UI en `g`; en tests el contexto de app se comparte entre requests.
        from flask import g

        g.pop('_runtime_ui_config', None)

    def _otro_usuario(self, username='barbero1', nombre='Barbero Uno'):
        from app.models import Rol

        rol = Rol.query.filter(Rol.id_rol.notin_([self.admin.id_rol, 4])).order_by(Rol.id_rol.asc()).first()
        usuario = Usuario(username=username, nombre_completo=nombre, id_rol=rol.id_rol, activo=True)
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()
        return usuario


class TestMarcaSegunRubro(Fase5TestBase):
    def test_peluqueria_no_dice_gastronomica(self):
        dashboard = self.client.get('/').get_data(as_text=True)
        login = self.app.test_client().get('/auth/login').get_data(as_text=True)

        for html in (dashboard, login):
            for texto in ('Gastronómica', 'Gastronomía', 'Gastronom&#237;a', 'Gastron&#243;mica', 'Gastronomica'):
                self.assertNotIn(texto, html)
        self.assertIn('Peluquería · Barbería', dashboard)
        self.assertIn('Sistema de Gestión para Peluquería y Barbería', login)

    def test_nombre_de_empresa_tiene_prioridad(self):
        marca = construir_marca_rubro(modo='servicios', dashboard_id='peluqueria_barberia', nombre_empresa='Barbería Don Juan')

        self.assertEqual(marca['titulo'], 'Barbería Don Juan')
        self.assertEqual(marca['rubro'], 'Peluquería · Barbería')

    def test_gastronomia_siempre_igual(self):
        marca = construir_marca_rubro(modo='gastronomia', dashboard_id='peluqueria_barberia', nombre_empresa='Otra')

        self.assertTrue(marca['es_gastronomia'])
        self.assertEqual(marca['titulo'], 'Sistema de Gestión Gastronómica')

    def test_servicios_generico(self):
        Configuracion.establecer('dashboard_negocio_activo', 'servicios')
        self._limpiar_cache_config()

        html = self.client.get('/').get_data(as_text=True)

        self.assertNotIn('Gastronómica', html)
        self.assertNotIn('Gastronomía', html)
        # La base de prueba tiene nombre de empresa: tiene prioridad sobre el texto del rubro.
        nombre = Configuracion.obtener('nombre_empresa')
        self.assertIn(f"Dashboard Servicios - {nombre}".replace("'", '&#39;'), html)
        self.assertIn('Sistema de Gestión de Servicios', self.app.test_client().get('/auth/login').get_data(as_text=True))


class TestAtiendeClientes(Fase5TestBase):
    def _profesionales_alta(self):
        html = self.client.get('/agenda/turnos/peluqueria/nuevo').get_data(as_text=True)
        return html

    def test_sin_marcados_aparecen_todos(self):
        barbero = self._otro_usuario()

        html = self._profesionales_alta()

        self.assertIn('Barbero Uno', html)
        self.assertIn(self.admin.nombre_completo, html)

    def test_con_marcados_solo_esos(self):
        barbero = self._otro_usuario()
        barbero.atiende_clientes = True
        db.session.commit()

        alta = self._profesionales_alta()
        agenda = self.client.get('/agenda/peluqueria/dia').get_data(as_text=True)
        ocupados_admin = self.client.get('/agenda/api/peluqueria/ocupados', query_string={'profesional_id': self.admin.id_usuario, 'fecha': '2030-01-10'})

        self.assertIn('Barbero Uno', alta)
        self.assertNotIn(f'"nombre": "{self.admin.nombre_completo}"', alta)
        self.assertIn('Barbero Uno', agenda)
        self.assertEqual(agenda.count('agenda-dia-head agenda-dia-col'), 1)
        self.assertEqual(ocupados_admin.status_code, 404)

    def test_inactivo_marcado_no_cuenta(self):
        barbero = self._otro_usuario()
        barbero.atiende_clientes = True
        barbero.activo = False
        db.session.commit()

        self.assertIn(self.admin.nombre_completo, self._profesionales_alta())

    def test_checkbox_en_formularios_de_usuario(self):
        nuevo = self.client.get('/usuarios/nuevo').get_data(as_text=True)
        self.assertIn('name="atiende_clientes"', nuevo)

        barbero = self._otro_usuario()
        editar = self.client.get(f'/usuarios/{barbero.id_usuario}/editar').get_data(as_text=True)
        self.assertIn('name="atiende_clientes"', editar)

    def test_editar_guarda_atiende_clientes_y_no_lo_toca_sin_el_campo(self):
        barbero = self._otro_usuario()
        datos = {
            'username': barbero.username,
            'nombre_completo': barbero.nombre_completo,
            'id_rol': str(barbero.id_rol),
            'activo': 'on',
            'atiende_clientes_presente': '1',
            'atiende_clientes': '1',
        }
        self.client.post(f'/usuarios/{barbero.id_usuario}/editar', data=datos)
        db.session.refresh(barbero)
        self.assertTrue(barbero.atiende_clientes)

        datos.pop('atiende_clientes_presente')
        datos.pop('atiende_clientes')
        self.client.post(f'/usuarios/{barbero.id_usuario}/editar', data=datos)
        db.session.refresh(barbero)
        self.assertTrue(barbero.atiende_clientes)


class TestAccionesDelDashboard(Fase5TestBase):
    def test_tres_acciones_y_menu_mas(self):
        html = self.client.get('/').get_data(as_text=True)
        acciones, _, resto = html.partition('dashboard-acciones-mas')

        self.assertIn('Nuevo turno', acciones)
        self.assertIn('Agenda de hoy', acciones)
        self.assertIn('>Cobrar\n', acciones)
        menu = resto.split('</details>', 1)[0]
        for texto in ('Cargar servicio', 'Servicios y costos', 'Cliente nuevo'):
            self.assertIn(texto, menu)

    def test_dashboard_servicios_generico_no_cambia(self):
        Configuracion.establecer('dashboard_negocio_activo', 'servicios')
        self._limpiar_cache_config()

        html = self.client.get('/').get_data(as_text=True)

        self.assertNotIn('dashboard-acciones-mas', html)
        self.assertIn('Cargar servicio', html)
        self.assertIn('Cobrar servicio', html)


if __name__ == '__main__':
    unittest.main()
