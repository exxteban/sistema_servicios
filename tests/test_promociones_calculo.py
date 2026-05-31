from decimal import Decimal
from types import SimpleNamespace

from app.routes.ventas.parte3_helpers import _construir_detalle_servicio
from app.services.promociones_calculo import calculate_promotion_totals
from app.services.tienda_promociones import validate_promotion_payload


def _promotion(tipo, **values):
    return SimpleNamespace(tipo=tipo, nombre='Promo', **values)


def test_calcula_dos_por_uno_por_grupos_completos():
    promotion = _promotion('cantidad', cantidad_lleva=2, cantidad_paga=1, valor=1)

    metrics = calculate_promotion_totals(30000, 5, promotion)

    assert metrics['subtotal_base'] == 90000
    assert metrics['descuento_linea'] == 60000
    assert metrics['cantidad_bonificada'] == 2
    assert metrics['descripcion'] == '2x1'


def test_calcula_descuento_porcentaje_sobre_toda_la_linea():
    promotion = _promotion('porcentaje', valor=10)

    metrics = calculate_promotion_totals(30000, 2, promotion)

    assert metrics['subtotal_base'] == 54000
    assert metrics['descuento_linea'] == 6000


def test_rechaza_descuento_porcentaje_superior_a_cien():
    _normalized, error = validate_promotion_payload({
        'nombre': 'Porcentaje imposible',
        'tipo': 'porcentaje',
        'valor': 150,
        'fecha_inicio': '2026-05-31T10:00',
        'fecha_fin': '2026-05-31T11:00',
        'productos': [1],
    })

    assert error == 'valor_invalido'


def test_cola_gastronomica_conserva_subtotal_exacto_si_el_promedio_redondea():
    servicio = SimpleNamespace(id_servicio=7, precio=Decimal('66.67'), porcentaje_iva=10)
    cola = SimpleNamespace(tipo_origen='gastronomia')

    result, error = _construir_detalle_servicio(
        {
            'id_servicio': 7,
            'cantidad': 3,
            'precio': 66.67,
            'precio_base': 66.67,
            'subtotal': 200,
            'subtotal_cantidad': 3,
        },
        {7: servicio},
        {},
        cola,
    )

    assert error is None
    assert result[0].subtotal == Decimal('200.00')
