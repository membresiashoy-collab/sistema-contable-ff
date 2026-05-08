from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from database import conectar, ejecutar_query

try:
    from services.asientos_origen_service import migrar_asientos_origen
except Exception:  # pragma: no cover - compatibilidad con bases parciales
    migrar_asientos_origen = None

try:
    from services.iva_cierre_service import asegurar_estructura_iva_cierres
except Exception:  # pragma: no cover - compatibilidad con bases parciales
    asegurar_estructura_iva_cierres = None


# ======================================================
# CONTABILIDAD PRO - BANDEJA DE ASIENTOS PROPUESTOS
# ======================================================
#
# Este servicio centraliza el control de asientos propuestos.
#
# Responsabilidad:
# - Leer asientos propuestos centrales:
#   asientos_propuestos + asientos_propuestos_detalle.
# - Leer asientos propuestos de IVA:
#   iva_cierres_asientos_propuestos, agrupados por cierre/pago/tipo.
# - Confirmar pase controlado al Libro Diario.
# - Evitar doble contabilización.
# - Rechazar propuestas pendientes con motivo.
# - Generar reverso controlado de asientos ya contabilizados.
# - Dejar auditoría funcional.
#
# Importante:
# - No toca Ventas, Compras, Banco/Caja, Caja, Cobranzas ni Pagos.
# - No borra asientos del Libro Diario.
# - No reemplaza todavía los módulos viejos que escriben directo al Libro Diario.
#   Esa migración debe hacerse etapa por etapa.
# ======================================================


TABLA_CENTRAL = "asientos_propuestos"
TABLA_CENTRAL_DETALLE = "asientos_propuestos_detalle"
TABLA_CENTRAL_EVENTOS = "asientos_propuestos_eventos"
TABLA_IVA = "iva_cierres_asientos_propuestos"
TABLA_LIBRO = "libro_diario"
TABLA_EVENTOS = "asientos_bandeja_eventos"
TABLA_LOTES = "asientos_bandeja_lotes"

FUENTE_CENTRAL = "CENTRAL"
FUENTE_IVA = "IVA"

ESTADO_PROPUESTO = "PROPUESTO"
ESTADO_CONTABILIZADO = "CONTABILIZADO"
ESTADO_RECHAZADO = "RECHAZADO"
ESTADO_ANULADO = "ANULADO"
ESTADO_REVERSADO = "REVERSADO"

TOLERANCIA_CUADRE = 0.01

COLUMNAS_BANDEJA = [
    "fuente",
    "fuente_id",
    "fuente_clave",
    "empresa_id",
    "ejercicio_id",
    "fecha",
    "anio",
    "mes",
    "periodo",
    "origen",
    "origen_tabla",
    "origen_id",
    "tipo_asiento",
    "referencia",
    "descripcion",
    "estado",
    "total_debe",
    "total_haber",
    "diferencia",
    "id_asiento_libro_diario",
    "id_asiento_reversion_libro_diario",
    "fecha_contabilizacion",
    "fecha_reversion",
    "usuario_contabilizacion",
    "usuario_reversion",
    "fecha_creacion",
]


# ======================================================
# UTILIDADES INTERNAS
# ======================================================

def _resultado(ok: bool, mensaje: str, **extras) -> Dict[str, Any]:
    data = {"ok": bool(ok), "mensaje": str(mensaje)}
    data.update(extras)
    return data


def _texto(valor: Any, default: str = "") -> str:
    try:
        if valor is None:
            return default
        if isinstance(valor, float) and pd.isna(valor):
            return default
        return str(valor).strip()
    except Exception:
        return default


def _int(valor: Any, default: int = 0) -> int:
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        if pd.isna(valor):
            return default
        return int(float(valor))
    except Exception:
        return default


def _float(valor: Any, default: float = 0.0) -> float:
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        if pd.isna(valor):
            return default
        return round(float(valor), 2)
    except Exception:
        return default


def _fecha_iso(valor: Any = None) -> str:
    if valor is None:
        return date.today().isoformat()
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()

    texto = _texto(valor)
    if not texto:
        return date.today().isoformat()

    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except Exception:
        return texto[:10]


def _df(resultado: Any) -> pd.DataFrame:
    if isinstance(resultado, pd.DataFrame):
        return resultado.copy()
    if resultado is None:
        return pd.DataFrame()
    try:
        return pd.DataFrame(resultado)
    except Exception:
        return pd.DataFrame()


def _df_a_dict(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if df is None or df.empty:
        return None

    fila = df.iloc[0].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in fila.items()}


def _tabla_existe(conn, tabla: str) -> bool:
    try:
        fila = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            LIMIT 1
            """,
            (tabla,),
        ).fetchone()
        return fila is not None
    except Exception:
        return False


def _columnas_tabla(conn, tabla: str) -> set:
    try:
        filas = conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        return {fila[1] for fila in filas}
    except Exception:
        return set()


def _agregar_columna_si_no_existe(conn, tabla: str, columna: str, definicion: str) -> None:
    if not _tabla_existe(conn, tabla):
        return

    columnas = _columnas_tabla(conn, tabla)
    if columna not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _sql_migracion_bandeja() -> str:
    ruta = Path(__file__).resolve().parents[1] / "migrations" / "017_bandeja_asientos_propuestos.sql"

    if ruta.exists():
        return ruta.read_text(encoding="utf-8")

    return _sql_tabla_eventos_bandeja()


def _sql_tabla_eventos_bandeja() -> str:
    """
    SQL mínimo indispensable para que la bandeja pueda auditar decisiones.

    Se mantiene dentro del servicio además de la migración externa porque:
    - en tests se trabaja con bases temporales;
    - una migración incompleta no debe dejar inutilizable el módulo;
    - el inicializador del servicio debe ser idempotente y autosuficiente.
    """
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLA_EVENTOS} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL DEFAULT 1,
        fuente TEXT NOT NULL,
        fuente_id INTEGER,
        fuente_clave TEXT NOT NULL,
        evento TEXT NOT NULL,
        detalle TEXT,
        usuario TEXT,
        fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """


def _asegurar_tabla_eventos_bandeja_conn(conn) -> None:
    """
    Crea explícitamente la tabla de eventos aunque el archivo de migración 017
    esté vacío, incompleto o no haya sido aplicado todavía.

    Esta es una defensa de origen: los índices y la auditoría nunca deben
    depender de que un archivo externo se haya pegado perfecto.
    """
    conn.executescript(_sql_tabla_eventos_bandeja())


