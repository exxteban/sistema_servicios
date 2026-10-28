"""Asigna una fecha a cada bloque de ventas y detecta lo que no cuadra.

Si el bloque trae fecha propia se usa esa. Si no, se busca en la hoja de
totales por dia un total igual (o muy parecido) que todavia no este usado.
"""
from __future__ import annotations

from decimal import Decimal

from gastronomia.services.importacion.excel_lector import Bloque, TotalDiario


TOLERANCIA_PARECIDO = Decimal('0.10')


def resolver_dias(bloques: list[Bloque], totales: list[TotalDiario]) -> tuple[list[dict], list[dict]]:
    usados: set[int] = set()
    dias = [_dia_base(indice, bloque) for indice, bloque in enumerate(bloques)]

    for dia, bloque in zip(dias, bloques):
        if bloque.fecha:
            _verificar_con_totales(dia, bloque, totales, usados)
    for dia, bloque in zip(dias, bloques):
        if not bloque.fecha:
            _buscar_fecha_por_total(dia, bloque, totales, usados)

    sin_detalle = [
        {'fecha': total.fecha.isoformat(), 'monto': float(total.monto), 'hoja': total.hoja, 'fila': total.fila}
        for indice, total in enumerate(totales)
        if indice not in usados
    ]
    return dias, sin_detalle


def _dia_base(indice: int, bloque: Bloque) -> dict:
    suma = bloque.suma
    avisos = []
    if bloque.total_excel is not None and bloque.total_excel != suma:
        avisos.append(
            f'La suma de las filas ({_fmt(suma)}) no coincide con el Total escrito ({_fmt(bloque.total_excel)}). '
            'Se importa lo que suman las filas.'
        )
    sin_monto = [fila.fila for fila in bloque.filas if fila.monto is None]
    if sin_monto:
        avisos.append(f'Filas sin monto (se omiten): {", ".join(str(n) for n in sin_monto)}.')
    return {
        'indice': indice,
        'hoja': bloque.hoja,
        'fila_inicio': bloque.fila_inicio,
        'fila_fin': bloque.fila_fin,
        'fecha_texto': bloque.fecha_texto,
        'fecha': bloque.fecha.isoformat() if bloque.fecha else None,
        'origen_fecha': 'excel' if bloque.fecha else None,
        'filas': len([fila for fila in bloque.filas if fila.monto is not None]),
        'suma': float(suma),
        'total_excel': float(bloque.total_excel) if bloque.total_excel is not None else None,
        'estado': 'revisar' if avisos else 'ok',
        'avisos': avisos,
    }


def _verificar_con_totales(dia: dict, bloque: Bloque, totales: list[TotalDiario], usados: set[int]) -> None:
    del_mismo_dia = [i for i, t in enumerate(totales) if t.fecha == bloque.fecha and i not in usados]
    for indice in del_mismo_dia:
        if totales[indice].monto in _montos_bloque(bloque):
            usados.add(indice)
            return
    if del_mismo_dia:
        usados.add(del_mismo_dia[0])
        dia['estado'] = 'revisar'
        dia['avisos'].append(
            f'La hoja de totales dice {_fmt(totales[del_mismo_dia[0]].monto)} para ese dia.'
        )


def _buscar_fecha_por_total(dia: dict, bloque: Bloque, totales: list[TotalDiario], usados: set[int]) -> None:
    montos = _montos_bloque(bloque)
    for indice, total in enumerate(totales):
        if indice not in usados and total.monto in montos:
            usados.add(indice)
            dia['fecha'] = total.fecha.isoformat()
            dia['origen_fecha'] = 'totales'
            return
    parecido = _total_mas_parecido(bloque, totales, usados)
    if parecido is not None:
        usados.add(parecido)
        total = totales[parecido]
        dia['fecha'] = total.fecha.isoformat()
        dia['origen_fecha'] = 'parecido'
        dia['estado'] = 'revisar'
        dia['avisos'].append(
            f'Sin fecha en el Excel. Se sugiere el {total.fecha.strftime("%d/%m/%Y")} porque la hoja '
            f'de totales tiene {_fmt(total.monto)}, parecido a este bloque. Confirmala.'
        )
        return
    dia['estado'] = 'sin_fecha'
    dia['avisos'].append('No se pudo deducir la fecha: elegila a mano.')


def _total_mas_parecido(bloque: Bloque, totales: list[TotalDiario], usados: set[int]) -> int | None:
    referencia = bloque.suma or bloque.total_excel or Decimal('0')
    if referencia <= 0:
        return None
    mejor, mejor_diferencia = None, None
    for indice, total in enumerate(totales):
        if indice in usados:
            continue
        diferencia = min(abs(total.monto - monto) for monto in _montos_bloque(bloque))
        if diferencia <= referencia * TOLERANCIA_PARECIDO and (mejor_diferencia is None or diferencia < mejor_diferencia):
            mejor, mejor_diferencia = indice, diferencia
    return mejor


def _montos_bloque(bloque: Bloque) -> set[Decimal]:
    montos = {bloque.suma}
    if bloque.total_excel is not None:
        montos.add(bloque.total_excel)
    return montos


def _fmt(monto) -> str:
    return f'{int(Decimal(str(monto))):,}'.replace(',', '.')
