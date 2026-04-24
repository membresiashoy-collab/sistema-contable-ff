import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "contabilidad_ff.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT,
            nombre TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo TEXT,
            descripcion TEXT,
            signo INTEGER
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial_cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            nombre_archivo TEXT,
            registros INTEGER
        )
        """)


def ejecutar_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if fetch:
        try:
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            return df
        except:
            conn.close()
            return pd.DataFrame()

    cursor.execute(query, params)
    conn.commit()
    conn.close()


def registrar_carga(modulo, archivo, registros):
    ejecutar_query("""
    INSERT INTO historial_cargas (modulo, nombre_archivo, registros)
    VALUES (?, ?, ?)
    """, (modulo, archivo, registros))


def eliminar_todo_diario():
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM sqlite_sequence WHERE name='libro_diario'")


def limpiar_historial():
    ejecutar_query("DELETE FROM historial_cargas")


def proximo_asiento():
    df = ejecutar_query("SELECT MAX(id_asiento) as max FROM libro_diario", fetch=True)
    if df.empty or df.iloc[0]["max"] is None:
        return 1
    return int(df.iloc[0]["max"]) + 1