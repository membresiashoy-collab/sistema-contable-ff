from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


ESTADOS_BANCO_PENDIENTES = {"PENDIENTE", "PARCIAL"}
ESTADOS_TESORERIA_PENDIENTES = {"PENDIENTE", "SUGERIDA", "PARCIAL"}
ESTADOS_CONCILIACION_ACTIVA = {"CONFIRMADA", "PARCIAL"}

SEVERIDAD_ORDEN = {
    "OK": 0,
    "INFORMATIVO": 1,
    "ADVERTENCIA": 2,
    "CRITICO": 3,
}

PALABRAS_RUIDO = {
    "BANCO", "CTA", "CUENTA", "CBU", "CVU", "ALIAS", "ARS", "PESOS",
    "TRANSFERENCIA", "TRANSF", "PAGO", "COBRO", "DEBITO", "CREDITO", "MOV",
    "MOVIMIENTO", "OPERACION", "COMPROBANTE", "FACTURA", "RECIBO", "VARIOS",
}


class ConciliacionParametrizacionError(RuntimeError):
    pass


def analizar_parametrizacion_conciliacion(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
    tolerancia_importe: float = 1.0,
    max_sugerencias_por_movimiento: int = 5,
) -> Dict[str, Any]:
    """
    Conciliación PRO v2A: parametrización asistida y sugerencias de conciliación.

    Servicio deliberadamente de solo lectura:
    - no ejecuta migraciones;
    - no llama a inicializar_conciliacion();
    - no inicializa Banco ni Tesorería;
    - no confirma conciliaciones;
    - no desconcilia;
    - no actualiza importes pendientes ni estados;
    - no registra auditoría.

    Su responsabilidad es construir una matriz de sugerencias para revisión
    asistida. La aceptación, edición, descarte o ejecución controlada queda para
    una etapa posterior.
    """

    empresa_id = int(empresa_id or 1)
    tolerancia_importe = max(float(tolerancia_importe or 0), 0.0)
    max_sugerencias_por_movimiento = max(int(max_sugerencias_por_movimiento or 5), 1)
    cerrar_conexion = conexion is None
    con = conexion or _obtener_conexion()

    try:
        _configurar_conexion(con)

        resultado: Dict[str, Any] = {
            "empresa_id": empresa_id,
            "estado": "OK",
            "solo_lectura": True,
            "version": "CONCILIACION_PRO_V2A_PARAMETRIZACION_ASISTIDA",
            "parametros": {
                "tolerancia_importe": tolerancia_importe,
                "max_sugerencias_por_movimiento": max_sugerencias_por_movimiento,
            },
            "resumen": {
                "movimientos_bancarios_pendientes": 0,
                "operaciones_tesoreria_pendientes": 0,
                "sugerencias": 0,
                "sugerencias_alta": 0,
                "sugerencias_media": 0,
                "sugerencias_baja": 0,
                "sugerencias_ambiguas": 0,
                "sugerencias_con_par_activo": 0,
                "movimientos_con_sugerencia": 0,
                "operaciones_con_sugerencia": 0,
                "movimientos_sin_sugerencia": 0,
                "operaciones_sin_sugerencia": 0,
                "pares_descartados_signo": 0,
                "pares_descartados_importe": 0,
                "tablas_requeridas_detectadas": 0,
            },
            "tablas": {},
            "movimientos_bancarios": [],
            "operaciones_tesoreria": [],
            "sugerencias": [],
            "matriz_por_confianza": {},
            "alertas": [],
            "recomendaciones": [],
        }

        tablas_requeridas = ("bancos_movimientos", "tesoreria_operaciones")
        tablas_referencia = ("bancos_conciliaciones", "bancos_conciliaciones_detalle")

        for tabla in tablas_requeridas + tablas_referencia:
            existe = _tabla_existe(con, tabla)
            resultado["tablas"][tabla] = {
                "existe": existe,
                "tipo": "requerida" if tabla in tablas_requeridas else "referencia",
                "columnas": _columnas_tabla(con, tabla) if existe else [],
            }
            if existe and tabla in tablas_requeridas:
                resultado["resumen"]["tablas_requeridas_detectadas"] += 1
            if not existe and tabla in tablas_requeridas:
                _agregar_alerta(
                    resultado,
                    codigo="CONCILIACION_PARAM_TABLA_REQUERIDA_INEXISTENTE",
                    severidad="CRITICO",
                    titulo=f"No existe la tabla requerida {tabla}",
                    detalle=(
                        "La parametrización asistida no inicializa tablas ni ejecuta migraciones. "
                        "Sin esta tabla no puede construir sugerencias de conciliación."
                    ),
                    entidad=tabla,
                )

        movimientos = _leer_movimientos_bancarios_pendientes(con, empresa_id)
        operaciones = _leer_operaciones_tesoreria_pendientes(con, empresa_id)
        pares_activos = _leer_pares_conciliacion_activos(con, empresa_id)

        resultado["resumen"]["movimientos_bancarios_pendientes"] = len(movimientos)
        resultado["resumen"]["operaciones_tesoreria_pendientes"] = len(operaciones)
        resultado["movimientos_bancarios"] = [_resumen_movimiento(mov) for mov in movimientos]
        resultado["operaciones_tesoreria"] = [_resumen_operacion(ope) for ope in operaciones]

        sugerencias, descartes = _generar_sugerencias(
            movimientos=movimientos,
            operaciones=operaciones,
            pares_activos=pares_activos,
            tolerancia_importe=tolerancia_importe,
        )
        resultado["resumen"]["pares_descartados_signo"] = descartes.get("signo", 0)
        resultado["resumen"]["pares_descartados_importe"] = descartes.get("importe", 0)

        sugerencias = _limitar_y_marcar_ambiguedades(sugerencias, max_sugerencias_por_movimiento)
        resultado["sugerencias"] = sugerencias
        _actualizar_resumen_sugerencias(resultado, movimientos, operaciones, sugerencias)
        _agregar_alertas_sugerencias(resultado, sugerencias)
        _agregar_recomendaciones(resultado)
        _actualizar_estado_general(resultado)

        return resultado
    finally:
        if cerrar_conexion:
            con.close()


