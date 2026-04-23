import sqlite3
import pandas as pd
import os

# Ruta absoluta para garantizar que todos los módulos vean el mismo archivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    """Inicializa la base de datos y asegura que todas las columnas existan."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Tabla Libro Diario (Con id_asiento para individualidad)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_asiento INTEGER,
            fecha TEXT,
            cuenta TEXT,
            debe REAL,
            haber REAL,
            glosa TEXT
        )
    """)
    
    # 2. Parche de seguridad: Asegurar que id_asiento existe si la DB es vieja
    try:
        cursor.execute("ALTER TABLE libro_diario ADD COLUMN id_asiento INTEGER")
    except sqlite3.OperationalError:
        pass # La columna ya existe

    # 3. Tabla Plan de Cuentas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT PRIMARY KEY,
            nombre TEXT
        )
    """)

    # 4. Tabla de Comprobantes (Lógica de signos ARCA)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo INTEGER PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
    """)

    # 5. NUEVA: Tabla de Mapeo Inteligente (Aprendizaje del sistema)
    # Aquí se guardará cuando tú decidas que 'VENTAS' debe ser otra cuenta específica
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mapeo_cuentas (
            concepto TEXT PRIMARY KEY,
            cuenta_asignada TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def ejecutar_query(query, params=(), fetch=False):
    """Ejecuta sentencias SQL y maneja la devolución de datos con Pandas."""
    with sqlite3.connect(DB_PATH) as conn:
        if fetch:
            try:
                # El uso de read_sql_query permite devolver DataFrames listos para Streamlit
                return pd.read_sql_query(query, conn, params=params)
            except Exception:
                return pd.DataFrame()
        
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback() # Si hay error, deshace los cambios para no corromper la contabilidad
            raise e