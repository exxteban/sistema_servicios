"""Rol "Contador/a": entra al área Contador/a y a nada más del negocio.

`ver_area_contador` se siembra al arrancar y el rol queda listo para asignar.
Con ese rol se ve el resumen de IVA (y se puede marcar el mes presentado),
pero no la caja, los reportes ni el POS.
"""
from app import db
from app.models import Rol, Usuario
from app.services.contador_permisos import PERMISO_AREA_CONTADOR, ROL_CONTADOR, ensure_rol_contador

from test_facturacion_electronica_proveedor_base import BaseProveedorApi


class TestRolContador(BaseProveedorApi):
    def _contadora(self):
        rol = Rol.query.filter_by(nombre=ROL_CONTADOR).one()
        usuario = Usuario(username='contadora', nombre_completo='María Contadora', id_rol=rol.id_rol, activo=True)
        usuario.set_password('una-clave-larga-123')
        db.session.add(usuario)
        db.session.commit()
        http = self.app.test_client()
        with http.session_transaction() as sesion:
            sesion['_user_id'] = str(usuario.id_usuario)
            sesion['_fresh'] = True
        return http

    def test_el_rol_se_crea_al_arrancar_con_su_permiso_y_es_idempotente(self):
        rol = Rol.query.filter_by(nombre=ROL_CONTADOR).one()
        self.assertEqual([p.codigo for p in rol.permisos.all()], [PERMISO_AREA_CONTADOR])
        ensure_rol_contador()
        self.assertEqual(Rol.query.filter_by(nombre=ROL_CONTADOR).count(), 1)
        self.assertEqual(rol.permisos.count(), 1)

    def test_contadora_ve_el_area_y_nada_mas(self):
        http = self._contadora()

        respuesta = http.get('/contador/iva?mes=2026-09')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        self.assertIn('data-sidebar-trigger="contador"', html)
        self.assertIn('Marcar como presentado', html)
        self.assertNotIn('Talonarios de factura', html)       # configurar es del dueño

        for url in ('/caja/', '/reportes/', '/ventas/pos', '/contador/talonarios'):
            self.assertEqual(http.get(url).status_code, 302, url)
