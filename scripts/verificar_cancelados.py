import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Reparacion
from sqlalchemy import func

app = create_app('development')
with app.app_context():
    conteos_query = db.session.query(Reparacion.estado, func.count(Reparacion.id_reparacion)).group_by(Reparacion.estado).all()
    for estado, total in conteos_query:
        print(f"Estado '{estado}': {total}")
