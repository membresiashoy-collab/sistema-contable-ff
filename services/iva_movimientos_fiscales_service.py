from datetime import datetime

import pandas as pd

from database import conectar, ejecutar_query


# ======================================================
# IVA PRO - MOVIMIENTOS FISCALES ADICIONALES
# ======================================================
#
# Este servicio registra conceptos fiscales de IVA que NO nacen
# directamente de ventas_comprobantes ni compras_comprobantes.
#
# No reemplaza Ventas.
# No reemplaza Compras.
# No reemplaza Banco/Tesorería.
# No modifica Conciliación.
#
# Objetivo:
# - Crear una capa fiscal reutilizable para IVA.
# - Permitir conceptos manuales controlados.
# - Preparar integración futura con Banco, Tarjetas y Acreditadoras.
# - Evitar cargar extractos bancarios como compras manuales.
#
# Ejemplos de movimientos:
# - IVA crédito fiscal por comisión bancaria.
# - Percepción IVA sufrida en banco.
# - Retención IVA sufrida.
# - Saldo técnico anterior.
# - Saldo de libre disponibilidad aplicado.
# - Pago a cuenta.
# - Ajuste técnico controlado.
#
# Regla importante:
# Solo los movimientos CONFIRMADOS e incluidos en posición deben impactar
# en la posición IVA declarable.
# BORRADOR no impacta.
# CONFIRMADO no incluido queda como crédito/control pendiente.
# ANULADO no impacta.


# ======================================================
# CONSTANTES
# ======================================================

TABLA_MOVIMIENTOS = "iva_movimientos_fiscales"
TABLA_EVENTOS = "iva_movimientos_fiscales_eventos"

ESTADO_BORRADOR = "BORRADOR"
ESTADO_CONFIRMADO = "CONFIRMADO"
ESTADO_ANULADO = "ANULADO"

ESTADOS_VALIDOS = {
    ESTADO_BORRADOR,
    ESTADO_CONFIRMADO,
    ESTADO_ANULADO,
}

ORIGENES_VALIDOS = {
    "MANUAL",
    "BANCO",
    "TARJETA",
    "ACREDITADORA",
    "SALDO_ANTERIOR",
    "RETENCION",
    "PERCEPCION",
    "AJUSTE_TECNICO",
    "OTRO",
}

TIPOS_CONCEPTO_VALIDOS = {
    "IVA_DEBITO",
    "IVA_CREDITO",
    "IVA_NO_COMPUTABLE",
    "PERCEPCION_IVA",
    "RETENCION_IVA",
    "PERCEPCION_IIBB_INFORMATIVA",
    "SALDO_TECNICO_ANTERIOR",
    "SALDO_LIBRE_DISPONIBILIDAD",
    "PAGO_A_CUENTA",
    "AJUSTE_SALDO",
    "OTRO",
}

# Conceptos que integran la vista y el cálculo operativo de IVA.
# IIBB, Ley 25.413 y otros tributos quedan como control informativo.
TIPOS_CONCEPTO_IVA_OPERATIVOS = {
    "IVA_DEBITO",
    "IVA_CREDITO",
    "IVA_NO_COMPUTABLE",
    "PERCEPCION_IVA",
    "RETENCION_IVA",
    "SALDO_TECNICO_ANTERIOR",
    "SALDO_LIBRE_DISPONIBILIDAD",
    "PAGO_A_CUENTA",
    "AJUSTE_SALDO",
}

TIPOS_CONCEPTO_SOLO_CONTROL = TIPOS_CONCEPTO_VALIDOS - TIPOS_CONCEPTO_IVA_OPERATIVOS

COLUMNAS_MONETARIAS = [
    "neto_gravado",
    "iva_debito",
    "credito_fiscal_computable",
    "iva_no_computable",
    "percepcion_iva",
    "retencion_iva",
    "percepcion_iibb_informativa",
    "saldo_tecnico_anterior",
    "saldo_libre_disponibilidad",
    "pago_a_cuenta",
    "otros_tributos",
    "total",
]


# ======================================================
# HELPERS GENERALES
# ======================================================

def _float(valor, default=0.0):
    try:
        if valor is None:
            return default

        if isinstance(valor, str):
            texto = valor.strip()

            if texto == "":
                return default

            # Soporta formato argentino simple: 1.234,56
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")

            return float(texto)

        return float(valor)
    except Exception:
        return default


def _int(valor, default=0):
    try:
        if valor is None:
            return default

        if isinstance(valor, str) and valor.strip() == "":
            return default

        return int(float(valor))
    except Exception:
        return default


def _texto(valor, default=""):
    try:
        if valor is None:
            return default

        return str(valor).strip()
    except Exception:
        return default


def _upper(valor, default=""):
    return _texto(valor, default).upper().strip()


def _round2(valor):
    return round(_float(valor), 2)


def _bool_int(valor, default=0):
    if valor is None:
        return 1 if default else 0

    if isinstance(valor, str):
        texto = valor.strip().upper()

        if texto in {"1", "SI", "SÍ", "TRUE", "T", "YES", "Y"}:
            return 1

        if texto in {"0", "NO", "FALSE", "F", "N"}:
            return 0

    return 1 if bool(valor) else 0


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fecha_iso(valor=None):
    """
    Normaliza fecha a YYYY-MM-DD.

    Acepta:
    - YYYY-MM-DD
    - DD/MM/YYYY
    - datetime/date
    - None: usa fecha actual
    """
    if valor is None or _texto(valor) == "":
        return datetime.now().strftime("%Y-%m-%d")

    texto = _texto(valor)

    if (
        len(texto) == 10
        and texto[4] == "-"
        and texto[7] == "-"
        and texto[:4].isdigit()
        and texto[5:7].isdigit()
        and texto[8:10].isdigit()
    ):
        try:
            fecha = pd.to_datetime(texto, format="%Y-%m-%d", errors="raise")
            return fecha.strftime("%Y-%m-%d")
        except Exception:
            pass

    try:
        fecha = pd.to_datetime(valor, errors="raise", dayfirst=True)
        return fecha.strftime("%Y-%m-%d")
    except Exception:
        raise ValueError(f"Fecha inválida para movimiento fiscal IVA: {valor}")


def _anio_mes_desde_fecha(fecha_iso):
    fecha = pd.to_datetime(fecha_iso, errors="raise")
    return int(fecha.year), int(fecha.month)


def _periodo_texto(anio, mes):
    anio = _int(anio)
    mes = _int(mes)

    if anio <= 0 or mes <= 0:
        return ""

    return f"{anio}-{mes:02d}"


def _resultado_a_dataframe(resultado):
    if isinstance(resultado, pd.DataFrame):
        return resultado.copy()

    if resultado is None:
        return pd.DataFrame()

    try:
        return pd.DataFrame(resultado)
    except Exception:
        return pd.DataFrame()


def _normalizar_estado(estado):
    estado = _upper(estado, ESTADO_CONFIRMADO)

    if estado not in ESTADOS_VALIDOS:
        raise ValueError(
            f"Estado inválido para movimiento fiscal IVA: {estado}. "
            f"Valores permitidos: {sorted(ESTADOS_VALIDOS)}"
        )

    return estado


def _normalizar_origen(origen):
    origen = _upper(origen, "MANUAL")

    if origen not in ORIGENES_VALIDOS:
        raise ValueError(
            f"Origen inválido para movimiento fiscal IVA: {origen}. "
            f"Valores permitidos: {sorted(ORIGENES_VALIDOS)}"
        )

    return origen


def _normalizar_tipo_concepto(tipo_concepto):
    tipo_concepto = _upper(tipo_concepto, "OTRO")

    if tipo_concepto not in TIPOS_CONCEPTO_VALIDOS:
        raise ValueError(
            f"Tipo de concepto inválido para movimiento fiscal IVA: {tipo_concepto}. "
            f"Valores permitidos: {sorted(TIPOS_CONCEPTO_VALIDOS)}"
        )

    return tipo_concepto


def es_tipo_concepto_iva_operativo(tipo_concepto):
    """Indica si el concepto debe integrar la vista operativa de IVA."""
    return _upper(tipo_concepto, "") in TIPOS_CONCEPTO_IVA_OPERATIVOS


def _validar_periodo(anio, mes):
    anio = _int(anio)
    mes = _int(mes)

    if anio <= 0:
        raise ValueError("El año del movimiento fiscal IVA debe ser válido.")

    if mes < 1 or mes > 12:
        raise ValueError("El mes del movimiento fiscal IVA debe estar entre 1 y 12.")

    return anio, mes


def _validar_descripcion(descripcion):
    descripcion = _texto(descripcion)

    if not descripcion:
        raise ValueError("La descripción del movimiento fiscal IVA es obligatoria.")

    return descripcion


def _normalizar_origen_id(origen_id):
    if origen_id is None or _texto(origen_id) == "":
        return None

    valor = _int(origen_id)

    if valor <= 0:
        return None

    return valor


def _preparar_dataframe_monetario(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    for columna in COLUMNAS_MONETARIAS:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce").fillna(0).round(2)

    return df


# ======================================================
# ESTRUCTURA DB
# ======================================================

def _tabla_existe_conn(conn, tabla):
    df = pd.read_sql_query(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        conn,
        params=(tabla,),
    )

    return not df.empty


def _columnas_tabla_conn(conn, tabla):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)

        if df.empty or "name" not in df.columns:
            return set()

        return set(df["name"].astype(str).tolist())
    except Exception:
        return set()


