from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional, Tuple
import re
import sqlite3

import pandas as pd

from database import conectar


TABLA_ACTIVIDADES = "ventas_actividades_empresa"
TABLA_VENTAS = "ventas_comprobantes"
ORIGEN_VENTA = "VENTA_ARCA"

TIPOS_VENTA = {
    "VENTA_MERCADERIAS": "Venta de mercaderías / bienes",
    "VENTA_SERVICIOS": "Prestación de servicios",
    "EXPORTACION_BIENES": "Exportación de bienes",
    "EXPORTACION_SERVICIOS": "Exportación de servicios",
    "VENTA_EXENTA": "Venta exenta",
    "VENTA_NO_GRAVADA": "Venta no gravada",
    "OTRA_ACTIVIDAD": "Otra actividad",
}

TRATAMIENTOS_IVA = {
    "GRAVADO": "Gravado",
    "EXENTO": "Exento",
    "NO_GRAVADO": "No gravado",
    "EXPORTACION": "Exportación",
    "A_REVISAR": "A revisar",
}

ACTIVIDADES_BASE = [
    {
        "codigo": "VENTA_MERCADERIAS",
        "nombre": "Venta de mercaderías / bienes",
        "tipo_venta": "VENTA_MERCADERIAS",
        "tratamiento_iva": "GRAVADO",
        "descripcion": "Agrupación base inicial para venta de bienes o mercaderías.",
    },
    {
        "codigo": "VENTA_SERVICIOS",
        "nombre": "Prestación de servicios",
        "tipo_venta": "VENTA_SERVICIOS",
        "tratamiento_iva": "GRAVADO",
        "descripcion": "Agrupación base inicial para servicios prestados.",
    },
    {
        "codigo": "VENTA_EXENTA",
        "nombre": "Venta exenta",
        "tipo_venta": "VENTA_EXENTA",
        "tratamiento_iva": "EXENTO",
        "descripcion": "Agrupación base inicial para ventas exentas.",
    },
    {
        "codigo": "VENTA_NO_GRAVADA",
        "nombre": "Venta no gravada",
        "tipo_venta": "VENTA_NO_GRAVADA",
        "tratamiento_iva": "NO_GRAVADO",
        "descripcion": "Agrupación base inicial para ventas no gravadas.",
    },
]


class ErrorVentasActividades(Exception):
    """Error controlado de agrupaciones internas de venta."""


def _conexion(conn: Optional[sqlite3.Connection] = None) -> Tuple[sqlite3.Connection, bool]:
    if conn is not None:
        return conn, False
    return conectar(), True


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (tabla,),
    ).fetchone() is not None


