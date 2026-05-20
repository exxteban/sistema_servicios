#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$app_dir/deploy/install.sh" "$@"


#2954ea8b65cc320cd29a9b8e064720ec