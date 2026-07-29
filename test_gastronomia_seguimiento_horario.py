from datetime import datetime, timedelta, timezone

from app.utils.helpers import utc_isoformat
from gastronomia.routes.public_routes import _evento_dict


class _Evento:
    tipo = 'pedido_cobrado'
    fecha_evento = datetime(2026, 7, 29, 11, 42)


def test_evento_publico_declara_utc_para_conversion_del_navegador():
    evento = _evento_dict(_Evento())

    assert evento['fecha_evento'] == '2026-07-29T11:42:00Z'


def test_utc_isoformat_normaliza_fechas_con_zona():
    fecha_con_zona = datetime(
        2026,
        7,
        29,
        8,
        42,
        tzinfo=timezone(timedelta(hours=-3)),
    )

    assert utc_isoformat(fecha_con_zona) == '2026-07-29T11:42:00Z'
