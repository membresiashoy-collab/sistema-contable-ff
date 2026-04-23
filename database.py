import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def eliminar_todo_diario():
    # Limpieza total y reseteo de contadores automáticos
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM sqlite_sequence WHERE name='libro_diario'")
    ejecutar_query("DELETE FROM historial_cargas")