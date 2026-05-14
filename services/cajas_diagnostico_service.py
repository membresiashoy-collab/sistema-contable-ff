"""
Diagnostico contable-operativo de Caja PRO.

Servicio de solo lectura. No registra movimientos, no crea asientos,
no modifica Caja, Tesoreria, Banco, Cobranzas, Pagos ni Bandeja.
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

TABLAS_REQUERIDAS = (
    "tesoreria_cuentas",
    "tesoreria_medios_pago",
    "caja_movimientos",
    "caja_arqueos",
    "caja_asientos",
    "caja_auditoria",
)


def _fila_a_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


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


def _tiene_columna(conn: sqlite3.Connection, tabla: str, columna: str) -> bool:
    return columna in _columnas_tabla(conn, tabla)


def _where_empresa(conn: sqlite3.Connection, tabla: str, empresa_id: Optional[int]) -> Tuple[str, List[Any]]:
    if empresa_id is not None and _tiene_columna(conn, tabla, "empresa_id"):
        return "empresa_id = ?", [empresa_id]
    return "1 = 1", []


def _count(
    conn: sqlite3.Connection,
    tabla: str,
    where: str = "1 = 1",
    params: Sequence[Any] = (),
) -> int:
    if not _tabla_existe(conn, tabla):
        return 0
    row = conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {where}", tuple(params)).fetchone()
    return int(row[0] or 0)


def _safe_scalar(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
    default: Any = 0,
) -> Any:
    try:
        row = conn.execute(sql, tuple(params)).fetchone()
        if row is None:
            return default
        return row[0]
    except sqlite3.Error:
        return default


def _agregar_alerta(
    alertas: List[Dict[str, Any]],
    nivel: str,
    codigo: str,
    mensaje: str,
    detalle: Optional[str] = None,
    accion_sugerida: Optional[str] = None,
) -> None:
    alertas.append(
        {
            "nivel": nivel,
            "codigo": codigo,
            "mensaje": mensaje,
            "detalle": detalle or "",
            "accion_sugerida": accion_sugerida or "",
        }
    )


def _estado_desde_alertas(alertas: Iterable[Dict[str, Any]]) -> str:
    niveles = {a.get("nivel") for a in alertas}
    if NIVEL_CRITICO in niveles:
        return ESTADO_CRITICO
    if NIVEL_ADVERTENCIA in niveles:
        return ESTADO_REQUIERE_REVISION
    return ESTADO_OK


def _contar_cajas_activas(conn: sqlite3.Connection, empresa_id: Optional[int]) -> int:
    if not _tabla_existe(conn, "tesoreria_cuentas"):
        return 0
    where, params = _where_empresa(conn, "tesoreria_cuentas", empresa_id)
    columnas = _columnas_tabla(conn, "tesoreria_cuentas")
    condiciones = [where, "UPPER(COALESCE(tipo_cuenta, '')) = 'CAJA'"]
    if "activo" in columnas:
        condiciones.append("COALESCE(activo, 1) = 1")
    return _count(conn, "tesoreria_cuentas", " AND ".join(condiciones), params)


def _contar_cajas_sin_cuenta_contable(conn: sqlite3.Connection, empresa_id: Optional[int]) -> int:
    if not _tabla_existe(conn, "tesoreria_cuentas"):
        return 0
    columnas = _columnas_tabla(conn, "tesoreria_cuentas")
    if "cuenta_contable_codigo" not in columnas:
        return 0
    where, params = _where_empresa(conn, "tesoreria_cuentas", empresa_id)
    condiciones = [where, "UPPER(COALESCE(tipo_cuenta, '')) = 'CAJA'"]
    if "activo" in columnas:
        condiciones.append("COALESCE(activo, 1) = 1")
    condiciones.append("TRIM(COALESCE(cuenta_contable_codigo, '')) = ''")
    return _count(conn, "tesoreria_cuentas", " AND ".join(condiciones), params)


def _contar_medio_efectivo_activo(conn: sqlite3.Connection, empresa_id: Optional[int]) -> int:
    if not _tabla_existe(conn, "tesoreria_medios_pago"):
        return 0
    columnas = _columnas_tabla(conn, "tesoreria_medios_pago")
    where, params = _where_empresa(conn, "tesoreria_medios_pago", empresa_id)
    condiciones = [where]
    if "activo" in columnas:
        condiciones.append("COALESCE(activo, 1) = 1")
    partes_efectivo = []
    if "tipo" in columnas:
        partes_efectivo.append("UPPER(COALESCE(tipo, '')) = 'EFECTIVO'")
    if "codigo" in columnas:
        partes_efectivo.append("UPPER(COALESCE(codigo, '')) = 'EFECTIVO'")
    if "nombre" in columnas:
        partes_efectivo.append("UPPER(COALESCE(nombre, '')) LIKE '%EFECTIVO%'")
    condiciones.append("(" + " OR ".join(partes_efectivo or ["0 = 1"]) + ")")
    return _count(conn, "tesoreria_medios_pago", " AND ".join(condiciones), params)


def diagnosticar_cajas(conn: sqlite3.Connection, empresa_id: Optional[int] = 1) -> Dict[str, Any]:
    """
    Devuelve diagnostico de Caja PRO en modo solo lectura.

    Parametros:
        conn: conexion sqlite3 existente.
        empresa_id: empresa a analizar. Si es None, no filtra por empresa.
    """
    conn.row_factory = sqlite3.Row
    alertas: List[Dict[str, Any]] = []
    metricas: Dict[str, Any] = {}
    tablas: Dict[str, Dict[str, Any]] = {}

    for tabla in TABLAS_REQUERIDAS:
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
                f"CAJA_TABLA_FALTANTE_{tabla.upper()}",
                f"Falta la tabla requerida {tabla} para diagnosticar Caja.",
                accion_sugerida="Revisar migracion base de Caja antes de avanzar con operatoria.",
            )

    if alertas and any(a["nivel"] == NIVEL_CRITICO for a in alertas):
        return {
            "modulo": "Caja",
            "version": "PRO_V1_DIAGNOSTICO",
            "solo_lectura": True,
            "empresa_id": empresa_id,
            "estado": _estado_desde_alertas(alertas),
            "metricas": metricas,
            "tablas": tablas,
            "alertas": alertas,
            "acciones_realizadas": [],
        }

    metricas["cajas_activas"] = _contar_cajas_activas(conn, empresa_id)
    metricas["cajas_activas_sin_cuenta_contable"] = _contar_cajas_sin_cuenta_contable(conn, empresa_id)
    metricas["medio_efectivo_activo"] = _contar_medio_efectivo_activo(conn, empresa_id)

    if metricas["cajas_activas"] == 0:
        _agregar_alerta(
            alertas,
            NIVEL_ADVERTENCIA,
            "CAJA_SIN_CAJAS_ACTIVAS",
            "No hay cajas activas configuradas como cuenta de Tesoreria tipo CAJA.",
            accion_sugerida="Crear o activar una caja fisica vinculada al Plan Empresa antes de operar efectivo.",
        )

    if metricas["cajas_activas_sin_cuenta_contable"] > 0:
        _agregar_alerta(
            alertas,
            NIVEL_ADVERTENCIA,
            "CAJA_CUENTAS_SIN_CUENTA_CONTABLE",
            "Hay cajas activas sin cuenta contable vinculada.",
            detalle=f"Cantidad detectada: {metricas['cajas_activas_sin_cuenta_contable']}",
            accion_sugerida="Vincular cada caja activa con una cuenta imputable del Plan Empresa.",
        )

    if metricas["medio_efectivo_activo"] == 0:
        _agregar_alerta(
            alertas,
            NIVEL_ADVERTENCIA,
            "CAJA_MEDIO_EFECTIVO_NO_ACTIVO",
            "No se detecto medio de pago efectivo activo.",
            accion_sugerida="Asegurar el medio de pago EFECTIVO en Tesoreria para cobranzas y pagos en caja.",
        )

    if _tabla_existe(conn, "caja_movimientos"):
        where, params = _where_empresa(conn, "caja_movimientos", empresa_id)
        columnas = _columnas_tabla(conn, "caja_movimientos")
        activos = where
        if "estado" in columnas:
            activos += " AND UPPER(COALESCE(estado, '')) <> 'ANULADO'"
        metricas["movimientos_total"] = _count(conn, "caja_movimientos", where, params)
        metricas["movimientos_activos"] = _count(conn, "caja_movimientos", activos, params)
        metricas["movimientos_anulados"] = _count(
            conn,
            "caja_movimientos",
            where + " AND UPPER(COALESCE(estado, '')) = 'ANULADO'" if "estado" in columnas else "0 = 1",
            params,
        )
        metricas["movimientos_importe_no_positivo"] = _count(
            conn,
            "caja_movimientos",
            activos + " AND COALESCE(importe, 0) <= 0" if "importe" in columnas else "0 = 1",
            params,
        )
        metricas["movimientos_sin_caja_referenciada"] = _count(
            conn,
            "caja_movimientos",
            activos
            + " AND COALESCE(caja_id_origen, caja_id_destino) IS NULL"
            if {"caja_id_origen", "caja_id_destino"}.issubset(set(columnas))
            else "0 = 1",
            params,
        )

        if metricas["movimientos_total"] == 0:
            _agregar_alerta(
                alertas,
                NIVEL_INFO,
                "CAJA_SIN_MOVIMIENTOS",
                "No hay movimientos de Caja cargados en la base analizada.",
                detalle="En una base demo limpia esto es esperable.",
            )
        if metricas["movimientos_importe_no_positivo"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                "CAJA_MOVIMIENTOS_IMPORTE_INVALIDO",
                "Hay movimientos activos de Caja con importe menor o igual a cero.",
                detalle=f"Cantidad detectada: {metricas['movimientos_importe_no_positivo']}",
                accion_sugerida="Revisar origen del movimiento y definir anulacion/correccion controlada.",
            )
        if metricas["movimientos_sin_caja_referenciada"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                "CAJA_MOVIMIENTOS_SIN_CAJA",
                "Hay movimientos activos sin caja de origen ni destino.",
                detalle=f"Cantidad detectada: {metricas['movimientos_sin_caja_referenciada']}",
                accion_sugerida="Revisar integridad de movimientos de Caja antes de exponerlos en UI.",
            )

    if _tabla_existe(conn, "caja_arqueos"):
        where, params = _where_empresa(conn, "caja_arqueos", empresa_id)
        columnas = _columnas_tabla(conn, "caja_arqueos")
        activos = where
        if "estado" in columnas:
            activos += " AND UPPER(COALESCE(estado, '')) <> 'ANULADO'"
        metricas["arqueos_total"] = _count(conn, "caja_arqueos", where, params)
        metricas["arqueos_con_diferencia"] = _count(
            conn,
            "caja_arqueos",
            activos + " AND ABS(COALESCE(diferencia, 0)) > 0" if "diferencia" in columnas else "0 = 1",
            params,
        )
        metricas["arqueos_diferencia_sin_ajuste"] = _count(
            conn,
            "caja_arqueos",
            activos
            + " AND ABS(COALESCE(diferencia, 0)) > 0 AND movimiento_ajuste_id IS NULL"
            if {"diferencia", "movimiento_ajuste_id"}.issubset(set(columnas))
            else "0 = 1",
            params,
        )
        if metricas["arqueos_diferencia_sin_ajuste"] > 0:
            _agregar_alerta(
                alertas,
                NIVEL_ADVERTENCIA,
                "CAJA_ARQUEOS_DIFERENCIA_SIN_AJUSTE",
                "Hay arqueos activos con diferencia sin movimiento de ajuste vinculado.",
                detalle=f"Cantidad detectada: {metricas['arqueos_diferencia_sin_ajuste']}",
                accion_sugerida="Revisar diferencias de arqueo y su asiento/control asociado.",
            )

    if _tabla_existe(conn, "caja_asientos"):
        where, params = _where_empresa(conn, "caja_asientos", empresa_id)
        metricas["caja_asientos_total"] = _count(conn, "caja_asientos", where, params)

    if _tabla_existe(conn, "tesoreria_operaciones"):
        where, params = _where_empresa(conn, "tesoreria_operaciones", empresa_id)
        columnas = _columnas_tabla(conn, "tesoreria_operaciones")
        if "origen_modulo" in columnas:
            metricas["tesoreria_operaciones_origen_caja"] = _count(
                conn,
                "tesoreria_operaciones",
                where + " AND UPPER(COALESCE(origen_modulo, '')) LIKE '%CAJA%'",
                params,
            )

    return {
        "modulo": "Caja",
        "version": "PRO_V1_DIAGNOSTICO",
        "solo_lectura": True,
        "empresa_id": empresa_id,
        "estado": _estado_desde_alertas(alertas),
        "metricas": metricas,
        "tablas": tablas,
        "alertas": alertas,
        "acciones_realizadas": [],
    }


# Alias explicito para mantener legibilidad en futuras integraciones.
generar_diagnostico_cajas = diagnosticar_cajas

