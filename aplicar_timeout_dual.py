"""
Migración: Agrega columnas de tracking de timeout dual a whatsapp_asignacion_conversacion.

Columnas nuevas:
  - ultima_respuesta_asesor_at  (DATETIME, nullable): última vez que el asesor envió un mensaje activo.
  - motivo_devolucion           (VARCHAR(30), nullable): razón por la que se devolvió la asignación.

Ejecutar una sola vez:
    python aplicar_timeout_dual.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'inventario.db')

COLUMNAS = [
    ("ultima_respuesta_asesor_at", "DATETIME"),
    ("motivo_devolucion", "VARCHAR(30)"),
]

TABLE = "whatsapp_asignacion_conversacion"


def columnas_existentes(cursor, tabla):
    cursor.execute(f"PRAGMA table_info({tabla})")
    return {row[1] for row in cursor.fetchall()}


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: No se encontró la base de datos en: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    existentes = columnas_existentes(cursor, TABLE)
    agregadas = []
    ya_existian = []

    for nombre, tipo in COLUMNAS:
        if nombre in existentes:
            ya_existian.append(nombre)
        else:
            cursor.execute(f"ALTER TABLE {TABLE} ADD COLUMN {nombre} {tipo}")
            agregadas.append(nombre)

    conn.commit()
    conn.close()

    if agregadas:
        print(f"OK: Columnas agregadas: {', '.join(agregadas)}")
    if ya_existian:
        print(f"YA EXISTÍAN: {', '.join(ya_existian)}")
    if not agregadas and not ya_existian:
        print("Sin cambios.")


if __name__ == '__main__':
    main()
