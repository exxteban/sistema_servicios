# Deploy Breaking Fat

Datos fijos del cliente:

- Dominio: `breakingfat.pysystems.online`
- IP publica: `151.243.137.190`
- Servicio systemd: `sistema-breakingfat`
- Puerto interno app: `3120`
- Env server: `/etc/sistema_breakingfat.env`

Servidor compartido (cada instancia con su propia DB, servicio y env):

| Cliente | Puerto | Repo |
|---|---|---|
| Silvio (`ryjcell2`) | `3117` | `sistema_silvio_cel` |
| Lions Burguer | `3118` | `sistema_servicios` |
| (otra instancia, ocupado) | `3119` | ? |
| (otra instancia, ocupado) | `3124` | ? |
| Breaking Fat | `3120` | `sistema_servicios` |

Antes de instalar, confirmar que el puerto esta libre: `ss -tuln | grep 3120`.

## DNS en Namecheap

Crear o verificar este registro:

```text
Type: A Record
Host: breakingfat
Value: 151.243.137.190
TTL: Automatic
```

## Panel del servidor

La regla web debe exponer `https://breakingfat.pysystems.online` y enviar el trafico al servidor interno donde corre la app. Si el panel maneja el certificado y proxy, debe apuntar al puerto `3120`. Si Caddy queda dentro del servidor, el trafico publico 80/443 debe llegar al Caddy y Caddy hace proxy a `127.0.0.1:3120`.

## Primer Deploy

Usar un clon propio del repo (NO el de Lions Burguer): `logs/`, `app/static/uploads`, `app/static/tienda_uploads` y `.venv` viven dentro del directorio del repo, asi que compartirlo mezclaria archivos entre clientes.

En este servidor los repos viven en `/root` (`/root/silvio`, `/root/lionsburguer`, ...), asi que Breaking Fat va en `/root/breakingfat`:

```bash
cd /root
git clone https://github.com/exxteban/sistema_servicios.git breakingfat
cd breakingfat
```

Usar el mismo `SERVICE_USER` que Lions Burguer (ver `grep -E '^User|^WorkingDirectory' /etc/systemd/system/sistema-lionsburguer.service`). Si el servicio corre como un usuario distinto de root, ese usuario no puede leer `/root`.

En el servidor, dentro de ese clon:

```bash
cp deploy/breakingfat.env.example deploy/breakingfat.env
nano deploy/breakingfat.env
bash deploy/install_breakingfat.sh
```

En un servidor compartido con otro cliente, el instalador crea o actualiza solo `/etc/caddy/sites.d/sistema-breakingfat.caddy`. Si el `Caddyfile` base ya importa `sites.d/*.caddy`, no toca nada mas. Si no existe ese import, el script se detiene y te pide integrarlo manualmente o ejecutar con `CADDY_APPEND_IMPORT=1`.

Si MariaDB `root` usa password, define `DB_ROOT_PASSWORD`. Si el servidor usa `auth_socket` y ejecutas el instalador con `sudo/root`, puede quedar vacio. Si dejas vacios `DB_PASSWORD`, `SECRET_KEY`, `APP_BOOTSTRAP_ADMIN_PASSWORD` y `APP_BOOTSTRAP_ROOT_PASSWORD`, el instalador genera valores seguros.

## Actualizar Codigo Despues

Si ya copiaste/subiste cambios al repo del servidor:

```bash
ENV_FILE_PATH=/etc/sistema_breakingfat.env SERVICE_NAME=sistema-breakingfat bash deploy/update_min.sh
```

Si el servidor hace `git pull` directamente:

```bash
ENV_FILE_PATH=/etc/sistema_breakingfat.env SERVICE_NAME=sistema-breakingfat SKIP_GIT=0 bash deploy/update_min.sh
```

## Verificacion

```bash
systemctl status sistema-breakingfat --no-pager
systemctl status caddy --no-pager
caddy validate --config /etc/caddy/Caddyfile
journalctl -u sistema-breakingfat -n 80 --no-pager
```
