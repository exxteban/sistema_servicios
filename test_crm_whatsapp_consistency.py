import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app import create_app, db
from app.models import Permiso, Rol, Usuario
from app.models.crm_contacto import CrmContacto
from app.models.crm_nota_interna import CrmNotaInterna
from app.models.whatsapp import (
    WhatsAppAsignacionConversacion,
    WhatsAppConversacion,
    WhatsAppEstadoAsesor,
    WhatsAppMensaje,
)
from app.routes.crm import asesor as crm_asesor_routes
from app.utils.init_db import inicializar_datos_base


class TestCrmWhatsAppConsistency(unittest.TestCase):
    class _FakeUser:
        def __init__(self, id_usuario: int, *, admin: bool = False, supervisor: bool = False, permisos=None):
            self.id_usuario = id_usuario
            self._admin = admin
            self._supervisor = supervisor
            self._permisos = set(permisos or [])

        def es_admin(self):
            return self._admin

        def es_supervisor(self):
            return self._supervisor

        def tiene_permiso(self, codigo):
            return codigo in self._permisos

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

        self.get_pref_patcher = patch.object(Usuario, 'get_preferencia', lambda _self, _clave, default=None: default)
        self.get_pref_patcher.start()

        self.client = self.app.test_client()

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.supervisor_role = Rol.query.filter_by(nombre='Supervisor').first()
        self.asesor_role = Rol(nombre='Asesor CRM', descripcion='Rol de pruebas CRM', nivel_jerarquia=10, activo=True)
        permisos = Permiso.query.filter(Permiso.codigo.in_(['crm_whatsapp', 'crm_operar_como_asesor'])).all()
        for permiso in permisos:
            self.asesor_role.permisos.append(permiso)
        db.session.add(self.asesor_role)
        db.session.commit()

        self.assertIsNotNone(self.admin)
        self.assertIsNotNone(self.supervisor_role)
        self.assertIsNotNone(self.asesor_role)

        self.asesor_1 = self._crear_usuario('asesor_a')
        self.asesor_2 = self._crear_usuario('asesor_b')

    def tearDown(self):
        self.get_pref_patcher.stop()
        db.session.remove()

    def _crear_usuario(self, suffix: str) -> Usuario:
        user = Usuario(
            username=f'test_crm_{suffix}',
            nombre_completo=f'Test {suffix}',
            id_rol=self.asesor_role.id_rol,
            activo=True,
        )
        user.set_password('test1234')
        db.session.add(user)
        db.session.commit()
        return user

    def _login(self, user: Usuario):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user.id_usuario)
            sess['_fresh'] = True

    def _crear_conversacion_asignada(self, telefono: str, id_asesor: int, estado: str = 'activa'):
        conv = WhatsAppConversacion(
            telefono=telefono,
            nombre_contacto='Cliente Test',
            modo='asesor',
            activa=True,
        )
        db.session.add(conv)
        db.session.flush()

        msg = WhatsAppMensaje(
            id_conversacion=conv.id,
            direccion='entrante',
            remitente='cliente',
            contenido='Hola',
        )
        db.session.add(msg)

        asig = WhatsAppAsignacionConversacion(
            id_conversacion=conv.id,
            id_asesor=id_asesor,
            estado=estado,
        )
        db.session.add(asig)
        db.session.commit()
        return conv, asig

    def test_supervisor_tiene_permisos_crm_y_whatsapp(self):
        codigos = {p.codigo for p in self.supervisor_role.permisos.all()}
        self.assertIn('crm_whatsapp', codigos)
        self.assertIn('whatsapp_conversaciones', codigos)
        self.assertIn('crm_operar_como_asesor', codigos)

    def test_asesor_no_asignado_no_puede_ver_responder_ni_anotar(self):
        conv, _asig = self._crear_conversacion_asignada('5959test1001', self.asesor_1.id_usuario)
        fake_user = self._FakeUser(
            self.asesor_2.id_usuario,
            permisos={'crm_whatsapp', 'crm_operar_como_asesor'},
        )

        with self.app.test_request_context(f'/crm/api/asesor/conversacion/{conv.id}/mensajes', method='GET'):
            with patch('app.routes.crm.asesor.current_user', fake_user):
                resp_get = crm_asesor_routes.api_mensajes_conversacion(conv.id)
        self.assertEqual(resp_get[1], 403)

        with self.app.test_request_context(
            f'/crm/api/asesor/responder/{conv.id}',
            method='POST',
            json={'mensaje': 'Respuesta no autorizada'},
        ):
            with patch('app.routes.crm.asesor.current_user', fake_user):
                resp_post = crm_asesor_routes.api_responder(conv.id)
        self.assertEqual(resp_post[1], 403)

        with self.app.test_request_context(
            f'/crm/api/asesor/conversacion/{conv.id}/notas',
            method='POST',
            json={'contenido': 'Nota no autorizada'},
        ):
            with patch('app.routes.crm.asesor.current_user', fake_user):
                resp_nota = crm_asesor_routes.api_nota_conversacion(conv.id)
        self.assertEqual(resp_nota[1], 403)

    def test_admin_puede_ver_pero_no_operar_en_panel_asesor(self):
        conv, _asig = self._crear_conversacion_asignada('5959test1002', self.asesor_1.id_usuario)
        self._login(self.admin)

        resp_get = self.client.get(f'/crm/api/asesor/conversacion/{conv.id}/mensajes')
        self.assertEqual(resp_get.status_code, 200)

        resp_post = self.client.post(
            f'/crm/api/asesor/responder/{conv.id}',
            json={'mensaje': 'No debería poder responder'},
        )
        self.assertEqual(resp_post.status_code, 403)

    def test_admin_panel_asesor_muestra_cola_y_asignadas_en_solo_lectura(self):
        conv_asignada, _asig = self._crear_conversacion_asignada('5959test1003', self.asesor_1.id_usuario)
        conv_pendiente = WhatsAppConversacion(
            telefono='5959test1004',
            nombre_contacto='Cliente Pendiente',
            modo='derivacion',
            activa=True,
        )
        db.session.add(conv_pendiente)
        db.session.commit()

        self._login(self.admin)
        resp = self.client.get('/crm/api/asesor/conversaciones')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get('panel_mode'), 'control')

        pendientes_ids = {item['id'] for item in data.get('pendientes', [])}
        asignadas = {item['id']: item for item in data.get('mis_conversaciones', [])}

        self.assertIn(conv_pendiente.id, pendientes_ids)
        self.assertIn(conv_asignada.id, asignadas)
        self.assertEqual(asignadas[conv_asignada.id].get('asesor'), self.asesor_1.nombre_completo)

    def test_admin_panel_asesor_incluye_historico_cerrado(self):
        conv, _asig = self._crear_conversacion_asignada('5959test1005', self.asesor_1.id_usuario)
        self._login(self.asesor_1)
        resp_cierre = self.client.post(f'/crm/api/asesor/cerrar/{conv.id}')
        self.assertEqual(resp_cierre.status_code, 200)

        self._login(self.admin)
        resp = self.client.get('/crm/api/asesor/conversaciones')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        asignadas = {item['id']: item for item in data.get('mis_conversaciones', [])}
        self.assertIn(conv.id, asignadas)
        self.assertEqual(asignadas[conv.id].get('estado_asignacion'), 'cerrada')

    def test_admin_panel_asesor_separa_historiales_web_de_cola_operativa(self):
        conv_web = WhatsAppConversacion(
            telefono='WBS-9001',
            nombre_contacto='Cliente Web',
            modo='bot',
            activa=True,
            contexto=json.dumps({
                'web_bot': {
                    'id_sesion_web': 77,
                    'label': 'Bot tienda',
                    'slug_tienda': 'demo',
                },
                'web_chat': {
                    'session_token': 'token-demo',
                },
            }),
        )
        db.session.add(conv_web)
        db.session.flush()
        db.session.add(WhatsAppMensaje(
            id_conversacion=conv_web.id,
            direccion='entrante',
            remitente='cliente',
            contenido='¿Qué día es hoy?',
        ))
        db.session.commit()

        self._login(self.admin)
        resp = self.client.get('/crm/api/asesor/conversaciones')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        pendientes_ids = {item['id'] for item in data.get('pendientes', [])}

        self.assertNotIn(conv_web.id, pendientes_ids)
        self.assertEqual(data.get('historiales_total'), 1)

        resp_historial = self.client.get('/crm/api/asesor/historiales-web?periodo=all')
        self.assertEqual(resp_historial.status_code, 200)
        historiales_ids = {item['id'] for item in (resp_historial.get_json() or {}).get('items', [])}
        self.assertIn(conv_web.id, historiales_ids)

    def test_historiales_web_admiten_paginacion_y_filtros(self):
        for idx in range(3):
            conv = WhatsAppConversacion(
                telefono=f'WBS-91{idx}',
                nombre_contacto=f'Cliente Web {idx}',
                modo='bot',
                activa=True,
                ultima_actividad=datetime.utcnow() - timedelta(days=idx),
                contexto=json.dumps({'web_bot': {'id_sesion_web': 100 + idx}}),
            )
            db.session.add(conv)
        conv_cerrada = WhatsAppConversacion(
            telefono='WBS-9199',
            nombre_contacto='Cliente Web Cerrado',
            modo='bot',
            activa=False,
            ultima_actividad=datetime.utcnow(),
            contexto=json.dumps({'web_bot': {'id_sesion_web': 999}}),
        )
        db.session.add(conv_cerrada)
        db.session.commit()

        self._login(self.admin)
        resp = self.client.get('/crm/api/asesor/historiales-web?per_page=1&page=2&q=Cliente%20Web&estado=activas&periodo=all')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get('total'), 3)
        self.assertEqual(data.get('pages'), 3)
        self.assertEqual(data.get('page'), 2)
        self.assertEqual(len(data.get('items', [])), 1)
        self.assertTrue(all(item.get('activa') for item in data.get('items', [])))

    def test_panel_asesor_timeline_paginado_devuelve_lotes_ordenados(self):
        conv, _asig = self._crear_conversacion_asignada('5959test5001', self.asesor_1.id_usuario)
        base = datetime.utcnow() - timedelta(minutes=10)
        WhatsAppMensaje.query.filter_by(id_conversacion=conv.id).delete()
        db.session.commit()

        for idx in range(5):
            db.session.add(WhatsAppMensaje(
                id_conversacion=conv.id,
                direccion='entrante' if idx % 2 == 0 else 'saliente',
                remitente='cliente' if idx % 2 == 0 else 'asesor',
                contenido=f'msg-{idx}',
                created_at=base + timedelta(minutes=idx),
            ))
        db.session.commit()

        self._login(self.asesor_1)
        resp_page_1 = self.client.get(f'/crm/api/asesor/conversacion/{conv.id}/mensajes?limit=2')

        self.assertEqual(resp_page_1.status_code, 200)
        data_1 = resp_page_1.get_json() or {}
        contenidos_1 = [item.get('contenido') for item in data_1.get('items', []) if not item.get('es_evento')]
        self.assertEqual(contenidos_1, ['msg-3', 'msg-4'])
        self.assertTrue(data_1.get('has_more'))
        self.assertTrue(data_1.get('next_cursor'))

        resp_page_2 = self.client.get(
            f"/crm/api/asesor/conversacion/{conv.id}/mensajes?limit=2&cursor={data_1.get('next_cursor')}"
        )
        self.assertEqual(resp_page_2.status_code, 200)
        data_2 = resp_page_2.get_json() or {}
        contenidos_2 = [item.get('contenido') for item in data_2.get('items', []) if not item.get('es_evento')]
        self.assertEqual(contenidos_2, ['msg-1', 'msg-2'])
        self.assertTrue(data_2.get('has_more'))

    def test_nota_contacto_valida_coherencia_conversacion_contacto(self):
        contacto = CrmContacto(telefono='5959test2001', nombre='Contacto A')
        conv = WhatsAppConversacion(telefono='5959test2002', nombre_contacto='Contacto B', modo='bot', activa=True)
        db.session.add_all([contacto, conv])
        db.session.commit()

        self._login(self.asesor_1)
        resp = self.client.post(
            f'/crm/api/contactos/{contacto.id}/notas',
            json={'contenido': 'Nota inválida', 'id_conversacion': conv.id},
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('no pertenece', (data.get('error') or '').lower())

    def test_reasignar_sincroniza_contadores_y_estado(self):
        conv, asig = self._crear_conversacion_asignada('5959test3001', self.asesor_1.id_usuario)
        estado_origen = WhatsAppEstadoAsesor(
            id_usuario=self.asesor_1.id_usuario,
            online=True,
            conversaciones_activas=1,
            max_conversaciones=5,
        )
        estado_destino = WhatsAppEstadoAsesor(
            id_usuario=self.asesor_2.id_usuario,
            online=True,
            conversaciones_activas=0,
            max_conversaciones=5,
        )
        db.session.add_all([estado_origen, estado_destino])
        db.session.commit()

        self._login(self.admin)
        resp = self.client.post(
            '/crm/api/admin/reasignar',
            json={'id_conversacion': conv.id, 'id_asesor': self.asesor_2.id_usuario},
        )

        self.assertEqual(resp.status_code, 200)
        db.session.refresh(asig)
        db.session.refresh(conv)
        db.session.refresh(estado_origen)
        db.session.refresh(estado_destino)

        self.assertEqual(asig.id_asesor, self.asesor_2.id_usuario)
        self.assertEqual(asig.estado, 'pendiente')
        self.assertEqual(conv.modo, 'derivacion')
        self.assertEqual(estado_origen.conversaciones_activas, 0)
        self.assertEqual(estado_destino.conversaciones_activas, 1)

    def test_api_admin_asesores_excluye_usuarios_sin_permiso_operativo(self):
        rol_sin_crm = Rol(nombre='No CRM', descripcion='Sin acceso CRM', nivel_jerarquia=1, activo=True)
        db.session.add(rol_sin_crm)
        db.session.commit()

        intruso = Usuario(
            username='test_crm_intruso',
            nombre_completo='Usuario Sin CRM',
            id_rol=rol_sin_crm.id_rol,
            activo=True,
        )
        intruso.set_password('test1234')
        db.session.add(intruso)
        db.session.commit()

        self._login(self.admin)
        resp = self.client.get('/crm/api/admin/asesores')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        ids = {item['id_usuario'] for item in data.get('asesores', [])}

        self.assertIn(self.asesor_1.id_usuario, ids)
        self.assertIn(self.asesor_2.id_usuario, ids)
        self.assertNotIn(intruso.id_usuario, ids)

    def test_responder_devuelve_error_si_servicio_falla(self):
        conv, _asig = self._crear_conversacion_asignada('5959test4001', self.asesor_1.id_usuario)
        fake_user = self._FakeUser(
            self.asesor_1.id_usuario,
            permisos={'crm_whatsapp', 'crm_operar_como_asesor'},
        )

        with self.app.test_request_context(
            f'/crm/api/asesor/responder/{conv.id}',
            method='POST',
            json={'mensaje': 'Hola'},
        ):
            with patch('app.routes.crm.asesor.current_user', fake_user), patch(
                'app.routes.crm.asesor.enviar_mensaje_asesor',
                return_value={'ok': False, 'error': 'fallo controlado'},
            ):
                resp = crm_asesor_routes.api_responder(conv.id)

        self.assertEqual(resp[1], 400)
        data = resp[0].get_json() or {}
        self.assertEqual(data.get('error'), 'fallo controlado')

    def test_historial_asesor_permanece_accesible_tras_cierre_con_eventos(self):
        conv, _asig = self._crear_conversacion_asignada('5959test4002', self.asesor_1.id_usuario)
        self._login(self.asesor_1)

        resp_cierre = self.client.post(f'/crm/api/asesor/cerrar/{conv.id}')
        self.assertEqual(resp_cierre.status_code, 200)

        resp_historial = self.client.get(f'/crm/api/asesor/conversacion/{conv.id}/mensajes')
        self.assertEqual(resp_historial.status_code, 200)
        data = resp_historial.get_json() or {}

        tipos_evento = {item.get('tipo') for item in data.get('eventos', [])}
        self.assertIn('asesor_cerro_conversacion', tipos_evento)
        self.assertTrue(any(msg.get('contenido') == 'Hola' for msg in data.get('mensajes', [])))

    def test_monitor_ia_detalle_incluye_eventos_operativos(self):
        conv, _asig = self._crear_conversacion_asignada('5959test4003', self.asesor_1.id_usuario)
        self._login(self.asesor_1)
        self.client.post(f'/crm/api/asesor/cerrar/{conv.id}')

        self._login(self.admin)
        resp = self.client.get(f'/crm/api/monitor/conversacion/{conv.id}')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        tipos_evento = {item.get('tipo') for item in data.get('eventos', [])}
        self.assertIn('asesor_cerro_conversacion', tipos_evento)


if __name__ == '__main__':
    unittest.main()
