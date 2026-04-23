import sqlite3
import pandas as pd
import os

# Ubicación absoluta de la base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
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