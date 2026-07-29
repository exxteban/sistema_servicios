from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.utils.helpers import local_strftime, utc_isoformat
from gastronomia.routes.public_routes import _evento_dict


class _Evento:
    tipo = 'pedido_cobrado'
    fecha_evento = datetime(2026, 7, 29, 11, 42)


def test_evento_publico_declara_utc_para_conversion_del_navegador():
    evento = _evento_dict(_Evento())

    assert evento['fecha_evento'] == '2026-07-29T11:42:00Z'


def test_evento_publico_incluye_la_hora_ya_formateada_en_zona_local():
    evento = _evento_dict(_Evento())

    assert evento['fecha_evento_label'] == local_strftime(_Evento.fecha_evento)
    assert evento['fecha_evento_label'] != '29/07/2026 11:42'


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


def test_seguimiento_fuerza_la_zona_horaria_configurada_en_el_navegador():
    template_path = (
        Path(__file__).parent
        / 'gastronomia'
        / 'templates'
        / 'gastronomia'
        / 'seguimiento_pedido.html'
    )
    template = template_path.read_text(encoding='utf-8')

    assert 'var APP_TIMEZONE = {{ timezone_name|tojson }};' in template
    assert 'timeZone: APP_TIMEZONE' in template


def test_seguimiento_usa_la_etiqueta_del_servidor_al_repintar():
    template_path = (
        Path(__file__).parent
        / 'gastronomia'
        / 'templates'
        / 'gastronomia'
        / 'seguimiento_pedido.html'
    )
    template = template_path.read_text(encoding='utf-8')

    assert 'displayDate(event.fecha_evento_label, event.fecha_evento)' in template
    assert 'displayDate(data.pedido.fecha_modificacion_label, data.pedido.fecha_modificacion)' in template
