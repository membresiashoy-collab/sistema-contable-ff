import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def ejecutar_query(query, params=(), fetch=False):
    """Ejecuta SQL de forma segura."""
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def init_db():
    """Inicializa las tablas necesarias."""
    ejecutar_query("CREATE TABLE IF NOT EXISTS tabla_comprobantes (codigo INTEGER PRIMARY KEY, descripcion TEXT, es_reverso INTEGER)")
    ejecutar_query("CREATE TABLE IF NOT EXISTS libro_diario (id INTEGER PRIMARY KEY AUTOINCREMENT, id_asiento INTEGER, fecha TEXT, cuenta TEXT, debe REAL, haber REAL, glosa TEXT, origen TEXT)")

def cargar_tabla_referencia(df):
    """Carga los tipos de comprobante de ARCA."""
    init_db()
    # Detectamos columnas sin importar si tienen tildes
    df.columns = [c.strip().upper() for c in df.columns]
    col_cod = next(c for c in df.columns if "COD" in c)
    col_desc = next(c for c in df.columns if "DESC" in c)
    
    ejecutar_query("DELETE FROM tabla_comprobantes")
    for _, r in df.iterrows():
        cod = int(r[col_cod])
        desc = str(r[col_desc]).upper()
        # Lógica: si el nombre del comprobante tiene "CREDITO", es reverso
        reverso = 1 if "CREDITO" in desc or "CRÉDITO" in desc else 0
        ejecutar_query("INSERT INTO tabla_comprobantes VALUES (?,?,?)", (cod, desc, reverso))

def es_reverso(tipo_str):
    """Determina si el asiento debe invertirse."""
    t = str(tipo_str).upper()
    df = ejecutar_query("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || descripcion || '%'", (t,), fetch=True)
    if not df.empty:
        return df['es_reverso'].iloc[0] == 1
    return "CREDITO" in t

def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as m FROM libro_diario", fetch=True)
    if df.empty or pd.isnull(df['m'].iloc[0]): return 1
    return int(df['m'].iloc[0]) + 1