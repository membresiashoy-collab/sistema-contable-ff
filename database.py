import sqlite3
import pandas as pd

# Base de datos en la raíz para evitar errores de ruta
DB_PATH = "contabilidad_ff.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Reinicio total para asegurar consistencia
        cursor.execute("DROP TABLE IF EXISTS libro_diario")
        cursor.execute("""
            CREATE TABLE libro_diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_asiento INTEGER,
                fecha TEXT,
                cuenta TEXT,
                debe REAL,
                haber REAL,
                glosa TEXT,
                origen TEXT
            )
        """)
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            return pd.read_sql_query(query, conn, params=params)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()