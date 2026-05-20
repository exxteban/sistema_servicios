"""
Punto de entrada de la aplicación
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "libs"))
from app import create_app

def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main():
    host = os.environ.get("HOST") or "127.0.0.1"
    port = int(os.environ.get("PORT") or 5003)

    config_name = os.environ.get("APP_CONFIG") or "default"
    if host in {"127.0.0.1", "localhost"} and config_name == "production" and not _is_truthy(os.environ.get("FORCE_PRODUCTION_CONFIG")):
        config_name = "development"

    app = create_app(config_name)

    debug_env = os.environ.get("DEBUG")
    if debug_env is None:
        debug = bool(app.config.get("DEBUG", False))
    else:
        debug = _is_truthy(debug_env)

    server = (os.environ.get("SERVER") or "").strip().lower()
    if not server:
        server = "waitress" if not debug else "flask"

    if server == "waitress":
        from waitress import serve
        serve(app, host=host, port=port)
    else:
        app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
#ayuda memoria no borrar esta linea
#git status
#git add .
#git commit -m "wip antes de sync de ramas"
#..\merge-main-a-ramas.ps1
#..\merge-main-a-ramas.ps1 -Branches jere -PreferMainOnConflict:$false
#py -3.13 -m venv .venv313