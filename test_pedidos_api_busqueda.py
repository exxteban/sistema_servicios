import unittest

from app import create_app, db


class TestPedidosApiBusqueda(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Permiso, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)
        self.permisos = {permiso.codigo: permiso for permiso in Permiso.query.all()}

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _login(self, usuario):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id_usuario)
            sess['_fresh'] = True

    def _crear_rol_con_permisos(self, nombre, codigos):
        from app.models import Rol

        rol = Rol(
            nombre=nombre,
            descripcion=f'Rol de pruebas {nombre}',
            nivel_jerarquia=5,
            activo=True,
        )
        for codigo in codigos:
            permiso = self.permisos.get(codigo)
            if permiso is not None:
                rol.permisos.append(permiso)
        db.session.add(rol)
        db.session.commit()
        return rol

    def _crear_usuario(self, username, rol):
        from app.models import Usuario

        usuario = Usuario(
            username=username,
            nombre_completo=username,
            id_rol=int(rol.id_rol),
            activo=True,
        )
        usuario.set_password('test1234')
        db.session.add(usuario)
        db.session.commit()
        return usuario

    def _crear_producto_simple(self, codigo='TEST-PED-API-001', precio=85000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Pedidos API').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Pedidos API', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=int(categoria.id_categoria),
            precio_compra=40000,
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=8,
            stock_minimo=1,
            es_servicio=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto

    def test_busqueda_productos_permite_usuario_con_permiso_editar(self):
        producto = self._crear_producto_simple()
        rol = self._crear_rol_con_permisos('Pedidos API Editor', ['editar_cliente'])
        usuario = self._crear_usuario('pedidos_api_editor', rol)
        self._login(usuario)

        response = self.client.get('/pedidos/api/productos?q=API-001&limit=20')

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('items'))
        self.assertEqual(int(data['items'][0]['id_producto']), int(producto.id_producto))


if __name__ == '__main__':
    unittest.main()