def _columnas(conn: sqlite3.Connection, tabla: str) -> set[str]:
    if not _tabla_existe(conn, tabla):
        return set()
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _numero(valor: Any) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    texto = str(valor).strip()
    if texto == "":
        return 0.0
    texto = texto.replace("$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return round(float(texto), 2)
    except Exception:
        return 0.0


def _normalizar_codigo(valor: Any) -> str:
    texto = _texto(valor).upper()
    reemplazos = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    texto = re.sub(r"[^A-Z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto[:80]


def _normalizar_busqueda(valor: Any) -> str:
    texto = _texto(valor).upper()
    reemplazos = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _fila_a_dict(cursor: sqlite3.Cursor, fila: Any) -> Optional[dict[str, Any]]:
    if fila is None:
        return None
    columnas = [col[0] for col in cursor.description]
    return dict(zip(columnas, fila))


def _query_uno(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[dict[str, Any]]:
    cur = conn.execute(sql, tuple(params))
    return _fila_a_dict(cur, cur.fetchone())


def _query_todos(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur = conn.execute(sql, tuple(params))
    columnas = [col[0] for col in cur.description]
    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def _validar_tipo_venta(tipo_venta: str) -> str:
    codigo = _normalizar_codigo(tipo_venta)
    if codigo not in TIPOS_VENTA:
        raise ErrorVentasActividades(f"Tipo de venta inválido: {tipo_venta}")
    return codigo


def _validar_tratamiento_iva(tratamiento: str) -> str:
    codigo = _normalizar_codigo(tratamiento)
    if codigo not in TRATAMIENTOS_IVA:
        raise ErrorVentasActividades(f"Tratamiento IVA inválido: {tratamiento}")
    return codigo


def _where_empresa(tabla_alias: str, columnas: set[str]) -> str:
    if "empresa_id" in columnas:
        return f"COALESCE({tabla_alias}.empresa_id, 1) = ?"
    return "1 = ?"


def asegurar_estructura_ventas_actividades(conn: Optional[sqlite3.Connection] = None) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        conexion.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLA_ACTIVIDADES} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                codigo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                tipo_venta TEXT NOT NULL,
                tratamiento_iva TEXT DEFAULT 'GRAVADO',
                cuenta_ventas_codigo TEXT DEFAULT '',
                cuenta_ventas_nombre TEXT DEFAULT '',
                descripcion TEXT,
                activo INTEGER DEFAULT 1,
                usuario_creacion TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario_ultima_modificacion TEXT,
                fecha_ultima_modificacion TEXT,
                UNIQUE(empresa_id, codigo)
            )
            """
        )

        columnas_agregadas: list[str] = []
        if not _tabla_existe(conexion, TABLA_VENTAS):
            raise ErrorVentasActividades("No existe la tabla ventas_comprobantes.")

        columnas_ventas = _columnas(conexion, TABLA_VENTAS)
        columnas_requeridas = {
            "actividad_venta_id": "INTEGER",
            "actividad_venta_codigo": "TEXT",
            "actividad_venta_nombre": "TEXT",
            "tipo_venta": "TEXT",
            "tratamiento_iva_venta": "TEXT",
            "usuario_clasificacion_venta": "TEXT",
            "fecha_clasificacion_venta": "TEXT",
        }
        for columna, tipo_sql in columnas_requeridas.items():
            if columna not in columnas_ventas:
                conexion.execute(f"ALTER TABLE {TABLA_VENTAS} ADD COLUMN {columna} {tipo_sql}")
                columnas_agregadas.append(columna)

        # Regla central: la agrupación interna no es cuenta contable.
        conexion.execute(
            f"""
            UPDATE {TABLA_ACTIVIDADES}
            SET cuenta_ventas_codigo = '',
                cuenta_ventas_nombre = ''
            WHERE COALESCE(TRIM(cuenta_ventas_codigo), '') <> ''
               OR COALESCE(TRIM(cuenta_ventas_nombre), '') <> ''
            """
        )

        if cerrar:
            conexion.commit()

        return {"ok": True, "columnas_ventas_agregadas": columnas_agregadas}
    finally:
        if cerrar:
            conexion.close()


def sembrar_actividades_base(
    empresa_id: int = 1,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    insertadas = 0
    try:
        asegurar_estructura_ventas_actividades(conexion)
        for actividad in ACTIVIDADES_BASE:
            existe = _query_uno(
                conexion,
                f"""
                SELECT id
                FROM {TABLA_ACTIVIDADES}
                WHERE COALESCE(empresa_id, 1) = ?
                  AND codigo = ?
                LIMIT 1
                """,
                (int(empresa_id), actividad["codigo"]),
            )
            if existe:
                continue
            conexion.execute(
                f"""
                INSERT INTO {TABLA_ACTIVIDADES}
                    (empresa_id, codigo, nombre, tipo_venta, tratamiento_iva,
                     cuenta_ventas_codigo, cuenta_ventas_nombre, descripcion, activo, usuario_creacion)
                VALUES (?, ?, ?, ?, ?, '', '', ?, 1, ?)
                """,
                (
                    int(empresa_id),
                    actividad["codigo"],
                    actividad["nombre"],
                    actividad["tipo_venta"],
                    actividad["tratamiento_iva"],
                    actividad["descripcion"],
                    _texto(usuario) or "sistema",
                ),
            )
            insertadas += 1

        if cerrar:
            conexion.commit()

        return {"ok": True, "insertadas": insertadas}
    finally:
        if cerrar:
            conexion.close()


def crear_actividad_venta(
    empresa_id: int,
    codigo: str,
    nombre: str,
    tipo_venta: str,
    tratamiento_iva: str = "GRAVADO",
    cuenta_ventas_codigo: str = "",
    cuenta_ventas_nombre: str = "",
    descripcion: str = "",
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    codigo_final = _normalizar_codigo(codigo or nombre)
    nombre_final = _texto(nombre)
    tipo_final = _validar_tipo_venta(tipo_venta)
    tratamiento_final = _validar_tratamiento_iva(tratamiento_iva)

    if not codigo_final:
        raise ErrorVentasActividades("El código de agrupación es obligatorio.")
    if not nombre_final:
        raise ErrorVentasActividades("El nombre de agrupación es obligatorio.")

    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)

        conexion.execute(
            f"""
            INSERT INTO {TABLA_ACTIVIDADES}
                (empresa_id, codigo, nombre, tipo_venta, tratamiento_iva,
                 cuenta_ventas_codigo, cuenta_ventas_nombre, descripcion,
                 activo, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, '', '', ?, 1, ?)
            """,
            (
                int(empresa_id),
                codigo_final,
                nombre_final,
                tipo_final,
                tratamiento_final,
                _texto(descripcion),
                _texto(usuario) or "sistema",
            ),
        )

        actividad_id = conexion.execute("SELECT last_insert_rowid()").fetchone()[0]

        if cerrar:
            conexion.commit()

        return {
            "ok": True,
            "actividad_id": int(actividad_id),
            "codigo": codigo_final,
            "nombre": nombre_final,
            "tipo_venta": tipo_final,
            "tratamiento_iva": tratamiento_final,
        }
    except sqlite3.IntegrityError:
        raise ErrorVentasActividades(
            f"Ya existe una agrupación de venta con código '{codigo_final}' para esta empresa."
        )
    finally:
        if cerrar:
            conexion.close()


def listar_actividades_venta(
    empresa_id: int = 1,
    solo_activas: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        sembrar_actividades_base(empresa_id=int(empresa_id), conn=conexion)

        condiciones = ["COALESCE(empresa_id, 1) = ?"]
        params: list[Any] = [int(empresa_id)]

        if solo_activas:
            condiciones.append("COALESCE(activo, 1) = 1")

        sql = f"""
            SELECT *
            FROM {TABLA_ACTIVIDADES}
            WHERE {' AND '.join(condiciones)}
            ORDER BY activo DESC, nombre
        """
        df = pd.read_sql_query(sql, conexion, params=params)
        for col in ("cuenta_ventas_codigo", "cuenta_ventas_nombre"):
            if col in df.columns:
                df[col] = ""
        return df
    finally:
        if cerrar:
            conexion.close()


def obtener_actividad_venta(
    actividad_id: int,
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
    solo_activa: bool = True,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        condiciones = [
            "id = ?",
            "COALESCE(empresa_id, 1) = ?",
        ]
        params: list[Any] = [int(actividad_id), int(empresa_id)]
        if solo_activa:
            condiciones.append("COALESCE(activo, 1) = 1")

        fila = _query_uno(
            conexion,
            f"""
            SELECT *
            FROM {TABLA_ACTIVIDADES}
            WHERE {' AND '.join(condiciones)}
            LIMIT 1
            """,
            params,
        )
        if not fila:
            raise ErrorVentasActividades("No existe la agrupación de venta seleccionada.")
        fila["cuenta_ventas_codigo"] = ""
        fila["cuenta_ventas_nombre"] = ""
        return fila
    finally:
        if cerrar:
            conexion.close()


def _referencia_venta(empresa_id: int, venta_id: int) -> str:
    return f"VENTA:{int(empresa_id)}:{int(venta_id)}"


def _venta_tiene_asiento_propuesto(conn: sqlite3.Connection, empresa_id: int, venta_id: int) -> bool:
    referencia = _referencia_venta(empresa_id, venta_id)

    if _tabla_existe(conn, "asientos_origen"):
        fila = conn.execute(
            """
            SELECT 1
            FROM asientos_origen
            WHERE COALESCE(empresa_id, 1) = ?
              AND tipo_origen = ?
              AND referencia = ?
              AND COALESCE(estado, '') <> 'ANULADO'
            LIMIT 1
            """,
            (int(empresa_id), ORIGEN_VENTA, referencia),
        ).fetchone()
        if fila is not None:
            return True

    if _tabla_existe(conn, "asientos_propuestos"):
        columnas = _columnas(conn, "asientos_propuestos")
        if {"empresa_id", "origen", "referencia"}.issubset(columnas):
            fila = conn.execute(
                """
                SELECT 1
                FROM asientos_propuestos
                WHERE COALESCE(empresa_id, 1) = ?
                  AND origen = ?
                  AND referencia = ?
                  AND COALESCE(estado, '') <> 'ANULADO'
                LIMIT 1
                """,
                (int(empresa_id), ORIGEN_VENTA, referencia),
            ).fetchone()
            if fila is not None:
                return True

    return False


def _ventas_con_asiento_propuesto(
    conn: sqlite3.Connection,
    empresa_id: int,
    venta_ids: Iterable[int],
) -> list[int]:
    bloqueadas: list[int] = []
    for venta_id in sorted({int(v) for v in venta_ids if int(v) > 0}):
        if _venta_tiene_asiento_propuesto(conn, int(empresa_id), int(venta_id)):
            bloqueadas.append(int(venta_id))
    return bloqueadas


def _validar_ids_ventas(conn: sqlite3.Connection, empresa_id: int, venta_ids: Iterable[int]) -> list[int]:
    ids = sorted({int(v) for v in venta_ids if int(v) > 0})
    if not ids:
        raise ErrorVentasActividades("No se indicaron ventas para actualizar.")

    placeholders = ", ".join("?" for _ in ids)
    columnas_ventas = _columnas(conn, TABLA_VENTAS)
    where_empresa = "COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas_ventas else "1 = ?"

    filas = conn.execute(
        f"""
        SELECT id
        FROM {TABLA_VENTAS}
        WHERE {where_empresa}
          AND id IN ({placeholders})
        """,
        (int(empresa_id), *ids),
    ).fetchall()

    encontrados = sorted(int(fila[0]) for fila in filas)
    faltantes = sorted(set(ids) - set(encontrados))
    if faltantes:
        raise ErrorVentasActividades(f"Hay ventas inexistentes para la empresa: {faltantes}")
    return encontrados


def listar_ventas_sin_actividad(
    empresa_id: int = 1,
    archivo: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)

        columnas_ventas = _columnas(conexion, TABLA_VENTAS)
        condiciones = ["COALESCE(actividad_venta_id, 0) = 0"]
        params: list[Any] = []

        if "empresa_id" in columnas_ventas:
            condiciones.insert(0, "COALESCE(empresa_id, 1) = ?")
            params.append(int(empresa_id))

        if archivo and "archivo" in columnas_ventas:
            condiciones.append("archivo = ?")
            params.append(archivo)

        sql = f"""
            SELECT *
            FROM {TABLA_VENTAS}
            WHERE {' AND '.join(condiciones)}
            ORDER BY fecha, id
        """
        return pd.read_sql_query(sql, conexion, params=params)
    finally:
        if cerrar:
            conexion.close()


def listar_archivos_ventas_importadas(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> list[str]:
    conexion, cerrar = _conexion(conn)
    try:
        if not _tabla_existe(conexion, TABLA_VENTAS):
            return []
        columnas_ventas = _columnas(conexion, TABLA_VENTAS)
        if "archivo" not in columnas_ventas:
            return []

        condiciones = ["COALESCE(TRIM(archivo), '') <> ''"]
        params: list[Any] = []
        if "empresa_id" in columnas_ventas:
            condiciones.insert(0, "COALESCE(empresa_id, 1) = ?")
            params.append(int(empresa_id))

        filas = conexion.execute(
            f"""
            SELECT DISTINCT archivo
            FROM {TABLA_VENTAS}
            WHERE {' AND '.join(condiciones)}
            ORDER BY archivo
            """,
            tuple(params),
        ).fetchall()
        return [_texto(fila[0]) for fila in filas if _texto(fila[0])]
    finally:
        if cerrar:
            conexion.close()


def obtener_resumen_actividades_ventas(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        if not _tabla_existe(conexion, TABLA_VENTAS):
            return {
                "ok": False,
                "total": 0,
                "con_actividad": 0,
                "sin_actividad": 0,
                "por_actividad": {},
                "detalle_por_actividad": {},
            }

        asegurar_estructura_ventas_actividades(conexion)
        columnas_ventas = _columnas(conexion, TABLA_VENTAS)

        condiciones = []
        params: list[Any] = []
        if "empresa_id" in columnas_ventas:
            condiciones.append("COALESCE(empresa_id, 1) = ?")
            params.append(int(empresa_id))
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

        total = conexion.execute(
            f"SELECT COUNT(*) FROM {TABLA_VENTAS} {where}",
            tuple(params),
        ).fetchone()[0]

        con_actividad = conexion.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABLA_VENTAS}
            {where}
            {'AND' if where else 'WHERE'} COALESCE(actividad_venta_id, 0) > 0
            """,
            tuple(params),
        ).fetchone()[0]

        def campo_numerico(campo: str) -> str:
            if campo in columnas_ventas:
                return f"CAST(COALESCE({campo}, 0) AS REAL)"
            return "0"

        filas = conexion.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(actividad_venta_nombre), ''), 'SIN_ACTIVIDAD') AS actividad,
                   COUNT(*) AS cantidad,
                   ROUND(COALESCE(SUM({campo_numerico('neto')}), 0), 2) AS neto,
                   ROUND(COALESCE(SUM({campo_numerico('iva')}), 0), 2) AS iva,
                   ROUND(COALESCE(SUM({campo_numerico('total')}), 0), 2) AS total
            FROM {TABLA_VENTAS}
            {where}
            GROUP BY COALESCE(NULLIF(TRIM(actividad_venta_nombre), ''), 'SIN_ACTIVIDAD')
            ORDER BY cantidad DESC, actividad
            """,
            tuple(params),
        ).fetchall()

        por_actividad = {fila[0]: int(fila[1]) for fila in filas}
        detalle_por_actividad = {
            fila[0]: {
                "cantidad": int(fila[1]),
                "neto": round(float(fila[2] or 0), 2),
                "iva": round(float(fila[3] or 0), 2),
                "total": round(float(fila[4] or 0), 2),
            }
            for fila in filas
        }

        return {
            "ok": True,
            "total": int(total),
            "con_actividad": int(con_actividad),
            "sin_actividad": int(total - con_actividad),
            "por_actividad": por_actividad,
            "detalle_por_actividad": detalle_por_actividad,
        }
    finally:
        if cerrar:
            conexion.close()


def obtener_resumen_ventas_por_agrupacion(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)

        if not _tabla_existe(conexion, TABLA_VENTAS):
            return pd.DataFrame(
                columns=[
                    "agrupacion_codigo",
                    "agrupacion_nombre",
                    "actividad_venta_codigo",
                    "actividad_venta_nombre",
                    "cantidad",
                    "cantidad_comprobantes",
                    "neto",
                    "iva",
                    "total",
                ]
            )

        columnas = _columnas(conexion, TABLA_VENTAS)
        campo_codigo = "actividad_venta_codigo" if "actividad_venta_codigo" in columnas else "''"
        campo_nombre = "actividad_venta_nombre" if "actividad_venta_nombre" in columnas else "''"

        condiciones = []
        params: list[Any] = []
        if "empresa_id" in columnas:
            condiciones.append("COALESCE(empresa_id, 1) = ?")
            params.append(int(empresa_id))
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

        def campo_numerico(campo: str) -> str:
            if campo in columnas:
                return f"CAST(COALESCE({campo}, 0) AS REAL)"
            return "0"

        sql = f"""
            SELECT
                COALESCE(NULLIF(TRIM({campo_codigo}), ''), 'SIN_AGRUPACION') AS agrupacion_codigo,
                COALESCE(NULLIF(TRIM({campo_nombre}), ''), 'Sin agrupación') AS agrupacion_nombre,
                COUNT(*) AS cantidad,
                ROUND(COALESCE(SUM({campo_numerico('neto')}), 0), 2) AS neto,
                ROUND(COALESCE(SUM({campo_numerico('iva')}), 0), 2) AS iva,
                ROUND(COALESCE(SUM({campo_numerico('total')}), 0), 2) AS total
            FROM {TABLA_VENTAS}
            {where}
            GROUP BY
                COALESCE(NULLIF(TRIM({campo_codigo}), ''), 'SIN_AGRUPACION'),
                COALESCE(NULLIF(TRIM({campo_nombre}), ''), 'Sin agrupación')
            ORDER BY agrupacion_nombre
        """

        df = pd.read_sql_query(sql, conexion, params=params)

        if df.empty:
            return df

        df["cantidad_comprobantes"] = df["cantidad"]
        df["actividad_venta_codigo"] = df["agrupacion_codigo"]
        df["actividad_venta_nombre"] = df["agrupacion_nombre"]

        columnas_finales = [
            "agrupacion_codigo",
            "agrupacion_nombre",
            "actividad_venta_codigo",
            "actividad_venta_nombre",
            "cantidad",
            "cantidad_comprobantes",
            "neto",
            "iva",
            "total",
        ]

        return df[columnas_finales]
    finally:
        if cerrar:
            conexion.close()


def asignar_actividad_a_ventas(
    empresa_id: int,
    venta_ids: Iterable[int],
    actividad_id: int,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        actividad = obtener_actividad_venta(
            actividad_id=int(actividad_id),
            empresa_id=int(empresa_id),
            conn=conexion,
        )
        ids = _validar_ids_ventas(conexion, int(empresa_id), venta_ids)

        ahora = datetime.now().isoformat(timespec="seconds")
        placeholders = ", ".join("?" for _ in ids)

        conexion.execute(
            f"""
            UPDATE {TABLA_VENTAS}
            SET actividad_venta_id = ?,
                actividad_venta_codigo = ?,
                actividad_venta_nombre = ?,
                tipo_venta = ?,
                tratamiento_iva_venta = ?,
                usuario_clasificacion_venta = ?,
                fecha_clasificacion_venta = ?
            WHERE COALESCE(empresa_id, 1) = ?
              AND id IN ({placeholders})
            """,
            (
                int(actividad["id"]),
                _texto(actividad["codigo"]),
                _texto(actividad["nombre"]),
                _texto(actividad["tipo_venta"]),
                _texto(actividad["tratamiento_iva"]),
                _texto(usuario) or "sistema",
                ahora,
                int(empresa_id),
                *ids,
            ),
        )

        if cerrar:
            conexion.commit()

        return {
            "ok": True,
            "ventas_actualizadas": len(ids),
            "actividad_id": int(actividad["id"]),
            "actividad_codigo": _texto(actividad["codigo"]),
            "actividad_nombre": _texto(actividad["nombre"]),
            "ids": ids,
        }
    finally:
        if cerrar:
            conexion.close()


def asignar_actividad_a_ventas_pendientes(
    empresa_id: int,
    actividad_id: int,
    archivo: Optional[str] = None,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        pendientes = listar_ventas_sin_actividad(
            empresa_id=int(empresa_id),
            archivo=archivo,
            conn=conexion,
        )
        if pendientes.empty:
            actividad = obtener_actividad_venta(int(actividad_id), int(empresa_id), conn=conexion)
            return {
                "ok": True,
                "ventas_actualizadas": 0,
                "actividad_id": int(actividad["id"]),
                "actividad_codigo": _texto(actividad["codigo"]),
                "actividad_nombre": _texto(actividad["nombre"]),
                "ids": [],
                "mensaje": "No hay ventas pendientes de agrupación para el alcance seleccionado.",
            }

        return asignar_actividad_a_ventas(
            empresa_id=int(empresa_id),
            venta_ids=[int(v) for v in pendientes["id"].tolist()],
            actividad_id=int(actividad_id),
            usuario=usuario,
            conn=conexion,
        )
    finally:
        if cerrar:
            conexion.close()


def editar_agrupacion_venta(
    empresa_id: int,
    actividad_id: int,
    codigo: str,
    nombre: str,
    tipo_venta: str,
    tratamiento_iva: str,
    descripcion: str = "",
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """
    Edita una agrupación interna de venta.

    Regla:
    - Código/nombre/descripción son reportables y pueden actualizar ventas asociadas.
    - Tipo/tratamiento pueden afectar propuestas contables futuras.
    - Si hay ventas asociadas con propuesta no anulada en Bandeja, no se cambia
      el tipo/tratamiento de esas operaciones de forma silenciosa.
    """
    codigo_final = _normalizar_codigo(codigo or nombre)
    nombre_final = _texto(nombre)
    tipo_final = _validar_tipo_venta(tipo_venta)
    tratamiento_final = _validar_tratamiento_iva(tratamiento_iva)

    if not codigo_final:
        raise ErrorVentasActividades("El código de agrupación es obligatorio.")
    if not nombre_final:
        raise ErrorVentasActividades("El nombre de agrupación es obligatorio.")

    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        actual = obtener_actividad_venta(
            actividad_id=int(actividad_id),
            empresa_id=int(empresa_id),
            conn=conexion,
            solo_activa=False,
        )

        cambia_tipo = (
            _texto(actual.get("tipo_venta")) != tipo_final
            or _texto(actual.get("tratamiento_iva")) != tratamiento_final
        )

        ventas_asociadas = _query_todos(
            conexion,
            f"""
            SELECT id, fecha, tipo, punto_venta, numero, cliente, cuit, archivo
            FROM {TABLA_VENTAS}
            WHERE COALESCE(empresa_id, 1) = ?
              AND COALESCE(actividad_venta_id, 0) = ?
            ORDER BY fecha, id
            """,
            (int(empresa_id), int(actividad_id)),
        )
        ids_asociados = [int(v["id"]) for v in ventas_asociadas]
        ids_bloqueados = _ventas_con_asiento_propuesto(conexion, int(empresa_id), ids_asociados)

        if cambia_tipo and ids_bloqueados:
            return {
                "ok": False,
                "estado": "BLOQUEADO_ASIENTOS_PROPUESTOS",
                "mensaje": (
                    "La agrupación tiene ventas con propuesta contable no anulada en Bandeja. "
                    "No se modifica el tipo fiscal/contable ni el tratamiento IVA de esas operaciones. "
                    "Revise o anule la propuesta de cada comprobante puntual que necesite corregir; "
                    "las demás ventas no se ven afectadas."
                ),
                "ventas_bloqueadas": ids_bloqueados,
                "ventas_bloqueadas_cantidad": len(ids_bloqueados),
            }

        ahora = datetime.now().isoformat(timespec="seconds")
        conexion.execute(
            f"""
            UPDATE {TABLA_ACTIVIDADES}
            SET codigo = ?,
                nombre = ?,
                tipo_venta = ?,
                tratamiento_iva = ?,
                cuenta_ventas_codigo = '',
                cuenta_ventas_nombre = '',
                descripcion = ?,
                usuario_ultima_modificacion = ?,
                fecha_ultima_modificacion = ?
            WHERE id = ?
              AND COALESCE(empresa_id, 1) = ?
            """,
            (
                codigo_final,
                nombre_final,
                tipo_final,
                tratamiento_final,
                _texto(descripcion),
                _texto(usuario) or "sistema",
                ahora,
                int(actividad_id),
                int(empresa_id),
            ),
        )

        conexion.execute(
            f"""
            UPDATE {TABLA_VENTAS}
            SET actividad_venta_codigo = ?,
                actividad_venta_nombre = ?,
                tipo_venta = ?,
                tratamiento_iva_venta = ?,
                usuario_clasificacion_venta = ?,
                fecha_clasificacion_venta = ?
            WHERE COALESCE(empresa_id, 1) = ?
              AND COALESCE(actividad_venta_id, 0) = ?
            """,
            (
                codigo_final,
                nombre_final,
                tipo_final,
                tratamiento_final,
                _texto(usuario) or "sistema",
                ahora,
                int(empresa_id),
                int(actividad_id),
            ),
        )

        if cerrar:
            conexion.commit()

        return {
            "ok": True,
            "estado": "ACTUALIZADO",
            "actividad_id": int(actividad_id),
            "codigo": codigo_final,
            "nombre": nombre_final,
            "ventas_actualizadas": len(ids_asociados),
            "mensaje": "Agrupación actualizada.",
        }
    except sqlite3.IntegrityError:
        raise ErrorVentasActividades(
            f"Ya existe una agrupación de venta con código '{codigo_final}' para esta empresa."
        )
    finally:
        if cerrar:
            conexion.close()


def desactivar_agrupacion_venta(
    empresa_id: int,
    actividad_id: int,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        ahora = datetime.now().isoformat(timespec="seconds")
        conexion.execute(
            f"""
            UPDATE {TABLA_ACTIVIDADES}
            SET activo = 0,
                usuario_ultima_modificacion = ?,
                fecha_ultima_modificacion = ?
            WHERE id = ?
              AND COALESCE(empresa_id, 1) = ?
            """,
            (_texto(usuario) or "sistema", ahora, int(actividad_id), int(empresa_id)),
        )
        if cerrar:
            conexion.commit()
        return {"ok": True, "estado": "DESACTIVADO", "actividad_id": int(actividad_id)}
    finally:
        if cerrar:
            conexion.close()


def reactivar_agrupacion_venta(
    empresa_id: int,
    actividad_id: int,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        ahora = datetime.now().isoformat(timespec="seconds")
        conexion.execute(
            f"""
            UPDATE {TABLA_ACTIVIDADES}
            SET activo = 1,
                usuario_ultima_modificacion = ?,
                fecha_ultima_modificacion = ?
            WHERE id = ?
              AND COALESCE(empresa_id, 1) = ?
            """,
            (_texto(usuario) or "sistema", ahora, int(actividad_id), int(empresa_id)),
        )
        if cerrar:
            conexion.commit()
        return {"ok": True, "estado": "REACTIVADO", "actividad_id": int(actividad_id)}
    finally:
        if cerrar:
            conexion.close()


def listar_ventas_por_agrupacion(
    empresa_id: int = 1,
    actividad_id: Optional[int] = None,
    archivo: Optional[str] = None,
    busqueda: str = "",
    incluir_sin_agrupacion: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        columnas = _columnas(conexion, TABLA_VENTAS)

        condiciones: list[str] = []
        params: list[Any] = []

        if "empresa_id" in columnas:
            condiciones.append("COALESCE(empresa_id, 1) = ?")
            params.append(int(empresa_id))

        if actividad_id is not None:
            actividad_id_int = int(actividad_id)
            if actividad_id_int > 0:
                condiciones.append("COALESCE(actividad_venta_id, 0) = ?")
                params.append(actividad_id_int)
            elif actividad_id_int == 0:
                condiciones.append("COALESCE(actividad_venta_id, 0) = 0")
            elif not incluir_sin_agrupacion:
                condiciones.append("COALESCE(actividad_venta_id, 0) > 0")
        elif not incluir_sin_agrupacion:
            condiciones.append("COALESCE(actividad_venta_id, 0) > 0")

        if archivo and "archivo" in columnas:
            condiciones.append("archivo = ?")
            params.append(_texto(archivo))

        sql = f"""
            SELECT *
            FROM {TABLA_VENTAS}
            {'WHERE ' + ' AND '.join(condiciones) if condiciones else ''}
            ORDER BY fecha, id
        """

        df = pd.read_sql_query(sql, conexion, params=params)

        if df.empty:
            return df

        filtro = _normalizar_busqueda(busqueda)
        if filtro:
            texto = pd.Series([""] * len(df), index=df.index)
            for columna in ("cliente", "cuit", "tipo", "numero", "punto_venta", "archivo", "actividad_venta_nombre", "actividad_venta_codigo"):
                if columna in df.columns:
                    texto = texto + " " + df[columna].astype(str)
            df = df[texto.apply(_normalizar_busqueda).str.contains(filtro, na=False)].copy()

        if df.empty:
            return df

        df["tiene_asiento_propuesto"] = [
            _venta_tiene_asiento_propuesto(conexion, int(empresa_id), int(venta_id))
            for venta_id in df["id"].tolist()
        ]
        df["estado_correccion"] = df["tiene_asiento_propuesto"].apply(
            lambda tiene: "Bloqueada por propuesta en Bandeja" if tiene else "Editable"
        )
        return df
    finally:
        if cerrar:
            conexion.close()


def reasignar_agrupacion_ventas(
    empresa_id: int,
    venta_ids: Iterable[int],
    actividad_id: int,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        actividad = obtener_actividad_venta(
            actividad_id=int(actividad_id),
            empresa_id=int(empresa_id),
            conn=conexion,
        )
        ids = _validar_ids_ventas(conexion, int(empresa_id), venta_ids)
        bloqueadas = _ventas_con_asiento_propuesto(conexion, int(empresa_id), ids)
        actualizables = [venta_id for venta_id in ids if venta_id not in set(bloqueadas)]

        ahora = datetime.now().isoformat(timespec="seconds")

        if actualizables:
            placeholders = ", ".join("?" for _ in actualizables)
            conexion.execute(
                f"""
                UPDATE {TABLA_VENTAS}
                SET actividad_venta_id = ?,
                    actividad_venta_codigo = ?,
                    actividad_venta_nombre = ?,
                    tipo_venta = ?,
                    tratamiento_iva_venta = ?,
                    usuario_clasificacion_venta = ?,
                    fecha_clasificacion_venta = ?
                WHERE COALESCE(empresa_id, 1) = ?
                  AND id IN ({placeholders})
                """,
                (
                    int(actividad["id"]),
                    _texto(actividad["codigo"]),
                    _texto(actividad["nombre"]),
                    _texto(actividad["tipo_venta"]),
                    _texto(actividad["tratamiento_iva"]),
                    _texto(usuario) or "sistema",
                    ahora,
                    int(empresa_id),
                    *actualizables,
                ),
            )

        if cerrar:
            conexion.commit()

        return {
            "ok": bool(actualizables),
            "estado": "ACTUALIZADO_PARCIAL" if bloqueadas and actualizables else ("BLOQUEADO_ASIENTOS_PROPUESTOS" if bloqueadas else "ACTUALIZADO"),
            "ventas_solicitadas": len(ids),
            "ventas_actualizadas": len(actualizables),
            "ventas_bloqueadas": bloqueadas,
            "ventas_bloqueadas_cantidad": len(bloqueadas),
            "actividad_id": int(actividad["id"]),
            "actividad_codigo": _texto(actividad["codigo"]),
            "actividad_nombre": _texto(actividad["nombre"]),
            "mensaje": (
                "Se actualizaron las ventas editables. "
                "Las ventas bloqueadas tienen propuesta contable en Bandeja y deben revisarse por comprobante puntual."
                if bloqueadas and actualizables
                else (
                    "Las ventas seleccionadas tienen propuesta contable en Bandeja. "
                    "Revise o anule cada propuesta puntual antes de cambiar su clasificación fiscal/contable."
                    if bloqueadas
                    else "Ventas reasignadas correctamente."
                )
            ),
        }
    finally:
        if cerrar:
            conexion.close()


def desasignar_agrupacion_ventas(
    empresa_id: int,
    venta_ids: Iterable[int],
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        ids = _validar_ids_ventas(conexion, int(empresa_id), venta_ids)
        bloqueadas = _ventas_con_asiento_propuesto(conexion, int(empresa_id), ids)
        actualizables = [venta_id for venta_id in ids if venta_id not in set(bloqueadas)]
        ahora = datetime.now().isoformat(timespec="seconds")

        if actualizables:
            placeholders = ", ".join("?" for _ in actualizables)
            conexion.execute(
                f"""
                UPDATE {TABLA_VENTAS}
                SET actividad_venta_id = NULL,
                    actividad_venta_codigo = '',
                    actividad_venta_nombre = '',
                    tipo_venta = '',
                    tratamiento_iva_venta = '',
                    usuario_clasificacion_venta = ?,
                    fecha_clasificacion_venta = ?
                WHERE COALESCE(empresa_id, 1) = ?
                  AND id IN ({placeholders})
                """,
                (
                    _texto(usuario) or "sistema",
                    ahora,
                    int(empresa_id),
                    *actualizables,
                ),
            )

        if cerrar:
            conexion.commit()

        return {
            "ok": bool(actualizables),
            "estado": "ACTUALIZADO_PARCIAL" if bloqueadas and actualizables else ("BLOQUEADO_ASIENTOS_PROPUESTOS" if bloqueadas else "ACTUALIZADO"),
            "ventas_solicitadas": len(ids),
            "ventas_actualizadas": len(actualizables),
            "ventas_bloqueadas": bloqueadas,
            "ventas_bloqueadas_cantidad": len(bloqueadas),
            "mensaje": (
                "Se desagruparon las ventas editables. "
                "Las ventas bloqueadas tienen propuesta contable en Bandeja y deben revisarse por comprobante puntual."
                if bloqueadas and actualizables
                else (
                    "Las ventas seleccionadas tienen propuesta contable en Bandeja. "
                    "Revise o anule cada propuesta puntual antes de desagrupar."
                    if bloqueadas
                    else "Ventas desagrupadas correctamente."
                )
            ),
        }
    finally:
        if cerrar:
            conexion.close()


__all__ = [
    "TABLA_ACTIVIDADES",
    "TABLA_VENTAS",
    "TIPOS_VENTA",
    "TRATAMIENTOS_IVA",
    "asegurar_estructura_ventas_actividades",
    "sembrar_actividades_base",
    "crear_actividad_venta",
    "listar_actividades_venta",
    "obtener_actividad_venta",
    "listar_ventas_sin_actividad",
    "listar_archivos_ventas_importadas",
    "obtener_resumen_actividades_ventas",
    "obtener_resumen_ventas_por_agrupacion",
    "asignar_actividad_a_ventas",
    "asignar_actividad_a_ventas_pendientes",
    "editar_agrupacion_venta",
    "desactivar_agrupacion_venta",
    "reactivar_agrupacion_venta",
    "listar_ventas_por_agrupacion",
    "reasignar_agrupacion_ventas",
    "desasignar_agrupacion_ventas",
]