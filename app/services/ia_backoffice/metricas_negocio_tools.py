import re
import unicodedata

from app.services.ia_backoffice.caja_tools import caja_resumen_periodo
from app.services.ia_backoffice.drilldown_shared import _puede_ver_caja, _puede_ver_gastos, _puede_ver_ventas
from app.services.ia_backoffice.gastos_tools import gastos_resumen_periodo
from app.services.ia_backoffice.periods import resolver_rango
from app.services.ia_backoffice.ventas_tools import ventas_ganancia_periodo


CONCEPTOS = {
    'ganancia_bruta': {
        'titulo': 'Ganancia bruta',
        'definicion': 'Es lo vendido menos el costo estimado de los productos vendidos.',
        'formula_resumida': 'Ventas - costo estimado.',
        'incluye': ['ventas completadas', 'costo estimado de mercaderia vendida'],
        'no_incluye': ['gastos corrientes', 'impuestos', 'sueldos', 'depreciaciones'],
        'disponible_en_sistema': True,
        'tool_sugerida': 'ventas_ganancia_periodo',
        'nota_sistema': 'En este sistema se estima con el precio_compra actual del producto.',
    },
    'ganancia_neta': {
        'titulo': 'Ganancia neta',
        'definicion': 'Es lo que queda despues de costos, gastos, impuestos y otros ajustes contables.',
        'formula_resumida': 'Ganancia bruta - gastos - impuestos - otros ajustes.',
        'incluye': ['costos de venta', 'gastos operativos', 'impuestos', 'ajustes contables'],
        'no_incluye': ['no deberia confundirse con caja ni con ventas totales'],
        'disponible_en_sistema': False,
        'tool_sugerida': '',
        'nota_sistema': 'Hoy el backoffice no calcula una ganancia neta contable exacta; solo puede aproximar rentabilidad operativa con ventas, gastos y caja.',
    },
    'margen_bruto': {
        'titulo': 'Margen bruto',
        'definicion': 'Es la ganancia bruta expresada como porcentaje sobre la venta.',
        'formula_resumida': '(Ganancia bruta / ventas) * 100.',
        'incluye': ['ventas completadas', 'costo estimado'],
        'no_incluye': ['gastos corrientes', 'impuestos', 'flujo de caja'],
        'disponible_en_sistema': True,
        'tool_sugerida': 'ventas_ganancia_periodo',
        'nota_sistema': 'Se calcula sobre la misma ganancia bruta estimada del modulo de ventas.',
    },
    'resultado_caja': {
        'titulo': 'Resultado de caja',
        'definicion': 'Es la diferencia entre ingresos y egresos de caja observados en un periodo.',
        'formula_resumida': 'Ingresos de caja - egresos de caja.',
        'incluye': ['cobros', 'ingresos manuales', 'egresos', 'movimientos de caja'],
        'no_incluye': ['costos no pagados', 'depreciaciones', 'utilidad contable'],
        'disponible_en_sistema': True,
        'tool_sugerida': 'caja_resumen_periodo',
        'nota_sistema': 'Puede moverse distinto a la rentabilidad porque una venta rentable no siempre entra a caja en el mismo momento.',
    },
    'diferencia_cierre_caja': {
        'titulo': 'Diferencia de cierre de caja',
        'definicion': 'Es la diferencia entre lo declarado al cerrar la caja y lo que el sistema esperaba.',
        'formula_resumida': 'Monto declarado - monto sistema.',
        'incluye': ['monto declarado', 'monto esperado por sistema'],
        'no_incluye': ['ganancia del negocio', 'rentabilidad de ventas'],
        'disponible_en_sistema': True,
        'tool_sugerida': 'caja_cierre_diferencia',
        'nota_sistema': 'Sirve para controlar faltantes o sobrantes de caja, no para medir utilidad.',
    },
}

