from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


USOS_BANCO = {"BANCO", "BANCO_CUENTA_CORRIENTE", "BANCO_CAJA_AHORRO"}
USOS_CAJA = {"CAJA", "CAJA_GENERAL", "FONDO_FIJO", "RECAUDACIONES_A_DEPOSITAR"}
USOS_CLIENTES = {"CLIENTES", "DEUDORES_POR_VENTAS", "CUENTAS_A_COBRAR", "SALDOS_A_FAVOR_CLIENTES"}
USOS_PROVEEDORES = {"PROVEEDORES", "CUENTAS_A_PAGAR", "ANTICIPO_A_PROVEEDOR"}
USOS_IVA_CREDITO = {"IVA_CREDITO_FISCAL", "IVA_CREDITO", "CREDITO_FISCAL_IVA"}
USOS_PERCEPCION_IVA = {"PERCEPCION_IVA", "PERCEPCIONES_IVA"}
USOS_PERCEPCION_IIBB = {"PERCEPCION_IIBB", "PERCEPCIONES_IIBB"}
USOS_IMPUESTOS = {"IMPUESTOS_A_PAGAR", "CARGAS_FISCALES", "IVA_SALDO_A_PAGAR", "PAGO_IMPUESTOS"}
USOS_SOCIOS = {"CUENTA_PARTICULAR_SOCIOS", "PRESTAMO_SOCIO", "APORTES_IRREVOCABLES", "CAPITAL_SOCIAL"}

