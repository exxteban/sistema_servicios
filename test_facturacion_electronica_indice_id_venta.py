"""El índice UNIQUE histórico de `id_venta` y por qué rompe la nota de crédito.

`id_venta` nació UNIQUE, cuando una venta tenía un solo documento. Desde que
existen las notas de crédito y la re-facturación tiene varios: la factura, la
NC que la corrige, y el DE nuevo tras cancelar o inutilizar el anterior.

El modelo ya dice `index=True` sin unique, pero `create_all` no cambia un
índice que ya existe. Toda instalación creada antes sigue con el UNIQUE, y el
INSERT de la NC muere con "Duplicate entry '<id_venta>' for key
ix_facturacion_electronica_documentos_id_venta" — que es exactamente lo que
pasó en testserver2 el 2026-09-21 al emitir la primera NC real.
"""
import unittest
from datetime import datetime

from sqlalchemy import inspect, text

from app import create_app, db
from app.bootstrap.fe_schema import (
    _ensure_fe_documentos_id_venta_no_unico,
    _sentencias_id_venta_no_unico,
)
from app.bootstrap.fe_schema import FE_IDX_ID_VENTA, FE_IDX_ID_VENTA_TMP
from facturacion_electronica import ESTADO_APROBADO, TIPO_FACTURA, TIPO_NOTA_CREDITO

TABLA = 'facturacion_electronica_documentos'
INDICE = 'ix_facturacion_electronica_documentos_id_venta'


class TestIndiceIdVenta(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _indice(self):
        for definicion in inspect(db.engine).get_indexes(TABLA):
            if definicion['name'] == INDICE:
                return definicion
        return None

    def _volver_al_indice_viejo(self):
        """Deja la base como una instalación anterior a las notas de crédito."""
        with db.engine.begin() as conexion:
            conexion.execute(text(f'DROP INDEX IF EXISTS {INDICE}'))
            conexion.execute(text(f'CREATE UNIQUE INDEX {INDICE} ON {TABLA} (id_venta)'))

    def _venta(self):
        from app.models import Cliente, SesionCaja, Usuario, Venta

        admin = Usuario.query.filter_by(username='admin').first()
        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.flush()
        venta = Venta(
            id_cliente=db.session.get(Cliente, 1).id_cliente,
            id_sesion_caja=sesion.id_sesion,
            subtotal=100000, total=100000,
            fecha_venta=datetime.utcnow(), estado='completada',
        )
        db.session.add(venta)
        db.session.flush()
        return venta

    def test_una_base_nueva_ya_nace_con_el_indice_comun(self):
        indice = self._indice()
        self.assertIsNotNone(indice)
        self.assertFalse(indice['unique'])

    def test_el_indice_unico_viejo_rompe_la_nota_de_credito(self):
        """La reproducción del 500 del servidor, para que la corrección tenga
        algo que corregir."""
        from facturacion_electronica.models import DocumentoElectronico

        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA,
            estado=ESTADO_APROBADO, numero='0000001',
        ))
        db.session.commit()

        self._volver_al_indice_viejo()

        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO,
            id_devolucion=1, numero='0000001',
        ))
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    def test_el_arreglo_convierte_el_indice_y_la_nc_entra(self):
        from facturacion_electronica.models import DocumentoElectronico

        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA,
            estado=ESTADO_APROBADO, numero='0000001',
        ))
        db.session.commit()

        self._volver_al_indice_viejo()
        self.assertTrue(self._indice()['unique'])

        _ensure_fe_documentos_id_venta_no_unico(db)

        indice = self._indice()
        self.assertIsNotNone(indice, 'el índice no puede desaparecer: id_venta se filtra en cada pantalla')
        self.assertFalse(indice['unique'])

        # Y ahora la NC entra, que es el punto de todo esto.
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO,
            id_devolucion=1, numero='0000001',
        ))
        db.session.commit()
        self.assertEqual(
            DocumentoElectronico.query.filter_by(id_venta=venta.id_venta).count(), 2,
        )

    def test_es_idempotente(self):
        """Corre en cada arranque: no puede romper si ya está bien."""
        for _ in range(3):
            _ensure_fe_documentos_id_venta_no_unico(db)
        self.assertFalse(self._indice()['unique'])


class TestOrdenDelDDL(unittest.TestCase):
    """El orden de las sentencias, que es lo único que no se ve sin un MySQL.

    En InnoDB `id_venta` tiene una FK a `ventas`, que exige un índice que la
    sostenga. Borrar primero falla con 1553 "needed in a foreign key
    constraint" — y eso tumbó el arranque entero de testserver2 el 2026-09-21,
    porque esta migración corre fuera del try/except.
    """

    def test_mysql_crea_el_reemplazo_antes_de_borrar(self):
        sentencias = _sentencias_id_venta_no_unico('mysql')

        primera = sentencias[0].upper()
        self.assertTrue(primera.startswith('CREATE INDEX'),
                        f'la primera sentencia no puede ser un DROP: {sentencias[0]}')
        self.assertIn(FE_IDX_ID_VENTA_TMP, sentencias[0])

        posiciones = {s: i for i, s in enumerate(sentencias)}
        drop_unico = next(i for s, i in posiciones.items()
                          if s.startswith(f'DROP INDEX {FE_IDX_ID_VENTA} '))
        self.assertGreater(drop_unico, 0)

    def test_mysql_no_deja_el_indice_temporal(self):
        sentencias = _sentencias_id_venta_no_unico('mysql')
        self.assertTrue(
            any(s.startswith(f'DROP INDEX {FE_IDX_ID_VENTA_TMP}') for s in sentencias),
            'el índice temporal quedaría para siempre en la tabla',
        )
        # Y termina existiendo el canónico, que es el que el modelo declara.
        creados = [s for s in sentencias if s.startswith(f'CREATE INDEX {FE_IDX_ID_VENTA} ')]
        self.assertEqual(len(creados), 1)

    def test_sqlite_usa_el_camino_corto(self):
        sentencias = _sentencias_id_venta_no_unico('sqlite')
        self.assertEqual(len(sentencias), 2)
        self.assertNotIn(FE_IDX_ID_VENTA_TMP, ' '.join(sentencias))


class TestNoTumbaElArranque(unittest.TestCase):
    """Lo que de verdad hizo daño el 2026-09-21.

    La migración corre fuera del try/except general, así que su excepción se
    propagaba hasta `create_app` y el servicio no levantaba. Una base sin este
    arreglo rompe la nota de crédito; una excepción acá deja la app entera
    abajo, que es mucho peor.
    """

    def test_un_fallo_se_loguea_y_no_se_propaga(self):
        import logging

        class EngineRoto:
            @property
            def dialect(self):
                raise RuntimeError('base inaccesible')

        class DbRoto:
            engine = EngineRoto()

            class session:
                @staticmethod
                def rollback():
                    pass

        registro = []

        class LoggerFalso(logging.Logger):
            def __init__(self):
                super().__init__('falso')

            def exception(self, *args, **kwargs):
                registro.append(args)

        # No debe levantar.
        _ensure_fe_documentos_id_venta_no_unico(DbRoto(), LoggerFalso())

        self.assertEqual(len(registro), 1, 'el fallo tiene que quedar en el log')
        self.assertIn('Duplicate entry', registro[0][0])