def _agregar_columna_si_no_existe(conn, tabla, columna, definicion):
    columnas = _columnas_tabla_conn(conn, tabla)

    if columna not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def asegurar_estructura_iva_movimientos_fiscales():
    """
    Crea o completa la estructura de movimientos fiscales IVA.

    Es segura:
    - No borra datos.
    - No hace DROP TABLE.
    - Solo crea tablas/índices faltantes y agrega columnas faltantes.
    """
    conn = conectar()

    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS iva_movimientos_fiscales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                empresa_id INTEGER NOT NULL DEFAULT 1,

                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                periodo TEXT,

                fecha TEXT NOT NULL,

                origen TEXT NOT NULL DEFAULT 'MANUAL',
                tipo_concepto TEXT NOT NULL,

                descripcion TEXT NOT NULL,

                contraparte TEXT,
                cuit TEXT,

                comprobante_codigo TEXT,
                comprobante_tipo TEXT,
                punto_venta TEXT,
                numero TEXT,

                neto_gravado REAL NOT NULL DEFAULT 0,
                iva_debito REAL NOT NULL DEFAULT 0,
                credito_fiscal_computable REAL NOT NULL DEFAULT 0,
                iva_no_computable REAL NOT NULL DEFAULT 0,

                percepcion_iva REAL NOT NULL DEFAULT 0,
                retencion_iva REAL NOT NULL DEFAULT 0,
                percepcion_iibb_informativa REAL NOT NULL DEFAULT 0,

                saldo_tecnico_anterior REAL NOT NULL DEFAULT 0,
                saldo_libre_disponibilidad REAL NOT NULL DEFAULT 0,
                pago_a_cuenta REAL NOT NULL DEFAULT 0,

                otros_tributos REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,

                estado TEXT NOT NULL DEFAULT 'CONFIRMADO',

                incluido_en_posicion INTEGER NOT NULL DEFAULT 1,
                incluido_en_portal_iva INTEGER NOT NULL DEFAULT 0,
                periodo_declaracion TEXT,
                motivo_no_inclusion TEXT,
                fecha_inclusion_posicion TIMESTAMP,
                usuario_inclusion_posicion TEXT,
                fecha_declaracion_portal TIMESTAMP,
                usuario_declaracion_portal TEXT,

                origen_tabla TEXT,
                origen_id INTEGER,

                observacion TEXT,
                usuario TEXT,

                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_confirmacion TIMESTAMP,
                fecha_anulacion TIMESTAMP,
                motivo_anulacion TEXT,

                CHECK (mes BETWEEN 1 AND 12),
                CHECK (estado IN ('BORRADOR', 'CONFIRMADO', 'ANULADO')),
                CHECK (incluido_en_posicion IN (0, 1)),
                CHECK (incluido_en_portal_iva IN (0, 1)),
                CHECK (
                    origen IN (
                        'MANUAL',
                        'BANCO',
                        'TARJETA',
                        'ACREDITADORA',
                        'SALDO_ANTERIOR',
                        'RETENCION',
                        'PERCEPCION',
                        'AJUSTE_TECNICO',
                        'OTRO'
                    )
                ),
                CHECK (
                    tipo_concepto IN (
                        'IVA_DEBITO',
                        'IVA_CREDITO',
                        'IVA_NO_COMPUTABLE',
                        'PERCEPCION_IVA',
                        'RETENCION_IVA',
                        'PERCEPCION_IIBB_INFORMATIVA',
                        'SALDO_TECNICO_ANTERIOR',
                        'SALDO_LIBRE_DISPONIBILIDAD',
                        'PAGO_A_CUENTA',
                        'AJUSTE_SALDO',
                        'OTRO'
                    )
                )
            )
        """)

        columnas_seguras = {
            "empresa_id": "INTEGER NOT NULL DEFAULT 1",
            "anio": "INTEGER NOT NULL DEFAULT 0",
            "mes": "INTEGER NOT NULL DEFAULT 1",
            "periodo": "TEXT",
            "fecha": "TEXT",
            "origen": "TEXT NOT NULL DEFAULT 'MANUAL'",
            "tipo_concepto": "TEXT",
            "descripcion": "TEXT",
            "contraparte": "TEXT",
            "cuit": "TEXT",
            "comprobante_codigo": "TEXT",
            "comprobante_tipo": "TEXT",
            "punto_venta": "TEXT",
            "numero": "TEXT",
            "neto_gravado": "REAL NOT NULL DEFAULT 0",
            "iva_debito": "REAL NOT NULL DEFAULT 0",
            "credito_fiscal_computable": "REAL NOT NULL DEFAULT 0",
            "iva_no_computable": "REAL NOT NULL DEFAULT 0",
            "percepcion_iva": "REAL NOT NULL DEFAULT 0",
            "retencion_iva": "REAL NOT NULL DEFAULT 0",
            "percepcion_iibb_informativa": "REAL NOT NULL DEFAULT 0",
            "saldo_tecnico_anterior": "REAL NOT NULL DEFAULT 0",
            "saldo_libre_disponibilidad": "REAL NOT NULL DEFAULT 0",
            "pago_a_cuenta": "REAL NOT NULL DEFAULT 0",
            "otros_tributos": "REAL NOT NULL DEFAULT 0",
            "total": "REAL NOT NULL DEFAULT 0",
            "estado": "TEXT NOT NULL DEFAULT 'CONFIRMADO'",
            "incluido_en_posicion": "INTEGER NOT NULL DEFAULT 1",
            "incluido_en_portal_iva": "INTEGER NOT NULL DEFAULT 0",
            "periodo_declaracion": "TEXT",
            "motivo_no_inclusion": "TEXT",
            "fecha_inclusion_posicion": "TIMESTAMP",
            "usuario_inclusion_posicion": "TEXT",
            "fecha_declaracion_portal": "TIMESTAMP",
            "usuario_declaracion_portal": "TEXT",
            "origen_tabla": "TEXT",
            "origen_id": "INTEGER",
            "observacion": "TEXT",
            "usuario": "TEXT",
            "fecha_carga": "TIMESTAMP",
            "fecha_confirmacion": "TIMESTAMP",
            "fecha_anulacion": "TIMESTAMP",
            "motivo_anulacion": "TEXT",
        }

        for columna, definicion in columnas_seguras.items():
            _agregar_columna_si_no_existe(
                conn,
                TABLA_MOVIMIENTOS,
                columna,
                definicion,
            )

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_empresa_periodo
            ON iva_movimientos_fiscales (empresa_id, anio, mes)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_estado
            ON iva_movimientos_fiscales (estado)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_inclusion
            ON iva_movimientos_fiscales (empresa_id, anio, mes, estado, incluido_en_posicion)
        """)

        # Índice de protección contra duplicados activos por origen fiscal.
        # En bases antiguas puede fallar si ya existen duplicados históricos;
        # en ese caso no se rompe la app y se deja un índice común. La limpieza
        # se realiza desde el sistema con normalizar_duplicados_activos_banco_iva().
        try:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen_concepto_activo
                ON iva_movimientos_fiscales (empresa_id, origen, origen_tabla, origen_id, tipo_concepto)
                WHERE origen_id IS NOT NULL AND estado <> 'ANULADO'
            """)
        except Exception:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen_concepto_activo_control
                ON iva_movimientos_fiscales (empresa_id, origen, origen_tabla, origen_id, tipo_concepto, estado)
            """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen
            ON iva_movimientos_fiscales (origen)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_tipo
            ON iva_movimientos_fiscales (tipo_concepto)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_origen_vinculo
            ON iva_movimientos_fiscales (origen_tabla, origen_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_cuit
            ON iva_movimientos_fiscales (cuit)
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS iva_movimientos_fiscales_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                movimiento_id INTEGER,
                empresa_id INTEGER NOT NULL DEFAULT 1,

                evento TEXT NOT NULL,
                detalle TEXT,

                usuario TEXT,
                fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (movimiento_id)
                    REFERENCES iva_movimientos_fiscales(id)
                    ON DELETE SET NULL
            )
        """)

        columnas_eventos = {
            "movimiento_id": "INTEGER",
            "empresa_id": "INTEGER NOT NULL DEFAULT 1",
            "evento": "TEXT",
            "detalle": "TEXT",
            "usuario": "TEXT",
            "fecha_evento": "TIMESTAMP",
        }

        for columna, definicion in columnas_eventos.items():
            _agregar_columna_si_no_existe(
                conn,
                TABLA_EVENTOS,
                columna,
                definicion,
            )

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_eventos_movimiento
            ON iva_movimientos_fiscales_eventos (movimiento_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_eventos_empresa
            ON iva_movimientos_fiscales_eventos (empresa_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_iva_mov_fiscales_eventos_fecha
            ON iva_movimientos_fiscales_eventos (fecha_evento)
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def estructura_iva_movimientos_fiscales_existe():
    conn = conectar()

    try:
        return (
            _tabla_existe_conn(conn, TABLA_MOVIMIENTOS)
            and _tabla_existe_conn(conn, TABLA_EVENTOS)
        )
    finally:
        conn.close()


# ======================================================
# EVENTOS / AUDITORÍA FUNCIONAL
# ======================================================

def _registrar_evento_conn(
    conn,
    movimiento_id,
    empresa_id,
    evento,
    detalle="",
    usuario="",
):
    conn.execute(
        """
        INSERT INTO iva_movimientos_fiscales_eventos
        (
            movimiento_id,
            empresa_id,
            evento,
            detalle,
            usuario,
            fecha_evento
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            movimiento_id,
            int(empresa_id),
            _upper(evento, "EVENTO"),
            _texto(detalle),
            _texto(usuario),
            _now(),
        ),
    )


