"""Análisis de solo lectura; comparte entradas y matemática con el cálculo."""
from datetime import datetime, timedelta

from gastronomia.models import GastronomiaProducto
from gastronomia.sugerencias_models import GastronomiaSugerenciaExcluido
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.calculo import _Conteo, peso_por_antiguedad
from gastronomia.services.sugerencias.tickets import tickets_gastronomia


def analizar(cliente_id, ahora=None):
    ahora = ahora or datetime.utcnow()
    excluidos = GastronomiaSugerenciaExcluido.query.filter_by(cliente_id=cliente_id).all()
    ids = {e.id_ref for e in excluidos if e.tipo == 'producto'}
    categorias = {e.id_ref for e in excluidos if e.tipo == 'categoria'}
    productos = {
        p.id_producto: p for p in GastronomiaProducto.query.filter_by(cliente_id=cliente_id, activo=True)
        if p.id_producto not in ids and p.categoria_id not in categorias
    }
    conteos = {'producto': _Conteo(), 'categoria': _Conteo()}
    pedidos = multiples = renglones = 0
    for fecha, canasta in tickets_gastronomia(
        cliente_id, ahora - timedelta(days=C.VENTANA_DIAS), ahora, set(productos),
    ):
        pedidos += 1
        multiples += len(canasta) > 1
        renglones += len(canasta)
        peso = peso_por_antiguedad(fecha, ahora)
        conteos['producto'].sumar(canasta, peso)
        conteos['categoria'].sumar({productos[p].categoria_id for p in canasta}, peso)
    pares = {
        nivel: [dict(nivel=nivel, id_origen=origen, **par)
                for origen, destinos in conteo.pares().items() for par in destinos]
        for nivel, conteo in conteos.items()
    }
    return {
        'cliente_id': cliente_id, 'pedidos': pedidos,
        'porcentaje_multiples': round(100 * multiples / pedidos, 2) if pedidos else 0,
        'platos_promedio': round(renglones / pedidos, 2) if pedidos else 0,
        'pares': pares, 'conteos': conteos,
        'nombres': {p: producto.nombre for p, producto in productos.items()},
    }