def _sql_tabla_lotes_bandeja() -> str:
    """
    Tabla de lotes de contabilización masiva.

    No reemplaza los eventos por asiento. Agrega trazabilidad de la operación
    grupal para que el usuario pueda auditar qué se contabilizó junto.
    """
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLA_LOTES} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL DEFAULT 1,
        accion TEXT NOT NULL,
        estado TEXT NOT NULL,
        cantidad_solicitada INTEGER NOT NULL DEFAULT 0,
        cantidad_procesada INTEGER NOT NULL DEFAULT 0,
        cantidad_error INTEGER NOT NULL DEFAULT 0,
        total_debe REAL NOT NULL DEFAULT 0,
        total_haber REAL NOT NULL DEFAULT 0,
        diferencia REAL NOT NULL DEFAULT 0,
        detalle TEXT,
        usuario TEXT,
        fecha_lote TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """


def _asegurar_tabla_lotes_bandeja_conn(conn) -> None:
    conn.executescript(_sql_tabla_lotes_bandeja())


# ======================================================
# MIGRACIÓN / ESTRUCTURA
# ======================================================

def asegurar_estructura_bandeja_asientos() -> None:
    """
    Asegura la estructura necesaria para operar la bandeja.

    No borra datos.
    No migra datos existentes a otra tabla.
    Solo crea auditoría propia y agrega columnas seguras de trazabilidad
    en las fuentes de asientos propuestos ya existentes.
    """

    if migrar_asientos_origen is not None:
        migrar_asientos_origen()

    if asegurar_estructura_iva_cierres is not None:
        asegurar_estructura_iva_cierres()

    conn = conectar()

    try:
        conn.executescript(_sql_migracion_bandeja())
        _asegurar_tabla_eventos_bandeja_conn(conn)
        _asegurar_tabla_lotes_bandeja_conn(conn)

        # Trazabilidad adicional en asientos_propuestos.
        _agregar_columna_si_no_existe(conn, TABLA_CENTRAL, "id_asiento_reversion_libro_diario", "INTEGER")
        _agregar_columna_si_no_existe(conn, TABLA_CENTRAL, "fecha_reversion", "TIMESTAMP")
        _agregar_columna_si_no_existe(conn, TABLA_CENTRAL, "usuario_reversion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_CENTRAL, "motivo_reversion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_CENTRAL, "lote_contabilizacion_id", "INTEGER")
        _agregar_columna_si_no_existe(conn, TABLA_CENTRAL, "lote_reversion_id", "INTEGER")

        # Trazabilidad adicional en IVA, que hoy guarda líneas sueltas.
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "id_asiento_libro_diario", "INTEGER")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "fecha_contabilizacion", "TIMESTAMP")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "usuario_contabilizacion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "motivo_anulacion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "usuario_anulacion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "fecha_anulacion", "TIMESTAMP")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "id_asiento_reversion_libro_diario", "INTEGER")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "fecha_reversion", "TIMESTAMP")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "usuario_reversion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "motivo_reversion", "TEXT")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "fecha_actualizacion", "TIMESTAMP")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "lote_contabilizacion_id", "INTEGER")
        _agregar_columna_si_no_existe(conn, TABLA_IVA, "lote_reversion_id", "INTEGER")

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bandeja_iva_estado
            ON {TABLA_IVA} (empresa_id, estado)
            """
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bandeja_iva_grupo
            ON {TABLA_IVA} (empresa_id, cierre_id, pago_id, tipo_asiento)
            """
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bandeja_eventos_clave
            ON {TABLA_EVENTOS} (fuente, fuente_clave, fecha_evento)
            """
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bandeja_eventos_empresa
            ON {TABLA_EVENTOS} (empresa_id, fecha_evento)
            """
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bandeja_lotes_empresa
            ON {TABLA_LOTES} (empresa_id, fecha_lote)
            """
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bandeja_lotes_estado
            ON {TABLA_LOTES} (empresa_id, estado, accion)
            """
        )

        conn.commit()

    finally:
        conn.close()


# ======================================================
# EVENTOS / AUDITORÍA
# ======================================================

def _registrar_evento_bandeja(
    conn,
    *,
    empresa_id: int,
    fuente: str,
    fuente_id: Optional[int],
    fuente_clave: str,
    evento: str,
    detalle: str = "",
    usuario: Optional[str] = None,
) -> None:
    conn.execute(
        f"""
        INSERT INTO {TABLA_EVENTOS}
        (empresa_id, fuente, fuente_id, fuente_clave, evento, detalle, usuario, fecha_evento)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(empresa_id),
            _texto(fuente),
            fuente_id,
            _texto(fuente_clave),
            _texto(evento),
            _texto(detalle),
            _texto(usuario),
        ),
    )


