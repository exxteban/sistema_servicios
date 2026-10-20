# Deploy Demo Gastronomia (hoy usada como demo de peluqueria)

El nombre quedo de la instalacion original; el rubro que se muestra sale de la configuracion
(`modo_operacion_principal` / `dashboard_negocio_activo`), no del nombre del servicio.

Datos fijos de la instancia (servidor `testserver2`):

- Dominio: `demogastronomia.pysystems.online`
- Servicio systemd: `service-demogastronomia` (backup: `service-demogastronomia-backup`)
- Carpeta del repo: `/home/administrator/gastronomia/sistema_servicios`
- Puerto interno: `3119`
- Env server: `/etc/sistema_demogastronomia.env`
- Caddy: `/etc/caddy/sites.d/service-demogastronomia.caddy`

En el mismo servidor corren otras instancias (por ejemplo `sistema-demo1`, que es otro sistema y
usa `/home/administrator/sistema_silvio_cel`). `/home/administrator/sistema_servicios` NO es la
carpeta de esta instancia: actualizar ahi no cambia lo que sirve `demogastronomia`.

## Actualizar Codigo

Siempre desde la carpeta del servicio:

```bash
cd /home/administrator/gastronomia/sistema_servicios
ENV_FILE_PATH=/etc/sistema_demogastronomia.env SERVICE_NAME=service-demogastronomia SKIP_GIT=0 bash deploy/update_min.sh
```

## Verificacion

```bash
systemctl show service-demogastronomia -p WorkingDirectory --no-pager
git -C /home/administrator/gastronomia/sistema_servicios rev-parse --short HEAD
systemctl status service-demogastronomia --no-pager
journalctl -u service-demogastronomia -n 80 --no-pager
```

Caddy hace proxy de `https://demogastronomia.pysystems.online` a `127.0.0.1:3119`.
