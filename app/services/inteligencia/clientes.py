from __future__ import annotations

from datetime import date

from sqlalchemy import func

from app import db
from app.models import Cliente, Venta
from app.services.inteligencia.common import formatear_moneda
from app.utils.helpers import local_strftime
from app.utils.phone_utils import formatear_telefono_display, normalizar_telefono

DIAS_CLIENTE_DORMIDO = 45


def obtener_inteligencia_clientes(fecha_corte: date) -> dict:
    filas = (
        db.session.query(
            Cliente.id_cliente,
            Cliente.nombre,
            Cliente.telefono,
            func.max(Venta.fecha_venta).label('ultima_compra'),
            func.count(Venta.id_venta).label('cantidad_compras'),
            func.coalesce(func.sum(Venta.total), 0).label('total_gastado'),
        )
        .join(Venta, Venta.id_cliente == Cliente.id_cliente)
        .filter(
            Cliente.activo.is_(True),
            Cliente.id_cliente != 1,
            Venta.estado == 'completada',
        )
        .group_by(Cliente.id_cliente, Cliente.nombre, Cliente.telefono)
        .all()
    )

    registros = []
    for fila in filas:
        ultima_compra = getattr(fila, 'ultima_compra', None)
        if ultima_compra is None:
            continue

        cantidad_compras = int(getattr(fila, 'cantidad_compras', 0) or 0)
        total_gastado = float(getattr(fila, 'total_gastado', 0) or 0)
        ticket_promedio = total_gastado / cantidad_compras if cantidad_compras > 0 else 0
        dias_inactivo = max((fecha_corte - ultima_compra.date()).days, 0)
        telefono = (getattr(fila, 'telefono', '') or '').strip()
        telefono_normalizado = normalizar_telefono(telefono) if telefono else None
        registros.append({
            'id_cliente': int(fila.id_cliente),
            'nombre': (fila.nombre or '').strip() or f'Cliente #{fila.id_cliente}',
            'ultima_compra': ultima_compra,
            'cantidad_compras': cantidad_compras,
            'total_gastado': total_gastado,
            'ticket_promedio': ticket_promedio,
            'dias_inactivo': dias_inactivo,
            'telefono': telefono,
            'telefono_normalizado': telefono_normalizado,
        })

    if not registros:
        return _clientes_sin_resultados()

    umbral_alto_valor = _percentil([item['total_gastado'] for item in registros], 0.8)
    umbral_ticket_alto = _percentil([item['ticket_promedio'] for item in registros], 0.75)

    candidatos = []
    registros_dormidos = []
    registros_frecuentes = []
    registros_alto_valor = []
    candidatos_valiosos = []
    candidatos_frecuentes = []
    total_dormidos = 0
    total_frecuentes = 0
    total_alto_valor = 0
    valiosos_dormidos = 0
    frecuentes_en_pausa = 0

    for registro in registros:
        es_dormido = registro['dias_inactivo'] >= DIAS_CLIENTE_DORMIDO
        es_frecuente = registro['cantidad_compras'] >= 3
        es_alto_valor = registro['total_gastado'] > 0 and registro['total_gastado'] >= umbral_alto_valor
        es_ticket_alto = registro['ticket_promedio'] > 0 and registro['ticket_promedio'] >= umbral_ticket_alto
        es_poca_recurrencia = registro['cantidad_compras'] <= 2
        registro['es_dormido'] = es_dormido
        registro['es_frecuente'] = es_frecuente
        registro['es_alto_valor'] = es_alto_valor

        if es_dormido:
            total_dormidos += 1
            registros_dormidos.append(registro)
        if es_frecuente:
            total_frecuentes += 1
            registros_frecuentes.append(registro)
        if es_alto_valor:
            total_alto_valor += 1
            registros_alto_valor.append(registro)
        if es_dormido and es_alto_valor:
            valiosos_dormidos += 1
        if es_dormido and es_frecuente:
            frecuentes_en_pausa += 1

        if not es_dormido:
            continue

        prioridad, motivo, accion = _clasificar_cliente(
            dias_inactivo=registro['dias_inactivo'],
            es_alto_valor=es_alto_valor,
            es_frecuente=es_frecuente,
            es_ticket_alto=es_ticket_alto,
            es_poca_recurrencia=es_poca_recurrencia,
        )
        puntaje = _calcular_puntaje_prioridad(prioridad, registro['total_gastado'], registro['dias_inactivo'])
        candidato = {
            **registro,
            'prioridad': prioridad,
            'motivo': motivo,
            'accion': accion,
            'puntaje': puntaje,
        }
        candidatos.append(candidato)
        if es_alto_valor:
            candidatos_valiosos.append(candidato)
        if es_frecuente:
            candidatos_frecuentes.append(candidato)

    candidatos_ordenados = _ordenar_candidatos_por_prioridad(candidatos)
    clientes_para_activar = [_serializar_cliente_inteligencia(candidato) for candidato in candidatos_ordenados[:8]]

    return {
        'total_para_activar': len(candidatos_ordenados),
        'segmentos': {
            'dormidos': total_dormidos,
            'frecuentes': total_frecuentes,
            'alto_valor': total_alto_valor,
        },
        'clientes_para_activar': clientes_para_activar,
        'para_activar_detalle': [_serializar_cliente_inteligencia(candidato) for candidato in candidatos_ordenados[:25]],
        'segmentos_detalle': {
            'para_activar': [_serializar_cliente_inteligencia(candidato) for candidato in candidatos_ordenados[:25]],
            'dormidos': _serializar_clientes_segmento(registros_dormidos, limite=25),
            'frecuentes': _serializar_clientes_segmento(registros_frecuentes, limite=25),
            'alto_valor': _serializar_clientes_segmento(registros_alto_valor, limite=25),
            'valiosos_dormidos': _serializar_clientes_segmento(candidatos_valiosos, limite=25),
            'frecuentes_en_pausa': _serializar_clientes_segmento(candidatos_frecuentes, limite=25),
        },
        'valiosos_dormidos': valiosos_dormidos,
        'frecuentes_en_pausa': frecuentes_en_pausa,
    }


