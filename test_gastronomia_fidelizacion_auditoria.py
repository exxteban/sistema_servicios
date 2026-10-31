"""Auditoria de fichas por celular anteriores a BI-05d (datos ficticios)."""
from app import create_app, db
from gastronomia.bi_models import GastronomiaBiFichaTelefono
from gastronomia.services.bi.identidad import telefono_normalizado
from gastronomia.services.fidelizacion_auditoria import auditar_fichas_telefono
from test_gastronomia_fidelizacion_telefono import _cliente

CLIENTE_AUDITADO = 1


def _filas(telefonos):
    objetivos = {telefono_normalizado(t) for t in telefonos}
    return [
        f for f in GastronomiaBiFichaTelefono.query.filter_by(cliente_id=CLIENTE_AUDITADO).all()
        if f.telefono_normalizado in objetivos
    ]


def test_registra_celulares_unicos_y_lista_repetidos_sin_tocarlos():
    app = create_app()
    unica = _cliente(app, 'Unica Auditoria', '0981 990 001')
    _cliente(app, 'Repetida A', '0981 990 002')
    _cliente(app, 'Repetida B', '0981 990 002')
    with app.app_context():
        try:
            resultado = auditar_fichas_telefono(CLIENTE_AUDITADO)
            filas = _filas(['0981990001', '0981990002'])
            assert [f.id_cliente_ficha for f in filas] == [unica]
            assert len(resultado['duplicados'][telefono_normalizado('0981990002')]) == 2
            # Repetir no duplica filas.
            auditar_fichas_telefono(CLIENTE_AUDITADO)
            assert len(_filas(['0981990001'])) == 1
        finally:
            GastronomiaBiFichaTelefono.query.filter_by(cliente_id=CLIENTE_AUDITADO).delete()
            db.session.commit()


def test_solo_listar_no_escribe():
    app = create_app()
    _cliente(app, 'Solo Listar', '0981 990 003')
    with app.app_context():
        auditar_fichas_telefono(CLIENTE_AUDITADO, registrar=False)
        assert _filas(['0981990003']) == []
