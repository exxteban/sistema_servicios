# Validación del sugeridor en MariaDB

El runner usa los ejecutables existentes de XAMPP para crear una instancia
temporal: puerto libre en `127.0.0.1`, contraseña aleatoria y directorio de
datos nuevo en `.pytest_cache/mariadb_sugerencias_<uuid>`.

```powershell
.\.venv\Scripts\python.exe scripts/probar_sugerencias_mysql.py
```

Si XAMPP está en otra carpeta, indicar `--mysql-bin RUTA`. Para repetir un
escenario concreto, agregar `--caso texto_del_nombre` (filtro `-k` de pytest).
No instala servicios de Windows ni utiliza la configuración, el directorio
`data` o las bases de la instancia habitual de XAMPP.

Cada caso recibe una base nueva. La fixture valida el nombre aleatorio,
la dirección local y `@@datadir` antes de crear o eliminar bases. El URI de
prueba se genera en el proceso: no usa `DATABASE_URL` ni se guarda en `.env`.
Sin ese entorno, los casos nativos se omiten en una corrida normal de pytest.

Al terminar, apaga el servidor y elimina exclusivamente su carpeta temporal,
verificando primero la ruta absoluta y el prefijo. Se ejecuta con `utf8mb4`,
UTC y modo estricto incluyendo `ONLY_FULL_GROUP_BY`. Las opciones de flush
relajadas se limitan a esta instancia desechable para agilizar pruebas
funcionales; estos tiempos no representan rendimiento o durabilidad de producción.

Los escenarios se reutilizan desde las pruebas existentes: cálculo,
exclusiones, reglas, aislamiento, precios por canal, registro por pedido,
anulaciones, medición, fatiga, diagnóstico y candado entre workers.
Además se fuerza un error SQL real al insertar en cada tabla estadística y
se comprueba que el pedido, envío a cocina, cobro central y stock siguen bien.

Dos detalles que las pruebas deben respetar en este motor:

- Con `REPEATABLE READ`, `expire_all()` no renueva la instantánea de una
  transacción. Las comprobaciones de escrituras confirmadas en otra sesión
  terminan primero la transacción de lectura anterior, como sucede entre
  requests. Se conserva el registro estadístico en su transacción independiente.
- `DATETIME` sin precisión fraccionaria guarda segundos. La comparación de
  los 30 días de fatiga contempla esa precisión sin exigir microsegundos.

Resultado del 30/10/2026: **33 escenarios aprobados en MariaDB 10.4.32**,
incluidos candado entre workers y errores SQL reales en las dos tablas
estadísticas. Se crearon y consultaron tablas reales, no solo DDL compilado.
También pasaron las **61 pruebas del sugeridor en SQLite** después de ajustar
las comprobaciones de transacciones y fechas. El servidor temporal se apagó
y se eliminó su directorio al finalizar.

Esta comprobación corresponde a MariaDB local; Oracle MySQL no se ejecutó
en esta ronda. La revisión de
historiales y tiempos HTTP de instalaciones desplegadas se documenta aparte.
