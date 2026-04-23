import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # 1. Tabla de Comprobantes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tipos_comprobantes (
                nombre TEXT PRIMARY KEY,
                es_reverso INTEGER
            )
        """)
        # 2. Libro Diario (Aseguramos que origen exista)
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
        # Parche de seguridad: si la columna origen no existe por una versión previa, la agregamos
        try:
            cursor.execute("ALTER TABLE libro_diario ADD COLUMN origen TEXT")
        except:
            pass # Ya existe
            
        cursor.execute("CREATE TABLE IF NOT EXISTS historial_archivos (nombre TEXT PRIMARY KEY, modulo TEXT)")
        
        # Carga de reglas contables ARCA
        cursor.execute("SELECT COUNT(*) FROM tipos_comprobantes")
        if cursor.fetchone()[0] == 0:
            reglas = [
                ('FACTURA', 0), ('NOTA DE DÉBITO', 0), ('RECIBO', 0),
                ('NOTA DE CRÉDITO', 1), ('NC-', 1)
            ]
            cursor.executemany("INSERT INTO tipos_comprobantes VALUES (?,?)", reglas)
        conn.commit()

def ejecutar_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try: return pd.read_sql_query(query, conn, params=params)
            except: return pd.DataFrame()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def es_comprobante_inverso(tipo_str):
    t = str(tipo_str).upper()
    df = ejecutar_query("SELECT es_reverso FROM tipos_comprobantes WHERE ? LIKE '%' || nombre || '%'", (t,), fetch=True)
    return not df.empty and df['es_reverso'].iloc[0] == 1

def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as maximo FROM libro_diario", fetch=True)
    val = df['maximo'].iloc[0]
    try:
        return (int(val) + 1) if pd.notnull(val) else 1
    except:
        return 1

def borrar_datos_modulo(mod):
    # Usamos try/except para que si la tabla está bloqueada o vacía no rompa la app
    try:
        ejecutar_query("DELETE FROM libro_diario WHERE origen = ?", (mod,))
        ejecutar_query("DELETE FROM historial_archivos WHERE modulo = ?", (mod,))
    except Exception as e:
        print(f"Error al limpiar: {e}")