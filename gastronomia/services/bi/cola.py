"""Cola de envio asistido: candidatos disponibles y resumen para el tablero (BI-02)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.bi_models import GastronomiaBiContacto, GastronomiaBiNoContactar
from gastronomia.services.bi.cola_config import SEGMENTOS_PLANTILLA, leer_config, plantilla
from gastronomia.services.bi.historial import historial_clientes
from gastronomia.services.bi.plantillas import contexto_negocio, renderizar
from gastronomia.services.bi.segmentos import HABITUAL_AUSENTE, clasificar_segmentos

ESTADOS_CERRADOS = ('enviado', 'omitido')


def hoy_local() -> date:
    return utc_naive_to_local(datetime.utcnow()).date()


def clave_contacto(candidato: dict) -> tuple:
    return (candidato['telefono'], candidato['segmento'], int(candidato['ultimo_pedido_id']))


def construir_cola(cliente_id: int, hoy: date) -> tuple[dict, list[dict]]:
    """Devuelve (historial, candidatos disponibles en orden). No aplica el limite diario."""
    historial = historial_clientes(cliente_id)
    cfg = leer_config(cliente_id)
    candidatos = clasificar_segmentos(
        historial, hoy, segunda_min=cfg['segunda_min'], segunda_max=cfg['segunda_max'],
    )
    no_contactar = _telefonos_no_contactar(cliente_id)
    recientes = _telefonos_enviados_recientes(cliente_id, cfg['frecuencia_dias'])
    cerrados = _claves_cerradas(cliente_id)
    disponibles = [
        candidato for candidato in candidatos
        if candidato['telefono'] not in no_contactar
        and candidato['telefono'] not in recientes
        and clave_contacto(candidato) not in cerrados
    ]
    disponibles.sort(key=lambda c: (c['segmento'] != HABITUAL_AUSENTE, -c['dias_sin_comprar'], c['telefono']))
    return historial, disponibles


def contar_enviados_hoy(cliente_id: int, hoy: date) -> int:
    inicio, fin = utc_bounds_for_local_dates(hoy, hoy)
    return GastronomiaBiContacto.query.filter(
        GastronomiaBiContacto.cliente_id == int(cliente_id),
        GastronomiaBiContacto.estado == 'enviado',
        GastronomiaBiContacto.fecha_estado >= inicio,
        GastronomiaBiContacto.fecha_estado < fin,
    ).count()


def motivo(candidato: dict) -> str:
    if candidato['segmento'] == HABITUAL_AUSENTE:
        return f"Suele pedir cada {candidato['intervalo_dias']} días y hace {candidato['dias_sin_comprar']} que no pide."
    return f"Pidió una sola vez, hace {candidato['dias_sin_comprar']} días."


def mensaje_para(cliente_id: int, candidato: dict, contexto: dict | None = None) -> str:
    contexto = contexto or contexto_negocio(cliente_id)
    return renderizar(
        candidato['segmento'],
        plantilla(cliente_id, candidato['segmento']),
        nombre=candidato['nombre'],
        plato=candidato['plato_favorito'],
        negocio=contexto['negocio'],
        link=contexto['link'],
    )


def resumen_cola(cliente_id: int, hoy: date | None = None) -> dict:
    hoy = hoy or hoy_local()
    cfg = leer_config(cliente_id)
    historial, disponibles = construir_cola(cliente_id, hoy)
    enviados = contar_enviados_hoy(cliente_id, hoy)
    limite_alcanzado = enviados >= cfg['limite_dia']
    siguiente = None
    if disponibles and not limite_alcanzado:
        contexto = contexto_negocio(cliente_id)
        candidato = disponibles[0]
        siguiente = {
            **candidato,
            'ultima_compra_label': candidato['ultima_compra'].strftime('%d/%m/%Y'),
            'motivo': motivo(candidato),
            'mensaje': mensaje_para(cliente_id, candidato, contexto),
        }
    return {
        'hay_telefonos': bool(historial),
        'en_cola': len(disponibles),
        'enviados_hoy': enviados,
        'limite_dia': cfg['limite_dia'],
        'limite_alcanzado': limite_alcanzado,
        'frecuencia_dias': cfg['frecuencia_dias'],
        'siguiente': siguiente,
        'config': cfg,
        'plantillas': {segmento: plantilla(cliente_id, segmento) for segmento in SEGMENTOS_PLANTILLA},
    }


def _telefonos_no_contactar(cliente_id: int) -> set[str]:
    filas = (
        GastronomiaBiNoContactar.query
        .with_entities(GastronomiaBiNoContactar.telefono_normalizado)
        .filter_by(cliente_id=int(cliente_id))
        .all()
    )
    return {fila[0] for fila in filas}


def _telefonos_enviados_recientes(cliente_id: int, frecuencia_dias: int) -> set[str]:
    desde = datetime.utcnow() - timedelta(days=frecuencia_dias)
    filas = (
        GastronomiaBiContacto.query
        .with_entities(GastronomiaBiContacto.telefono_normalizado)
        .filter(
            GastronomiaBiContacto.cliente_id == int(cliente_id),
            GastronomiaBiContacto.estado == 'enviado',
            GastronomiaBiContacto.fecha_estado >= desde,
        )
        .all()
    )
    return {fila[0] for fila in filas}


def _claves_cerradas(cliente_id: int) -> set[tuple]:
    filas = GastronomiaBiContacto.query.filter(
        GastronomiaBiContacto.cliente_id == int(cliente_id),
        GastronomiaBiContacto.estado.in_(ESTADOS_CERRADOS),
    ).all()
    return {(fila.telefono_normalizado, fila.segmento, int(fila.ultimo_pedido_id)) for fila in filas}
