import unittest

from sqlalchemy import text

from app import create_app, db
from facturacion_electronica import TIPO_FACTURA, TIPO_NOTA_CREDITO
from facturacion_electronica.models import DocumentoElectronico, SecuenciaNumeracionDE
from facturacion_electronica.services.numeracion_service import (
    NUMERO_MAX,
    ajustar_secuencia,
    listar_secuencias,
    peek_proximo_numero,
    reservar_numero,
)


class TestNumeracionDE(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()
        SecuenciaNumeracionDE.query.delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        SecuenciaNumeracionDE.query.delete()
        db.session.commit()
        self.ctx.pop()

    def test_reserva_es_correlativa_y_formatea_siete_digitos(self):
        n1, e1 = reservar_numero('001', '001')
        n2, e2 = reservar_numero('001', '001')
        self.assertIsNone(e1)
        self.assertIsNone(e2)
        self.assertEqual(n1, '0000001')
        self.assertEqual(n2, '0000002')

    def test_secuencia_independiente_por_establecimiento_punto(self):
        reservar_numero('001', '001')
        n_otro, _ = reservar_numero('001', '002')
        self.assertEqual(n_otro, '0000001')

    def test_peek_no_consume_numero(self):
        self.assertEqual(peek_proximo_numero('001', '001'), '0000001')
        self.assertEqual(peek_proximo_numero('001', '001'), '0000001')
        n, _ = reservar_numero('001', '001')
        self.assertEqual(n, '0000001')
        self.assertEqual(peek_proximo_numero('001', '001'), '0000002')

    def test_normaliza_codigos_a_tres_digitos(self):
        n, _ = reservar_numero('1', '1')
        self.assertEqual(n, '0000001')
        seq = SecuenciaNumeracionDE.query.filter_by(establecimiento='001', punto='001').first()
        self.assertIsNotNone(seq)

    def test_rechaza_al_agotar_el_rango_del_timbrado(self):
        seq = SecuenciaNumeracionDE(establecimiento='001', punto='001', ultimo_numero=NUMERO_MAX)
        db.session.add(seq)
        db.session.commit()
        numero, error = reservar_numero('001', '001')
        self.assertIsNone(numero)
        self.assertIn('rango', error.lower())


class TestAjusteDeCorrelativo(unittest.TestCase):
    """El admin fija el correlativo a mano: reset previo a produccion (las pruebas
    en ambiente test consumen numeros) o siembra al migrar de otro sistema."""

    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()
        # Lo que se prueba es la consulta del correlativo, no la integridad
        # referencial: se insertan documentos sueltos sin armar toda la cadena
        # cliente -> caja -> sesion -> venta, que no aporta nada a este caso.
        db.session.execute(text('PRAGMA foreign_keys=OFF'))
        SecuenciaNumeracionDE.query.delete()
        DocumentoElectronico.query.delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        SecuenciaNumeracionDE.query.delete()
        DocumentoElectronico.query.delete()
        db.session.commit()
        self.ctx.pop()

    def test_reset_a_cero_despues_de_las_pruebas(self):
        for _ in range(15):
            reservar_numero('001', '001')
        db.session.commit()

        seq, error = ajustar_secuencia('001', '001', 0)

        self.assertIsNone(error)
        self.assertEqual(seq.ultimo_numero, 0)
        self.assertEqual(peek_proximo_numero('001', '001'), '0000001')

    def test_siembra_el_ultimo_numero_de_otro_sistema(self):
        seq, error = ajustar_secuencia('002', '001', 1250)

        self.assertIsNone(error)
        self.assertEqual(seq.ultimo_numero, 1250)
        self.assertEqual(peek_proximo_numero('002', '001'), '0001251')

    def test_no_deja_bajar_por_debajo_de_un_numero_ya_emitido(self):
        db.session.add(DocumentoElectronico(
            id_venta=1, establecimiento='001', punto='001', numero='0000042',
        ))
        db.session.commit()

        seq, error = ajustar_secuencia('001', '001', 10)

        self.assertIsNone(seq)
        self.assertIn('0000042', error)

    def test_forzar_permite_bajarlo_igual(self):
        db.session.add(DocumentoElectronico(
            id_venta=1, establecimiento='001', punto='001', numero='0000042',
        ))
        db.session.commit()

        seq, error = ajustar_secuencia('001', '001', 10, forzar=True)

        self.assertIsNone(error)
        self.assertEqual(seq.ultimo_numero, 10)

    def test_documentos_de_otro_punto_no_frenan_el_ajuste(self):
        db.session.add(DocumentoElectronico(
            id_venta=1, establecimiento='002', punto='001', numero='0000900',
        ))
        db.session.commit()

        seq, error = ajustar_secuencia('001', '001', 0)

        self.assertIsNone(error)
        self.assertEqual(seq.ultimo_numero, 0)

    def test_rechaza_valores_fuera_de_rango_o_no_numericos(self):
        _, error_alto = ajustar_secuencia('001', '001', NUMERO_MAX + 1)
        _, error_negativo = ajustar_secuencia('001', '001', -1)
        _, error_texto = ajustar_secuencia('001', '001', 'abc')

        self.assertIsNotNone(error_alto)
        self.assertIsNotNone(error_negativo)
        self.assertIn('entero', error_texto)

    def test_normaliza_codigos_al_ajustar(self):
        seq, error = ajustar_secuencia('1', '2', 5)

        self.assertIsNone(error)
        self.assertEqual(seq.establecimiento, '001')
        self.assertEqual(seq.punto, '002')

    def test_listado_muestra_proximo_y_maximo_emitido(self):
        reservar_numero('001', '001')
        db.session.add(DocumentoElectronico(
            id_venta=1, establecimiento='001', punto='001', numero='0000001',
        ))
        db.session.commit()

        filas = listar_secuencias()

        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['establecimiento'], '001')
        self.assertEqual(filas[0]['ultimo_numero'], 1)
        self.assertEqual(filas[0]['proximo'], '0000002')
        self.assertEqual(filas[0]['max_emitido'], 1)


