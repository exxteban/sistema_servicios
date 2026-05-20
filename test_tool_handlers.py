import unittest
from datetime import datetime

from app.services.ia import tool_handlers as th


class _FakeQuery:
    def __init__(self, rep):
        self._rep = rep

    def get(self, _id_rep):
        return self._rep


class _FakeListQuery:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class _FakeHistorialQuery:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class _FakeHistorialItem:
    def __init__(self, estado_nuevo, fecha_cambio, nota=None):
        self.estado_nuevo = estado_nuevo
        self.fecha_cambio = fecha_cambio
        self.nota = nota


class _FakeReparacionModel:
    query = None


class _FakeRep:
    def __init__(self):
        self.id_reparacion = 9
        self.tipo_equipo = "Celular"
        self.marca_modelo = "Redmi K60"
        self.estado = "pendiente"
        self.falla_reportada = "No enciende"
        self.fecha_ingreso = datetime(2026, 2, 17)
        self.fecha_estimada = datetime(2026, 2, 18)
        self.fecha_estimada_hora = datetime(2026, 2, 18, 19, 8)
        self.nota_cliente = "En revisión"
        self.cliente = None
        self.diagnostico_tecnico = "Diagnostico"
        self.solucion = "Solucion"
        self.mostrar_costo = False
        self.costo_estimado = 0
        self.costo_final_calculado = 0
        self.abono = 0
        self.saldo_pendiente = 0
        self.historial_estados = _FakeHistorialQuery([
            _FakeHistorialItem("en_proceso", datetime(2026, 2, 18, 10, 30), "Se abrió el equipo"),
            _FakeHistorialItem("pendiente", datetime(2026, 2, 17, 9, 0), None),
        ])


class _FakeRepCosto:
    def __init__(self, tipo_equipo, marca_modelo, falla_reportada, costo_final_calculado=0, costo_estimado=0):
        self.tipo_equipo = tipo_equipo
        self.marca_modelo = marca_modelo
        self.falla_reportada = falla_reportada
        self.costo_final_calculado = costo_final_calculado
        self.costo_estimado = costo_estimado


class TestToolConsultarEstadoModoConsulta(unittest.TestCase):
    def setUp(self):
        self._original_reparacion = th.Reparacion
        fake_rep = _FakeRep()
        _FakeReparacionModel.query = _FakeQuery(fake_rep)
        th.Reparacion = _FakeReparacionModel

    def tearDown(self):
        th.Reparacion = self._original_reparacion

    def test_consultar_estado_solo_fecha(self):
        out = th._handle_consultar_estado(
            {"id_reparacion": 9, "modo_consulta": "solo_fecha"},
            {"telefono": "", "verificado": False},
        )
        self.assertEqual(out.get("modo_consulta"), "solo_fecha")
        self.assertEqual(out.get("fecha_estimada"), "18/02/2026")
        self.assertEqual(out.get("hora_estimada"), "19:08")
        self.assertNotIn("estado", out)

    def test_consultar_estado_modo_estado(self):
        out = th._handle_consultar_estado(
            {"id_reparacion": 9, "modo_consulta": "estado"},
            {"telefono": "", "verificado": False},
        )
        self.assertEqual(out.get("modo_consulta"), "estado")
        self.assertEqual(out.get("estado"), "pendiente")
        self.assertIn("estado_texto", out)
        self.assertNotIn("diagnostico", out)

    def test_consultar_estado_modo_invalido_caer_a_detalle(self):
        out = th._handle_consultar_estado(
            {"id_reparacion": 9, "modo_consulta": "cualquier_cosa"},
            {"telefono": "", "verificado": False},
        )
        self.assertEqual(out.get("modo_consulta"), "detalle")
        self.assertIn("nota_seguridad", out)

    def test_consultar_estado_puede_tomar_id_desde_contexto_verificado(self):
        out = th._handle_consultar_estado(
            {"modo_consulta": "estado"},
            {"telefono": "", "verificado": True, "reparacion_verificada": 9},
        )
        self.assertEqual(out.get("id_reparacion"), 9)
        self.assertEqual(out.get("modo_consulta"), "estado")

    def test_consultar_estado_detalle_incluye_seguimiento_publico(self):
        fake_rep = _FakeRep()
        fake_rep.mostrar_costo = True
        fake_rep.costo_estimado = 150000
        _FakeReparacionModel.query = _FakeQuery(fake_rep)

        out = th._handle_consultar_estado(
            {"id_reparacion": 9, "modo_consulta": "detalle"},
            {"telefono": "", "verificado": False},
        )

        seguimiento = out.get("seguimiento_publico") or {}
        self.assertEqual(seguimiento.get("equipo"), "Celular Redmi K60")
        self.assertEqual(seguimiento.get("fecha_ingreso_detalle"), "17/02/2026 00:00")
        self.assertEqual(seguimiento.get("costo_visible"), 150000.0)
        self.assertEqual(len(seguimiento.get("historial") or []), 2)
        self.assertEqual(seguimiento["historial"][0]["estado"], "en_proceso")


class TestToolEstimarPrecioReparacion(unittest.TestCase):
    def setUp(self):
        self._original_reparacion = th.Reparacion
        _FakeReparacionModel.query = _FakeListQuery([
            _FakeRepCosto("Celular", "Samsung A15", "cambio display", costo_final_calculado=180000),
            _FakeRepCosto("Celular", "Samsung A14", "display roto", costo_final_calculado=220000),
            _FakeRepCosto("Celular", "Xiaomi Redmi", "cambio bateria", costo_estimado=120000),
        ])
        th.Reparacion = _FakeReparacionModel

    def tearDown(self):
        th.Reparacion = self._original_reparacion

    def test_estimar_precio_reparacion_por_similares(self):
        out = th._handle_estimar_precio_reparacion(
            {"consulta": "cambio de display samsung"},
            {},
        )
        rango = out.get("rango_estimado") or {}
        self.assertEqual(out.get("criterio"), "similares")
        self.assertEqual(rango.get("min"), 180000)
        self.assertEqual(rango.get("max"), 220000)
        self.assertEqual(rango.get("moneda"), "Gs")

    def test_estimar_precio_reparacion_fallback_historico(self):
        out = th._handle_estimar_precio_reparacion(
            {"consulta": "microfono nokia antiguo"},
            {},
        )
        self.assertEqual(out.get("criterio"), "historico_general")
        self.assertEqual(out.get("confianza"), "baja")
        self.assertGreaterEqual(out.get("cantidad_referencias", 0), 1)


if __name__ == "__main__":
    unittest.main()
