from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ESTADOS_BANCO_VALIDOS = {
    "PENDIENTE",
    "PARCIAL",
    "CONCILIADO",
    "NO_CONCILIABLE",
}

ESTADOS_TESORERIA_CONCILIACION_VALIDOS = {
    "PENDIENTE",
    "SUGERIDA",
    "PARCIAL",
    "CONCILIADA",
    "NO_CONCILIABLE",
}

ESTADOS_OPERACION_TESORERIA_VALIDOS = {
    "CONFIRMADA",
    "BORRADOR",
    "ANULADA",
}

ESTADOS_CONCILIACION_VALIDOS = {
    "CONFIRMADA",
    "PARCIAL",
    "ANULADA",
}

TIPOS_CONCILIACION_REFERENCIA = {
    "TESORERIA_OPERACION",
}

SEVERIDAD_ORDEN = {
    "OK": 0,
    "INFORMATIVO": 1,
    "ADVERTENCIA": 2,
    "CRITICO": 3,
}

TABLAS_REQUERIDAS = (
    "bancos_movimientos",
    "tesoreria_operaciones",
    "bancos_conciliaciones",
    "bancos_conciliaciones_detalle",
)

TABLAS_REFERENCIA = (
    "tesoreria_cuentas",
    "tesoreria_medios_pago",
    "tesoreria_auditoria",
)


