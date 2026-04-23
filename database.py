import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Tabla de Comprobantes (Referencia ARCA)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tabla_comprobantes (
                codigo INTEGER PRIMARY KEY,
                nombre TEXT,
                es_reverso INTEGER DEFAULT 0
            )
        """)
        # Libro Diario con columna origen
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
        cursor.execute("CREATE TABLE IF NOT EXISTS archivos_cargados (nombre TEXT PRIMARY KEY, modulo TEXT)")
        
        # Insertar comprobantes básicos si la tabla está vacía
        cursor.execute("SELECT COUNT(*) FROM tabla_comprobantes")
        if cursor.fetchone()[0] == 0:
            comprobantes = [
                (1, 'Factura A', 0), (6, 'Factura B', 0), (11, 'Factura C', 0),
                (3, 'Nota de Crédito A', 1), (8, 'Nota de Crédito B', 1), (13, 'Nota de Crédito C', 1),
                (2, 'Nota de Débito A', 0), (7, 'Nota de Débito B', 0), (12, 'Nota de Débito C', 0)
            ]
            cursor.executemany("INSERT INTO tabla_comprobantes VALUES (?,?,?)", comprobantes)
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def limpiar_modulo(modulo):
    """Limpia datos específicos de un módulo (Ventas o Compras)"""
    ejecutar_query("DELETE FROM libro_diario WHERE origen = ?", (modulo,))
    ejecutar_query("DELETE FROM archivos_cargados WHERE modulo = ?", (modulo,))

def es_reverso(tipo_str):
    """Consulta la tabla de comprobantes para decidir la lógica del asiento"""
    df = ejecutar_query("SELECT es_reverso FROM tabla_comprobantes WHERE ? LIKE '%' || nombre || '%'", (tipo_str,), fetch=True)
    if not df.empty:
        return df['es_reverso'].iloc[0] == 1
    return "CREDITO" in tipo_str.upper() or "NC-" in tipo_str.upper()

def obtener_proximo_asiento():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id_asiento) FROM libro_diario")
        res = cursor.fetchone()[0]
        return (res + 1) if res else 1