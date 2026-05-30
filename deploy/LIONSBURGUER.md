# Deploy Lions Burguer

Datos fijos del cliente:

- Dominio: `lionsburguer.pysystems.online`
- IP publica: `173.208.162.124`
- Servicio systemd: `sistema-lionsburguer`
- Puerto interno app: `3117`
- Env server: `/etc/sistema_lionsburguer.env`

## DNS en Namecheap

Crear o verificar este registro:

```text
Type: A Record
Host: lionsburguer
Value: 173.208.162.124
TTL: Automatic
```

## Panel del servidor

La regla web debe exponer `https://lionsburguer.pysystems.online` y enviar el trafico al servidor interno donde corre la app. Si el panel maneja el certificado y proxy, debe apuntar al puerto `3117`. Si Caddy queda dentro del servidor, el trafico publico 80/443 debe llegar al Caddy y Caddy hace proxy a `127.0.0.1:3117`.

## Primer Deploy

En el servidor, dentro del repo:

```bash
cp deploy/lionsburguer.env.example deploy/lionsburguer.env
nano deploy/lionsburguer.env
bash deploy/install_lionsburguer.sh
```

Si MariaDB `root` usa password, define `DB_ROOT_PASSWORD`. Si el servidor usa `auth_socket` y ejecutas el instalador con `sudo/root`, puede quedar vacio. Si dejas vacios `DB_PASSWORD`, `SECRET_KEY`, `APP_BOOTSTRAP_ADMIN_PASSWORD` y `APP_BOOTSTRAP_ROOT_PASSWORD`, el instalador genera valores seguros.

## Actualizar Codigo Despues

Si ya copiaste/subiste cambios al repo del servidor:

```bash
ENV_FILE_PATH=/etc/sistema_lionsburguer.env SERVICE_NAME=sistema-lionsburguer bash deploy/update_min.sh
```

Si el servidor hace `git pull` directamente:

```bash
ENV_FILE_PATH=/etc/sistema_lionsburguer.env SERVICE_NAME=sistema-lionsburguer SKIP_GIT=0 bash deploy/update_min.sh
```

## Verificacion

```bash
systemctl status sistema-lionsburguer --no-pager
systemctl status caddy --no-pager
caddy validate --config /etc/caddy/Caddyfile
journalctl -u sistema-lionsburguer -n 80 --no-pager
```
