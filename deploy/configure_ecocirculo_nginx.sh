#!/usr/bin/env bash
set -euo pipefail

domain="${DOMAIN:-ecocirculo.pysystems.online}"
expected_public_ip="${EXPECTED_PUBLIC_IP:-204.12.245.108}"
app_port="${APP_PORT:-3116}"
site_name="${NGINX_SITE_NAME:-ecocirculo}"
check_dns="${CHECK_DNS:-1}"
setup_ufw="${SETUP_UFW:-1}"
enable_ufw="${ENABLE_UFW:-1}"
ssh_port="${SSH_PORT:-22}"
stop_caddy="${STOP_CADDY:-1}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

install_nginx() {
  if have_cmd nginx; then
    return 0
  fi

  if have_cmd apt-get; then
    as_root apt-get update -y
    as_root apt-get install -y nginx
  elif have_cmd dnf; then
    as_root dnf install -y nginx
  elif have_cmd yum; then
    as_root yum install -y nginx
  else
    echo "No se detecto gestor de paquetes compatible para instalar Nginx."
    exit 1
  fi
}

install_ufw() {
  if [ "$setup_ufw" != "1" ] || have_cmd ufw; then
    return 0
  fi

  if have_cmd apt-get; then
    as_root apt-get update -y
    as_root apt-get install -y ufw
  elif have_cmd dnf; then
    as_root dnf install -y ufw
  elif have_cmd yum; then
    as_root yum install -y ufw
  else
    echo "Aviso: no se detecto gestor de paquetes compatible para instalar UFW."
  fi
}

configure_ufw() {
  if [ "$setup_ufw" != "1" ]; then
    return 0
  fi

  install_ufw

  if ! have_cmd ufw; then
    echo "Aviso: UFW no esta instalado; se omite configuracion de firewall."
    return 0
  fi

  as_root ufw allow "${ssh_port}/tcp"
  as_root ufw allow 80/tcp
  as_root ufw allow 443/tcp
  as_root ufw default deny incoming
  as_root ufw default allow outgoing

  if [ "$enable_ufw" = "1" ]; then
    as_root ufw --force enable
  else
    echo "UFW configurado pero no habilitado porque ENABLE_UFW=$enable_ufw."
  fi
}

validate_dns() {
  if [ "$check_dns" != "1" ]; then
    return 0
  fi

  if ! have_cmd getent; then
    echo "Aviso: no se pudo validar DNS porque no existe getent."
    return 0
  fi

  resolved_ips="$(getent ahostsv4 "$domain" | awk '{print $1}' | sort -u | tr '\n' ' ')"
  if [ -z "$resolved_ips" ]; then
    echo "Aviso: $domain todavia no resuelve por DNS."
    echo "Configura un registro A hacia $expected_public_ip."
    return 0
  fi

  case " $resolved_ips " in
    *" $expected_public_ip "*) ;;
    *)
      echo "Aviso: $domain resuelve a: $resolved_ips"
      echo "El IP esperado es: $expected_public_ip"
      ;;
  esac
}

write_nginx_site() {
  local available_path="/etc/nginx/sites-available/$site_name"
  local enabled_path="/etc/nginx/sites-enabled/$site_name"
  local tmp_path

  as_root mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
  tmp_path="$(mktemp)"

  cat > "$tmp_path" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $domain;

    client_max_body_size 64m;

    location / {
        proxy_pass http://127.0.0.1:$app_port;
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 3600;
    }
}
EOF

  as_root install -m 0644 "$tmp_path" "$available_path"
  rm -f "$tmp_path"

  as_root ln -sfn "$available_path" "$enabled_path"
}

reload_nginx() {
  as_root nginx -t
  if have_cmd systemctl; then
    as_root systemctl enable --now nginx
    as_root systemctl reload nginx >/dev/null 2>&1 || as_root systemctl restart nginx
  else
    as_root nginx -s reload
  fi
}

disable_caddy() {
  if [ "$stop_caddy" != "1" ]; then
    return 0
  fi

  if have_cmd systemctl; then
    as_root systemctl stop caddy >/dev/null 2>&1 || true
    as_root systemctl disable caddy >/dev/null 2>&1 || true
  fi
}

if [ -z "$domain" ]; then
  echo "DOMAIN no puede estar vacio."
  exit 1
fi

if ! [[ "$app_port" =~ ^[0-9]+$ ]]; then
  echo "APP_PORT invalido: $app_port"
  exit 1
fi

install_nginx
validate_dns
configure_ufw
write_nginx_site
reload_nginx
disable_caddy

echo "Nginx configurado para http://$domain -> 127.0.0.1:$app_port"
echo "Site Nginx: /etc/nginx/sites-available/$site_name"
echo "Caddy detenido/deshabilitado: $stop_caddy"
if [ "$setup_ufw" = "1" ]; then
  echo "Firewall UFW: abiertos ${ssh_port}/tcp, 80/tcp y 443/tcp."
fi
