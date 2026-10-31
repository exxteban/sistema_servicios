"""Lista de activacion comercial: pasos detectados solos y pasos que confirma el dueno.

Los pasos automaticos salen de la configuracion actual (tienda, platos, horario).
Los externos (QR impreso, bio de Instagram, estado de WhatsApp) los confirma el dueno
y se guardan en Configuracion. La clave incluye el id_cliente porque una instalacion
puede alojar mas de un cliente.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.configuracion import Configuracion
from app.models.tienda import TiendaConfig
from gastronomia.models import GastronomiaProducto

PASOS_MANUALES = ('qr_impreso', 'bio_instagram', 'estado_whatsapp')
PREFIJO_CLAVE = 'bi.activacion'


def _clave_manual(cliente_id: int, paso: str) -> str:
    return f'{PREFIJO_CLAVE}.{int(cliente_id)}.{paso}'


def marcar_paso_manual(cliente_id: int, paso: str, hecho: bool) -> None:
    if paso not in PASOS_MANUALES:
        raise ValueError('Paso de activacion desconocido.')
    Configuracion.establecer_bool(
        _clave_manual(cliente_id, paso),
        hecho,
        descripcion='Paso manual de activacion comercial (BI gastronomia)',
    )


def _paso(paso_id: str, titulo: str, *, hecho: bool, automatico: bool, detalle: str, endpoint: str) -> dict:
    return {
        'id': paso_id,
        'titulo': titulo,
        'hecho': bool(hecho),
        'automatico': automatico,
        'detalle': detalle,
        'endpoint': endpoint,
    }


def _pasos_automaticos(tienda: TiendaConfig | None, productos: list) -> list[dict]:
    total = len(productos)
    sin_foto = sum(1 for producto in productos if not (producto.imagen_url or '').strip())
    sin_precio = sum(1 for producto in productos if Decimal(str(producto.precio or 0)) <= 0)
    horario = bool(tienda and tienda.mostrar_horarios and (tienda.texto_horarios or '').strip())
    return [
        _paso(
            'platos', 'Platos cargados',
            hecho=total > 0, automatico=True,
            detalle=f'{total} platos activos' if total else 'Todavia no hay platos activos.',
            endpoint='gastronomia.menu_config',
        ),
        _paso(
            'tienda', 'Tienda online publicada',
            hecho=bool(tienda and tienda.activa), automatico=True,
            detalle=(
                'La tienda esta activa.' if tienda and tienda.activa
                else 'Todavia no esta publicada la tienda online.'
            ),
            endpoint='tienda_admin.panel',
        ),
        _paso(
            'fotos', 'Platos con foto',
            hecho=total > 0 and sin_foto == 0, automatico=True,
            detalle=f'{sin_foto} sin foto' if sin_foto else 'Todos tienen foto.',
            endpoint='gastronomia.menu_config',
        ),
        _paso(
            'precios', 'Platos con precio',
            hecho=total > 0 and sin_precio == 0, automatico=True,
            detalle=f'{sin_precio} sin precio' if sin_precio else 'Todos tienen precio.',
            endpoint='gastronomia.menu_config',
        ),
        _paso(
            'horario', 'Horario visible en la tienda',
            hecho=horario, automatico=True,
            detalle='Se muestra en la tienda.' if horario else 'Cargalo para que el cliente sepa cuando pedir.',
            endpoint='tienda_admin.panel',
        ),
    ]


def _pasos_manuales(cliente_id: int) -> list[dict]:
    textos = {
        'qr_impreso': ('QR impreso (mesa, mostrador o bolsa)', 'Imprimilo y confirmalo cuando este puesto.'),
        'bio_instagram': ('Link de la tienda en la bio de Instagram', 'Confirmalo cuando lo hayas pegado.'),
        'estado_whatsapp': ('Link de la tienda en el estado de WhatsApp', 'Confirmalo cuando lo hayas publicado.'),
    }
    return [
        _paso(
            paso, textos[paso][0],
            hecho=Configuracion.obtener_bool(_clave_manual(cliente_id, paso), default=False),
            automatico=False,
            detalle=textos[paso][1],
            endpoint='tienda_admin.panel',
        )
        for paso in PASOS_MANUALES
    ]


def lista_activacion(cliente_id: int) -> dict:
    cliente_id = int(cliente_id)
    tienda = TiendaConfig.query.filter_by(id_cliente=cliente_id).first()
    productos = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, activo=True).all()
    pasos = _pasos_automaticos(tienda, productos) + _pasos_manuales(cliente_id)
    pendiente = next((paso for paso in pasos if not paso['hecho']), None)
    completados = sum(1 for paso in pasos if paso['hecho'])
    return {
        'pasos': pasos,
        'completados': completados,
        'total': len(pasos),
        'completa': pendiente is None,
        'siguiente': pendiente,
    }
