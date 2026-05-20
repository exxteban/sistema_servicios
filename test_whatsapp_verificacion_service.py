import unittest
from datetime import datetime, timedelta

from app.services.whatsapp import verificacion_service as vs


class _FakeColumn:
    def __gt__(self, _other):
        return True


class _FakeSession:
    def commit(self):
        return None


class _FakeConv:
    def __init__(self):
        self.intentos_codigo_fallidos = 2
        self.bloqueado_hasta = None


class _FakeRegistro:
    def __init__(self, id_reparacion=44):
        self.id_reparacion = id_reparacion
        self.usado = False
        self.expira_at = datetime.utcnow() + timedelta(days=1)


class _FakeConvQuery:
    def __init__(self, conv):
        self._conv = conv

    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return self._conv


class _FakeCodigoQuery:
    def __init__(self, registro):
        self._registro = registro

    def filter_by(self, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._registro


class _FakeWhatsAppConversacion:
    query = None


class _FakeWhatsAppCodigoVerificacion:
    query = None
    expira_at = _FakeColumn()


class TestWhatsAppVerificacionService(unittest.TestCase):
    def setUp(self):
        self._original_conv = vs.WhatsAppConversacion
        self._original_codigo = vs.WhatsAppCodigoVerificacion
        self._original_session = vs.db.session
        self._original_normalizar = vs.normalizar_telefono

    def tearDown(self):
        vs.WhatsAppConversacion = self._original_conv
        vs.WhatsAppCodigoVerificacion = self._original_codigo
        vs.db.session = self._original_session
        vs.normalizar_telefono = self._original_normalizar

    def test_verificar_codigo_ok_no_consumir_codigo_impreso(self):
        conv = _FakeConv()
        registro = _FakeRegistro()
        _FakeWhatsAppConversacion.query = _FakeConvQuery(conv)
        _FakeWhatsAppCodigoVerificacion.query = _FakeCodigoQuery(registro)

        vs.WhatsAppConversacion = _FakeWhatsAppConversacion
        vs.WhatsAppCodigoVerificacion = _FakeWhatsAppCodigoVerificacion
        vs.db.session = _FakeSession()
        vs.normalizar_telefono = lambda telefono: telefono

        out = vs.verificar_codigo("+595981123456", "123456")

        self.assertTrue(out.get("verificado"))
        self.assertEqual(out.get("id_reparacion"), 44)
        self.assertFalse(registro.usado)
        self.assertEqual(conv.intentos_codigo_fallidos, 0)
        self.assertIsNone(conv.bloqueado_hasta)


if __name__ == "__main__":
    unittest.main()