def diagnosticar_conciliacion(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Conciliación PRO v1: diagnóstico contable-operativo integral.

    Servicio deliberadamente de solo lectura:
    - no ejecuta migraciones;
    - no llama a inicializar_conciliacion();
    - no inicializa Banco ni Tesorería;
    - no genera sugerencias automáticas;
    - no confirma conciliaciones;
    - no desconcilia;
    - no registra auditoría;
    - no modifica importes pendientes ni estados.

    Si se pasa ``conexion`` usa esa conexión sin cerrarla.
    Si no se pasa, intenta abrir una conexión usando helpers conocidos del
    proyecto y, como último recurso, rutas SQLite habituales del repositorio.
    """

    empresa_id = int(empresa_id or 1)
    cerrar_conexion = conexion is None
    con = conexion or _obtener_conexion()

    try:
        _configurar_conexion(con)

        diagnostico: Dict[str, Any] = {
            "empresa_id": empresa_id,
            "estado": "OK",
            "solo_lectura": True,
            "version": "CONCILIACION_PRO_V1_DIAGNOSTICO",
            "resumen": {
                "tablas_requeridas": len(TABLAS_REQUERIDAS),
                "tablas_requeridas_detectadas": 0,
                "tablas_referencia_detectadas": 0,
                "movimientos_bancarios": 0,
                "movimientos_bancarios_pendientes": 0,
                "movimientos_bancarios_parciales": 0,
                "movimientos_bancarios_conciliados": 0,
                "movimientos_bancarios_no_conciliables": 0,
                "movimientos_bancarios_estado_desconocido": 0,
                "operaciones_tesoreria": 0,
                "operaciones_tesoreria_pendientes": 0,
                "operaciones_tesoreria_parciales": 0,
                "operaciones_tesoreria_conciliadas": 0,
                "operaciones_tesoreria_no_conciliables": 0,
                "operaciones_tesoreria_anuladas": 0,
                "operaciones_tesoreria_estado_desconocido": 0,
                "conciliaciones": 0,
                "conciliaciones_activas": 0,
                "conciliaciones_parciales": 0,
                "conciliaciones_anuladas": 0,
                "conciliaciones_sin_detalle": 0,
                "conciliaciones_detalle": 0,
                "detalles_sin_conciliacion": 0,
                "detalles_sin_movimiento_banco": 0,
                "detalles_sin_operacion_tesoreria": 0,
                "posibles_pares_por_importe_signo": 0,
                "alertas_criticas": 0,
                "advertencias": 0,
            },
            "tablas": {},
            "bancos": {
                "totales_por_estado_conciliacion": {},
                "pendientes": [],
                "parciales": [],
                "estado_desconocido": [],
                "con_pendiente_inconsistente": [],
            },
            "tesoreria": {
                "totales_por_estado_operacion": {},
                "totales_por_estado_conciliacion": {},
                "pendientes": [],
                "parciales": [],
                "anuladas": [],
                "estado_desconocido": [],
                "con_pendiente_inconsistente": [],
            },
            "conciliaciones": {
                "totales_por_estado": {},
                "totales_por_tipo": {},
                "sin_detalle": [],
                "anuladas": [],
                "detalles_huerfanos": [],
                "detalles_sin_movimiento_banco": [],
                "detalles_sin_operacion_tesoreria": [],
                "detalles_importe_invalido": [],
            },
            "sugerencias_diagnosticas": {
                "posibles_pares_por_importe_signo": [],
            },
            "alertas": [],
            "recomendaciones": [],
        }

        for tabla in TABLAS_REQUERIDAS:
            existe = _tabla_existe(con, tabla)
            diagnostico["tablas"][tabla] = {
                "existe": existe,
                "tipo": "requerida",
                "columnas": _columnas_tabla(con, tabla) if existe else [],
            }
            if existe:
                diagnostico["resumen"]["tablas_requeridas_detectadas"] += 1
            else:
                _agregar_alerta(
                    diagnostico,
                    codigo="CONCILIACION_TABLA_REQUERIDA_INEXISTENTE",
                    severidad="CRITICO",
                    titulo=f"No existe la tabla requerida {tabla}",
                    detalle=(
                        "El diagnóstico no ejecuta migraciones ni inicializaciones. "
                        "La ausencia de esta tabla impide evaluar conciliación de forma integral."
                    ),
                    entidad=tabla,
                )

        for tabla in TABLAS_REFERENCIA:
            existe = _tabla_existe(con, tabla)
            diagnostico["tablas"][tabla] = {
                "existe": existe,
                "tipo": "referencia",
                "columnas": _columnas_tabla(con, tabla) if existe else [],
            }
            if existe:
                diagnostico["resumen"]["tablas_referencia_detectadas"] += 1

        movimientos = _leer_movimientos_bancarios(con, empresa_id)
        operaciones = _leer_operaciones_tesoreria(con, empresa_id)
        conciliaciones = _leer_conciliaciones(con, empresa_id)
        detalles = _leer_detalles_conciliacion(con, empresa_id)

        diagnostico["resumen"]["movimientos_bancarios"] = len(movimientos)
        diagnostico["resumen"]["operaciones_tesoreria"] = len(operaciones)
        diagnostico["resumen"]["conciliaciones"] = len(conciliaciones)
        diagnostico["resumen"]["conciliaciones_detalle"] = len(detalles)

        _diagnosticar_movimientos_bancarios(diagnostico, movimientos)
        _diagnosticar_operaciones_tesoreria(diagnostico, operaciones)
        _diagnosticar_conciliaciones(diagnostico, conciliaciones, detalles, movimientos, operaciones)
        _diagnosticar_posibles_pares(diagnostico, movimientos, operaciones)
        _agregar_recomendaciones(diagnostico)
        _actualizar_estado_general(diagnostico)

        return diagnostico
    finally:
        if cerrar_conexion:
            con.close()


def obtener_alertas_conciliacion(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Devuelve únicamente las alertas del diagnóstico de Conciliación."""
    return diagnosticar_conciliacion(empresa_id=empresa_id, conexion=conexion).get("alertas", [])


def obtener_resumen_conciliacion_diagnostico(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Devuelve únicamente el resumen del diagnóstico de Conciliación."""
    return diagnosticar_conciliacion(empresa_id=empresa_id, conexion=conexion).get("resumen", {})


def _diagnosticar_movimientos_bancarios(diagnostico: Dict[str, Any], movimientos: List[Dict[str, Any]]) -> None:
    contador_estados = Counter(_texto_upper(mov.get("estado_conciliacion") or "PENDIENTE") for mov in movimientos)
    diagnostico["bancos"]["totales_por_estado_conciliacion"] = dict(sorted(contador_estados.items()))

    for mov in movimientos:
        estado = _texto_upper(mov.get("estado_conciliacion") or "PENDIENTE")
        pendiente = _pendiente_financiero(mov)
        item = _resumen_movimiento_banco(mov, pendiente=pendiente)

        if estado == "PENDIENTE" and pendiente > 0.01:
            diagnostico["resumen"]["movimientos_bancarios_pendientes"] += 1
            diagnostico["bancos"]["pendientes"].append(item)
        elif estado == "PARCIAL" and pendiente > 0.01:
            diagnostico["resumen"]["movimientos_bancarios_parciales"] += 1
            diagnostico["bancos"]["parciales"].append(item)
        elif estado == "CONCILIADO":
            diagnostico["resumen"]["movimientos_bancarios_conciliados"] += 1
        elif estado == "NO_CONCILIABLE":
            diagnostico["resumen"]["movimientos_bancarios_no_conciliables"] += 1

        if estado not in ESTADOS_BANCO_VALIDOS:
            diagnostico["resumen"]["movimientos_bancarios_estado_desconocido"] += 1
            diagnostico["bancos"]["estado_desconocido"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_BANCO_ESTADO_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Movimiento bancario con estado de conciliación desconocido",
                detalle=(
                    f"Movimiento bancario {item.get('id')} con estado '{estado}'. "
                    "Revise estados permitidos antes de automatizar conciliación."
                ),
                entidad="bancos_movimientos",
                entidad_id=item.get("id"),
            )

        if estado == "CONCILIADO" and pendiente > 0.01:
            diagnostico["bancos"]["con_pendiente_inconsistente"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_BANCO_CONCILIADO_CON_PENDIENTE",
                severidad="CRITICO",
                titulo="Movimiento bancario conciliado conserva importe pendiente",
                detalle=(
                    f"Movimiento bancario {item.get('id')} figura conciliado pero conserva pendiente "
                    f"por {pendiente:.2f}."
                ),
                entidad="bancos_movimientos",
                entidad_id=item.get("id"),
            )


def _diagnosticar_operaciones_tesoreria(diagnostico: Dict[str, Any], operaciones: List[Dict[str, Any]]) -> None:
    contador_estados_operacion = Counter(_texto_upper(ope.get("estado") or "CONFIRMADA") for ope in operaciones)
    contador_estados_conciliacion = Counter(_texto_upper(ope.get("estado_conciliacion") or "PENDIENTE") for ope in operaciones)
    diagnostico["tesoreria"]["totales_por_estado_operacion"] = dict(sorted(contador_estados_operacion.items()))
    diagnostico["tesoreria"]["totales_por_estado_conciliacion"] = dict(sorted(contador_estados_conciliacion.items()))

    for ope in operaciones:
        estado_operacion = _texto_upper(ope.get("estado") or "CONFIRMADA")
        estado_conciliacion = _texto_upper(ope.get("estado_conciliacion") or "PENDIENTE")
        pendiente = _pendiente_financiero(ope)
        item = _resumen_operacion_tesoreria(ope, pendiente=pendiente)

        if estado_operacion == "ANULADA":
            diagnostico["resumen"]["operaciones_tesoreria_anuladas"] += 1
            diagnostico["tesoreria"]["anuladas"].append(item)
            if not _texto(ope.get("motivo_anulacion")):
                _agregar_alerta(
                    diagnostico,
                    codigo="CONCILIACION_TESORERIA_ANULADA_SIN_MOTIVO",
                    severidad="ADVERTENCIA",
                    titulo="Operación de Tesorería anulada sin motivo visible",
                    detalle=f"Operación {item.get('id')} anulada sin motivo informado.",
                    entidad="tesoreria_operaciones",
                    entidad_id=item.get("id"),
                )
            continue

        if estado_conciliacion in {"PENDIENTE", "SUGERIDA"} and pendiente > 0.01:
            diagnostico["resumen"]["operaciones_tesoreria_pendientes"] += 1
            diagnostico["tesoreria"]["pendientes"].append(item)
        elif estado_conciliacion == "PARCIAL" and pendiente > 0.01:
            diagnostico["resumen"]["operaciones_tesoreria_parciales"] += 1
            diagnostico["tesoreria"]["parciales"].append(item)
        elif estado_conciliacion == "CONCILIADA":
            diagnostico["resumen"]["operaciones_tesoreria_conciliadas"] += 1
        elif estado_conciliacion == "NO_CONCILIABLE":
            diagnostico["resumen"]["operaciones_tesoreria_no_conciliables"] += 1

        if estado_operacion not in ESTADOS_OPERACION_TESORERIA_VALIDOS:
            diagnostico["resumen"]["operaciones_tesoreria_estado_desconocido"] += 1
            diagnostico["tesoreria"]["estado_desconocido"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_TESORERIA_ESTADO_OPERACION_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Operación de Tesorería con estado operativo desconocido",
                detalle=f"Operación {item.get('id')} con estado '{estado_operacion}'.",
                entidad="tesoreria_operaciones",
                entidad_id=item.get("id"),
            )

        if estado_conciliacion not in ESTADOS_TESORERIA_CONCILIACION_VALIDOS:
            diagnostico["resumen"]["operaciones_tesoreria_estado_desconocido"] += 1
            diagnostico["tesoreria"]["estado_desconocido"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_TESORERIA_ESTADO_CONCILIACION_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Operación de Tesorería con estado de conciliación desconocido",
                detalle=f"Operación {item.get('id')} con estado conciliación '{estado_conciliacion}'.",
                entidad="tesoreria_operaciones",
                entidad_id=item.get("id"),
            )

        if estado_conciliacion == "CONCILIADA" and pendiente > 0.01:
            diagnostico["tesoreria"]["con_pendiente_inconsistente"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_TESORERIA_CONCILIADA_CON_PENDIENTE",
                severidad="CRITICO",
                titulo="Operación de Tesorería conciliada conserva importe pendiente",
                detalle=(
                    f"Operación {item.get('id')} figura conciliada pero conserva pendiente "
                    f"por {pendiente:.2f}."
                ),
                entidad="tesoreria_operaciones",
                entidad_id=item.get("id"),
            )


def _diagnosticar_conciliaciones(
    diagnostico: Dict[str, Any],
    conciliaciones: List[Dict[str, Any]],
    detalles: List[Dict[str, Any]],
    movimientos: List[Dict[str, Any]],
    operaciones: List[Dict[str, Any]],
) -> None:
    conciliaciones_por_id = {_entero(conc.get("id")): conc for conc in conciliaciones if _entero(conc.get("id")) is not None}
    movimientos_por_id = {_entero(mov.get("id")): mov for mov in movimientos if _entero(mov.get("id")) is not None}
    operaciones_por_id = {_entero(ope.get("id")): ope for ope in operaciones if _entero(ope.get("id")) is not None}
    detalles_por_conciliacion: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for det in detalles:
        conciliacion_id = _entero(det.get("conciliacion_id"))
        if conciliacion_id is not None:
            detalles_por_conciliacion[conciliacion_id].append(det)

    contador_estados = Counter(_texto_upper(conc.get("estado") or "CONFIRMADA") for conc in conciliaciones)
    contador_tipos = Counter(_texto_upper(conc.get("tipo_conciliacion") or "") for conc in conciliaciones)
    diagnostico["conciliaciones"]["totales_por_estado"] = dict(sorted(contador_estados.items()))
    diagnostico["conciliaciones"]["totales_por_tipo"] = dict(sorted(contador_tipos.items()))

    for conc in conciliaciones:
        conciliacion_id = _entero(conc.get("id"))
        estado = _texto_upper(conc.get("estado") or "CONFIRMADA")
        tipo = _texto_upper(conc.get("tipo_conciliacion"))
        item = _resumen_conciliacion(conc)

        if estado == "ANULADA":
            diagnostico["resumen"]["conciliaciones_anuladas"] += 1
            diagnostico["conciliaciones"]["anuladas"].append(item)
        elif estado == "PARCIAL":
            diagnostico["resumen"]["conciliaciones_parciales"] += 1
            diagnostico["resumen"]["conciliaciones_activas"] += 1
        else:
            diagnostico["resumen"]["conciliaciones_activas"] += 1

        if estado not in ESTADOS_CONCILIACION_VALIDOS:
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_ESTADO_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Conciliación con estado desconocido",
                detalle=f"Conciliación {conciliacion_id} con estado '{estado}'.",
                entidad="bancos_conciliaciones",
                entidad_id=conciliacion_id,
            )

        if tipo and tipo not in TIPOS_CONCILIACION_REFERENCIA:
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_TIPO_NO_TESORERIA",
                severidad="INFORMATIVO",
                titulo="Conciliación con tipo distinto de Tesorería",
                detalle=(
                    f"Conciliación {conciliacion_id} tiene tipo '{tipo}'. "
                    "Este diagnóstico prioriza Banco/Tesorería; otros tipos deben tratarse en sus módulos."
                ),
                entidad="bancos_conciliaciones",
                entidad_id=conciliacion_id,
            )

        if estado != "ANULADA" and conciliacion_id is not None and not detalles_por_conciliacion.get(conciliacion_id):
            diagnostico["resumen"]["conciliaciones_sin_detalle"] += 1
            diagnostico["conciliaciones"]["sin_detalle"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_ACTIVA_SIN_DETALLE",
                severidad="CRITICO",
                titulo="Conciliación activa sin detalle",
                detalle=f"Conciliación {conciliacion_id} no tiene detalle asociado.",
                entidad="bancos_conciliaciones",
                entidad_id=conciliacion_id,
            )

    for det in detalles:
        detalle_id = _entero(det.get("id"))
        conciliacion_id = _entero(det.get("conciliacion_id"))
        movimiento_banco_id = _entero(det.get("movimiento_banco_id"))
        entidad_tabla = _texto(det.get("entidad_tabla"))
        entidad_id = _entero(det.get("entidad_id"))
        importe = abs(_numero(det.get("importe_imputado")))
        item = _resumen_detalle(det)

        if conciliacion_id is not None and conciliacion_id not in conciliaciones_por_id:
            diagnostico["resumen"]["detalles_sin_conciliacion"] += 1
            diagnostico["conciliaciones"]["detalles_huerfanos"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_DETALLE_SIN_CABECERA",
                severidad="CRITICO",
                titulo="Detalle de conciliación sin cabecera",
                detalle=f"Detalle {detalle_id} referencia conciliación inexistente {conciliacion_id}.",
                entidad="bancos_conciliaciones_detalle",
                entidad_id=detalle_id,
            )

        if movimiento_banco_id is not None and movimiento_banco_id not in movimientos_por_id:
            diagnostico["resumen"]["detalles_sin_movimiento_banco"] += 1
            diagnostico["conciliaciones"]["detalles_sin_movimiento_banco"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_DETALLE_SIN_MOVIMIENTO_BANCO",
                severidad="CRITICO",
                titulo="Detalle de conciliación referencia movimiento bancario inexistente",
                detalle=f"Detalle {detalle_id} referencia movimiento bancario inexistente {movimiento_banco_id}.",
                entidad="bancos_conciliaciones_detalle",
                entidad_id=detalle_id,
            )

        if entidad_tabla == "tesoreria_operaciones" and entidad_id is not None and entidad_id not in operaciones_por_id:
            diagnostico["resumen"]["detalles_sin_operacion_tesoreria"] += 1
            diagnostico["conciliaciones"]["detalles_sin_operacion_tesoreria"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_DETALLE_SIN_OPERACION_TESORERIA",
                severidad="CRITICO",
                titulo="Detalle de conciliación referencia operación de Tesorería inexistente",
                detalle=f"Detalle {detalle_id} referencia operación de Tesorería inexistente {entidad_id}.",
                entidad="bancos_conciliaciones_detalle",
                entidad_id=detalle_id,
            )

        if importe <= 0.01:
            diagnostico["conciliaciones"]["detalles_importe_invalido"].append(item)
            _agregar_alerta(
                diagnostico,
                codigo="CONCILIACION_DETALLE_IMPORTE_INVALIDO",
                severidad="ADVERTENCIA",
                titulo="Detalle de conciliación con importe inválido",
                detalle=f"Detalle {detalle_id} tiene importe imputado nulo o insignificante.",
                entidad="bancos_conciliaciones_detalle",
                entidad_id=detalle_id,
            )


def _diagnosticar_posibles_pares(
    diagnostico: Dict[str, Any],
    movimientos: List[Dict[str, Any]],
    operaciones: List[Dict[str, Any]],
) -> None:
    movimientos_pendientes = [
        mov for mov in movimientos
        if _texto_upper(mov.get("estado_conciliacion") or "PENDIENTE") in {"PENDIENTE", "PARCIAL"}
        and _pendiente_financiero(mov) > 0.01
    ]
    operaciones_pendientes = [
        ope for ope in operaciones
        if _texto_upper(ope.get("estado") or "CONFIRMADA") != "ANULADA"
        and _texto_upper(ope.get("estado_conciliacion") or "PENDIENTE") in {"PENDIENTE", "SUGERIDA", "PARCIAL"}
        and _pendiente_financiero(ope) > 0.01
    ]

    pares: List[Dict[str, Any]] = []
    for mov in movimientos_pendientes:
        if len(pares) >= 50:
            break
        pendiente_mov = _pendiente_financiero(mov)
        signo_mov = _signo(_numero(mov.get("importe")))
        for ope in operaciones_pendientes:
            if len(pares) >= 50:
                break
            pendiente_ope = _pendiente_financiero(ope)
            signo_ope = _signo(_numero(ope.get("importe")))
            if signo_mov == 0 or signo_mov != signo_ope:
                continue
            diferencia = abs(abs(pendiente_mov) - abs(pendiente_ope))
            if diferencia <= 1.0:
                pares.append({
                    "movimiento_banco_id": _entero(mov.get("id")),
                    "operacion_tesoreria_id": _entero(ope.get("id")),
                    "importe_banco_pendiente": round(abs(pendiente_mov), 2),
                    "importe_tesoreria_pendiente": round(abs(pendiente_ope), 2),
                    "diferencia_importe": round(diferencia, 2),
                    "fecha_banco": _texto(mov.get("fecha")),
                    "fecha_tesoreria": _texto(ope.get("fecha_operacion") or ope.get("fecha")),
                    "motivo": "Coincidencia diagnóstica por signo financiero e importe pendiente. No confirma conciliación.",
                })

    diagnostico["sugerencias_diagnosticas"]["posibles_pares_por_importe_signo"] = pares
    diagnostico["resumen"]["posibles_pares_por_importe_signo"] = len(pares)

    if pares:
        _agregar_alerta(
            diagnostico,
            codigo="CONCILIACION_PARES_DIAGNOSTICOS_PENDIENTES",
            severidad="INFORMATIVO",
            titulo="Existen pares Banco/Tesorería candidatos a revisión",
            detalle=(
                f"Se detectaron {len(pares)} pares por signo financiero e importe pendiente. "
                "Esto es diagnóstico, no conciliación automática."
            ),
            entidad="conciliacion",
        )


def _agregar_recomendaciones(diagnostico: Dict[str, Any]) -> None:
    resumen = diagnostico.get("resumen", {})
    recomendaciones: List[str] = []

    if resumen.get("tablas_requeridas_detectadas", 0) < resumen.get("tablas_requeridas", 0):
        recomendaciones.append(
            "Completar la estructura mínima de Banco, Tesorería y Conciliación antes de exponer diagnósticos en UI."
        )

    if resumen.get("movimientos_bancarios_pendientes", 0) or resumen.get("operaciones_tesoreria_pendientes", 0):
        recomendaciones.append(
            "Revisar pendientes Banco/Tesorería antes de activar conciliación automática o aceptación masiva."
        )

    if resumen.get("conciliaciones_sin_detalle", 0) or resumen.get("detalles_sin_conciliacion", 0):
        recomendaciones.append(
            "Normalizar trazabilidad de conciliaciones antes de conectar con Libro Diario o Bandeja de asientos."
        )

    if resumen.get("detalles_sin_movimiento_banco", 0) or resumen.get("detalles_sin_operacion_tesoreria", 0):
        recomendaciones.append(
            "Corregir referencias huérfanas de conciliación antes de permitir desconciliaciones operativas."
        )

    if resumen.get("movimientos_bancarios_estado_desconocido", 0) or resumen.get("operaciones_tesoreria_estado_desconocido", 0):
        recomendaciones.append(
            "Unificar estados operativos y de conciliación para evitar ramas especiales en módulos de pantalla."
        )

    if not recomendaciones:
        recomendaciones.append(
            "Conciliación no presenta inconsistencias críticas en el diagnóstico de solo lectura."
        )

    diagnostico["recomendaciones"] = recomendaciones


def _actualizar_estado_general(diagnostico: Dict[str, Any]) -> None:
    alertas = diagnostico.get("alertas", [])
    severidad_maxima = "OK"
    for alerta in alertas:
        severidad = _texto_upper(alerta.get("severidad") or "OK")
        if SEVERIDAD_ORDEN.get(severidad, 0) > SEVERIDAD_ORDEN.get(severidad_maxima, 0):
            severidad_maxima = severidad

    diagnostico["estado"] = severidad_maxima
    diagnostico["resumen"]["alertas_criticas"] = sum(
        1 for alerta in alertas if _texto_upper(alerta.get("severidad")) == "CRITICO"
    )
    diagnostico["resumen"]["advertencias"] = sum(
        1 for alerta in alertas if _texto_upper(alerta.get("severidad")) == "ADVERTENCIA"
    )


def _leer_movimientos_bancarios(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, "bancos_movimientos"):
        return []
    columnas = _columnas_tabla(con, "bancos_movimientos")
    columnas_select = _columnas_para_select(columnas)
    where, params = _where_empresa(columnas, empresa_id)
    sql = f"SELECT {columnas_select} FROM bancos_movimientos {where} ORDER BY {_orden_por_columnas(columnas, ('fecha', 'id'))}"
    return _consultar_dicts(con, sql, params)


def _leer_operaciones_tesoreria(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, "tesoreria_operaciones"):
        return []
    columnas = _columnas_tabla(con, "tesoreria_operaciones")
    columnas_select = _columnas_para_select(columnas)
    where, params = _where_empresa(columnas, empresa_id)
    sql = f"SELECT {columnas_select} FROM tesoreria_operaciones {where} ORDER BY {_orden_por_columnas(columnas, ('fecha_operacion', 'fecha', 'id'))}"
    return _consultar_dicts(con, sql, params)


def _leer_conciliaciones(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, "bancos_conciliaciones"):
        return []
    columnas = _columnas_tabla(con, "bancos_conciliaciones")
    columnas_select = _columnas_para_select(columnas)
    where, params = _where_empresa(columnas, empresa_id)
    sql = f"SELECT {columnas_select} FROM bancos_conciliaciones {where} ORDER BY {_orden_por_columnas(columnas, ('fecha_confirmacion', 'fecha', 'id'))}"
    return _consultar_dicts(con, sql, params)


def _leer_detalles_conciliacion(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, "bancos_conciliaciones_detalle"):
        return []
    columnas = _columnas_tabla(con, "bancos_conciliaciones_detalle")
    columnas_select = _columnas_para_select(columnas)
    where, params = _where_empresa(columnas, empresa_id)
    sql = f"SELECT {columnas_select} FROM bancos_conciliaciones_detalle {where} ORDER BY {_orden_por_columnas(columnas, ('conciliacion_id', 'id'))}"
    return _consultar_dicts(con, sql, params)


def _where_empresa(columnas: Sequence[str], empresa_id: int) -> Tuple[str, List[Any]]:
    if "empresa_id" in columnas:
        return "WHERE empresa_id = ?", [empresa_id]
    return "", []


def _columnas_para_select(columnas: Sequence[str]) -> str:
    if not columnas:
        return "*"
    return ", ".join(columnas)


def _orden_por_columnas(columnas: Sequence[str], candidatas: Sequence[str]) -> str:
    disponibles = [col for col in candidatas if col in columnas]
    return ", ".join(disponibles) if disponibles else "1"


def _consultar_dicts(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    try:
        cur = con.execute(sql, tuple(params))
        columnas = [col[0] for col in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]
    except sqlite3.Error:
        return []


def _resumen_movimiento_banco(mov: Dict[str, Any], pendiente: Optional[float] = None) -> Dict[str, Any]:
    return {
        "id": _entero(mov.get("id")),
        "fecha": _texto(mov.get("fecha")),
        "banco": _texto(mov.get("banco")),
        "cuenta": _texto(mov.get("nombre_cuenta") or mov.get("cuenta") or mov.get("numero_cuenta")),
        "concepto": _texto(mov.get("concepto") or mov.get("descripcion")),
        "referencia": _texto(mov.get("referencia")),
        "importe": round(_numero(mov.get("importe")), 2),
        "importe_conciliado": round(_numero(mov.get("importe_conciliado")), 2),
        "importe_pendiente": round(float(pendiente if pendiente is not None else _pendiente_financiero(mov)), 2),
        "estado_conciliacion": _texto_upper(mov.get("estado_conciliacion") or "PENDIENTE"),
    }


def _resumen_operacion_tesoreria(ope: Dict[str, Any], pendiente: Optional[float] = None) -> Dict[str, Any]:
    return {
        "id": _entero(ope.get("id")),
        "fecha_operacion": _texto(ope.get("fecha_operacion") or ope.get("fecha")),
        "tipo_operacion": _texto_upper(ope.get("tipo_operacion")),
        "subtipo": _texto_upper(ope.get("subtipo")),
        "cuenta_tesoreria_id": _entero(ope.get("cuenta_tesoreria_id")),
        "tercero_nombre": _texto(ope.get("tercero_nombre")),
        "tercero_cuit": _texto(ope.get("tercero_cuit")),
        "descripcion": _texto(ope.get("descripcion")),
        "referencia_externa": _texto(ope.get("referencia_externa")),
        "importe": round(_numero(ope.get("importe")), 2),
        "importe_conciliado": round(_numero(ope.get("importe_conciliado")), 2),
        "importe_pendiente": round(float(pendiente if pendiente is not None else _pendiente_financiero(ope)), 2),
        "estado": _texto_upper(ope.get("estado") or "CONFIRMADA"),
        "estado_conciliacion": _texto_upper(ope.get("estado_conciliacion") or "PENDIENTE"),
    }


def _resumen_conciliacion(conc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _entero(conc.get("id")),
        "fecha": _texto(conc.get("fecha")),
        "tipo_conciliacion": _texto_upper(conc.get("tipo_conciliacion")),
        "estado": _texto_upper(conc.get("estado") or "CONFIRMADA"),
        "movimiento_banco_id": _entero(conc.get("movimiento_banco_id")),
        "importe_total": round(_numero(conc.get("importe_total")), 2),
        "importe_imputado": round(_numero(conc.get("importe_imputado")), 2),
        "importe_pendiente": round(_numero(conc.get("importe_pendiente")), 2),
        "observacion": _texto(conc.get("observacion")),
    }


def _resumen_detalle(det: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _entero(det.get("id")),
        "conciliacion_id": _entero(det.get("conciliacion_id")),
        "movimiento_banco_id": _entero(det.get("movimiento_banco_id")),
        "entidad_tabla": _texto(det.get("entidad_tabla")),
        "entidad_id": _entero(det.get("entidad_id")),
        "importe_imputado": round(_numero(det.get("importe_imputado")), 2),
        "comprobante": _texto(det.get("comprobante")),
    }


def _pendiente_financiero(fila: Dict[str, Any]) -> float:
    if fila is None:
        return 0.0
    if "importe_pendiente" in fila and fila.get("importe_pendiente") is not None:
        pendiente = abs(_numero(fila.get("importe_pendiente")))
        if pendiente > 0:
            return round(pendiente, 2)
    importe = abs(_numero(fila.get("importe")))
    conciliado = abs(_numero(fila.get("importe_conciliado")))
    return round(max(importe - conciliado, 0.0), 2)


def _signo(valor: Any) -> int:
    numero = _numero(valor)
    if numero > 0:
        return 1
    if numero < 0:
        return -1
    return 0


def _agregar_alerta(
    diagnostico: Dict[str, Any],
    codigo: str,
    severidad: str,
    titulo: str,
    detalle: str,
    entidad: str = "",
    entidad_id: Any = None,
) -> None:
    diagnostico.setdefault("alertas", []).append({
        "codigo": _texto_upper(codigo),
        "severidad": _texto_upper(severidad or "INFORMATIVO"),
        "titulo": _texto(titulo),
        "detalle": _texto(detalle),
        "entidad": _texto(entidad),
        "entidad_id": entidad_id,
    })


def _tabla_existe(con: sqlite3.Connection, tabla: str) -> bool:
    try:
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (_texto(tabla),))
        return cur.fetchone() is not None
    except sqlite3.Error:
        return False


def _columnas_tabla(con: sqlite3.Connection, tabla: str) -> List[str]:
    try:
        cur = con.execute(f"PRAGMA table_info({tabla})")
        return [str(row[1]) for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def _configurar_conexion(con: sqlite3.Connection) -> None:
    try:
        con.row_factory = sqlite3.Row
    except Exception:
        pass


def _obtener_conexion() -> sqlite3.Connection:
    candidatos = (
        ("database", "get_connection"),
        ("db", "get_connection"),
        ("core.database", "get_connection"),
        ("core.db", "get_connection"),
        ("services.database", "get_connection"),
        ("services.db", "get_connection"),
        ("database", "obtener_conexion"),
        ("db", "obtener_conexion"),
        ("core.database", "obtener_conexion"),
        ("core.db", "obtener_conexion"),
        ("services.database", "obtener_conexion"),
        ("services.db", "obtener_conexion"),
    )

    for modulo_nombre, funcion_nombre in candidatos:
        try:
            modulo = __import__(modulo_nombre, fromlist=[funcion_nombre])
            funcion = getattr(modulo, funcion_nombre, None)
            if callable(funcion):
                con = funcion()
                if isinstance(con, sqlite3.Connection):
                    return con
        except Exception:
            continue

    rutas = (
        Path("data/sistema_contable.db"),
        Path("sistema_contable.db"),
        Path("database.db"),
        Path("contable.db"),
        Path("app.db"),
    )
    for ruta in rutas:
        if ruta.exists():
            return sqlite3.connect(str(ruta))

    raise RuntimeError(
        "No se pudo obtener conexión SQLite para diagnóstico de Conciliación. "
        "Pase una conexión explícita con el parámetro conexion=."
    )


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _texto_upper(valor: Any) -> str:
    return _texto(valor).upper()


def _numero(valor: Any) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = _texto(valor)
    if not texto:
        return 0.0
    texto = texto.replace("$", "").replace(" ", "")
    if texto.count(",") == 1 and texto.count(".") >= 1:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except (TypeError, ValueError):
        return 0.0


def _entero(valor: Any) -> Optional[int]:
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