def _registrar_evento_central(
    conn,
    asiento_propuesto_id: int,
    empresa_id: int,
    evento: str,
    detalle: str = "",
    usuario: Optional[str] = None,
) -> None:
    if not _tabla_existe(conn, TABLA_CENTRAL_EVENTOS):
        return

    conn.execute(
        f"""
        INSERT INTO {TABLA_CENTRAL_EVENTOS}
        (asiento_propuesto_id, empresa_id, evento, detalle, usuario, fecha_evento)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(asiento_propuesto_id),
            int(empresa_id),
            _texto(evento),
            _texto(detalle),
            _texto(usuario),
        ),
    )


# ======================================================
# CLAVES / NORMALIZACIÓN
# ======================================================

def _normalizar_estado(valor: Any) -> str:
    return _texto(valor, ESTADO_PROPUESTO).upper()


def _normalizar_origen_iva(pago_id: Any, tipo_asiento: Any) -> str:
    tipo = _texto(tipo_asiento).upper()

    if _int(pago_id) > 0 or "PAGO" in tipo:
        return "IVA_PAGO"

    return "IVA_CIERRE"


def _clave_central(asiento_id: int) -> str:
    return f"{FUENTE_CENTRAL}:{int(asiento_id)}"


def _clave_iva(cierre_id: int, pago_id: Any, tipo_asiento: str) -> str:
    pago = _int(pago_id)
    return f"{FUENTE_IVA}:{int(cierre_id)}:{pago}:{_texto(tipo_asiento).upper()}"


def parsear_fuente_clave(fuente_clave: str) -> Dict[str, Any]:
    texto = _texto(fuente_clave)
    partes = texto.split(":")

    if len(partes) == 2 and partes[0].upper() == FUENTE_CENTRAL:
        return {
            "ok": True,
            "fuente": FUENTE_CENTRAL,
            "asiento_id": _int(partes[1]),
            "fuente_clave": texto,
        }

    if len(partes) >= 4 and partes[0].upper() == FUENTE_IVA:
        return {
            "ok": True,
            "fuente": FUENTE_IVA,
            "cierre_id": _int(partes[1]),
            "pago_id": _int(partes[2]),
            "tipo_asiento": ":".join(partes[3:]).upper(),
            "fuente_clave": texto,
        }

    return {
        "ok": False,
        "mensaje": "Clave de asiento propuesto inválida.",
        "fuente_clave": texto,
    }


def _asegurar_columnas_bandeja(df: pd.DataFrame) -> pd.DataFrame:
    df = _df(df)

    for col in COLUMNAS_BANDEJA:
        if col in df.columns:
            continue

        if col in {
            "fuente_id",
            "empresa_id",
            "ejercicio_id",
            "anio",
            "mes",
            "origen_id",
            "id_asiento_libro_diario",
            "id_asiento_reversion_libro_diario",
        }:
            df[col] = None
        elif col in {"total_debe", "total_haber", "diferencia"}:
            df[col] = 0.0
        else:
            df[col] = ""

    return df[COLUMNAS_BANDEJA].copy()


# ======================================================
# LISTADOS DE BANDEJA
# ======================================================

def _listar_centrales(empresa_id: int) -> pd.DataFrame:
    conn = conectar()

    try:
        if not _tabla_existe(conn, TABLA_CENTRAL):
            return pd.DataFrame(columns=COLUMNAS_BANDEJA)
    finally:
        conn.close()

    df = ejecutar_query(
        f"""
        SELECT
            '{FUENTE_CENTRAL}' AS fuente,
            id AS fuente_id,
            '{FUENTE_CENTRAL}:' || id AS fuente_clave,
            empresa_id,
            ejercicio_id,
            fecha,
            NULL AS anio,
            NULL AS mes,
            '' AS periodo,
            origen,
            origen_tabla,
            origen_id,
            tipo_asiento,
            referencia,
            descripcion,
            estado,
            total_debe,
            total_haber,
            diferencia,
            id_asiento_libro_diario,
            id_asiento_reversion_libro_diario,
            fecha_contabilizacion,
            fecha_reversion,
            usuario_contabilizacion,
            usuario_reversion,
            fecha_creacion
        FROM {TABLA_CENTRAL}
        WHERE empresa_id = ?
        """,
        (int(empresa_id),),
        fetch=True,
    )

    return _asegurar_columnas_bandeja(df)


def _listar_iva(empresa_id: int) -> pd.DataFrame:
    conn = conectar()

    try:
        if not _tabla_existe(conn, TABLA_IVA):
            return pd.DataFrame(columns=COLUMNAS_BANDEJA)
    finally:
        conn.close()

    df = ejecutar_query(
        f"""
        SELECT
            '{FUENTE_IVA}' AS fuente,
            MIN(id) AS fuente_id,
            '{FUENTE_IVA}:' || cierre_id || ':' || COALESCE(pago_id, 0) || ':' || UPPER(tipo_asiento) AS fuente_clave,
            empresa_id,
            NULL AS ejercicio_id,
            MIN(fecha) AS fecha,
            anio,
            mes,
            periodo,
            CASE
                WHEN COALESCE(pago_id, 0) > 0 OR UPPER(tipo_asiento) LIKE '%PAGO%' THEN 'IVA_PAGO'
                ELSE 'IVA_CIERRE'
            END AS origen,
            '{TABLA_IVA}' AS origen_tabla,
            cierre_id AS origen_id,
            tipo_asiento,
            CASE
                WHEN COALESCE(pago_id, 0) > 0 THEN 'Pago IVA #' || pago_id
                ELSE 'Cierre IVA #' || cierre_id
            END AS referencia,
            CASE
                WHEN COALESCE(pago_id, 0) > 0 THEN 'Pago IVA período ' || periodo
                ELSE 'Liquidación / ajuste IVA período ' || periodo
            END AS descripcion,
            CASE
                WHEN COUNT(DISTINCT estado) = 1 THEN MAX(estado)
                WHEN SUM(CASE WHEN estado = '{ESTADO_PROPUESTO}' THEN 1 ELSE 0 END) > 0 THEN '{ESTADO_PROPUESTO}'
                ELSE 'MIXTO'
            END AS estado,
            ROUND(SUM(COALESCE(debe, 0)), 2) AS total_debe,
            ROUND(SUM(COALESCE(haber, 0)), 2) AS total_haber,
            ROUND(SUM(COALESCE(debe, 0)) - SUM(COALESCE(haber, 0)), 2) AS diferencia,
            MAX(id_asiento_libro_diario) AS id_asiento_libro_diario,
            MAX(id_asiento_reversion_libro_diario) AS id_asiento_reversion_libro_diario,
            MAX(fecha_contabilizacion) AS fecha_contabilizacion,
            MAX(fecha_reversion) AS fecha_reversion,
            MAX(usuario_contabilizacion) AS usuario_contabilizacion,
            MAX(usuario_reversion) AS usuario_reversion,
            MIN(fecha_carga) AS fecha_creacion
        FROM {TABLA_IVA}
        WHERE empresa_id = ?
        GROUP BY empresa_id, cierre_id, COALESCE(pago_id, 0), anio, mes, periodo, tipo_asiento
        """,
        (int(empresa_id),),
        fetch=True,
    )

    return _asegurar_columnas_bandeja(df)


def listar_bandeja_asientos_propuestos(
    empresa_id: int = 1,
    estado: Optional[str] = None,
    origen: Optional[str] = None,
    fuente: Optional[str] = None,
    incluir_anulados: bool = False,
) -> pd.DataFrame:
    asegurar_estructura_bandeja_asientos()

    partes = [
        _listar_centrales(empresa_id),
        _listar_iva(empresa_id),
    ]

    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUMNAS_BANDEJA)
    df = _asegurar_columnas_bandeja(df)

    if df.empty:
        return df

    df["estado"] = df["estado"].fillna("").astype(str).str.upper()
    df["origen"] = df["origen"].fillna("").astype(str).str.upper()
    df["fuente"] = df["fuente"].fillna("").astype(str).str.upper()

    if estado:
        df = df[df["estado"] == _texto(estado).upper()].copy()
    elif not incluir_anulados:
        df = df[~df["estado"].isin([ESTADO_ANULADO, ESTADO_RECHAZADO])].copy()

    if origen:
        df = df[df["origen"] == _texto(origen).upper()].copy()

    if fuente:
        df = df[df["fuente"] == _texto(fuente).upper()].copy()

    for col in ["total_debe", "total_haber", "diferencia"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).round(2)

    return df.sort_values(
        ["fecha", "fuente", "fuente_id"],
        ascending=[False, True, False],
    ).reset_index(drop=True)


def obtener_resumen_bandeja_asientos(empresa_id: int = 1) -> Dict[str, Any]:
    df = listar_bandeja_asientos_propuestos(
        empresa_id=empresa_id,
        incluir_anulados=True,
    )

    def contar(estado: str) -> int:
        if df.empty:
            return 0
        return int((df["estado"].fillna("").astype(str).str.upper() == estado).sum())

    pendientes = contar(ESTADO_PROPUESTO)

    return {
        "empresa_id": int(empresa_id),
        "total": int(len(df)) if not df.empty else 0,
        "pendientes": pendientes,
        "contabilizados": contar(ESTADO_CONTABILIZADO),
        "rechazados": contar(ESTADO_RECHAZADO),
        "anulados": contar(ESTADO_ANULADO),
        "reversados": contar(ESTADO_REVERSADO),
        "importe_pendiente_debe": round(float(df.loc[df["estado"] == ESTADO_PROPUESTO, "total_debe"].sum()), 2) if not df.empty else 0.0,
        "importe_pendiente_haber": round(float(df.loc[df["estado"] == ESTADO_PROPUESTO, "total_haber"].sum()), 2) if not df.empty else 0.0,
    }


# ======================================================
# OBTENER ASIENTO INDIVIDUAL
# ======================================================

def _obtener_central(asiento_id: int) -> Optional[Dict[str, Any]]:
    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_CENTRAL}
        WHERE id = ?
        """,
        (int(asiento_id),),
        fetch=True,
    )

    cabecera = _df_a_dict(df)

    if not cabecera:
        return None

    detalle = ejecutar_query(
        f"""
        SELECT
            renglon,
            cuenta_codigo,
            cuenta_nombre,
            debe,
            haber,
            glosa
        FROM {TABLA_CENTRAL_DETALLE}
        WHERE asiento_propuesto_id = ?
        ORDER BY renglon
        """,
        (int(asiento_id),),
        fetch=True,
    )

    detalle = _df(detalle)

    cabecera["fuente"] = FUENTE_CENTRAL
    cabecera["fuente_id"] = int(asiento_id)
    cabecera["fuente_clave"] = _clave_central(asiento_id)
    cabecera["detalle"] = detalle.to_dict("records") if not detalle.empty else []
    cabecera["anio"] = None
    cabecera["mes"] = None
    cabecera["periodo"] = ""

    return cabecera


