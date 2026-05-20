import unittest
from datetime import datetime, timedelta

from app import create_app, db
from app.models import AgendaActividad, Usuario
from app.models.agenda_actividad import (
    agenda_actividad_recordatorio_usuarios,
    agenda_actividad_visible_usuarios,
)
from app.utils.init_db import inicializar_datos_base


class TestAgendaDeleteSync(unittest.TestCase):
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

        self.viewer = Usuario(
            username='agenda_viewer_test',
            nombre_completo='Agenda Viewer Test',
            id_rol=self.admin.id_rol,
            activo=True,
        )
        self.viewer.set_password('test1234')
        db.session.add(self.viewer)
        db.session.commit()

        self.admin_client = self.app.test_client()
        self.viewer_client = self.app.test_client()
        self._login(self.admin_client, self.admin)
        self._login(self.viewer_client, self.viewer)

    def tearDown(self):
        db.session.remove()

    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id_usuario)
            sess['_fresh'] = True

    def _crear_actividad_visible_y_recordatorio(self):
        actividad = AgendaActividad(
            titulo='Llamar cliente agenda',
            tipo='llamada',
            fecha_inicio=datetime.utcnow() - timedelta(minutes=30),
            estado='pendiente',
            prioridad='alta',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            mostrar_agenda_en='usuarios_especificos',
            recordatorio_a='usuarios_especificos',
            recordatorio_minutos=0,
        )
        actividad.usuarios_agenda = [self.viewer]
        actividad.usuarios_recordatorio = [self.viewer]
        db.session.add(actividad)
        db.session.commit()
        return actividad

    def test_eliminar_actividad_limpia_destinatarios_y_alertas(self):
        actividad = self._crear_actividad_visible_y_recordatorio()

        resumen_antes = self.viewer_client.get('/agenda/api/alertas/resumen')
        self.assertEqual(resumen_antes.status_code, 200)
        payload_antes = resumen_antes.get_json()
        self.assertTrue(any(item['id'] == actividad.id for item in payload_antes['items']))

        response = self.admin_client.post(
            f'/agenda/actividades/{actividad.id}/eliminar',
            headers={
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['eliminada'])
        self.assertEqual(payload['id'], actividad.id)

        db.session.expire_all()
        self.assertIsNone(db.session.get(AgendaActividad, actividad.id))

        visibles_restantes = db.session.execute(
            agenda_actividad_visible_usuarios.select().where(
                agenda_actividad_visible_usuarios.c.actividad_id == actividad.id
            )
        ).fetchall()
        recordatorios_restantes = db.session.execute(
            agenda_actividad_recordatorio_usuarios.select().where(
                agenda_actividad_recordatorio_usuarios.c.actividad_id == actividad.id
            )
        ).fetchall()
        self.assertEqual(visibles_restantes, [])
        self.assertEqual(recordatorios_restantes, [])

        db.session.remove()
        resumen_despues = self.viewer_client.get('/agenda/api/alertas/resumen')
        self.assertEqual(resumen_despues.status_code, 200)
        payload_despues = resumen_despues.get_json()
        self.assertFalse(any(item['id'] == actividad.id for item in payload_despues['items']))

        estado_lista = self.viewer_client.get(
            f'/agenda/api/actividades/estado?ids={actividad.id}'
        )
        self.assertEqual(estado_lista.status_code, 200)
        payload_estado_lista = estado_lista.get_json()
        self.assertEqual(payload_estado_lista['items'], [])
        self.assertEqual(payload_estado_lista['missing_ids'], [actividad.id])

    def test_estado_lista_incluye_nueva_actividad_visible_para_otra_sesion(self):
        actividad = self._crear_actividad_visible_y_recordatorio()

        estado_lista = self.viewer_client.get('/agenda/api/actividades/estado?page=1')
        self.assertEqual(estado_lista.status_code, 200)
        payload_estado_lista = estado_lista.get_json()

        self.assertIn(actividad.id, payload_estado_lista['page_ids'])
        self.assertTrue(any(item['id'] == actividad.id for item in payload_estado_lista['items']))


if __name__ == '__main__':
    unittest.main()
