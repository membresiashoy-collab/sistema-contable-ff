import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    """Crea las tablas si no existen. Se asegura de que los nombres sean exactos."""
    try:
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
    except Exception as e:
        print(f"Error inicializando DB: {e}")

def cargar_tabla_referencia(df):
    """Procesa el CSV TABLACOMPROBANTES.csv con sus nombres exactos."""
    init_db() # Nos aseguramos de que la tabla existe
    # Normalizamos: Código y Descripción
    df.columns = [c.strip().replace('ó', 'o').replace('í', 'i').upper() for c in df.columns]
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tabla_comprobantes")
        for _, r in df.iterrows():
            cod = int(r.get('CODIGO', 0))
            desc = str(r.get('DESCRIPCION', '')).upper()
            # Si el nombre tiene 'CREDITO', el sistema sabe que es un asiento de reverso
            reverso = 1 if "CREDITO" in desc else 0
            cursor.execute("INSERT INTO tabla_comprobantes VALUES (?,?,?)", (cod, desc, reverso))
        conn.commit()

def es_comprobante_reverso(tipo_str):
    """Busca si el comprobante anula/reversa una operacion."""
    t = str(tipo_str).upper()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || descripcion || '%'", (t,))
            res = cursor.fetchone()
            if res: return res[0] == 1
    except:
        pass
    return "CREDITO" in t

def ejecutar_query(query, params=(), fetch=False):
    """Ejecuta SQL con manejo de errores para evitar que la app se ponga negra."""
    init_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if fetch:
                return pd.read_sql_query(query, conn, params=params)
            conn.execute(query, params)
            conn.commit()
    except Exception as e:
        # Si la tabla no existe aún, devolvemos un DataFrame vacío en lugar de error
        if fetch: return pd.DataFrame()
        raise e

def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as m FROM libro_diario", fetch=True)
    if df.empty or pd.isnull(df['m'].iloc[0]): return 1
    return int(df['m'].iloc[0]) + 1