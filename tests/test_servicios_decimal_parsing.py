from decimal import Decimal

import pytest

from app.routes.servicios import _currency_gs, _parse_decimal_value, _parsear_variantes


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('50000.00', Decimal('50000.00')),
        ('50.000', Decimal('50000')),
        ('1.500.000', Decimal('1500000')),
        ('1500000,50', Decimal('1500000.50')),
        ('1,500,000.50', Decimal('1500000.50')),
        ('₲ 35.000', Decimal('35000')),
    ],
)
def test_parse_decimal_value_soporta_formatos_de_edicion_y_miles(raw, expected):
    assert _parse_decimal_value(raw) == expected


def test_parsear_variantes_conserva_precios_al_reeditar():
    variantes = _parsear_variantes(
        'Corte clasico | 35.000 | 50.000\n'
        'Premium | 1500000.00 | 1750000.00\n'
    )

    assert variantes == [
        {
            'etiqueta': 'Corte clasico',
            'costo': Decimal('35000'),
            'precio': Decimal('50000'),
        },
        {
            'etiqueta': 'Premium',
            'costo': Decimal('1500000.00'),
            'precio': Decimal('1750000.00'),
        },
    ]


def test_currency_gs_formatea_importes_con_miles_consistentes():
    assert _currency_gs(Decimal('1500000')) == '₲ 1.500.000'
    assert _currency_gs(Decimal('50000.50')) == '₲ 50.000'
