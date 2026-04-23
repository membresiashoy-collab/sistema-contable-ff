import sqlite3
import pandas as pd

DB_NAME = "sistema_ff.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Libro Diario
        cursor.execute("""CREATE TABLE IF NOT EXISTS libro_diario 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cuenta TEXT, 
             debe REAL, haber REAL, glosa TEXT)""")
        
        # Plan de Cuentas (Manda sobre el asiento)
        cursor.execute("""CREATE TABLE IF NOT EXISTS plan_cuentas 
            (codigo TEXT PRIMARY KEY, nombre TEXT, tipo TEXT)""")
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_NAME) as conn:
        if fetch: return pd.read_sql(query, conn, params=params)
        conn.execute(query, params)
        conn.commit()