ALIAS_CONCEPTOS = {
    'ganancia bruta': 'ganancia_bruta',
    'ganancia bruto': 'ganancia_bruta',
    'utilidad bruta': 'ganancia_bruta',
    'margen bruto': 'margen_bruto',
    'margen de ganancia': 'margen_bruto',
    'ganancia neta': 'ganancia_neta',
    'utilidad neta': 'ganancia_neta',
    'resultado de caja': 'resultado_caja',
    'resultado caja': 'resultado_caja',
    'neto de caja': 'resultado_caja',
    'flujo de caja': 'resultado_caja',
    'diferencia de cierre de caja': 'diferencia_cierre_caja',
    'diferencia de caja': 'diferencia_cierre_caja',
    'faltante de caja': 'diferencia_cierre_caja',
    'sobrante de caja': 'diferencia_cierre_caja',
    'cierre de caja': 'diferencia_cierre_caja',
}

PARES_COMPARABLES = {
    frozenset({'ganancia_neta', 'resultado_caja'}): {
        'resumen_corto': 'La ganancia neta mide utilidad despues de costos y gastos; el resultado de caja mide entrada y salida real de dinero.',
        'diferencia_clave': 'Una habla de rentabilidad economica y la otra de liquidez o movimiento de efectivo.',
        'cuando_no_coinciden': [
            'cuando hay ventas a credito y aun no se cobraron',
            'cuando se pagan gastos en un periodo distinto al de la venta',
            'cuando hay movimientos de caja que no cambian la utilidad',
        ],
        'lectura_sistema': 'En este sistema se puede ver caja y rentabilidad operativa, pero no una ganancia neta contable exacta.',
    },
    frozenset({'ganancia_bruta', 'resultado_caja'}): {
        'resumen_corto': 'La ganancia bruta compara venta contra costo; el resultado de caja compara ingresos contra egresos de caja.',
        'diferencia_clave': 'La ganancia bruta ignora gastos corrientes y tiempos de cobro/pago; la caja no.',
        'cuando_no_coinciden': [
            'cuando se cobra despues de vender',
            'cuando hubo egresos de caja sin relacion directa con esa venta',
            'cuando el costo contable no coincide con el flujo de efectivo del dia',
        ],
        'lectura_sistema': 'La ganancia bruta del backoffice es estimada con costo actual del producto.',
    },
    frozenset({'diferencia_cierre_caja', 'resultado_caja'}): {
        'resumen_corto': 'El resultado de caja resume un periodo; la diferencia de cierre mide si el arqueo final coincide con lo esperado.',
        'diferencia_clave': 'Uno mira flujo neto y el otro control operativo del cierre.',
        'cuando_no_coinciden': [
            'cuando hubo errores de conteo',
            'cuando faltan registrar movimientos',
            'cuando el periodo tuvo caja positiva pero el cierre quedo mal contado',
        ],
        'lectura_sistema': 'El cierre sirve para detectar faltante o sobrante, no para medir utilidad.',
    },
}


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', (texto or '').lower()).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', texto).strip()


def _resolver_concepto(valor: str) -> str:
    texto = _normalizar_texto(valor)
    if texto in CONCEPTOS:
        return texto
    for alias, concepto in ALIAS_CONCEPTOS.items():
        if alias in texto:
            return concepto
    return ''


def _resolver_conceptos(args: dict | None) -> list[str]:
    data = args or {}
    conceptos = []
    for clave in ('concepto', 'comparar_con', 'busqueda', 'referencia'):
        concepto = _resolver_concepto(data.get(clave) or '')
        if concepto and concepto not in conceptos:
            conceptos.append(concepto)
    if len(conceptos) >= 2:
        return conceptos[:2]
    texto = _normalizar_texto(' '.join(str(data.get(clave) or '') for clave in ('busqueda', 'referencia')))
    for alias, concepto in ALIAS_CONCEPTOS.items():
        if alias in texto and concepto not in conceptos:
            conceptos.append(concepto)
    return conceptos[:2]


def metricas_explicacion_negocio(args: dict | None = None, usuario=None) -> dict:
    concepto = _resolver_concepto((args or {}).get('concepto') or (args or {}).get('busqueda') or (args or {}).get('referencia') or '')
    if not concepto:
        return {
            'encontrado': False,
            'conceptos_disponibles': sorted(CONCEPTOS.keys()),
        }
    return {
        'encontrado': True,
        'concepto': concepto,
        **CONCEPTOS[concepto],
    }


