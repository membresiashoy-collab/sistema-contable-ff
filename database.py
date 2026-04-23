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
        try: cursor.execute("ALTER TABLE libro_diario ADD COLUMN origen TEXT")
        except: pass
        conn.commit()

def cargar_tabla_referencia(df):
    """Procesa el CSV y marca las Notas de Crédito como Reverso (1)"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tabla_comprobantes")
        for _, r in df.iterrows():
            desc = str(r.get('Descripción', r.get('DESCRIPCION', ''))).upper()
            cod = int(r.get('Código', r.get('CODIGO', 0)))
            # Lógica contable: Si contiene CREDITO o CRÉDITO, es reverso
            reverso = 1 if "CREDITO" in desc or "CRÉDITO" in desc else 0
            cursor.execute("INSERT INTO tabla_comprobantes VALUES (?,?,?)", (cod, desc, reverso))
        conn.commit()

def es_comprobante_reverso(tipo_str):
    """Busca en la tabla si el tipo de comprobante debe invertir el asiento"""
    t = str(tipo_str).upper()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Busca coincidencia exacta en la descripción
        cursor.execute("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || descripcion || '%'", (t,))
        res = cursor.fetchone()
        if res: return res[0] == 1
    # Fallback si no encuentra el código: lógica por palabra clave
    return "CREDITO" in t or "CRÉDITO" in t

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch: return pd.read_sql_query(query, conn, params=params)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as m FROM libro_diario", fetch=True)
    val = df['m'].iloc[0]
    return (int(val) + 1) if pd.notnull(val) else 1