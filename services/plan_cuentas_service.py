from __future__ import annotations

from datetime import datetime
import re
import sqlite3
import unicodedata
from typing import Any

import pandas as pd

from core.contabilidad_coherencia import COMPORTAMIENTOS_CONTABLES, normalizar_codigo


TIPOS_CUENTA = {
    "A": "Activo",
    "P": "Pasivo",
    "PN": "Patrimonio neto",
    "R": "Resultado",
    "D": "Detalle / sin clasificar",
    "N": "Sin clasificar",
}

MODULOS_ORIGEN_PREFERIDO = [
    "",
    "VENTAS",
    "COMPRAS",
    "COBRANZAS",
    "PAGOS",
    "BANCO",
    "CAJA",
    "TESORERIA",
    "IVA",
    "SUELDOS",
    "CAPITAL",
    "CONTABILIDAD",
]

COMPORTAMIENTOS_OPERATIVOS = tuple(sorted(COMPORTAMIENTOS_CONTABLES.keys()))


# ======================================================
# Infraestructura
# ======================================================


def _conectar_default() -> sqlite3.Connection:
    from database import conectar

    return conectar()


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _add_column(conn: sqlite3.Connection, table_name: str, column: str, definition: str) -> None:
    if column not in _columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {definition}")


def _fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], sqlite3.Row):
        return [dict(row) for row in rows]
    columnas = [col[0] for col in cursor.description]
    return [dict(zip(columnas, row)) for row in rows]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def limpiar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar_si_no(valor: Any, default: str = "N") -> str:
    texto = limpiar_texto(valor).upper()
    if texto in {"S", "SI", "SÍ", "1", "TRUE", "T", "Y", "YES"}:
        return "S"
    if texto in {"N", "NO", "0", "FALSE", "F"}:
        return "N"
    return default


def _to_int(valor: Any, default: int = 0) -> int:
    try:
        if valor is None or valor == "":
            return default
        return int(float(valor))
    except Exception:
        return default


def _to_bool_int(valor: Any, default: int = 0) -> int:
    texto = limpiar_texto(valor).upper()
    if texto in {"S", "SI", "SÍ", "1", "TRUE", "T", "Y", "YES"}:
        return 1
    if texto in {"N", "NO", "0", "FALSE", "F"}:
        return 0
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return 1 if valor else 0
    return default


