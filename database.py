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
        # Parche de columna origen
        try: cursor.execute("ALTER TABLE libro_diario ADD COLUMN origen TEXT")
        except: pass
        conn.commit()

def cargar_tabla_referencia(df):
    """Carga masiva desde el CSV de comprobantes"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tabla_comprobantes")
        for _, r in df.iterrows():
            # Determinamos si es reverso por el nombre (Nota de Crédito)
            desc = str(r['Descripción']).upper()
            reverso = 1 if "CREDITO" in desc or "CRÉDITO" in desc else 0
            cursor.execute("INSERT INTO tabla_comprobantes VALUES (?,?,?)", (r['Código'], r['Descripción'], reverso))
        conn.commit()

def es_reverso(tipo_str):
    """Busca en la tabla cargada si el nombre coincide con un comprobante de reverso"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || descripcion || '%'", (str(tipo_str).upper(),))
        res = cursor.fetchone()
        return (res[0] == 1) if res else ("CREDITO" in str(tipo_str).upper())

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as maximo FROM libro_diario", fetch=True)
    val = df['maximo'].iloc[0]
    return (int(val) + 1) if pd.notnull(val) else 1

def borrar_datos_modulo(mod):
    ejecutar_query("DELETE FROM libro_diario WHERE origen = ?", (mod,))