from datetime import date

from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services import construir_params_emisor, validar_configuracion


def _config_ejemplo():
    return FacturacionElectronicaConfig(
        id=1,
        ambiente='test',
        razon_social='MI EMPRESA SA',
        nombre_fantasia='Mi Empresa',
        ruc='80069563',
        dv_ruc='1',
        tipo_contribuyente='2',
        tipo_regimen='8',
        timbrado_numero='12558946',
        timbrado_fecha_inicio=date(2022, 8, 25),
        establecimiento='001',
        punto_expedicion='001',
        actividad_economica_codigo='1254',
        actividad_economica_desc='Desarrollo de Software',
        departamento_codigo='11',
        departamento_desc='ALTO PARANA',
        distrito_codigo='145',
        distrito_desc='CIUDAD DEL ESTE',
        ciudad_codigo='3432',
        ciudad_desc='PUERTO',
        direccion='Barrio Carolina',
        numero_casa='0',
        telefono='0973-527155',
        email='empresa@mail.com',
    )


def test_params_emisor_mapea_campos_principales():
    params = construir_params_emisor(_config_ejemplo())

    assert params['version'] == 150
    assert params['ruc'] == '80069563-1'
    assert params['razonSocial'] == 'MI EMPRESA SA'
    assert params['timbradoNumero'] == '12558946'
    assert params['timbradoFecha'] == '2022-08-25'
    assert params['tipoContribuyente'] == 2
    assert params['tipoRegimen'] == 8
    assert params['actividadesEconomicas'] == [
        {'codigo': '1254', 'descripcion': 'Desarrollo de Software'}
    ]


def test_params_emisor_establecimiento_usa_enteros_en_codigos():
    establecimiento = construir_params_emisor(_config_ejemplo())['establecimientos'][0]

    assert establecimiento['codigo'] == '001'
    assert establecimiento['departamento'] == 11
    assert establecimiento['distrito'] == 145
    assert establecimiento['ciudad'] == 3432
    assert establecimiento['denominacion'] == 'Mi Empresa'


def test_params_emisor_tolera_campos_vacios():
    config = FacturacionElectronicaConfig(id=1, ambiente='test', establecimiento='001')
    params = construir_params_emisor(config)

    assert params['ruc'] is None
    assert params['timbradoFecha'] is None
    assert params['tipoContribuyente'] is None
    establecimiento = params['establecimientos'][0]
    assert establecimiento['departamento'] is None
    assert establecimiento['numeroCasa'] == '0'
    assert establecimiento['denominacion'] == 'Casa Matriz'


def test_validacion_lista_lo_que_falta():
    vacio = FacturacionElectronicaConfig(id=1, establecimiento='001', punto_expedicion='001')
    faltantes = validar_configuracion(vacio)
    assert 'RUC y dígito verificador' in faltantes
    assert 'Certificado digital (.p12)' in faltantes
    assert 'CSC (Código de Seguridad del Contribuyente)' in faltantes


def test_validacion_config_completa_sin_faltantes():
    completa = _config_ejemplo()
    completa.cert_path = '/tmp/certificado.p12'
    completa.cert_password = 'secreta'
    completa.csc = 'ABCD0000000000000000000000000000'
    completa.csc_id = '0001'
    assert validar_configuracion(completa) == []
