import hashlib
import re
import unicodedata
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd

from database import conectar, ejecutar_query


# ======================================================
# TIPOS Y CUENTAS BASE
# ======================================================

TIPOS_MOVIMIENTO_BANCO = {
    "COBRO_POSIBLE": "Cobro posible",
    "PAGO_POSIBLE": "Pago posible",
    "GASTO_BANCARIO_GRAVADO": "Gasto bancario gravado",
    "IVA_CREDITO_FISCAL_BANCARIO": "IVA crédito fiscal bancario",
    "PERCEPCION_IVA_BANCARIA": "Percepción IVA bancaria",
    "IMPUESTO_DEBITOS_CREDITOS": "Impuesto débitos/créditos bancarios",
    "RECAUDACION_IIBB": "Recaudación / percepción IIBB",
    "PAGO_IMPUESTOS": "ARCA / AFIP / impuestos a clasificar",
    "TRANSFERENCIA_ENTRE_CUENTAS": "Transferencia entre cuentas propias",
    "EFECTIVO_CAJA": "Movimiento de efectivo / caja",
    "INVERSION_RESCATE": "Inversión / rescate financiero",
    "MOVIMIENTO_SOCIOS": "Socios / aportes / cuenta particular",
    "INTERES_BANCARIO_POSIBLE_105": "Interés o comisión financiera posible 10,5%",
    "OTRO_GASTO_A_REVISAR": "Otro gasto a revisar",
    "A_REVISAR": "A revisar",
}


COLUMNAS_CANONICAS = [
    "fecha",
    "referencia",
    "causal",
    "concepto",
    "importe",
    "debito",
    "credito",
    "saldo",
]


CUENTAS_BANCO_RECOMENDADAS = [
    {
        "codigo": "1.3.09",
        "nombre": "IMPUESTO DEBITOS Y CREDITOS A COMPUTAR",
        "detalle": "IMPUESTO DEBITOS Y CREDITOS A COMPUTAR",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "A",
        "madre": "1.3",
        "nivel": 3,
        "orden": 165,
    },
    {
        "codigo": "1.6",
        "nombre": "OTROS CREDITOS",
        "detalle": "OTROS CREDITOS",
        "imputable": "N",
        "ajustable": "N",
        "tipo": "A",
        "madre": "1",
        "nivel": 2,
        "orden": 270,
    },
    {
        "codigo": "1.6.01",
        "nombre": "ANTICIPOS A PROVEEDORES",
        "detalle": "ANTICIPOS A PROVEEDORES",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "A",
        "madre": "1.6",
        "nivel": 3,
        "orden": 280,
    },
    {
        "codigo": "1.6.02",
        "nombre": "CUENTA PARTICULAR SOCIOS / DIRECTORES",
        "detalle": "CUENTA PARTICULAR SOCIOS / DIRECTORES",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "A",
        "madre": "1.6",
        "nivel": 3,
        "orden": 290,
    },
    {
        "codigo": "2.1.02",
        "nombre": "ANTICIPOS DE CLIENTES",
        "detalle": "ANTICIPOS DE CLIENTES",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "P",
        "madre": "2.1",
        "nivel": 3,
        "orden": 325,
    },
    {
        "codigo": "2.4",
        "nombre": "DEUDAS FINANCIERAS Y SOCIOS",
        "detalle": "DEUDAS FINANCIERAS Y SOCIOS",
        "imputable": "N",
        "ajustable": "N",
        "tipo": "P",
        "madre": "2",
        "nivel": 2,
        "orden": 460,
    },
    {
        "codigo": "2.4.01",
        "nombre": "PRESTAMOS DE SOCIOS / DIRECTORES",
        "detalle": "PRESTAMOS DE SOCIOS / DIRECTORES",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "P",
        "madre": "2.4",
        "nivel": 3,
        "orden": 470,
    },
    {
        "codigo": "3.1.03",
        "nombre": "APORTES IRREVOCABLES",
        "detalle": "APORTES IRREVOCABLES",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "PN",
        "madre": "3.1",
        "nivel": 3,
        "orden": 540,
    },
    {
        "codigo": "6.1.27",
        "nombre": "IMPUESTO DEBITOS Y CREDITOS BANCARIOS",
        "detalle": "IMPUESTO DEBITOS Y CREDITOS BANCARIOS",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "R",
        "madre": "6.1",
        "nivel": 3,
        "orden": 1080,
    },
    {
        "codigo": "6.1.28",
        "nombre": "INTERESES BANCARIOS",
        "detalle": "INTERESES BANCARIOS",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "R",
        "madre": "6.1",
        "nivel": 3,
        "orden": 1090,
    },
    {
        "codigo": "6.1.29",
        "nombre": "DIFERENCIAS MENORES DE CONCILIACION",
        "detalle": "DIFERENCIAS MENORES DE CONCILIACION",
        "imputable": "S",
        "ajustable": "N",
        "tipo": "R",
        "madre": "6.1",
        "nivel": 3,
        "orden": 1100,
    },
]


CONFIG_CONTABLE_DEFAULT = {
    "cuenta_banco": ("1.1.02", "BANCO CUENTA CORRIENTE"),
    "cuenta_caja": ("1.1.01", "CAJA"),
    "cuenta_deudores": ("1.2.01", "DEUDORES POR VENTAS"),
    "cuenta_proveedores": ("2.1.01", "PROVEEDORES"),
    "cuenta_gastos_bancarios": ("6.1.06", "GASTOS BANCARIOS Y COMISIONES"),
    "cuenta_iva_credito": ("1.3.01", "IVA CREDITO FISCAL"),
    "cuenta_percepciones_iva": ("1.3.02", "PERCEPCIONES IVA"),
    "cuenta_percepciones_iibb": ("1.3.03", "PERCEPCIONES IIBB"),
    "cuenta_impuesto_debcred_gasto": ("6.1.27", "IMPUESTO DEBITOS Y CREDITOS BANCARIOS"),
    "cuenta_impuesto_debcred_computable": ("1.3.09", "IMPUESTO DEBITOS Y CREDITOS A COMPUTAR"),
    "cuenta_anticipo_cliente": ("2.1.02", "ANTICIPOS DE CLIENTES"),
    "cuenta_anticipo_proveedor": ("1.6.01", "ANTICIPOS A PROVEEDORES"),
    "cuenta_socios_activo": ("1.6.02", "CUENTA PARTICULAR SOCIOS / DIRECTORES"),
    "cuenta_prestamos_socios": ("2.4.01", "PRESTAMOS DE SOCIOS / DIRECTORES"),
    "cuenta_aportes_irrevocables": ("3.1.03", "APORTES IRREVOCABLES"),
    "cuenta_intereses_bancarios": ("6.1.28", "INTERESES BANCARIOS"),
    "cuenta_diferencias_conciliacion": ("6.1.29", "DIFERENCIAS MENORES DE CONCILIACION"),
    "cuenta_otros_gastos_revisar": ("6.1.26", "OTROS GASTOS A REVISAR"),
}


# ======================================================
# INICIALIZACIÓN
# ======================================================

def inicializar_bancos():
    crear_tablas_bancarias()
    asegurar_cuentas_bancarias_recomendadas()
    crear_configuracion_contable_default()
    crear_permisos_bancarios()


def _columnas_tabla(conn, tabla):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)
        return df["name"].tolist()
    except Exception:
        return []