class TestSecuenciaPorTipoDocumento(unittest.TestCase):
    """La secuencia pasó a llevar un rango por tipo de documento."""

    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()
        SecuenciaNumeracionDE.query.delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        SecuenciaNumeracionDE.query.delete()
        db.session.commit()
        self.ctx.pop()

    def test_factura_y_nota_de_credito_conviven_en_el_mismo_punto(self):
        factura, _e = reservar_numero('001', '001', TIPO_FACTURA)
        nota, _e = reservar_numero('001', '001', TIPO_NOTA_CREDITO)
        db.session.commit()

        self.assertEqual(factura, '0000001')
        self.assertEqual(nota, '0000001')
        self.assertEqual(peek_proximo_numero('001', '001', TIPO_FACTURA), '0000002')
        self.assertEqual(peek_proximo_numero('001', '001', TIPO_NOTA_CREDITO), '0000002')

    def test_migracion_desde_la_tabla_vieja_conserva_el_correlativo(self):
        """Instalación existente: UNIQUE(establecimiento, punto) impedía el
        segundo tipo. La migración rehace la tabla sin perder la fila."""
        from app.bootstrap.fe_schema import _ensure_fe_secuencia_por_tipo

        tabla = 'facturacion_electronica_secuencia'
        with db.engine.begin() as conexion:
            conexion.execute(text(f'DROP TABLE {tabla}'))
            conexion.execute(text(f"""
                CREATE TABLE {tabla} (
                    id INTEGER NOT NULL PRIMARY KEY,
                    establecimiento VARCHAR(3) NOT NULL,
                    punto VARCHAR(3) NOT NULL,
                    ultimo_numero INTEGER NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT uq_fe_secuencia_estab_punto UNIQUE (establecimiento, punto)
                )
            """))
            conexion.execute(text(
                f"INSERT INTO {tabla} (id, establecimiento, punto, ultimo_numero, updated_at) "
                "VALUES (1, '001', '001', 42, '2026-01-01 00:00:00')"
            ))
            conexion.execute(text(
                f'ALTER TABLE {tabla} ADD COLUMN tipo_documento INTEGER NOT NULL DEFAULT 1'
            ))

        _ensure_fe_secuencia_por_tipo(db)

        # El correlativo de la factura sobrevivió intacto...
        self.assertEqual(peek_proximo_numero('001', '001', TIPO_FACTURA), '0000043')
        # ...y ahora el mismo punto admite el rango de la nota de crédito.
        nota, error = reservar_numero('001', '001', TIPO_NOTA_CREDITO)
        db.session.commit()
        self.assertIsNone(error)
        self.assertEqual(nota, '0000001')

    def test_la_migracion_es_idempotente(self):
        from app.bootstrap.fe_schema import _ensure_fe_secuencia_por_tipo

        reservar_numero('001', '001', TIPO_FACTURA)
        db.session.commit()
        _ensure_fe_secuencia_por_tipo(db)
        _ensure_fe_secuencia_por_tipo(db)
        self.assertEqual(peek_proximo_numero('001', '001', TIPO_FACTURA), '0000002')


if __name__ == '__main__':
    unittest.main()
