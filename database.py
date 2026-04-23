import sqlite3
import pandas as pd
import os
from datetime import datetime

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

def registrar_archivo(nombre, tipo, cantidad):
    """Guarda constancia del archivo procesado."""
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    # Aseguramos que la tabla tenga las columnas correctas
    ejecutar_query("INSERT INTO historial_archivos (nombre_archivo, tipo, registros, fecha_proceso) VALUES (?,?,?,?)", 
                   (nombre, tipo, cantidad, ahora))

# Mantener init_db, es_reverso y proximo_asiento igual que en el mensaje anterior