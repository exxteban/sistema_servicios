# Deploy Braking Fat

Datos fijos del cliente:

- Dominio: `brakingfat.pysystems.online`
- IP publica: `151.243.137.190`
- Servicio systemd: `sistema-brakingfat`
- Puerto interno app: `3119`
- Env server: `/etc/sistema_brakingfat.env`

Servidor compartido (3 instancias, cada una con su propia DB, servicio y env):

| Cliente | Puerto | Repo |
|---|---|---|
| Silvio (`ryjcell2`) | `3117` | `sistema_silvio_cel` |
| Lions Burguer | `3118` | `sistema_servicios` |
| Braking Fat | `3119` | `sistema_servicios` |

Antes de instalar, confirmar que el puerto esta libre: `ss -tuln | grep 3119`.

## DNS en Namecheap

Crear o verificar este registro:

```text
Type: A Record
Host: brakingfat
Value: 151.243.137.190
TTL: Automatic
```

## Panel del servidor

La regla web debe exponer `https://brakingfat.pysystems.online` y enviar el trafico al servidor interno donde corre la app. Si el panel maneja el certificado y proxy, debe apuntar al puerto `3119`. Si Caddy queda dentro del servidor, el trafico publico 80/443 debe llegar al Caddy y Caddy hace proxy a `127.0.0.1:3119`.

## Primer Deploy

Usar un clon propio del repo (NO el de Lions Burguer): `logs/`, `app/static/uploads`, `app/static/tienda_uploads` y `.venv` viven dentro del directorio del repo, asi que compartirlo mezclaria archivos entre clientes.

```bash
cd /home/administrator
git clone <url-del-repo-sistema_servicios> sistema_brakingfat
cd sistema_brakingfat
```

En el servidor, dentro de ese clon:

```bash
cp deploy/brakingfat.env.example deploy/brakingfat.env
nano deploy/brakingfat.env
bash deploy/install_brakingfat.sh
```

En un servidor compartido con otro cliente, el instalador crea o actualiza solo `/etc/caddy/sites.d/sistema-brakingfat.caddy`. Si el `Caddyfile` base ya importa `sites.d/*.caddy`, no toca nada mas. Si no existe ese import, el script se detiene y te pide integrarlo manualmente o ejecutar con `CADDY_APPEND_IMPORT=1`.

Si MariaDB `root` usa password, define `DB_ROOT_PASSWORD`. Si el servidor usa `auth_socket` y ejecutas el instalador con `sudo/root`, puede quedar vacio. Si dejas vacios `DB_PASSWORD`, `SECRET_KEY`, `APP_BOOTSTRAP_ADMIN_PASSWORD` y `APP_BOOTSTRAP_ROOT_PASSWORD`, el instalador genera valores seguros.

## Actualizar Codigo Despues

Si ya copiaste/subiste cambios al repo del servidor:

```bash
ENV_FILE_PATH=/etc/sistema_brakingfat.env SERVICE_NAME=sistema-brakingfat bash deploy/update_min.sh
```

Si el servidor hace `git pull` directamente:

```bash
ENV_FILE_PATH=/etc/sistema_brakingfat.env SERVICE_NAME=sistema-brakingfat SKIP_GIT=0 bash deploy/update_min.sh
```

## Verificacion

```bash
systemctl status sistema-brakingfat --no-pager
systemctl status caddy --no-pager
caddy validate --config /etc/caddy/Caddyfile
journalctl -u sistema-brakingfat -n 80 --no-pager
```