def listar_eventos_movimiento(movimiento_id):
    asegurar_estructura_iva_movimientos_fiscales()

    movimiento_id = _int(movimiento_id)

    if movimiento_id <= 0:
        return pd.DataFrame(columns=[
            "id",
            "movimiento_id",
            "empresa_id",
            "evento",
            "detalle",
            "usuario",
            "fecha_evento",
        ])

    df = ejecutar_query(
        """
        SELECT *
        FROM iva_movimientos_fiscales_eventos
        WHERE movimiento_id = ?
        ORDER BY fecha_evento, id
        """,
        (movimiento_id,),
        fetch=True,
    )

    return _resultado_a_dataframe(df)


def _prioridad_decision_fiscal(estado, incluido_en_posicion=False):
    estado = _upper(estado)
    incluido = _bool_int(incluido_en_posicion, default=0)

    if estado == ESTADO_CONFIRMADO and incluido:
        return 30

    if estado == ESTADO_CONFIRMADO and not incluido:
        return 20

    if estado == ESTADO_BORRADOR:
        return 10

    return 0


def _prioridad_movimiento_row(row):
    return _prioridad_decision_fiscal(
        row.get("estado"),
        row.get("incluido_en_posicion"),
    )


def _clave_operativa_banco_row(row):
    """
    Clave de control para detectar duplicados Banco -> IVA aun cuando
    existan grupos fiscales bancarios repetidos con distinto id.
    """
    return (
        _int(row.get("empresa_id"), 1),
        _upper(row.get("origen")),
        _upper(row.get("tipo_concepto")),
        _texto(row.get("fecha")),
        _texto(row.get("contraparte")).upper(),
        _texto(row.get("numero")).upper(),
        _round2(row.get("neto_gravado")),
        _round2(row.get("iva_debito")),
        _round2(row.get("credito_fiscal_computable")),
        _round2(row.get("iva_no_computable")),
        _round2(row.get("percepcion_iva")),
        _round2(row.get("retencion_iva")),
        _round2(row.get("percepcion_iibb_informativa")),
        _round2(row.get("otros_tributos")),
        _round2(row.get("total")),
    )


def _buscar_movimiento_activo_origen_conn(
    conn,
    empresa_id,
    origen,
    origen_tabla,
    origen_id,
    tipo_concepto,
):
    origen_id = _normalizar_origen_id(origen_id)

    if origen_id is None:
        return None

    df = pd.read_sql_query(
        """
        SELECT *
        FROM iva_movimientos_fiscales
        WHERE empresa_id = ?
          AND origen = ?
          AND IFNULL(origen_tabla, '') = ?
          AND origen_id = ?
          AND tipo_concepto = ?
          AND estado <> ?
        ORDER BY
            CASE
                WHEN estado = 'CONFIRMADO' AND IFNULL(incluido_en_posicion, 0) = 1 THEN 3
                WHEN estado = 'CONFIRMADO' THEN 2
                WHEN estado = 'BORRADOR' THEN 1
                ELSE 0
            END DESC,
            id ASC
        LIMIT 1
        """,
        conn,
        params=(
            _int(empresa_id, 1),
            _normalizar_origen(origen),
            _texto(origen_tabla),
            origen_id,
            _normalizar_tipo_concepto(tipo_concepto),
            ESTADO_ANULADO,
        ),
    )

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def _buscar_movimiento_activo_banco_equivalente_conn(
    conn,
    movimiento_normalizado,
):
    """
    Busca duplicados operativos de Banco -> IVA aunque el grupo fiscal
    bancario tenga otro id. Esto evita duplicar el mismo extracto/ref/importe.
    """
    if _upper(movimiento_normalizado.get("origen")) != "BANCO":
        return None

    df = pd.read_sql_query(
        """
        SELECT *
        FROM iva_movimientos_fiscales
        WHERE empresa_id = ?
          AND origen = 'BANCO'
          AND tipo_concepto = ?
          AND fecha = ?
          AND IFNULL(contraparte, '') = ?
          AND IFNULL(numero, '') = ?
          AND estado <> ?
        ORDER BY
            CASE
                WHEN estado = 'CONFIRMADO' AND IFNULL(incluido_en_posicion, 0) = 1 THEN 3
                WHEN estado = 'CONFIRMADO' THEN 2
                WHEN estado = 'BORRADOR' THEN 1
                ELSE 0
            END DESC,
            id ASC
        """,
        conn,
        params=(
            _int(movimiento_normalizado.get("empresa_id"), 1),
            _upper(movimiento_normalizado.get("tipo_concepto")),
            _texto(movimiento_normalizado.get("fecha")),
            _texto(movimiento_normalizado.get("contraparte")),
            _texto(movimiento_normalizado.get("numero")),
            ESTADO_ANULADO,
        ),
    )

    if df.empty:
        return None

    objetivo = _clave_operativa_banco_row(movimiento_normalizado)

    for _, fila in df.iterrows():
        row = fila.to_dict()
        if _clave_operativa_banco_row(row) == objetivo:
            return row

    return None


def _actualizar_movimiento_fiscal_existente_conn(
    conn,
    movimiento_id,
    movimiento_actual,
    datos,
    usuario="",
):
    prioridad_actual = _prioridad_movimiento_row(movimiento_actual)
    prioridad_nueva = _prioridad_decision_fiscal(
        datos.get("estado"),
        datos.get("incluido_en_posicion"),
    )

    if prioridad_actual > prioridad_nueva:
        _registrar_evento_conn(
            conn=conn,
            movimiento_id=_int(movimiento_id),
            empresa_id=_int(datos.get("empresa_id"), 1),
            evento="DUPLICADO_OMITIDO",
            detalle=(
                "Se intentó registrar nuevamente el mismo concepto Banco -> IVA, "
                "pero ya existía una decisión fiscal de mayor prioridad. "
                f"Estado vigente: {movimiento_actual.get('estado')}."
            ),
            usuario=usuario,
        )
        return False

    fecha_confirmacion = _now() if datos.get("estado") == ESTADO_CONFIRMADO else None
    fecha_inclusion_posicion = _now() if _bool_int(datos.get("incluido_en_posicion"), default=0) else None
    fecha_declaracion_portal = _now() if _bool_int(datos.get("incluido_en_portal_iva"), default=0) else None

    conn.execute(
        """
        UPDATE iva_movimientos_fiscales
        SET
            anio = ?,
            mes = ?,
            periodo = ?,
            fecha = ?,
            descripcion = ?,
            contraparte = ?,
            cuit = ?,
            comprobante_codigo = ?,
            comprobante_tipo = ?,
            punto_venta = ?,
            numero = ?,
            neto_gravado = ?,
            iva_debito = ?,
            credito_fiscal_computable = ?,
            iva_no_computable = ?,
            percepcion_iva = ?,
            retencion_iva = ?,
            percepcion_iibb_informativa = ?,
            saldo_tecnico_anterior = ?,
            saldo_libre_disponibilidad = ?,
            pago_a_cuenta = ?,
            otros_tributos = ?,
            total = ?,
            estado = ?,
            incluido_en_posicion = ?,
            incluido_en_portal_iva = ?,
            periodo_declaracion = ?,
            motivo_no_inclusion = ?,
            fecha_confirmacion = COALESCE(?, fecha_confirmacion),
            fecha_inclusion_posicion = ?,
            usuario_inclusion_posicion = ?,
            fecha_declaracion_portal = ?,
            usuario_declaracion_portal = ?,
            fecha_anulacion = NULL,
            motivo_anulacion = '',
            observacion = ?,
            usuario = ?
        WHERE id = ?
        """,
        (
            datos["anio"],
            datos["mes"],
            datos["periodo"],
            datos["fecha"],
            datos["descripcion"],
            datos["contraparte"],
            datos["cuit"],
            datos["comprobante_codigo"],
            datos["comprobante_tipo"],
            datos["punto_venta"],
            datos["numero"],
            datos["neto_gravado"],
            datos["iva_debito"],
            datos["credito_fiscal_computable"],
            datos["iva_no_computable"],
            datos["percepcion_iva"],
            datos["retencion_iva"],
            datos["percepcion_iibb_informativa"],
            datos["saldo_tecnico_anterior"],
            datos["saldo_libre_disponibilidad"],
            datos["pago_a_cuenta"],
            datos["otros_tributos"],
            datos["total"],
            datos["estado"],
            datos["incluido_en_posicion"],
            datos["incluido_en_portal_iva"],
            datos["periodo_declaracion"],
            datos["motivo_no_inclusion"],
            fecha_confirmacion,
            fecha_inclusion_posicion,
            _texto(usuario) if datos["incluido_en_posicion"] else "",
            fecha_declaracion_portal,
            _texto(usuario) if datos["incluido_en_portal_iva"] else "",
            datos["observacion"],
            _texto(usuario),
            _int(movimiento_id),
        ),
    )

    _registrar_evento_conn(
        conn=conn,
        movimiento_id=_int(movimiento_id),
        empresa_id=_int(datos.get("empresa_id"), 1),
        evento="ACTUALIZACION_IDEMPOTENTE",
        detalle=(
            "Se actualizó una decisión Banco -> IVA existente en lugar de crear un duplicado. "
            f"Estado: {datos['estado']}. Incluido en posición: "
            f"{'sí' if datos['incluido_en_posicion'] else 'no'}."
        ),
        usuario=usuario,
    )

    return True