def _obtener_iva(cierre_id: int, pago_id: int, tipo_asiento: str) -> Optional[Dict[str, Any]]:
    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_IVA}
        WHERE cierre_id = ?
          AND COALESCE(pago_id, 0) = ?
          AND UPPER(tipo_asiento) = ?
        ORDER BY id
        """,
        (int(cierre_id), int(pago_id), _texto(tipo_asiento).upper()),
        fetch=True,
    )

    df = _df(df)

    if df.empty:
        return None

    primera = df.iloc[0].to_dict()

    total_debe = round(float(pd.to_numeric(df["debe"], errors="coerce").fillna(0.0).sum()), 2)
    total_haber = round(float(pd.to_numeric(df["haber"], errors="coerce").fillna(0.0).sum()), 2)

    estados = df["estado"].fillna("").astype(str).str.upper().unique().tolist()
    estado = estados[0] if len(estados) == 1 else (ESTADO_PROPUESTO if ESTADO_PROPUESTO in estados else "MIXTO")

    origen = _normalizar_origen_iva(pago_id, tipo_asiento)
    periodo = _texto(primera.get("periodo"))

    detalle = []

    for idx, row in df.reset_index(drop=True).iterrows():
        detalle.append({
            "renglon": idx + 1,
            "cuenta_codigo": _texto(row.get("cuenta_codigo")),
            "cuenta_nombre": _texto(row.get("cuenta_nombre")),
            "debe": _float(row.get("debe")),
            "haber": _float(row.get("haber")),
            "glosa": _texto(row.get("glosa")),
        })

    clave = _clave_iva(cierre_id, pago_id, tipo_asiento)

    return {
        "id": int(primera.get("id")),
        "fuente": FUENTE_IVA,
        "fuente_id": int(primera.get("id")),
        "fuente_clave": clave,
        "empresa_id": _int(primera.get("empresa_id"), 1),
        "ejercicio_id": None,
        "fecha": _texto(primera.get("fecha")),
        "anio": _int(primera.get("anio")),
        "mes": _int(primera.get("mes")),
        "periodo": periodo,
        "origen": origen,
        "origen_tabla": TABLA_IVA,
        "origen_id": int(cierre_id),
        "tipo_asiento": _texto(tipo_asiento).upper(),
        "referencia": f"{'Pago' if origen == 'IVA_PAGO' else 'Cierre'} IVA #{pago_id if origen == 'IVA_PAGO' else cierre_id}",
        "descripcion": f"{'Pago IVA' if origen == 'IVA_PAGO' else 'Liquidación / ajuste IVA'} período {periodo}",
        "estado": estado,
        "total_debe": total_debe,
        "total_haber": total_haber,
        "diferencia": round(total_debe - total_haber, 2),
        "id_asiento_libro_diario": _int(primera.get("id_asiento_libro_diario"), 0) or None,
        "id_asiento_reversion_libro_diario": _int(primera.get("id_asiento_reversion_libro_diario"), 0) or None,
        "fecha_contabilizacion": primera.get("fecha_contabilizacion"),
        "fecha_reversion": primera.get("fecha_reversion"),
        "usuario_contabilizacion": primera.get("usuario_contabilizacion"),
        "usuario_reversion": primera.get("usuario_reversion"),
        "detalle": detalle,
        "cierre_id": int(cierre_id),
        "pago_id": int(pago_id),
    }


def obtener_asiento_bandeja(fuente_clave: str) -> Optional[Dict[str, Any]]:
    asegurar_estructura_bandeja_asientos()

    parsed = parsear_fuente_clave(fuente_clave)

    if not parsed.get("ok"):
        return None

    if parsed["fuente"] == FUENTE_CENTRAL:
        return _obtener_central(parsed["asiento_id"])

    if parsed["fuente"] == FUENTE_IVA:
        return _obtener_iva(
            parsed["cierre_id"],
            parsed["pago_id"],
            parsed["tipo_asiento"],
        )

    return None


def listar_eventos_bandeja(fuente_clave: str) -> pd.DataFrame:
    asegurar_estructura_bandeja_asientos()

    parsed = parsear_fuente_clave(fuente_clave)

    if not parsed.get("ok"):
        return pd.DataFrame()

    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_EVENTOS}
        WHERE fuente_clave = ?
        ORDER BY fecha_evento DESC, id DESC
        """,
        (_texto(fuente_clave),),
        fetch=True,
    )

    return _df(df)


# ======================================================
# VALIDACIÓN CONTABLE
# ======================================================

def _validar_asiento_para_contabilizar(asiento: Dict[str, Any]) -> Dict[str, Any]:
    if not asiento:
        return _resultado(False, "No se encontró el asiento propuesto.")

    estado = _normalizar_estado(asiento.get("estado"))

    if estado != ESTADO_PROPUESTO:
        return _resultado(
            False,
            f"Solo se pueden contabilizar asientos en estado {ESTADO_PROPUESTO}. Estado actual: {estado}.",
        )

    detalle = list(asiento.get("detalle") or [])

    if len(detalle) < 2:
        return _resultado(False, "El asiento debe tener al menos dos líneas.")

    total_debe = round(sum(_float(linea.get("debe")) for linea in detalle), 2)
    total_haber = round(sum(_float(linea.get("haber")) for linea in detalle), 2)
    diferencia = round(total_debe - total_haber, 2)

    if abs(diferencia) > TOLERANCIA_CUADRE:
        return _resultado(
            False,
            "El asiento no está cuadrado.",
            total_debe=total_debe,
            total_haber=total_haber,
            diferencia=diferencia,
        )

    for idx, linea in enumerate(detalle, start=1):
        cuenta = _texto(linea.get("cuenta_nombre") or linea.get("cuenta_codigo"))
        debe = _float(linea.get("debe"))
        haber = _float(linea.get("haber"))

        if not cuenta:
            return _resultado(False, f"La línea {idx} no tiene cuenta contable.")
        if debe < 0 or haber < 0:
            return _resultado(False, f"La línea {idx} tiene importes negativos.")
        if debe > 0 and haber > 0:
            return _resultado(False, f"La línea {idx} no puede tener Debe y Haber simultáneamente.")
        if debe == 0 and haber == 0:
            return _resultado(False, f"La línea {idx} no tiene importe.")

    return _resultado(
        True,
        "Asiento válido.",
        total_debe=total_debe,
        total_haber=total_haber,
        diferencia=diferencia,
    )


# ======================================================
# LIBRO DIARIO
# ======================================================

def _proximo_id_asiento_conn(conn) -> int:
    fila = conn.execute(
        f"""
        SELECT COALESCE(MAX(id_asiento), 0) + 1
        FROM {TABLA_LIBRO}
        """
    ).fetchone()

    return int(fila[0] or 1)


