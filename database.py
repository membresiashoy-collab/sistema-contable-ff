import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")


def ejecutar_query(sql, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)

    if fetch:
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df

    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    conn.close()


def init_db():

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # TABLA LIBRO DIARIO
    cur.execute("""
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

    # TABLA HISTORIAL
    cur.execute("""
        CREATE TABLE IF NOT EXISTS historial_cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            nombre_archivo TEXT,
            registros INTEGER,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # TIPOS COMPROBANTES
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo TEXT,
            descripcion TEXT,
            signo INTEGER
        )
    """)

    # PLAN CUENTAS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT,
            nombre TEXT
        )
    """)

    conn.commit()

    # ===============================
    # AGREGAR COLUMNAS FALTANTES
    # ===============================

    columnas = pd.read_sql_query(
        "PRAGMA table_info(libro_diario)",
        conn
    )["name"].tolist()

    if "archivo" not in columnas:
        cur.execute("""
            ALTER TABLE libro_diario
            ADD COLUMN archivo TEXT
        """)

    conn.commit()
    conn.close()


def registrar_carga(modulo, archivo, registros):
    ejecutar_query("""
        INSERT INTO historial_cargas
        (modulo,nombre_archivo,registros)
        VALUES (?,?,?)
    """, (modulo, archivo, registros))


def proximo_asiento():
    df = ejecutar_query("""
        SELECT MAX(id_asiento) maximo
        FROM libro_diario
    """, fetch=True)

    if df.empty or pd.isna(df.iloc[0]["maximo"]):
        return 1

    return int(df.iloc[0]["maximo"]) + 1


def archivo_ya_cargado(nombre):
    df = ejecutar_query("""
        SELECT *
        FROM historial_cargas
        WHERE nombre_archivo = ?
    """, (nombre,), fetch=True)

    return not df.empty


def obtener_historial():
    return ejecutar_query("""
        SELECT fecha, modulo, nombre_archivo, registros
        FROM historial_cargas
        ORDER BY id DESC
    """, fetch=True)


def eliminar_carga(nombre):
    ejecutar_query("""
        DELETE FROM libro_diario
        WHERE archivo = ?
    """, (nombre,))

    ejecutar_query("""
        DELETE FROM historial_cargas
        WHERE nombre_archivo = ?
    """, (nombre,))


def limpiar_historial():
    ejecutar_query("DELETE FROM historial_cargas")


def eliminar_todo_diario():
    ejecutar_query("DELETE FROM libro_diario")