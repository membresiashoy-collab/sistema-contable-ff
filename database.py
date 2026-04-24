import sqlite3
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ===============================
    # LIBRO DIARIO
    # ===============================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libro_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_asiento INTEGER,
        fecha TEXT,
        cuenta TEXT,
        debe REAL,
        haber REAL,
        glosa TEXT,
        origen TEXT,
        archivo TEXT
    )
    """)

    # ===============================
    # HISTORIAL DE CARGAS
    # ===============================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historial_cargas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        modulo TEXT,
        nombre_archivo TEXT UNIQUE,
        registros INTEGER
    )
    """)

    # ===============================
    # TIPOS COMPROBANTES
    # ===============================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_comprobantes (
        codigo TEXT,
        descripcion TEXT,
        signo INTEGER
    )
    """)

    # ===============================
    # PLAN DE CUENTAS
    # ===============================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plan_cuentas (
        codigo TEXT,
        nombre TEXT
    )
    """)

    conn.commit()
    conn.close()


# ===================================
# QUERY GENERAL
# ===================================
def ejecutar_query(query, params=(), fetch=False):

    conn = sqlite3.connect(DB_PATH)

    if fetch:
        try:
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            return df
        except:
            conn.close()
            return pd.DataFrame()

    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()


# ===================================
# PROXIMO ASIENTO
# ===================================
def proximo_asiento():

    df = ejecutar_query("""
        SELECT MAX(id_asiento) AS maximo
        FROM libro_diario
    """, fetch=True)

    if df.empty:
        return 1

    if df.iloc[0]["maximo"] is None:
        return 1

    return int(df.iloc[0]["maximo"]) + 1


# ===================================
# REGISTRAR CARGA
# ===================================
def registrar_carga(modulo, archivo, registros):

    ejecutar_query("""
        INSERT INTO historial_cargas
        (modulo, nombre_archivo, registros)
        VALUES (?, ?, ?)
    """, (modulo, archivo, registros))


# ===================================
# VERIFICAR ARCHIVO DUPLICADO
# ===================================
def archivo_ya_cargado(nombre_archivo):

    df = ejecutar_query("""
        SELECT *
        FROM historial_cargas
        WHERE nombre_archivo = ?
    """, (nombre_archivo,), fetch=True)

    return not df.empty


# ===================================
# ELIMINAR CARGA + DATOS
# ===================================
def eliminar_carga(nombre_archivo):

    ejecutar_query("""
        DELETE FROM libro_diario
        WHERE archivo = ?
    """, (nombre_archivo,))

    ejecutar_query("""
        DELETE FROM historial_cargas
        WHERE nombre_archivo = ?
    """, (nombre_archivo,))


# ===================================
# HISTORIAL
# ===================================
def obtener_historial():

    return ejecutar_query("""
        SELECT fecha,
               modulo,
               nombre_archivo,
               registros
        FROM historial_cargas
        ORDER BY id DESC
    """, fetch=True)


# ===================================
# LIMPIAR TODO
# ===================================
def eliminar_todo_diario():
    ejecutar_query("DELETE FROM libro_diario")


def limpiar_historial():
    ejecutar_query("DELETE FROM historial_cargas")