def _insertar_linea_libro(
    conn,
    *,
    id_asiento: int,
    empresa_id: int,
    fecha: str,
    cuenta: str,
    debe: float,
    haber: float,
    glosa: str,
    origen: str,
    origen_tabla: str,
    origen_id: Optional[int],
    comprobante_clave: str,
    usuario: Optional[str],
) -> None:
    columnas_disponibles = _columnas_tabla(conn, TABLA_LIBRO)

    valores = {
        "id_asiento": int(id_asiento),
        "fecha": _fecha_iso(fecha),
        "cuenta": _texto(cuenta),
        "debe": _float(debe),
        "haber": _float(haber),
        "glosa": _texto(glosa),
        "origen": _texto(origen),
        "archivo": None,
        "empresa_id": int(empresa_id),
        "origen_tabla": _texto(origen_tabla),
        "origen_id": int(origen_id) if origen_id is not None else None,
        "comprobante_clave": _texto(comprobante_clave),
        "estado": ESTADO_CONTABILIZADO,
        "usuario_creacion": _texto(usuario),
        "fecha_creacion": datetime.now().isoformat(timespec="seconds"),
    }

    columnas = [col for col in valores if col in columnas_disponibles]
    placeholders = ", ".join(["?"] * len(columnas))

    sql = f"""
        INSERT INTO {TABLA_LIBRO}
        ({', '.join(columnas)})
        VALUES ({placeholders})
    """

    conn.execute(sql, tuple(valores[col] for col in columnas))


def _insertar_asiento_en_libro(conn, asiento: Dict[str, Any], usuario: Optional[str], reverso: bool = False) -> int:
    id_asiento = _proximo_id_asiento_conn(conn)

    empresa_id = _int(asiento.get("empresa_id"), 1)
    fuente_clave = _texto(asiento.get("fuente_clave"))
    origen_base = _texto(asiento.get("origen"), "ASIENTO_PROPUESTO").upper()
    origen = f"REVERSO_{origen_base}" if reverso else origen_base
    origen_tabla = _texto(asiento.get("origen_tabla"), TABLA_CENTRAL)
    origen_id = _int(asiento.get("origen_id") or asiento.get("fuente_id"))
    fecha = _fecha_iso(asiento.get("fecha"))

    for linea in asiento.get("detalle") or []:
        cuenta_codigo = _texto(linea.get("cuenta_codigo"))
        cuenta_nombre = _texto(linea.get("cuenta_nombre"))
        cuenta = cuenta_nombre or cuenta_codigo
        glosa_base = _texto(linea.get("glosa") or asiento.get("descripcion"))
        glosa = f"REVERSO - {glosa_base}" if reverso else glosa_base

        debe_original = _float(linea.get("debe"))
        haber_original = _float(linea.get("haber"))

        debe = haber_original if reverso else debe_original
        haber = debe_original if reverso else haber_original

        _insertar_linea_libro(
            conn,
            id_asiento=id_asiento,
            empresa_id=empresa_id,
            fecha=fecha,
            cuenta=cuenta,
            debe=debe,
            haber=haber,
            glosa=glosa,
            origen=origen,
            origen_tabla=origen_tabla,
            origen_id=origen_id,
            comprobante_clave=f"REVERSO:{fuente_clave}" if reverso else fuente_clave,
            usuario=usuario,
        )

    return id_asiento


# ======================================================
# ACTUALIZACIÓN DE FUENTES
# ======================================================

def _actualizar_central_contabilizado(conn, asiento: Dict[str, Any], id_asiento: int, usuario: Optional[str], lote_id: Optional[int] = None) -> None:
    asiento_id = _int(asiento.get("id") or asiento.get("fuente_id"))
    empresa_id = _int(asiento.get("empresa_id"), 1)

    cur = conn.execute(
        f"""
        UPDATE {TABLA_CENTRAL}
        SET estado = ?,
            id_asiento_libro_diario = ?,
            fecha_contabilizacion = CURRENT_TIMESTAMP,
            usuario_contabilizacion = ?,
            lote_contabilizacion_id = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE id = ?
          AND empresa_id = ?
          AND estado = ?
        """,
        (
            ESTADO_CONTABILIZADO,
            int(id_asiento),
            _texto(usuario),
            lote_id,
            asiento_id,
            empresa_id,
            ESTADO_PROPUESTO,
        ),
    )

    if cur.rowcount != 1:
        raise ValueError("El asiento central ya no está pendiente. No se contabilizó para evitar duplicados.")

    if _texto(asiento.get("origen_tabla")) == "asientos_origen" and _int(asiento.get("origen_id")) > 0:
        conn.execute(
            """
            UPDATE asientos_origen
            SET estado = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
              AND empresa_id = ?
              AND estado = ?
            """,
            (
                ESTADO_CONTABILIZADO,
                _int(asiento.get("origen_id")),
                empresa_id,
                ESTADO_PROPUESTO,
            ),
        )

    _registrar_evento_central(
        conn,
        asiento_id,
        empresa_id,
        "CONTABILIZACION",
        f"Asiento pasado a Libro Diario con id_asiento {id_asiento}.",
        usuario,
    )


def _actualizar_iva_contabilizado(conn, asiento: Dict[str, Any], id_asiento: int, usuario: Optional[str], lote_id: Optional[int] = None) -> None:
    cierre_id = _int(asiento.get("cierre_id") or asiento.get("origen_id"))
    pago_id = _int(asiento.get("pago_id"))
    tipo_asiento = _texto(asiento.get("tipo_asiento")).upper()
    empresa_id = _int(asiento.get("empresa_id"), 1)

    cur = conn.execute(
        f"""
        UPDATE {TABLA_IVA}
        SET estado = ?,
            id_asiento_libro_diario = ?,
            fecha_contabilizacion = CURRENT_TIMESTAMP,
            usuario_contabilizacion = ?,
            lote_contabilizacion_id = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE empresa_id = ?
          AND cierre_id = ?
          AND COALESCE(pago_id, 0) = ?
          AND UPPER(tipo_asiento) = ?
          AND estado = ?
        """,
        (
            ESTADO_CONTABILIZADO,
            int(id_asiento),
            _texto(usuario),
            lote_id,
            empresa_id,
            cierre_id,
            pago_id,
            tipo_asiento,
            ESTADO_PROPUESTO,
        ),
    )

    if cur.rowcount <= 0:
        raise ValueError("El asiento IVA ya no está pendiente. No se contabilizó para evitar duplicados.")


# ======================================================
# OPERACIONES PRINCIPALES
# ======================================================

def contabilizar_asiento_bandeja(fuente_clave: str, usuario: Optional[str] = "sistema") -> Dict[str, Any]:
    asegurar_estructura_bandeja_asientos()

    asiento = obtener_asiento_bandeja(fuente_clave)
    validacion = _validar_asiento_para_contabilizar(asiento)

    if not validacion["ok"]:
        return validacion

    conn = conectar()

    try:
        conn.execute("BEGIN IMMEDIATE")

        id_asiento = _insertar_asiento_en_libro(
            conn,
            asiento,
            usuario,
            reverso=False,
        )

        fuente = _texto(asiento.get("fuente")).upper()

        if fuente == FUENTE_CENTRAL:
            _actualizar_central_contabilizado(conn, asiento, id_asiento, usuario)
        elif fuente == FUENTE_IVA:
            _actualizar_iva_contabilizado(conn, asiento, id_asiento, usuario)
        else:
            raise ValueError("Fuente de asiento no soportada.")

        _registrar_evento_bandeja(
            conn,
            empresa_id=_int(asiento.get("empresa_id"), 1),
            fuente=fuente,
            fuente_id=_int(asiento.get("fuente_id")),
            fuente_clave=_texto(asiento.get("fuente_clave")),
            evento="CONTABILIZACION",
            detalle=f"Asiento pasado a Libro Diario con id_asiento {id_asiento}.",
            usuario=usuario,
        )

        conn.commit()

        return _resultado(
            True,
            "Asiento contabilizado correctamente.",
            id_asiento=id_asiento,
            fuente_clave=fuente_clave,
        )

    except Exception as exc:
        conn.rollback()
        return _resultado(
            False,
            f"No se pudo contabilizar el asiento: {exc}",
            fuente_clave=fuente_clave,
        )

    finally:
        conn.close()