def anular_movimientos_banco_sin_grupo_fiscal_activo(
    empresa_id=1,
    usuario="sistema",
    motivo="",
):
    """
    Anula lógicamente movimientos Banco -> IVA cuyo grupo fiscal bancario
    ya no existe o cuya importación bancaria origen fue eliminada.

    Corrige residuos históricos: si antes se borró una importación bancaria
    sin anular el movimiento fiscal asociado, IVA no debe seguir mostrándolo
    como pendiente ni tomado.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    empresa_id = _int(empresa_id, 1)
    motivo_final = _texto(motivo) or (
        "Anulación automática: el grupo fiscal/importación bancaria de origen ya no existe."
    )

    conn = conectar()

    try:
        if not _tabla_existe_conn(conn, "bancos_grupos_fiscales"):
            return {
                "ok": True,
                "mensaje": "No existe tabla de grupos fiscales bancarios para controlar huérfanos.",
                "anulados": 0,
                "ids_anulados": [],
            }

        tiene_importaciones = _tabla_existe_conn(conn, "bancos_importaciones")
        join_importaciones = ""
        condicion_importacion_inexistente = "0 = 1"

        if tiene_importaciones:
            join_importaciones = """
            LEFT JOIN bancos_importaciones bi
                   ON bi.empresa_id = g.empresa_id
                  AND bi.id = g.importacion_id
            """
            condicion_importacion_inexistente = "(IFNULL(g.importacion_id, 0) > 0 AND bi.id IS NULL)"

        sql = f"""
            SELECT m.id
            FROM iva_movimientos_fiscales m
            LEFT JOIN bancos_grupos_fiscales g
                   ON g.empresa_id = m.empresa_id
                  AND g.id = m.origen_id
            {join_importaciones}
            WHERE m.empresa_id = ?
              AND m.origen = 'BANCO'
              AND IFNULL(m.origen_tabla, '') = 'bancos_grupos_fiscales'
              AND IFNULL(m.origen_id, 0) > 0
              AND m.estado <> ?
              AND (
                    g.id IS NULL
                    OR {condicion_importacion_inexistente}
                  )
            ORDER BY m.id
        """

        df = pd.read_sql_query(
            sql,
            conn,
            params=(empresa_id, ESTADO_ANULADO),
        )

        if df.empty:
            return {
                "ok": True,
                "mensaje": "No hay movimientos Banco -> IVA huérfanos activos.",
                "anulados": 0,
                "ids_anulados": [],
            }

        ids = [_int(valor) for valor in df["id"].tolist() if _int(valor) > 0]

        if not ids:
            return {
                "ok": True,
                "mensaje": "No hay movimientos Banco -> IVA huérfanos válidos para anular.",
                "anulados": 0,
                "ids_anulados": [],
            }

        placeholders = ",".join(["?"] * len(ids))

        conn.execute(
            f"""
            UPDATE iva_movimientos_fiscales
            SET estado = ?,
                incluido_en_posicion = 0,
                incluido_en_portal_iva = 0,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE empresa_id = ?
              AND id IN ({placeholders})
            """,
            tuple([ESTADO_ANULADO, _now(), motivo_final, empresa_id, *ids]),
        )

        for movimiento_id in ids:
            _registrar_evento_conn(
                conn=conn,
                movimiento_id=movimiento_id,
                empresa_id=empresa_id,
                evento="ANULACION_ORIGEN_BANCO_ELIMINADO",
                detalle=motivo_final,
                usuario=usuario,
            )

        conn.commit()

        return {
            "ok": True,
            "mensaje": "Movimientos Banco -> IVA huérfanos anulados lógicamente.",
            "anulados": len(ids),
            "ids_anulados": ids,
        }

    except Exception as exc:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudieron anular movimientos Banco -> IVA huérfanos: {exc}",
            "anulados": 0,
            "ids_anulados": [],
        }

    finally:
        conn.close()


def normalizar_duplicados_activos_banco_iva(empresa_id=1, usuario="sistema"):
    """
    Limpieza por sistema: anula duplicados activos Banco -> IVA y conserva
    la decisión fiscal más fuerte para cada mismo movimiento/concepto.

    Prioridad de conservación:
    1) CONFIRMADO + incluido_en_posicion = 1
    2) CONFIRMADO + incluido_en_posicion = 0
    3) BORRADOR
    """
    asegurar_estructura_iva_movimientos_fiscales()

    conn = conectar()

    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM iva_movimientos_fiscales
            WHERE empresa_id = ?
              AND origen = 'BANCO'
              AND estado <> ?
            ORDER BY anio, mes, fecha, tipo_concepto, id
            """,
            conn,
            params=(_int(empresa_id, 1), ESTADO_ANULADO),
        )

        if df.empty:
            return {
                "ok": True,
                "mensaje": "No hay movimientos Banco -> IVA activos para normalizar.",
                "grupos_revisados": 0,
                "anulados": 0,
                "conservados": 0,
            }

        grupos = {}

        for _, fila in df.iterrows():
            row = fila.to_dict()
            clave = _clave_operativa_banco_row(row)
            grupos.setdefault(clave, []).append(row)

        anulados = 0
        conservados = 0
        grupos_revisados = 0

        for filas in grupos.values():
            if len(filas) <= 1:
                continue

            grupos_revisados += 1
            filas_ordenadas = sorted(
                filas,
                key=lambda r: (-_prioridad_movimiento_row(r), _int(r.get("id"))),
            )
            ganador = filas_ordenadas[0]
            conservados += 1

            for dup in filas_ordenadas[1:]:
                conn.execute(
                    """
                    UPDATE iva_movimientos_fiscales
                    SET
                        estado = ?,
                        incluido_en_posicion = 0,
                        incluido_en_portal_iva = 0,
                        fecha_anulacion = ?,
                        motivo_anulacion = ?
                    WHERE id = ?
                    """,
                    (
                        ESTADO_ANULADO,
                        _now(),
                        f"Anulación técnica por duplicado Banco -> IVA. Se conserva movimiento #{_int(ganador.get('id'))}.",
                        _int(dup.get("id")),
                    ),
                )

                _registrar_evento_conn(
                    conn=conn,
                    movimiento_id=_int(dup.get("id")),
                    empresa_id=_int(empresa_id, 1),
                    evento="ANULACION_DUPLICADO_BANCO_IVA",
                    detalle=f"Duplicado operativo. Se conserva movimiento #{_int(ganador.get('id'))}.",
                    usuario=usuario,
                )
                anulados += 1

        conn.commit()

        return {
            "ok": True,
            "mensaje": "Normalización Banco -> IVA finalizada.",
            "grupos_revisados": grupos_revisados,
            "anulados": anulados,
            "conservados": conservados,
        }

    except Exception as exc:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo normalizar duplicados Banco -> IVA: {exc}",
            "grupos_revisados": 0,
            "anulados": 0,
            "conservados": 0,
        }

    finally:
        conn.close()


# ======================================================
# MOVIMIENTOS FISCALES
# ======================================================

