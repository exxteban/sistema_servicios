#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file_path="${ENV_FILE_PATH:-/etc/sistema_cliente2.env}"
backup_dir="${BACKUP_DIR:-$app_dir/backups}"
retention_days="${RETENTION_DAYS:-14}"
compress="${COMPRESS:-1}"

now_ts="$(date +%F_%H-%M-%S)"
lock_dir="${LOCK_DIR:-/tmp/sistema_cliente2_backup.lock}"
tmp_dump=""

if [ -d "$lock_dir" ]; then
  echo "Backup ya en ejecución (lock: $lock_dir)."
  exit 0
fi

mkdir -p "$lock_dir"
cleanup() {
  rm -f "${tmp_dump:-}" 2>/dev/null || true
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

if [ -f "$env_file_path" ]; then
  set -a
  . "$env_file_path"
  set +a
fi

database_url="${DATABASE_URL:-}"
if [ -z "$database_url" ]; then
  echo "Falta DATABASE_URL (no se encontró en ENV_FILE_PATH: $env_file_path)."
  exit 1
fi

mkdir -p "$backup_dir"

eval "$(
python3 - <<'PY'
import os
import shlex
import urllib.parse

u = os.environ.get("DATABASE_URL") or ""
p = urllib.parse.urlparse(u)
scheme = p.scheme or ""
host = urllib.parse.unquote(p.hostname or "")
port = str(p.port or (3306 if scheme.startswith("mysql") else ""))
user = urllib.parse.unquote(p.username or "")
password = urllib.parse.unquote(p.password or "")
db_name = urllib.parse.unquote((p.path or "").lstrip("/"))
sqlite_path = urllib.parse.unquote(p.path or "")

def out(k, v):
    print(f"{k}={shlex.quote(v)}")

out("DB_SCHEME", scheme)
out("DB_HOST", host)
out("DB_PORT", port)
out("DB_USER", user)
out("DB_PASSWORD", password)
out("DB_NAME", db_name)
out("SQLITE_PATH", sqlite_path)
PY
)"

backup_path=""

if [[ "$DB_SCHEME" == sqlite* ]]; then
  db_file="$SQLITE_PATH"
  if [ -z "$db_file" ]; then
    echo "No se pudo resolver el path de SQLite desde DATABASE_URL."
    exit 1
  fi
  if [ ! -f "$db_file" ]; then
    echo "No existe el archivo SQLite: $db_file"
    exit 1
  fi

  base_name="$(basename "$db_file")"
  backup_path="$backup_dir/${base_name%.db}_${now_ts}.db"
  cp -f "$db_file" "$backup_path"
else
  dump_cmd=""
  if command -v mysqldump >/dev/null 2>&1; then
    dump_cmd="mysqldump"
  elif command -v mariadb-dump >/dev/null 2>&1; then
    dump_cmd="mariadb-dump"
  else
    echo "No se encontró mysqldump/mariadb-dump."
    exit 1
  fi

  supports_dump_arg() {
    "$dump_cmd" --help 2>&1 | grep -q -- "$1"
  }

  if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_HOST" ]; then
    echo "DATABASE_URL incompleto para MySQL/MariaDB."
    exit 1
  fi

  base_dump="$backup_dir/${DB_NAME}_${now_ts}.sql"
  tmp_dump="${base_dump}.tmp"
  export MYSQL_PWD="$DB_PASSWORD"

  dump_args=(--host="$DB_HOST" --port="${DB_PORT:-3306}" --user="$DB_USER" --single-transaction --routines --events --triggers)
  if supports_dump_arg "set-gtid-purged"; then
    dump_args+=(--set-gtid-purged=OFF)
  fi
  if supports_dump_arg "column-statistics"; then
    dump_args+=(--column-statistics=0)
  fi

  "$dump_cmd" "${dump_args[@]}" "$DB_NAME" >"$tmp_dump"
  if [ ! -s "$tmp_dump" ]; then
    echo "El dump salió vacío: $tmp_dump"
    exit 1
  fi

  if [ "$compress" = "1" ] && command -v gzip >/dev/null 2>&1; then
    gzip -c "$tmp_dump" >"${base_dump}.gz"
    rm -f "$tmp_dump"
    tmp_dump=""
    backup_path="${base_dump}.gz"
  else
    mv -f "$tmp_dump" "$base_dump"
    tmp_dump=""
    backup_path="$base_dump"
  fi
fi

if [ -n "$backup_path" ]; then
  chmod 600 "$backup_path" 2>/dev/null || true
  echo "Backup OK: $backup_path"

  rclone_dest_dir="${RCLONE_DEST_DIR:-}"
  rclone_config="${RCLONE_CONFIG:-}"
  rclone_fail_open="${RCLONE_FAIL_OPEN:-0}"
  rclone_op="${RCLONE_OP:-copy}"

  if [ -n "$rclone_dest_dir" ]; then
    if ! command -v rclone >/dev/null 2>&1; then
      echo "No se encontró rclone (RCLONE_DEST_DIR definido: $rclone_dest_dir)."
      if [ "$rclone_fail_open" != "1" ]; then
        exit 1
      fi
    else
      rclone_args=()
      if [ -n "$rclone_config" ]; then
        rclone_args+=(--config "$rclone_config")
      fi
      dest_path="${rclone_dest_dir%/}/$(basename "$backup_path")"
      if [ "$rclone_op" = "move" ]; then
        rclone moveto "${rclone_args[@]}" "$backup_path" "$dest_path"
      else
        rclone copyto "${rclone_args[@]}" "$backup_path" "$dest_path"
      fi
      echo "Backup enviado: $dest_path"
    fi
  fi
fi

if [ "$retention_days" -gt 0 ] 2>/dev/null; then
  find "$backup_dir" -type f \( -name "*.sql" -o -name "*.sql.gz" -o -name "*.db" \) -mtime "+$retention_days" -delete 2>/dev/null || true
  find "$backup_dir" -type f -name "*.tmp" -mtime "+2" -delete 2>/dev/null || true
fi
