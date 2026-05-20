import unittest
from decimal import Decimal

from app import create_app, db
from app.models import Cliente, Configuracion, Permiso, Rol, Usuario
from control_de_empleados import CLAVE_MODULO_CONTROL_EMPLEADOS, DESC_MODULO_CONTROL_EMPLEADOS
from control_de_empleados.models import Empleado


class TestUsuariosClienteScope(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.rol_no_admin = Rol.query.filter(
            Rol.activo == True,
            Rol.id_rol != self.admin.id_rol,
        ).order_by(Rol.nivel_jerarquia.asc()).first()
        self.permiso_ver_control = Permiso.query.filter_by(codigo='ver_control_empleados').first()
        self.permiso_gestionar_control = Permiso.query.filter_by(codigo='gestionar_control_empleados').first()
        assert self.admin is not None
        assert self.rol_no_admin is not None
        assert self.permiso_ver_control is not None
        assert self.permiso_gestionar_control is not None

        Configuracion.establecer_bool(
            CLAVE_MODULO_CONTROL_EMPLEADOS,
            True,
            DESC_MODULO_CONTROL_EMPLEADOS,
        )

        self.cliente_a = Cliente(nombre='Cliente Scope A', tipo='minorista', activo=True)
        self.cliente_b = Cliente(nombre='Cliente Scope B', tipo='minorista', activo=True)
        db.session.add_all([self.cliente_a, self.cliente_b])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _login(self, usuario):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(usuario.id_usuario)
            session['_fresh'] = True

    def test_editar_usuario_permite_asignar_cliente(self):
        usuario = Usuario(
            username='vendedora_cliente_edit',
            nombre_completo='Vendedora Edit',
            id_rol=self.rol_no_admin.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()

        self._login(self.admin)
        response = self.client.post(
            f'/usuarios/{usuario.id_usuario}/editar',
            data={
                'username': usuario.username,
                'nombre_completo': usuario.nombre_completo,
                'id_rol': str(usuario.id_rol),
                'id_cliente': str(self.cliente_a.id_cliente),
                'activo': '1',
            },
            follow_redirects=False,
        )

        usuario_actualizado = db.session.get(Usuario, usuario.id_usuario)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(usuario_actualizado)
        self.assertEqual(usuario_actualizado.id_cliente, self.cliente_a.id_cliente)
        self.assertEqual(usuario_actualizado.cliente_id, self.cliente_a.id_cliente)

    def test_control_empleados_usa_cliente_asignado_del_usuario(self):
        usuario = Usuario(
            username='vendedora_control_scope',
            nombre_completo='Vendedora Scope',
            id_rol=self.rol_no_admin.id_rol,
            id_cliente=self.cliente_a.id_cliente,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.flush()
        usuario.permisos_adicionales.append(self.permiso_ver_control)

        empleado_visible = Empleado(
            nombre_completo='Empleado Visible',
            salario_base=Decimal('2100000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=self.cliente_a.id_cliente,
        )
        empleado_oculto = Empleado(
            nombre_completo='Empleado Oculto',
            salario_base=Decimal('2200000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=self.cliente_b.id_cliente,
        )
        db.session.add_all([empleado_visible, empleado_oculto])
        db.session.commit()

        self._login(usuario)
        response = self.client.get('/control-empleados/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Empleado Visible', html)
        self.assertNotIn('Empleado Oculto', html)

    def test_editar_usuario_permite_permiso_control_empleados_sin_cliente(self):
        usuario = Usuario(
            username='vendedora_control_global',
            nombre_completo='Vendedora Global',
            id_rol=self.rol_no_admin.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()

        self._login(self.admin)
        response = self.client.post(
            f'/usuarios/{usuario.id_usuario}/editar',
            data={
                'username': usuario.username,
                'nombre_completo': usuario.nombre_completo,
                'id_rol': str(usuario.id_rol),
                'id_cliente': '',
                'activo': '1',
                'permisos_extra': [str(self.permiso_ver_control.id_permiso)],
            },
            follow_redirects=False,
        )

        usuario_actualizado = db.session.get(Usuario, usuario.id_usuario)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(usuario_actualizado.id_cliente)
        self.assertTrue(usuario_actualizado.tiene_permiso('ver_control_empleados'))

    def test_control_empleados_sin_cliente_usa_scope_global_legacy(self):
        usuario = Usuario(
            username='cajero_control_global',
            nombre_completo='Cajero Control Global',
            id_rol=self.rol_no_admin.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.flush()
        usuario.permisos_adicionales.append(self.permiso_gestionar_control)

        empleado_global = Empleado(
            nombre_completo='Empleado Global Legacy',
            salario_base=Decimal('2100000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=None,
        )
        empleado_scoped = Empleado(
            nombre_completo='Empleado Scoped Oculto',
            salario_base=Decimal('2200000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=self.cliente_a.id_cliente,
        )
        db.session.add_all([empleado_global, empleado_scoped])
        db.session.commit()

        self._login(usuario)
        response = self.client.get('/control-empleados/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Empleado Global Legacy', html)
        self.assertNotIn('Empleado Scoped Oculto', html)
        self.assertIn('Nuevo empleado', html)

    def test_permiso_gestionar_control_empleados_permite_ver_listado(self):
        usuario = Usuario(
            username='cajero_control_gestionar',
            nombre_completo='Cajero Gestionar Control',
            id_rol=self.rol_no_admin.id_rol,
            id_cliente=self.cliente_a.id_cliente,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.flush()
        usuario.permisos_adicionales.append(self.permiso_gestionar_control)

        empleado_visible = Empleado(
            nombre_completo='Empleado Gestion Visible',
            salario_base=Decimal('2100000.00'),
            tipo_pago='mensual',
            activo=True,
            cliente_id=self.cliente_a.id_cliente,
        )
        db.session.add(empleado_visible)
        db.session.commit()

        self._login(usuario)
        response = self.client.get('/control-empleados/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Empleado Gestion Visible', html)
        self.assertIn('Nuevo empleado', html)


if __name__ == '__main__':
    unittest.main()
