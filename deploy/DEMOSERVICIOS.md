# Deploy Demo Servicios

Datos fijos del demo:

- Dominio: `demoservicios.pysystems.online`
- IP publica: `38.247.128.125`
- Servicio systemd: `sistema-demoservicios`
- Puerto interno: `3117`
- Env server: `/etc/sistema_demoservicios.env`

## DNS en Namecheap

Crear o verificar este registro:

```text
Type: A Record
Host: demoservicios
Value: 38.247.128.125
TTL: Automatic
```

## Primer Deploy

En el servidor, dentro del repo:

```bash
cp deploy/demoservicios.env.example deploy/demoservicios.env
nano deploy/demoservicios.env
bash deploy/install_demoservicios.sh
```

Si MariaDB `root` usa password, define `DB_ROOT_PASSWORD`. Si el servidor usa `auth_socket` y ejecutas el instalador con `sudo/root`, puede quedar vacio. Si dejas vacios `DB_PASSWORD`, `SECRET_KEY`, `APP_BOOTSTRAP_ADMIN_PASSWORD` y `APP_BOOTSTRAP_ROOT_PASSWORD`, el instalador genera valores seguros. El deploy ejecuta tambien la migracion base de gastronomia (`RUN_GASTRONOMIA_MIGRATIONS=1`).

## Actualizar Codigo Despues

Si ya copiaste/subiste cambios al repo del servidor:

```bash
ENV_FILE_PATH=/etc/sistema_demoservicios.env SERVICE_NAME=sistema-demoservicios bash deploy/update_min.sh
```

Si el servidor hace `git pull` directamente:

```bash
ENV_FILE_PATH=/etc/sistema_demoservicios.env SERVICE_NAME=sistema-demoservicios SKIP_GIT=0 bash deploy/update_min.sh
```

## Verificacion

```bash
systemctl status sistema-demoservicios --no-pager
systemctl status caddy --no-pager
caddy validate --config /etc/caddy/Caddyfile
journalctl -u sistema-demoservicios -n 80 --no-pager
```

Caddy debe exponer `https://demoservicios.pysystems.online` y hacer proxy a `127.0.0.1:3117`. No hace falta abrir el puerto `3117` en UFW.
