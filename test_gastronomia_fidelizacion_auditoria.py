"""Auditoria de fichas por celular anteriores a BI-05d (datos ficticios)."""
import secrets

from app import create_app, db
from gastronomia.bi_models import GastronomiaBiFichaTelefono
from gastronomia.services.bi.identidad import telefono_normalizado
from gastronomia.services.fidelizacion_auditoria import auditar_fichas_telefono
from test_gastronomia_fidelizacion_telefono import _cliente

CLIENTE_AUDITADO = 1


def _celular() -> str:
    """Celular paraguayo valido y distinto en cada corrida: la base de pruebas persiste entre corridas."""
    return '0981' + f'{secrets.randbelow(10**6):06d}'


def _filas(telefonos):
    objetivos = {telefono_normalizado(t) for t in telefonos}
    return [
        f for f in GastronomiaBiFichaTelefono.query.filter_by(cliente_id=CLIENTE_AUDITADO).all()
        if f.telefono_normalizado in objetivos
    ]


def test_registra_celulares_unicos_y_lista_repetidos_sin_tocarlos():
    app = create_app()
    celular_unico, celular_repetido = _celular(), _celular()
    unica = _cliente(app, 'Unica Auditoria', celular_unico)
    _cliente(app, 'Repetida A', celular_repetido)
    _cliente(app, 'Repetida B', celular_repetido)
    with app.app_context():
        try:
            resultado = auditar_fichas_telefono(CLIENTE_AUDITADO)
            filas = _filas([celular_unico, celular_repetido])
            assert [f.id_cliente_ficha for f in filas] == [unica]
            assert len(resultado['duplicados'][telefono_normalizado(celular_repetido)]) == 2
            # Repetir no duplica filas.
            auditar_fichas_telefono(CLIENTE_AUDITADO)
            assert len(_filas([celular_unico])) == 1
        finally:
            GastronomiaBiFichaTelefono.query.filter_by(cliente_id=CLIENTE_AUDITADO).delete()
            db.session.commit()


def test_solo_listar_no_escribe():
    app = create_app()
    celular = _celular()
    _cliente(app, 'Solo Listar', celular)
    with app.app_context():
        auditar_fichas_telefono(CLIENTE_AUDITADO, registrar=False)
        assert _filas([celular]) == []
