import unittest

from app import create_app, db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_CANCELADO, ESTADO_GENERADO
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.emision_service import obtener_documento


class TestRefacturacion(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import SesionCaja, Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        sesion = SesionCaja(id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta')
        db.session.add(sesion)
        db.session.commit()

        from app.models.venta import Venta

        venta = Venta(id_cliente=1, id_sesion_caja=sesion.id_sesion, subtotal=0, total=0)
        db.session.add(venta)
        db.session.commit()
        self.venta_id = venta.id_venta

    def tearDown(self):
        DocumentoElectronico.query.filter_by(id_venta=self.venta_id).delete()
        db.session.commit()
        db.session.rollback()
        self.ctx.pop()

    def test_permite_varios_de_por_venta_y_devuelve_el_vigente(self):
        cancelado = DocumentoElectronico(
            id_venta=self.venta_id, estado=ESTADO_CANCELADO, numero='0000001'
        )
        db.session.add(cancelado)
        db.session.commit()

        # Antes esto fallaba por el UNIQUE en id_venta; ahora debe convivir.
        nuevo = DocumentoElectronico(
            id_venta=self.venta_id, estado=ESTADO_GENERADO, numero='0000002'
        )
        db.session.add(nuevo)
        db.session.commit()

        vigente = obtener_documento(self.venta_id)
        self.assertEqual(vigente.id, nuevo.id)
        self.assertEqual(vigente.estado, ESTADO_GENERADO)

        total = DocumentoElectronico.query.filter_by(id_venta=self.venta_id).count()
        self.assertEqual(total, 2)


if __name__ == '__main__':
    unittest.main()
