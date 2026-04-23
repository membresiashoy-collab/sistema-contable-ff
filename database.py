import sqlite3
import pandas as pd
import os

# 1. Definimos la ruta absoluta para que la DB no se "pierda" entre módulos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")

def init_db():
    """Inicializa la base de datos y crea las tablas necesarias."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabla: Libro Diario (Soporta número de asiento individual)
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
    
    # Tabla: Plan de Cuentas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT PRIMARY KEY,
            nombre TEXT
        )
    """)
    
    # Tabla: Tipos de Comprobantes (Lógica de ARCA)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo INTEGER PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"Base de datos inicializada en: {DB_PATH}")

def ejecutar_query(query, params=(), fetch=False):
    """
    Ejecuta una consulta SQL. 
    Si fetch=True, devuelve un DataFrame de Pandas con los resultados.
    """
    with sqlite3.connect(DB_PATH) as conn:
        # Ajustamos para que sqlite3 sea compatible con DataFrames
        if fetch:
            try:
                return pd.read_sql_query(query, conn, params=params)
            except Exception as e:
                # Si la tabla está vacía o hay error, devolvemos un DF vacío
                return pd.DataFrame()
        
        # Para INSERT, UPDATE, DELETE
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

# Función útil para mantenimiento (Opcional)
def eliminar_base_de_datos():
    """Borra el archivo físico de la base de datos para empezar de cero."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Base de datos eliminada.")