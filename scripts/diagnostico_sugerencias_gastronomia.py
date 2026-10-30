"""Diagnóstico de solo lectura. No usa create_app ni ejecuta migraciones."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask
from sqlalchemy import event, inspect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from config import config
from app import db
import app.models  # noqa: F401
from gastronomia.models import (
    GastronomiaClienteConfig, GastronomiaCategoria, GastronomiaProducto,
    GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago,
)
from gastronomia.channel_models import GastronomiaProductoPrecioCanal
from app.models.venta import Venta
from gastronomia.services.channel_price_service import CANALES_PRECIOS
from gastronomia.services.sugerencias.informe import informe_cliente


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cliente-id', type=int)
    parser.add_argument('--limite', type=int, default=20, help='Máximo de pares por muestra (1–100)')
    parser.add_argument('--muestra-pos', type=int, default=20, help='Productos más pedidos para simular carritos (1–100)')
    parser.add_argument('--repeticiones-pos', type=int, default=3, help='Consultas por producto y canal (1–5)')
    parser.add_argument('--canal', choices=['normal', *CANALES_PRECIOS, 'todos'], default='normal')
    parser.add_argument('--sqlite', type=Path, help='Archivo SQLite existente; reemplaza la base configurada, sin crearla')
    args = parser.parse_args()
    if args.cliente_id is not None and args.cliente_id <= 0:
        parser.error('--cliente-id debe ser positivo')
    if not 1 <= args.limite <= 100:
        parser.error('--limite debe estar entre 1 y 100')
    if not 1 <= args.muestra_pos <= 100 or not 1 <= args.repeticiones_pos <= 5:
        parser.error('--muestra-pos debe estar entre 1 y 100 y --repeticiones-pos entre 1 y 5')
    app = Flask(__name__)
    app.config.from_object(config['default'])
    url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
    if args.sqlite:
        url = URL.create('sqlite', database=str(args.sqlite.resolve()))
    if url.get_backend_name() == 'sqlite' and url.database != ':memory:':
        archivo = Path(url.database)
        if not archivo.is_absolute():
            archivo = Path(app.instance_path) / archivo
        if not archivo.is_file():
            parser.error('El archivo SQLite no existe; el diagnóstico no crea bases de datos.')
        url = url.set(database=str(archivo.resolve()))
    app.config['SQLALCHEMY_DATABASE_URI'] = url
    db.init_app(app)
    with app.app_context():
        try:
            if url.get_backend_name() == 'sqlite':
                # Resguardo ejecutable: incluso una escritura accidental falla en SQLite.
                event.listen(db.engine, 'connect', lambda conn, _: conn.execute('PRAGMA query_only=ON'))
            necesarias = {modelo.__tablename__ for modelo in (
                GastronomiaClienteConfig, GastronomiaCategoria, GastronomiaProducto,
                GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago,
                GastronomiaProductoPrecioCanal, Venta,
            )} | {nombre for nombre in db.metadata.tables if nombre.startswith('gastronomia_sugerencias_')}
            faltantes = sorted(necesarias - set(inspect(db.engine).get_table_names()))
            if faltantes:
                print(json.dumps({'estado': 'esquema_pendiente', 'tablas_faltantes': faltantes,
                                  'nota': 'No se crearon tablas ni se modificó la base. Preparar el esquema antes de medir.'},
                                 ensure_ascii=False, indent=2))
                return 2
            clientes = GastronomiaClienteConfig.query.filter_by(gastronomia_activo=True)
            if args.cliente_id is not None:
                clientes = clientes.filter_by(cliente_id=args.cliente_id)
            ids = [c.cliente_id for c in clientes]
            if not ids:
                print(json.dumps({'estado': 'sin_instalacion_activa', 'cliente_id': args.cliente_id}))
                return 2
            canales = [None, *CANALES_PRECIOS] if args.canal == 'todos' else [None if args.canal == 'normal' else args.canal]
            for cliente_id in ids:
                resultado = informe_cliente(cliente_id, limite_detalle=args.limite,
                                            muestra_pos=args.muestra_pos, repeticiones_pos=args.repeticiones_pos,
                                            canales_pos=canales)
                print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return 0
        except SQLAlchemyError as exc:
            print(json.dumps({'estado': 'error_base_datos', 'tipo_error': type(exc).__name__,
                              'nota': 'No se completó el diagnóstico. Revisar conexión y esquema.'}, ensure_ascii=False))
            return 2
        finally:
            db.session.rollback()


if __name__ == '__main__':
    sys.exit(main())
