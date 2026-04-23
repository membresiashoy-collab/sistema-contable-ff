import sqlite3
import pandas as pd
import os

# Forzamos la ruta al directorio actual para que no se pierda
DB_PATH = os.path.join(os.path.dirname(__file__), "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS libro_diario 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cuenta TEXT, 
             debe REAL, haber REAL, glosa TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS plan_cuentas 
            (codigo TEXT PRIMARY KEY, nombre TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS tipos_comprobantes 
            (codigo INTEGER PRIMARY KEY, descripcion TEXT, signo INTEGER)""")
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            return pd.read_sql(query, conn, params=params)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()