def rechazar_asiento_bandeja(fuente_clave: str, motivo: str, usuario: Optional[str] = "sistema") -> Dict[str, Any]:
    asegurar_estructura_bandeja_asientos()

    motivo_limpio = _texto(motivo)

    if not motivo_limpio:
        return _resultado(False, "Para rechazar un asiento propuesto se requiere motivo.")

    asiento = obtener_asiento_bandeja(fuente_clave)

    if not asiento:
        return _resultado(False, "No se encontró el asiento propuesto.")

    if _normalizar_estado(asiento.get("estado")) != ESTADO_PROPUESTO:
        return _resultado(False, "Solo se pueden rechazar asientos pendientes.")

    conn = conectar()

    try:
        conn.execute("BEGIN IMMEDIATE")

        fuente = _texto(asiento.get("fuente")).upper()
        empresa_id = _int(asiento.get("empresa_id"), 1)

        if fuente == FUENTE_CENTRAL:
            asiento_id = _int(asiento.get("id") or asiento.get("fuente_id"))

            cur = conn.execute(
                f"""
                UPDATE {TABLA_CENTRAL}
                SET estado = ?,
                    usuario_anulacion = ?,
                    fecha_anulacion = CURRENT_TIMESTAMP,
                    motivo_anulacion = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND empresa_id = ?
                  AND estado = ?
                """,
                (
                    ESTADO_RECHAZADO,
                    _texto(usuario),
                    motivo_limpio,
                    asiento_id,
                    empresa_id,
                    ESTADO_PROPUESTO,
                ),
            )

            if cur.rowcount != 1:
                raise ValueError("El asiento ya no está pendiente.")

            _registrar_evento_central(
                conn,
                asiento_id,
                empresa_id,
                "RECHAZO",
                f"Motivo: {motivo_limpio}",
                usuario,
            )

        elif fuente == FUENTE_IVA:
            cierre_id = _int(asiento.get("cierre_id") or asiento.get("origen_id"))
            pago_id = _int(asiento.get("pago_id"))
            tipo_asiento = _texto(asiento.get("tipo_asiento")).upper()

            cur = conn.execute(
                f"""
                UPDATE {TABLA_IVA}
                SET estado = ?,
                    usuario_anulacion = ?,
                    fecha_anulacion = CURRENT_TIMESTAMP,
                    motivo_anulacion = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE empresa_id = ?
                  AND cierre_id = ?
                  AND COALESCE(pago_id, 0) = ?
                  AND UPPER(tipo_asiento) = ?
                  AND estado = ?
                """,
                (
                    ESTADO_RECHAZADO,
                    _texto(usuario),
                    motivo_limpio,
                    empresa_id,
                    cierre_id,
                    pago_id,
                    tipo_asiento,
                    ESTADO_PROPUESTO,
                ),
            )

            if cur.rowcount <= 0:
                raise ValueError("El asiento IVA ya no está pendiente.")

        else:
            raise ValueError("Fuente de asiento no soportada.")

        _registrar_evento_bandeja(
            conn,
            empresa_id=empresa_id,
            fuente=fuente,
            fuente_id=_int(asiento.get("fuente_id")),
            fuente_clave=_texto(asiento.get("fuente_clave")),
            evento="RECHAZO",
            detalle=f"Motivo: {motivo_limpio}",
            usuario=usuario,
        )

        conn.commit()

        return _resultado(
            True,
            "Asiento rechazado correctamente.",
            fuente_clave=fuente_clave,
        )

    except Exception as exc:
        conn.rollback()
        return _resultado(
            False,
            f"No se pudo rechazar el asiento: {exc}",
            fuente_clave=fuente_clave,
        )

    finally:
        conn.close()


def reversar_asiento_bandeja(
    fuente_clave: str,
    motivo: str,
    usuario: Optional[str] = "sistema",
    fecha_reversion: Optional[Any] = None,
) -> Dict[str, Any]:
    asegurar_estructura_bandeja_asientos()

    motivo_limpio = _texto(motivo)

    if not motivo_limpio:
        return _resultado(False, "Para reversar un asiento contabilizado se requiere motivo.")

    asiento = obtener_asiento_bandeja(fuente_clave)

    if not asiento:
        return _resultado(False, "No se encontró el asiento.")

    if _normalizar_estado(asiento.get("estado")) != ESTADO_CONTABILIZADO:
        return _resultado(False, "Solo se pueden reversar asientos contabilizados.")

    if _int(asiento.get("id_asiento_reversion_libro_diario")) > 0:
        return _resultado(False, "El asiento ya tiene reverso registrado.")

    if fecha_reversion is not None:
        asiento["fecha"] = _fecha_iso(fecha_reversion)

    conn = conectar()

    try:
        conn.execute("BEGIN IMMEDIATE")

        id_reverso = _insertar_asiento_en_libro(
            conn,
            asiento,
            usuario,
            reverso=True,
        )

        fuente = _texto(asiento.get("fuente")).upper()
        empresa_id = _int(asiento.get("empresa_id"), 1)

        if fuente == FUENTE_CENTRAL:
            asiento_id = _int(asiento.get("id") or asiento.get("fuente_id"))

            cur = conn.execute(
                f"""
                UPDATE {TABLA_CENTRAL}
                SET estado = ?,
                    id_asiento_reversion_libro_diario = ?,
                    fecha_reversion = CURRENT_TIMESTAMP,
                    usuario_reversion = ?,
                    motivo_reversion = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND empresa_id = ?
                  AND estado = ?
                  AND COALESCE(id_asiento_reversion_libro_diario, 0) = 0
                """,
                (
                    ESTADO_REVERSADO,
                    int(id_reverso),
                    _texto(usuario),
                    motivo_limpio,
                    asiento_id,
                    empresa_id,
                    ESTADO_CONTABILIZADO,
                ),
            )

            if cur.rowcount != 1:
                raise ValueError("El asiento no se pudo reversar porque cambió de estado.")

            _registrar_evento_central(
                conn,
                asiento_id,
                empresa_id,
                "REVERSO",
                f"Reverso id_asiento {id_reverso}. Motivo: {motivo_limpio}",
                usuario,
            )

            if _texto(asiento.get("origen_tabla")) == "asientos_origen" and _int(asiento.get("origen_id")) > 0:
                conn.execute(
                    """
                    UPDATE asientos_origen
                    SET estado = ?,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                      AND empresa_id = ?
                    """,
                    (
                        ESTADO_REVERSADO,
                        _int(asiento.get("origen_id")),
                        empresa_id,
                    ),
                )

        elif fuente == FUENTE_IVA:
            cierre_id = _int(asiento.get("cierre_id") or asiento.get("origen_id"))
            pago_id = _int(asiento.get("pago_id"))
            tipo_asiento = _texto(asiento.get("tipo_asiento")).upper()

            cur = conn.execute(
                f"""
                UPDATE {TABLA_IVA}
                SET estado = ?,
                    id_asiento_reversion_libro_diario = ?,
                    fecha_reversion = CURRENT_TIMESTAMP,
                    usuario_reversion = ?,
                    motivo_reversion = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE empresa_id = ?
                  AND cierre_id = ?
                  AND COALESCE(pago_id, 0) = ?
                  AND UPPER(tipo_asiento) = ?
                  AND estado = ?
                  AND COALESCE(id_asiento_reversion_libro_diario, 0) = 0
                """,
                (
                    ESTADO_REVERSADO,
                    int(id_reverso),
                    _texto(usuario),
                    motivo_limpio,
                    empresa_id,
                    cierre_id,
                    pago_id,
                    tipo_asiento,
                    ESTADO_CONTABILIZADO,
                ),
            )

            if cur.rowcount <= 0:
                raise ValueError("El asiento IVA no se pudo reversar porque cambió de estado.")

        else:
            raise ValueError("Fuente de asiento no soportada.")

        _registrar_evento_bandeja(
            conn,
            empresa_id=empresa_id,
            fuente=fuente,
            fuente_id=_int(asiento.get("fuente_id")),
            fuente_clave=_texto(asiento.get("fuente_clave")),
            evento="REVERSO",
            detalle=f"Reverso id_asiento {id_reverso}. Motivo: {motivo_limpio}",
            usuario=usuario,
        )

        conn.commit()

        return _resultado(
            True,
            "Asiento reversado correctamente.",
            id_asiento_reverso=id_reverso,
            fuente_clave=fuente_clave,
        )

    except Exception as exc:
        conn.rollback()
        return _resultado(
            False,
            f"No se pudo reversar el asiento: {exc}",
            fuente_clave=fuente_clave,
        )

    finally:
        conn.close()


