import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Tabla de Diario con columna Origen para filtros
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS libro_diario (
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
        # Tabla de control de archivos
        cursor.execute("CREATE TABLE IF NOT EXISTS archivos_cargados (nombre TEXT PRIMARY KEY)")
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def obtener_proximo_asiento():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id_asiento) FROM libro_diario")
        res = cursor.fetchone()[0]
        return (res + 1) if res else 1

def es_comprobante_reverso(tipo_str):
    """Lógica basada en tabla de comprobantes ARCA"""
    t = str(tipo_str).upper()
    return any(x in t for x in ["NOTA DE CRÉDITO", "NOTA DE CREDITO", "NC-"])

def archivo_ya_cargado(nombre):
    df = ejecutar_query("SELECT nombre FROM archivos_cargados WHERE nombre = ?", (nombre,), fetch=True)
    return not df.empty

def registrar_archivo(nombre):
    ejecutar_query("INSERT OR REPLACE INTO archivos_cargados (nombre) VALUES (?)", (nombre,))

def borrar_todo_el_sistema():
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM archivos_cargados")
    ejecutar_query("DELETE FROM sqlite_sequence WHERE name='libro_diario'")