def obtener_sugerencias_conciliacion_asistida(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
    tolerancia_importe: float = 1.0,
) -> List[Dict[str, Any]]:
    return analizar_parametrizacion_conciliacion(
        empresa_id=empresa_id,
        conexion=conexion,
        tolerancia_importe=tolerancia_importe,
    ).get("sugerencias", [])


def obtener_resumen_parametrizacion_conciliacion(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    return analizar_parametrizacion_conciliacion(empresa_id=empresa_id, conexion=conexion).get("resumen", {})


def obtener_alertas_parametrizacion_conciliacion(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    return analizar_parametrizacion_conciliacion(empresa_id=empresa_id, conexion=conexion).get("alertas", [])


def _generar_sugerencias(
    movimientos: List[Dict[str, Any]],
    operaciones: List[Dict[str, Any]],
    pares_activos: Set[Tuple[int, int]],
    tolerancia_importe: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    sugerencias: List[Dict[str, Any]] = []
    descartes = {"signo": 0, "importe": 0}

    for mov in movimientos:
        for ope in operaciones:
            signo_mov = _signo(mov.get("importe"))
            signo_ope = _signo(ope.get("importe"))
            if signo_mov == 0 or signo_ope == 0 or signo_mov != signo_ope:
                descartes["signo"] += 1
                continue

            pendiente_banco = _pendiente_financiero(mov)
            pendiente_tesoreria = _pendiente_financiero(ope)
            diferencia_importe = abs(abs(pendiente_banco) - abs(pendiente_tesoreria))
            if diferencia_importe > tolerancia_importe:
                descartes["importe"] += 1
                continue

            sugerencia = _puntuar_sugerencia(mov, ope, diferencia_importe, pares_activos)
            if sugerencia["score"] <= 0:
                continue
            sugerencias.append(sugerencia)

    sugerencias.sort(key=lambda item: (-int(item.get("score") or 0), float(item.get("diferencia_importe") or 0), abs(int(item.get("diferencia_dias") or 9999))))
    return sugerencias, descartes


def _puntuar_sugerencia(
    movimiento: Dict[str, Any],
    operacion: Dict[str, Any],
    diferencia_importe: float,
    pares_activos: Set[Tuple[int, int]],
) -> Dict[str, Any]:
    score = 0
    motivos: List[str] = []
    controles: List[str] = []

    if diferencia_importe <= 0.01:
        score += 45
        motivos.append("importe exacto pendiente")
    elif diferencia_importe <= 0.10:
        score += 38
        motivos.append("importe con diferencia mínima")
    else:
        score += 28
        motivos.append("importe dentro de tolerancia")

    ref = _coincidencia_referencias(movimiento, operacion)
    score += ref["score"]
    motivos.extend(ref["motivos"])

    texto = _coincidencia_texto(movimiento, operacion)
    score += texto["score"]
    motivos.extend(texto["motivos"])

    tipo = _coincidencia_tipo_operacion(movimiento, operacion)
    score += tipo["score"]
    motivos.extend(tipo["motivos"])

    dias = _dias_entre(movimiento.get("fecha"), operacion.get("fecha_operacion") or operacion.get("fecha"))
    if dias is None:
        controles.append("fecha no comparable")
    elif dias == 0:
        score += 10
        motivos.append("misma fecha")
    elif abs(dias) <= 1:
        score += 8
        motivos.append("fecha cercana hasta 1 día")
    elif abs(dias) <= 3:
        score += 6
        motivos.append("fecha cercana hasta 3 días")
    elif abs(dias) <= 7:
        score += 3
        motivos.append("fecha cercana hasta 7 días")
    else:
        controles.append(f"fecha distante: {abs(dias)} días")

    movimiento_id = _entero(movimiento.get("id")) or 0
    operacion_id = _entero(operacion.get("id")) or 0
    par_activo = (movimiento_id, operacion_id) in pares_activos
    if par_activo:
        controles.append("ya existe conciliación activa para este par")
        score = min(score, 49)

    score = min(max(int(score), 0), 100)
    confianza = _clasificar_confianza(score, diferencia_importe, ref["score"], texto["score"])
    accion = _accion_por_confianza(confianza, par_activo=par_activo)

    return {
        "movimiento_banco_id": movimiento_id,
        "operacion_tesoreria_id": operacion_id,
        "score": score,
        "confianza": confianza,
        "accion_sugerida": accion,
        "ambigua": False,
        "par_conciliacion_activa": par_activo,
        "diferencia_importe": round(float(diferencia_importe), 2),
        "diferencia_dias": dias,
        "importe_sugerido": round(min(abs(_pendiente_financiero(movimiento)), abs(_pendiente_financiero(operacion))), 2),
        "fecha_banco": _texto(movimiento.get("fecha")),
        "banco": _texto(movimiento.get("banco")),
        "cuenta_banco": _texto(movimiento.get("nombre_cuenta")),
        "concepto_banco": _texto(movimiento.get("concepto")),
        "referencia_banco": _texto(movimiento.get("referencia")),
        "importe_banco": round(_numero(movimiento.get("importe")), 2),
        "pendiente_banco": round(_pendiente_financiero(movimiento), 2),
        "fecha_tesoreria": _texto(operacion.get("fecha_operacion") or operacion.get("fecha")),
        "tipo_operacion": _texto_upper(operacion.get("tipo_operacion")),
        "subtipo": _texto_upper(operacion.get("subtipo")),
        "origen_modulo": _texto_upper(operacion.get("origen_modulo")),
        "cuenta_tesoreria": _texto(operacion.get("cuenta_tesoreria")),
        "tercero_nombre": _texto(operacion.get("tercero_nombre")),
        "tercero_cuit": _texto(operacion.get("tercero_cuit")),
        "descripcion_tesoreria": _texto(operacion.get("descripcion")),
        "referencia_tesoreria": _texto(operacion.get("referencia_externa")),
        "importe_tesoreria": round(_numero(operacion.get("importe")), 2),
        "pendiente_tesoreria": round(_pendiente_financiero(operacion), 2),
        "motivos": _unicos(motivos),
        "controles": _unicos(controles),
    }


def _limitar_y_marcar_ambiguedades(sugerencias: List[Dict[str, Any]], max_por_movimiento: int) -> List[Dict[str, Any]]:
    por_movimiento: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    por_operacion: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for item in sugerencias:
        por_movimiento[int(item.get("movimiento_banco_id") or 0)].append(item)
        por_operacion[int(item.get("operacion_tesoreria_id") or 0)].append(item)

    filtradas: List[Dict[str, Any]] = []
    for movimiento_id, grupo in por_movimiento.items():
        grupo_ordenado = sorted(grupo, key=lambda item: (-int(item.get("score") or 0), float(item.get("diferencia_importe") or 0)))[:max_por_movimiento]
        filtradas.extend(grupo_ordenado)

    ids_filtradas = {(int(item.get("movimiento_banco_id") or 0), int(item.get("operacion_tesoreria_id") or 0)) for item in filtradas}

    for item in filtradas:
        mov_id = int(item.get("movimiento_banco_id") or 0)
        ope_id = int(item.get("operacion_tesoreria_id") or 0)
        grupo_mov = [s for s in por_movimiento[mov_id] if (int(s.get("movimiento_banco_id") or 0), int(s.get("operacion_tesoreria_id") or 0)) in ids_filtradas]
        grupo_ope = [s for s in por_operacion[ope_id] if (int(s.get("movimiento_banco_id") or 0), int(s.get("operacion_tesoreria_id") or 0)) in ids_filtradas]
        mejor_mov = max([int(s.get("score") or 0) for s in grupo_mov] or [0])
        mejor_ope = max([int(s.get("score") or 0) for s in grupo_ope] or [0])
        competidores_mov = [s for s in grupo_mov if s is not item and mejor_mov - int(s.get("score") or 0) < 10]
        competidores_ope = [s for s in grupo_ope if s is not item and mejor_ope - int(s.get("score") or 0) < 10]
        if competidores_mov or competidores_ope:
            item["ambigua"] = True
            item["accion_sugerida"] = "REVISAR_CANDIDATOS_AMBIGUOS"
            item.setdefault("controles", []).append("hay más de un candidato competitivo")

    filtradas.sort(key=lambda item: (-int(item.get("score") or 0), float(item.get("diferencia_importe") or 0), abs(int(item.get("diferencia_dias") or 9999))))
    return filtradas


def _clasificar_confianza(score: int, diferencia_importe: float, score_referencia: int, score_texto: int) -> str:
    if score >= 85 and diferencia_importe <= 0.01 and (score_referencia > 0 or score_texto >= 12):
        return "ALTA"
    if score >= 70:
        return "MEDIA"
    if score >= 50:
        return "BAJA"
    return "NULA"


def _accion_por_confianza(confianza: str, par_activo: bool = False) -> str:
    if par_activo:
        return "NO_SUGERIR_PAR_YA_CONCILIADO"
    if confianza in {"ALTA", "MEDIA"}:
        return "SUGERIR_CONCILIACION_ASISTIDA"
    if confianza == "BAJA":
        return "REVISAR_MANUALMENTE"
    return "NO_SUGERIR"


def _actualizar_resumen_sugerencias(
    resultado: Dict[str, Any],
    movimientos: List[Dict[str, Any]],
    operaciones: List[Dict[str, Any]],
    sugerencias: List[Dict[str, Any]],
) -> None:
    resultado["resumen"]["sugerencias"] = len(sugerencias)
    contador = Counter(_texto_upper(item.get("confianza")) for item in sugerencias)
    resultado["resumen"]["sugerencias_alta"] = contador.get("ALTA", 0)
    resultado["resumen"]["sugerencias_media"] = contador.get("MEDIA", 0)
    resultado["resumen"]["sugerencias_baja"] = contador.get("BAJA", 0)
    resultado["resumen"]["sugerencias_ambiguas"] = sum(1 for item in sugerencias if item.get("ambigua"))
    resultado["resumen"]["sugerencias_con_par_activo"] = sum(1 for item in sugerencias if item.get("par_conciliacion_activa"))

    movimientos_con = {int(item.get("movimiento_banco_id") or 0) for item in sugerencias if item.get("confianza") != "NULA"}
    operaciones_con = {int(item.get("operacion_tesoreria_id") or 0) for item in sugerencias if item.get("confianza") != "NULA"}
    todos_movimientos = {_entero(mov.get("id")) or 0 for mov in movimientos}
    todas_operaciones = {_entero(ope.get("id")) or 0 for ope in operaciones}
    resultado["resumen"]["movimientos_con_sugerencia"] = len(movimientos_con)
    resultado["resumen"]["operaciones_con_sugerencia"] = len(operaciones_con)
    resultado["resumen"]["movimientos_sin_sugerencia"] = len(todos_movimientos.difference(movimientos_con))
    resultado["resumen"]["operaciones_sin_sugerencia"] = len(todas_operaciones.difference(operaciones_con))

    matriz: Dict[str, List[Dict[str, Any]]] = {"ALTA": [], "MEDIA": [], "BAJA": [], "NULA": []}
    for item in sugerencias:
        matriz.setdefault(_texto_upper(item.get("confianza") or "NULA"), []).append(item)
    resultado["matriz_por_confianza"] = matriz


def _agregar_alertas_sugerencias(resultado: Dict[str, Any], sugerencias: List[Dict[str, Any]]) -> None:
    if resultado["resumen"].get("sugerencias_ambiguas", 0) > 0:
        _agregar_alerta(
            resultado,
            codigo="CONCILIACION_PARAM_SUGERENCIAS_AMBIGUAS",
            severidad="ADVERTENCIA",
            titulo="Hay sugerencias de conciliación ambiguas",
            detalle="Existen movimientos u operaciones con más de un candidato competitivo. No deben automatizarse sin revisión.",
            entidad="sugerencias_conciliacion",
        )

    if resultado["resumen"].get("sugerencias_con_par_activo", 0) > 0:
        _agregar_alerta(
            resultado,
            codigo="CONCILIACION_PARAM_PAR_YA_ACTIVO",
            severidad="ADVERTENCIA",
            titulo="Hay candidatos que ya tienen conciliación activa",
            detalle="El par Banco/Tesorería ya aparece en conciliaciones activas. Revise antes de sugerir una nueva imputación.",
            entidad="bancos_conciliaciones",
        )

    if resultado["resumen"].get("movimientos_bancarios_pendientes", 0) > 0 and resultado["resumen"].get("sugerencias", 0) == 0:
        _agregar_alerta(
            resultado,
            codigo="CONCILIACION_PARAM_SIN_CANDIDATOS",
            severidad="INFORMATIVO",
            titulo="No se encontraron candidatos de conciliación",
            detalle="Hay movimientos pendientes, pero no se detectaron pares Banco/Tesorería dentro de la tolerancia configurada.",
            entidad="conciliacion",
        )


def _agregar_recomendaciones(resultado: Dict[str, Any]) -> None:
    recomendaciones: List[str] = []
    resumen = resultado.get("resumen", {})

    if resumen.get("sugerencias_alta", 0):
        recomendaciones.append("Revisar primero las sugerencias de confianza alta; son candidatas para una futura aceptación controlada.")
    if resumen.get("sugerencias_media", 0):
        recomendaciones.append("Las sugerencias de confianza media deben mostrarse como conciliación asistida, no automática.")
    if resumen.get("sugerencias_ambiguas", 0):
        recomendaciones.append("Separar candidatos ambiguos en una bandeja de revisión manual.")
    if resumen.get("movimientos_sin_sugerencia", 0):
        recomendaciones.append("Analizar movimientos bancarios sin sugerencia: pueden requerir carga operativa faltante o clasificación bancaria previa.")
    if not recomendaciones:
        recomendaciones.append("No se detectaron acciones de parametrización asistida relevantes para Conciliación.")

    resultado["recomendaciones"] = recomendaciones


def _actualizar_estado_general(resultado: Dict[str, Any]) -> None:
    peor = "OK"
    for alerta in resultado.get("alertas", []):
        severidad = _texto_upper(alerta.get("severidad") or "INFORMATIVO")
        if SEVERIDAD_ORDEN.get(severidad, 0) > SEVERIDAD_ORDEN.get(peor, 0):
            peor = severidad
    resultado["estado"] = peor


def _coincidencia_referencias(movimiento: Dict[str, Any], operacion: Dict[str, Any]) -> Dict[str, Any]:
    refs_banco = _referencias_utiles(
        movimiento.get("referencia"),
        movimiento.get("concepto"),
        movimiento.get("causal"),
    )
    refs_tesoreria = _referencias_utiles(
        operacion.get("referencia_externa"),
        operacion.get("descripcion"),
        operacion.get("tercero_cuit"),
    )
    motivos: List[str] = []
    if not refs_banco or not refs_tesoreria:
        return {"score": 0, "motivos": motivos}

    for ref_banco in refs_banco:
        for ref_tesoreria in refs_tesoreria:
            if ref_banco == ref_tesoreria:
                motivos.append("referencia exacta Banco/Tesorería")
                return {"score": 28, "motivos": motivos}
            if len(ref_banco) >= 8 and len(ref_tesoreria) >= 8:
                if ref_banco in ref_tesoreria or ref_tesoreria in ref_banco:
                    motivos.append("referencia contenida Banco/Tesorería")
                    return {"score": 20, "motivos": motivos}
    return {"score": 0, "motivos": motivos}


def _coincidencia_texto(movimiento: Dict[str, Any], operacion: Dict[str, Any]) -> Dict[str, Any]:
    texto_banco = _normalizar_texto(" ".join([
        _texto(movimiento.get("referencia")),
        _texto(movimiento.get("concepto")),
        _texto(movimiento.get("causal")),
        _texto(movimiento.get("banco")),
        _texto(movimiento.get("nombre_cuenta")),
    ]))
    texto_tesoreria = _normalizar_texto(" ".join([
        _texto(operacion.get("referencia_externa")),
        _texto(operacion.get("descripcion")),
        _texto(operacion.get("tercero_nombre")),
        _texto(operacion.get("tercero_cuit")),
        _texto(operacion.get("medio_pago")),
        _texto(operacion.get("cuenta_tesoreria")),
    ]))
    tokens_banco = _tokens_utiles(texto_banco)
    tokens_tesoreria = _tokens_utiles(texto_tesoreria)
    comunes = tokens_banco.intersection(tokens_tesoreria)
    motivos: List[str] = []
    score = min(len(comunes) * 5, 18)
    if comunes:
        motivos.append("coincidencia de texto: " + ", ".join(sorted(list(comunes))[:4]))

    tercero_cuit = re.sub(r"\D+", "", _texto(operacion.get("tercero_cuit")))
    banco_digitos = re.sub(r"\D+", "", texto_banco)
    if tercero_cuit and len(tercero_cuit) >= 8 and tercero_cuit in banco_digitos:
        score += 10
        motivos.append("CUIT del tercero encontrado en banco")

    return {"score": min(score, 24), "motivos": motivos}


def _coincidencia_tipo_operacion(movimiento: Dict[str, Any], operacion: Dict[str, Any]) -> Dict[str, Any]:
    importe_banco = _numero(movimiento.get("importe"))
    tipo = _texto_upper(operacion.get("tipo_operacion"))
    subtipo = _texto_upper(operacion.get("subtipo"))
    origen = _texto_upper(operacion.get("origen_modulo"))
    motivos: List[str] = []

    if importe_banco > 0 and tipo in {"COBRANZA", "INGRESO"}:
        motivos.append("crédito bancario compatible con cobranza/ingreso")
        return {"score": 10, "motivos": motivos}
    if importe_banco < 0 and tipo in {"PAGO", "EGRESO", "IMPUESTO", "TRANSFERENCIA"}:
        motivos.append("débito bancario compatible con pago/egreso")
        return {"score": 10, "motivos": motivos}
    if importe_banco < 0 and ("PAGO" in subtipo or "PAGO" in origen):
        motivos.append("origen operativo compatible con pago")
        return {"score": 8, "motivos": motivos}
    if importe_banco > 0 and ("COBRANZA" in subtipo or "COBRANZA" in origen):
        motivos.append("origen operativo compatible con cobranza")
        return {"score": 8, "motivos": motivos}
    return {"score": 0, "motivos": motivos}


def _leer_movimientos_bancarios_pendientes(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, "bancos_movimientos"):
        return []
    columnas = _columnas_tabla(con, "bancos_movimientos")
    select = _columnas_para_select(columnas)
    where = ["empresa_id = ?"] if "empresa_id" in columnas else []
    params: List[Any] = [empresa_id] if "empresa_id" in columnas else []
    if "estado_conciliacion" in columnas:
        where.append("COALESCE(estado_conciliacion, 'PENDIENTE') IN ('PENDIENTE', 'PARCIAL')")
    sql = f"SELECT {select} FROM bancos_movimientos"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + ("fecha, id" if "fecha" in columnas else "id")
    filas = [_fila_a_dict(row) for row in con.execute(sql, params).fetchall()]
    return [fila for fila in filas if _pendiente_financiero(fila) > 0.01]


def _leer_operaciones_tesoreria_pendientes(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, "tesoreria_operaciones"):
        return []
    columnas = _columnas_tabla(con, "tesoreria_operaciones")
    select = _columnas_para_select(columnas, alias="o")
    joins = ""
    if _tabla_existe(con, "tesoreria_cuentas"):
        columnas_cuentas = _columnas_tabla(con, "tesoreria_cuentas")
        if "cuenta_tesoreria_id" in columnas and "id" in columnas_cuentas:
            joins += " LEFT JOIN tesoreria_cuentas c ON c.id = o.cuenta_tesoreria_id"
            if "nombre" in columnas_cuentas:
                select += ", c.nombre AS cuenta_tesoreria"
            if "tipo_cuenta" in columnas_cuentas:
                select += ", c.tipo_cuenta AS tipo_cuenta"
    if _tabla_existe(con, "tesoreria_medios_pago"):
        columnas_medios = _columnas_tabla(con, "tesoreria_medios_pago")
        if "medio_pago_id" in columnas and "id" in columnas_medios:
            joins += " LEFT JOIN tesoreria_medios_pago mp ON mp.id = o.medio_pago_id"
            if "nombre" in columnas_medios:
                select += ", mp.nombre AS medio_pago"

    where = ["o.empresa_id = ?"] if "empresa_id" in columnas else []
    params: List[Any] = [empresa_id] if "empresa_id" in columnas else []
    if "estado" in columnas:
        where.append("COALESCE(o.estado, 'CONFIRMADA') <> 'ANULADA'")
    if "estado_conciliacion" in columnas:
        where.append("COALESCE(o.estado_conciliacion, 'PENDIENTE') IN ('PENDIENTE', 'SUGERIDA', 'PARCIAL')")
    sql = f"SELECT {select} FROM tesoreria_operaciones o{joins}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + ("o.fecha_operacion, o.id" if "fecha_operacion" in columnas else "o.id")
    filas = [_fila_a_dict(row) for row in con.execute(sql, params).fetchall()]
    return [fila for fila in filas if _pendiente_financiero(fila) > 0.01]


def _leer_pares_conciliacion_activos(con: sqlite3.Connection, empresa_id: int) -> Set[Tuple[int, int]]:
    if not (_tabla_existe(con, "bancos_conciliaciones") and _tabla_existe(con, "bancos_conciliaciones_detalle")):
        return set()
    columnas_c = _columnas_tabla(con, "bancos_conciliaciones")
    columnas_d = _columnas_tabla(con, "bancos_conciliaciones_detalle")
    if not {"id", "movimiento_banco_id"}.issubset(set(columnas_c)):
        return set()
    if not {"conciliacion_id", "entidad_id"}.issubset(set(columnas_d)):
        return set()

    where = []
    params: List[Any] = []
    if "empresa_id" in columnas_c:
        where.append("c.empresa_id = ?")
        params.append(empresa_id)
    if "estado" in columnas_c:
        where.append("COALESCE(c.estado, 'CONFIRMADA') IN ('CONFIRMADA', 'PARCIAL')")
    if "tipo_conciliacion" in columnas_c:
        where.append("COALESCE(c.tipo_conciliacion, 'TESORERIA_OPERACION') = 'TESORERIA_OPERACION'")
    if "entidad_tabla" in columnas_d:
        where.append("COALESCE(d.entidad_tabla, 'tesoreria_operaciones') = 'tesoreria_operaciones'")
    sql = """
        SELECT c.movimiento_banco_id AS movimiento_banco_id, d.entidad_id AS operacion_tesoreria_id
        FROM bancos_conciliaciones c
        JOIN bancos_conciliaciones_detalle d ON d.conciliacion_id = c.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    pares: Set[Tuple[int, int]] = set()
    for row in con.execute(sql, params).fetchall():
        fila = _fila_a_dict(row)
        mov_id = _entero(fila.get("movimiento_banco_id"))
        ope_id = _entero(fila.get("operacion_tesoreria_id"))
        if mov_id and ope_id:
            pares.add((mov_id, ope_id))
    return pares


def _resumen_movimiento(mov: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _entero(mov.get("id")),
        "fecha": _texto(mov.get("fecha")),
        "banco": _texto(mov.get("banco")),
        "cuenta": _texto(mov.get("nombre_cuenta")),
        "concepto": _texto(mov.get("concepto")),
        "referencia": _texto(mov.get("referencia")),
        "importe": round(_numero(mov.get("importe")), 2),
        "importe_pendiente": round(_pendiente_financiero(mov), 2),
        "estado_conciliacion": _texto_upper(mov.get("estado_conciliacion") or "PENDIENTE"),
    }


def _resumen_operacion(ope: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _entero(ope.get("id")),
        "fecha_operacion": _texto(ope.get("fecha_operacion") or ope.get("fecha")),
        "tipo_operacion": _texto_upper(ope.get("tipo_operacion")),
        "subtipo": _texto_upper(ope.get("subtipo")),
        "origen_modulo": _texto_upper(ope.get("origen_modulo")),
        "cuenta_tesoreria": _texto(ope.get("cuenta_tesoreria")),
        "tercero_nombre": _texto(ope.get("tercero_nombre")),
        "tercero_cuit": _texto(ope.get("tercero_cuit")),
        "descripcion": _texto(ope.get("descripcion")),
        "referencia_externa": _texto(ope.get("referencia_externa")),
        "importe": round(_numero(ope.get("importe")), 2),
        "importe_pendiente": round(_pendiente_financiero(ope), 2),
        "estado": _texto_upper(ope.get("estado") or "CONFIRMADA"),
        "estado_conciliacion": _texto_upper(ope.get("estado_conciliacion") or "PENDIENTE"),
    }


def _referencias_utiles(*valores: Any) -> Set[str]:
    refs: Set[str] = set()
    for valor in valores:
        texto = _normalizar_texto(valor)
        if not texto:
            continue
        for token in re.findall(r"[A-Z0-9]{5,}", texto):
            if token not in PALABRAS_RUIDO:
                refs.add(token)
    return refs


def _tokens_utiles(valor: Any, largo_minimo: int = 4) -> Set[str]:
    texto = _normalizar_texto(valor)
    tokens = set()
    for token in re.findall(r"[A-Z0-9]+", texto):
        if len(token) >= largo_minimo and token not in PALABRAS_RUIDO:
            tokens.add(token)
    return tokens


def _normalizar_texto(valor: Any) -> str:
    texto = _texto(valor).upper()
    reemplazos = {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U", "Ñ": "N",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _dias_entre(fecha_a: Any, fecha_b: Any) -> Optional[int]:
    fa = _fecha(fecha_a)
    fb = _fecha(fecha_b)
    if fa is None or fb is None:
        return None
    return (fa - fb).days


def _fecha(valor: Any) -> Optional[date]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = _texto(valor)
    if not texto:
        return None
    formatos = ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y")
    for formato in formatos:
        try:
            return datetime.strptime(texto[:19] if "%H" in formato else texto[:10], formato).date()
        except ValueError:
            continue
    return None


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


def _columnas_para_select(columnas: Sequence[str], alias: str = "") -> str:
    prefijo = f"{alias}." if alias else ""
    if not columnas:
        return "*"
    return ", ".join(f"{prefijo}{col}" for col in columnas)


def _fila_a_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return {clave: row[clave] for clave in row.keys()}
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


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

    raiz = Path(__file__).resolve().parents[1]
    rutas = (
        raiz / "data" / "sistema_contable.db",
        raiz / "data" / "contabilidad.db",
        raiz / "sistema_contable.db",
        raiz / "contabilidad.db",
        raiz / "database.db",
    )
    for ruta in rutas:
        if ruta.exists():
            return sqlite3.connect(str(ruta))

    raise ConciliacionParametrizacionError(
        "No se pudo obtener una conexión SQLite para parametrización asistida de Conciliación. "
        "Pase una conexión explícita con analizar_parametrizacion_conciliacion(..., conexion=con)."
    )


def _agregar_alerta(
    resultado: Dict[str, Any],
    codigo: str,
    severidad: str,
    titulo: str,
    detalle: str,
    entidad: str = "",
    entidad_id: Any = None,
) -> None:
    resultado.setdefault("alertas", []).append({
        "codigo": _texto_upper(codigo),
        "severidad": _texto_upper(severidad or "INFORMATIVO"),
        "titulo": _texto(titulo),
        "detalle": _texto(detalle),
        "entidad": _texto(entidad),
        "entidad_id": entidad_id,
    })


def _unicos(valores: Iterable[str]) -> List[str]:
    vistos = set()
    salida: List[str] = []
    for valor in valores:
        texto = _texto(valor)
        if texto and texto not in vistos:
            vistos.add(texto)
            salida.append(texto)
    return salida


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


def _signo(valor: Any) -> int:
    numero = _numero(valor)
    if numero > 0:
        return 1
    if numero < 0:
        return -1
    return 0
