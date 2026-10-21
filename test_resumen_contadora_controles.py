"""Controles de datos del resumen para el/la contador/a.

Compras sin timbrado, compras cuyo IVA no cierra con el total y RUC con el
dígito verificador mal: lo que Marangatu rechazaría. Todo es pendiente.
"""
from datetime import date, datetime

from app import db
from app.models import Cliente, Compra, Configuracion, Proveedor, Usuario, Venta
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

from test_facturacion_electronica_proveedor_base import BaseProveedorApi

PRIMERO = date(2026, 9, 1)


class TestControlesContadora(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        db.session.commit()

    def _compra(self, numero, total, iva10, timbrado='12345678', ruc='80012345-0'):
        proveedor = Proveedor.query.filter_by(ruc=ruc).first()
        if proveedor is None:
            proveedor = Proveedor(nombre=f'Proveedor {ruc}', ruc=ruc)
            db.session.add(proveedor)
            db.session.flush()
        compra = Compra(numero_factura=numero, timbrado=timbrado, id_proveedor=proveedor.id_proveedor,
                        id_usuario=Usuario.query.filter_by(username='admin').first().id_usuario,
                        fecha_compra=date(2026, 9, 10), subtotal=total, total=total,
                        total_iva_10=iva10, total_iva_5=0, estado='completada')
        db.session.add(compra)
        db.session.commit()
        return compra

    def test_digito_verificador_del_ruc(self):
        from app.services.resumen_contadora_controles import ruc_invalido
        from facturacion_electronica.services.validacion import digito_verificador_ruc

        bueno = f'80012345-{digito_verificador_ruc("80012345")}'
        malo = f'80012345-{(digito_verificador_ruc("80012345") + 1) % 10}'
        self.assertFalse(ruc_invalido(bueno))
        self.assertTrue(ruc_invalido(malo))
        self.assertTrue(ruc_invalido('80012345-X'))
        self.assertFalse(ruc_invalido('4281292'))            # cédula: no tiene DV
        self.assertFalse(ruc_invalido(''))
        self.assertFalse(ruc_invalido('00000000-0'))         # consumidor final

    def test_controles_del_mes(self):
        from app.services.resumen_contadora import resumen_del_mes
        from facturacion_electronica.services.validacion import digito_verificador_ruc

        dv = digito_verificador_ruc('80012345')
        ruc_bueno, ruc_malo = f'80012345-{dv}', f'80012345-{(dv + 1) % 10}'
        self._compra('001-001-0000001', 110000, 10000, ruc=ruc_bueno)           # todo bien
        self._compra('001-001-0000002', 110000, 10000, timbrado=None, ruc=ruc_bueno)
        self._compra('001-001-0000003', 50000, 10000, ruc=ruc_bueno)            # IVA > total/11
        self._compra('001-001-0000004', 110000, 10000, ruc=ruc_malo)
        self._compra('001-001-0000005', 110000, 10000, ruc=ruc_malo)            # mismo proveedor: una vez
        cliente = Cliente(nombre='Cliente con RUC mal', ruc_ci=ruc_malo)
        db.session.add(cliente)
        db.session.flush()
        db.session.add(Venta(id_cliente=cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
                             subtotal=11000, total=11000, total_iva_10=1000, numero_factura='001-001-0000009',
                             fecha_venta=datetime(2026, 9, 15, 15)))
        db.session.commit()

        r = resumen_del_mes(PRIMERO, fe_activa=False)
        c = r['controles']

        self.assertEqual([f['numero'] for f in c['compras_sin_timbrado']['filas']], ['001-001-0000002'])
        self.assertEqual([f['numero'] for f in c['iva_no_cierra']['filas']], ['001-001-0000003'])
        self.assertEqual(sorted(f['tipo'] for f in c['ruc_invalidos']['filas']), ['Cliente', 'Proveedor'])
        self.assertEqual(c['cantidad'], 4)
        self.assertEqual(r['pendientes'], 4)

        # Con SIFEN el RUC del cliente lo valida la emisión: no se repite acá.
        self.assertEqual(resumen_del_mes(PRIMERO, fe_activa=True)['controles']['ruc_invalidos']['cantidad'], 1)

        usuario = Usuario.query.filter_by(username='admin').first()
        cliente_http = self.app.test_client()
        with cliente_http.session_transaction() as sesion:
            sesion['_user_id'] = str(usuario.id_usuario)
            sesion['_fresh'] = True
        html = cliente_http.get('/contador/iva?mes=2026-09').get_data(as_text=True)
        self.assertIn('compra(s) con factura sin timbrado', html)
        self.assertIn('más IVA del que el total permite', html)
        self.assertIn('dígito verificador mal', html)

    def test_compra_guarda_el_timbrado_al_editar(self):
        compra = self._compra('001-001-0000001', 110000, 10000, timbrado=None)
        usuario = Usuario.query.filter_by(username='admin').first()
        cliente_http = self.app.test_client()
        with cliente_http.session_transaction() as sesion:
            sesion['_user_id'] = str(usuario.id_usuario)
            sesion['_fresh'] = True

        assert 'name="timbrado"' in cliente_http.get(f'/compras/{compra.id_compra}/editar').get_data(as_text=True)
        cliente_http.post(f'/compras/{compra.id_compra}/editar', data={
            'numero_factura': '001-001-0000001', 'timbrado': ' 15151515 ', 'fecha_compra': '2026-09-10',
            'id_proveedor': compra.id_proveedor,
        })

        db.session.refresh(compra)
        self.assertEqual(compra.timbrado, '15151515')