def _clientes_sin_resultados() -> dict:
    return {
        'total_para_activar': 0,
        'segmentos': {'dormidos': 0, 'frecuentes': 0, 'alto_valor': 0},
        'clientes_para_activar': [],
        'para_activar_detalle': [],
        'segmentos_detalle': {
            'para_activar': [],
            'dormidos': [],
            'frecuentes': [],
            'alto_valor': [],
            'valiosos_dormidos': [],
            'frecuentes_en_pausa': [],
        },
        'valiosos_dormidos': 0,
        'frecuentes_en_pausa': 0,
    }


def _clasificar_cliente(
    dias_inactivo: int,
    es_alto_valor: bool,
    es_frecuente: bool,
    es_ticket_alto: bool,
    es_poca_recurrencia: bool,
) -> tuple[str, str, str]:
    if es_alto_valor and es_frecuente:
        return ('alta', f'Compraba seguido y lleva {dias_inactivo} días sin volver.', 'Llamar hoy')
    if es_alto_valor:
        return ('alta', f'Tiene gasto acumulado alto y está dormido hace {dias_inactivo} días.', 'Ofrecer beneficio')
    if es_frecuente:
        return ('media', f'Era recurrente y no compra hace {dias_inactivo} días.', 'Enviar reactivación')
    if es_ticket_alto and es_poca_recurrencia:
        return ('media', f'Deja buen ticket, pero lleva {dias_inactivo} días sin comprar.', 'Ofrecer recompra')
    return ('baja', f'Cliente inactivo hace {dias_inactivo} días.', 'Enviar saludo')


def _calcular_puntaje_prioridad(prioridad: str, total_gastado: float, dias_inactivo: int) -> tuple[int, float, int]:
    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    return (prioridad_orden.get(prioridad, 99), -float(total_gastado or 0), -int(dias_inactivo or 0))


def _percentil(valores: list[float], proporcion: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(float(valor or 0) for valor in valores)
    if len(ordenados) == 1:
        return ordenados[0]
    indice = int(round((len(ordenados) - 1) * proporcion))
    indice = max(0, min(indice, len(ordenados) - 1))
    return ordenados[indice]


def _ordenar_candidatos_por_prioridad(clientes: list[dict]) -> list[dict]:
    return sorted(clientes, key=lambda item: (
        item.get('puntaje', (99, 0, 0)),
        -float(item.get('total_gastado', 0) or 0),
        -int(item.get('dias_inactivo', 0) or 0),
        item.get('nombre', '').lower(),
    ))


def _serializar_clientes_segmento(clientes: list[dict], limite: int = 25) -> list[dict]:
    clientes_ordenados = sorted(clientes, key=lambda item: (
        -int(item.get('dias_inactivo', 0) or 0),
        -float(item.get('total_gastado', 0) or 0),
        item.get('nombre', '').lower(),
    ))
    return [_serializar_cliente_inteligencia(cliente) for cliente in clientes_ordenados[:limite]]


def _serializar_cliente_inteligencia(cliente: dict) -> dict:
    telefono_normalizado = (cliente.get('telefono_normalizado') or '').strip()
    telefono = (cliente.get('telefono') or '').strip()
    telefono_label = formatear_telefono_display(telefono_normalizado) if telefono_normalizado else (telefono or 'Sin teléfono cargado')
    whatsapp_url = f"https://wa.me/{telefono_normalizado.replace('+', '')}" if telefono_normalizado else None
    telefono_enlace = f"tel:{telefono_normalizado.replace('+', '')}" if telefono_normalizado else None

    return {
        'id_cliente': cliente['id_cliente'],
        'nombre': cliente['nombre'],
        'ultima_compra_label': local_strftime(cliente['ultima_compra'], '%d/%m/%Y'),
        'dias_inactivo': cliente['dias_inactivo'],
        'cantidad_compras': cliente['cantidad_compras'],
        'total_gastado_label': formatear_moneda(cliente['total_gastado']),
        'ticket_promedio_label': formatear_moneda(cliente['ticket_promedio']),
        'prioridad': cliente.get('prioridad', 'baja'),
        'motivo': cliente.get('motivo', ''),
        'accion': cliente.get('accion', 'Revisar cliente'),
        'telefono_label': telefono_label,
        'telefono_enlace': telefono_enlace,
        'whatsapp_url': whatsapp_url,
    }