def _agregar_columna_si_no_existe(conn, tabla, columna, definicion):
    columnas = _columnas_tabla(conn, tabla)

    if columna not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def crear_tablas_bancarias():
    conn = conectar()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                banco TEXT,
                nombre_cuenta TEXT,
                cbu_alias TEXT,
                cuenta_contable_codigo TEXT,
                cuenta_contable_nombre TEXT,
                activo INTEGER DEFAULT 1,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(empresa_id, banco, nombre_cuenta)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_importaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                banco TEXT,
                nombre_cuenta TEXT,
                nombre_archivo TEXT,
                formato_archivo TEXT,
                registros_detectados INTEGER DEFAULT 0,
                procesados INTEGER DEFAULT 0,
                duplicados INTEGER DEFAULT 0,
                errores INTEGER DEFAULT 0,
                saldo_inicial_extracto REAL DEFAULT 0,
                total_debitos REAL DEFAULT 0,
                total_creditos REAL DEFAULT 0,
                saldo_final_extracto REAL DEFAULT 0,
                saldo_final_calculado REAL DEFAULT 0,
                diferencia_saldo REAL DEFAULT 0,
                observacion TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        for columna, definicion in {
            "saldo_inicial_extracto": "REAL DEFAULT 0",
            "total_debitos": "REAL DEFAULT 0",
            "total_creditos": "REAL DEFAULT 0",
            "saldo_final_extracto": "REAL DEFAULT 0",
            "saldo_final_calculado": "REAL DEFAULT 0",
            "diferencia_saldo": "REAL DEFAULT 0",
        }.items():
            _agregar_columna_si_no_existe(conn, "bancos_importaciones", columna, definicion)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                importacion_id INTEGER,
                banco TEXT,
                nombre_cuenta TEXT,
                fecha TEXT,
                anio INTEGER,
                mes INTEGER,
                referencia TEXT,
                causal TEXT,
                concepto TEXT,
                importe REAL DEFAULT 0,
                debito REAL DEFAULT 0,
                credito REAL DEFAULT 0,
                saldo REAL DEFAULT 0,
                importe_conciliado REAL DEFAULT 0,
                importe_pendiente REAL DEFAULT 0,
                porcentaje_conciliado REAL DEFAULT 0,
                tipo_movimiento_sugerido TEXT,
                subtipo_sugerido TEXT,
                confianza_sugerencia TEXT,
                motivo_sugerencia TEXT,
                cuenta_debe_codigo TEXT,
                cuenta_debe_nombre TEXT,
                cuenta_haber_codigo TEXT,
                cuenta_haber_nombre TEXT,
                tratamiento_fiscal TEXT,
                alicuota_iva_sugerida REAL,
                estado_conciliacion TEXT DEFAULT 'PENDIENTE',
                estado_contable TEXT DEFAULT 'NO_CONTABILIZADO',
                clave_movimiento TEXT,
                archivo TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(empresa_id, clave_movimiento)
            )
        """)

        columnas_mov = {
            "importe_conciliado": "REAL DEFAULT 0",
            "importe_pendiente": "REAL DEFAULT 0",
            "porcentaje_conciliado": "REAL DEFAULT 0",
            "subtipo_sugerido": "TEXT",
            "cuenta_debe_codigo": "TEXT",
            "cuenta_debe_nombre": "TEXT",
            "cuenta_haber_codigo": "TEXT",
            "cuenta_haber_nombre": "TEXT",
            "tratamiento_fiscal": "TEXT",
            "alicuota_iva_sugerida": "REAL",
        }

        for columna, definicion in columnas_mov.items():
            _agregar_columna_si_no_existe(conn, "bancos_movimientos", columna, definicion)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_reglas_clasificacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                nombre_regla TEXT,
                patron TEXT,
                causal TEXT,
                tipo_movimiento TEXT,
                subtipo TEXT,
                cuenta_debe_codigo TEXT,
                cuenta_debe_nombre TEXT,
                cuenta_haber_codigo TEXT,
                cuenta_haber_nombre TEXT,
                tratamiento_fiscal TEXT,
                alicuota_iva REAL,
                automatizar_asiento INTEGER DEFAULT 0,
                requiere_confirmacion INTEGER DEFAULT 1,
                confianza TEXT DEFAULT 'Media',
                veces_detectada INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_grupos_fiscales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                importacion_id INTEGER,
                fecha TEXT,
                referencia TEXT,
                causal TEXT,
                banco TEXT,
                nombre_cuenta TEXT,
                base_gasto_bancario REAL DEFAULT 0,
                iva_credito_21 REAL DEFAULT 0,
                iva_credito_105 REAL DEFAULT 0,
                iva_sin_base REAL DEFAULT 0,
                percepcion_iva REAL DEFAULT 0,
                percepcion_iibb REAL DEFAULT 0,
                impuesto_debitos_creditos REAL DEFAULT 0,
                total_banco REAL DEFAULT 0,
                alicuota_detectada TEXT,
                confianza TEXT,
                estado_revision TEXT DEFAULT 'PENDIENTE',
                motivo TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_conciliaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                movimiento_banco_id INTEGER,
                fecha TEXT,
                tipo_conciliacion TEXT,
                estado TEXT DEFAULT 'BORRADOR',
                importe_total REAL DEFAULT 0,
                importe_imputado REAL DEFAULT 0,
                importe_pendiente REAL DEFAULT 0,
                porcentaje_conciliado REAL DEFAULT 0,
                observacion TEXT,
                usuario_id INTEGER,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_confirmacion TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_conciliaciones_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conciliacion_id INTEGER,
                empresa_id INTEGER DEFAULT 1,
                movimiento_banco_id INTEGER,
                tipo_imputacion TEXT,
                entidad_tabla TEXT,
                entidad_id INTEGER,
                tercero_nombre TEXT,
                tercero_cuit TEXT,
                comprobante TEXT,
                cuenta_codigo TEXT,
                cuenta_nombre TEXT,
                importe_imputado REAL DEFAULT 0,
                saldo_anterior REAL DEFAULT 0,
                saldo_posterior REAL DEFAULT 0,
                observacion TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_asientos_propuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                movimiento_banco_id INTEGER,
                conciliacion_id INTEGER,
                fecha TEXT,
                cuenta_codigo TEXT,
                cuenta_nombre TEXT,
                debe REAL DEFAULT 0,
                haber REAL DEFAULT 0,
                glosa TEXT,
                estado TEXT DEFAULT 'PROPUESTO',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bancos_configuracion_contable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                clave TEXT,
                cuenta_codigo TEXT,
                cuenta_nombre TEXT,
                descripcion TEXT,
                activo INTEGER DEFAULT 1,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(empresa_id, clave)
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_mov_empresa ON bancos_movimientos(empresa_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_mov_fecha ON bancos_movimientos(fecha)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_mov_tipo ON bancos_movimientos(tipo_movimiento_sugerido)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_mov_estado ON bancos_movimientos(estado_conciliacion)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_mov_clave ON bancos_movimientos(empresa_id, clave_movimiento)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_conc_mov ON bancos_conciliaciones(movimiento_banco_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bancos_grupos_importacion ON bancos_grupos_fiscales(importacion_id)")

        conn.commit()

    finally:
        conn.close()


def crear_permisos_bancarios():
    permisos = [
        ("bancos.ver", "Ver módulo Banco / Caja", "Banco / Caja"),
        ("bancos.cargar", "Cargar extractos bancarios", "Banco / Caja"),
        ("bancos.reglas", "Administrar reglas bancarias", "Banco / Caja"),
        ("bancos.conciliar", "Conciliar movimientos bancarios", "Banco / Caja"),
    ]

    for permiso, descripcion, modulo in permisos:
        ejecutar_query("""
            INSERT OR IGNORE INTO permisos (permiso, descripcion, modulo)
            VALUES (?, ?, ?)
        """, (permiso, descripcion, modulo))

    for rol in ["ADMINISTRADOR", "CONTADOR", "AUXILIAR"]:
        for permiso, _, _ in permisos:
            ejecutar_query("""
                INSERT OR IGNORE INTO rol_permisos (rol, permiso)
                VALUES (?, ?)
            """, (rol, permiso))


def asegurar_cuentas_bancarias_recomendadas(empresa_id=1):
    for cuenta in CUENTAS_BANCO_RECOMENDADAS:
        df = ejecutar_query("""
            SELECT cuenta
            FROM plan_cuentas_detallado
            WHERE empresa_id = ?
              AND cuenta = ?
        """, (empresa_id, cuenta["codigo"]), fetch=True)

        if df.empty:
            ejecutar_query("""
                INSERT INTO plan_cuentas_detallado
                (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden, empresa_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cuenta["codigo"],
                cuenta["detalle"],
                cuenta["imputable"],
                cuenta["ajustable"],
                cuenta["tipo"],
                cuenta["madre"],
                cuenta["nivel"],
                cuenta["orden"],
                empresa_id,
            ))

        df_simple = ejecutar_query("""
            SELECT codigo
            FROM plan_cuentas
            WHERE empresa_id = ?
              AND codigo = ?
        """, (empresa_id, cuenta["codigo"]), fetch=True)

        if df_simple.empty:
            ejecutar_query("""
                INSERT INTO plan_cuentas
                (codigo, nombre, empresa_id)
                VALUES (?, ?, ?)
            """, (
                cuenta["codigo"],
                cuenta["nombre"],
                empresa_id,
            ))


def crear_configuracion_contable_default(empresa_id=1):
    for clave, (codigo, nombre) in CONFIG_CONTABLE_DEFAULT.items():
        ejecutar_query("""
            INSERT OR IGNORE INTO bancos_configuracion_contable
            (empresa_id, clave, cuenta_codigo, cuenta_nombre, descripcion)
            VALUES (?, ?, ?, ?, ?)
        """, (
            empresa_id,
            clave,
            codigo,
            nombre,
            f"Cuenta default Banco/Caja: {clave}"
        ))


def obtener_configuracion_contable_bancos(empresa_id=1):
    crear_configuracion_contable_default(empresa_id)

    return ejecutar_query("""
        SELECT clave, cuenta_codigo, cuenta_nombre, descripcion, activo
        FROM bancos_configuracion_contable
        WHERE empresa_id = ?
        ORDER BY clave
    """, (empresa_id,), fetch=True)


# ======================================================
# NORMALIZACIÓN
# ======================================================

def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def normalizar_texto(texto):
    if texto is None or pd.isna(texto):
        return ""

    texto = str(texto).strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto


