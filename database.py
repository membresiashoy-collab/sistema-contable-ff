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

def init_db():
    # 1. Creamos las tablas base
    ejecutar_query("CREATE TABLE IF NOT EXISTS tabla_comprobantes (codigo INTEGER PRIMARY KEY, descripcion TEXT, es_reverso INTEGER)")
    ejecutar_query("CREATE TABLE IF NOT EXISTS libro_diario (id INTEGER PRIMARY KEY AUTOINCREMENT, id_asiento INTEGER, fecha TEXT, cuenta TEXT, debe REAL, haber REAL, glosa TEXT, origen TEXT)")
    ejecutar_query("CREATE TABLE IF NOT EXISTS historial_archivos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre_archivo TEXT, tipo TEXT, registros INTEGER)")

    # 2. PARCHE DE EMERGENCIA: Agregamos la columna fecha_proceso si no existe
    try:
        ejecutar_query("ALTER TABLE historial_archivos ADD COLUMN fecha_proceso TEXT")
    except:
        # Si ya existe, SQLite dará error y simplemente lo ignoramos
        pass

def registrar_archivo(nombre, tipo, cantidad):
    from datetime import datetime
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    ejecutar_query("INSERT INTO historial_archivos (fecha_proceso, nombre_archivo, tipo, registros) VALUES (?,?,?,?)", (ahora, nombre, tipo, cantidad))

def es_reverso(tipo_str):
    t = str(tipo_str).upper()
    df = ejecutar_query("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || descripcion || '%'", (t,), fetch=True)
    if not df.empty: return df['es_reverso'].iloc[0] == 1
    return "CREDITO" in t

def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as m FROM libro_diario", fetch=True)
    if df.empty or pd.isnull(df['m'].iloc[0]): return 1
    return int(df['m'].iloc[0]) + 1