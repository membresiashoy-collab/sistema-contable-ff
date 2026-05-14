"""
Diagnostico contable-operativo de Documentos de Tesoreria PRO.

Analiza recibos emitidos y ordenes de pago desde Cobranzas/Pagos en modo
solo lectura. No emite, no anula, no modifica documentos y no genera asientos.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

NIVEL_CRITICO = "CRITICO"
NIVEL_ADVERTENCIA = "ADVERTENCIA"
NIVEL_INFO = "INFO"

ESTADO_CRITICO = "CRITICO"
ESTADO_REQUIERE_REVISION = "REQUIERE_REVISION"
ESTADO_OK = "OK"

TABLAS_BASE = (
    "cobranzas",
    "pagos",
    "cobranzas_imputaciones",
    "pagos_imputaciones",
    "cobranzas_retenciones",
    "pagos_retenciones",
)


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (tabla,),
    ).fetchone()
    return row is not None


def _columnas_tabla(conn: sqlite3.Connection, tabla: str) -> List[str]:
    if not _tabla_existe(conn, tabla):
        return []
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]


def _where_empresa(conn: sqlite3.Connection, tabla: str, empresa_id: Optional[int]) -> Tuple[str, List[Any]]:
    if empresa_id is not None and "empresa_id" in _columnas_tabla(conn, tabla):
        return "empresa_id = ?", [empresa_id]
    return "1 = 1", []


def _count(conn: sqlite3.Connection, tabla: str, where: str = "1 = 1", params: Sequence[Any] = ()) -> int:
    if not _tabla_existe(conn, tabla):
        return 0
    row = conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {where}", tuple(params)).fetchone()
    return int(row[0] or 0)


def _agregar_alerta(
    alertas: List[Dict[str, Any]],
    nivel: str,
    codigo: str,
    mensaje: str,
    detalle: str = "",
    accion_sugerida: str = "",
) -> None:
    alertas.append(
        {
            "nivel": nivel,
            "codigo": codigo,
            "mensaje": mensaje,
            "detalle": detalle,
            "accion_sugerida": accion_sugerida,
        }
    )


def _estado_desde_alertas(alertas: Iterable[Dict[str, Any]]) -> str:
    niveles = {a.get("nivel") for a in alertas}
    if NIVEL_CRITICO in niveles:
        return ESTADO_CRITICO
    if NIVEL_ADVERTENCIA in niveles:
        return ESTADO_REQUIERE_REVISION
    return ESTADO_OK


def _duplicados_por_columna(
    conn: sqlite3.Connection,
    tabla: str,
    columna: str,
    empresa_id: Optional[int],
) -> int:
    if not _tabla_existe(conn, tabla) or columna not in _columnas_tabla(conn, tabla):
        return 0
    where, params = _where_empresa(conn, tabla, empresa_id)
    sql = f"""
        SELECT COUNT(*)
        FROM (
            SELECT {columna}, COUNT(*) cantidad
            FROM {tabla}
            WHERE {where}
              AND TRIM(COALESCE({columna}, '')) <> ''
            GROUP BY {columna}
            HAVING COUNT(*) > 1
        ) d
    """
    row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0] or 0)


def _metricas_documento_operativo(
    conn: sqlite3.Connection,
    tabla: str,
    columna_numero: str,
    columna_importe: str,
    empresa_id: Optional[int],
) -> Dict[str, int]:
    if not _tabla_existe(conn, tabla):
        return {
            "total": 0,
            "sin_numero": 0,
            "duplicados_numero": 0,
            "anulados": 0,
            "importe_no_positivo": 0,
            "sin_tesoreria_operacion": 0,
            "sin_asiento": 0,
        }
    columnas = _columnas_tabla(conn, tabla)
    where, params = _where_empresa(conn, tabla, empresa_id)
    activo = where
    if "estado" in columnas:
        activo += " AND UPPER(COALESCE(estado, '')) <> 'ANULADO'"

    return {
        "total": _count(conn, tabla, where, params),
        "sin_numero": _count(
            conn,
            tabla,
            activo + f" AND TRIM(COALESCE({columna_numero}, '')) = ''" if columna_numero in columnas else "0 = 1",
            params,
        ),
        "duplicados_numero": _duplicados_por_columna(conn, tabla, columna_numero, empresa_id),
        "anulados": _count(
            conn,
            tabla,
            where + " AND UPPER(COALESCE(estado, '')) = 'ANULADO'" if "estado" in columnas else "0 = 1",
            params,
        ),
        "importe_no_positivo": _count(
            conn,
            tabla,
            activo + f" AND COALESCE({columna_importe}, 0) <= 0" if columna_importe in columnas else "0 = 1",
            params,
        ),
        "sin_tesoreria_operacion": _count(
            conn,
            tabla,
            activo + " AND tesoreria_operacion_id IS NULL" if "tesoreria_operacion_id" in columnas else "0 = 1",
            params,
        ),
        "sin_asiento": _count(
            conn,
            tabla,
            activo + " AND asiento_id IS NULL" if "asiento_id" in columnas else "0 = 1",
            params,
        ),
    }


def diagnosticar_documentos_tesoreria(conn: sqlite3.Connection, empresa_id: Optional[int] = 1) -> Dict[str, Any]:
    """Devuelve diagnostico de recibos emitidos y ordenes de pago en modo solo lectura."""
    conn.row_factory = sqlite3.Row
    alertas: List[Dict[str, Any]] = []
    metricas: Dict[str, Any] = {}
    tablas: Dict[str, Dict[str, Any]] = {}

    for tabla in TABLAS_BASE:
        existe = _tabla_existe(conn, tabla)
        tablas[tabla] = {
            "existe": existe,
            "columnas": _columnas_tabla(conn, tabla) if existe else [],
            "registros": _count(conn, tabla) if existe else 0,
        }
        if not existe:
            _agregar_alerta(
                alertas,
                NIVEL_CRITICO,
                f"DOC_TESORERIA_TABLA_FALTANTE_{tabla.upper()}",
                f"Falta la tabla requerida {tabla}.",
                accion_sugerida="Revisar migraciones de Cobranzas/Pagos antes de diagnosticar documentos.",
            )

    tablas["tesoreria_operaciones"] = {
        "existe": _tabla_existe(conn, "tesoreria_operaciones"),
        "columnas": _columnas_tabla(conn, "tesoreria_operaciones") if _tabla_existe(conn, "tesoreria_operaciones") else [],
        "registros": _count(conn, "tesoreria_operaciones") if _tabla_existe(conn, "tesoreria_operaciones") else 0,
    }

    if any(a["nivel"] == NIVEL_CRITICO for a in alertas):
        return {
            "modulo": "Documentos de Tesoreria",
            "version": "PRO_V1_DIAGNOSTICO",
            "solo_lectura": True,
            "empresa_id": empresa_id,
            "estado": _estado_desde_alertas(alertas),
            "metricas": metricas,
            "tablas": tablas,
            "alertas": alertas,
            "acciones_realizadas": [],
        }

    recibos = _metricas_documento_operativo(
        conn, "cobranzas", "numero_recibo", "importe_recibido", empresa_id
    )
    ordenes = _metricas_documento_operativo(
        conn, "pagos", "numero_orden_pago", "importe_pagado", empresa_id
    )
    metricas["recibos_emitidos"] = recibos
    metricas["ordenes_pago_emitidas"] = ordenes
    metricas["imputaciones_cobranzas"] = _count(conn, "cobranzas_imputaciones", *_where_empresa(conn, "cobranzas_imputaciones", empresa_id))
    metricas["imputaciones_pagos"] = _count(conn, "pagos_imputaciones", *_where_empresa(conn, "pagos_imputaciones", empresa_id))
    metricas["retenciones_cobranzas"] = _count(conn, "cobranzas_retenciones", *_where_empresa(conn, "cobranzas_retenciones", empresa_id))
    metricas["retenciones_pagos"] = _count(conn, "pagos_retenciones", *_where_empresa(conn, "pagos_retenciones", empresa_id))

    if recibos["total"] == 0 and ordenes["total"] == 0:
        _agregar_alerta(
            alertas,
            NIVEL_INFO,
            "DOC_TESORERIA_SIN_DOCUMENTOS",
            "No hay recibos ni ordenes de pago en la base analizada.",
            detalle="En una base demo limpia esto es esperable.",
        )

    controles = (
        ("RECIBOS", recibos, "recibos emitidos"),
        ("ORDENES_PAGO", ordenes, "ordenes de pago emitidas"),
    )
    for prefijo, datos, nombre in controles:
        if datos["sin_numero"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                f"DOC_TESORERIA_{prefijo}_SIN_NUMERO",
                f"Hay {nombre} activos sin numero documental.",
                detalle=f"Cantidad detectada: {datos['sin_numero']}",
                accion_sugerida="Revisar numeracion antes de exponer documentos finales.",
            )
        if datos["duplicados_numero"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                f"DOC_TESORERIA_{prefijo}_NUMERO_DUPLICADO",
                f"Hay numeros duplicados en {nombre}.",
                detalle=f"Grupos duplicados detectados: {datos['duplicados_numero']}",
                accion_sugerida="Definir control de unicidad por tipo documental/punto de venta antes de emitir masivamente.",
            )
        if datos["importe_no_positivo"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                f"DOC_TESORERIA_{prefijo}_IMPORTE_INVALIDO",
                f"Hay {nombre} activos con importe menor o igual a cero.",
                detalle=f"Cantidad detectada: {datos['importe_no_positivo']}",
                accion_sugerida="Revisar origen operativo y anulacion/correccion controlada.",
            )
        if datos["sin_tesoreria_operacion"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                f"DOC_TESORERIA_{prefijo}_SIN_OPERACION_TESORERIA",
                f"Hay {nombre} activos sin operacion de Tesoreria vinculada.",
                detalle=f"Cantidad detectada: {datos['sin_tesoreria_operacion']}",
                accion_sugerida="Revisar trazabilidad documental contra Tesoreria.",
            )

    return {
        "modulo": "Documentos de Tesoreria",
        "version": "PRO_V1_DIAGNOSTICO",
        "solo_lectura": True,
        "empresa_id": empresa_id,
        "estado": _estado_desde_alertas(alertas),
        "metricas": metricas,
        "tablas": tablas,
        "alertas": alertas,
        "acciones_realizadas": [],
    }


# Alias explicito.
generar_diagnostico_documentos_tesoreria = diagnosticar_documentos_tesoreria