def _normalizar_texto_busqueda(valor: Any) -> str:
    texto = limpiar_texto(valor).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _codigo_sin_puntos(codigo: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", limpiar_texto(codigo)).upper()


def _nombre_comportamiento(codigo: Any) -> str:
    codigo_norm = normalizar_codigo(codigo)
    datos = COMPORTAMIENTOS_CONTABLES.get(codigo_norm)
    if not datos:
        return ""
    return datos.get("nombre", codigo_norm)


# ======================================================
# Estructura y sincronización
# ======================================================


def asegurar_estructura_plan_cuentas(conn: sqlite3.Connection | None = None) -> None:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_cuentas (
                codigo TEXT,
                nombre TEXT,
                empresa_id INTEGER DEFAULT 1
            )
            """
        )
        _add_column(conn, "plan_cuentas", "empresa_id", "INTEGER DEFAULT 1")
        _add_column(conn, "plan_cuentas", "comportamiento_contable", "TEXT")
        _add_column(conn, "plan_cuentas", "requiere_auxiliar", "INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "plan_cuentas", "permite_imputacion_operativa", "INTEGER NOT NULL DEFAULT 1")
        _add_column(conn, "plan_cuentas", "modulo_origen_preferido", "TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_cuentas_detallado (
                cuenta TEXT PRIMARY KEY,
                detalle TEXT,
                imputable TEXT,
                ajustable TEXT,
                tipo TEXT,
                madre TEXT,
                nivel INTEGER,
                orden INTEGER,
                empresa_id INTEGER DEFAULT 1
            )
            """
        )
        _add_column(conn, "plan_cuentas_detallado", "empresa_id", "INTEGER DEFAULT 1")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_cuentas_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                codigo_cuenta TEXT,
                evento TEXT NOT NULL,
                detalle TEXT,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                usuario TEXT,
                motivo TEXT,
                fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_plan_cuentas_eventos_empresa
            ON plan_cuentas_eventos (empresa_id, fecha_evento)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_plan_cuentas_codigo_empresa
            ON plan_cuentas (empresa_id, codigo)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_plan_cuentas_detallado_empresa
            ON plan_cuentas_detallado (empresa_id, cuenta)
            """
        )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def registrar_evento_plan(
    empresa_id: int,
    codigo_cuenta: str,
    evento: str,
    detalle: str = "",
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
    usuario: str | None = None,
    motivo: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    propia = conn is None
    conn = conn or _conectar_default()
    try:
        asegurar_estructura_plan_cuentas(conn)
        conn.execute(
            """
            INSERT INTO plan_cuentas_eventos
            (empresa_id, codigo_cuenta, evento, detalle, valor_anterior, valor_nuevo, usuario, motivo, fecha_evento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                codigo_cuenta,
                evento,
                detalle,
                "" if valor_anterior is None else str(valor_anterior),
                "" if valor_nuevo is None else str(valor_nuevo),
                usuario,
                motivo,
                _now(),
            ),
        )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def _sincronizar_compatibilidad_comportamientos(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    codigo_cuenta: str,
    nombre_cuenta: str,
    comportamiento: str,
    usuario: str | None,
    motivo: str | None,
) -> None:
    """
    Mantiene compatibilidad con la etapa anterior, pero la fuente vigente pasa a ser plan_cuentas.

    No se usa esta tabla como fuente principal para la UI nueva; solo se deja trazabilidad y compatibilidad
    con diagnósticos/servicios antiguos mientras se migra el sistema completo.
    """
    if not _table_exists(conn, "contabilidad_cuentas_comportamiento"):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contabilidad_cuentas_comportamiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                cuenta_id INTEGER,
                codigo_cuenta TEXT,
                cuenta_nombre TEXT,
                comportamiento TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                origen TEXT NOT NULL DEFAULT 'PLAN_CUENTAS',
                observaciones TEXT,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT,
                estado TEXT DEFAULT 'ACTIVO',
                usuario_actualizacion TEXT,
                motivo_baja TEXT,
                fecha_baja TEXT,
                usuario_baja TEXT
            )
            """
        )

    agregados = {
        "cuenta_nombre": "TEXT",
        "estado": "TEXT DEFAULT 'ACTIVO'",
        "usuario_actualizacion": "TEXT",
        "actualizado_en": "TEXT",
        "motivo_baja": "TEXT",
        "fecha_baja": "TEXT",
        "usuario_baja": "TEXT",
    }
    columnas = _columns(conn, "contabilidad_cuentas_comportamiento")
    for columna, definicion in agregados.items():
        if columna not in columnas:
            conn.execute(f"ALTER TABLE contabilidad_cuentas_comportamiento ADD COLUMN {columna} {definicion}")

    comportamiento_norm = normalizar_codigo(comportamiento)
    if comportamiento_norm:
        conn.execute(
            """
            UPDATE contabilidad_cuentas_comportamiento
               SET activo = 0,
                   estado = 'INACTIVO',
                   actualizado_en = ?,
                   usuario_actualizacion = ?,
                   motivo_baja = ?
             WHERE empresa_id = ?
               AND codigo_cuenta = ?
               AND COALESCE(activo, 1) = 1
               AND COALESCE(estado, 'ACTIVO') = 'ACTIVO'
               AND comportamiento <> ?
            """,
            (_now(), usuario, motivo or "Sincronización desde Plan de Cuentas", empresa_id, codigo_cuenta, comportamiento_norm),
        )
        existe = conn.execute(
            """
            SELECT id
              FROM contabilidad_cuentas_comportamiento
             WHERE empresa_id = ?
               AND codigo_cuenta = ?
               AND comportamiento = ?
               AND COALESCE(activo, 1) = 1
               AND COALESCE(estado, 'ACTIVO') = 'ACTIVO'
             LIMIT 1
            """,
            (empresa_id, codigo_cuenta, comportamiento_norm),
        ).fetchone()
        if not existe:
            conn.execute(
                """
                INSERT INTO contabilidad_cuentas_comportamiento
                (empresa_id, codigo_cuenta, cuenta_nombre, comportamiento, activo, origen, observaciones, estado, creado_en)
                VALUES (?, ?, ?, ?, 1, 'PLAN_CUENTAS_PRO', ?, 'ACTIVO', ?)
                """,
                (
                    empresa_id,
                    codigo_cuenta,
                    nombre_cuenta,
                    comportamiento_norm,
                    motivo or "Sincronizado desde Configuración → Plan de Cuentas",
                    _now(),
                ),
            )
    else:
        conn.execute(
            """
            UPDATE contabilidad_cuentas_comportamiento
               SET activo = 0,
                   estado = 'ANULADO',
                   actualizado_en = ?,
                   usuario_actualizacion = ?,
                   motivo_baja = ?
             WHERE empresa_id = ?
               AND codigo_cuenta = ?
               AND COALESCE(activo, 1) = 1
               AND COALESCE(estado, 'ACTIVO') = 'ACTIVO'
            """,
            (_now(), usuario, motivo or "Uso operativo limpiado desde Plan de Cuentas", empresa_id, codigo_cuenta),
        )


def normalizar_metadata_plan_cuentas(
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str = "Normalización segura del Plan de Cuentas PRO",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Aplica reglas seguras basadas en imputable S/N sin tocar movimientos operativos."""
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        cuentas = listar_plan_cuentas(empresa_id=empresa_id, conn=conn)
        corregidas_no_imputables = 0
        sincronizadas = 0
        for cuenta in cuentas:
            codigo = cuenta["codigo"]
            imputable = cuenta["imputable"]
            comportamiento_actual = cuenta.get("comportamiento_contable") or ""
            permite_actual = _to_bool_int(cuenta.get("permite_imputacion_operativa"), 1)
            if imputable != "S" and (comportamiento_actual or permite_actual != 0):
                conn.execute(
                    """
                    UPDATE plan_cuentas
                       SET comportamiento_contable = NULL,
                           permite_imputacion_operativa = 0,
                           requiere_auxiliar = 0
                     WHERE empresa_id = ? AND codigo = ?
                    """,
                    (empresa_id, codigo),
                )
                _sincronizar_compatibilidad_comportamientos(
                    conn,
                    empresa_id=empresa_id,
                    codigo_cuenta=codigo,
                    nombre_cuenta=cuenta.get("nombre") or "",
                    comportamiento="",
                    usuario=usuario,
                    motivo=motivo,
                )
                registrar_evento_plan(
                    empresa_id,
                    codigo,
                    "NORMALIZACION_NO_IMPUTABLE",
                    "Se limpió uso operativo/imputación operativa porque la cuenta no es imputable.",
                    valor_anterior=comportamiento_actual,
                    valor_nuevo="",
                    usuario=usuario,
                    motivo=motivo,
                    conn=conn,
                )
                corregidas_no_imputables += 1
            elif imputable == "S" and comportamiento_actual:
                _sincronizar_compatibilidad_comportamientos(
                    conn,
                    empresa_id=empresa_id,
                    codigo_cuenta=codigo,
                    nombre_cuenta=cuenta.get("nombre") or "",
                    comportamiento=comportamiento_actual,
                    usuario=usuario,
                    motivo=motivo,
                )
                sincronizadas += 1
        if propia:
            conn.commit()
        return {
            "ok": True,
            "corregidas_no_imputables": corregidas_no_imputables,
            "sincronizadas": sincronizadas,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


# ======================================================
# Lecturas
# ======================================================


def listar_plan_cuentas(
    empresa_id: int = 1,
    incluir_no_imputables: bool = True,
    solo_imputables: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        params: list[Any] = [empresa_id, empresa_id]
        sql = """
            SELECT
                COALESCE(d.cuenta, p.codigo) AS codigo,
                COALESCE(d.detalle, p.nombre) AS nombre,
                COALESCE(d.imputable, 'S') AS imputable,
                COALESCE(d.ajustable, 'N') AS ajustable,
                COALESCE(d.tipo, 'D') AS tipo,
                COALESCE(d.madre, '') AS madre,
                COALESCE(d.nivel, 1) AS nivel,
                COALESCE(d.orden, 0) AS orden,
                p.comportamiento_contable AS comportamiento_contable,
                COALESCE(p.requiere_auxiliar, 0) AS requiere_auxiliar,
                COALESCE(p.permite_imputacion_operativa, 1) AS permite_imputacion_operativa,
                COALESCE(p.modulo_origen_preferido, '') AS modulo_origen_preferido,
                p.rowid AS plan_rowid
            FROM plan_cuentas p
            LEFT JOIN plan_cuentas_detallado d
              ON d.cuenta = p.codigo
             AND COALESCE(d.empresa_id, 1) = COALESCE(p.empresa_id, 1)
            WHERE COALESCE(p.empresa_id, 1) = ?

            UNION

            SELECT
                d.cuenta AS codigo,
                d.detalle AS nombre,
                COALESCE(d.imputable, 'S') AS imputable,
                COALESCE(d.ajustable, 'N') AS ajustable,
                COALESCE(d.tipo, 'D') AS tipo,
                COALESCE(d.madre, '') AS madre,
                COALESCE(d.nivel, 1) AS nivel,
                COALESCE(d.orden, 0) AS orden,
                p.comportamiento_contable AS comportamiento_contable,
                COALESCE(p.requiere_auxiliar, 0) AS requiere_auxiliar,
                COALESCE(p.permite_imputacion_operativa, 1) AS permite_imputacion_operativa,
                COALESCE(p.modulo_origen_preferido, '') AS modulo_origen_preferido,
                p.rowid AS plan_rowid
            FROM plan_cuentas_detallado d
            LEFT JOIN plan_cuentas p
              ON p.codigo = d.cuenta
             AND COALESCE(p.empresa_id, 1) = COALESCE(d.empresa_id, 1)
            WHERE COALESCE(d.empresa_id, 1) = ?
            ORDER BY orden, codigo
        """
        filas = _fetch_dicts(conn, sql, tuple(params))
        normalizadas: list[dict[str, Any]] = []
        vistos: set[str] = set()
        for row in filas:
            codigo = limpiar_texto(row.get("codigo"))
            if not codigo or codigo in vistos:
                continue
            vistos.add(codigo)
            imputable = _normalizar_si_no(row.get("imputable"), "S")
            comportamiento = normalizar_codigo(row.get("comportamiento_contable"))
            if comportamiento not in COMPORTAMIENTOS_CONTABLES:
                comportamiento = ""
            permite = _to_bool_int(row.get("permite_imputacion_operativa"), 1 if imputable == "S" else 0)
            requiere = _to_bool_int(row.get("requiere_auxiliar"), 0)
            item = {
                "codigo": codigo,
                "nombre": limpiar_texto(row.get("nombre")),
                "imputable": imputable,
                "ajustable": _normalizar_si_no(row.get("ajustable"), "N"),
                "tipo": limpiar_texto(row.get("tipo") or "D").upper(),
                "madre": limpiar_texto(row.get("madre")),
                "nivel": _to_int(row.get("nivel"), 1),
                "orden": _to_int(row.get("orden"), 0),
                "comportamiento_contable": comportamiento,
                "comportamiento_nombre": _nombre_comportamiento(comportamiento),
                "requiere_auxiliar": requiere,
                "permite_imputacion_operativa": permite if imputable == "S" else 0,
                "modulo_origen_preferido": limpiar_texto(row.get("modulo_origen_preferido")),
                "es_imputable": imputable == "S",
                "es_no_imputable": imputable != "S",
                "estado_configuracion": "OK",
            }
            if item["es_no_imputable"] and comportamiento:
                item["estado_configuracion"] = "ERROR: cuenta no imputable con comportamiento"
            elif item["es_no_imputable"]:
                item["estado_configuracion"] = "Agrupadora / no imputable"
            elif not comportamiento:
                item["estado_configuracion"] = "Pendiente de comportamiento"
            normalizadas.append(item)

        if solo_imputables:
            normalizadas = [item for item in normalizadas if item["es_imputable"]]
        elif not incluir_no_imputables:
            normalizadas = [item for item in normalizadas if item["es_imputable"]]
        return normalizadas
    finally:
        if propia:
            conn.close()


def obtener_cuenta_plan(
    codigo: str,
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    codigo = limpiar_texto(codigo)
    for cuenta in listar_plan_cuentas(empresa_id=empresa_id, conn=conn):
        if cuenta["codigo"] == codigo:
            return cuenta
    return None


def listar_cuentas_para_selector(
    empresa_id: int = 1,
    solo_imputables: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    return listar_plan_cuentas(
        empresa_id=empresa_id,
        incluir_no_imputables=not solo_imputables,
        solo_imputables=solo_imputables,
        conn=conn,
    )


def listar_eventos_plan_cuentas(
    empresa_id: int = 1,
    limite: int = 200,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        return _fetch_dicts(
            conn,
            """
            SELECT id, empresa_id, codigo_cuenta, evento, detalle, valor_anterior, valor_nuevo,
                   usuario, motivo, fecha_evento
              FROM plan_cuentas_eventos
             WHERE empresa_id = ?
             ORDER BY id DESC
             LIMIT ?
            """,
            (empresa_id, limite),
        )
    finally:
        if propia:
            conn.close()


# ======================================================
# Validación y escritura
# ======================================================


def validar_datos_cuenta(datos: dict[str, Any]) -> list[str]:
    errores: list[str] = []
    codigo = limpiar_texto(datos.get("codigo") or datos.get("cuenta"))
    nombre = limpiar_texto(datos.get("nombre") or datos.get("detalle"))
    imputable = _normalizar_si_no(datos.get("imputable"), "S")
    comportamiento = normalizar_codigo(datos.get("comportamiento_contable"))
    permite = _to_bool_int(datos.get("permite_imputacion_operativa"), 1 if imputable == "S" else 0)

    if not codigo:
        errores.append("Debe indicar el código de cuenta.")
    if not nombre:
        errores.append("Debe indicar el nombre/detalle de la cuenta.")
    if comportamiento and comportamiento not in COMPORTAMIENTOS_CONTABLES:
        errores.append(f"El uso operativo {comportamiento} no pertenece al catálogo vigente.")
    if imputable != "S" and comportamiento:
        errores.append("Una cuenta no imputable no puede tener uso operativo del sistema.")
    if imputable != "S" and permite:
        errores.append("Una cuenta no imputable no puede permitir imputación operativa.")

    return errores


def guardar_cuenta_plan(
    *,
    empresa_id: int = 1,
    codigo: str,
    nombre: str,
    imputable: str = "S",
    ajustable: str = "N",
    tipo: str = "D",
    madre: str = "",
    nivel: int = 1,
    orden: int = 0,
    comportamiento_contable: str = "",
    permite_imputacion_operativa: int | bool = 1,
    requiere_auxiliar: int | bool = 0,
    modulo_origen_preferido: str = "",
    usuario: str | None = None,
    motivo: str = "Edición desde Configuración → Plan de Cuentas",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        codigo = limpiar_texto(codigo)
        nombre = limpiar_texto(nombre)
        imputable = _normalizar_si_no(imputable, "S")
        ajustable = _normalizar_si_no(ajustable, "N")
        tipo = limpiar_texto(tipo).upper() or "D"
        madre = limpiar_texto(madre)
        comportamiento = normalizar_codigo(comportamiento_contable)
        if comportamiento not in COMPORTAMIENTOS_CONTABLES:
            comportamiento = ""
        if imputable != "S" and comportamiento:
            return {
                "ok": False,
                "errores": ["Una cuenta no imputable no puede tener uso operativo del sistema."],
            }
        if imputable != "S":
            comportamiento = ""
            permite_imputacion_operativa = 0
            requiere_auxiliar = 0
        permite = _to_bool_int(permite_imputacion_operativa, 1 if imputable == "S" else 0)
        requiere = _to_bool_int(requiere_auxiliar, 0)
        modulo = limpiar_texto(modulo_origen_preferido).upper()
        datos = {
            "codigo": codigo,
            "nombre": nombre,
            "imputable": imputable,
            "comportamiento_contable": comportamiento,
            "permite_imputacion_operativa": permite,
        }
        errores = validar_datos_cuenta(datos)
        if errores:
            return {"ok": False, "errores": errores}

        anterior = obtener_cuenta_plan(codigo, empresa_id=empresa_id, conn=conn)

        conn.execute(
            """
            INSERT INTO plan_cuentas_detallado
            (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden, empresa_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cuenta) DO UPDATE SET
                detalle = excluded.detalle,
                imputable = excluded.imputable,
                ajustable = excluded.ajustable,
                tipo = excluded.tipo,
                madre = excluded.madre,
                nivel = excluded.nivel,
                orden = excluded.orden,
                empresa_id = excluded.empresa_id
            """,
            (codigo, nombre, imputable, ajustable, tipo, madre, _to_int(nivel, 1), _to_int(orden, 0), empresa_id),
        )

        existe_plan = conn.execute(
            "SELECT rowid FROM plan_cuentas WHERE empresa_id = ? AND codigo = ? LIMIT 1",
            (empresa_id, codigo),
        ).fetchone()
        if existe_plan:
            conn.execute(
                """
                UPDATE plan_cuentas
                   SET nombre = ?,
                       comportamiento_contable = ?,
                       requiere_auxiliar = ?,
                       permite_imputacion_operativa = ?,
                       modulo_origen_preferido = ?
                 WHERE empresa_id = ? AND codigo = ?
                """,
                (nombre, comportamiento or None, requiere, permite, modulo or None, empresa_id, codigo),
            )
        else:
            conn.execute(
                """
                INSERT INTO plan_cuentas
                (codigo, nombre, empresa_id, comportamiento_contable, requiere_auxiliar,
                 permite_imputacion_operativa, modulo_origen_preferido)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (codigo, nombre, empresa_id, comportamiento or None, requiere, permite, modulo or None),
            )

        _sincronizar_compatibilidad_comportamientos(
            conn,
            empresa_id=empresa_id,
            codigo_cuenta=codigo,
            nombre_cuenta=nombre,
            comportamiento=comportamiento,
            usuario=usuario,
            motivo=motivo,
        )

        evento = "CUENTA_EDITADA" if anterior else "CUENTA_CREADA"
        registrar_evento_plan(
            empresa_id,
            codigo,
            evento,
            f"Cuenta {'actualizada' if anterior else 'creada'} desde Plan de Cuentas PRO.",
            valor_anterior=anterior,
            valor_nuevo={
                "nombre": nombre,
                "imputable": imputable,
                "tipo": tipo,
                "madre": madre,
                "comportamiento_contable": comportamiento,
                "permite_imputacion_operativa": permite,
                "requiere_auxiliar": requiere,
                "modulo_origen_preferido": modulo,
            },
            usuario=usuario,
            motivo=motivo,
            conn=conn,
        )
        if propia:
            conn.commit()
        return {"ok": True, "codigo": codigo, "comportamiento_contable": comportamiento}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def limpiar_comportamiento_cuenta(
    codigo: str,
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not limpiar_texto(motivo):
        return {"ok": False, "errores": ["Debe indicar un motivo para limpiar el comportamiento."]}
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        cuenta = obtener_cuenta_plan(codigo, empresa_id=empresa_id, conn=conn)
        if not cuenta:
            return {"ok": False, "errores": ["La cuenta no existe en el plan."]}
        anterior = cuenta.get("comportamiento_contable") or ""
        conn.execute(
            """
            UPDATE plan_cuentas
               SET comportamiento_contable = NULL,
                   permite_imputacion_operativa = CASE WHEN ? = 'S' THEN permite_imputacion_operativa ELSE 0 END,
                   requiere_auxiliar = 0
             WHERE empresa_id = ? AND codigo = ?
            """,
            (cuenta.get("imputable"), empresa_id, limpiar_texto(codigo)),
        )
        _sincronizar_compatibilidad_comportamientos(
            conn,
            empresa_id=empresa_id,
            codigo_cuenta=limpiar_texto(codigo),
            nombre_cuenta=cuenta.get("nombre") or "",
            comportamiento="",
            usuario=usuario,
            motivo=motivo,
        )
        registrar_evento_plan(
            empresa_id,
            limpiar_texto(codigo),
            "COMPORTAMIENTO_LIMPIADO",
            "Se limpió el uso operativo desde Plan de Cuentas PRO.",
            valor_anterior=anterior,
            valor_nuevo="",
            usuario=usuario,
            motivo=motivo,
            conn=conn,
        )
        if propia:
            conn.commit()
        return {"ok": True, "codigo": limpiar_texto(codigo)}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def eliminar_cuenta_plan(
    codigo: str,
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str = "Eliminación manual desde Plan de Cuentas PRO",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    codigo = limpiar_texto(codigo)
    if not codigo:
        return {"ok": False, "errores": ["Debe indicar el código de cuenta."]}
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        cuenta = obtener_cuenta_plan(codigo, empresa_id=empresa_id, conn=conn)
        if not cuenta:
            return {"ok": False, "errores": ["La cuenta no existe."]}
        conn.execute("DELETE FROM plan_cuentas_detallado WHERE empresa_id = ? AND cuenta = ?", (empresa_id, codigo))
        conn.execute("DELETE FROM plan_cuentas WHERE empresa_id = ? AND codigo = ?", (empresa_id, codigo))
        _sincronizar_compatibilidad_comportamientos(
            conn,
            empresa_id=empresa_id,
            codigo_cuenta=codigo,
            nombre_cuenta=cuenta.get("nombre") or "",
            comportamiento="",
            usuario=usuario,
            motivo=motivo,
        )
        registrar_evento_plan(
            empresa_id,
            codigo,
            "CUENTA_ELIMINADA",
            "Cuenta eliminada desde Plan de Cuentas PRO.",
            valor_anterior=cuenta,
            valor_nuevo="",
            usuario=usuario,
            motivo=motivo,
            conn=conn,
        )
        if propia:
            conn.commit()
        return {"ok": True}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


# ======================================================
# Importación / reemplazo de plan
# ======================================================


def reemplazar_plan_desde_dataframe(
    df: pd.DataFrame,
    *,
    empresa_id: int = 1,
    formato: str = "auto",
    usuario: str | None = None,
    motivo: str = "Reemplazo de plan de cuentas desde CSV",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_plan_cuentas(conn)
        columnas = {str(col).strip().lower(): col for col in df.columns}
        es_detallado = {"cuenta", "detalle"}.issubset(columnas.keys())
        es_simple = {"codigo", "nombre"}.issubset(columnas.keys())
        if formato == "auto":
            formato = "detallado" if es_detallado else "simple" if es_simple else ""
        if formato not in {"detallado", "simple"}:
            return {"ok": False, "errores": ["El archivo debe tener columnas cuenta/detalle o codigo/nombre."]}

        anteriores = listar_plan_cuentas(empresa_id=empresa_id, conn=conn)
        conn.execute("DELETE FROM plan_cuentas_detallado WHERE empresa_id = ?", (empresa_id,))
        conn.execute("DELETE FROM plan_cuentas WHERE empresa_id = ?", (empresa_id,))

        procesadas = 0
        for _, fila in df.iterrows():
            if formato == "detallado":
                codigo = limpiar_texto(fila.get(columnas["cuenta"]))
                nombre = limpiar_texto(fila.get(columnas["detalle"]))
                imputable = _normalizar_si_no(fila.get(columnas.get("imputable", ""), "S"), "S") if "imputable" in columnas else "S"
                ajustable = _normalizar_si_no(fila.get(columnas.get("ajustable", ""), "N"), "N") if "ajustable" in columnas else "N"
                tipo = limpiar_texto(fila.get(columnas.get("tipo", ""), "D")).upper() if "tipo" in columnas else "D"
                madre = limpiar_texto(fila.get(columnas.get("madre", ""), "")) if "madre" in columnas else ""
                nivel = _to_int(fila.get(columnas.get("nivel", ""), 1), 1) if "nivel" in columnas else 1
                orden = _to_int(fila.get(columnas.get("orden", ""), 0), 0) if "orden" in columnas else 0
            else:
                codigo = limpiar_texto(fila.get(columnas["codigo"]))
                nombre = limpiar_texto(fila.get(columnas["nombre"]))
                imputable, ajustable, tipo, madre, nivel, orden = "S", "N", "D", "", 1, procesadas + 1
            if not codigo or not nombre:
                continue
            guardar_cuenta_plan(
                empresa_id=empresa_id,
                codigo=codigo,
                nombre=nombre,
                imputable=imputable,
                ajustable=ajustable,
                tipo=tipo,
                madre=madre,
                nivel=nivel,
                orden=orden,
                comportamiento_contable="",
                permite_imputacion_operativa=1 if imputable == "S" else 0,
                requiere_auxiliar=0,
                modulo_origen_preferido="",
                usuario=usuario,
                motivo=motivo,
                conn=conn,
            )
            procesadas += 1

        registrar_evento_plan(
            empresa_id,
            "*",
            "PLAN_REEMPLAZADO",
            f"Plan reemplazado desde CSV. Cuentas anteriores: {len(anteriores)}. Cuentas nuevas: {procesadas}.",
            valor_anterior=f"{len(anteriores)} cuentas",
            valor_nuevo=f"{procesadas} cuentas",
            usuario=usuario,
            motivo=motivo,
            conn=conn,
        )
        if propia:
            conn.commit()
        return {"ok": True, "procesadas": procesadas}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def borrar_plan_cuentas_completo(
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str = "Borrado manual del plan de cuentas",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    try:
        asegurar_estructura_plan_cuentas(conn)
        cantidad = len(listar_plan_cuentas(empresa_id=empresa_id, conn=conn))
        conn.execute("DELETE FROM plan_cuentas_detallado WHERE empresa_id = ?", (empresa_id,))
        conn.execute("DELETE FROM plan_cuentas WHERE empresa_id = ?", (empresa_id,))
        if _table_exists(conn, "contabilidad_cuentas_comportamiento"):
            conn.execute(
                """
                UPDATE contabilidad_cuentas_comportamiento
                   SET activo = 0,
                       estado = 'ANULADO',
                       actualizado_en = ?,
                       motivo_baja = ?
                 WHERE empresa_id = ?
                """,
                (_now(), motivo, empresa_id),
            )
        registrar_evento_plan(
            empresa_id,
            "*",
            "PLAN_BORRADO",
            f"Se borró el plan de cuentas completo ({cantidad} cuentas).",
            valor_anterior=f"{cantidad} cuentas",
            valor_nuevo="0 cuentas",
            usuario=usuario,
            motivo=motivo,
            conn=conn,
        )
        if propia:
            conn.commit()
        return {"ok": True, "borradas": cantidad}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


# ======================================================
# Diagnóstico / sugerencias
# ======================================================


def sugerir_comportamiento_plan(codigo: Any, nombre: Any, imputable: Any = "S") -> dict[str, Any]:
    if _normalizar_si_no(imputable, "S") != "S":
        return {
            "comportamiento": "",
            "confianza": "No aplica",
            "motivo": "La cuenta no es imputable; no debe tener uso operativo del sistema.",
            "aplicable": False,
        }
    texto = _normalizar_texto_busqueda(f"{codigo} {nombre}")
    comportamiento = ""
    confianza = "Media"
    motivo = ""

    # Banco: se usan términos bancarios explícitos. No se interpreta 'nacionales' como Banco Nación.
    bancos = [
        r"\bbanco\b",
        r"\bcuenta corriente\b",
        r"\bcuenta bancaria\b",
        r"\bcbu\b",
        r"\bgalicia\b",
        r"\bsantander\b",
        r"\bmacro\b",
        r"\bbbva\b",
        r"\bicbc\b",
        r"\bsupervielle\b",
        r"\bmercado pago\b",
        r"\bbilletera\b",
        r"\bnacion\b",
    ]
    if "percepcion" not in texto and "retencion" not in texto and "impuesto" not in texto:
        if any(re.search(patron, texto) for patron in bancos):
            comportamiento, confianza, motivo = "BANCO", "Alta", "La cuenta contiene una referencia bancaria explícita."

    if not comportamiento and re.search(r"\bcaja\b|\befectivo\b|\bfondo fijo\b", texto):
        comportamiento, confianza, motivo = "CAJA", "Alta", "La cuenta representa caja, efectivo o fondo fijo."
    elif not comportamiento and ("iva credito" in texto or "credito fiscal" in texto or "iva compras" in texto):
        comportamiento, confianza, motivo = "IVA_CREDITO", "Alta", "La cuenta contiene IVA crédito fiscal o crédito fiscal de compras."
    elif not comportamiento and ("iva debito" in texto or "debito fiscal" in texto or "iva ventas" in texto or "iva a pagar" in texto):
        comportamiento, confianza, motivo = "IVA_DEBITO", "Alta", "La cuenta contiene IVA débito fiscal, IVA ventas o IVA a pagar."
    elif not comportamiento and ("deudores por ventas" in texto or "clientes" in texto or "cuentas a cobrar" in texto):
        comportamiento, confianza, motivo = "CLIENTES", "Alta", "La cuenta representa clientes o deudores por ventas."
    elif not comportamiento and ("proveedores" in texto or "acreedores comerciales" in texto or "cuentas a pagar" in texto):
        comportamiento, confianza, motivo = "PROVEEDORES", "Alta", "La cuenta representa proveedores o acreedores comerciales."
    elif not comportamiento and "capital social" in texto:
        comportamiento, confianza, motivo = "CAPITAL_SOCIAL", "Alta", "La cuenta representa capital social."
    elif not comportamiento and ("socios por integracion" in texto or "accionistas por integracion" in texto or "capital pendiente" in texto):
        comportamiento, confianza, motivo = "SOCIOS_INTEGRACION", "Alta", "La cuenta representa integración pendiente de socios/accionistas."
    elif not comportamiento and "aportes irrevocables" in texto:
        comportamiento, confianza, motivo = "APORTE_IRREVOCABLE", "Alta", "La cuenta representa aportes irrevocables."
    elif not comportamiento and ("prestamos de socios" in texto or "prestamo de socios" in texto):
        comportamiento, confianza, motivo = "PRESTAMO_SOCIO", "Alta", "La cuenta representa préstamos de socios/directores."
    elif not comportamiento and ("cuenta particular socios" in texto or "cuenta particular directores" in texto):
        comportamiento, confianza, motivo = "CUENTA_PARTICULAR_SOCIO", "Media", "La cuenta representa cuenta particular de socios/directores."
    elif not comportamiento and ("sueldos y jornales" in texto or "remuneraciones" in texto or "haberes" in texto):
        comportamiento, confianza, motivo = "SUELDOS_GASTO", "Alta", "La cuenta representa gasto de sueldos y jornales."
    elif not comportamiento and "sueldos a pagar" in texto:
        comportamiento, confianza, motivo = "SUELDOS_A_PAGAR", "Alta", "La cuenta representa sueldos a pagar."
    elif not comportamiento and "cargas sociales a pagar" in texto:
        comportamiento, confianza, motivo = "CARGAS_SOCIALES_A_PAGAR", "Alta", "La cuenta representa cargas sociales a pagar."
    elif not comportamiento and "obra social a pagar" in texto:
        comportamiento, confianza, motivo = "OBRA_SOCIAL_A_PAGAR", "Alta", "La cuenta representa obra social a pagar."
    elif not comportamiento and "sindicato a pagar" in texto:
        comportamiento, confianza, motivo = "SINDICATO_A_PAGAR", "Alta", "La cuenta representa sindicato a pagar."
    elif not comportamiento and "art a pagar" in texto:
        comportamiento, confianza, motivo = "ART_A_PAGAR", "Alta", "La cuenta representa ART a pagar."
    elif not comportamiento and "cargas sociales" in texto:
        comportamiento, confianza, motivo = "CARGAS_SOCIALES_GASTO", "Media", "La cuenta contiene cargas sociales; revisar si es gasto o pasivo."

    return {
        "comportamiento": comportamiento,
        "confianza": confianza if comportamiento else "Sin sugerencia",
        "motivo": motivo if comportamiento else "No se detectó un uso operativo claro.",
        "aplicable": bool(comportamiento),
    }


def listar_sugerencias_plan_cuentas(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    cuentas = listar_plan_cuentas(empresa_id=empresa_id, solo_imputables=True, conn=conn)
    sugerencias: list[dict[str, Any]] = []
    for cuenta in cuentas:
        if cuenta.get("comportamiento_contable"):
            continue
        sugerencia = sugerir_comportamiento_plan(cuenta["codigo"], cuenta["nombre"], cuenta["imputable"])
        if sugerencia.get("comportamiento"):
            sugerencias.append({**cuenta, **sugerencia})
    return sugerencias


def diagnosticar_plan_cuentas_pro(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    cuentas = listar_plan_cuentas(empresa_id=empresa_id, conn=conn)
    errores: list[dict[str, Any]] = []
    advertencias: list[dict[str, Any]] = []
    pendientes: list[dict[str, Any]] = []
    for cuenta in cuentas:
        comportamiento = cuenta.get("comportamiento_contable") or ""
        if cuenta.get("imputable") != "S" and comportamiento:
            errores.append({
                "codigo": cuenta["codigo"],
                "nombre": cuenta["nombre"],
                "problema": "Cuenta no imputable con uso operativo del sistema",
                "accion": "Limpiar comportamiento desde Plan de Cuentas",
                "comportamiento_contable": comportamiento,
            })
        if cuenta.get("imputable") != "S" and _to_bool_int(cuenta.get("permite_imputacion_operativa"), 0):
            errores.append({
                "codigo": cuenta["codigo"],
                "nombre": cuenta["nombre"],
                "problema": "Cuenta no imputable permite imputación operativa",
                "accion": "Normalizar metadata del plan",
                "comportamiento_contable": comportamiento,
            })
        if comportamiento == "BANCO":
            texto = _normalizar_texto_busqueda(cuenta.get("nombre"))
            if any(pal in texto for pal in ["percepcion", "retencion", "impuesto"]):
                advertencias.append({
                    "codigo": cuenta["codigo"],
                    "nombre": cuenta["nombre"],
                    "problema": "Posible comportamiento Banco mal asignado",
                    "accion": "Revisar y limpiar si corresponde",
                    "comportamiento_contable": comportamiento,
                })
        if cuenta.get("imputable") == "S" and not comportamiento:
            pendientes.append(cuenta)
    comportamientos_presentes = {c.get("comportamiento_contable") for c in cuentas if c.get("comportamiento_contable")}
    criticos_faltantes = [
        codigo
        for codigo in ["CAJA", "BANCO", "IVA_CREDITO", "IVA_DEBITO", "CAPITAL_SOCIAL"]
        if codigo not in comportamientos_presentes
    ]
    return {
        "total_cuentas": len(cuentas),
        "imputables": sum(1 for c in cuentas if c.get("imputable") == "S"),
        "no_imputables": sum(1 for c in cuentas if c.get("imputable") != "S"),
        "con_comportamiento": sum(1 for c in cuentas if c.get("comportamiento_contable")),
        "pendientes": len(pendientes),
        "errores": errores,
        "advertencias": advertencias,
        "criticos_faltantes": criticos_faltantes,
    }