PATRONES_TIPO_MOVIMIENTO = {
    "GASTO_BANCARIO_GRAVADO": {
        "debe_usos": {"GASTOS_BANCARIOS", "COMISIONES_BANCARIAS", "GASTOS_Y_COMISIONES_BANCARIAS"},
        "debe_keywords": ["GASTO BANC", "COMISION", "COMIS", "MANTENIMIENTO CUENTA"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "GASTO_BANCARIO_GRAVADO",
    },
    "IVA_CREDITO_FISCAL_BANCARIO": {
        "debe_usos": USOS_IVA_CREDITO,
        "debe_keywords": ["IVA CREDITO", "CRÉDITO FISCAL", "CREDITO FISCAL"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "IVA_CREDITO_FISCAL",
    },
    "PERCEPCION_IVA_BANCARIA": {
        "debe_usos": USOS_PERCEPCION_IVA,
        "debe_keywords": ["PERCEPCION IVA", "PERCEPCIONES IVA"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "PERCEPCION_IVA_COMPUTABLE",
    },
    "RECAUDACION_IIBB": {
        "debe_usos": USOS_PERCEPCION_IIBB,
        "debe_keywords": ["PERCEPCION IIBB", "PERCEPCIONES IIBB", "INGRESOS BRUTOS"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "PERCEPCION_IIBB_INFORMATIVA",
    },
    "IMPUESTO_DEBITOS_CREDITOS": {
        "debe_usos": {"IMPUESTO_DEBITOS_CREDITOS", "IMPUESTOS_Y_TASAS", "GASTOS_BANCARIOS"},
        "debe_keywords": ["DEBITOS Y CREDITOS", "DÉBITOS Y CRÉDITOS", "LEY 25413", "IMPUESTO DEBITO"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "LEY_25413_CONTROL",
    },
    "PAGO_IMPUESTOS": {
        "debe_usos": USOS_IMPUESTOS,
        "debe_keywords": ["IMPUESTO", "ARCA", "AFIP", "IVA SALDO", "CARGAS FISCALES"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "PAGO_IMPUESTOS",
    },
    "COBRO_POSIBLE": {
        "debe_usos": USOS_BANCO,
        "debe_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "haber_usos": USOS_CLIENTES,
        "haber_keywords": ["DEUDORES", "CLIENTES", "CUENTAS A COBRAR"],
        "impacto_fiscal": "CONCILIAR_CLIENTE_ANTICIPO_OTRO",
    },
    "PAGO_POSIBLE": {
        "debe_usos": USOS_PROVEEDORES,
        "debe_keywords": ["PROVEEDORES", "CUENTAS A PAGAR"],
        "haber_usos": USOS_BANCO,
        "haber_keywords": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "CONCILIAR_PROVEEDOR_ANTICIPO_GASTO",
    },
    "TRANSFERENCIA_ENTRE_CUENTAS": {
        "debe_usos": USOS_CAJA | USOS_BANCO,
        "debe_keywords": ["BANCO", "CAJA", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "haber_usos": USOS_BANCO | USOS_CAJA,
        "haber_keywords": ["BANCO", "CAJA", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
        "impacto_fiscal": "SIN_IMPACTO_RESULTADO",
    },
    "EFECTIVO_CAJA": {
        "debe_usos": USOS_CAJA | USOS_BANCO,
        "debe_keywords": ["CAJA", "EFECTIVO", "RECAUDACIONES", "BANCO"],
        "haber_usos": USOS_BANCO | USOS_CAJA,
        "haber_keywords": ["BANCO", "CAJA", "EFECTIVO"],
        "impacto_fiscal": "REQUIERE_IMPUTACION",
    },
    "MOVIMIENTO_SOCIOS": {
        "debe_usos": USOS_SOCIOS | USOS_BANCO,
        "debe_keywords": ["SOCIO", "DIRECTOR", "CUENTA PARTICULAR", "CAPITAL", "APORTE"],
        "haber_usos": USOS_SOCIOS | USOS_BANCO,
        "haber_keywords": ["SOCIO", "DIRECTOR", "CUENTA PARTICULAR", "CAPITAL", "APORTE", "BANCO"],
        "impacto_fiscal": "PATRIMONIAL_REQUIERE_REVISION",
    },
}

TIPOS_FISCALES_IVA = {
    "IVA_CREDITO_FISCAL_BANCARIO",
    "PERCEPCION_IVA_BANCARIA",
    "RECAUDACION_IIBB",
    "IMPUESTO_DEBITOS_CREDITOS",
    "GASTO_BANCARIO_GRAVADO",
}

CONFIANZA_ORDEN = {"NULA": 0, "BAJA": 1, "MEDIA": 2, "ALTA": 3}


def generar_parametrizacion_asistida_bancos(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
    limite_movimientos: int = 300,
) -> Dict[str, Any]:
    """
    Banco/Caja PRO v2A: parametrización asistida de solo lectura.

    Devuelve sugerencias para cuentas bancarias, movimientos, tipos de
    clasificación, impacto fiscal y futura integración con Tesorería/Conciliación.
    No crea reglas, no vincula cuentas, no modifica movimientos, no genera IVA,
    no genera asientos y no llama a inicializar_bancos().
    """

    empresa_id = int(empresa_id or 1)
    cerrar_conexion = conexion is None
    con = conexion or _obtener_conexion()

    try:
        _configurar_conexion(con)
        plan = _leer_plan_empresa(con, empresa_id)
        cuentas_bancarias = _leer_filas_empresa(con, "bancos_cuentas", empresa_id)
        movimientos = _leer_filas_empresa(con, "bancos_movimientos", empresa_id)
        reglas = _leer_filas_empresa(con, "bancos_reglas_clasificacion", empresa_id)
        grupos_fiscales = _leer_filas_empresa(con, "bancos_grupos_fiscales", empresa_id)

        matriz: Dict[str, Any] = {
            "empresa_id": empresa_id,
            "estado": "OK",
            "solo_lectura": True,
            "resumen": {
                "cuentas_bancarias": len(cuentas_bancarias),
                "cuentas_con_sugerencia_alta": 0,
                "cuentas_requieren_revision": 0,
                "movimientos_analizados": 0,
                "tipos_movimiento_detectados": 0,
                "tipos_con_sugerencia_alta": 0,
                "tipos_requieren_revision": 0,
                "movimientos_con_sugerencia_alta": 0,
                "movimientos_con_sugerencia_media": 0,
                "movimientos_con_sugerencia_baja": 0,
                "movimientos_sin_sugerencia": 0,
                "grupos_fiscales_pendientes": 0,
                "reglas_existentes": len(reglas),
            },
            "plan_cuentas": {
                "cuentas_leidas": len(plan),
                "fuente": "plan_cuentas_empresa",
            },
            "cuentas_bancarias": [],
            "tipos_movimiento": [],
            "movimientos_muestra": [],
            "fiscal": {
                "grupos_pendientes": [],
                "sugerencias": [],
            },
            "reglas_existentes": [_resumen_regla(regla) for regla in reglas],
            "alertas": [],
            "recomendaciones": [],
        }

        sugerencias_cuenta = _sugerir_cuentas_bancarias(cuentas_bancarias, plan)
        matriz["cuentas_bancarias"] = sugerencias_cuenta
        matriz["resumen"]["cuentas_con_sugerencia_alta"] = sum(1 for item in sugerencias_cuenta if item.get("confianza") == "ALTA")
        matriz["resumen"]["cuentas_requieren_revision"] = sum(1 for item in sugerencias_cuenta if item.get("accion_sugerida") != "MANTENER")

        tipos = _agrupar_movimientos_por_tipo(movimientos)
        sugerencias_tipos = [_sugerir_tipo_movimiento(tipo, filas, plan) for tipo, filas in sorted(tipos.items())]
        matriz["tipos_movimiento"] = sugerencias_tipos
        matriz["resumen"]["tipos_movimiento_detectados"] = len(sugerencias_tipos)
        matriz["resumen"]["tipos_con_sugerencia_alta"] = sum(1 for item in sugerencias_tipos if item.get("confianza") == "ALTA")
        matriz["resumen"]["tipos_requieren_revision"] = sum(1 for item in sugerencias_tipos if item.get("accion_sugerida") != "MANTENER")

        muestra = _seleccionar_muestra_movimientos(movimientos, limite_movimientos=limite_movimientos)
        matriz["movimientos_muestra"] = [_sugerir_movimiento(mov, plan) for mov in muestra]
        matriz["resumen"]["movimientos_analizados"] = len(matriz["movimientos_muestra"])
        for item in matriz["movimientos_muestra"]:
            confianza = item.get("confianza", "NULA")
            if confianza == "ALTA":
                matriz["resumen"]["movimientos_con_sugerencia_alta"] += 1
            elif confianza == "MEDIA":
                matriz["resumen"]["movimientos_con_sugerencia_media"] += 1
            elif confianza == "BAJA":
                matriz["resumen"]["movimientos_con_sugerencia_baja"] += 1
            else:
                matriz["resumen"]["movimientos_sin_sugerencia"] += 1

        _sugerir_fiscal(matriz, grupos_fiscales)
        _agregar_alertas_y_recomendaciones(matriz)
        _actualizar_estado(matriz)
        return matriz
    finally:
        if cerrar_conexion:
            con.close()


def parametrizar_banco_caja_asistido(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
    limite_movimientos: int = 300,
) -> Dict[str, Any]:
    """Alias explícito para UI/futuro."""

    return generar_parametrizacion_asistida_bancos(
        empresa_id=empresa_id,
        conexion=conexion,
        limite_movimientos=limite_movimientos,
    )


def _sugerir_cuentas_bancarias(cuentas_bancarias: Sequence[Dict[str, Any]], plan: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resultado = []
    for cuenta in cuentas_bancarias:
        codigo_actual = _texto(cuenta.get("cuenta_contable_codigo"))
        candidato = _buscar_mejor_cuenta(plan, USOS_BANCO, ["BANCO", cuenta.get("banco"), cuenta.get("nombre_cuenta")])
        confianza = candidato.get("confianza", "NULA") if candidato else "NULA"
        accion = "REVISAR"
        motivo = "No se encontró una cuenta bancaria clara en Plan Empresa."

        if codigo_actual and candidato and codigo_actual == candidato.get("codigo"):
            accion = "MANTENER"
            motivo = "La cuenta bancaria ya coincide con la mejor sugerencia del Plan Empresa."
        elif codigo_actual and not candidato:
            accion = "REVISAR_VINCULO_EXISTENTE"
            motivo = "Existe cuenta contable cargada, pero no se pudo validar contra una sugerencia fuerte."
        elif candidato:
            accion = "SUGERIR_VINCULACION"
            motivo = "Se encontró una cuenta bancaria probable en Plan Empresa."

        resultado.append({
            "cuenta_bancaria_id": _obtener_id(cuenta),
            "banco": _texto(cuenta.get("banco")),
            "nombre_cuenta": _texto(cuenta.get("nombre_cuenta")),
            "cuenta_contable_actual_codigo": codigo_actual,
            "cuenta_contable_actual_nombre": _texto(cuenta.get("cuenta_contable_nombre")),
            "cuenta_sugerida": candidato,
            "confianza": confianza,
            "accion_sugerida": accion,
            "motivo": motivo,
        })
    return resultado


def _agrupar_movimientos_por_tipo(movimientos: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grupos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for mov in movimientos:
        tipo = _texto_upper(mov.get("tipo_movimiento_sugerido") or "A_REVISAR")
        grupos[tipo].append(mov)
    return grupos


def _sugerir_tipo_movimiento(tipo: str, movimientos: Sequence[Dict[str, Any]], plan: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    patron = PATRONES_TIPO_MOVIMIENTO.get(tipo, PATRONES_TIPO_MOVIMIENTO.get("GASTO_BANCARIO_GRAVADO", {}))
    importe_neto = round(sum(_numero(mov.get("importe")) for mov in movimientos), 2)
    debitos = round(sum(abs(_numero(mov.get("importe"))) for mov in movimientos if _numero(mov.get("importe")) < 0), 2)
    creditos = round(sum(abs(_numero(mov.get("importe"))) for mov in movimientos if _numero(mov.get("importe")) > 0), 2)

    debe = _buscar_mejor_cuenta(plan, patron.get("debe_usos", set()), patron.get("debe_keywords", []))
    haber = _buscar_mejor_cuenta(plan, patron.get("haber_usos", USOS_BANCO), patron.get("haber_keywords", ["BANCO"]))
    confianza = _combinar_confianza(debe, haber)
    accion = "MANTENER" if confianza == "ALTA" else "REVISAR"
    if tipo not in PATRONES_TIPO_MOVIMIENTO:
        accion = "CLASIFICAR_MANUALMENTE"
        confianza = "BAJA" if debe or haber else "NULA"

    return {
        "tipo_movimiento": tipo,
        "movimientos": len(movimientos),
        "debitos": debitos,
        "creditos": creditos,
        "neto": importe_neto,
        "debe_sugerido": debe,
        "haber_sugerido": haber,
        "tratamiento_fiscal_sugerido": patron.get("impacto_fiscal", "REQUIERE_REVISION"),
        "requiere_iva": tipo in TIPOS_FISCALES_IVA,
        "requiere_conciliacion": tipo in {"COBRO_POSIBLE", "PAGO_POSIBLE", "TRANSFERENCIA_ENTRE_CUENTAS", "EFECTIVO_CAJA", "MOVIMIENTO_SOCIOS", "A_REVISAR"},
        "confianza": confianza,
        "accion_sugerida": accion,
        "motivo": _motivo_tipo(tipo, confianza, debe, haber),
    }


def _sugerir_movimiento(mov: Dict[str, Any], plan: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tipo = _texto_upper(mov.get("tipo_movimiento_sugerido") or "A_REVISAR")
    base = _sugerir_tipo_movimiento(tipo, [mov], plan)
    concepto = " ".join([
        _texto(mov.get("concepto")),
        _texto(mov.get("causal")),
        _texto(mov.get("referencia")),
    ])

    ajuste_confianza = _score_texto_movimiento(concepto, tipo)
    confianza = base.get("confianza", "NULA")
    if ajuste_confianza >= 15 and CONFIANZA_ORDEN.get(confianza, 0) < CONFIANZA_ORDEN["MEDIA"]:
        confianza = "MEDIA"
    elif ajuste_confianza <= 0 and confianza == "ALTA":
        confianza = "MEDIA"

    return {
        "movimiento_banco_id": _obtener_id(mov),
        "fecha": _texto(mov.get("fecha")),
        "banco": _texto(mov.get("banco")),
        "nombre_cuenta": _texto(mov.get("nombre_cuenta")),
        "concepto": _texto(mov.get("concepto")),
        "referencia": _texto(mov.get("referencia")),
        "importe": _numero(mov.get("importe")),
        "tipo_movimiento": tipo,
        "debe_sugerido": base.get("debe_sugerido"),
        "haber_sugerido": base.get("haber_sugerido"),
        "tratamiento_fiscal_sugerido": base.get("tratamiento_fiscal_sugerido"),
        "requiere_iva": base.get("requiere_iva", False),
        "requiere_conciliacion": base.get("requiere_conciliacion", False),
        "confianza": confianza,
        "accion_sugerida": "REVISAR" if confianza in {"BAJA", "NULA"} else "SUGERIR",
        "motivo": base.get("motivo", ""),
    }


def _seleccionar_muestra_movimientos(movimientos: Sequence[Dict[str, Any]], limite_movimientos: int) -> List[Dict[str, Any]]:
    limite = max(int(limite_movimientos or 0), 0)
    if limite <= 0 or len(movimientos) <= limite:
        return list(movimientos)

    # Muestra equilibrada: primero pendientes/parciales y luego importes más significativos.
    ordenados = sorted(
        movimientos,
        key=lambda mov: (
            0 if _texto_upper(mov.get("estado_conciliacion")) in {"PENDIENTE", "PARCIAL"} else 1,
            -abs(_numero(mov.get("importe"))),
            _texto(mov.get("fecha")),
        ),
    )
    return ordenados[:limite]


def _sugerir_fiscal(matriz: Dict[str, Any], grupos_fiscales: Sequence[Dict[str, Any]]) -> None:
    for grupo in grupos_fiscales:
        estado = _texto_upper(grupo.get("estado_revision") or "PENDIENTE")
        total_iva = _numero(grupo.get("iva_credito_21")) + _numero(grupo.get("iva_credito_105")) + _numero(grupo.get("iva_sin_base"))
        percepcion_iva = _numero(grupo.get("percepcion_iva"))
        if estado in {"PENDIENTE", "REVISAR_ALICUOTA", "REVISAR_DIFERENCIA", "IVA_SIN_BASE", "BASE_SIN_IVA"}:
            matriz["resumen"]["grupos_fiscales_pendientes"] += 1
            item = {
                "grupo_fiscal_id": _obtener_id(grupo),
                "fecha": _texto(grupo.get("fecha")),
                "banco": _texto(grupo.get("banco")),
                "nombre_cuenta": _texto(grupo.get("nombre_cuenta")),
                "estado_revision": estado,
                "iva_credito_detectado": round(total_iva, 2),
                "percepcion_iva_detectada": round(percepcion_iva, 2),
                "accion_sugerida": "DECIDIR_EN_CONTROL_FISCAL_BANCARIO" if abs(total_iva) > 0.01 or abs(percepcion_iva) > 0.01 else "CONTROL_INFORMATIVO",
            }
            matriz["fiscal"]["grupos_pendientes"].append(item)

    if matriz["resumen"]["grupos_fiscales_pendientes"] > 0:
        matriz["fiscal"]["sugerencias"].append(
            "Revisar grupos fiscales bancarios pendientes antes de confirmar IVA o generar asientos definitivos."
        )


def _buscar_mejor_cuenta(plan: Sequence[Dict[str, Any]], usos: Iterable[str], keywords: Iterable[Any]) -> Optional[Dict[str, Any]]:
    usos_norm = {_normalizar_uso_operativo(uso) for uso in usos if _texto(uso)}
    keywords_norm = [_normalizar_texto_busqueda(k) for k in keywords if _texto(k)]
    candidatos = []

    for cuenta in plan:
        codigo = _texto(cuenta.get("codigo") or cuenta.get("cuenta_codigo") or cuenta.get("cuenta"))
        nombre = _texto(cuenta.get("nombre") or cuenta.get("detalle"))
        if not codigo or not nombre:
            continue
        if not _es_activo(cuenta.get("estado") or cuenta.get("activo"), default=True):
            continue
        if not _es_imputable(cuenta.get("imputable"), default=True):
            continue

        uso = _normalizar_uso_operativo(cuenta.get("uso_operativo_sistema"))
        texto = _normalizar_texto_busqueda(f"{codigo} {nombre} {uso}")
        score = 0
        motivos = []

        if uso and uso in usos_norm:
            score += 70
            motivos.append(f"uso operativo {uso}")

        for keyword in keywords_norm:
            if keyword and keyword in texto:
                score += 18
                motivos.append(f"coincide texto {keyword}")

        if _texto(cuenta.get("cuenta_maestro_id")):
            score += 4
            motivos.append("vinculada al Plan Maestro")
        if _es_activo(cuenta.get("es_cuenta_especifica_empresa"), default=False):
            score += 3
            motivos.append("cuenta específica de empresa")
        if _es_activo(cuenta.get("es_cuenta_modelo"), default=False):
            score -= 5
            motivos.append("cuenta modelo; revisar si corresponde cuenta específica")

        if score > 0:
            candidatos.append((score, cuenta, motivos))

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: item[0], reverse=True)
    score, cuenta, motivos = candidatos[0]
    confianza = "ALTA" if score >= 75 else "MEDIA" if score >= 45 else "BAJA"
    return {
        "codigo": _texto(cuenta.get("codigo") or cuenta.get("cuenta_codigo") or cuenta.get("cuenta")),
        "nombre": _texto(cuenta.get("nombre") or cuenta.get("detalle")),
        "uso_operativo_sistema": _normalizar_uso_operativo(cuenta.get("uso_operativo_sistema")),
        "cuenta_maestro_id": cuenta.get("cuenta_maestro_id"),
        "score": int(score),
        "confianza": confianza,
        "motivos": motivos[:5],
    }


def _combinar_confianza(debe: Optional[Dict[str, Any]], haber: Optional[Dict[str, Any]]) -> str:
    if not debe or not haber:
        if debe or haber:
            return "BAJA"
        return "NULA"
    menor = min(CONFIANZA_ORDEN.get(debe.get("confianza", "NULA"), 0), CONFIANZA_ORDEN.get(haber.get("confianza", "NULA"), 0))
    for nombre, valor in CONFIANZA_ORDEN.items():
        if valor == menor:
            return nombre
    return "NULA"


def _motivo_tipo(tipo: str, confianza: str, debe: Optional[Dict[str, Any]], haber: Optional[Dict[str, Any]]) -> str:
    if tipo not in PATRONES_TIPO_MOVIMIENTO:
        return "Tipo bancario no parametrizado todavía; requiere revisión manual."
    if confianza == "ALTA":
        return "Se encontraron cuentas activas e imputables compatibles para Debe y Haber."
    if debe and not haber:
        return "Se encontró cuenta probable para Debe, pero falta cuenta bancaria/Haber confiable."
    if haber and not debe:
        return "Se encontró cuenta bancaria/Haber probable, pero falta cuenta de contrapartida confiable."
    return "No se encontraron cuentas suficientemente confiables para automatizar."


def _score_texto_movimiento(texto: str, tipo: str) -> int:
    normalizado = _normalizar_texto_busqueda(texto)
    tipo = _texto_upper(tipo)
    patrones = {
        "IVA_CREDITO_FISCAL_BANCARIO": ["IVA", "DEBITO FISCAL", "IVA BASICO"],
        "PERCEPCION_IVA_BANCARIA": ["PERCEPCION IVA", "PERC IVA"],
        "RECAUDACION_IIBB": ["IIBB", "INGRESOS BRUTOS"],
        "IMPUESTO_DEBITOS_CREDITOS": ["LEY 25413", "DEBITOS Y CREDITOS"],
        "PAGO_IMPUESTOS": ["AFIP", "ARCA", "IVA", "GANANCIAS", "SUSS"],
        "GASTO_BANCARIO_GRAVADO": ["COMISION", "MANTENIMIENTO", "SERVICIO CUENTA"],
        "COBRO_POSIBLE": ["TRANSFERENCIA", "CREDITO", "COBRO"],
        "PAGO_POSIBLE": ["PAGO", "TRANSFERENCIA", "DEBITO"],
        "MOVIMIENTO_SOCIOS": ["SOCIO", "DIRECTOR", "APORTE", "CAPITAL"],
    }
    return sum(5 for patron in patrones.get(tipo, []) if patron in normalizado)


def _agregar_alertas_y_recomendaciones(matriz: Dict[str, Any]) -> None:
    resumen = matriz["resumen"]

    if resumen["cuentas_requieren_revision"] > 0:
        matriz["alertas"].append({
            "codigo": "BANCO_CAJA_PARAM_CUENTAS_REQUIEREN_REVISION",
            "severidad": "ADVERTENCIA",
            "titulo": "Hay cuentas bancarias que requieren revisión de parametrización",
            "detalle": f"Cuentas a revisar: {resumen['cuentas_requieren_revision']}.",
        })
        matriz["recomendaciones"].append(
            "Revisar y aceptar vínculos de cuentas bancarias contra Plan Empresa en una futura v2B auditada."
        )

    if resumen["tipos_requieren_revision"] > 0:
        matriz["alertas"].append({
            "codigo": "BANCO_CAJA_PARAM_TIPOS_REQUIEREN_REVISION",
            "severidad": "ADVERTENCIA",
            "titulo": "Hay tipos de movimiento que requieren parametrización manual",
            "detalle": f"Tipos a revisar: {resumen['tipos_requieren_revision']}.",
        })
        matriz["recomendaciones"].append(
            "No automatizar asientos o imputaciones para tipos con confianza baja o nula."
        )

    if resumen["grupos_fiscales_pendientes"] > 0:
        matriz["recomendaciones"].append(
            "Separar decisión de IVA de la parametrización contable: Banco/Caja v2A solo sugiere; IVA decide período/portal."
        )

    if not matriz["recomendaciones"]:
        matriz["recomendaciones"].append(
            "La matriz de Banco/Caja no detectó bloqueos fuertes. La aceptación auditada debería quedar para v2B."
        )


def _actualizar_estado(matriz: Dict[str, Any]) -> None:
    mayor = "OK"
    orden = {"OK": 0, "INFORMATIVO": 1, "ADVERTENCIA": 2, "CRITICO": 3}
    for alerta in matriz.get("alertas", []):
        severidad = alerta.get("severidad", "OK")
        if orden.get(severidad, 0) > orden.get(mayor, 0):
            mayor = severidad
    matriz["estado"] = "REQUIERE_PARAMETRIZACION" if mayor == "ADVERTENCIA" else "CRITICO" if mayor == "CRITICO" else "OK"


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
                return funcion()
        except Exception:
            continue

    raiz = Path(__file__).resolve().parents[1]
    for ruta in (
        raiz / "data" / "sistema_contable.db",
        raiz / "data" / "contabilidad.db",
        raiz / "sistema_contable.db",
        raiz / "contabilidad.db",
        raiz / "database.db",
    ):
        if ruta.exists():
            return sqlite3.connect(str(ruta))
    raise RuntimeError(
        "No se pudo obtener una conexión SQLite para parametrizar Banco/Caja. "
        "Pase una conexión explícita."
    )


def _configurar_conexion(con: sqlite3.Connection) -> None:
    try:
        con.row_factory = sqlite3.Row
    except Exception:
        pass


def _tabla_existe(con: sqlite3.Connection, tabla: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (tabla,))
    return cur.fetchone() is not None


def _columnas_tabla(con: sqlite3.Connection, tabla: str) -> List[str]:
    if not _tabla_existe(con, tabla):
        return []
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({_identificador_seguro(tabla)})")
    return [str(fila[1]) for fila in cur.fetchall()]


def _identificador_seguro(nombre: str) -> str:
    limpio = "".join(ch for ch in str(nombre) if ch.isalnum() or ch == "_")
    if limpio != nombre or not limpio:
        raise ValueError(f"Identificador SQLite inválido: {nombre}")
    return limpio


def _leer_filas_empresa(con: sqlite3.Connection, tabla: str, empresa_id: int) -> List[Dict[str, Any]]:
    if not _tabla_existe(con, tabla):
        return []
    columnas = _columnas_tabla(con, tabla)
    cur = con.cursor()
    if "empresa_id" in columnas:
        cur.execute(f"SELECT * FROM {_identificador_seguro(tabla)} WHERE empresa_id = ?", (empresa_id,))
    else:
        cur.execute(f"SELECT * FROM {_identificador_seguro(tabla)}")
    return [_fila_a_dict(fila) for fila in cur.fetchall()]


def _leer_plan_empresa(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    return _leer_filas_empresa(con, "plan_cuentas_empresa", empresa_id)


def _fila_a_dict(fila: Any) -> Dict[str, Any]:
    if fila is None:
        return {}
    if isinstance(fila, sqlite3.Row):
        return {clave: fila[clave] for clave in fila.keys()}
    if isinstance(fila, dict):
        return dict(fila)
    try:
        return dict(fila)
    except Exception:
        return {}


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _texto_upper(valor: Any) -> str:
    return _texto(valor).upper()


def _numero(valor: Any) -> float:
    if valor is None:
        return 0.0
    try:
        if isinstance(valor, str):
            texto = valor.strip()
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            valor = texto
        return float(valor)
    except Exception:
        return 0.0


def _es_activo(valor: Any, default: bool = True) -> bool:
    if valor is None:
        return default
    texto = _texto_upper(valor)
    if texto in {"", "NONE", "NULL"}:
        return default
    if texto in {"0", "NO", "N", "FALSE", "FALSO", "INACTIVO", "INACTIVA", "BAJA", "ANULADO", "ANULADA", "ELIMINADO", "ELIMINADA"}:
        return False
    if texto in {"1", "SI", "SÍ", "S", "TRUE", "VERDADERO", "ACTIVO", "ACTIVA", "ALTA"}:
        return True
    return bool(valor)


def _es_imputable(valor: Any, default: bool = True) -> bool:
    return _es_activo(valor, default=default)


def _normalizar_uso_operativo(valor: Any) -> str:
    return _texto_upper(valor).replace(" ", "_").replace("-", "_")


def _normalizar_texto_busqueda(valor: Any) -> str:
    texto = _texto_upper(valor)
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
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _obtener_id(fila: Dict[str, Any]) -> Any:
    for clave in ("id", "movimiento_id", "cuenta_id", "grupo_fiscal_id", "regla_id"):
        if clave in fila and fila.get(clave) is not None:
            return fila.get(clave)
    return None


def _resumen_regla(regla: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "regla_id": _obtener_id(regla),
        "patron": _texto(regla.get("patron")),
        "tipo_movimiento": _texto_upper(regla.get("tipo_movimiento")),
        "cuenta_debe_codigo": _texto(regla.get("cuenta_debe_codigo")),
        "cuenta_haber_codigo": _texto(regla.get("cuenta_haber_codigo")),
        "tratamiento_fiscal": _texto(regla.get("tratamiento_fiscal")),
        "automatizar_asiento": _es_activo(regla.get("automatizar_asiento"), default=False),
    }
