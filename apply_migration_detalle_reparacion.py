from app import create_app, db
from sqlalchemy import text

app = create_app()

def migrate_detalle_reparacion():
    with app.app_context():
        # Verificar si la tabla ya existe
        inspector = db.inspect(db.engine)
        if 'detalle_reparaciones' not in inspector.get_table_names():
            print("Creando tabla detalle_reparaciones...")
            try:
                # Crear la tabla usando SQL directo para evitar problemas con migraciones complejas
                sql = """
                CREATE TABLE detalle_reparaciones (
                    id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_reparacion INTEGER NOT NULL,
                    id_producto INTEGER NOT NULL,
                    cantidad INTEGER DEFAULT 1,
                    precio_unitario NUMERIC(10, 2) NOT NULL,
                    subtotal NUMERIC(10, 2) NOT NULL,
                    nombre_producto VARCHAR(200),
                    es_servicio BOOLEAN DEFAULT 0,
                    FOREIGN KEY(id_reparacion) REFERENCES reparaciones(id_reparacion),
                    FOREIGN KEY(id_producto) REFERENCES productos(id_producto)
                );
                """
                # Ajuste para MySQL/MariaDB si fuera necesario, pero SQLite usa AUTOINCREMENT
                # Si usas MySQL en producción, el SQL sería ligeramente diferente (AUTO_INCREMENT)
                # Como veo archivos .FDB (Firebird?) y .db (SQLite?), asumo SQLite por el contexto de Flask local usualmente
                # pero el archivo LS muestra .FDB.
                # Voy a usar SQLAlchemy para crearlo de forma agnóstica si es posible, 
                # pero db.create_all() podría intentar crear todo.
                
                # Mejor estrategia: Usar db.create_all() solo para las tablas nuevas si es posible,
                # o ejecutar el SQL específico.
                
                db.session.execute(text(sql))
                db.session.commit()
                print("Tabla creada exitosamente.")
            except Exception as e:
                print(f"Error creando tabla: {e}")
                db.session.rollback()
        else:
            print("La tabla detalle_reparaciones ya existe.")

if __name__ == '__main__':
    migrate_detalle_reparacion()
