import sqlite3
import pandas as pd
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "contabilidad_ff.db")


def conectar():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ejecutar_query(sql, params=(), fetch=False):
    conn = conectar()

    if fetch:
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df

    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    conn.close()


def ejecutar_transaccion(operaciones):
    """
    Ejecuta una lista de operaciones en una sola transacción.
    Cada operación debe ser una tupla:
        (sql, params)

    Si algo falla, no se guarda nada de esa tanda.
    """
    conn = conectar()
    cur = conn.cursor()

    try:
        for sql, params in operaciones:
            cur.execute(sql, params)

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()


def columna_existe(conn, tabla, columna):
    columnas = pd.read_sql_query(
        f"PRAGMA table_info({tabla})",
        conn
    )["name"].tolist()

    return columna in columnas


def agregar_columna_si_no_existe(conn, tabla, columna, definicion):
    if not columna_existe(conn, tabla, columna):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def init_db():
    conn = conectar()
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
            archivo TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS historial_cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            nombre_archivo TEXT,
            registros INTEGER DEFAULT 0,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_comprobantes (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT,
            signo INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT,
            nombre TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS comprobantes_procesados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            fecha TEXT,
            codigo TEXT,
            numero TEXT,
            cliente_proveedor TEXT,
            total REAL,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS errores_carga (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            archivo TEXT,
            fila INTEGER,
            motivo TEXT,
            contenido TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ventas_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            anio INTEGER,
            mes INTEGER,
            codigo TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            cliente TEXT,
            cuit TEXT,
            neto REAL,
            iva REAL,
            total REAL,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuenta_corriente_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cliente TEXT,
            cuit TEXT,
            tipo TEXT,
            numero TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            saldo REAL DEFAULT 0,
            origen TEXT,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Compatibilidad con bases antiguas
    agregar_columna_si_no_existe(conn, "libro_diario", "archivo", "TEXT")
    agregar_columna_si_no_existe(conn, "historial_cargas", "registros", "INTEGER DEFAULT 0")

    # Índices para mejorar velocidad
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_libro_diario_archivo
        ON libro_diario(archivo)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_libro_diario_origen
        ON libro_diario(origen)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ventas_archivo
        ON ventas_comprobantes(archivo)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cta_cte_cliente
        ON cuenta_corriente_clientes(cliente)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_comprobantes_procesados
        ON comprobantes_procesados(modulo, codigo, numero, cliente_proveedor)
    """)

    conn.commit()
    conn.close()


# ======================================================
# FUNCIONES GENERALES
# ======================================================

def registrar_carga(modulo, archivo, registros):
    ejecutar_query("""
        INSERT INTO historial_cargas
        (modulo, nombre_archivo, registros)
        VALUES (?, ?, ?)
    """, (modulo, archivo, registros))


def proximo_asiento():
    df = ejecutar_query("""
        SELECT MAX(id_asiento) AS maximo
        FROM libro_diario
    """, fetch=True)

    if df.empty or pd.isna(df.iloc[0]["maximo"]):
        return 1

    return int(df.iloc[0]["maximo"]) + 1


def archivo_ya_cargado(nombre):
    df = ejecutar_query("""
        SELECT id
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
    ejecutar_query("DELETE FROM libro_diario WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM comprobantes_procesados WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM errores_carga WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM ventas_comprobantes WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM cuenta_corriente_clientes WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM historial_cargas WHERE nombre_archivo = ?", (nombre,))


def limpiar_historial():
    ejecutar_query("DELETE FROM historial_cargas")
    ejecutar_query("DELETE FROM comprobantes_procesados")
    ejecutar_query("DELETE FROM errores_carga")


def eliminar_todo_diario():
    ejecutar_query("DELETE FROM libro_diario")


def eliminar_diferencias_redondeo():
    ejecutar_query("""
        DELETE FROM libro_diario
        WHERE cuenta = 'DIFERENCIA POR REDONDEO'
    """)


def limpiar_errores():
    ejecutar_query("DELETE FROM errores_carga")


def limpiar_comprobantes_procesados():
    ejecutar_query("DELETE FROM comprobantes_procesados")


def limpiar_base_pruebas():
    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM historial_cargas")
    ejecutar_query("DELETE FROM comprobantes_procesados")
    ejecutar_query("DELETE FROM errores_carga")
    ejecutar_query("DELETE FROM ventas_comprobantes")
    ejecutar_query("DELETE FROM cuenta_corriente_clientes")


# ======================================================
# COMPROBANTES
# ======================================================

def comprobante_ya_procesado(modulo, codigo, numero, cliente_proveedor):
    df = ejecutar_query("""
        SELECT id
        FROM comprobantes_procesados
        WHERE modulo = ?
          AND codigo = ?
          AND numero = ?
          AND cliente_proveedor = ?
    """, (modulo, codigo, numero, cliente_proveedor), fetch=True)

    return not df.empty


def registrar_comprobante(modulo, fecha, codigo, numero, cliente_proveedor, total, archivo):
    ejecutar_query("""
        INSERT INTO comprobantes_procesados
        (modulo, fecha, codigo, numero, cliente_proveedor, total, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (modulo, fecha, codigo, numero, cliente_proveedor, total, archivo))


def tipo_comprobante_existe(codigo):
    df = ejecutar_query("""
        SELECT codigo
        FROM tipos_comprobantes
        WHERE codigo = ?
    """, (str(codigo),), fetch=True)

    return not df.empty


def obtener_tipo_comprobante_config(codigo):
    df = ejecutar_query("""
        SELECT descripcion, signo
        FROM tipos_comprobantes
        WHERE codigo = ?
    """, (str(codigo).strip(),), fetch=True)

    if df.empty:
        return None

    descripcion = str(df.iloc[0]["descripcion"])
    signo = int(df.iloc[0]["signo"])

    return {
        "descripcion": descripcion,
        "signo": signo
    }


# ======================================================
# ERRORES
# ======================================================

def registrar_error(modulo, archivo, fila, motivo, contenido):
    try:
        contenido_json = json.dumps(contenido, ensure_ascii=False, default=str)
    except Exception:
        contenido_json = str(contenido)

    ejecutar_query("""
        INSERT INTO errores_carga
        (modulo, archivo, fila, motivo, contenido)
        VALUES (?, ?, ?, ?, ?)
    """, (modulo, archivo, fila, motivo, contenido_json))


def obtener_errores():
    return ejecutar_query("""
        SELECT fecha, modulo, archivo, fila, motivo, contenido
        FROM errores_carga
        ORDER BY id DESC
    """, fetch=True)


def obtener_errores_por_archivo(archivo):
    return ejecutar_query("""
        SELECT fecha, modulo, archivo, fila, motivo, contenido
        FROM errores_carga
        WHERE archivo = ?
        ORDER BY id DESC
    """, (archivo,), fetch=True)


# ======================================================
# VENTAS
# ======================================================

def registrar_venta(fecha, anio, mes, codigo, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo):
    ejecutar_query("""
        INSERT INTO ventas_comprobantes
        (fecha, anio, mes, codigo, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, anio, mes, codigo, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo))


def registrar_cta_cte_cliente(fecha, cliente, cuit, tipo, numero, debe, haber, saldo, origen, archivo):
    ejecutar_query("""
        INSERT INTO cuenta_corriente_clientes
        (fecha, cliente, cuit, tipo, numero, debe, haber, saldo, origen, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, cliente, cuit, tipo, numero, debe, haber, saldo, origen, archivo))