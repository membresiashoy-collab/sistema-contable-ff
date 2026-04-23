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
    """
    Consulta si el comprobante es una Nota de Crédito (Reverso contable).
    """
    t = str(tipo_str).upper()
    return "NOTA DE CRÉDITO" in t or "NOTA DE CREDITO" in t or "NC-" in t

def eliminar_todo_diario():
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM sqlite_sequence WHERE name='libro_diario'")