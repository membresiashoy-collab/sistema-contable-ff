import os
import json
import shutil
import sqlite3
from datetime import datetime

import pandas as pd

from config import DB_PATH, DB_ENGINE, asegurar_directorios


# ======================================================
# CONFIGURACIÓN DE SEGURIDAD DE BASE
# ======================================================

def ruta_base_datos():
    """
    Devuelve la ruta absoluta de la base de datos.
    Mantiene compatibilidad con config.py.
    """
    return DB_PATH


def asegurar_carpeta_db():
    """
    Asegura que exista la carpeta donde vive la base SQLite.
    """
    asegurar_directorios()

    carpeta = os.path.dirname(DB_PATH)

    if carpeta:
        os.makedirs(carpeta, exist_ok=True)


def backup_base_datos(motivo="backup"):
    """
    Crea una copia de seguridad del archivo SQLite si existe.

    No borra ni modifica la base original.
    """
    asegurar_carpeta_db()

    if not os.path.exists(DB_PATH):
        return None

    carpeta_backup = os.path.join(os.path.dirname(DB_PATH), "backups")
    os.makedirs(carpeta_backup, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_base = os.path.basename(DB_PATH)
    destino = os.path.join(
        carpeta_backup,
        f"{nombre_base}_{motivo}_{timestamp}.bak"
    )

    shutil.copy2(DB_PATH, destino)

    return destino


def operacion_destructiva_permitida(nombre_operacion, confirmar=False):
    """
    Evita que funciones peligrosas borren datos por accidente.

    Para borrar masivamente, la función debe llamarse explícitamente con:
    confirmar=True

    Esto protege contra ejecuciones automáticas desde Streamlit, main.py
    o inicializadores.
    """
    if confirmar is True:
        backup_base_datos(nombre_operacion)
        return True

    print(
        f"[PROTECCIÓN DB] Operación bloqueada: {nombre_operacion}. "
        "Para ejecutarla debe pasarse confirmar=True."
    )

    return False


# ======================================================
# CONEXIÓN BASE DE DATOS
# ======================================================

def conectar():
    """
    Conexión centralizada a la base de datos.

    Hoy usa SQLite.
    Más adelante puede adaptarse a PostgreSQL sin romper módulos.
    """

    asegurar_carpeta_db()

    if DB_ENGINE != "sqlite":
        raise NotImplementedError(
            "Por ahora el sistema usa SQLite. "
            "La arquitectura ya queda preparada para PostgreSQL más adelante."
        )

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass

    return conn


def ejecutar_query(sql, params=(), fetch=False):
    """
    Ejecuta consultas SQL.
    Si fetch=True devuelve un DataFrame.
    """

    conn = conectar()

    try:
        if fetch:
            df = pd.read_sql_query(sql, conn, params=params)
            return df

        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur

    finally:
        conn.close()


def ejecutar_transaccion(operaciones):
    """
    Ejecuta varias operaciones SQL como una sola transacción.
    Si una falla, se revierte todo.
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


# ======================================================
# UTILIDADES DE ESTRUCTURA
# ======================================================

def tabla_existe(conn, tabla):
    df = pd.read_sql_query("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, conn, params=(tabla,))

    return not df.empty


def columnas_tabla(conn, tabla):
    try:
        return pd.read_sql_query(
            f"PRAGMA table_info({tabla})",
            conn
        )["name"].tolist()
    except Exception:
        return []


def columna_existe(conn, tabla, columna):
    columnas = columnas_tabla(conn, tabla)
    return columna in columnas


def agregar_columna_si_no_existe(conn, tabla, columna, definicion):
    if not columna_existe(conn, tabla, columna):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def reparar_tablas_seguridad(conn, cur):
    """
    Repara tablas de seguridad sin borrar datos.

    Versión segura:
    - No hace DROP TABLE.
    - Solo agrega columnas faltantes.
    """

    if tabla_existe(conn, "roles"):
        agregar_columna_si_no_existe(conn, "roles", "descripcion", "TEXT")

    if tabla_existe(conn, "permisos"):
        agregar_columna_si_no_existe(conn, "permisos", "descripcion", "TEXT")
        agregar_columna_si_no_existe(conn, "permisos", "modulo", "TEXT")

    if tabla_existe(conn, "rol_permisos"):
        agregar_columna_si_no_existe(conn, "rol_permisos", "rol", "TEXT")
        agregar_columna_si_no_existe(conn, "rol_permisos", "permiso", "TEXT")

    if tabla_existe(conn, "usuarios"):
        agregar_columna_si_no_existe(conn, "usuarios", "nombre", "TEXT")
        agregar_columna_si_no_existe(conn, "usuarios", "email", "TEXT")
        agregar_columna_si_no_existe(conn, "usuarios", "password_hash", "TEXT")
        agregar_columna_si_no_existe(conn, "usuarios", "rol", "TEXT DEFAULT 'LECTURA'")
        agregar_columna_si_no_existe(conn, "usuarios", "activo", "INTEGER DEFAULT 1")
        agregar_columna_si_no_existe(conn, "usuarios", "debe_cambiar_password", "INTEGER DEFAULT 0")
        agregar_columna_si_no_existe(conn, "usuarios", "fecha_creacion", "TIMESTAMP")
        agregar_columna_si_no_existe(conn, "usuarios", "ultimo_login", "TIMESTAMP")

    if tabla_existe(conn, "empresas"):
        agregar_columna_si_no_existe(conn, "empresas", "cuit", "TEXT")
        agregar_columna_si_no_existe(conn, "empresas", "razon_social", "TEXT")
        agregar_columna_si_no_existe(conn, "empresas", "domicilio", "TEXT")
        agregar_columna_si_no_existe(conn, "empresas", "actividad", "TEXT")
        agregar_columna_si_no_existe(conn, "empresas", "activo", "INTEGER DEFAULT 1")
        agregar_columna_si_no_existe(conn, "empresas", "fecha_creacion", "TIMESTAMP")

    if tabla_existe(conn, "usuario_empresas"):
        agregar_columna_si_no_existe(conn, "usuario_empresas", "usuario_id", "INTEGER")
        agregar_columna_si_no_existe(conn, "usuario_empresas", "empresa_id", "INTEGER")
        agregar_columna_si_no_existe(conn, "usuario_empresas", "activo", "INTEGER DEFAULT 1")


# ======================================================
# INICIALIZACIÓN GENERAL
# ======================================================

def init_db():
    """
    Inicializa la estructura de la base.

    IMPORTANTE:
    Esta función NO borra datos.
    Solo crea tablas faltantes y agrega columnas faltantes.
    """

    conn = conectar()
    cur = conn.cursor()

    reparar_tablas_seguridad(conn, cur)

    # ======================================================
    # SEGURIDAD / MULTIEMPRESA
    # ======================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cuit TEXT,
            razon_social TEXT,
            domicilio TEXT,
            actividad TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            nombre TEXT,
            email TEXT,
            password_hash TEXT NOT NULL,
            rol TEXT DEFAULT 'LECTURA',
            activo INTEGER DEFAULT 1,
            debe_cambiar_password INTEGER DEFAULT 0,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ultimo_login TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            rol TEXT PRIMARY KEY,
            descripcion TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS permisos (
            permiso TEXT PRIMARY KEY,
            descripcion TEXT,
            modulo TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rol_permisos (
            rol TEXT,
            permiso TEXT,
            PRIMARY KEY (rol, permiso)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuario_empresas (
            usuario_id INTEGER,
            empresa_id INTEGER,
            activo INTEGER DEFAULT 1,
            PRIMARY KEY (usuario_id, empresa_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_cambios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_id INTEGER,
            empresa_id INTEGER,
            modulo TEXT,
            accion TEXT,
            entidad TEXT,
            entidad_id TEXT,
            valor_anterior TEXT,
            valor_nuevo TEXT,
            motivo TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS periodos_contables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            anio INTEGER,
            mes INTEGER,
            estado TEXT DEFAULT 'ABIERTO',
            fecha_cierre TIMESTAMP,
            usuario_cierre INTEGER,
            UNIQUE(empresa_id, anio, mes)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS proveedores_configuracion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            cuit TEXT,
            proveedor TEXT,
            categoria_habitual TEXT,
            cuenta_principal_codigo TEXT,
            cuenta_principal_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            tipo_categoria TEXT,
            observacion TEXT,
            activo INTEGER DEFAULT 1,
            fecha_ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(empresa_id, cuit)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes_configuracion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            cuit TEXT,
            cliente TEXT,
            categoria_habitual TEXT,
            cuenta_cliente_codigo TEXT,
            cuenta_cliente_nombre TEXT,
            observacion TEXT,
            activo INTEGER DEFAULT 1,
            fecha_ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(empresa_id, cuit)
        )
    """)

    # ======================================================
    # TABLAS CONTABLES BASE
    # ======================================================

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
        CREATE TABLE IF NOT EXISTS plan_cuentas_detallado (
            cuenta TEXT PRIMARY KEY,
            detalle TEXT,
            imputable TEXT,
            ajustable TEXT,
            tipo TEXT,
            madre TEXT,
            nivel INTEGER,
            orden INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categorias_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            tipo_categoria TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS conceptos_fiscales_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            tratamiento TEXT,
            activo INTEGER DEFAULT 1
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
        CREATE TABLE IF NOT EXISTS advertencias_carga (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            archivo TEXT,
            fila INTEGER,
            motivo TEXT,
            contenido TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS compras_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            anio INTEGER,
            mes INTEGER,
            codigo TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            proveedor TEXT,
            cuit TEXT,
            neto REAL,
            iva REAL,
            total REAL,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuenta_corriente_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proveedor TEXT,
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS iva_config_periodo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            anio INTEGER,
            mes INTEGER,
            modo_credito_fiscal TEXT DEFAULT 'SEGUN_PORTAL_IVA',
            ventas_gravadas REAL DEFAULT 0,
            ventas_exentas REAL DEFAULT 0,
            ventas_no_gravadas REAL DEFAULT 0,
            exportaciones REAL DEFAULT 0,
            coeficiente_credito_fiscal REAL DEFAULT 1,
            usar_credito_fiscal TEXT DEFAULT 'SISTEMA',
            observacion TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ======================================================
    # COLUMNAS COMPATIBLES PARA MULTIEMPRESA
    # ======================================================

    tablas_empresa = [
        "libro_diario",
        "historial_cargas",
        "comprobantes_procesados",
        "errores_carga",
        "advertencias_carga",
        "ventas_comprobantes",
        "cuenta_corriente_clientes",
        "compras_comprobantes",
        "cuenta_corriente_proveedores",
        "plan_cuentas",
        "plan_cuentas_detallado",
        "categorias_compra",
        "conceptos_fiscales_compra"
    ]

    for tabla in tablas_empresa:
        agregar_columna_si_no_existe(conn, tabla, "empresa_id", "INTEGER DEFAULT 1")

    columnas_diario = {
        "origen_tabla": "TEXT",
        "origen_id": "INTEGER",
        "comprobante_clave": "TEXT",
        "estado": "TEXT DEFAULT 'CONTABILIZADO'",
        "usuario_creacion": "INTEGER",
        "fecha_creacion": "TIMESTAMP"
    }

    for columna, definicion in columnas_diario.items():
        agregar_columna_si_no_existe(conn, "libro_diario", columna, definicion)

    columnas_categorias = {
        "tratamiento_iva": "TEXT DEFAULT 'SEGUN_CONFIG_PERIODO'",
        "porcentaje_iva_computable": "REAL DEFAULT NULL"
    }

    for columna, definicion in columnas_categorias.items():
        agregar_columna_si_no_existe(conn, "categorias_compra", columna, definicion)

    columnas_compras = {
        "categoria_compra": "TEXT",
        "cuenta_principal_codigo": "TEXT",
        "cuenta_principal_nombre": "TEXT",
        "cuenta_proveedor_codigo": "TEXT",
        "cuenta_proveedor_nombre": "TEXT",
        "importe_no_gravado": "REAL DEFAULT 0",
        "importe_exento": "REAL DEFAULT 0",
        "iva_total": "REAL DEFAULT 0",
        "credito_fiscal_computable": "REAL DEFAULT 0",
        "metodo_credito_fiscal": "TEXT",
        "coeficiente_iva_aplicado": "REAL DEFAULT 1",
        "iva_computable_sistema": "REAL DEFAULT 0",
        "iva_no_computable_sistema": "REAL DEFAULT 0",
        "iva_computable_csv": "REAL DEFAULT 0",
        "diferencia_iva_csv_sistema": "REAL DEFAULT 0",
        "iva_no_computable": "REAL DEFAULT 0",
        "percepcion_iva": "REAL DEFAULT 0",
        "percepcion_iibb": "REAL DEFAULT 0",
        "percepcion_otros_imp_nac": "REAL DEFAULT 0",
        "impuestos_municipales": "REAL DEFAULT 0",
        "impuestos_internos": "REAL DEFAULT 0",
        "otros_tributos": "REAL DEFAULT 0",
        "moneda": "TEXT",
        "tipo_cambio": "REAL DEFAULT 1",
        "neto_iva_0": "REAL DEFAULT 0",
        "neto_iva_25": "REAL DEFAULT 0",
        "iva_25": "REAL DEFAULT 0",
        "neto_iva_5": "REAL DEFAULT 0",
        "iva_5": "REAL DEFAULT 0",
        "neto_iva_105": "REAL DEFAULT 0",
        "iva_105": "REAL DEFAULT 0",
        "neto_iva_21": "REAL DEFAULT 0",
        "iva_21": "REAL DEFAULT 0",
        "neto_iva_27": "REAL DEFAULT 0",
        "iva_27": "REAL DEFAULT 0",
        "origen_carga": "TEXT"
    }

    for columna, definicion in columnas_compras.items():
        agregar_columna_si_no_existe(conn, "compras_comprobantes", columna, definicion)

    # ======================================================
    # ÍNDICES
    # ======================================================

    cur.execute("CREATE INDEX IF NOT EXISTS idx_libro_diario_empresa ON libro_diario(empresa_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_libro_diario_archivo ON libro_diario(archivo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_libro_diario_origen ON libro_diario(origen)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_libro_diario_comprobante ON libro_diario(comprobante_clave)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_historial_archivo ON historial_cargas(nombre_archivo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ventas_empresa ON ventas_comprobantes(empresa_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_compras_empresa ON compras_comprobantes(empresa_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_compras_cuit ON compras_comprobantes(cuit)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_proveedores_config ON proveedores_configuracion(empresa_id, cuit)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_clientes_config ON clientes_configuracion(empresa_id, cuit)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_cta_cte_cliente ON cuenta_corriente_clientes(cliente)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cta_cte_proveedor ON cuenta_corriente_proveedores(proveedor)")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_comprobantes_procesados
        ON comprobantes_procesados(modulo, codigo, numero, cliente_proveedor)
    """)

    conn.commit()
    conn.close()


# ======================================================
# FUNCIONES GENERALES COMPATIBLES CON MÓDULOS ACTUALES
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
    """
    Elimina una carga específica por nombre de archivo.

    Esta función sí es destructiva, pero es puntual y explícita.
    Crea backup antes de borrar.
    """
    backup_base_datos("antes_eliminar_carga")

    ejecutar_query("DELETE FROM libro_diario WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM comprobantes_procesados WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM errores_carga WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM advertencias_carga WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM ventas_comprobantes WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM cuenta_corriente_clientes WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM compras_comprobantes WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM cuenta_corriente_proveedores WHERE archivo = ?", (nombre,))
    ejecutar_query("DELETE FROM historial_cargas WHERE nombre_archivo = ?", (nombre,))

    return True


def limpiar_historial(confirmar=False):
    """
    Limpieza masiva protegida.

    No se ejecuta salvo que se llame con confirmar=True.
    """
    if not operacion_destructiva_permitida("limpiar_historial", confirmar):
        return False

    ejecutar_query("DELETE FROM historial_cargas")
    ejecutar_query("DELETE FROM comprobantes_procesados")
    ejecutar_query("DELETE FROM errores_carga")
    ejecutar_query("DELETE FROM advertencias_carga")

    return True


def eliminar_todo_diario(confirmar=False):
    """
    Limpieza masiva protegida.
    """
    if not operacion_destructiva_permitida("eliminar_todo_diario", confirmar):
        return False

    ejecutar_query("DELETE FROM libro_diario")
    return True


def eliminar_diferencias_redondeo():
    """
    Limpieza puntual y no masiva.
    """
    backup_base_datos("antes_eliminar_diferencias_redondeo")

    ejecutar_query("""
        DELETE FROM libro_diario
        WHERE cuenta = 'DIFERENCIA POR REDONDEO'
    """)

    return True


def limpiar_errores():
    """
    Limpieza de errores solamente.
    No borra comprobantes ni libro diario.
    """
    ejecutar_query("DELETE FROM errores_carga")
    return True


def limpiar_comprobantes_procesados(confirmar=False):
    """
    Limpieza masiva protegida porque permite reprocesar duplicados.
    """
    if not operacion_destructiva_permitida("limpiar_comprobantes_procesados", confirmar):
        return False

    ejecutar_query("DELETE FROM comprobantes_procesados")
    return True


def limpiar_base_pruebas(confirmar=False):
    """
    Limpieza masiva protegida.

    Esta función NO debe llamarse automáticamente desde main.py
    ni desde inicializadores.
    """
    if not operacion_destructiva_permitida("limpiar_base_pruebas", confirmar):
        return False

    ejecutar_query("DELETE FROM libro_diario")
    ejecutar_query("DELETE FROM historial_cargas")
    ejecutar_query("DELETE FROM comprobantes_procesados")
    ejecutar_query("DELETE FROM errores_carga")
    ejecutar_query("DELETE FROM advertencias_carga")
    ejecutar_query("DELETE FROM ventas_comprobantes")
    ejecutar_query("DELETE FROM cuenta_corriente_clientes")
    ejecutar_query("DELETE FROM compras_comprobantes")
    ejecutar_query("DELETE FROM cuenta_corriente_proveedores")

    return True


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