"""Permiso y rol del área Contador/a. Se siembran en `app/utils/init_db.py` al arrancar.

El/la contador/a es un profesional de afuera: con `ver_area_contador` ve el
resumen de IVA del mes, su detalle y el Excel, sin vender ni ver caja ni los
reportes del negocio (para eso estaba `ver_reportes`, que abre todo). El rol
"Contador/a" queda listo para asignarle a su usuario; el dueño le puede sumar
permisos desde Roles si quiere que vea algo más.
"""
from app import db
from app.models import Permiso, Rol

PERMISO_AREA_CONTADOR = 'ver_area_contador'

PERMISOS_CONTADOR = (
    {
        'codigo': PERMISO_AREA_CONTADOR,
        'nombre': 'Ver Área Contador/a',
        'descripcion': 'Permite ver el resumen de IVA del mes, su detalle y el Excel, sin ver caja ni reportes',
        'modulo': 'contador',
        'requiere_autorizacion': False,
    },
)

SIMBOLOS_GUARANI = ('₲', 'Gs', 'Gs.')


def instalacion_paraguaya():
    """El área Contador/a es IVA paraguayo: con otra moneda (R$ en Brasil) no aplica."""
    from app.utils.helpers import config_moneda

    moneda = config_moneda()
    return moneda.get('locale') == 'es-PY' and moneda.get('simbolo') in SIMBOLOS_GUARANI


ROL_CONTADOR = 'Contador/a'
DESCRIPCION_ROL_CONTADOR = ('Profesional de afuera: ve el resumen de IVA del mes y su detalle. '
                            'No vende ni ve la caja ni los reportes del negocio.')


def ensure_rol_contador(*, commit=True):
    """Crea el rol y le garantiza el permiso. Idempotente; devuelve el rol."""
    rol = Rol.query.filter_by(nombre=ROL_CONTADOR).first()
    if rol is None:
        rol = Rol(nombre=ROL_CONTADOR, descripcion=DESCRIPCION_ROL_CONTADOR, nivel_jerarquia=5)
        db.session.add(rol)
        db.session.flush()
    permiso = Permiso.query.filter_by(codigo=PERMISO_AREA_CONTADOR).first()
    if permiso is not None and permiso not in rol.permisos.all():
        rol.permisos.append(permiso)
    if commit:
        db.session.commit()
    return rol


__all__ = ['PERMISOS_CONTADOR', 'PERMISO_AREA_CONTADOR', 'ROL_CONTADOR', 'ensure_rol_contador', 'instalacion_paraguaya']
