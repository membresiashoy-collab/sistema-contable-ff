"""
Parametrizacion asistida de Documentos de Tesoreria PRO.

Servicio de solo lectura para sugerir controles sobre recibos emitidos,
ordenes de pago, numeracion, trazabilidad e imputaciones documentales.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ESTADO_OK = "OK"
ESTADO_REQUIERE_PARAMETRIZACION = "REQUIERE_PARAMETRIZACION"
ESTADO_ESTRUCTURA_INCOMPLETA = "ESTRUCTURA_INCOMPLETA"

CASOS_DOCUMENTOS: List[Dict[str, Any]] = [
    {
        "codigo": "RECIBO_COBRANZA",
        "descripcion": "Recibo emitido desde una cobranza registrada.",
        "tipo_documento": "RECIBO",
        "origen_operativo": "COBRANZAS",
        "prioridad": "ALTA",
        "columnas_requeridas": ["numero_recibo", "fecha_cobranza", "importe_recibido", "estado"],
    },
    {
        "codigo": "ORDEN_PAGO_PAGO",
        "descripcion": "Orden de pago emitida desde un pago registrado.",
        "tipo_documento": "ORDEN_PAGO",
        "origen_operativo": "PAGOS",
        "prioridad": "ALTA",
        "columnas_requeridas": ["numero_orden_pago", "fecha_pago", "importe_pagado", "estado"],
    },
    {
        "codigo": "NUMERACION_RECIBOS",
        "descripcion": "Control de numeracion de recibos emitidos.",
        "tipo_documento": "RECIBO",
        "origen_operativo": "COBRANZAS",
        "prioridad": "ALTA",
        "columnas_requeridas": ["numero_recibo"],
    },
    {
        "codigo": "NUMERACION_ORDENES_PAGO",
        "descripcion": "Control de numeracion de ordenes de pago emitidas.",
        "tipo_documento": "ORDEN_PAGO",
        "origen_operativo": "PAGOS",
        "prioridad": "ALTA",
        "columnas_requeridas": ["numero_orden_pago"],
    },
    {
        "codigo": "TRAZABILIDAD_TESORERIA",
        "descripcion": "Vinculo documental con operaciones de Tesoreria.",
        "tipo_documento": "AMBOS",
        "origen_operativo": "TESORERIA",
        "prioridad": "ALTA",
        "columnas_requeridas": ["tesoreria_operacion_id"],
    },
    {
        "codigo": "ANULACION_CONTROLADA_DOCUMENTOS",
        "descripcion": "Anulacion logica con motivo y fecha de anulacion.",
        "tipo_documento": "AMBOS",
        "origen_operativo": "COBRANZAS_PAGOS",
        "prioridad": "ALTA",
        "columnas_requeridas": ["estado", "motivo_anulacion", "fecha_anulacion"],
    },
    {
        "codigo": "IMPUTACIONES_DOCUMENTALES",
        "descripcion": "Detalle documental de imputaciones contra cuenta corriente.",
        "tipo_documento": "AMBOS",
        "origen_operativo": "CUENTAS_CORRIENTES",
        "prioridad": "MEDIA",
        "columnas_requeridas": ["cuenta_corriente_id", "importe_imputado"],
    },
    {
        "codigo": "RETENCIONES_DOCUMENTALES",
        "descripcion": "Detalle documental de retenciones vinculadas a cobros/pagos.",
        "tipo_documento": "AMBOS",
        "origen_operativo": "RETENCIONES",
        "prioridad": "MEDIA",
        "columnas_requeridas": ["tipo_retencion", "importe"],
    },
    {
        "codigo": "EXPORTACION_HTML_DOCUMENTO",
        "descripcion": "Generacion de comprobante HTML descargable.",
        "tipo_documento": "AMBOS",
        "origen_operativo": "DOCUMENTOS_TESORERIA_SERVICE",
        "prioridad": "MEDIA",
        "columnas_requeridas": [],
    },
]


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


def _tabla_y_columnas_para_caso(codigo: str) -> List[Tuple[str, List[str]]]:
    if codigo in {"RECIBO_COBRANZA", "NUMERACION_RECIBOS"}:
        return [("cobranzas", [])]
    if codigo in {"ORDEN_PAGO_PAGO", "NUMERACION_ORDENES_PAGO"}:
        return [("pagos", [])]
    if codigo == "TRAZABILIDAD_TESORERIA":
        return [("cobranzas", ["tesoreria_operacion_id"]), ("pagos", ["tesoreria_operacion_id"]), ("tesoreria_operaciones", [])]
    if codigo == "ANULACION_CONTROLADA_DOCUMENTOS":
        return [("cobranzas", ["estado", "motivo_anulacion", "fecha_anulacion"]), ("pagos", ["estado", "motivo_anulacion", "fecha_anulacion"])]
    if codigo == "IMPUTACIONES_DOCUMENTALES":
        return [("cobranzas_imputaciones", ["cuenta_corriente_id", "importe_imputado"]), ("pagos_imputaciones", ["cuenta_corriente_id", "importe_imputado"])]
    if codigo == "RETENCIONES_DOCUMENTALES":
        return [("cobranzas_retenciones", ["tipo_retencion", "importe"]), ("pagos_retenciones", ["tipo_retencion", "importe"])]
    return []


def _servicio_documentos_existe() -> bool:
    return Path("services/documentos_tesoreria_service.py").exists()


def _evaluar_soporte(conn: sqlite3.Connection, caso: Dict[str, Any]) -> Tuple[bool, List[str]]:
    codigo = caso["codigo"]
    if codigo == "EXPORTACION_HTML_DOCUMENTO":
        if _servicio_documentos_existe():
            return True, ["services/documentos_tesoreria_service.py detectado"]
        return False, ["No se detecto services/documentos_tesoreria_service.py desde el directorio actual"]

    faltantes: List[str] = []
    requerimientos = _tabla_y_columnas_para_caso(codigo)
    if not requerimientos:
        return False, ["No hay requerimientos definidos para el caso"]

    for tabla, columnas_extra in requerimientos:
        if not _tabla_existe(conn, tabla):
            faltantes.append(f"tabla faltante: {tabla}")
            continue
        columnas = set(_columnas_tabla(conn, tabla))
        # Los casos transversales tienen requerimientos distintos por tabla.
        # Por ejemplo, TRAZABILIDAD_TESORERIA exige tesoreria_operacion_id
        # en cobranzas/pagos, pero solo existencia de tesoreria_operaciones.
        if codigo in {
            "TRAZABILIDAD_TESORERIA",
            "ANULACION_CONTROLADA_DOCUMENTOS",
            "IMPUTACIONES_DOCUMENTALES",
            "RETENCIONES_DOCUMENTALES",
        }:
            columnas_requeridas = set(columnas_extra)
        else:
            columnas_requeridas = set(caso.get("columnas_requeridas") or []) | set(columnas_extra)
        for col in columnas_requeridas:
            if col and col not in columnas:
                faltantes.append(f"{tabla}.{col}")
    return len(faltantes) == 0, faltantes


def generar_parametrizacion_asistida_documentos_tesoreria(
    conn: sqlite3.Connection,
    empresa_id: Optional[int] = 1,
) -> Dict[str, Any]:
    """Genera matriz sugerida de documentos de Tesoreria en modo solo lectura."""
    conn.row_factory = sqlite3.Row
    matriz: List[Dict[str, Any]] = []
    resumen = {
        "casos_total": len(CASOS_DOCUMENTOS),
        "soportados": 0,
        "sugeridos": 0,
        "estructura_incompleta": 0,
        "recibos_emitidos": _count(conn, "cobranzas", *_where_empresa(conn, "cobranzas", empresa_id)) if _tabla_existe(conn, "cobranzas") else 0,
        "ordenes_pago_emitidas": _count(conn, "pagos", *_where_empresa(conn, "pagos", empresa_id)) if _tabla_existe(conn, "pagos") else 0,
    }

    for caso in CASOS_DOCUMENTOS:
        soportado, detalle = _evaluar_soporte(conn, caso)
        if soportado:
            estado = "SUGERIDO"
            resumen["soportados"] += 1
            resumen["sugeridos"] += 1
        else:
            estado = "ESTRUCTURA_INCOMPLETA"
            resumen["estructura_incompleta"] += 1

        matriz.append(
            {
                **caso,
                "estado": estado,
                "soporte_estructural": soportado,
                "detalle_soporte": "; ".join(detalle) if detalle else "Estructura disponible",
                "solo_lectura": True,
                "accion_sugerida": "Revisar y aceptar en una futura etapa v2B auditada." if soportado else "Completar estructura base antes de parametrizar.",
            }
        )

    estado_general = (
        ESTADO_ESTRUCTURA_INCOMPLETA
        if resumen["estructura_incompleta"] > 0 and resumen["soportados"] == 0
        else ESTADO_REQUIERE_PARAMETRIZACION
        if resumen["sugeridos"] > 0
        else ESTADO_OK
    )

    return {
        "modulo": "Documentos de Tesoreria",
        "version": "PRO_V2A_PARAMETRIZACION_ASISTIDA",
        "solo_lectura": True,
        "empresa_id": empresa_id,
        "estado": estado_general,
        "resumen": resumen,
        "matriz": matriz,
        "acciones_realizadas": [],
    }


# Alias de lectura natural.
generar_matriz_parametrizacion_documentos_tesoreria = generar_parametrizacion_asistida_documentos_tesoreria

