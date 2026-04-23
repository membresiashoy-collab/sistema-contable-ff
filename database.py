import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Tabla Libro Diario (ya existente)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS libro_diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_asiento INTEGER,
                fecha TEXT,
                cuenta TEXT,
                debe REAL,
                haber REAL,
                glosa TEXT
            )
        """)
        # NUEVA: Tabla de Compras para estadísticas e IVA
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                proveedor TEXT,
                neto_gravado REAL,
                iva_total REAL,
                total REAL
            )
        """)
        conn.commit()

def obtener_proximo_asiento():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id_asiento) FROM libro_diario")
        res = cursor.fetchone()[0]
        return (res + 1) if res else 1