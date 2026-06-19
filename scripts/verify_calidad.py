import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def main() -> int:
    app = create_app()
    with app.app_context():
        app.jinja_env.get_template("crm/admin/calidad.html")
        app.jinja_env.get_template("crm/admin/config.html")
        app.jinja_env.get_template("crm/layout.html")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
