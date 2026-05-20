import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import event

from app import create_app, db
from app.models import AgendaActividad, Usuario
from app.routes.main import _obtener_resumen_agenda_dashboard
from app.utils.helpers import utc_bounds_for_local_dates
from app.utils.init_db import inicializar_datos_base


class _FakeAdminUser:
    def __init__(self, id_usuario):
        self.id_usuario = id_usuario

    def es_admin(self):
        return True

    def tiene_permiso(self, _permiso):
        return True


class TestDashboardAgendaResumen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
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
        self.today = date(2026, 3, 28)

    def tearDown(self):
        db.session.remove()

    @contextmanager
    def _capture_selects(self):
        statements = []

        def before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
            if (statement or '').lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', before_cursor_execute)
        try:
            yield statements
        finally:
            event.remove(db.engine, 'before_cursor_execute', before_cursor_execute)

    def _crear_actividad(self, titulo, fecha_inicio, estado='pendiente'):
        actividad = AgendaActividad(
            titulo=titulo,
            tipo='tarea_interna',
            fecha_inicio=fecha_inicio,
            estado=estado,
            prioridad='media',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            mostrar_agenda_en='todos',
            recordatorio_a='solo_responsable',
        )
        db.session.add(actividad)
        db.session.commit()
        return actividad

    def test_resumen_agenda_consolida_metricas_en_dos_selects(self):
        start_utc, end_utc = utc_bounds_for_local_dates(self.today, self.today)
        vencida = self._crear_actividad('Vencida', start_utc - timedelta(hours=2))
        hoy_primera = self._crear_actividad('Hoy 1', start_utc + timedelta(hours=1))
        hoy_segunda = self._crear_actividad('Hoy 2', start_utc + timedelta(hours=3))
        self._crear_actividad('Futura', end_utc + timedelta(hours=1))
        self._crear_actividad('Completada', start_utc + timedelta(hours=2), estado='completada')

        with patch('app.routes.main.current_user', _FakeAdminUser(self.admin.id_usuario)):
            with self._capture_selects() as statements:
                resumen = _obtener_resumen_agenda_dashboard(True, self.today)

        self.assertTrue(resumen['can_ver_agenda'])
        self.assertEqual(resumen['total_pendientes'], 4)
        self.assertEqual(resumen['pendientes_hoy'], 2)
        self.assertEqual(resumen['vencidas'], 1)
        self.assertEqual(
            [item['id'] for item in resumen['proximas_actividades']],
            [hoy_primera.id, hoy_segunda.id],
        )
        agenda_statements = [
            statement for statement in statements
            if 'agenda_actividades' in (statement or '').lower()
        ]
        self.assertEqual(len(agenda_statements), 2)
        self.assertTrue(any('sum(case' in statement.lower() for statement in agenda_statements))
        self.assertTrue(any('order by' in statement.lower() for statement in agenda_statements))
        self.assertNotIn(
            vencida.id,
            [item['id'] for item in resumen['proximas_actividades']],
        )

    def test_resumen_agenda_sin_permiso_no_ejecuta_queries(self):
        with self._capture_selects() as statements:
            resumen = _obtener_resumen_agenda_dashboard(False, self.today)

        self.assertFalse(resumen['can_ver_agenda'])
        self.assertEqual(resumen['total_pendientes'], 0)
        self.assertEqual(resumen['pendientes_hoy'], 0)
        self.assertEqual(resumen['vencidas'], 0)
        self.assertEqual(resumen['proximas_actividades'], [])
        self.assertEqual(statements, [])


if __name__ == '__main__':
    unittest.main()