def metricas_comparacion_negocio(args: dict | None = None, usuario=None) -> dict:
    conceptos = _resolver_conceptos(args)
    if len(conceptos) < 2:
        return {
            'encontrado': False,
            'conceptos_disponibles': sorted(CONCEPTOS.keys()),
        }
    concepto_a, concepto_b = conceptos[0], conceptos[1]
    comparacion = PARES_COMPARABLES.get(frozenset({concepto_a, concepto_b}))
    if comparacion is None:
        comparacion = {
            'resumen_corto': f'{CONCEPTOS[concepto_a]["titulo"]} y {CONCEPTOS[concepto_b]["titulo"]} no miden lo mismo.',
            'diferencia_clave': 'Conviene revisar formula, alcance y momento de reconocimiento de cada metrica.',
            'cuando_no_coinciden': [
                'cuando una mide rentabilidad y la otra flujo',
                'cuando hay cobros o pagos en fechas distintas',
            ],
            'lectura_sistema': 'Si la consulta es operativa, conviene calcular ventas, gastos y caja por separado.',
        }
    return {
        'encontrado': True,
        'concepto_a': concepto_a,
        'concepto_b': concepto_b,
        'titulo_a': CONCEPTOS[concepto_a]['titulo'],
        'titulo_b': CONCEPTOS[concepto_b]['titulo'],
        **comparacion,
    }


def metricas_resumen_operativo(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    ventas = ventas_ganancia_periodo(args, usuario) if _puede_ver_ventas(usuario) else None
    caja = caja_resumen_periodo(args, usuario) if _puede_ver_caja(usuario) else None
    gastos = gastos_resumen_periodo(args, usuario) if _puede_ver_gastos(usuario) else None
    gastos_pagados = float((gastos or {}).get('total_pagado') or 0)
    resultado_operativo_aprox = None
    if ventas is not None and gastos is not None:
        resultado_operativo_aprox = round(float(ventas.get('ganancia_bruta_estimada') or 0) - gastos_pagados, 2)

    lecturas = []
    if ventas is not None:
        lecturas.append('La ganancia de ventas disponible es bruta y estimada, no neta contable.')
    if caja is not None:
        lecturas.append('La caja resume flujo de dinero; puede no coincidir con la rentabilidad del mismo periodo.')
    if gastos is not None:
        lecturas.append('Los gastos corrientes ayudan a aproximar resultado operativo, pero no reemplazan contabilidad completa.')

    return {
        'periodo_label': rango['periodo_label'],
        'desde': rango['desde'].isoformat(),
        'hasta': rango['hasta'].isoformat(),
        'ventas_total': float((ventas or {}).get('total_ventas') or 0),
        'ganancia_bruta_estimada': float((ventas or {}).get('ganancia_bruta_estimada') or 0),
        'margen_bruto_pct': (ventas or {}).get('margen_bruto_pct'),
        'costo_estimado': float((ventas or {}).get('costo_estimado') or 0),
        'resultado_caja_movimientos': float((caja or {}).get('neto_movimientos') or 0),
        'ventas_total_caja': float((caja or {}).get('ventas_total') or 0),
        'gastos_estimados': float((gastos or {}).get('total_estimado') or 0),
        'gastos_pagados': gastos_pagados,
        'gastos_pendientes': float((gastos or {}).get('total_pendiente') or 0),
        'resultado_operativo_aproximado': resultado_operativo_aprox,
        'ganancia_neta_exacta_disponible': False,
        'nota_ganancia_neta': 'La ganancia neta exacta requeriria impuestos, devengamientos, depreciaciones y otros ajustes contables que esta capa no calcula.',
        'ventas_disponibles': ventas is not None,
        'caja_disponible': caja is not None,
        'gastos_disponibles': gastos is not None,
        'lecturas_clave': lecturas,
    }
