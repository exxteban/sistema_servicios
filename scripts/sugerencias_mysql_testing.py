"""Bases desechables exclusivamente dentro del servidor aislado del runner de pruebas."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@contextmanager
def base_mysql():
    url = make_url(os.environ['SUGERENCIAS_TEST_MYSQL_URL'])
    if (url.get_backend_name() not in {'mysql', 'mariadb'} or url.host != '127.0.0.1'
            or not re.fullmatch(r'qa_sugerencias_[0-9a-f]{32}', url.database or '')):
        raise ValueError('Solo se admite el servidor temporal creado por probar_sugerencias_mysql.py.')
    admin = create_engine(url, connect_args={'connect_timeout': 3})
    nombre = 'qa_sugerencias_' + uuid4().hex
    creado = False
    try:
        with admin.begin() as conn:
            carpeta = Path(conn.execute(text('SELECT @@datadir')).scalar_one()).resolve()
            cache = (Path(__file__).resolve().parents[1] / '.pytest_cache').resolve()
            if carpeta.parent != cache or not re.fullmatch(r'mariadb_sugerencias_[0-9a-f]{32}', carpeta.name):
                raise ValueError('El servidor no usa el directorio de datos temporal del runner.')
            conn.execute(text(f'CREATE DATABASE `{nombre}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
            creado = True
        yield url.set(database=nombre)
    finally:
        if creado:
            with admin.begin() as conn:
                conn.execute(text(f'DROP DATABASE `{nombre}`'))
        admin.dispose()
