import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_cargas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modulo TEXT,
                nombre_archivo TEXT,
                registros_procesados INTEGER
            )
        """)
        cursor.execute("CREATE TABLE IF NOT EXISTS plan_cuentas (codigo TEXT PRIMARY KEY, nombre TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS tipos_comprobantes (codigo INTEGER PRIMARY KEY, descripcion TEXT, signo INTEGER)")

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def registrar_carga(modulo, archivo, cantidad):
    ejecutar_query(
        "INSERT INTO historial_cargas (modulo, nombre_archivo, registros_procesados) VALUES (?,?,?)",
        (modulo, archivo, cantidad)
    )

def eliminar_todo_diario():
    # Limpieza profunda de tablas y reseteo de IDs
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM sqlite_sequence WHERE name='libro_diario'")
    ejecutar_query("DELETE FROM historial_cargas")