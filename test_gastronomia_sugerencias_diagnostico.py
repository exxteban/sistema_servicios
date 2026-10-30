import json

from app import db
from gastronomia.services.sugerencias.calculo import _Conteo
from gastronomia.services.sugerencias.informe import comparar, informe_cliente
from gastronomia.sugerencias_models import GastronomiaSugerenciaPar
from test_gastronomia_sugerencias import datos, pedido  # noqa: F401


def test_comparacion_soporte_lift_y_confianza():
    conteo = _Conteo()
    for _ in range(3):
        conteo.sumar({1, 2}, 1)
    for _ in range(9):
        conteo.sumar({3}, 1)
    actual = comparar(conteo, soporte=4, confianza=.15, lift=1.5)
    assert actual['pares'] == 0
    assert actual['descartes'] == {'soporte': 2}
    variante = comparar(conteo, soporte=3, confianza=.1, lift=1.2)
    assert variante['pares'] == 2
    assert variante['cobertura_teorica_porcentaje'] == 66.67
    ubicuo = _Conteo()
    for _ in range(4):
        ubicuo.sumar({1, 2}, 1)
    assert comparar(ubicuo, soporte=4, confianza=.15, lift=1.5)['descartes'] == {'lift': 2}
    for _ in range(40):
        ubicuo.sumar({1}, 1)
    resultado = comparar(ubicuo, soporte=4, confianza=.15, lift=1.5)
    assert resultado['descartes']['confianza'] == 1


def test_informe_no_escribe_y_coincide_con_calculo(datos):
    cliente, _, ids = datos
    for _ in range(4):
        pedido(datos, ids[:2])
    for _ in range(8):
        pedido(datos, [ids[2]])
    from gastronomia.services.sugerencias.diagnostico import analizar
    esperado = analizar(cliente)['pares']['producto']
    resultado = informe_cliente(cliente, limite_detalle=1)
    actual = resultado['comparacion']['producto']['actual']
    assert actual['pares'] == len(esperado) == 2
    assert len(actual['top']) == 1
    assert actual['top'][0]['origen'] == 'Plato 0'
    assert GastronomiaSugerenciaPar.query.count() == 0
    assert not db.session.new and not db.session.dirty
    json.dumps(resultado)


def test_sin_pedidos_es_serializable_y_sugiere_reglas(datos):
    resultado = informe_cliente(datos[0])
    assert resultado['pedidos'] == 0
    assert resultado['comparacion']['producto']['actual']['cobertura_teorica_porcentaje'] == 0
    assert 'reglas' in resultado['recomendacion']
    json.dumps(resultado)
