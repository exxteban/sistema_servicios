"""Comparación explicable de umbrales, sin escribir ni cambiar constantes."""
from collections import Counter

from gastronomia.models import GastronomiaCategoria
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.calculo import medir
from gastronomia.services.sugerencias.diagnostico import analizar


def comparar(conteo, *, soporte, confianza, lift, limite_detalle=20):
    descartes = Counter()
    aceptados = []
    rechazados = []
    for (a, b), cantidad in conteo.par_crudo.items():
        for origen, destino in ((a, b), (b, a)):
            medidas = medir(conteo.par_peso[(a, b)], conteo.peso[origen],
                            conteo.peso[destino], conteo.peso_total, 0, 0)
            if medidas is None:
                continue
            razon = None
            if cantidad < soporte:
                razon = 'soporte'
            elif medidas['confianza'] < confianza:
                razon = 'confianza'
            elif medidas['lift'] < lift:
                razon = 'lift'
            fila = dict(id_origen=origen, id_destino=destino, soporte=cantidad, **medidas)
            if razon:
                descartes[razon] += 1
                rechazados.append(dict(fila, descarte=razon))
            else:
                aceptados.append(fila)
    aceptados.sort(key=lambda p: (-p['puntaje'], p['id_origen'], p['id_destino']))
    # Igual que el cálculo persistido, máximo 10 destinos por origen.
    cupos = Counter()
    finales = []
    for fila in aceptados:
        origen = fila['id_origen']
        if cupos[origen] >= C.MAX_DESTINOS_POR_ORIGEN:
            descartes['limite_destinos'] += 1
            rechazados.append(dict(fila, descarte='limite_destinos'))
            continue
        cupos[origen] += 1
        finales.append(fila)
    origenes = {p['id_origen'] for p in finales}
    rechazados.sort(key=lambda p: (-p['puntaje'], p['id_origen'], p['id_destino']))
    return {
        'umbrales': dict(soporte=soporte, confianza=confianza, lift=lift),
        'pares': len(finales), 'origenes_con_asociacion': len(origenes),
        'origenes_analizados': len(conteo.crudo),
        'cobertura_teorica_porcentaje': round(100 * len(origenes) / len(conteo.crudo), 2) if conteo.crudo else 0,
        'descartes': dict(descartes),
        'top': finales[:limite_detalle], 'muestra_descartados': rechazados[:limite_detalle],
    }


def informe_cliente(cliente_id, ahora=None, limite_detalle=20):
    resultado = analizar(cliente_id, ahora)
    conteos = resultado.pop('conteos')
    categorias = {c.id_categoria: c.nombre for c in GastronomiaCategoria.query.filter_by(cliente_id=cliente_id)}
    nombres = {'producto': resultado['nombres'], 'categoria': categorias}
    variantes = {
        'actual': dict(soporte=C.SOPORTE_MINIMO, confianza=C.CONFIANZA_MINIMA, lift=C.LIFT_MINIMO),
        'exploratoria': dict(soporte=3, confianza=0.10, lift=1.2),
    }
    resultado['comparacion'] = {}
    for nivel, conteo in conteos.items():
        resultado['comparacion'][nivel] = {}
        for nombre, umbrales in variantes.items():
            resumen = comparar(conteo, limite_detalle=limite_detalle, **umbrales)
            for fila in resumen['top'] + resumen['muestra_descartados']:
                fila['origen'] = nombres[nivel].get(fila['id_origen'])
                fila['destino'] = nombres[nivel].get(fila['id_destino'])
            resultado['comparacion'][nivel][nombre] = resumen
    # Los pares completos viven en el cálculo; el CLI devuelve muestras acotadas.
    resultado.pop('pares')
    resultado['nota_cobertura'] = (
        'Porcentaje de productos/categorías con asociaciones; previo a filtros de stock, '
        'precio, reglas y carrito. No mide apariciones reales de la franja.'
    )
    resultado['recomendacion'] = (
        'Pocas canastas múltiples: priorizar reglas del negocio.'
        if resultado['porcentaje_multiples'] < 15 else 'Revisar los pares antes de activar el POS.'
    )
    return resultado
