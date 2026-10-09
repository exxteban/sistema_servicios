"""El receptor de una nota de crédito: el que declaró la factura, no el de hoy.

La NC corrige un documento que ya existe en SIFEN, y tiene que hablar del
mismo comprador. Armarla desde la ficha del cliente es armarla con los datos de
**hoy**: si alguien completó el RUC después de facturar ("4281292" pasó a
"4281292-5"), la factura dice no contribuyente con cédula y la NC dice
contribuyente con RUC. Eso le pasó a la venta #123 de Janelipy.

La única fuente que no cambia es el XML de la factura (`gDatRec`). Acá se lee
y se traduce a cada dialecto: el `receiver` de la API y el `cliente` de xmlgen.
"""
import xml.etree.ElementTree as ET

NS_SIFEN = '{http://ekuatia.set.gov.py/sifen/xsd}'

NATURALEZA_CONTRIBUYENTE = '1'

# Claves de identidad del `cliente` de xmlgen: se reemplazan enteras, para que
# no sobreviva un RUC de la ficha en un receptor que la factura declaró con cédula.
CLAVES_IDENTIDAD_PROPIO = (
    'contribuyente', 'ruc', 'tipoOperacion', 'tipoContribuyente',
    'documentoTipo', 'documentoNumero',
)


def leer_receptor(xml):
    """Los campos de `gDatRec` como {tag: texto}, o None si no se pueden leer."""
    if not xml:
        return None
    try:
        # En bytes: un str con declaración `encoding=` hace fallar a ElementTree.
        raiz = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml)
    except (ET.ParseError, ValueError):
        return None
    nodo = raiz.find(f'.//{NS_SIFEN}gDatRec')
    if nodo is None:
        nodo = raiz.find('.//gDatRec')
    if nodo is None:
        return None
    return {hijo.tag.split('}')[-1]: (hijo.text or '').strip() for hijo in nodo}


def redondeo_declarado(xml):
    """`dRedon` de la factura en guaraníes (0 si no hay o no se puede leer).

    La NC tiene que acreditar el mismo total general que declaró la factura:
    si ésta salió con redondeo SEDECO, la NC también; si salió cruda (las de la
    API antes de su 1.20.0), la NC tampoco.
    """
    if not xml:
        return 0
    try:
        raiz = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml)
    except (ET.ParseError, ValueError):
        return 0
    nodo = raiz.find(f'.//{NS_SIFEN}dRedon')
    if nodo is None:
        nodo = raiz.find('.//dRedon')
    try:
        return float((nodo.text or '0').strip()) if nodo is not None else 0
    except ValueError:
        return 0


def _entero(texto, defecto=None):
    try:
        return int(texto)
    except (TypeError, ValueError):
        return defecto


def receptor_api(campos):
    """`receiver` de la API con la identidad exacta de la factura."""
    receptor = {
        'name': campos.get('dNomRec') or 'Sin Nombre',
        'country_code': campos.get('cPaisRec') or 'PRY',
        'country_name': campos.get('dDesPaisRe') or 'Paraguay',
        'operation_type': _entero(campos.get('iTiOpe'), 2),
    }
    if campos.get('dEmailRec'):
        receptor['email'] = campos['dEmailRec']
    if campos.get('iNatRec') == NATURALEZA_CONTRIBUYENTE:
        receptor.update({
            'nature': 1,
            'contributor_type': _entero(campos.get('iTiContRec'), 1),
            'ruc': campos.get('dRucRec') or '',
            'dv': _entero(campos.get('dDVRec'), 0),
        })
    else:
        receptor.update({
            'nature': 2,
            'id_type': _entero(campos.get('iTipIDRec'), 5),
            'id_number': campos.get('dNumIDRec') or '0',
        })
    return receptor


def cliente_propio(campos, base):
    """`cliente` de xmlgen: el de la ficha (`base`) con la identidad de la factura.

    De la ficha quedan el código y el teléfono, que SIFEN no cruza; nombre,
    email y todo lo que identifica al comprador sale de la factura.
    """
    cliente = {k: v for k, v in base.items() if k not in CLAVES_IDENTIDAD_PROPIO}
    cliente['razonSocial'] = campos.get('dNomRec') or cliente.get('razonSocial')
    cliente['email'] = campos.get('dEmailRec') or None
    cliente['tipoOperacion'] = _entero(campos.get('iTiOpe'), 2)
    if campos.get('iNatRec') == NATURALEZA_CONTRIBUYENTE:
        cliente.update({
            'contribuyente': True,
            'ruc': f"{campos.get('dRucRec') or ''}-{campos.get('dDVRec') or ''}",
            'tipoContribuyente': _entero(campos.get('iTiContRec'), 1),
        })
    else:
        cliente.update({
            'contribuyente': False,
            'documentoTipo': _entero(campos.get('iTipIDRec'), 5),
            'documentoNumero': campos.get('dNumIDRec') or '0',
        })
    return cliente


def xml_local(documento):
    """El XML que el motor propio guardó de la factura, el más completo que haya."""
    return (
        getattr(documento, 'xml_qr', None)
        or getattr(documento, 'xml_firmado', None)
        or getattr(documento, 'xml', None)
    )


def cliente_facturado_propio(original, cliente_actual):
    """`cliente` de xmlgen para la NC del motor propio.

    Si la factura no tiene XML guardado (no debería pasar con una aprobada),
    queda la ficha: es lo que se hacía antes y el motor propio no tiene otra
    fuente.
    """
    from facturacion_electronica.services.data_builder import construir_cliente

    base = construir_cliente(cliente_actual)
    campos = leer_receptor(xml_local(original))
    return cliente_propio(campos, base) if campos else base


__all__ = [
    'cliente_facturado_propio',
    'cliente_propio',
    'leer_receptor',
    'receptor_api',
    'redondeo_declarado',
    'xml_local',
]
