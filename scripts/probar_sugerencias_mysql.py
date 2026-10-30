"""Ejecuta las pruebas contra MariaDB de XAMPP en un puerto y datadir temporales."""
import argparse
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4

import pymysql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql-bin', type=Path, default=Path('C:/xampp/mysql/bin'))
    parser.add_argument('--caso', help='Filtro -k de pytest para repetir un escenario concreto')
    args = parser.parse_args()
    instalador, servidor = args.mysql_bin / 'mysql_install_db.exe', args.mysql_bin / 'mysqld.exe'
    if not instalador.is_file() or not servidor.is_file():
        parser.error('Indicar --mysql-bin con mysql_install_db.exe y mysqld.exe existentes.')
    raiz = Path(__file__).resolve().parents[1]
    cache = (raiz / '.pytest_cache').resolve()
    cache.mkdir(exist_ok=True)
    carpeta = cache / ('mariadb_sugerencias_' + uuid4().hex)
    carpeta.mkdir()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        puerto = sock.getsockname()[1]
    clave = secrets.token_hex(24)
    nombre = 'qa_sugerencias_' + uuid4().hex
    proceso = None
    salida = 1
    opciones = dict(host='127.0.0.1', port=puerto, user='root', password=clave, connect_timeout=1)
    invisible = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        inicio = subprocess.run([str(instalador), '--datadir=' + str(carpeta), '--password=' + clave,
                                 '--port=' + str(puerto), '--silent'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=invisible, timeout=45)
        if inicio.returncode:
            print('No se pudo inicializar el directorio temporal de MariaDB.', file=sys.stderr)
            return 1
        proceso = subprocess.Popen([
            str(servidor), '--no-defaults', '--basedir=' + str(args.mysql_bin.parent.resolve()),
            '--datadir=' + str(carpeta), '--port=' + str(puerto), '--bind-address=127.0.0.1',
            '--log-error=' + str(carpeta / 'servidor.log'), '--innodb-buffer-pool-size=64M',
            '--innodb-flush-log-at-trx-commit=2', '--sync-binlog=0',
            '--character-set-server=utf8mb4', '--collation-server=utf8mb4_unicode_ci',
            '--default-time-zone=+00:00',
            '--sql-mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,ONLY_FULL_GROUP_BY',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=invisible)
        limite = time.monotonic() + 30
        while True:
            try:
                conexion = pymysql.connect(**opciones)
                break
            except pymysql.Error:
                if proceso.poll() is not None or time.monotonic() >= limite:
                    print('MariaDB temporal no pudo arrancar; ninguna instalación existente fue usada.', file=sys.stderr)
                    log = carpeta / 'servidor.log'
                    if log.exists():
                        print('\n'.join(log.read_text(errors='replace').splitlines()[-12:]), file=sys.stderr)
                    return 1
                time.sleep(.2)
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute('SELECT VERSION(), @@sql_mode, @@session.time_zone')
                print('Motor, modo SQL y zona de prueba:', cursor.fetchone(), flush=True)
                cursor.execute(f'CREATE DATABASE `{nombre}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        entorno = {**os.environ, 'SUGERENCIAS_TEST_MYSQL_URL':
                   f'mysql+pymysql://root:{clave}@127.0.0.1:{puerto}/{nombre}?charset=utf8mb4'}
        comando = [sys.executable, '-m', 'pytest', 'test_gastronomia_sugerencias_mysql.py', '-q', '--tb=short']
        if args.caso:
            comando.extend(['-k', args.caso])
        resultado = subprocess.run(comando, cwd=raiz, env=entorno)
        salida = resultado.returncode
        return salida
    finally:
        if proceso is not None and proceso.poll() is None:
            try:
                with pymysql.connect(**opciones) as conexion:
                    with conexion.cursor() as cursor:
                        cursor.execute('SHUTDOWN')
                proceso.wait(timeout=10)
            except (pymysql.Error, subprocess.TimeoutExpired):
                proceso.terminate()
                proceso.wait(timeout=10)
        # Verificación previa a cualquier borrado recursivo en Windows.
        destino = carpeta.resolve()
        if destino.parent != cache or not re.fullmatch(r'mariadb_sugerencias_[0-9a-f]{32}', destino.name):
            raise RuntimeError('Se rechazó limpiar un directorio fuera del área temporal de pruebas.')
        shutil.rmtree(destino)


if __name__ == '__main__':
    sys.exit(main())
