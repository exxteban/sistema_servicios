#!/usr/bin/env bash
#
# Instala el microservicio SIFEN (Node) como servicio systemd para que arranque
# solo y se reinicie si se cae. Pensado para el mismo servidor donde corre el
# sistema Flask (lo consume en localhost).
#
# Uso:
#   sudo SERVICE_USER=miusuario PORT=3010 bash install_systemd.sh
#
# Variables (todas opcionales):
#   SERVICE_NAME   Nombre del servicio systemd        (default: sifen-service)
#   SERVICE_USER   Usuario que corre el servicio       (default: www-data)
#   SERVICE_GROUP  Grupo del servicio                  (default: = SERVICE_USER)
#   PORT           Puerto donde escucha                (default: 3010)
#   NODE_BIN       Ruta del binario node               (default: autodetect)
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-sifen-service}"
SERVICE_USER="${SERVICE_USER:-www-data}"
SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"
PORT="${PORT:-3010}"

# Carpeta del servicio = carpeta padre de este script (deploy/..).
SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NODE_BIN="${NODE_BIN:-$(command -v node || true)}"
if [ -z "$NODE_BIN" ]; then
  echo "ERROR: no se encontró 'node'. Instalá Node.js 18+ antes de continuar." >&2
  exit 1
fi
echo "Node: $NODE_BIN ($($NODE_BIN --version))"

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

echo "==> Instalando dependencias en $SERVICE_DIR"
install_deps='cd "'"$SERVICE_DIR"'" && ( npm ci --omit=dev 2>/dev/null || npm install --omit=dev )'
if [ "$(id -u)" -eq 0 ] && [ "$SERVICE_USER" != "root" ]; then
  # Que node_modules quede del usuario del servicio, no de root.
  as_root chown -R "$SERVICE_USER:$SERVICE_GROUP" "$SERVICE_DIR"
  sudo -u "$SERVICE_USER" bash -lc "$install_deps"
else
  bash -lc "$install_deps"
fi

unit_path="/etc/systemd/system/${SERVICE_NAME}.service"
echo "==> Escribiendo unidad systemd: $unit_path"

as_root bash -lc "cat > '$unit_path' <<EOF
[Unit]
Description=Microservicio SIFEN (xmlgen/xmlsign) - TIPS
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$SERVICE_DIR
Environment=NODE_ENV=production
Environment=PORT=$PORT
ExecStart=$NODE_BIN $SERVICE_DIR/index.js
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF"

echo "==> Activando servicio"
as_root systemctl daemon-reload
as_root systemctl enable --now "$SERVICE_NAME"

echo
echo "Listo. El servicio '$SERVICE_NAME' quedó corriendo en http://localhost:$PORT"
echo "  Estado:  systemctl status $SERVICE_NAME"
echo "  Logs:    journalctl -u $SERVICE_NAME -f"
echo "  Probar:  curl http://localhost:$PORT/health"
