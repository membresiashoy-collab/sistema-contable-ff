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
        
        # Plan de Cuentas
        cursor.execute("""CREATE TABLE IF NOT EXISTS plan_cuentas 
            (codigo TEXT PRIMARY KEY, nombre TEXT)""")
        
        # NUEVA: Tabla de Tipos de Comprobantes
        cursor.execute("""CREATE TABLE IF NOT EXISTS tipos_comprobantes 
            (codigo INTEGER PRIMARY KEY, descripcion TEXT, signo INTEGER)""")
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_NAME) as conn:
        if fetch: return pd.read_sql(query, conn, params=params)
        conn.execute(query, params)
        conn.commit()