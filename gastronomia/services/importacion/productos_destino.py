"""Convierte las decisiones de la vista previa en productos reales del menu."""
from __future__ import annotations

from decimal import Decimal

from app import db
from gastronomia.importacion_models import GastronomiaImportAlias
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.channel_price_service import asegurar_precios_producto
from gastronomia.services.importacion.productos_match import NOMBRE_VARIOS, clave_alias


CATEGORIA_DEFECTO = 'Menu'


class ResolutorProductos:
    """Crea (una sola vez) o reutiliza el producto de cada grupo."""

    def __init__(self, cliente_id: int, grupos: dict[str, dict], categoria_id: int | None = None):
        self.cliente_id = int(cliente_id)
        self.grupos = grupos
        self.categoria_id = categoria_id
        self._por_clave: dict[str, GastronomiaProducto] = {}
        self.creados: list[str] = []

    def producto_para(self, clave: str) -> GastronomiaProducto:
        if clave in self._por_clave:
            return self._por_clave[clave]
        grupo = self.grupos.get(clave) or {'accion': 'varios'}
        accion = grupo.get('accion')
        if accion == 'existente':
            producto = GastronomiaProducto.query.filter_by(
                cliente_id=self.cliente_id, id_producto=int(grupo.get('producto_id') or 0),
            ).first()
            if not producto:
                raise ValueError(f'El producto elegido para "{grupo.get("nombre")}" ya no existe.')
        elif accion == 'crear':
            producto = self._crear_o_reutilizar(grupo)
        else:
            producto = self._producto_varios()
        self._por_clave[clave] = producto
        return producto

    def producto_resuelto(self, clave: str) -> GastronomiaProducto | None:
        return self._por_clave.get(clave)

    def _crear_o_reutilizar(self, grupo: dict) -> GastronomiaProducto:
        nombre = (grupo.get('nombre') or '').strip()[:160]
        if not nombre:
            raise ValueError('Hay un producto nuevo sin nombre.')
        existente = self._buscar_por_nombre(nombre)
        if existente:
            return existente
        producto = GastronomiaProducto(
            cliente_id=self.cliente_id,
            categoria_id=self._categoria().id_categoria,
            nombre=nombre,
            precio=_precio(grupo.get('precio')),
            disponible=True,
            visible=True,
        )
        db.session.add(producto)
        db.session.flush()
        asegurar_precios_producto(producto, commit=False)
        self.creados.append(nombre)
        return producto

    def _producto_varios(self) -> GastronomiaProducto:
        existente = self._buscar_por_nombre(NOMBRE_VARIOS)
        if existente:
            return existente
        producto = GastronomiaProducto(
            cliente_id=self.cliente_id,
            categoria_id=self._categoria().id_categoria,
            nombre=NOMBRE_VARIOS,
            descripcion='Ventas historicas que no se pudieron asociar a un producto del menu.',
            precio=Decimal('0'),
            disponible=False,
            visible=False,
            visible_en_tv=False,
            publicado_tienda=False,
        )
        db.session.add(producto)
        db.session.flush()
        return producto

    def _buscar_por_nombre(self, nombre: str) -> GastronomiaProducto | None:
        objetivo = clave_alias(nombre)
        for producto in GastronomiaProducto.query.filter_by(cliente_id=self.cliente_id).all():
            if clave_alias(producto.nombre) == objetivo:
                if not producto.activo:
                    producto.activo = True
                return producto
        return None

    def _categoria(self) -> GastronomiaCategoria:
        if self.categoria_id:
            categoria = GastronomiaCategoria.query.filter_by(
                cliente_id=self.cliente_id, id_categoria=int(self.categoria_id),
            ).first()
            if categoria:
                return categoria
        categoria = GastronomiaCategoria.query.filter_by(cliente_id=self.cliente_id, nombre=CATEGORIA_DEFECTO).first()
        if not categoria:
            categoria = GastronomiaCategoria(cliente_id=self.cliente_id, nombre=CATEGORIA_DEFECTO, orden=0, visible=True)
            db.session.add(categoria)
            db.session.flush()
        self.categoria_id = categoria.id_categoria
        return categoria


def recordar_alias(cliente_id: int, alias_a_clave: dict[str, str], resolutor: ResolutorProductos) -> int:
    """Guarda el diccionario para que el proximo Excel salga solo."""
    guardados = 0
    existentes = {
        item.alias: item
        for item in GastronomiaImportAlias.query.filter_by(cliente_id=int(cliente_id)).all()
    }
    for alias, clave in alias_a_clave.items():
        producto = resolutor.producto_resuelto(clave)
        if not producto or not alias:
            continue
        registro = existentes.get(alias)
        if registro:
            registro.producto_id = producto.id_producto
        else:
            db.session.add(GastronomiaImportAlias(cliente_id=int(cliente_id), alias=alias[:160], producto_id=producto.id_producto))
        guardados += 1
    return guardados


def _precio(valor) -> Decimal:
    try:
        precio = Decimal(str(valor or 0)).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')
    return precio if precio >= 0 else Decimal('0.00')
