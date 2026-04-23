import sqlite3
import pandas as pd
import os

# Usamos una ruta absoluta para evitar que el archivo "desaparezca" entre módulos
DB_PATH = os.path.join(os.getcwd(), "contabilidad_ff.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Tabla de Diario
    cursor.execute("""CREATE TABLE IF NOT EXISTS libro_diario 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cuenta TEXT, 
         debe REAL, haber REAL, glosa TEXT)""")
    # Tabla de Plan de Cuentas
    cursor.execute("""CREATE TABLE IF NOT EXISTS plan_cuentas 
        (codigo TEXT PRIMARY KEY, nombre TEXT)""")
    # Tabla de Comprobantes
    cursor.execute("""CREATE TABLE IF NOT EXISTS tipos_comprobantes 
        (codigo INTEGER PRIMARY KEY, descripcion TEXT, signo INTEGER)""")
    conn.commit()
    conn.close()

def ejecutar_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    try:
        if fetch:
            return pd.read_sql(query, conn, params=params)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
    finally:
        conn.close()