# Deploy Demo Peluqueria

Datos fijos del demo:

- Dominio: `peluqueriademo.pysystems.online`
- IP publica: `38.247.128.125` (mismo servidor que `demoservicios`)
- Carpeta del repo: `/home/administrator/peluqueriademo/sistema_servicios`
- Servicio systemd: `sistema-peluqueriademo`
- Puerto interno: `3126`
- Env server: `/etc/sistema_peluqueriademo.env`
- Base de datos: `peluqueriademo` (usuario `peluqueriademo_user`)

## DNS

Registro A `peluqueriademo` -> `38.247.128.125` (en Cloudflare "Solo DNS", sin proxy naranja,
asi Caddy puede sacar el certificado).

## Primer Deploy

En el servidor:

```bash
ss -ltnp | grep ':3126' || echo "puerto 3126 libre"
mkdir -p /home/administrator/peluqueriademo && cd /home/administrator/peluqueriademo
git clone -b main --single-branch https://github.com/exxteban/sistema_servicios.git
cd sistema_servicios
cp deploy/peluqueriademo.env.example deploy/peluqueriademo.env
nano deploy/peluqueriademo.env
bash deploy/install_peluqueriademo.sh
```

Si MariaDB `root` usa password, define `DB_ROOT_PASSWORD`. Si el servidor usa `auth_socket` y ejecutas el instalador con `sudo/root`, puede quedar vacio. Si dejas vacios `DB_PASSWORD`, `SECRET_KEY`, `APP_BOOTSTRAP_ADMIN_PASSWORD` y `APP_BOOTSTRAP_ROOT_PASSWORD`, el instalador genera valores seguros y los imprime una sola vez: guardalos.

El rubro no sale del nombre de la instancia: despues del primer login, en Configuracion elegir
peluqueria como modo de operacion / dashboard del negocio (`modo_operacion_principal` /
`dashboard_negocio_activo`).

## Actualizar Codigo Despues

```bash
cd /home/administrator/peluqueriademo/sistema_servicios
ENV_FILE_PATH=/etc/sistema_peluqueriademo.env SERVICE_NAME=sistema-peluqueriademo SKIP_GIT=0 bash deploy/update_min.sh
```

## Verificacion

```bash
systemctl show sistema-peluqueriademo -p WorkingDirectory --no-pager
systemctl status sistema-peluqueriademo --no-pager
systemctl status caddy --no-pager
caddy validate --config /etc/caddy/Caddyfile
journalctl -u sistema-peluqueriademo -n 80 --no-pager
```

Caddy debe exponer `https://peluqueriademo.pysystems.online` y hacer proxy a `127.0.0.1:3126`. No hace falta abrir el puerto `3126` en UFW.
