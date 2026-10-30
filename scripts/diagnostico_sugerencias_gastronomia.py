"""Diagnóstico de solo lectura. No usa create_app ni ejecuta migraciones."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask
from config import config
from app import db
import app.models  # noqa: F401
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.services.sugerencias.informe import informe_cliente


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cliente-id', type=int)
    parser.add_argument('--limite', type=int, default=20, help='Máximo de pares por muestra (1–100)')
    args = parser.parse_args()
    if args.cliente_id is not None and args.cliente_id <= 0:
        parser.error('--cliente-id debe ser positivo')
    if not 1 <= args.limite <= 100:
        parser.error('--limite debe estar entre 1 y 100')
    app = Flask(__name__)
    app.config.from_object(config['default'])
    db.init_app(app)
    with app.app_context():
        try:
            clientes = GastronomiaClienteConfig.query.filter_by(gastronomia_activo=True)
            if args.cliente_id is not None:
                clientes = clientes.filter_by(cliente_id=args.cliente_id)
            for cliente in clientes:
                resultado = informe_cliente(cliente.cliente_id, limite_detalle=args.limite)
                print(json.dumps(resultado, ensure_ascii=False, indent=2))
        finally:
            db.session.rollback()


if __name__ == '__main__':
    main()
