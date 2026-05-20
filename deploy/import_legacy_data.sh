#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file_path="${ENV_FILE_PATH:-/etc/sistema_cliente2.env}"
venv_path="${VENV_PATH:-$app_dir/.venv}"
python_bin="$venv_path/bin/python"
csv_dir="${CSV_DIR:-}"
csv_file="${CSV_FILE:-}"

if [ ! -x "$python_bin" ]; then
  echo "No se encontró python del venv: $python_bin"
  exit 1
fi

if [ -f "$env_file_path" ]; then
  set -a
  . "$env_file_path"
  set +a
fi

cd "$app_dir"
if [ -n "$csv_file" ]; then
  PYTHONPATH="$app_dir${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" "$app_dir/deploy/import_legacy_products_csv.py" --csv "$csv_file"
  exit 0
fi

if [ -z "$csv_dir" ]; then
  if ls "$app_dir/deploy/"*.csv* >/dev/null 2>&1; then
    csv_file="$(ls -t "$app_dir/deploy/"*.csv* | head -n 1)"
  elif ls "$app_dir/Base de datos/"*.csv >/dev/null 2>&1; then
    csv_dir="Base de datos"
  else
    exit 0
  fi
fi

if [ -n "${csv_file:-}" ]; then
  PYTHONPATH="$app_dir${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" "$app_dir/deploy/import_legacy_products_csv.py" --csv "$csv_file"
else
  PYTHONPATH="$app_dir${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" "$app_dir/deploy/import_legacy_products_csv.py" --auto --csv-dir "$csv_dir"
fi
