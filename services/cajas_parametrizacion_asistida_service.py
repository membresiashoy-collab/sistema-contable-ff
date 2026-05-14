"""
Parametrizacion asistida de Caja PRO.

Servicio de solo lectura. Sugiere configuraciones contables/operativas, pero no
crea mapeos, no edita cajas, no registra movimientos y no genera asientos.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

ESTADO_OK = "OK"
ESTADO_REQUIERE_PARAMETRIZACION = "REQUIERE_PARAMETRIZACION"
ESTADO_ESTRUCTURA_INCOMPLETA = "ESTRUCTURA_INCOMPLETA"

CASOS_CAJA: List[Dict[str, Any]] = [
    {
        "codigo": "CAJA_EFECTIVO",
        "descripcion": "Caja fisica para efectivo disponible.",
        "uso_operativo_sugerido": "CAJA_EFECTIVO",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja",
        "prioridad": "ALTA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "MEDIO_PAGO_EFECTIVO",
        "descripcion": "Medio de pago efectivo para cobranzas y pagos por Caja.",
        "uso_operativo_sugerido": "MEDIO_PAGO_EFECTIVO",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja",
        "prioridad": "ALTA",
        "requiere_plan_empresa": False,
    },
    {
        "codigo": "CAJA_COBRANZA_EFECTIVO",
        "descripcion": "Ingreso automatico a Caja por cobranza en efectivo.",
        "uso_operativo_sugerido": "COBRANZA_EFECTIVO",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja",
        "prioridad": "ALTA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "CAJA_PAGO_EFECTIVO",
        "descripcion": "Egreso automatico de Caja por pago en efectivo.",
        "uso_operativo_sugerido": "PAGO_EFECTIVO",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja",
        "prioridad": "ALTA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "CAJA_MOVIMIENTO_MANUAL_INGRESO",
        "descripcion": "Ingreso manual de fondos a Caja.",
        "uso_operativo_sugerido": "CAJA_INGRESO_MANUAL",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja",
        "prioridad": "MEDIA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "CAJA_MOVIMIENTO_MANUAL_EGRESO",
        "descripcion": "Egreso manual de fondos de Caja.",
        "uso_operativo_sugerido": "CAJA_EGRESO_MANUAL",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja",
        "prioridad": "MEDIA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "CAJA_TRANSFERENCIA_INTERNA",
        "descripcion": "Transferencias internas Caja a Caja / Caja a Banco / Banco a Caja.",
        "uso_operativo_sugerido": "CAJA_TRANSFERENCIA_INTERNA",
        "cuenta_sugerida_codigo": "1.1.01.01",
        "cuenta_sugerida_nombre": "Caja / Banco segun origen y destino",
        "prioridad": "MEDIA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "CAJA_ARQUEO_FALTANTE",
        "descripcion": "Diferencia negativa de arqueo de Caja.",
        "uso_operativo_sugerido": "CAJA_ARQUEO_FALTANTE",
        "cuenta_sugerida_codigo": "6.2",
        "cuenta_sugerida_nombre": "Perdidas / diferencias de caja",
        "prioridad": "MEDIA",
        "requiere_plan_empresa": True,
    },
    {
        "codigo": "CAJA_ARQUEO_SOBRANTE",
        "descripcion": "Diferencia positiva de arqueo de Caja.",
        "uso_operativo_sugerido": "CAJA_ARQUEO_SOBRANTE",
        "cuenta_sugerida_codigo": "5.2",
        "cuenta_sugerida_nombre": "Ganancias / diferencias de caja",
        "prioridad": "MEDIA",
        "requiere_plan_empresa": True,
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


def _mapeo_activo(conn: sqlite3.Connection, empresa_id: Optional[int], uso_operativo: str) -> Optional[Dict[str, Any]]:
    if not _tabla_existe(conn, "mapeos_contables_empresa"):
        return None
    columnas = _columnas_tabla(conn, "mapeos_contables_empresa")
    posibles_uso = [c for c in ("uso_operativo", "codigo_uso", "evento_operativo", "codigo_evento") if c in columnas]
    if not posibles_uso:
        return None
    uso_col = posibles_uso[0]
    where, params = _where_empresa(conn, "mapeos_contables_empresa", empresa_id)
    condiciones = [where, f"UPPER(COALESCE({uso_col}, '')) = UPPER(?)"]
    params = list(params) + [uso_operativo]
    if "activo" in columnas:
        condiciones.append("COALESCE(activo, 1) = 1")
    row = conn.execute(
        f"SELECT * FROM mapeos_contables_empresa WHERE {' AND '.join(condiciones)} LIMIT 1",
        tuple(params),
    ).fetchone()
    if row is None:
        return None
    conn.row_factory = sqlite3.Row
    return dict(row) if hasattr(row, "keys") else {"uso_operativo": uso_operativo}


def _cuenta_plan_disponible(conn: sqlite3.Connection, empresa_id: Optional[int], codigo: str) -> bool:
    if not codigo:
        return False
    for tabla in ("plan_cuentas_empresa", "plan_cuentas"):
        if not _tabla_existe(conn, tabla):
            continue
        columnas = _columnas_tabla(conn, tabla)
        posibles_codigo = [c for c in ("codigo", "cuenta_codigo", "codigo_cuenta") if c in columnas]
        if not posibles_codigo:
            continue
        codigo_col = posibles_codigo[0]
        where, params = _where_empresa(conn, tabla, empresa_id)
        condiciones = [where, f"({codigo_col} = ? OR {codigo_col} LIKE ?)"]
        params = list(params) + [codigo, codigo + "%"]
        if "activo" in columnas:
            condiciones.append("COALESCE(activo, 1) = 1")
        if _count(conn, tabla, " AND ".join(condiciones), params) > 0:
            return True
    return False


def _soporte_estructural(conn: sqlite3.Connection, caso_codigo: str, empresa_id: Optional[int]) -> Tuple[bool, str]:
    if caso_codigo in {"CAJA_EFECTIVO", "MEDIO_PAGO_EFECTIVO"}:
        if not _tabla_existe(conn, "tesoreria_cuentas") or not _tabla_existe(conn, "tesoreria_medios_pago"):
            return False, "Faltan tablas base de Tesoreria."
        return True, "Estructura base de Tesoreria disponible."
    if caso_codigo.startswith("CAJA_ARQUEO"):
        return _tabla_existe(conn, "caja_arqueos"), "Tabla caja_arqueos disponible." if _tabla_existe(conn, "caja_arqueos") else "Falta caja_arqueos."
    if caso_codigo in {"CAJA_COBRANZA_EFECTIVO"}:
        return _tabla_existe(conn, "cobranzas") and _tabla_existe(conn, "caja_movimientos"), "Cobranzas y movimientos de Caja disponibles."
    if caso_codigo in {"CAJA_PAGO_EFECTIVO"}:
        return _tabla_existe(conn, "pagos") and _tabla_existe(conn, "caja_movimientos"), "Pagos y movimientos de Caja disponibles."
    return _tabla_existe(conn, "caja_movimientos"), "Tabla caja_movimientos disponible." if _tabla_existe(conn, "caja_movimientos") else "Falta caja_movimientos."


def generar_parametrizacion_asistida_cajas(conn: sqlite3.Connection, empresa_id: Optional[int] = 1) -> Dict[str, Any]:
    """Genera matriz de parametrizacion sugerida para Caja en modo solo lectura."""
    conn.row_factory = sqlite3.Row
    matriz: List[Dict[str, Any]] = []
    resumen = {
        "casos_total": len(CASOS_CAJA),
        "configurados": 0,
        "sugeridos": 0,
        "estructura_incompleta": 0,
        "sin_plan_empresa_detectado": 0,
    }

    for caso in CASOS_CAJA:
        soportado, detalle_soporte = _soporte_estructural(conn, caso["codigo"], empresa_id)
        mapeo = _mapeo_activo(conn, empresa_id, caso["uso_operativo_sugerido"])
        cuenta_disponible = _cuenta_plan_disponible(conn, empresa_id, caso["cuenta_sugerida_codigo"])

        if not soportado:
            estado = "ESTRUCTURA_INCOMPLETA"
            resumen["estructura_incompleta"] += 1
        elif mapeo:
            estado = "CONFIGURADO"
            resumen["configurados"] += 1
        else:
            estado = "SUGERIDO"
            resumen["sugeridos"] += 1

        if caso.get("requiere_plan_empresa") and not cuenta_disponible:
            resumen["sin_plan_empresa_detectado"] += 1

        matriz.append(
            {
                **caso,
                "estado": estado,
                "soporte_estructural": soportado,
                "detalle_soporte": detalle_soporte,
                "mapeo_activo_detectado": bool(mapeo),
                "cuenta_plan_empresa_detectada": cuenta_disponible,
                "solo_lectura": True,
                "accion_sugerida": "Revisar y aceptar en una futura etapa v2B auditada." if estado == "SUGERIDO" else "Sin accion automatica.",
            }
        )

    if resumen["estructura_incompleta"] > 0:
        estado_general = ESTADO_ESTRUCTURA_INCOMPLETA
    elif resumen["sugeridos"] > 0:
        estado_general = ESTADO_REQUIERE_PARAMETRIZACION
    else:
        estado_general = ESTADO_OK

    return {
        "modulo": "Caja",
        "version": "PRO_V2A_PARAMETRIZACION_ASISTIDA",
        "solo_lectura": True,
        "empresa_id": empresa_id,
        "estado": estado_general,
        "resumen": resumen,
        "matriz": matriz,
        "acciones_realizadas": [],
    }


# Alias de lectura natural.
generar_matriz_parametrizacion_cajas = generar_parametrizacion_asistida_cajas

