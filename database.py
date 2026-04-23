import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tabla_comprobantes (
                codigo INTEGER PRIMARY KEY,
                descripcion TEXT,
                es_reverso INTEGER DEFAULT 0
            )
        """)
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
        conn.commit()

def cargar_tabla_referencia(df):
    # Forzamos nombres de columnas para que coincidan con tu CSV
    df.columns = [c.strip().capitalize() for c in df.columns] 
    # Buscamos 'Código' y 'Descripción'
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tabla_comprobantes")
        for _, r in df.iterrows():
            cod = int(r.get('Código', r.get('Codigo', 0)))
            desc = str(r.get('Descripción', r.get('Descripcion', ''))).upper()
            # Si es nota de crédito, marcamos como reverso (1)
            reverso = 1 if "CREDITO" in desc or "CRÉDITO" in desc else 0
            cursor.execute("INSERT INTO tabla_comprobantes VALUES (?,?,?)", (cod, desc, reverso))
        conn.commit()

def es_comprobante_reverso(tipo_str):
    t = str(tipo_str).upper()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Buscamos si la descripción del CSV de AFIP coincide con nuestra tabla
        cursor.execute("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || descripcion || '%'", (t,))
        res = cursor.fetchone()
        if res: return res[0] == 1
    return "CREDITO" in t or "CRÉDITO" in t

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch: return pd.read_sql_query(query, conn, params=params)
        conn.execute(query, params)
        conn.commit()

def proximo_asiento():
    res = ejecutar_query("SELECT MAX(id_asiento) as m FROM libro_diario", fetch=True)
    val = res['m'].iloc[0]
    return (int(val) + 1) if pd.notnull(val) else 1