# ======================================================
# CONTABILIZACIÓN MASIVA CONTROLADA
# ======================================================

def obtener_fuente_claves_por_filtros(
    empresa_id: int = 1,
    estado: str = ESTADO_PROPUESTO,
    origen: Optional[str] = None,
    fuente: Optional[str] = None,
) -> List[str]:
    """
    Devuelve claves de asientos de la bandeja según filtros operativos.

    Se usa para acciones masivas seguras: el usuario primero filtra y luego
    decide contabilizar ese universo filtrado.
    """
    df = listar_bandeja_asientos_propuestos(
        empresa_id=empresa_id,
        estado=estado,
        origen=origen,
        fuente=fuente,
        incluir_anulados=True,
    )

    if df.empty or "fuente_clave" not in df.columns:
        return []

    return list(dict.fromkeys(df["fuente_clave"].dropna().astype(str).tolist()))


def _normalizar_fuente_claves(fuente_claves: Optional[List[str]]) -> List[str]:
    if not fuente_claves:
        return []

    claves = []
    for clave in fuente_claves:
        texto = _texto(clave)
        if texto:
            claves.append(texto)

    return list(dict.fromkeys(claves))


def prevalidar_asientos_bandeja(
    fuente_claves: Optional[List[str]] = None,
    empresa_id: int = 1,
    estado: str = ESTADO_PROPUESTO,
    origen: Optional[str] = None,
    fuente: Optional[str] = None,
    todos_los_filtrados: bool = False,
    limite_maximo: int = 5000,
) -> Dict[str, Any]:
    """
    Prevalidación contable previa a una acción masiva.

    Reglas:
    - Solo se consideran asientos PROPUESTOS.
    - Cada asiento debe cuadrar individualmente.
    - No alcanza con que el total global cierre.
    - Se devuelve detalle de válidos y errores para no ejecutar a ciegas.
    """
    asegurar_estructura_bandeja_asientos()

    if todos_los_filtrados:
        claves = obtener_fuente_claves_por_filtros(
            empresa_id=empresa_id,
            estado=estado,
            origen=origen,
            fuente=fuente,
        )
    else:
        claves = _normalizar_fuente_claves(fuente_claves)

    if not claves:
        return _resultado(
            False,
            "No hay asientos seleccionados para prevalidar.",
            cantidad_solicitada=0,
            cantidad_valida=0,
            cantidad_error=0,
            asientos_validos=[],
            errores=[],
            fuente_claves_validas=[],
        )

    if len(claves) > int(limite_maximo):
        return _resultado(
            False,
            f"La selección supera el máximo permitido ({limite_maximo}). Filtrá mejor antes de ejecutar.",
            cantidad_solicitada=len(claves),
            cantidad_valida=0,
            cantidad_error=len(claves),
            asientos_validos=[],
            errores=[{"mensaje": "Selección demasiado grande.", "cantidad": len(claves)}],
            fuente_claves_validas=[],
        )

    validos = []
    errores = []

    for clave in claves:
        asiento = obtener_asiento_bandeja(clave)

        if not asiento:
            errores.append({
                "fuente_clave": clave,
                "mensaje": "No se encontró el asiento.",
            })
            continue

        if _int(asiento.get("empresa_id"), 1) != int(empresa_id):
            errores.append({
                "fuente_clave": clave,
                "mensaje": "El asiento pertenece a otra empresa.",
            })
            continue

        validacion = _validar_asiento_para_contabilizar(asiento)

        if not validacion.get("ok"):
            errores.append({
                "fuente_clave": clave,
                "origen": asiento.get("origen"),
                "estado": asiento.get("estado"),
                "descripcion": asiento.get("descripcion"),
                "mensaje": validacion.get("mensaje"),
            })
            continue

        validos.append({
            "fuente_clave": clave,
            "asiento": asiento,
            "origen": asiento.get("origen"),
            "fuente": asiento.get("fuente"),
            "periodo": asiento.get("periodo"),
            "descripcion": asiento.get("descripcion"),
            "total_debe": _float(validacion.get("total_debe")),
            "total_haber": _float(validacion.get("total_haber")),
            "diferencia": _float(validacion.get("diferencia")),
        })

    total_debe = round(sum(_float(item.get("total_debe")) for item in validos), 2)
    total_haber = round(sum(_float(item.get("total_haber")) for item in validos), 2)
    diferencia = round(total_debe - total_haber, 2)

    origenes = sorted({_texto(item.get("origen")) for item in validos if _texto(item.get("origen"))})
    fuentes = sorted({_texto(item.get("fuente")) for item in validos if _texto(item.get("fuente"))})
    periodos = sorted({_texto(item.get("periodo")) for item in validos if _texto(item.get("periodo"))})

    ok = len(validos) > 0 and len(errores) == 0

    return _resultado(
        ok,
        "Prevalidación correcta." if ok else "La prevalidación detectó asientos que no se pueden contabilizar.",
        cantidad_solicitada=len(claves),
        cantidad_valida=len(validos),
        cantidad_error=len(errores),
        total_debe=total_debe,
        total_haber=total_haber,
        diferencia=diferencia,
        origenes=origenes,
        fuentes=fuentes,
        periodos=periodos,
        asientos_validos=validos,
        errores=errores,
        fuente_claves_validas=[item["fuente_clave"] for item in validos],
    )