def normalizar_texto_busqueda(texto):
    texto = quitar_acentos(normalizar_texto(texto)).upper()
    texto = texto.replace(".", " ")
    texto = texto.replace("_", " ")
    texto = texto.replace("-", " ")
    texto = texto.replace("/", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def normalizar_importe_argentino(valor):
    if valor is None or pd.isna(valor):
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()

    if texto == "":
        return 0.0

    negativo = False

    if "(" in texto and ")" in texto:
        negativo = True

    if "-" in texto:
        negativo = True

    texto = texto.replace("$", "")
    texto = texto.replace("AR$", "")
    texto = texto.replace("ARS", "")
    texto = texto.replace("\xa0", "")
    texto = texto.replace(" ", "")
    texto = texto.replace("(", "")
    texto = texto.replace(")", "")
    texto = texto.replace("-", "")

    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    texto = re.sub(r"[^0-9.]", "", texto)

    if texto == "":
        return 0.0

    try:
        numero = float(texto)
    except Exception:
        return 0.0

    if negativo:
        numero = numero * -1

    return numero


def normalizar_fecha_bancaria(valor):
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto == "":
        return ""

    fecha = pd.to_datetime(texto, dayfirst=True, errors="coerce")

    if pd.isna(fecha):
        fecha = pd.to_datetime(texto, errors="coerce")

    if pd.isna(fecha):
        return ""

    return fecha.date().isoformat()


def obtener_anio_mes(fecha_iso):
    fecha = pd.to_datetime(fecha_iso, errors="coerce")

    if pd.isna(fecha):
        return None, None

    return int(fecha.year), int(fecha.month)


def normalizar_nombre_columna(columna):
    texto = normalizar_texto_busqueda(columna)
    texto = texto.replace("NRO", "NUMERO")
    texto = texto.replace("Nº", "NUMERO")
    texto = texto.replace("N°", "NUMERO")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def mapear_columna(columna):
    col = normalizar_nombre_columna(columna)

    sinonimos = {
        "fecha": [
            "FECHA", "FECHA MOVIMIENTO", "FECHA MOV", "FEC MOV",
            "FECHA VALOR", "DATE", "POSTING DATE", "VALUE DATE"
        ],
        "referencia": [
            "REFERENCIA", "NUMERO DE REFERENCIA", "NRO DE REFERENCIA",
            "NUMERO REFERENCIA", "NRO REFERENCIA", "REF", "NRO REF",
            "COMPROBANTE", "OPERACION", "NUMERO OPERACION", "ID OPERACION",
            "TRANSACTION ID", "REFERENCE"
        ],
        "causal": [
            "CAUSAL", "CODIGO", "CODIGO MOVIMIENTO", "COD MOV", "CODE",
            "TRANSACTION CODE", "CONCEPTO CODIGO"
        ],
        "concepto": [
            "CONCEPTO", "DESCRIPCION", "DETALLE", "MOVIMIENTO",
            "LEYENDA", "DESCRIPTION", "MEMO", "NARRATIVE", "CONCEPT"
        ],
        "importe": [
            "IMPORTE", "MONTO", "IMPORTE MOVIMIENTO", "VALOR",
            "AMOUNT", "NETO", "TOTAL"
        ],
        "debito": [
            "DEBITO", "DEBITOS", "EGRESO", "EGRESOS", "DEBE",
            "DEBIT", "WITHDRAWAL", "OUTFLOW", "CARGO"
        ],
        "credito": [
            "CREDITO", "CREDITOS", "INGRESO", "INGRESOS", "HABER",
            "CREDIT", "DEPOSIT", "INFLOW", "ABONO"
        ],
        "saldo": [
            "SALDO", "SALDO CUENTA", "SALDO FINAL", "SALDO ACTUAL",
            "BALANCE", "RUNNING BALANCE"
        ],
    }

    for canonica, valores in sinonimos.items():
        if col in valores:
            return canonica

    for canonica, valores in sinonimos.items():
        for valor in valores:
            if valor in col:
                return canonica

    return ""


# ======================================================
# LECTURA FLEXIBLE
# ======================================================

def leer_archivo_crudo(nombre_archivo, contenido):
    extension = Path(nombre_archivo).suffix.lower()
    candidatos = []

    if extension in [".xls", ".xlsx"]:
        candidatos.extend(_leer_excel_generico(contenido))
    elif extension in [".csv", ".txt"]:
        candidatos.extend(_leer_texto_generico(contenido))
    else:
        candidatos.extend(_leer_excel_generico(contenido))
        candidatos.extend(_leer_texto_generico(contenido))

    return [df for df in candidatos if df is not None and not df.empty]


def _leer_excel_generico(contenido):
    candidatos = []

    try:
        hojas = pd.read_excel(
            BytesIO(contenido),
            sheet_name=None,
            header=None,
            dtype=str
        )

        for nombre_hoja, df in hojas.items():
            if not df.empty:
                df = df.copy()
                df.attrs["origen_lectura"] = f"excel:{nombre_hoja}"
                candidatos.append(df)

    except Exception:
        pass

    try:
        tablas = pd.read_html(BytesIO(contenido))

        for i, df in enumerate(tablas):
            if not df.empty:
                df = df.astype(str)
                df.attrs["origen_lectura"] = f"html:{i + 1}"
                candidatos.append(df)

    except Exception:
        pass

    return candidatos


def _leer_texto_generico(contenido):
    candidatos = []

    texto = None

    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            texto = contenido.decode(encoding)
            break
        except Exception:
            pass

    if texto is None:
        return candidatos

    for sep in ["\t", ";", ",", "|"]:
        try:
            df = pd.read_csv(
                StringIO(texto),
                sep=sep,
                dtype=str,
                engine="python"
            )

            if not df.empty:
                df.attrs["origen_lectura"] = f"texto_sep_{repr(sep)}"
                candidatos.append(df)

        except Exception:
            pass

    try:
        df = pd.read_csv(
            StringIO(texto),
            sep=None,
            dtype=str,
            engine="python"
        )

        if not df.empty:
            df.attrs["origen_lectura"] = "texto_auto"
            candidatos.append(df)

    except Exception:
        pass

    return candidatos


def detectar_y_aplicar_encabezado(df):
    df = df.copy()
    df = df.dropna(how="all")

    if df.empty:
        return df

    columnas_mapeadas = [mapear_columna(c) for c in df.columns]

    if "fecha" in columnas_mapeadas and "concepto" in columnas_mapeadas:
        return df

    max_filas = min(len(df), 50)

    for idx in range(max_filas):
        valores = df.iloc[idx].tolist()
        valores_mapeados = [mapear_columna(v) for v in valores]

        if "fecha" in valores_mapeados and "concepto" in valores_mapeados:
            nuevo = df.iloc[idx + 1:].copy()
            nuevo.columns = valores
            nuevo = nuevo.dropna(how="all")
            nuevo.attrs["fila_encabezado_detectada"] = idx
            return nuevo

    return df


def detectar_mapeo_columnas(df):
    mapeo = {}

    for columna in df.columns:
        canonica = mapear_columna(columna)

        if canonica and canonica not in mapeo:
            mapeo[canonica] = columna

    return mapeo


def score_mapeo(mapeo):
    score = 0

    if "fecha" in mapeo:
        score += 3

    if "concepto" in mapeo:
        score += 3

    if "importe" in mapeo:
        score += 3

    if "debito" in mapeo and "credito" in mapeo:
        score += 3

    if "referencia" in mapeo:
        score += 1

    if "causal" in mapeo:
        score += 1

    if "saldo" in mapeo:
        score += 1

    return score


def elegir_mejor_candidato(candidatos):
    mejores = []

    for df_raw in candidatos:
        df = detectar_y_aplicar_encabezado(df_raw)
        mapeo = detectar_mapeo_columnas(df)
        score = score_mapeo(mapeo)

        mejores.append({
            "df": df,
            "mapeo": mapeo,
            "score": score,
            "columnas": [str(c) for c in df.columns],
            "origen": df_raw.attrs.get("origen_lectura", "")
        })

    mejores = sorted(mejores, key=lambda x: x["score"], reverse=True)

    if not mejores:
        return None

    return mejores[0]


def analizar_archivo_extracto(nombre_archivo, contenido, mapeo_manual=None):
    candidatos = leer_archivo_crudo(nombre_archivo, contenido)

    if not candidatos:
        return {
            "ok": False,
            "requiere_mapeo": False,
            "mensaje": "No se pudo leer el archivo. Probá exportarlo como CSV, TXT o Excel simple.",
            "df_movimientos": pd.DataFrame(),
            "df_preview": pd.DataFrame(),
            "columnas_detectadas": [],
            "mapeo_detectado": {},
            "control_saldo": {}
        }

    mejor = elegir_mejor_candidato(candidatos)

    if mejor is None:
        return {
            "ok": False,
            "requiere_mapeo": False,
            "mensaje": "No se pudo seleccionar una tabla válida dentro del archivo.",
            "df_movimientos": pd.DataFrame(),
            "df_preview": pd.DataFrame(),
            "columnas_detectadas": [],
            "mapeo_detectado": {},
            "control_saldo": {}
        }

    df_base = mejor["df"]
    mapeo_detectado = mejor["mapeo"]
    columnas = mejor["columnas"]

    if mapeo_manual:
        mapeo = {
            canonica: columna
            for canonica, columna in mapeo_manual.items()
            if columna and columna != "No usar"
        }
    else:
        mapeo = mapeo_detectado

    tiene_importe = "importe" in mapeo
    tiene_debito_credito = "debito" in mapeo or "credito" in mapeo

    if not ("fecha" in mapeo and "concepto" in mapeo and (tiene_importe or tiene_debito_credito)):
        return {
            "ok": False,
            "requiere_mapeo": True,
            "mensaje": (
                "No se pudo mapear automáticamente el extracto. "
                "Indicá manualmente fecha, concepto e importe, o fecha, concepto, débito/crédito."
            ),
            "df_movimientos": pd.DataFrame(),
            "df_preview": df_base.head(40).copy(),
            "columnas_detectadas": columnas,
            "mapeo_detectado": mapeo_detectado,
            "control_saldo": {}
        }

    df_movimientos = normalizar_dataframe_con_mapeo(df_base, mapeo)

    if df_movimientos.empty:
        return {
            "ok": False,
            "requiere_mapeo": True,
            "mensaje": (
                "El mapeo fue detectado, pero no se pudieron construir movimientos válidos. "
                "Revisá que fecha, concepto e importe estén bien asignados."
            ),
            "df_movimientos": pd.DataFrame(),
            "df_preview": df_base.head(40).copy(),
            "columnas_detectadas": columnas,
            "mapeo_detectado": mapeo_detectado,
            "control_saldo": {}
        }

    control_saldo = calcular_control_saldo_extracto(df_movimientos)

    return {
        "ok": True,
        "requiere_mapeo": False,
        "mensaje": "Extracto interpretado correctamente.",
        "df_movimientos": df_movimientos,
        "df_preview": df_base.head(40).copy(),
        "columnas_detectadas": columnas,
        "mapeo_detectado": mapeo,
        "control_saldo": control_saldo
    }


def leer_archivo_extracto(nombre_archivo, contenido):
    analisis = analizar_archivo_extracto(nombre_archivo, contenido)

    if not analisis["ok"]:
        raise ValueError(analisis["mensaje"])

    return analisis["df_movimientos"]


def normalizar_dataframe_con_mapeo(df, mapeo):
    filas = []

    for _, row in df.iterrows():
        fecha = normalizar_fecha_bancaria(row.get(mapeo.get("fecha"), ""))

        if fecha == "":
            continue

        concepto = normalizar_texto(row.get(mapeo.get("concepto"), ""))

        if concepto == "":
            continue

        referencia = normalizar_texto(row.get(mapeo.get("referencia"), ""))
        causal = normalizar_texto(row.get(mapeo.get("causal"), ""))

        if "importe" in mapeo:
            importe = normalizar_importe_argentino(row.get(mapeo["importe"]))
        else:
            debito_raw = normalizar_importe_argentino(row.get(mapeo.get("debito"), 0))
            credito_raw = normalizar_importe_argentino(row.get(mapeo.get("credito"), 0))

            debito_abs = abs(debito_raw)
            credito_abs = abs(credito_raw)

            importe = credito_abs - debito_abs

        saldo = normalizar_importe_argentino(row.get(mapeo.get("saldo"), 0))

        debito = abs(importe) if importe < 0 else 0.0
        credito = importe if importe > 0 else 0.0

        anio, mes = obtener_anio_mes(fecha)

        clasificacion = clasificar_movimiento(concepto, causal, importe)
        cuentas = sugerir_cuentas_por_movimiento(clasificacion["tipo"], importe)

        filas.append({
            "fecha": fecha,
            "anio": anio,
            "mes": mes,
            "referencia": referencia,
            "causal": causal,
            "concepto": concepto,
            "importe": importe,
            "debito": debito,
            "credito": credito,
            "saldo": saldo,
            "importe_conciliado": 0.0,
            "importe_pendiente": abs(importe),
            "porcentaje_conciliado": 0.0,
            "tipo_movimiento_sugerido": clasificacion["tipo"],
            "subtipo_sugerido": clasificacion.get("subtipo", ""),
            "confianza_sugerencia": clasificacion["confianza"],
            "motivo_sugerencia": clasificacion["motivo"],
            "cuenta_debe_codigo": cuentas["debe_codigo"],
            "cuenta_debe_nombre": cuentas["debe_nombre"],
            "cuenta_haber_codigo": cuentas["haber_codigo"],
            "cuenta_haber_nombre": cuentas["haber_nombre"],
            "tratamiento_fiscal": clasificacion.get("tratamiento_fiscal", ""),
            "alicuota_iva_sugerida": clasificacion.get("alicuota_iva_sugerida"),
        })

    df_norm = pd.DataFrame(filas)

    if df_norm.empty:
        return df_norm

    return df_norm.sort_values(
        by=["fecha", "referencia", "causal", "importe"],
        ascending=True
    ).reset_index(drop=True)


# ======================================================
# CLASIFICACIÓN Y CUENTAS
# ======================================================

def clasificar_movimiento(concepto, causal="", importe=0):
    texto = normalizar_texto_busqueda(f"{causal} {concepto}")
    importe = float(importe or 0)

    if "DBCR 25413" in texto or "25413" in texto:
        return {
            "tipo": "IMPUESTO_DEBITOS_CREDITOS",
            "subtipo": "LEY_25413",
            "confianza": "Alta",
            "motivo": "Detectado por patrón de impuesto a los débitos y créditos bancarios.",
            "tratamiento_fiscal": "CONFIGURABLE_GASTO_O_PAGO_A_CUENTA",
            "alicuota_iva_sugerida": None,
        }

    if "SIRCREB" in texto or "REC DE IIBB" in texto or "INGRESOS BR" in texto or "DPR JUY" in texto or "DGR" in texto or "RENTAS" in texto:
        return {
            "tipo": "RECAUDACION_IIBB",
            "subtipo": "PERCEPCION_IIBB_BANCARIA",
            "confianza": "Alta",
            "motivo": "Detectado como recaudación, retención o percepción provincial de IIBB.",
            "tratamiento_fiscal": "CREDITO_FISCAL_IIBB",
            "alicuota_iva_sugerida": None,
        }

    if "PERCEPCION IVA" in texto or "IVA PERCEPCION" in texto or "PERC IVA" in texto:
        return {
            "tipo": "PERCEPCION_IVA_BANCARIA",
            "subtipo": "PERCEPCION_IVA",
            "confianza": "Alta",
            "motivo": "Detectado como percepción de IVA separada del IVA crédito fiscal básico.",
            "tratamiento_fiscal": "PERCEPCION_IVA_COMPUTABLE",
            "alicuota_iva_sugerida": None,
        }

    if "DEBITO FISCAL IVA" in texto or "IVA BASICO" in texto or "IVA BASICA" in texto or "IVA COMISION" in texto:
        return {
            "tipo": "IVA_CREDITO_FISCAL_BANCARIO",
            "subtipo": "IVA_CREDITO_FISCAL_BANCO",
            "confianza": "Alta",
            "motivo": "El banco lo informa como IVA débito fiscal propio; para el usuario se interpreta como IVA crédito fiscal bancario si corresponde.",
            "tratamiento_fiscal": "IVA_CREDITO_FISCAL",
            "alicuota_iva_sugerida": 21.0,
        }

    if (
        "INTERES" in texto
        or "INT " in texto
        or "PRESTAMO" in texto
        or "FINANCIACION" in texto
        or "FINANCIERA" in texto
    ):
        return {
            "tipo": "INTERES_BANCARIO_POSIBLE_105",
            "subtipo": "INTERES_O_COMISION_FINANCIERA",
            "confianza": "Media",
            "motivo": "Detectado como interés o comisión financiera. Puede requerir revisión de alícuota IVA 10,5% o 21%.",
            "tratamiento_fiscal": "POSIBLE_IVA_105_REVISAR",
            "alicuota_iva_sugerida": 10.5,
        }

    if (
        "COMISION" in texto
        or "COM " in texto
        or "COMIS " in texto
        or "CHEQUERA" in texto
        or "CHEQUE RECH" in texto
        or "RECHAZO" in texto
        or "MANTENIMIENTO" in texto
        or "PAQUETE" in texto
        or "SERVICIO CUENTA" in texto
        or "MACROL" in texto
        or "ECHEQ" in texto
        or "E CHEQ" in texto
        or "CARGO BANCARIO" in texto
        or "GASTO BANCARIO" in texto
    ):
        return {
            "tipo": "GASTO_BANCARIO_GRAVADO",
            "subtipo": "GASTO_BANCARIO_21",
            "confianza": "Alta",
            "motivo": "Detectado como gasto o comisión bancaria recurrente, generalmente gravado al 21% salvo revisión.",
            "tratamiento_fiscal": "GASTO_BANCARIO_GRAVADO",
            "alicuota_iva_sugerida": 21.0,
        }

    if "IMP AFIP" in texto or "IMP. AFIP" in texto or "AFIP" in texto or "ARCA" in texto or "AUTONOMOS" in texto or "SUSS" in texto:
        return {
            "tipo": "PAGO_IMPUESTOS",
            "subtipo": "PAGO_FISCAL_PREVISIONAL",
            "confianza": "Media",
            "motivo": "Detectado como pago fiscal o previsional.",
            "tratamiento_fiscal": "PAGO_IMPUESTOS",
            "alicuota_iva_sugerida": None,
        }

    if "TRANSF AUT SDO MISMO TIT" in texto or "MISMO TIT" in texto or "MISMO TITULAR" in texto:
        return {
            "tipo": "TRANSFERENCIA_ENTRE_CUENTAS",
            "subtipo": "CUENTAS_PROPIAS",
            "confianza": "Alta",
            "motivo": "Detectado como transferencia entre cuentas del mismo titular.",
            "tratamiento_fiscal": "SIN_IMPACTO_RESULTADO",
            "alicuota_iva_sugerida": None,
        }

    if "RETIRO" in texto or "DEPOSITO EN EFECTIVO" in texto or "CAJ AH" in texto or "CAJA DE AHORROS" in texto or "EFECTIVO" in texto:
        return {
            "tipo": "EFECTIVO_CAJA",
            "subtipo": "CAJA_EFECTIVO",
            "confianza": "Media",
            "motivo": "Detectado como movimiento de efectivo o caja.",
            "tratamiento_fiscal": "REQUIERE_IMPUTACION",
            "alicuota_iva_sugerida": None,
        }

    if "LIQ SUSC" in texto or "SOL RESC" in texto or "RESC" in texto or "SUSC" in texto:
        return {
            "tipo": "INVERSION_RESCATE",
            "subtipo": "INVERSION_RESCATE",
            "confianza": "Media",
            "motivo": "Detectado como suscripción, liquidación o rescate financiero.",
            "tratamiento_fiscal": "REQUIERE_IMPUTACION",
            "alicuota_iva_sugerida": None,
        }

    if "APORTE" in texto or "SOCIO" in texto or "DIRECTOR" in texto or "CUENTA PARTICULAR" in texto or "CAPITAL" in texto:
        return {
            "tipo": "MOVIMIENTO_SOCIOS",
            "subtipo": "SOCIOS_APORTES_CUENTA_PARTICULAR",
            "confianza": "Media",
            "motivo": "Detectado como posible movimiento de socios, capital, préstamo o cuenta particular.",
            "tratamiento_fiscal": "PATRIMONIAL_REQUIERE_REVISION",
            "alicuota_iva_sugerida": None,
        }

    if ("TRANSF" in texto or "TPUSH" in texto or "CREDIN" in texto or "TEF" in texto) and importe > 0:
        return {
            "tipo": "COBRO_POSIBLE",
            "subtipo": "COBRO_CLIENTE_O_TERCERO",
            "confianza": "Media",
            "motivo": "Ingreso bancario compatible con cobro de cliente. El CUIT bancario no bloquea pagos de terceros.",
            "tratamiento_fiscal": "CONCILIAR_CLIENTE_ANTICIPO_OTRO",
            "alicuota_iva_sugerida": None,
        }

    if ("TRANSF" in texto or "PAGO" in texto or "TRF" in texto) and importe < 0:
        return {
            "tipo": "PAGO_POSIBLE",
            "subtipo": "PAGO_PROVEEDOR_O_TERCERO",
            "confianza": "Media",
            "motivo": "Egreso bancario compatible con pago a proveedor, gasto o anticipo.",
            "tratamiento_fiscal": "CONCILIAR_PROVEEDOR_ANTICIPO_GASTO",
            "alicuota_iva_sugerida": None,
        }

    if importe > 0:
        return {
            "tipo": "COBRO_POSIBLE",
            "subtipo": "INGRESO_SIN_PATRON",
            "confianza": "Baja",
            "motivo": "Ingreso bancario sin patrón específico.",
            "tratamiento_fiscal": "REQUIERE_CONCILIACION",
            "alicuota_iva_sugerida": None,
        }

    if importe < 0:
        return {
            "tipo": "OTRO_GASTO_A_REVISAR",
            "subtipo": "EGRESO_SIN_PATRON",
            "confianza": "Baja",
            "motivo": "Egreso bancario sin patrón específico. Revisar antes de contabilizar.",
            "tratamiento_fiscal": "REQUIERE_REVISION",
            "alicuota_iva_sugerida": None,
        }

    return {
        "tipo": "A_REVISAR",
        "subtipo": "SIN_CLASIFICAR",
        "confianza": "Baja",
        "motivo": "No se pudo clasificar automáticamente.",
        "tratamiento_fiscal": "REQUIERE_REVISION",
        "alicuota_iva_sugerida": None,
    }


def sugerir_cuentas_por_movimiento(tipo, importe):
    banco = CONFIG_CONTABLE_DEFAULT["cuenta_banco"]
    gasto_banco = CONFIG_CONTABLE_DEFAULT["cuenta_gastos_bancarios"]
    iva_credito = CONFIG_CONTABLE_DEFAULT["cuenta_iva_credito"]
    perc_iva = CONFIG_CONTABLE_DEFAULT["cuenta_percepciones_iva"]
    perc_iibb = CONFIG_CONTABLE_DEFAULT["cuenta_percepciones_iibb"]
    imp_debcred = CONFIG_CONTABLE_DEFAULT["cuenta_impuesto_debcred_gasto"]
    impuestos = ("6.1.15", "IMPUESTOS, TASAS Y CONTRIBUCIONES")
    intereses = CONFIG_CONTABLE_DEFAULT["cuenta_intereses_bancarios"]
    socios_pasivo = CONFIG_CONTABLE_DEFAULT["cuenta_prestamos_socios"]
    otros = CONFIG_CONTABLE_DEFAULT["cuenta_otros_gastos_revisar"]
    deudores = CONFIG_CONTABLE_DEFAULT["cuenta_deudores"]
    proveedores = CONFIG_CONTABLE_DEFAULT["cuenta_proveedores"]

    def salida_banco(debe):
        return {
            "debe_codigo": debe[0],
            "debe_nombre": debe[1],
            "haber_codigo": banco[0],
            "haber_nombre": banco[1],
        }

    def entrada_banco(haber):
        return {
            "debe_codigo": banco[0],
            "debe_nombre": banco[1],
            "haber_codigo": haber[0],
            "haber_nombre": haber[1],
        }

    if tipo == "GASTO_BANCARIO_GRAVADO":
        return salida_banco(gasto_banco)

    if tipo == "IVA_CREDITO_FISCAL_BANCARIO":
        return salida_banco(iva_credito)

    if tipo == "PERCEPCION_IVA_BANCARIA":
        return salida_banco(perc_iva)

    if tipo == "RECAUDACION_IIBB":
        return salida_banco(perc_iibb)

    if tipo == "IMPUESTO_DEBITOS_CREDITOS":
        return salida_banco(imp_debcred)

    if tipo == "PAGO_IMPUESTOS":
        return salida_banco(impuestos)

    if tipo == "INTERES_BANCARIO_POSIBLE_105":
        return salida_banco(intereses)

    if tipo == "MOVIMIENTO_SOCIOS":
        if importe > 0:
            return entrada_banco(socios_pasivo)
        return salida_banco(CONFIG_CONTABLE_DEFAULT["cuenta_socios_activo"])

    if tipo == "COBRO_POSIBLE":
        return entrada_banco(deudores)

    if tipo == "PAGO_POSIBLE":
        return salida_banco(proveedores)

    if tipo == "TRANSFERENCIA_ENTRE_CUENTAS":
        if importe > 0:
            return entrada_banco(CONFIG_CONTABLE_DEFAULT["cuenta_caja"])
        return salida_banco(CONFIG_CONTABLE_DEFAULT["cuenta_caja"])

    if tipo == "EFECTIVO_CAJA":
        if importe > 0:
            return entrada_banco(CONFIG_CONTABLE_DEFAULT["cuenta_caja"])
        return salida_banco(CONFIG_CONTABLE_DEFAULT["cuenta_caja"])

    return salida_banco(otros) if importe < 0 else entrada_banco(CONFIG_CONTABLE_DEFAULT["cuenta_otros_gastos_revisar"])


def nombre_tipo_movimiento(tipo):
    return TIPOS_MOVIMIENTO_BANCO.get(tipo, tipo)


# ======================================================
# CONTROL DE SALDO
# ======================================================

def calcular_control_saldo_extracto(df_movimientos):
    if df_movimientos.empty:
        return {
            "saldo_inicial_estimado": 0.0,
            "total_debitos": 0.0,
            "total_creditos": 0.0,
            "saldo_final_extracto": 0.0,
            "saldo_final_calculado": 0.0,
            "diferencia": 0.0,
        }

    df = df_movimientos.copy()
    df = df.sort_values(["fecha"]).reset_index(drop=True)

    total_debitos = float(df["debito"].sum())
    total_creditos = float(df["credito"].sum())
    saldo_final_extracto = float(df.iloc[-1]["saldo"]) if "saldo" in df.columns else 0.0

    if "saldo" in df.columns and abs(float(df.iloc[0]["saldo"])) > 0.0001:
        saldo_inicial = float(df.iloc[0]["saldo"]) - float(df.iloc[0]["importe"])
    else:
        saldo_inicial = 0.0

    saldo_final_calculado = saldo_inicial + total_creditos - total_debitos
    diferencia = saldo_final_extracto - saldo_final_calculado

    return {
        "saldo_inicial_estimado": saldo_inicial,
        "total_debitos": total_debitos,
        "total_creditos": total_creditos,
        "saldo_final_extracto": saldo_final_extracto,
        "saldo_final_calculado": saldo_final_calculado,
        "diferencia": diferencia,
    }


# ======================================================
# PERSISTENCIA
# ======================================================

def construir_clave_movimiento(empresa_id, banco, nombre_cuenta, movimiento):
    base = "|".join([
        str(empresa_id),
        normalizar_texto(banco).upper(),
        normalizar_texto(nombre_cuenta).upper(),
        str(movimiento.get("fecha", "")),
        normalizar_texto(movimiento.get("referencia", "")).upper(),
        normalizar_texto(movimiento.get("causal", "")).upper(),
        normalizar_texto(movimiento.get("concepto", "")).upper(),
        f"{float(movimiento.get('importe', 0)):.2f}",
        f"{float(movimiento.get('saldo', 0)):.2f}",
    ])

    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def guardar_importacion_bancaria(
    empresa_id,
    banco,
    nombre_cuenta,
    nombre_archivo,
    formato_archivo,
    df_movimientos,
    saldo_inicial_extracto=None,
    saldo_final_extracto=None
):
    if df_movimientos.empty:
        return {
            "importacion_id": None,
            "detectados": 0,
            "procesados": 0,
            "duplicados": 0,
            "errores": 0,
            "control_saldo": {}
        }

    control = calcular_control_saldo_extracto(df_movimientos)

    if saldo_inicial_extracto is not None:
        control["saldo_inicial_estimado"] = float(saldo_inicial_extracto)

    if saldo_final_extracto is not None:
        control["saldo_final_extracto"] = float(saldo_final_extracto)

    control["saldo_final_calculado"] = (
        float(control["saldo_inicial_estimado"])
        + float(control["total_creditos"])
        - float(control["total_debitos"])
    )
    control["diferencia"] = float(control["saldo_final_extracto"]) - float(control["saldo_final_calculado"])

    conn = conectar()
    cur = conn.cursor()

    procesados = 0
    duplicados = 0
    errores = 0

    try:
        cur.execute("""
            INSERT OR IGNORE INTO bancos_cuentas
            (empresa_id, banco, nombre_cuenta, cuenta_contable_codigo, cuenta_contable_nombre)
            VALUES (?, ?, ?, ?, ?)
        """, (
            empresa_id,
            banco,
            nombre_cuenta,
            CONFIG_CONTABLE_DEFAULT["cuenta_banco"][0],
            CONFIG_CONTABLE_DEFAULT["cuenta_banco"][1],
        ))

        cur.execute("""
            INSERT INTO bancos_importaciones
            (
                empresa_id,
                banco,
                nombre_cuenta,
                nombre_archivo,
                formato_archivo,
                registros_detectados,
                procesados,
                duplicados,
                errores,
                saldo_inicial_extracto,
                total_debitos,
                total_creditos,
                saldo_final_extracto,
                saldo_final_calculado,
                diferencia_saldo,
                observacion
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?)
        """, (
            empresa_id,
            banco,
            nombre_cuenta,
            nombre_archivo,
            formato_archivo,
            len(df_movimientos),
            control["saldo_inicial_estimado"],
            control["total_debitos"],
            control["total_creditos"],
            control["saldo_final_extracto"],
            control["saldo_final_calculado"],
            control["diferencia"],
            "Importación Banco/Caja v1 con control de saldos y conciliación preparada."
        ))

        importacion_id = int(cur.lastrowid)

        for _, row in df_movimientos.iterrows():
            movimiento = row.to_dict()
            clave = construir_clave_movimiento(
                empresa_id,
                banco,
                nombre_cuenta,
                movimiento
            )

            try:
                cur.execute("""
                    INSERT OR IGNORE INTO bancos_movimientos
                    (
                        empresa_id,
                        importacion_id,
                        banco,
                        nombre_cuenta,
                        fecha,
                        anio,
                        mes,
                        referencia,
                        causal,
                        concepto,
                        importe,
                        debito,
                        credito,
                        saldo,
                        importe_conciliado,
                        importe_pendiente,
                        porcentaje_conciliado,
                        tipo_movimiento_sugerido,
                        subtipo_sugerido,
                        confianza_sugerencia,
                        motivo_sugerencia,
                        cuenta_debe_codigo,
                        cuenta_debe_nombre,
                        cuenta_haber_codigo,
                        cuenta_haber_nombre,
                        tratamiento_fiscal,
                        alicuota_iva_sugerida,
                        estado_conciliacion,
                        estado_contable,
                        clave_movimiento,
                        archivo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', 'NO_CONTABILIZADO', ?, ?)
                """, (
                    empresa_id,
                    importacion_id,
                    banco,
                    nombre_cuenta,
                    movimiento.get("fecha", ""),
                    movimiento.get("anio", None),
                    movimiento.get("mes", None),
                    movimiento.get("referencia", ""),
                    movimiento.get("causal", ""),
                    movimiento.get("concepto", ""),
                    float(movimiento.get("importe", 0)),
                    float(movimiento.get("debito", 0)),
                    float(movimiento.get("credito", 0)),
                    float(movimiento.get("saldo", 0)),
                    abs(float(movimiento.get("importe", 0))),
                    movimiento.get("tipo_movimiento_sugerido", "A_REVISAR"),
                    movimiento.get("subtipo_sugerido", ""),
                    movimiento.get("confianza_sugerencia", "Baja"),
                    movimiento.get("motivo_sugerencia", ""),
                    movimiento.get("cuenta_debe_codigo", ""),
                    movimiento.get("cuenta_debe_nombre", ""),
                    movimiento.get("cuenta_haber_codigo", ""),
                    movimiento.get("cuenta_haber_nombre", ""),
                    movimiento.get("tratamiento_fiscal", ""),
                    movimiento.get("alicuota_iva_sugerida", None),
                    clave,
                    nombre_archivo,
                ))

                if cur.rowcount == 0:
                    duplicados += 1
                else:
                    procesados += 1

            except Exception:
                errores += 1

        cur.execute("""
            UPDATE bancos_importaciones
            SET procesados = ?,
                duplicados = ?,
                errores = ?
            WHERE id = ?
        """, (procesados, duplicados, errores, importacion_id))

        conn.commit()

        grupos_generados = generar_grupos_fiscales_bancarios(importacion_id, empresa_id)
        asientos_generados = generar_asientos_propuestos_bancarios(importacion_id, empresa_id)

        return {
            "importacion_id": importacion_id,
            "detectados": len(df_movimientos),
            "procesados": procesados,
            "duplicados": duplicados,
            "errores": errores,
            "control_saldo": control,
            "grupos_fiscales": grupos_generados,
            "asientos_propuestos": asientos_generados.get("movimientos", 0),
            "lineas_asiento_propuestas": asientos_generados.get("lineas", 0),
        }

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()


# ======================================================
# GRUPOS FISCALES BANCARIOS
# ======================================================

def generar_grupos_fiscales_bancarios(importacion_id, empresa_id=1):
    df = ejecutar_query("""
        SELECT *
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND importacion_id = ?
    """, (empresa_id, importacion_id), fetch=True)

    if df.empty:
        return 0

    ejecutar_query("""
        DELETE FROM bancos_grupos_fiscales
        WHERE empresa_id = ?
          AND importacion_id = ?
    """, (empresa_id, importacion_id))

    cantidad = 0

    claves = []

    for _, row in df.iterrows():
        referencia = normalizar_texto(row.get("referencia", ""))
        causal = normalizar_texto(row.get("causal", ""))
        fecha = normalizar_texto(row.get("fecha", ""))

        clave = (fecha, referencia, causal)

        if clave not in claves:
            claves.append(clave)

    for fecha, referencia, causal in claves:
        grupo = df[
            (df["fecha"].astype(str) == str(fecha))
            & (df["referencia"].astype(str) == str(referencia))
            & (df["causal"].astype(str) == str(causal))
        ].copy()

        if grupo.empty:
            continue

        base = float(grupo[grupo["tipo_movimiento_sugerido"] == "GASTO_BANCARIO_GRAVADO"]["debito"].sum())
        iva_total = float(grupo[grupo["tipo_movimiento_sugerido"] == "IVA_CREDITO_FISCAL_BANCARIO"]["debito"].sum())
        percepcion_iva = float(grupo[grupo["tipo_movimiento_sugerido"] == "PERCEPCION_IVA_BANCARIA"]["debito"].sum())
        percepcion_iibb = float(grupo[grupo["tipo_movimiento_sugerido"] == "RECAUDACION_IIBB"]["debito"].sum())
        impuesto_dc = float(grupo[grupo["tipo_movimiento_sugerido"] == "IMPUESTO_DEBITOS_CREDITOS"]["debito"].sum())

        if base == 0 and iva_total == 0 and percepcion_iva == 0 and percepcion_iibb == 0 and impuesto_dc == 0:
            continue

        iva_21_teorico = round(base * 0.21, 2)
        iva_105_teorico = round(base * 0.105, 2)

        iva_21 = 0.0
        iva_105 = 0.0
        iva_sin_base = 0.0
        alicuota = ""
        confianza = "Media"
        estado = "PENDIENTE"
        motivo = ""

        if iva_total > 0 and base > 0:
            if abs(iva_total - iva_21_teorico) <= 1:
                iva_21 = iva_total
                alicuota = "21%"
                confianza = "Alta"
                estado = "LISTO_PARA_REVISAR"
                motivo = "IVA bancario compatible con base de gasto bancario al 21%."
            elif abs(iva_total - iva_105_teorico) <= 1:
                iva_105 = iva_total
                alicuota = "10,5%"
                confianza = "Media"
                estado = "REVISAR_ALICUOTA"
                motivo = "IVA compatible con base al 10,5%. Revisar si corresponde a interés/comisión financiera."
            else:
                iva_sin_base = iva_total
                alicuota = "No determinada"
                confianza = "Baja"
                estado = "REVISAR_DIFERENCIA"
                motivo = "IVA detectado, pero no coincide con base estimada 21% ni 10,5%."
        elif iva_total > 0 and base == 0:
            iva_sin_base = iva_total
            alicuota = "Sin base"
            confianza = "Baja"
            estado = "IVA_SIN_BASE"
            motivo = "IVA bancario detectado sin gasto bancario asociado en la misma fecha/referencia/causal."
        elif base > 0:
            alicuota = "Sin IVA detectado"
            confianza = "Media"
            estado = "BASE_SIN_IVA"
            motivo = "Gasto bancario detectado sin línea de IVA relacionada."

        total_banco = float(grupo["debito"].sum())

        ejecutar_query("""
            INSERT INTO bancos_grupos_fiscales
            (
                empresa_id,
                importacion_id,
                fecha,
                referencia,
                causal,
                banco,
                nombre_cuenta,
                base_gasto_bancario,
                iva_credito_21,
                iva_credito_105,
                iva_sin_base,
                percepcion_iva,
                percepcion_iibb,
                impuesto_debitos_creditos,
                total_banco,
                alicuota_detectada,
                confianza,
                estado_revision,
                motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            empresa_id,
            importacion_id,
            fecha,
            referencia,
            causal,
            str(grupo.iloc[0].get("banco", "")),
            str(grupo.iloc[0].get("nombre_cuenta", "")),
            base,
            iva_21,
            iva_105,
            iva_sin_base,
            percepcion_iva,
            percepcion_iibb,
            impuesto_dc,
            total_banco,
            alicuota,
            confianza,
            estado,
            motivo,
        ))

        cantidad += 1

    return cantidad



# ======================================================
# ASIENTOS PROPUESTOS AUTOMÁTICOS
# ======================================================

TIPOS_ASIENTO_AUTOMATICO_BANCO = [
    "GASTO_BANCARIO_GRAVADO",
    "IVA_CREDITO_FISCAL_BANCARIO",
    "PERCEPCION_IVA_BANCARIA",
    "RECAUDACION_IIBB",
    "IMPUESTO_DEBITOS_CREDITOS",
]

TIPOS_REVISION_ASISTIDA_BANCO = [
    "PAGO_IMPUESTOS",
    "INTERES_BANCARIO_POSIBLE_105",
    "INVERSION_RESCATE",
    "MOVIMIENTO_SOCIOS",
    "TRANSFERENCIA_ENTRE_CUENTAS",
    "EFECTIVO_CAJA",
]

TIPOS_PENDIENTES_IMPUTACION_BANCO = [
    "COBRO_POSIBLE",
    "PAGO_POSIBLE",
    "PAGO_IMPUESTOS",
    "INTERES_BANCARIO_POSIBLE_105",
    "INVERSION_RESCATE",
    "MOVIMIENTO_SOCIOS",
    "TRANSFERENCIA_ENTRE_CUENTAS",
    "EFECTIVO_CAJA",
    "OTRO_GASTO_A_REVISAR",
    "A_REVISAR",
]


def es_tipo_asiento_automatico_banco(tipo):
    return str(tipo) in TIPOS_ASIENTO_AUTOMATICO_BANCO


def generar_asientos_propuestos_bancarios(importacion_id, empresa_id=1):
    """
    Genera asientos propuestos para conceptos rutinarios bancarios.

    No contabiliza definitivamente.
    No afecta libro diario.
    No marca el movimiento como conciliado.
    Solo prepara asiento para revisión/confirmación posterior.
    """

    df = ejecutar_query("""
        SELECT *
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND importacion_id = ?
          AND tipo_movimiento_sugerido IN (
              'GASTO_BANCARIO_GRAVADO',
              'IVA_CREDITO_FISCAL_BANCARIO',
              'PERCEPCION_IVA_BANCARIA',
              'RECAUDACION_IIBB',
              'IMPUESTO_DEBITOS_CREDITOS'
          )
          AND debito > 0
    """, (empresa_id, importacion_id), fetch=True)

    if df.empty:
        return {
            "movimientos": 0,
            "lineas": 0,
        }

    conn = conectar()
    cur = conn.cursor()

    movimientos = 0
    lineas = 0

    try:
        ids = [int(x) for x in df["id"].tolist()]

        for movimiento_id in ids:
            cur.execute("""
                DELETE FROM bancos_asientos_propuestos
                WHERE empresa_id = ?
                  AND movimiento_banco_id = ?
                  AND estado = 'PROPUESTO'
            """, (empresa_id, movimiento_id))

        for _, row in df.iterrows():
            movimiento_id = int(row["id"])
            fecha = str(row.get("fecha", ""))
            concepto = normalizar_texto(row.get("concepto", ""))
            tipo = str(row.get("tipo_movimiento_sugerido", ""))
            tipo_visible = nombre_tipo_movimiento(tipo)

            monto = abs(float(row.get("debito", 0) or 0))

            if monto <= 0:
                continue

            debe_codigo = normalizar_texto(row.get("cuenta_debe_codigo", ""))
            debe_nombre = normalizar_texto(row.get("cuenta_debe_nombre", ""))
            haber_codigo = normalizar_texto(row.get("cuenta_haber_codigo", ""))
            haber_nombre = normalizar_texto(row.get("cuenta_haber_nombre", ""))

            if debe_codigo == "" or debe_nombre == "":
                cuentas = sugerir_cuentas_por_movimiento(tipo, -monto)
                debe_codigo = cuentas["debe_codigo"]
                debe_nombre = cuentas["debe_nombre"]
                haber_codigo = cuentas["haber_codigo"]
                haber_nombre = cuentas["haber_nombre"]

            if haber_codigo == "" or haber_nombre == "":
                haber_codigo, haber_nombre = CONFIG_CONTABLE_DEFAULT["cuenta_banco"]

            glosa = f"Asiento propuesto Banco/Caja - {tipo_visible} - {concepto}"

            cur.execute("""
                INSERT INTO bancos_asientos_propuestos
                (
                    empresa_id,
                    movimiento_banco_id,
                    conciliacion_id,
                    fecha,
                    cuenta_codigo,
                    cuenta_nombre,
                    debe,
                    haber,
                    glosa,
                    estado
                )
                VALUES (?, ?, NULL, ?, ?, ?, ?, 0, ?, 'PROPUESTO')
            """, (
                empresa_id,
                movimiento_id,
                fecha,
                debe_codigo,
                debe_nombre,
                monto,
                glosa,
            ))

            cur.execute("""
                INSERT INTO bancos_asientos_propuestos
                (
                    empresa_id,
                    movimiento_banco_id,
                    conciliacion_id,
                    fecha,
                    cuenta_codigo,
                    cuenta_nombre,
                    debe,
                    haber,
                    glosa,
                    estado
                )
                VALUES (?, ?, NULL, ?, ?, ?, 0, ?, ?, 'PROPUESTO')
            """, (
                empresa_id,
                movimiento_id,
                fecha,
                haber_codigo,
                haber_nombre,
                monto,
                glosa,
            ))

            cur.execute("""
                UPDATE bancos_movimientos
                SET estado_contable = 'ASIENTO_PROPUESTO'
                WHERE empresa_id = ?
                  AND id = ?
            """, (empresa_id, movimiento_id))

            movimientos += 1
            lineas += 2

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        conn.close()

    return {
        "movimientos": movimientos,
        "lineas": lineas,
    }


def obtener_asientos_propuestos_banco(empresa_id=1, importacion_id=None):
    params = [empresa_id]

    filtro = ""

    if importacion_id is not None:
        filtro = "AND m.importacion_id = ?"
        params.append(importacion_id)

    return ejecutar_query(f"""
        SELECT
            a.id,
            a.fecha,
            m.importacion_id,
            m.banco,
            m.nombre_cuenta,
            m.concepto,
            m.tipo_movimiento_sugerido,
            a.movimiento_banco_id,
            a.cuenta_codigo,
            a.cuenta_nombre,
            a.debe,
            a.haber,
            a.glosa,
            a.estado
        FROM bancos_asientos_propuestos a
        LEFT JOIN bancos_movimientos m
               ON m.id = a.movimiento_banco_id
              AND m.empresa_id = a.empresa_id
        WHERE a.empresa_id = ?
          AND a.estado = 'PROPUESTO'
          {filtro}
        ORDER BY a.fecha DESC, a.movimiento_banco_id DESC, a.id
    """, tuple(params), fetch=True)


def obtener_movimientos_pendientes_imputacion(empresa_id=1):
    return ejecutar_query("""
        SELECT
            id,
            fecha,
            anio,
            mes,
            banco,
            nombre_cuenta,
            referencia,
            causal,
            concepto,
            importe,
            debito,
            credito,
            saldo,
            importe_conciliado,
            importe_pendiente,
            porcentaje_conciliado,
            tipo_movimiento_sugerido,
            subtipo_sugerido,
            confianza_sugerencia,
            motivo_sugerencia,
            tratamiento_fiscal,
            estado_conciliacion,
            estado_contable,
            archivo,
            fecha_carga
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND estado_conciliacion IN ('PENDIENTE', 'PARCIAL')
          AND tipo_movimiento_sugerido IN (
              'COBRO_POSIBLE',
              'PAGO_POSIBLE',
              'PAGO_IMPUESTOS',
              'INTERES_BANCARIO_POSIBLE_105',
              'INVERSION_RESCATE',
              'MOVIMIENTO_SOCIOS',
              'TRANSFERENCIA_ENTRE_CUENTAS',
              'EFECTIVO_CAJA',
              'OTRO_GASTO_A_REVISAR',
              'A_REVISAR'
          )
        ORDER BY fecha DESC, id DESC
    """, (empresa_id,), fetch=True)


def obtener_resumen_operativo_importacion(importacion_id, empresa_id=1):
    df = ejecutar_query("""
        SELECT *
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND importacion_id = ?
    """, (empresa_id, importacion_id), fetch=True)

    asientos = obtener_asientos_propuestos_banco(
        empresa_id=empresa_id,
        importacion_id=importacion_id
    )

    if df.empty:
        return {
            "movimientos": pd.DataFrame(),
            "asientos": asientos,
            "por_tipo": pd.DataFrame(),
            "automaticos": pd.DataFrame(),
            "revision": pd.DataFrame(),
            "pendientes": pd.DataFrame(),
            "totales": {
                "movimientos": 0,
                "automaticos": 0,
                "revision": 0,
                "pendientes": 0,
                "lineas_asiento": len(asientos),
                "debe_asiento": float(asientos["debe"].sum()) if not asientos.empty else 0.0,
                "haber_asiento": float(asientos["haber"].sum()) if not asientos.empty else 0.0,
            }
        }

    df = df.copy()
    df["tipo_visible"] = df["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

    automaticos = df[df["tipo_movimiento_sugerido"].isin(TIPOS_ASIENTO_AUTOMATICO_BANCO)].copy()
    revision = df[df["tipo_movimiento_sugerido"].isin(TIPOS_REVISION_ASISTIDA_BANCO)].copy()
    pendientes = df[df["tipo_movimiento_sugerido"].isin(TIPOS_PENDIENTES_IMPUTACION_BANCO)].copy()

    por_tipo = (
        df.groupby(["tipo_movimiento_sugerido", "tipo_visible"], as_index=False)
        .agg(
            movimientos=("id", "count"),
            debitos=("debito", "sum"),
            creditos=("credito", "sum"),
            neto=("importe", "sum"),
        )
        .sort_values(["movimientos", "debitos", "creditos"], ascending=False)
    )

    return {
        "movimientos": df,
        "asientos": asientos,
        "por_tipo": por_tipo,
        "automaticos": automaticos,
        "revision": revision,
        "pendientes": pendientes,
        "totales": {
            "movimientos": len(df),
            "automaticos": len(automaticos),
            "revision": len(revision),
            "pendientes": len(pendientes),
            "lineas_asiento": len(asientos),
            "debe_asiento": float(asientos["debe"].sum()) if not asientos.empty else 0.0,
            "haber_asiento": float(asientos["haber"].sum()) if not asientos.empty else 0.0,
        }
    }



# ======================================================
# REGLAS
# ======================================================

def obtener_reglas_bancarias(empresa_id=1):
    return ejecutar_query("""
        SELECT *
        FROM bancos_reglas_clasificacion
        WHERE empresa_id = ?
        ORDER BY activo DESC, nombre_regla
    """, (empresa_id,), fetch=True)


def crear_regla_bancaria(
    empresa_id,
    nombre_regla,
    patron,
    causal,
    tipo_movimiento,
    subtipo,
    cuenta_debe_codigo,
    cuenta_debe_nombre,
    cuenta_haber_codigo,
    cuenta_haber_nombre,
    tratamiento_fiscal,
    alicuota_iva,
    automatizar_asiento=False,
    requiere_confirmacion=True,
    confianza="Media"
):
    ejecutar_query("""
        INSERT INTO bancos_reglas_clasificacion
        (
            empresa_id,
            nombre_regla,
            patron,
            causal,
            tipo_movimiento,
            subtipo,
            cuenta_debe_codigo,
            cuenta_debe_nombre,
            cuenta_haber_codigo,
            cuenta_haber_nombre,
            tratamiento_fiscal,
            alicuota_iva,
            automatizar_asiento,
            requiere_confirmacion,
            confianza,
            veces_detectada,
            activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)
    """, (
        empresa_id,
        nombre_regla,
        patron,
        causal,
        tipo_movimiento,
        subtipo,
        cuenta_debe_codigo,
        cuenta_debe_nombre,
        cuenta_haber_codigo,
        cuenta_haber_nombre,
        tratamiento_fiscal,
        alicuota_iva,
        1 if automatizar_asiento else 0,
        1 if requiere_confirmacion else 0,
        confianza,
    ))


def obtener_patrones_recurrentes(empresa_id=1, minimo=3):
    df = obtener_movimientos_bancarios(empresa_id)

    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["patron_normalizado"] = (
        df["causal"].astype(str).fillna("")
        + " | "
        + df["concepto"].astype(str).fillna("").apply(normalizar_texto_busqueda)
    )

    resumen = (
        df.groupby(["patron_normalizado", "tipo_movimiento_sugerido"], as_index=False)
        .agg(
            veces=("id", "count"),
            debito_total=("debito", "sum"),
            credito_total=("credito", "sum"),
            importe_promedio=("importe", "mean"),
            primera_fecha=("fecha", "min"),
            ultima_fecha=("fecha", "max"),
            ejemplo=("concepto", "first"),
            causal=("causal", "first"),
            confianza=("confianza_sugerencia", "first")
        )
    )

    resumen = resumen[resumen["veces"] >= int(minimo)].copy()

    if resumen.empty:
        return resumen

    resumen = resumen.sort_values(["veces", "debito_total", "credito_total"], ascending=False)
    resumen["tipo_visible"] = resumen["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

    return resumen


# ======================================================
# CONSULTAS
# ======================================================

def obtener_movimientos_bancarios(empresa_id=1):
    return ejecutar_query("""
        SELECT
            id,
            fecha,
            anio,
            mes,
            banco,
            nombre_cuenta,
            referencia,
            causal,
            concepto,
            importe,
            debito,
            credito,
            saldo,
            importe_conciliado,
            importe_pendiente,
            porcentaje_conciliado,
            tipo_movimiento_sugerido,
            subtipo_sugerido,
            confianza_sugerencia,
            motivo_sugerencia,
            cuenta_debe_codigo,
            cuenta_debe_nombre,
            cuenta_haber_codigo,
            cuenta_haber_nombre,
            tratamiento_fiscal,
            alicuota_iva_sugerida,
            estado_conciliacion,
            estado_contable,
            archivo,
            fecha_carga
        FROM bancos_movimientos
        WHERE empresa_id = ?
        ORDER BY fecha DESC, id DESC
    """, (empresa_id,), fetch=True)


def obtener_importaciones_bancarias(empresa_id=1):
    return ejecutar_query("""
        SELECT
            id,
            fecha_carga,
            banco,
            nombre_cuenta,
            nombre_archivo,
            formato_archivo,
            registros_detectados,
            procesados,
            duplicados,
            errores,
            saldo_inicial_extracto,
            total_debitos,
            total_creditos,
            saldo_final_extracto,
            saldo_final_calculado,
            diferencia_saldo,
            observacion
        FROM bancos_importaciones
        WHERE empresa_id = ?
        ORDER BY id DESC
    """, (empresa_id,), fetch=True)


def obtener_grupos_fiscales_bancarios(empresa_id=1):
    return ejecutar_query("""
        SELECT
            id,
            fecha,
            referencia,
            causal,
            banco,
            nombre_cuenta,
            base_gasto_bancario,
            iva_credito_21,
            iva_credito_105,
            iva_sin_base,
            percepcion_iva,
            percepcion_iibb,
            impuesto_debitos_creditos,
            total_banco,
            alicuota_detectada,
            confianza,
            estado_revision,
            motivo,
            importacion_id,
            fecha_carga
        FROM bancos_grupos_fiscales
        WHERE empresa_id = ?
        ORDER BY fecha DESC, id DESC
    """, (empresa_id,), fetch=True)


def obtener_resumen_bancario(empresa_id=1):
    df = obtener_movimientos_bancarios(empresa_id)

    if df.empty:
        return {
            "por_tipo": pd.DataFrame(),
            "por_mes": pd.DataFrame(),
            "por_estado": pd.DataFrame(),
            "indicadores": {}
        }

    total_importe_abs = float(df["importe"].abs().sum())
    total_conciliado = float(df["importe_conciliado"].sum())
    total_pendiente = float(df["importe_pendiente"].sum())

    porcentaje_importe = 0.0
    if total_importe_abs > 0:
        porcentaje_importe = round(total_conciliado / total_importe_abs * 100, 2)

    total_movimientos = len(df)
    conciliados = len(df[df["estado_conciliacion"] == "CONCILIADO"])
    parciales = len(df[df["estado_conciliacion"] == "PARCIAL"])
    pendientes = len(df[df["estado_conciliacion"] == "PENDIENTE"])

    porcentaje_movimientos = 0.0
    if total_movimientos > 0:
        porcentaje_movimientos = round(conciliados / total_movimientos * 100, 2)

    por_tipo = (
        df.groupby("tipo_movimiento_sugerido", as_index=False)
        .agg(
            movimientos=("id", "count"),
            debitos=("debito", "sum"),
            creditos=("credito", "sum"),
            neto=("importe", "sum"),
            pendiente=("importe_pendiente", "sum"),
            conciliado=("importe_conciliado", "sum"),
        )
    )

    por_tipo["tipo_visible"] = por_tipo["tipo_movimiento_sugerido"].apply(nombre_tipo_movimiento)

    por_mes = (
        df.groupby(["anio", "mes"], as_index=False)
        .agg(
            movimientos=("id", "count"),
            debitos=("debito", "sum"),
            creditos=("credito", "sum"),
            neto=("importe", "sum"),
            pendiente=("importe_pendiente", "sum"),
            conciliado=("importe_conciliado", "sum"),
        )
        .sort_values(["anio", "mes"])
    )

    por_estado = (
        df.groupby("estado_conciliacion", as_index=False)
        .agg(
            movimientos=("id", "count"),
            debitos=("debito", "sum"),
            creditos=("credito", "sum"),
            neto=("importe", "sum"),
            pendiente=("importe_pendiente", "sum"),
            conciliado=("importe_conciliado", "sum"),
        )
    )

    return {
        "por_tipo": por_tipo,
        "por_mes": por_mes,
        "por_estado": por_estado,
        "indicadores": {
            "total_movimientos": total_movimientos,
            "conciliados": conciliados,
            "parciales": parciales,
            "pendientes": pendientes,
            "total_importe_abs": total_importe_abs,
            "total_conciliado": total_conciliado,
            "total_pendiente": total_pendiente,
            "porcentaje_importe_conciliado": porcentaje_importe,
            "porcentaje_movimientos_conciliados": porcentaje_movimientos,
        }
    }
