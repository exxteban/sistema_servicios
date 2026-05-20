# Testing local

## Preparar entorno

En Windows PowerShell:

```powershell
.\scripts\setup_test_env.ps1
```

Eso recrea `.venv` si quedo apuntando a otro Python, actualiza `pip` e instala dependencias de aplicacion y testing.
Tambien refresca las dependencias Node del proyecto y de `tienda_online`.

## Ejecutar pruebas

Backend + build del frontend:

```powershell
.\scripts\run_tests.ps1
```

Solo backend:

```powershell
.\scripts\run_tests.ps1 -SkipFrontend
```

Solo un subset de pytest:

```powershell
.\scripts\run_tests.ps1 test_pos_toggle_config.py -q
```

## Atajos

Tambien se puede usar:

```powershell
npm test
```

`conftest.py` fuerza defaults seguros para testing:

- usa una SQLite aislada en `.pytest_cache/test_runtime.sqlite3`
- desactiva IA y WhatsApp reales
- baja el ruido de logs
