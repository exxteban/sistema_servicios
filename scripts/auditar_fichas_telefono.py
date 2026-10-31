"""Registra la ficha por celular de los clientes anteriores a BI-05d y lista celulares repetidos.

Uso: python scripts/auditar_fichas_telefono.py <cliente_id> [--solo-listar]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from gastronomia.services.fidelizacion_auditoria import auditar_fichas_telefono  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cliente_id', type=int)
    parser.add_argument('--solo-listar', action='store_true')
    args = parser.parse_args()
    with create_app().app_context():
        resultado = auditar_fichas_telefono(args.cliente_id, registrar=not args.solo_listar)
    print(f"Fichas {'por registrar' if args.solo_listar else 'registradas'}: {resultado['registradas']}")
    for telefono, ids in resultado['duplicados'].items():
        print(f'Celular repetido {telefono}: clientes {ids}')


if __name__ == '__main__':
    main()