def registrar_movimiento_fiscal(
    empresa_id=1,
    anio=None,
    mes=None,
    fecha=None,
    origen="MANUAL",
    tipo_concepto="OTRO",
    descripcion="",
    contraparte="",
    cuit="",
    comprobante_codigo="",
    comprobante_tipo="",
    punto_venta="",
    numero="",
    neto_gravado=0,
    iva_debito=0,
    credito_fiscal_computable=0,
    iva_no_computable=0,
    percepcion_iva=0,
    retencion_iva=0,
    percepcion_iibb_informativa=0,
    saldo_tecnico_anterior=0,
    saldo_libre_disponibilidad=0,
    pago_a_cuenta=0,
    otros_tributos=0,
    total=None,
    estado=ESTADO_CONFIRMADO,
    incluido_en_posicion=True,
    incluido_en_portal_iva=False,
    periodo_declaracion="",
    motivo_no_inclusion="",
    usuario_inclusion_posicion="",
    usuario_declaracion_portal="",
    origen_tabla="",
    origen_id=None,
    observacion="",
    usuario="",
):
    """
    Registra un movimiento fiscal adicional de IVA.

    Importante:
    - Si estado = CONFIRMADO e incluido_en_posicion = True, impactará en la posición IVA.
    - Si estado = CONFIRMADO e incluido_en_posicion = False, quedará como crédito/control pendiente.
    - Si estado = BORRADOR, quedará guardado sin impactar.
    - ANULADO solo debería usarse por función anular_movimiento_fiscal,
      pero se permite para migraciones o importaciones controladas.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    empresa_id = _int(empresa_id, 1)

    if empresa_id <= 0:
        empresa_id = 1

    fecha = _fecha_iso(fecha)

    if anio is None or mes is None:
        anio_fecha, mes_fecha = _anio_mes_desde_fecha(fecha)
        anio = anio if anio is not None else anio_fecha
        mes = mes if mes is not None else mes_fecha

    anio, mes = _validar_periodo(anio, mes)
    periodo = _periodo_texto(anio, mes)

    origen = _normalizar_origen(origen)
    tipo_concepto = _normalizar_tipo_concepto(tipo_concepto)
    estado = _normalizar_estado(estado)
    descripcion = _validar_descripcion(descripcion)

    origen_id = _normalizar_origen_id(origen_id)

    valores = {
        "neto_gravado": _round2(neto_gravado),
        "iva_debito": _round2(iva_debito),
        "credito_fiscal_computable": _round2(credito_fiscal_computable),
        "iva_no_computable": _round2(iva_no_computable),
        "percepcion_iva": _round2(percepcion_iva),
        "retencion_iva": _round2(retencion_iva),
        "percepcion_iibb_informativa": _round2(percepcion_iibb_informativa),
        "saldo_tecnico_anterior": _round2(saldo_tecnico_anterior),
        "saldo_libre_disponibilidad": _round2(saldo_libre_disponibilidad),
        "pago_a_cuenta": _round2(pago_a_cuenta),
        "otros_tributos": _round2(otros_tributos),
        "total": _round2(total) if total is not None else 0.0,
    }

    incluido_en_posicion = _bool_int(incluido_en_posicion, default=1)
    incluido_en_portal_iva = _bool_int(incluido_en_portal_iva, default=0)

    if estado != ESTADO_CONFIRMADO:
        incluido_en_posicion = 0
        incluido_en_portal_iva = 0

    if not incluido_en_posicion:
        incluido_en_portal_iva = 0

    periodo_declaracion = _texto(periodo_declaracion)
    motivo_no_inclusion = _texto(motivo_no_inclusion)

    if incluido_en_portal_iva and not periodo_declaracion:
        periodo_declaracion = periodo

    fecha_confirmacion = _now() if estado == ESTADO_CONFIRMADO else None
    fecha_anulacion = _now() if estado == ESTADO_ANULADO else None
    fecha_inclusion_posicion = _now() if incluido_en_posicion else None
    fecha_declaracion_portal = _now() if incluido_en_portal_iva else None

    datos_normalizados = {
        "empresa_id": empresa_id,
        "anio": anio,
        "mes": mes,
        "periodo": periodo,
        "fecha": fecha,
        "origen": origen,
        "tipo_concepto": tipo_concepto,
        "descripcion": descripcion,
        "contraparte": _texto(contraparte),
        "cuit": _texto(cuit),
        "comprobante_codigo": _texto(comprobante_codigo),
        "comprobante_tipo": _texto(comprobante_tipo),
        "punto_venta": _texto(punto_venta),
        "numero": _texto(numero),
        "neto_gravado": valores["neto_gravado"],
        "iva_debito": valores["iva_debito"],
        "credito_fiscal_computable": valores["credito_fiscal_computable"],
        "iva_no_computable": valores["iva_no_computable"],
        "percepcion_iva": valores["percepcion_iva"],
        "retencion_iva": valores["retencion_iva"],
        "percepcion_iibb_informativa": valores["percepcion_iibb_informativa"],
        "saldo_tecnico_anterior": valores["saldo_tecnico_anterior"],
        "saldo_libre_disponibilidad": valores["saldo_libre_disponibilidad"],
        "pago_a_cuenta": valores["pago_a_cuenta"],
        "otros_tributos": valores["otros_tributos"],
        "total": valores["total"],
        "estado": estado,
        "incluido_en_posicion": incluido_en_posicion,
        "incluido_en_portal_iva": incluido_en_portal_iva,
        "periodo_declaracion": periodo_declaracion,
        "motivo_no_inclusion": motivo_no_inclusion,
        "origen_tabla": _texto(origen_tabla),
        "origen_id": origen_id,
        "observacion": _texto(observacion),
    }

    conn = conectar()

    try:
        cur = conn.cursor()

        existente = _buscar_movimiento_activo_origen_conn(
            conn=conn,
            empresa_id=empresa_id,
            origen=origen,
            origen_tabla=origen_tabla,
            origen_id=origen_id,
            tipo_concepto=tipo_concepto,
        )

        if existente is None:
            existente = _buscar_movimiento_activo_banco_equivalente_conn(
                conn=conn,
                movimiento_normalizado=datos_normalizados,
            )

        if existente is not None:
            movimiento_id = _int(existente.get("id"))
            _actualizar_movimiento_fiscal_existente_conn(
                conn=conn,
                movimiento_id=movimiento_id,
                movimiento_actual=existente,
                datos=datos_normalizados,
                usuario=usuario,
            )
            conn.commit()
            return obtener_movimiento_fiscal(movimiento_id)

        cur.execute(
            """
            INSERT INTO iva_movimientos_fiscales
            (
                empresa_id,
                anio,
                mes,
                periodo,
                fecha,
                origen,
                tipo_concepto,
                descripcion,
                contraparte,
                cuit,
                comprobante_codigo,
                comprobante_tipo,
                punto_venta,
                numero,
                neto_gravado,
                iva_debito,
                credito_fiscal_computable,
                iva_no_computable,
                percepcion_iva,
                retencion_iva,
                percepcion_iibb_informativa,
                saldo_tecnico_anterior,
                saldo_libre_disponibilidad,
                pago_a_cuenta,
                otros_tributos,
                total,
                estado,
                incluido_en_posicion,
                incluido_en_portal_iva,
                periodo_declaracion,
                motivo_no_inclusion,
                fecha_inclusion_posicion,
                usuario_inclusion_posicion,
                fecha_declaracion_portal,
                usuario_declaracion_portal,
                origen_tabla,
                origen_id,
                observacion,
                usuario,
                fecha_carga,
                fecha_confirmacion,
                fecha_anulacion,
                motivo_anulacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                anio,
                mes,
                periodo,
                fecha,
                origen,
                tipo_concepto,
                descripcion,
                _texto(contraparte),
                _texto(cuit),
                _texto(comprobante_codigo),
                _texto(comprobante_tipo),
                _texto(punto_venta),
                _texto(numero),
                valores["neto_gravado"],
                valores["iva_debito"],
                valores["credito_fiscal_computable"],
                valores["iva_no_computable"],
                valores["percepcion_iva"],
                valores["retencion_iva"],
                valores["percepcion_iibb_informativa"],
                valores["saldo_tecnico_anterior"],
                valores["saldo_libre_disponibilidad"],
                valores["pago_a_cuenta"],
                valores["otros_tributos"],
                valores["total"],
                estado,
                incluido_en_posicion,
                incluido_en_portal_iva,
                periodo_declaracion,
                motivo_no_inclusion,
                fecha_inclusion_posicion,
                _texto(usuario_inclusion_posicion) if incluido_en_posicion else "",
                fecha_declaracion_portal,
                _texto(usuario_declaracion_portal) if incluido_en_portal_iva else "",
                _texto(origen_tabla),
                origen_id,
                _texto(observacion),
                _texto(usuario),
                _now(),
                fecha_confirmacion,
                fecha_anulacion,
                "Alta registrada como anulada" if estado == ESTADO_ANULADO else "",
            ),
        )

        movimiento_id = cur.lastrowid

        _registrar_evento_conn(
            conn=conn,
            movimiento_id=movimiento_id,
            empresa_id=empresa_id,
            evento="CREACION",
            detalle=(
                f"Movimiento fiscal IVA creado en estado {estado}. "
                f"Incluido en posición: {'sí' if incluido_en_posicion else 'no'}. "
                f"Declarado Portal IVA: {'sí' if incluido_en_portal_iva else 'no'}."
            ),
            usuario=usuario,
        )

        if estado == ESTADO_CONFIRMADO:
            _registrar_evento_conn(
                conn=conn,
                movimiento_id=movimiento_id,
                empresa_id=empresa_id,
                evento="CONFIRMACION",
                detalle="Movimiento fiscal IVA confirmado al momento de la carga.",
                usuario=usuario,
            )

        if estado == ESTADO_ANULADO:
            _registrar_evento_conn(
                conn=conn,
                movimiento_id=movimiento_id,
                empresa_id=empresa_id,
                evento="ANULACION",
                detalle="Movimiento fiscal IVA creado directamente como anulado.",
                usuario=usuario,
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return obtener_movimiento_fiscal(movimiento_id)


def obtener_movimiento_fiscal(movimiento_id):
    asegurar_estructura_iva_movimientos_fiscales()

    movimiento_id = _int(movimiento_id)

    if movimiento_id <= 0:
        return None

    df = ejecutar_query(
        """
        SELECT *
        FROM iva_movimientos_fiscales
        WHERE id = ?
        LIMIT 1
        """,
        (movimiento_id,),
        fetch=True,
    )

    df = _resultado_a_dataframe(df)

    if df.empty:
        return None

    row = df.iloc[0].to_dict()

    for columna in COLUMNAS_MONETARIAS:
        if columna in row:
            row[columna] = _round2(row[columna])

    return row


def listar_movimientos_fiscales(
    empresa_id=1,
    anio=None,
    mes=None,
    estado=None,
    origen=None,
    tipo_concepto=None,
    incluido_en_posicion=None,
    incluido_en_portal_iva=None,
    incluir_anulados=False,
):
    """
    Lista movimientos fiscales IVA.

    Por defecto no muestra anulados.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    condiciones = []
    params = []

    if empresa_id is not None:
        condiciones.append("empresa_id = ?")
        params.append(_int(empresa_id, 1))

    if anio is not None:
        condiciones.append("anio = ?")
        params.append(_int(anio))

    if mes is not None:
        condiciones.append("mes = ?")
        params.append(_int(mes))

    if estado is not None and _texto(estado) != "":
        condiciones.append("estado = ?")
        params.append(_normalizar_estado(estado))
    elif not incluir_anulados:
        condiciones.append("estado <> ?")
        params.append(ESTADO_ANULADO)

    if origen is not None and _texto(origen) != "":
        condiciones.append("origen = ?")
        params.append(_normalizar_origen(origen))

    if tipo_concepto is not None and _texto(tipo_concepto) != "":
        condiciones.append("tipo_concepto = ?")
        params.append(_normalizar_tipo_concepto(tipo_concepto))

    if incluido_en_posicion is not None:
        condiciones.append("IFNULL(incluido_en_posicion, 1) = ?")
        params.append(_bool_int(incluido_en_posicion, default=1))

    if incluido_en_portal_iva is not None:
        condiciones.append("IFNULL(incluido_en_portal_iva, 0) = ?")
        params.append(_bool_int(incluido_en_portal_iva, default=0))

    # Vista operativa: no mostrar movimientos Banco -> IVA cuyo grupo fiscal
    # o importación origen ya no existe. Esto no modifica la base; solo evita
    # contaminar IVA con residuos técnicos de cargas bancarias eliminadas.
    #
    # Importante para tests y bases parciales: este filtro solo se agrega si
    # existen las tablas bancarias. El servicio de IVA debe poder funcionar
    # también en bases temporales/mínimas donde todavía no está creado Banco.
    filtrar_huerfanos_banco = False

    if not incluir_anulados:
        conn_check = None

        try:
            conn_check = conectar()
            filtrar_huerfanos_banco = (
                _tabla_existe_conn(conn_check, "bancos_grupos_fiscales")
                and _tabla_existe_conn(conn_check, "bancos_importaciones")
            )
        except Exception:
            filtrar_huerfanos_banco = False
        finally:
            try:
                if conn_check is not None:
                    conn_check.close()
            except Exception:
                pass

    if not incluir_anulados and filtrar_huerfanos_banco:
        condiciones.append(
            """
            NOT (
                origen = 'BANCO'
                AND IFNULL(origen_tabla, '') = 'bancos_grupos_fiscales'
                AND IFNULL(origen_id, 0) > 0
                AND NOT EXISTS (
                    SELECT 1
                    FROM bancos_grupos_fiscales g
                    LEFT JOIN bancos_importaciones bi
                           ON bi.empresa_id = g.empresa_id
                          AND bi.id = g.importacion_id
                    WHERE g.empresa_id = iva_movimientos_fiscales.empresa_id
                      AND g.id = iva_movimientos_fiscales.origen_id
                      AND (IFNULL(g.importacion_id, 0) = 0 OR bi.id IS NOT NULL)
                )
            )
            """
        )

    sql = """
        SELECT *
        FROM iva_movimientos_fiscales
    """

    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)

    sql += """
        ORDER BY anio DESC, mes DESC, fecha DESC, id DESC
    """

    df = ejecutar_query(sql, tuple(params), fetch=True)
    df = _resultado_a_dataframe(df)
    df = _preparar_dataframe_monetario(df)

    return df


def confirmar_movimiento_fiscal(
    movimiento_id,
    usuario="",
    detalle="Confirmación manual del movimiento fiscal IVA.",
    incluido_en_posicion=True,
    incluido_en_portal_iva=False,
    periodo_declaracion="",
    motivo_no_inclusion="",
):
    asegurar_estructura_iva_movimientos_fiscales()

    movimiento = obtener_movimiento_fiscal(movimiento_id)

    if movimiento is None:
        raise ValueError("No se encontró el movimiento fiscal IVA a confirmar.")

    if movimiento.get("estado") == ESTADO_ANULADO:
        raise ValueError("No se puede confirmar un movimiento fiscal IVA anulado.")

    if movimiento.get("estado") == ESTADO_CONFIRMADO:
        return actualizar_inclusion_movimiento_fiscal(
            movimiento_id=movimiento_id,
            incluido_en_posicion=incluido_en_posicion,
            incluido_en_portal_iva=incluido_en_portal_iva,
            periodo_declaracion=periodo_declaracion,
            motivo_no_inclusion=motivo_no_inclusion,
            usuario=usuario,
            detalle=detalle,
        )

    incluido_en_posicion = _bool_int(incluido_en_posicion, default=1)
    incluido_en_portal_iva = _bool_int(incluido_en_portal_iva, default=0)

    if not incluido_en_posicion:
        incluido_en_portal_iva = 0

    periodo_declaracion = _texto(periodo_declaracion)

    if incluido_en_portal_iva and not periodo_declaracion:
        periodo_declaracion = _periodo_texto(_int(movimiento.get("anio")), _int(movimiento.get("mes")))

    conn = conectar()

    try:
        conn.execute(
            """
            UPDATE iva_movimientos_fiscales
            SET
                estado = ?,
                incluido_en_posicion = ?,
                incluido_en_portal_iva = ?,
                periodo_declaracion = ?,
                motivo_no_inclusion = ?,
                fecha_confirmacion = ?,
                fecha_inclusion_posicion = ?,
                usuario_inclusion_posicion = ?,
                fecha_declaracion_portal = ?,
                usuario_declaracion_portal = ?,
                fecha_anulacion = NULL,
                motivo_anulacion = NULL
            WHERE id = ?
            """,
            (
                ESTADO_CONFIRMADO,
                incluido_en_posicion,
                incluido_en_portal_iva,
                periodo_declaracion,
                _texto(motivo_no_inclusion),
                _now(),
                _now() if incluido_en_posicion else None,
                _texto(usuario) if incluido_en_posicion else "",
                _now() if incluido_en_portal_iva else None,
                _texto(usuario) if incluido_en_portal_iva else "",
                _int(movimiento_id),
            ),
        )

        _registrar_evento_conn(
            conn=conn,
            movimiento_id=_int(movimiento_id),
            empresa_id=_int(movimiento.get("empresa_id"), 1),
            evento="CONFIRMACION",
            detalle=detalle,
            usuario=usuario,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return obtener_movimiento_fiscal(movimiento_id)



def actualizar_inclusion_movimiento_fiscal(
    movimiento_id,
    incluido_en_posicion=True,
    incluido_en_portal_iva=False,
    periodo_declaracion="",
    motivo_no_inclusion="",
    usuario="",
    detalle="Actualización de inclusión en posición IVA.",
):
    """
    Actualiza si un movimiento fiscal confirmado se toma o no en la posición IVA.

    Uso contable:
    - incluido_en_posicion = 1: impacta la posición IVA declarable.
    - incluido_en_posicion = 0: queda como crédito/control pendiente.
    - incluido_en_portal_iva = 1: marca que además fue declarado/tomado en Portal IVA.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    movimiento = obtener_movimiento_fiscal(movimiento_id)

    if movimiento is None:
        raise ValueError("No se encontró el movimiento fiscal IVA.")

    if movimiento.get("estado") == ESTADO_ANULADO:
        raise ValueError("No se puede modificar la inclusión de un movimiento fiscal IVA anulado.")

    incluido_en_posicion = _bool_int(incluido_en_posicion, default=1)
    incluido_en_portal_iva = _bool_int(incluido_en_portal_iva, default=0)

    if movimiento.get("estado") != ESTADO_CONFIRMADO:
        incluido_en_posicion = 0
        incluido_en_portal_iva = 0

    if not incluido_en_posicion:
        incluido_en_portal_iva = 0

    periodo_declaracion = _texto(periodo_declaracion)

    if incluido_en_portal_iva and not periodo_declaracion:
        periodo_declaracion = _periodo_texto(
            _int(movimiento.get("anio")),
            _int(movimiento.get("mes")),
        )

    conn = conectar()

    try:
        conn.execute(
            """
            UPDATE iva_movimientos_fiscales
            SET
                incluido_en_posicion = ?,
                incluido_en_portal_iva = ?,
                periodo_declaracion = ?,
                motivo_no_inclusion = ?,
                fecha_inclusion_posicion = ?,
                usuario_inclusion_posicion = ?,
                fecha_declaracion_portal = ?,
                usuario_declaracion_portal = ?
            WHERE id = ?
            """,
            (
                incluido_en_posicion,
                incluido_en_portal_iva,
                periodo_declaracion,
                _texto(motivo_no_inclusion),
                _now() if incluido_en_posicion else None,
                _texto(usuario) if incluido_en_posicion else "",
                _now() if incluido_en_portal_iva else None,
                _texto(usuario) if incluido_en_portal_iva else "",
                _int(movimiento_id),
            ),
        )

        _registrar_evento_conn(
            conn=conn,
            movimiento_id=_int(movimiento_id),
            empresa_id=_int(movimiento.get("empresa_id"), 1),
            evento="INCLUSION_POSICION",
            detalle=(
                f"{detalle} Incluido en posición: {'sí' if incluido_en_posicion else 'no'}. "
                f"Declarado Portal IVA: {'sí' if incluido_en_portal_iva else 'no'}. "
                f"Motivo: {_texto(motivo_no_inclusion)}"
            ),
            usuario=usuario,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return obtener_movimiento_fiscal(movimiento_id)


def anular_movimiento_fiscal(
    movimiento_id,
    motivo,
    usuario="",
):
    """
    Anula lógicamente un movimiento fiscal IVA.

    No borra físicamente.
    No recalcula base.
    No toca Ventas/Compras/Banco.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    motivo = _texto(motivo)

    if not motivo:
        raise ValueError("Debe indicarse un motivo para anular el movimiento fiscal IVA.")

    movimiento = obtener_movimiento_fiscal(movimiento_id)

    if movimiento is None:
        raise ValueError("No se encontró el movimiento fiscal IVA a anular.")

    if movimiento.get("estado") == ESTADO_ANULADO:
        return movimiento

    conn = conectar()

    try:
        conn.execute(
            """
            UPDATE iva_movimientos_fiscales
            SET
                estado = ?,
                incluido_en_posicion = 0,
                incluido_en_portal_iva = 0,
                fecha_anulacion = ?,
                motivo_anulacion = ?
            WHERE id = ?
            """,
            (
                ESTADO_ANULADO,
                _now(),
                motivo,
                _int(movimiento_id),
            ),
        )

        _registrar_evento_conn(
            conn=conn,
            movimiento_id=_int(movimiento_id),
            empresa_id=_int(movimiento.get("empresa_id"), 1),
            evento="ANULACION",
            detalle=motivo,
            usuario=usuario,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return obtener_movimiento_fiscal(movimiento_id)


# ======================================================
# TOTALES PARA POSICIÓN IVA
# ======================================================

def obtener_totales_movimientos_fiscales_periodo(
    empresa_id=1,
    anio=None,
    mes=None,
    incluir_borradores=False,
    solo_incluidos_en_posicion=True,
):
    """
    Devuelve totales de movimientos fiscales adicionales para un período.

    Por defecto:
    - Incluye solo CONFIRMADOS.
    - Excluye BORRADOR.
    - Excluye ANULADO.
    - Por defecto incluye únicamente movimientos marcados como incluidos en posición.

    Estos totales luego se integran a services/iva_service.py.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    anio, mes = _validar_periodo(anio, mes)

    estados = [ESTADO_CONFIRMADO]

    if incluir_borradores:
        estados.append(ESTADO_BORRADOR)

    placeholders = ",".join(["?"] * len(estados))
    tipos_operativos = sorted(TIPOS_CONCEPTO_IVA_OPERATIVOS)
    placeholders_tipos = ",".join(["?"] * len(tipos_operativos))

    params = [
        _int(empresa_id, 1),
        anio,
        mes,
        *estados,
        *tipos_operativos,
    ]

    filtro_inclusion = ""

    if solo_incluidos_en_posicion:
        if incluir_borradores:
            # Para control/revisión, los BORRADOR deben poder verse aunque
            # no estén incluidos en posición. Esto mantiene compatibilidad
            # con la regla histórica de incluir_borradores=True.
            filtro_inclusion = (
                "AND (IFNULL(incluido_en_posicion, 1) = 1 "
                "OR estado = 'BORRADOR')"
            )
        else:
            # Para posición IVA declarable, solo impactan movimientos
            # confirmados e incluidos.
            filtro_inclusion = "AND IFNULL(incluido_en_posicion, 1) = 1"

    df = ejecutar_query(
        f"""
        SELECT
            COUNT(*) AS cantidad_movimientos_fiscales,

            COALESCE(SUM(neto_gravado), 0) AS neto_gravado,
            COALESCE(SUM(iva_debito), 0) AS iva_debito,
            COALESCE(SUM(credito_fiscal_computable), 0) AS credito_fiscal_computable,
            COALESCE(SUM(iva_no_computable), 0) AS iva_no_computable,

            COALESCE(SUM(percepcion_iva), 0) AS percepcion_iva,
            COALESCE(SUM(retencion_iva), 0) AS retencion_iva,
            COALESCE(SUM(percepcion_iibb_informativa), 0) AS percepcion_iibb_informativa,

            COALESCE(SUM(saldo_tecnico_anterior), 0) AS saldo_tecnico_anterior,
            COALESCE(SUM(saldo_libre_disponibilidad), 0) AS saldo_libre_disponibilidad,
            COALESCE(SUM(pago_a_cuenta), 0) AS pago_a_cuenta,

            COALESCE(SUM(otros_tributos), 0) AS otros_tributos,
            COALESCE(SUM(total), 0) AS total
        FROM iva_movimientos_fiscales
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
          AND estado IN ({placeholders})
          AND tipo_concepto IN ({placeholders_tipos})
          {filtro_inclusion}
        """,
        tuple(params),
        fetch=True,
    )

    df = _resultado_a_dataframe(df)

    if df.empty:
        return {
            "cantidad_movimientos_fiscales": 0,
            "neto_gravado": 0.0,
            "iva_debito": 0.0,
            "credito_fiscal_computable": 0.0,
            "iva_no_computable": 0.0,
            "percepcion_iva": 0.0,
            "retencion_iva": 0.0,
            "percepcion_iibb_informativa": 0.0,
            "saldo_tecnico_anterior": 0.0,
            "saldo_libre_disponibilidad": 0.0,
            "pago_a_cuenta": 0.0,
            "otros_tributos": 0.0,
            "total": 0.0,
        }

    row = df.iloc[0].to_dict()

    return {
        "cantidad_movimientos_fiscales": _int(row.get("cantidad_movimientos_fiscales", 0)),
        "neto_gravado": _round2(row.get("neto_gravado", 0)),
        "iva_debito": _round2(row.get("iva_debito", 0)),
        "credito_fiscal_computable": _round2(row.get("credito_fiscal_computable", 0)),
        "iva_no_computable": _round2(row.get("iva_no_computable", 0)),
        "percepcion_iva": _round2(row.get("percepcion_iva", 0)),
        "retencion_iva": _round2(row.get("retencion_iva", 0)),
        "percepcion_iibb_informativa": _round2(row.get("percepcion_iibb_informativa", 0)),
        "saldo_tecnico_anterior": _round2(row.get("saldo_tecnico_anterior", 0)),
        "saldo_libre_disponibilidad": _round2(row.get("saldo_libre_disponibilidad", 0)),
        "pago_a_cuenta": _round2(row.get("pago_a_cuenta", 0)),
        "otros_tributos": _round2(row.get("otros_tributos", 0)),
        "total": _round2(row.get("total", 0)),
    }


def obtener_impacto_posicion_iva_periodo(
    empresa_id=1,
    anio=None,
    mes=None,
):
    """
    Devuelve el impacto fiscal adicional listo para integrarse
    en la posición mensual IVA.

    No calcula ventas/compras.
    Solo devuelve movimientos fiscales adicionales confirmados.
    """
    totales = obtener_totales_movimientos_fiscales_periodo(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
        incluir_borradores=False,
    )

    iva_debito_adicional = _round2(totales["iva_debito"])
    credito_fiscal_adicional = _round2(totales["credito_fiscal_computable"])
    percepcion_iva_adicional = _round2(totales["percepcion_iva"])
    retencion_iva_adicional = _round2(totales["retencion_iva"])
    saldo_tecnico_anterior = _round2(totales["saldo_tecnico_anterior"])
    saldo_libre_disponibilidad = _round2(totales["saldo_libre_disponibilidad"])
    pago_a_cuenta = _round2(totales["pago_a_cuenta"])

    deducciones_saldo_preliminar = _round2(
        percepcion_iva_adicional
        + retencion_iva_adicional
        + saldo_libre_disponibilidad
        + pago_a_cuenta
    )

    return {
        "cantidad_movimientos_fiscales": totales["cantidad_movimientos_fiscales"],

        "neto_gravado_movimientos_fiscales": _round2(totales["neto_gravado"]),

        "iva_debito_adicional": iva_debito_adicional,
        "credito_fiscal_computable_adicional": credito_fiscal_adicional,
        "iva_no_computable_adicional": _round2(totales["iva_no_computable"]),

        "percepcion_iva_adicional": percepcion_iva_adicional,
        "retencion_iva_adicional": retencion_iva_adicional,
        "percepcion_iibb_informativa_adicional": _round2(
            totales["percepcion_iibb_informativa"]
        ),

        "saldo_tecnico_anterior": saldo_tecnico_anterior,
        "saldo_libre_disponibilidad": saldo_libre_disponibilidad,
        "pago_a_cuenta": pago_a_cuenta,

        "otros_tributos_adicionales": _round2(totales["otros_tributos"]),
        "total_movimientos_fiscales": _round2(totales["total"]),

        "deducciones_saldo_preliminar": deducciones_saldo_preliminar,
    }


def obtener_resumen_movimientos_fiscales_por_origen(
    empresa_id=1,
    anio=None,
    mes=None,
    incluir_borradores=False,
    solo_incluidos_en_posicion=True,
):
    """
    Resume movimientos fiscales por origen y tipo de concepto.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    anio, mes = _validar_periodo(anio, mes)

    estados = [ESTADO_CONFIRMADO]

    if incluir_borradores:
        estados.append(ESTADO_BORRADOR)

    placeholders = ",".join(["?"] * len(estados))
    tipos_operativos = sorted(TIPOS_CONCEPTO_IVA_OPERATIVOS)
    placeholders_tipos = ",".join(["?"] * len(tipos_operativos))

    params = [
        _int(empresa_id, 1),
        anio,
        mes,
        *estados,
        *tipos_operativos,
    ]

    filtro_inclusion = ""

    if solo_incluidos_en_posicion:
        if incluir_borradores:
            # Para control/revisión, los BORRADOR deben poder verse aunque
            # no estén incluidos en posición. Esto mantiene compatibilidad
            # con la regla histórica de incluir_borradores=True.
            filtro_inclusion = (
                "AND (IFNULL(incluido_en_posicion, 1) = 1 "
                "OR estado = 'BORRADOR')"
            )
        else:
            # Para posición IVA declarable, solo impactan movimientos
            # confirmados e incluidos.
            filtro_inclusion = "AND IFNULL(incluido_en_posicion, 1) = 1"

    df = ejecutar_query(
        f"""
        SELECT
            origen,
            tipo_concepto,
            COUNT(*) AS cantidad,
            COALESCE(SUM(neto_gravado), 0) AS neto_gravado,
            COALESCE(SUM(iva_debito), 0) AS iva_debito,
            COALESCE(SUM(credito_fiscal_computable), 0) AS credito_fiscal_computable,
            COALESCE(SUM(iva_no_computable), 0) AS iva_no_computable,
            COALESCE(SUM(percepcion_iva), 0) AS percepcion_iva,
            COALESCE(SUM(retencion_iva), 0) AS retencion_iva,
            COALESCE(SUM(percepcion_iibb_informativa), 0) AS percepcion_iibb_informativa,
            COALESCE(SUM(saldo_tecnico_anterior), 0) AS saldo_tecnico_anterior,
            COALESCE(SUM(saldo_libre_disponibilidad), 0) AS saldo_libre_disponibilidad,
            COALESCE(SUM(pago_a_cuenta), 0) AS pago_a_cuenta,
            COALESCE(SUM(otros_tributos), 0) AS otros_tributos,
            COALESCE(SUM(total), 0) AS total
        FROM iva_movimientos_fiscales
        WHERE empresa_id = ?
          AND anio = ?
          AND mes = ?
          AND estado IN ({placeholders})
          AND tipo_concepto IN ({placeholders_tipos})
          {filtro_inclusion}
        GROUP BY origen, tipo_concepto
        ORDER BY origen, tipo_concepto
        """,
        tuple(params),
        fetch=True,
    )

    df = _resultado_a_dataframe(df)
    df = _preparar_dataframe_monetario(df)

    return df


# ======================================================
# VALIDACIONES DE CONTROL
# ======================================================

def validar_movimiento_fiscal_dict(movimiento):
    """
    Devuelve alertas de validación para un movimiento fiscal.
    No graba datos.
    """
    alertas = []

    if movimiento is None:
        return [{
            "nivel": "ERROR",
            "titulo": "Movimiento vacío",
            "detalle": "No se recibió información para validar.",
        }]

    tipo = _upper(movimiento.get("tipo_concepto"), "OTRO")
    estado = _upper(movimiento.get("estado"), ESTADO_CONFIRMADO)
    incluido_en_posicion = _bool_int(movimiento.get("incluido_en_posicion"), default=1)

    if estado == ESTADO_CONFIRMADO and not incluido_en_posicion:
        alertas.append({
            "nivel": "INFO",
            "titulo": "Movimiento confirmado no incluido en posición",
            "detalle": (
                "El crédito/control existe y queda trazado, pero no impactará la posición IVA "
                "hasta que se marque como incluido."
            ),
        })

    importes = {
        "iva_debito": _round2(movimiento.get("iva_debito", 0)),
        "credito_fiscal_computable": _round2(movimiento.get("credito_fiscal_computable", 0)),
        "iva_no_computable": _round2(movimiento.get("iva_no_computable", 0)),
        "percepcion_iva": _round2(movimiento.get("percepcion_iva", 0)),
        "retencion_iva": _round2(movimiento.get("retencion_iva", 0)),
        "saldo_tecnico_anterior": _round2(movimiento.get("saldo_tecnico_anterior", 0)),
        "saldo_libre_disponibilidad": _round2(movimiento.get("saldo_libre_disponibilidad", 0)),
        "pago_a_cuenta": _round2(movimiento.get("pago_a_cuenta", 0)),
    }

    if tipo == "IVA_DEBITO" and abs(importes["iva_debito"]) <= 0.01:
        alertas.append({
            "nivel": "ADVERTENCIA",
            "titulo": "Tipo IVA débito sin importe",
            "detalle": "El tipo de concepto es IVA_DEBITO, pero el campo iva_debito está en cero.",
        })

    if tipo == "IVA_CREDITO" and abs(importes["credito_fiscal_computable"]) <= 0.01:
        alertas.append({
            "nivel": "ADVERTENCIA",
            "titulo": "Tipo IVA crédito sin importe",
            "detalle": (
                "El tipo de concepto es IVA_CREDITO, pero el campo "
                "credito_fiscal_computable está en cero."
            ),
        })

    if tipo == "PERCEPCION_IVA" and abs(importes["percepcion_iva"]) <= 0.01:
        alertas.append({
            "nivel": "ADVERTENCIA",
            "titulo": "Percepción IVA sin importe",
            "detalle": "El tipo de concepto es PERCEPCION_IVA, pero percepcion_iva está en cero.",
        })

    if tipo == "RETENCION_IVA" and abs(importes["retencion_iva"]) <= 0.01:
        alertas.append({
            "nivel": "ADVERTENCIA",
            "titulo": "Retención IVA sin importe",
            "detalle": "El tipo de concepto es RETENCION_IVA, pero retencion_iva está en cero.",
        })

    if tipo == "SALDO_TECNICO_ANTERIOR" and abs(importes["saldo_tecnico_anterior"]) <= 0.01:
        alertas.append({
            "nivel": "ADVERTENCIA",
            "titulo": "Saldo técnico anterior sin importe",
            "detalle": (
                "El tipo de concepto es SALDO_TECNICO_ANTERIOR, "
                "pero saldo_tecnico_anterior está en cero."
            ),
        })

    campos_con_importe = [
        campo
        for campo, valor in importes.items()
        if abs(valor) > 0.01
    ]

    if not campos_con_importe:
        alertas.append({
            "nivel": "ADVERTENCIA",
            "titulo": "Movimiento fiscal sin impacto IVA",
            "detalle": (
                "No se detectaron importes fiscales relevantes. "
                "El movimiento puede servir como nota, pero no impactará la posición."
            ),
        })

    if len(campos_con_importe) > 3:
        alertas.append({
            "nivel": "INFO",
            "titulo": "Movimiento con varios impactos fiscales",
            "detalle": (
                "El movimiento tiene varios campos fiscales con importe. "
                "Revisar que no se estén mezclando conceptos que deberían registrarse por separado."
            ),
        })

    return alertas


# ======================================================
# UTILIDADES PARA UI / FUTURA INTEGRACIÓN
# ======================================================

def opciones_origenes():
    return sorted(ORIGENES_VALIDOS)


def opciones_tipos_concepto():
    return sorted(TIPOS_CONCEPTO_VALIDOS)


def opciones_estados():
    return sorted(ESTADOS_VALIDOS)


def formato_moneda(valor):
    valor = _round2(valor)
    return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ======================================================
# API PÚBLICA
# ======================================================

__all__ = [
    "TABLA_MOVIMIENTOS",
    "TABLA_EVENTOS",

    "ESTADO_BORRADOR",
    "ESTADO_CONFIRMADO",
    "ESTADO_ANULADO",
    "ESTADOS_VALIDOS",
    "ORIGENES_VALIDOS",
    "TIPOS_CONCEPTO_VALIDOS",
    "TIPOS_CONCEPTO_IVA_OPERATIVOS",
    "TIPOS_CONCEPTO_SOLO_CONTROL",

    "asegurar_estructura_iva_movimientos_fiscales",
    "estructura_iva_movimientos_fiscales_existe",

    "registrar_movimiento_fiscal",
    "obtener_movimiento_fiscal",
    "listar_movimientos_fiscales",
    "confirmar_movimiento_fiscal",
    "actualizar_inclusion_movimiento_fiscal",
    "anular_movimiento_fiscal",
    "listar_eventos_movimiento",

    "obtener_totales_movimientos_fiscales_periodo",
    "obtener_impacto_posicion_iva_periodo",
    "obtener_resumen_movimientos_fiscales_por_origen",

    "validar_movimiento_fiscal_dict",
    "es_tipo_concepto_iva_operativo",
    "anular_movimientos_banco_sin_grupo_fiscal_activo",

    "opciones_origenes",
    "opciones_tipos_concepto",
    "opciones_estados",
    "formato_moneda",
    "normalizar_duplicados_activos_banco_iva",
]