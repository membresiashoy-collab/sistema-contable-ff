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
# Solo los movimientos CONFIRMADOS deben impactar en la posición IVA.
# BORRADOR no impacta.
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
    origen_tabla="",
    origen_id=None,
    observacion="",
    usuario="",
):
    """
    Registra un movimiento fiscal adicional de IVA.

    Importante:
    - Si estado = CONFIRMADO, impactará en la posición IVA futura.
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

    fecha_confirmacion = _now() if estado == ESTADO_CONFIRMADO else None
    fecha_anulacion = _now() if estado == ESTADO_ANULADO else None

    conn = conectar()

    try:
        cur = conn.cursor()

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
                origen_tabla,
                origen_id,
                observacion,
                usuario,
                fecha_carga,
                fecha_confirmacion,
                fecha_anulacion,
                motivo_anulacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            detalle=f"Movimiento fiscal IVA creado en estado {estado}.",
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
):
    asegurar_estructura_iva_movimientos_fiscales()

    movimiento = obtener_movimiento_fiscal(movimiento_id)

    if movimiento is None:
        raise ValueError("No se encontró el movimiento fiscal IVA a confirmar.")

    if movimiento.get("estado") == ESTADO_ANULADO:
        raise ValueError("No se puede confirmar un movimiento fiscal IVA anulado.")

    if movimiento.get("estado") == ESTADO_CONFIRMADO:
        return movimiento

    conn = conectar()

    try:
        conn.execute(
            """
            UPDATE iva_movimientos_fiscales
            SET
                estado = ?,
                fecha_confirmacion = ?,
                fecha_anulacion = NULL,
                motivo_anulacion = NULL
            WHERE id = ?
            """,
            (
                ESTADO_CONFIRMADO,
                _now(),
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
):
    """
    Devuelve totales de movimientos fiscales adicionales para un período.

    Por defecto:
    - Incluye solo CONFIRMADOS.
    - Excluye BORRADOR.
    - Excluye ANULADO.

    Estos totales luego se integran a services/iva_service.py.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    anio, mes = _validar_periodo(anio, mes)

    estados = [ESTADO_CONFIRMADO]

    if incluir_borradores:
        estados.append(ESTADO_BORRADOR)

    placeholders = ",".join(["?"] * len(estados))

    params = [
        _int(empresa_id, 1),
        anio,
        mes,
        *estados,
    ]

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

    params = [
        _int(empresa_id, 1),
        anio,
        mes,
        *estados,
    ]

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

    "asegurar_estructura_iva_movimientos_fiscales",
    "estructura_iva_movimientos_fiscales_existe",

    "registrar_movimiento_fiscal",
    "obtener_movimiento_fiscal",
    "listar_movimientos_fiscales",
    "confirmar_movimiento_fiscal",
    "anular_movimiento_fiscal",
    "listar_eventos_movimiento",

    "obtener_totales_movimientos_fiscales_periodo",
    "obtener_impacto_posicion_iva_periodo",
    "obtener_resumen_movimientos_fiscales_por_origen",

    "validar_movimiento_fiscal_dict",

    "opciones_origenes",
    "opciones_tipos_concepto",
    "opciones_estados",
    "formato_moneda",
]