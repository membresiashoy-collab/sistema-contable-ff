from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional, Tuple
import re
import sqlite3

import pandas as pd

from database import conectar


TABLA_ACTIVIDADES = "ventas_actividades_empresa"
TABLA_VENTAS = "ventas_comprobantes"

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
        "descripcion": "Actividad base para venta de bienes o mercaderías.",
    },
    {
        "codigo": "VENTA_SERVICIOS",
        "nombre": "Prestación de servicios",
        "tipo_venta": "VENTA_SERVICIOS",
        "tratamiento_iva": "GRAVADO",
        "descripcion": "Actividad base para servicios prestados.",
    },
    {
        "codigo": "VENTA_EXENTA",
        "nombre": "Venta exenta",
        "tipo_venta": "VENTA_EXENTA",
        "tratamiento_iva": "EXENTO",
        "descripcion": "Actividad base para ventas exentas.",
    },
    {
        "codigo": "VENTA_NO_GRAVADA",
        "nombre": "Venta no gravada",
        "tipo_venta": "VENTA_NO_GRAVADA",
        "tratamiento_iva": "NO_GRAVADO",
        "descripcion": "Actividad base para ventas no gravadas.",
    },
]


class ErrorVentasActividades(Exception):
    """Error controlado de actividades de venta."""


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


def _fila_a_dict(cursor: sqlite3.Cursor, fila: Any) -> Optional[dict[str, Any]]:
    if fila is None:
        return None
    columnas = [col[0] for col in cursor.description]
    return dict(zip(columnas, fila))


def _query_uno(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[dict[str, Any]]:
    cur = conn.execute(sql, tuple(params))
    return _fila_a_dict(cur, cur.fetchone())


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
                cuenta_ventas_codigo TEXT,
                cuenta_ventas_nombre TEXT,
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
                     descripcion, activo, usuario_creacion)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
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
        raise ErrorVentasActividades("El código de actividad es obligatorio.")
    if not nombre_final:
        raise ErrorVentasActividades("El nombre de actividad es obligatorio.")

    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)

        conexion.execute(
            f"""
            INSERT INTO {TABLA_ACTIVIDADES}
                (empresa_id, codigo, nombre, tipo_venta, tratamiento_iva,
                 cuenta_ventas_codigo, cuenta_ventas_nombre, descripcion,
                 activo, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                int(empresa_id),
                codigo_final,
                nombre_final,
                tipo_final,
                tratamiento_final,
                _texto(cuenta_ventas_codigo),
                _texto(cuenta_ventas_nombre),
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
            f"Ya existe una actividad de venta con código '{codigo_final}' para esta empresa."
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
        return pd.read_sql_query(sql, conexion, params=params)
    finally:
        if cerrar:
            conexion.close()


def obtener_actividad_venta(
    actividad_id: int,
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)
        fila = _query_uno(
            conexion,
            f"""
            SELECT *
            FROM {TABLA_ACTIVIDADES}
            WHERE id = ?
              AND COALESCE(empresa_id, 1) = ?
              AND COALESCE(activo, 1) = 1
            LIMIT 1
            """,
            (int(actividad_id), int(empresa_id)),
        )
        if not fila:
            raise ErrorVentasActividades("No existe la actividad de venta seleccionada.")
        return fila
    finally:
        if cerrar:
            conexion.close()


def listar_ventas_sin_actividad(
    empresa_id: int = 1,
    archivo: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)

        condiciones = ["COALESCE(empresa_id, 1) = ?", "COALESCE(actividad_venta_id, 0) = 0"]
        params: list[Any] = [int(empresa_id)]

        if archivo:
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
        if "archivo" not in _columnas(conexion, TABLA_VENTAS):
            return []

        filas = conexion.execute(
            f"""
            SELECT DISTINCT archivo
            FROM {TABLA_VENTAS}
            WHERE COALESCE(empresa_id, 1) = ?
              AND COALESCE(TRIM(archivo), '') <> ''
            ORDER BY archivo
            """,
            (int(empresa_id),),
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
            return {"ok": False, "total": 0, "con_actividad": 0, "sin_actividad": 0, "por_actividad": {}}

        asegurar_estructura_ventas_actividades(conexion)

        total = conexion.execute(
            f"SELECT COUNT(*) FROM {TABLA_VENTAS} WHERE COALESCE(empresa_id, 1) = ?",
            (int(empresa_id),),
        ).fetchone()[0]
        con_actividad = conexion.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABLA_VENTAS}
            WHERE COALESCE(empresa_id, 1) = ?
              AND COALESCE(actividad_venta_id, 0) > 0
            """,
            (int(empresa_id),),
        ).fetchone()[0]

        filas = conexion.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(actividad_venta_nombre), ''), 'SIN_ACTIVIDAD') AS actividad,
                   COUNT(*) AS cantidad
            FROM {TABLA_VENTAS}
            WHERE COALESCE(empresa_id, 1) = ?
            GROUP BY COALESCE(NULLIF(TRIM(actividad_venta_nombre), ''), 'SIN_ACTIVIDAD')
            ORDER BY cantidad DESC, actividad
            """,
            (int(empresa_id),),
        ).fetchall()

        return {
            "ok": True,
            "total": int(total),
            "con_actividad": int(con_actividad),
            "sin_actividad": int(total - con_actividad),
            "por_actividad": {fila[0]: int(fila[1]) for fila in filas},
        }
    finally:
        if cerrar:
            conexion.close()


def _validar_ids_ventas(conn: sqlite3.Connection, empresa_id: int, venta_ids: Iterable[int]) -> list[int]:
    ids = sorted({int(v) for v in venta_ids if int(v) > 0})
    if not ids:
        raise ErrorVentasActividades("No se indicaron ventas para asignar actividad.")

    placeholders = ", ".join("?" for _ in ids)
    filas = conn.execute(
        f"""
        SELECT id
        FROM {TABLA_VENTAS}
        WHERE COALESCE(empresa_id, 1) = ?
          AND id IN ({placeholders})
        """,
        (int(empresa_id), *ids),
    ).fetchall()

    encontrados = sorted(int(fila[0]) for fila in filas)
    faltantes = sorted(set(ids) - set(encontrados))
    if faltantes:
        raise ErrorVentasActividades(f"Hay ventas inexistentes para la empresa: {faltantes}")
    return encontrados


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
                "mensaje": "No hay ventas pendientes de actividad para el alcance seleccionado.",
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


__all__ = [
    "TABLA_ACTIVIDADES",
    "TABLA_VENTAS",
    "TIPOS_VENTA",
    "TRATAMIENTOS_IVA",
    "asegurar_estructura_ventas_actividades",
    "sembrar_actividades_base",
    "crear_actividad_venta",
    "listar_actividades_venta",
    "listar_ventas_sin_actividad",
    "listar_archivos_ventas_importadas",
    "obtener_resumen_actividades_ventas",
    "asignar_actividad_a_ventas",
    "asignar_actividad_a_ventas_pendientes",
]

