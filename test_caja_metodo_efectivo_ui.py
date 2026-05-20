import re

from app import create_app
from app.models import Configuracion, MetodoPago, Usuario
from app.services.caja_metodos import CLAVE_METODO_EFECTIVO_ID


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def test_config_metodo_efectivo_preselecciona_metodo_resuelto_por_nombre():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        Configuracion.establecer(CLAVE_METODO_EFECTIVO_ID, '', 'test reset')
        metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        assert metodo_efectivo is not None
        efectivo_id = int(metodo_efectivo.id_metodo_pago)

    response = client.get('/caja/config/metodo-efectivo')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Automatico (match por nombre)' in html
    assert 'Origen de la resolucion' in html
    assert 'Configuracion explicita' in html
    assert re.search(rf'<option value="{efectivo_id}"\s+selected>', html)

    with app.app_context():
        assert (Configuracion.obtener(CLAVE_METODO_EFECTIVO_ID, '') or '').strip() == str(efectivo_id)
