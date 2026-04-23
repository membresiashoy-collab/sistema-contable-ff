import sqlite3
import pandas as pd
import os

# Ruta absoluta para evitar errores de "pantalla negra" o archivos perdidos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Tabla Libro Diario
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cuenta TEXT,
            debe REAL,
            haber REAL,
            glosa TEXT
        )
    """)
    
    # 2. Lógica de actualización para la individualidad de asientos
    try:
        cursor.execute("ALTER TABLE libro_diario ADD COLUMN id_asiento INTEGER")
    except sqlite3.OperationalError:
        pass # La columna ya existe, no hacemos nada

    # 3. Plan de Cuentas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT PRIMARY KEY, 
            nombre TEXT
        )
    """)

    # 4. Tabla de Comprobantes (Lógica ARCA)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo INTEGER PRIMARY KEY, 
            descripcion TEXT, 
            signo INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

def ejecutar_query(query, params=(), fetch=False):
    """Ejecuta comandos SQL y devuelve DataFrames si se solicita."""
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try:
                return pd.read_sql_query(query, conn, params=params)
            except:
                return pd.DataFrame()
        
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e