import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")


def conectar():
    return sqlite3.connect(DB_PATH)


def init_db():
    with conectar() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_asiento INTEGER,
            fecha TEXT,
            cuenta TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            glosa TEXT,
            origen TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT PRIMARY KEY,
            nombre TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo INTEGER PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS historial_cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modulo TEXT,
            nombre_archivo TEXT,
            registros_procesados INTEGER
        )
        """)

        conn.commit()


def ejecutar_query(query, params=(), fetch=False):
    with conectar() as conn:
        if fetch:
            try:
                return pd.read_sql_query(query, conn, params=params)
            except:
                return pd.DataFrame()

        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()


def proximo_asiento():
    df = ejecutar_query(
        "SELECT MAX(id_asiento) as maximo FROM libro_diario",
        fetch=True
    )

    if df.empty or pd.isna(df.iloc[0]["maximo"]):
        return 1

    return int(df.iloc[0]["maximo"]) + 1


def registrar_carga(modulo, archivo, cantidad):
    ejecutar_query("""
        INSERT INTO historial_cargas
        (modulo, nombre_archivo, registros_procesados)
        VALUES (?, ?, ?)
    """, (modulo, archivo, cantidad))


def registrar_archivo(nombre, tipo, cantidad):
    registrar_carga(tipo, nombre, cantidad)


def eliminar_todo_diario():
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM sqlite_sequence WHERE name='libro_diario'")