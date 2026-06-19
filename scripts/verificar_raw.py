import sqlite3
import pprint

conn = sqlite3.connect('inventario.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM reparaciones LIMIT 5")
rows = cur.fetchall()
for row in rows:
    print(dict(row))
print("--- Counts by estado ---")
cur.execute("SELECT estado, COUNT(*) as c FROM reparaciones GROUP BY estado")
for row in cur.fetchall():
    print(f"{row['estado']}: {row['c']}")
