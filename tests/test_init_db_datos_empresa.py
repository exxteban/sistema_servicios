from app import create_app, db
from app.models import Configuracion
from app.utils.init_db import inicializar_datos_base


def test_instalacion_nueva_no_trae_datos_de_otro_negocio():
    app = create_app('testing')
    with app.app_context():
        assert Configuracion.obtener('nombre_empresa') == 'Mi Negocio'
        assert Configuracion.obtener('direccion_empresa') == 'Dirección del local'
        assert Configuracion.obtener('telefono_empresa') == ''


def test_reinicio_conserva_los_datos_cargados_por_el_negocio():
    app = create_app('testing')
    with app.app_context():
        Configuracion.establecer('nombre_empresa', 'Café Aurora')
        Configuracion.establecer('telefono_empresa', '0981000000')
        db.session.commit()

        inicializar_datos_base(config_name='testing')

        assert Configuracion.obtener('nombre_empresa') == 'Café Aurora'
        assert Configuracion.obtener('telefono_empresa') == '0981000000'