def _crear_lote_bandeja_conn(
    conn,
    *,
    empresa_id: int,
    accion: str,
    cantidad_solicitada: int,
    total_debe: float,
    total_haber: float,
    diferencia: float,
    detalle: str,
    usuario: Optional[str],
) -> int:
    cur = conn.execute(
        f"""
        INSERT INTO {TABLA_LOTES}
        (
            empresa_id,
            accion,
            estado,
            cantidad_solicitada,
            cantidad_procesada,
            cantidad_error,
            total_debe,
            total_haber,
            diferencia,
            detalle,
            usuario,
            fecha_lote
        )
        VALUES (?, ?, 'EN_PROCESO', ?, 0, 0, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(empresa_id),
            _texto(accion),
            int(cantidad_solicitada),
            _float(total_debe),
            _float(total_haber),
            _float(diferencia),
            _texto(detalle),
            _texto(usuario),
        ),
    )
    return int(cur.lastrowid)


def _actualizar_lote_bandeja_conn(
    conn,
    *,
    lote_id: int,
    estado: str,
    cantidad_procesada: int,
    cantidad_error: int = 0,
    detalle: Optional[str] = None,
) -> None:
    conn.execute(
        f"""
        UPDATE {TABLA_LOTES}
        SET estado = ?,
            cantidad_procesada = ?,
            cantidad_error = ?,
            detalle = COALESCE(?, detalle)
        WHERE id = ?
        """,
        (
            _texto(estado),
            int(cantidad_procesada),
            int(cantidad_error),
            detalle,
            int(lote_id),
        ),
    )


def contabilizar_asientos_bandeja_masivo(
    fuente_claves: Optional[List[str]] = None,
    empresa_id: int = 1,
    usuario: Optional[str] = "sistema",
    estado: str = ESTADO_PROPUESTO,
    origen: Optional[str] = None,
    fuente: Optional[str] = None,
    todos_los_filtrados: bool = False,
    confirmar_texto: Optional[str] = None,
    umbral_confirmacion_fuerte: int = 50,
    limite_maximo: int = 5000,
) -> Dict[str, Any]:
    """
    Contabiliza masivamente asientos propuestos con control de lote.

    La operación es atómica: si un asiento falla durante el pase al Libro
    Diario, se revierte todo el lote para evitar contabilizaciones parciales.
    """
    validacion = prevalidar_asientos_bandeja(
        fuente_claves=fuente_claves,
        empresa_id=empresa_id,
        estado=estado,
        origen=origen,
        fuente=fuente,
        todos_los_filtrados=todos_los_filtrados,
        limite_maximo=limite_maximo,
    )

    if not validacion.get("ok"):
        return validacion

    cantidad = int(validacion.get("cantidad_valida") or 0)

    if cantidad <= 0:
        return _resultado(False, "No hay asientos válidos para contabilizar.")

    if cantidad >= int(umbral_confirmacion_fuerte) and _texto(confirmar_texto).upper() != "CONTABILIZAR":
        return _resultado(
            False,
            f"Para contabilizar {cantidad} asientos se requiere escribir CONTABILIZAR.",
            requiere_confirmacion_fuerte=True,
            cantidad_valida=cantidad,
        )

    conn = conectar()

    try:
        conn.execute("BEGIN IMMEDIATE")

        detalle_lote = (
            f"Contabilización masiva. Orígenes: {', '.join(validacion.get('origenes') or [])}. "
            f"Fuentes: {', '.join(validacion.get('fuentes') or [])}. "
            f"Períodos: {', '.join(validacion.get('periodos') or [])}."
        )

        lote_id = _crear_lote_bandeja_conn(
            conn,
            empresa_id=empresa_id,
            accion="CONTABILIZACION_MASIVA",
            cantidad_solicitada=int(validacion.get("cantidad_solicitada") or cantidad),
            total_debe=_float(validacion.get("total_debe")),
            total_haber=_float(validacion.get("total_haber")),
            diferencia=_float(validacion.get("diferencia")),
            detalle=detalle_lote,
            usuario=usuario,
        )

        ids_asientos = []

        for item in validacion.get("asientos_validos") or []:
            asiento = item.get("asiento") or {}
            fuente_asiento = _texto(asiento.get("fuente")).upper()
            fuente_clave = _texto(asiento.get("fuente_clave"))

            id_asiento = _insertar_asiento_en_libro(
                conn,
                asiento,
                usuario,
                reverso=False,
            )

            if fuente_asiento == FUENTE_CENTRAL:
                _actualizar_central_contabilizado(
                    conn,
                    asiento,
                    id_asiento,
                    usuario,
                    lote_id=lote_id,
                )
            elif fuente_asiento == FUENTE_IVA:
                _actualizar_iva_contabilizado(
                    conn,
                    asiento,
                    id_asiento,
                    usuario,
                    lote_id=lote_id,
                )
            else:
                raise ValueError(f"Fuente de asiento no soportada: {fuente_asiento}")

            _registrar_evento_bandeja(
                conn,
                empresa_id=_int(asiento.get("empresa_id"), 1),
                fuente=fuente_asiento,
                fuente_id=_int(asiento.get("fuente_id")),
                fuente_clave=fuente_clave,
                evento="CONTABILIZACION_MASIVA",
                detalle=f"Asiento pasado a Libro Diario con id_asiento {id_asiento}. Lote {lote_id}.",
                usuario=usuario,
            )

            ids_asientos.append(id_asiento)

        _actualizar_lote_bandeja_conn(
            conn,
            lote_id=lote_id,
            estado="FINALIZADO",
            cantidad_procesada=len(ids_asientos),
            cantidad_error=0,
            detalle=f"Lote finalizado correctamente. Asientos Libro Diario: {ids_asientos}",
        )

        conn.commit()

        return _resultado(
            True,
            f"Se contabilizaron {len(ids_asientos)} asientos correctamente.",
            lote_id=lote_id,
            cantidad_procesada=len(ids_asientos),
            ids_asientos_libro_diario=ids_asientos,
            total_debe=_float(validacion.get("total_debe")),
            total_haber=_float(validacion.get("total_haber")),
            diferencia=_float(validacion.get("diferencia")),
        )

    except Exception as exc:
        conn.rollback()
        return _resultado(
            False,
            f"No se pudo contabilizar el lote: {exc}",
            cantidad_procesada=0,
        )

    finally:
        conn.close()


def listar_lotes_bandeja(
    empresa_id: int = 1,
    limite: int = 50,
) -> pd.DataFrame:
    asegurar_estructura_bandeja_asientos()

    df = ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_LOTES}
        WHERE empresa_id = ?
        ORDER BY fecha_lote DESC, id DESC
        LIMIT ?
        """,
        (int(empresa_id), int(limite)),
        fetch=True,
    )

    return _df(df)


__all__ = [
    "FUENTE_CENTRAL",
    "FUENTE_IVA",
    "ESTADO_PROPUESTO",
    "ESTADO_CONTABILIZADO",
    "ESTADO_RECHAZADO",
    "ESTADO_ANULADO",
    "ESTADO_REVERSADO",
    "asegurar_estructura_bandeja_asientos",
    "listar_bandeja_asientos_propuestos",
    "obtener_resumen_bandeja_asientos",
    "obtener_asiento_bandeja",
    "listar_eventos_bandeja",
    "contabilizar_asiento_bandeja",
    "rechazar_asiento_bandeja",
    "reversar_asiento_bandeja",
    "obtener_fuente_claves_por_filtros",
    "prevalidar_asientos_bandeja",
    "contabilizar_asientos_bandeja_masivo",
    "listar_lotes_bandeja",
    "parsear_fuente_clave",
]