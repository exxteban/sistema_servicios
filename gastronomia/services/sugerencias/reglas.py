"""Administración validada y acotada al contexto operativo resuelto por la vista."""
from app import db
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaRegla as Regla,
    GastronomiaSugerenciaExcluido as Excluido,
)


def referencia(cliente_id, valor, *, cualquiera=False):
    if cualquiera and valor == 'cualquiera':
        return 'cualquiera', None
    try:
        tipo, numero = str(valor).split(':')
        numero = int(numero)
    except (ValueError, TypeError):
        raise ValueError('Seleccioná un plato o categoría válido.') from None
    modelo = {'producto': GastronomiaProducto, 'categoria': GastronomiaCategoria}.get(tipo)
    if modelo is None or not modelo.query.filter_by(cliente_id=cliente_id).filter(
        getattr(modelo, 'id_producto' if tipo == 'producto' else 'id_categoria') == numero,
    ).first():
        raise ValueError('El plato o categoría no pertenece a este negocio.')
    return tipo, numero


def guardar_config(cliente_id, data):
    try:
        maximo = int(data.get('max_franja', 3))
    except (TypeError, ValueError):
        raise ValueError('La cantidad debe estar entre 1 y 3.') from None
    if not 1 <= maximo <= 3:
        raise ValueError('La cantidad debe estar entre 1 y 3.')
    fila = Config.query.filter_by(cliente_id=cliente_id).first()
    if fila is None:
        fila = Config(cliente_id=cliente_id)
        db.session.add(fila)
    fila.activo = data.get('activo') == '1'
    fila.mostrar_en_pos = fila.activo and data.get('mostrar_en_pos') == '1'
    fila.max_franja = maximo
    db.session.commit()


def guardar_regla(cliente_id, usuario_id, data, regla_id=None):
    tipo = data.get('tipo')
    if tipo not in ('forzar', 'prohibir'):
        raise ValueError('Seleccioná Sugerir o Nunca sugerir.')
    origen_tipo, origen_id = referencia(cliente_id, data.get('origen'), cualquiera=True)
    destino_tipo, destino_id = referencia(cliente_id, data.get('destino'))
    if origen_tipo == destino_tipo == 'producto' and origen_id == destino_id:
        raise ValueError('Elegí un complemento distinto del plato de origen.')
    fila = None
    if regla_id is not None:
        fila = Regla.query.filter_by(cliente_id=cliente_id, id=regla_id).first()
        if fila is None:
            raise ValueError('La regla no existe en este negocio.')
    # Una regla nueva o editada reemplaza la anterior para esa combinación.
    repetidas = Regla.query.filter_by(
        cliente_id=cliente_id, origen_tipo=origen_tipo, origen_id=origen_id,
        destino_tipo=destino_tipo, destino_id=destino_id,
    )
    if fila is not None:
        repetidas = repetidas.filter(Regla.id != fila.id)
    repetidas.delete(synchronize_session=False)
    if fila is None:
        fila = Regla(cliente_id=cliente_id, creado_por_id=usuario_id)
        db.session.add(fila)
    fila.tipo, fila.origen_tipo, fila.origen_id = tipo, origen_tipo, origen_id
    fila.destino_tipo, fila.destino_id = destino_tipo, destino_id
    fila.prioridad = 1 if data.get('prioridad') == '1' else 0
    fila.activa = True
    db.session.commit()


def cambiar_regla(cliente_id, regla_id, accion):
    fila = Regla.query.filter_by(cliente_id=cliente_id, id=regla_id).first()
    if fila is None:
        raise ValueError('La regla no existe en este negocio.')
    if accion == 'eliminar':
        db.session.delete(fila)
    elif accion == 'alternar':
        fila.activa = not fila.activa
    else:
        raise ValueError('Acción inválida.')
    db.session.commit()


def excluir(cliente_id, valor):
    tipo, numero = referencia(cliente_id, valor)
    if Excluido.query.filter_by(cliente_id=cliente_id, tipo=tipo, id_ref=numero).first() is None:
        db.session.add(Excluido(cliente_id=cliente_id, tipo=tipo, id_ref=numero))
    db.session.commit()


def quitar_exclusion(cliente_id, exclusion_id):
    fila = Excluido.query.filter_by(cliente_id=cliente_id, id=exclusion_id).first()
    if fila is None:
        raise ValueError('La exclusión no existe en este negocio.')
    db.session.delete(fila)
    db.session.commit()
