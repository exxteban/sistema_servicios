"""Pruebas de humo: los cambios del módulo peluquería/barbería no deben alterar el modo gastronomía."""
import unittest
from datetime import timedelta

from app import create_app, db
from app.models import AgendaActividad, Configuracion, Usuario
from app.utils.helpers import today_local
from app.utils.init_db import inicializar_datos_base
from gastronomia.services.modo_operacion import (
    MODO_GASTRONOMIA,
    establecer_modo_operacion,
    obtener_modo_operacion,
)


class TestPeluqueriaNoAfectaGastronomia(unittest.TestCase):
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
        establecer_modo_operacion(MODO_GASTRONOMIA, usuario_id=self.admin.id_usuario)
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()

    def _loguear(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def test_inicio_redirige_a_gastronomia(self):
        self._loguear()
        response = self.client.get('/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/gastronomia', response.headers['Location'])

    def test_login_mantiene_marca_gastronomica(self):
        html = self.client.get('/auth/login').get_data(as_text=True)

        self.assertIn('<title>Iniciar Sesion - Sistema de Gestion Gastronomica</title>', html)
        self.assertIn('Sistema de Gesti&#243;n para Gastronom&#237;a', html)

    def test_layout_mantiene_marca_gastronomica(self):
        self._loguear()
        response = self.client.get('/gastronomia/')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Sistema de Gestión Gastronómica', html)
        self.assertIn("'Sistema de Gestión Gastronómica'", html)

    def test_formulario_de_usuario_no_muestra_atiende_clientes(self):
        self._loguear()

        html = self.client.get('/usuarios/nuevo').get_data(as_text=True)

        self.assertNotIn('atiende_clientes', html)

    def test_turno_peluqueria_no_cambia_modo_ni_dashboard(self):
        self._loguear()
        dashboard_antes = Configuracion.obtener('dashboard_negocio_activo', None)
        fecha = (today_local() + timedelta(days=1)).strftime('%Y-%m-%d')

        response = self.client.post(
            '/agenda/turnos/peluqueria/crear',
            data={
                'usuario_id': str(self.admin.id_usuario),
                'servicio_turno_id': 'corte',
                'servicio_turno_nombre': 'Corte',
                'fecha_inicio': f'{fecha}T10:00',
                'duracion': '30',
                'accion': 'crear',
            },
        )

        self.assertIn(response.status_code, (200, 302))
        self.assertEqual(AgendaActividad.query.filter_by(tipo='cita').count(), 1)
        self.assertEqual(obtener_modo_operacion(), MODO_GASTRONOMIA)
        self.assertEqual(Configuracion.obtener('dashboard_negocio_activo', None), dashboard_antes)


class TestMigracionBasesExistentes(unittest.TestCase):
    """Las instalaciones de gastronomía ya tienen la tabla de agenda: la columna nueva se agrega sola."""

    def test_no_hay_claves_de_tabla_duplicadas_en_migraciones(self):
        import ast
        import collections
        from pathlib import Path

        import app.bootstrap.schema as schema

        arbol = ast.parse(Path(schema.__file__).read_text(encoding='utf-8'))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Assign) and any(getattr(t, 'id', '') == 'SCHEMA_COLUMN_MIGRATIONS' for t in nodo.targets):
                claves = [k.value for k in nodo.value.keys]
                duplicadas = [k for k, n in collections.Counter(claves).items() if n > 1]
                self.assertEqual(duplicadas, [])
                return
        self.fail('No se encontró SCHEMA_COLUMN_MIGRATIONS')

    def test_base_vieja_recibe_columna_sena_monto(self):
        from sqlalchemy import text

        from app.bootstrap.schema import _apply_sqlite_migrations, _sqlite_columns

        app = create_app('testing')
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            db.session.execute(text('ALTER TABLE agenda_actividades DROP COLUMN sena_monto'))
            db.session.commit()
            self.assertNotIn('sena_monto', _sqlite_columns(db, 'agenda_actividades'))

            _apply_sqlite_migrations(db)

            self.assertIn('sena_monto', _sqlite_columns(db, 'agenda_actividades'))
            db.session.remove()


if __name__ == '__main__':
    unittest.main()
