"""
Servicio de parametrización asistida para Compras PRO.

Etapa v2A definitiva: lectura y matriz profesional sin modificar datos.

Regla central:
- Plan Maestro FF es fuente madre.
- Plan de Cuentas Empresa es la parametrización por empresa/usuario.
- Compras debe vincular categorías y conceptos fiscales contra cuentas activas
  e imputables del Plan Empresa.
- Este servicio NO escribe, NO actualiza y NO crea cuentas.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


UMBRAL_SUGERENCIA_CATEGORIA = 100
UMBRAL_SUGERENCIA_FISCAL = 90
MAX_SUGERENCIAS = 5


# ======================================================
# NORMALIZACIÓN / ACCESO SEGURO
# ======================================================

def _normalizar_texto(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = texto.upper().strip()
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _tokenizar(valor: Any) -> list[str]:
    ignorar = {
        "DE", "DEL", "LA", "LAS", "LOS", "Y", "A", "POR", "PARA", "EN",
        "CON", "SIN", "P", "EL", "AL", "O", "U", "UN", "UNA", "VARIOS",
        "VARIAS", "OTROS", "OTRAS", "GASTOS", "GASTO",
    }
    tokens = [t for t in _normalizar_texto(valor).split() if len(t) >= 4 and t not in ignorar]
    return tokens


def _int_bool(valor: Any) -> int:
    try:
        if valor is None:
            return 0
        if isinstance(valor, str):
            return 1 if valor.strip().upper() in {"1", "SI", "SÍ", "TRUE", "ACTIVO", "ACTIVA"} else 0
        return 1 if int(valor) else 0
    except Exception:
        return 0


def _valor(row: dict[str, Any], *claves: str, default: Any = "") -> Any:
    for clave in claves:
        if clave in row and row[clave] is not None:
            return row[clave]
    return default


def _row_a_dict(cursor: sqlite3.Cursor, row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, sqlite3.Row):
        return {k: row[k] for k in row.keys()}
    columnas = [col[0] for col in (cursor.description or [])]
    return {col: row[idx] for idx, col in enumerate(columnas)}


def _consultar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    return [_row_a_dict(cursor, row) for row in cursor.fetchall()]


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tabla,),
    ).fetchone()
    return row is not None


def _abrir_conexion(conn: sqlite3.Connection | None) -> tuple[sqlite3.Connection, bool]:
    if conn is not None:
        return conn, False

    try:
        from database import conectar  # type: ignore

        return conectar(), True
    except Exception:
        return sqlite3.connect("database.db"), True


# ======================================================
# LECTURA DE DATOS BASE
# ======================================================

def _leer_categorias(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _tabla_existe(conn, "categorias_compra_config"):
        return []

    filas = _consultar(conn, "SELECT * FROM categorias_compra_config")
    categorias = []
    for fila in filas:
        activo = _valor(fila, "activo", "estado", default=1)
        if isinstance(activo, str) and activo.strip().upper() in {"INACTIVA", "ANULADA", "BAJA"}:
            continue
        if not _int_bool(activo) and str(activo).strip() not in {"", "None"}:
            continue
        categorias.append(fila)
    return categorias


def _leer_conceptos_fiscales(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _tabla_existe(conn, "conceptos_fiscales_compra_config"):
        return []

    filas = _consultar(conn, "SELECT * FROM conceptos_fiscales_compra_config")
    conceptos = []
    for fila in filas:
        activo = _valor(fila, "activo", "estado", default=1)
        if isinstance(activo, str) and activo.strip().upper() in {"INACTIVO", "INACTIVA", "ANULADO", "ANULADA", "BAJA"}:
            continue
        if not _int_bool(activo) and str(activo).strip() not in {"", "None"}:
            continue
        conceptos.append(fila)
    return conceptos


def _leer_cuentas_plan_empresa(conn: sqlite3.Connection, empresa_id: int) -> list[dict[str, Any]]:
    if not _tabla_existe(conn, "plan_cuentas_empresa"):
        return []

    try:
        filas = _consultar(conn, "SELECT * FROM plan_cuentas_empresa WHERE empresa_id = ?", (empresa_id,))
    except Exception:
        filas = _consultar(conn, "SELECT * FROM plan_cuentas_empresa")

    cuentas = []
    for fila in filas:
        estado = str(_valor(fila, "estado", default="ACTIVA") or "").strip().upper()
        if estado and estado not in {"ACTIVA", "ACTIVO"}:
            continue

        imputable = _valor(fila, "imputable", "es_imputable", default=1)
        if not _int_bool(imputable):
            continue

        cuentas.append(fila)
    return cuentas


# ======================================================
# CLASIFICACIÓN PROFESIONAL DE CATEGORÍAS
# ======================================================

def _clasificar_categoria(categoria: dict[str, Any]) -> dict[str, Any]:
    nombre = str(_valor(categoria, "categoria", "nombre", default=""))
    tipo = _normalizar_texto(_valor(categoria, "tipo_categoria", default=""))
    tratamiento = _normalizar_texto(_valor(categoria, "tratamiento_contable", "tratamiento", default=""))
    nombre_n = _normalizar_texto(nombre)

    afecta_inventario = _int_bool(_valor(categoria, "afecta_inventario", default=0))
    afecta_bienes_uso = _int_bool(_valor(categoria, "afecta_bienes_uso", default=0))
    afecta_resultado = _int_bool(_valor(categoria, "afecta_resultado", default=0))
    afecta_iva = _int_bool(_valor(categoria, "afecta_iva", default=1))

    # Corrección de raíz: Librería y útiles son gasto por defecto.
    # No deben confundirse con Muebles y útiles, que sí puede ser bien de uso.
    if nombre_n in {"LIBRERIA Y UTILES", "LIBRERIA UTILES"}:
        return {
            "tratamiento_clave": "GASTO_RESULTADO",
            "tratamiento_etiqueta": "Gasto del período / Resultado",
            "naturaleza": "RESULTADO",
            "afecta_inventario": 0,
            "afecta_bienes_uso": 0,
            "afecta_resultado": 1,
            "afecta_iva": afecta_iva,
            "es_bienes_de_cambio": 0,
            "parece_cmv": 0,
            "resultado_directo_bienes_cambio": 0,
        }

    if "IMPORTACION" in nombre_n and "SERVICIO" in nombre_n:
        return {
            "tratamiento_clave": "REQUIERE_REVISION",
            "tratamiento_etiqueta": "Requiere revisión profesional",
            "naturaleza": "MIXTA",
            "afecta_inventario": 0,
            "afecta_bienes_uso": 0,
            "afecta_resultado": 1,
            "afecta_iva": afecta_iva,
            "es_bienes_de_cambio": 0,
            "parece_cmv": 0,
            "resultado_directo_bienes_cambio": 0,
        }

    es_bien_uso_por_nombre = any(p in nombre_n for p in [
        "BIENES DE USO", "MUEBLES Y UTILES", "RODADOS", "MAQUINARIAS",
        "INSTALACIONES", "EQUIPOS DE COMPUTACION", "EQUIPOS INFORMATICOS",
    ])
    if "BIENES_USO" in tipo or "BIEN USO" in tratamiento or "BIENES USO" in tratamiento or afecta_bienes_uso or es_bien_uso_por_nombre:
        return {
            "tratamiento_clave": "BIENES_USO",
            "tratamiento_etiqueta": "Bienes de uso",
            "naturaleza": "ACTIVO_NO_CORRIENTE",
            "afecta_inventario": 0,
            "afecta_bienes_uso": 1,
            "afecta_resultado": 0,
            "afecta_iva": afecta_iva,
            "es_bienes_de_cambio": 0,
            "parece_cmv": 0,
            "resultado_directo_bienes_cambio": 0,
        }

    es_bienes_cambio = any(p in nombre_n for p in [
        "MERCADERIA", "MERCADERIAS", "MATERIA PRIMA", "MATERIAS PRIMAS",
        "INSUMOS PRODUCTIVOS", "IMPORTACION DE BIENES",
    ]) or "BIENES_CAMBIO" in tipo or "BIENES CAMBIO" in tratamiento or afecta_inventario

    parece_cmv = "COSTO" in nombre_n and ("MERCADERIA" in nombre_n or "VENDIDA" in nombre_n or "VENTA" in nombre_n)

    if es_bienes_cambio:
        return {
            "tratamiento_clave": "BIENES_CAMBIO",
            "tratamiento_etiqueta": "Bienes de cambio / Inventario",
            "naturaleza": "ACTIVO",
            "afecta_inventario": 1,
            "afecta_bienes_uso": 0,
            "afecta_resultado": 0 if not afecta_resultado else 1,
            "afecta_iva": afecta_iva,
            "es_bienes_de_cambio": 1,
            "parece_cmv": 1 if parece_cmv else 0,
            "resultado_directo_bienes_cambio": 1 if afecta_resultado else 0,
        }

    if any(p in nombre_n for p in ["NO GRAVADA", "NO GRAVADO", "EXENTA", "EXENTO"]) or "MAYOR COSTO" in tratamiento:
        return {
            "tratamiento_clave": "MAYOR_COSTO",
            "tratamiento_etiqueta": "Mayor costo / No recuperable",
            "naturaleza": "ACTIVO_O_RESULTADO_SEGUN_COMPRA",
            "afecta_inventario": 0,
            "afecta_bienes_uso": 0,
            "afecta_resultado": 1,
            "afecta_iva": afecta_iva,
            "es_bienes_de_cambio": 0,
            "parece_cmv": 0,
            "resultado_directo_bienes_cambio": 0,
        }

    if "REVISION" in tratamiento or "REVISAR" in nombre_n or "REGIMEN" in nombre_n or "USADOS" in nombre_n:
        return {
            "tratamiento_clave": "REQUIERE_REVISION",
            "tratamiento_etiqueta": "Requiere revisión profesional",
            "naturaleza": "MIXTA",
            "afecta_inventario": afecta_inventario,
            "afecta_bienes_uso": afecta_bienes_uso,
            "afecta_resultado": afecta_resultado or 1,
            "afecta_iva": afecta_iva,
            "es_bienes_de_cambio": 0,
            "parece_cmv": 0,
            "resultado_directo_bienes_cambio": 0,
        }

    return {
        "tratamiento_clave": "GASTO_RESULTADO",
        "tratamiento_etiqueta": "Gasto del período / Resultado",
        "naturaleza": "RESULTADO",
        "afecta_inventario": 0,
        "afecta_bienes_uso": 0,
        "afecta_resultado": 1,
        "afecta_iva": afecta_iva,
        "es_bienes_de_cambio": 0,
        "parece_cmv": 0,
        "resultado_directo_bienes_cambio": 0,
    }


# ======================================================
# CLASIFICACIÓN PROFESIONAL DE CONCEPTOS FISCALES
# ======================================================

def _clasificar_concepto_fiscal(concepto: dict[str, Any]) -> dict[str, Any]:
    nombre = str(_valor(concepto, "concepto", "nombre", default=""))
    tratamiento = _normalizar_texto(_valor(concepto, "tratamiento_fiscal", "tratamiento", default=""))
    nombre_n = _normalizar_texto(nombre)

    # Bases exentas / no gravadas no son una cuenta fiscal propia por defecto.
    # Siguen la naturaleza de la compra principal: gasto, bien de cambio o bien de uso.
    if nombre_n in {"EXENTO", "EXENTA", "NO GRAVADO", "NO GRAVADA", "NO_GRAVADO", "NO_GRAVADA"}:
        return {
            "concepto_clave": "BASE_EXENTA_NO_GRAVADA",
            "concepto_etiqueta": "Base exenta/no gravada: sigue categoría principal",
            "naturaleza": "INFORMATIVO_SIN_CUENTA_DIRECTA",
            "requiere_cuenta_directa": 0,
        }

    if "PERCEPCION" in nombre_n and "IVA" in nombre_n:
        return {
            "concepto_clave": "PERCEPCION_IVA",
            "concepto_etiqueta": "Percepción IVA sufrida",
            "naturaleza": "CREDITO_FISCAL_IVA",
            "requiere_cuenta_directa": 1,
        }

    if "RETENCION" in nombre_n and "IVA" in nombre_n:
        return {
            "concepto_clave": "RETENCION_IVA",
            "concepto_etiqueta": "Retención IVA sufrida",
            "naturaleza": "CREDITO_FISCAL_IVA",
            "requiere_cuenta_directa": 1,
        }

    if "PERCEPCION" in nombre_n and "IIBB" in nombre_n:
        return {
            "concepto_clave": "PERCEPCION_IIBB",
            "concepto_etiqueta": "Percepción IIBB sufrida",
            "naturaleza": "CREDITO_FISCAL_PROVINCIAL",
            "requiere_cuenta_directa": 1,
        }

    if "RETENCION" in nombre_n and "IIBB" in nombre_n:
        return {
            "concepto_clave": "RETENCION_IIBB",
            "concepto_etiqueta": "Retención IIBB sufrida",
            "naturaleza": "CREDITO_FISCAL_PROVINCIAL",
            "requiere_cuenta_directa": 1,
        }

    if "PERCEPCION" in nombre_n and "GANANCIA" in nombre_n:
        return {
            "concepto_clave": "PERCEPCION_GANANCIAS",
            "concepto_etiqueta": "Percepción Ganancias sufrida",
            "naturaleza": "CREDITO_FISCAL_NACIONAL",
            "requiere_cuenta_directa": 1,
        }

    if "RETENCION" in nombre_n and "GANANCIA" in nombre_n:
        return {
            "concepto_clave": "RETENCION_GANANCIAS",
            "concepto_etiqueta": "Retención Ganancias sufrida",
            "naturaleza": "CREDITO_FISCAL_NACIONAL",
            "requiere_cuenta_directa": 1,
        }

    if "PERCEPCION" in nombre_n and "MUNICIPAL" in nombre_n:
        return {
            "concepto_clave": "PERCEPCION_MUNICIPAL",
            "concepto_etiqueta": "Percepción municipal sufrida",
            "naturaleza": "CREDITO_FISCAL_MUNICIPAL",
            "requiere_cuenta_directa": 1,
        }

    if "PERCEPCION" in nombre_n and ("OTROS" in nombre_n or "NAC" in nombre_n):
        return {
            "concepto_clave": "PERCEPCION_OTROS_NACIONALES",
            "concepto_etiqueta": "Percepción otros impuestos nacionales",
            "naturaleza": "CREDITO_FISCAL_NACIONAL",
            "requiere_cuenta_directa": 1,
        }

    if "IVA" in nombre_n and ("NO COMPUTABLE" in nombre_n or "NO_COMPUTABLE" in nombre_n):
        return {
            "concepto_clave": "IVA_NO_COMPUTABLE",
            "concepto_etiqueta": "IVA no computable / mayor costo o gasto",
            "naturaleza": "MAYOR_COSTO_GASTO",
            "requiere_cuenta_directa": 1,
        }

    if "IVA" in nombre_n and ("CREDITO" in nombre_n or "CRÉDITO" in nombre_n or "CREDITO_FISCAL" in nombre_n):
        return {
            "concepto_clave": "IVA_CREDITO",
            "concepto_etiqueta": "IVA crédito fiscal computable",
            "naturaleza": "CREDITO_FISCAL_IVA",
            "requiere_cuenta_directa": 1,
        }

    if "IMPUESTOS INTERNOS" in nombre_n or "OTROS TRIBUTOS" in nombre_n:
        return {
            "concepto_clave": "TRIBUTOS_NO_RECUPERABLES",
            "concepto_etiqueta": "Tributos no recuperables / mayor costo o gasto",
            "naturaleza": "MAYOR_COSTO_GASTO",
            "requiere_cuenta_directa": 1,
        }

    if "PERCEPCION" in tratamiento or "RETENCION" in tratamiento:
        return {
            "concepto_clave": "CREDITO_FISCAL_A_REVISAR",
            "concepto_etiqueta": "Crédito fiscal a revisar",
            "naturaleza": "CREDITO_FISCAL_A_REVISAR",
            "requiere_cuenta_directa": 1,
        }

    return {
        "concepto_clave": "TRIBUTOS_NO_RECUPERABLES",
        "concepto_etiqueta": "Tributos no recuperables / mayor costo o gasto",
        "naturaleza": "MAYOR_COSTO_GASTO",
        "requiere_cuenta_directa": 1,
    }


# ======================================================
# SUGERENCIAS DE CUENTAS PLAN EMPRESA
# ======================================================

def _codigo(cuenta: dict[str, Any]) -> str:
    return str(_valor(cuenta, "codigo", "cuenta_codigo", default=""))


def _nombre_cuenta(cuenta: dict[str, Any]) -> str:
    return str(_valor(cuenta, "nombre", "cuenta_nombre", default=""))


def _uso(cuenta: dict[str, Any]) -> str:
    return str(_valor(cuenta, "uso_operativo_sistema", "uso_operativo", default=""))


def _cuenta_id(cuenta: dict[str, Any]) -> int | None:
    valor = _valor(cuenta, "id", "cuenta_empresa_id", default=None)
    try:
        return int(valor) if valor is not None else None
    except Exception:
        return None


def _cuenta_conflictiva(nombre_n: str, uso_n: str, tratamiento_clave: str) -> bool:
    conflictos_generales = [
        "AMORTIZACION ACUM", "DESVALORIZACION", "OBSOLETO", "ANTICIPO P VENTAS",
        "DEUDORES POR VENTAS", "IVA DEBITO", "A PAGAR", "RETENCIONES A DEPOSITAR",
    ]
    if any(p in nombre_n for p in conflictos_generales):
        return True

    if tratamiento_clave == "GASTO_RESULTADO":
        # No sugerir activos genéricos para gastos corrientes, salvo que la categoría
        # trate expresamente pagos adelantados. Esto evita falsos positivos.
        if any(p in nombre_n for p in [
            "GASTOS PAGADOS POR ADELANTADO", "GASTOS DE ORGANIZACION",
            "INVESTIGACION", "EXPLORACION",
        ]):
            return True

    if tratamiento_clave == "BIENES_CAMBIO" and any(p in nombre_n for p in ["COSTO DE", "GASTOS", "COMISIONES"]):
        return True

    if tratamiento_clave == "BIENES_USO" and any(p in nombre_n for p in ["STOCK", "INSUMO DE COMPUTACION"]):
        return True

    return False


def _score_categoria(categoria: str, clasificacion: dict[str, Any], cuenta: dict[str, Any]) -> int:
    nombre_cuenta = _nombre_cuenta(cuenta)
    uso = _uso(cuenta)
    codigo = _codigo(cuenta)
    categoria_n = _normalizar_texto(categoria)
    cuenta_n = _normalizar_texto(nombre_cuenta)
    uso_n = _normalizar_texto(uso)
    tratamiento = clasificacion["tratamiento_clave"]

    if _cuenta_conflictiva(cuenta_n, uso_n, tratamiento):
        return -999

    # Evitar falsos positivos por subcadenas: INMUEBLES contiene MUEBLES,
    # pero no corresponde sugerir Inmuebles para Muebles y útiles.
    if tratamiento == "BIENES_USO":
        if "MUEBLES" in categoria_n and "INMUEBLES" in cuenta_n:
            return -999
        if ("EQUIPOS" in categoria_n or "COMPUTACION" in categoria_n) and any(p in cuenta_n for p in ["MAQUINARIAS", "ALQUILER", "INMUEBLES"]):
            return -999
        if "RODADOS" in categoria_n and any(p in cuenta_n for p in ["INMUEBLES", "MAQUINARIAS"]):
            return -999

    score = 0

    if tratamiento == "BIENES_CAMBIO":
        if not codigo.startswith("1."):
            score -= 80
        if any(p in cuenta_n for p in ["MERCADERIA", "STOCK", "MATERIA PRIMA", "INSUMO"]):
            score += 80
        if "MERCADERIA" in categoria_n and "MERCADERIA" in cuenta_n:
            score += 80
        if "MATERIA" in categoria_n and "MATERIA" in cuenta_n:
            score += 80
        if "INSUMO" in categoria_n and "INSUMO" in cuenta_n:
            score += 80
        if uso_n in {"MERCADERIAS_REVENTA", "MATERIAS_PRIMAS"}:
            score += 70

    elif tratamiento == "BIENES_USO":
        if not codigo.startswith("1."):
            score -= 80
        if any(p in cuenta_n for p in ["RODADOS", "MAQUINARIAS", "INSTALACIONES", "MUEBLES", "EQUIPOS"]):
            score += 70
        for token in _tokenizar(categoria):
            if token in cuenta_n:
                score += 35
        if uso_n.startswith("BIENES_USO"):
            score += 70

    elif tratamiento == "GASTO_RESULTADO":
        if not codigo.startswith("6."):
            score -= 90
        if any(p in cuenta_n for p in ["GASTOS", "HONORARIOS", "ALQUILER", "PUBLICIDAD", "LIMPIEZA", "MANTENIMIENTO", "COMISIONES", "MOVILIDAD", "CARGAS SOCIALES"]):
            score += 45
        if categoria_n in cuenta_n or cuenta_n in categoria_n:
            score += 80
        for token in _tokenizar(categoria):
            if token in cuenta_n or token in uso_n:
                score += 30

        # Regla específica: Librería y útiles debe ir a papelería/útiles/gastos de oficina,
        # nunca a Muebles y Útiles como sugerencia principal.
        if categoria_n in {"LIBRERIA Y UTILES", "LIBRERIA UTILES"}:
            if any(p in cuenta_n for p in ["PAPEL", "UTILES", "ESCRITORIO", "LIBRERIA"]):
                score += 90
            if "MUEBLES" in cuenta_n:
                score -= 150

    elif tratamiento == "MAYOR_COSTO":
        if any(p in cuenta_n for p in ["IVA NO COMPUTABLE", "MAYOR COSTO", "IMPUESTOS", "TASAS"]):
            score += 70
        if codigo.startswith("6."):
            score += 30

    else:  # REQUIERE_REVISION
        return -999

    return score


def _sugerir_cuentas_categoria(
    categoria: str,
    clasificacion: dict[str, Any],
    cuentas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sugerencias = []
    for cuenta in cuentas:
        score = _score_categoria(categoria, clasificacion, cuenta)
        if score >= UMBRAL_SUGERENCIA_CATEGORIA:
            sugerencias.append({
                "cuenta_empresa_id": _cuenta_id(cuenta),
                "codigo": _codigo(cuenta),
                "nombre": _nombre_cuenta(cuenta),
                "uso_operativo_sistema": _uso(cuenta),
                "score": score,
                "calidad": "FUERTE",
            })

    sugerencias.sort(key=lambda x: (-int(x["score"]), str(x["codigo"]), str(x["nombre"])))
    return sugerencias[:MAX_SUGERENCIAS]


def _sugerir_cuentas_cmv_futura(cuentas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sugerencias = []
    for cuenta in cuentas:
        nombre_n = _normalizar_texto(_nombre_cuenta(cuenta))
        uso_n = _normalizar_texto(_uso(cuenta))
        codigo = _codigo(cuenta)
        score = 0
        if codigo.startswith("6."):
            score += 40
        if "COSTO" in nombre_n and ("MERCADERIA" in nombre_n or "VENTA" in nombre_n or "VENDIDA" in nombre_n):
            score += 90
        if uso_n == "CMV":
            score += 80
        if score >= UMBRAL_SUGERENCIA_CATEGORIA:
            sugerencias.append({
                "cuenta_empresa_id": _cuenta_id(cuenta),
                "codigo": codigo,
                "nombre": _nombre_cuenta(cuenta),
                "uso_operativo_sistema": _uso(cuenta),
                "score": score,
                "calidad": "FUERTE",
            })
    sugerencias.sort(key=lambda x: (-int(x["score"]), str(x["codigo"]), str(x["nombre"])))
    return sugerencias[:MAX_SUGERENCIAS]


def _score_concepto_fiscal(concepto_clave: str, concepto: str, cuenta: dict[str, Any]) -> int:
    nombre_n = _normalizar_texto(_nombre_cuenta(cuenta))
    uso_n = _normalizar_texto(_uso(cuenta))
    codigo = _codigo(cuenta)
    concepto_n = _normalizar_texto(concepto)

    if concepto_clave == "BASE_EXENTA_NO_GRAVADA":
        return -999

    score = 0

    esperado_por_clave = {
        "IVA_CREDITO": ["IVA_CREDITO_FISCAL"],
        "PERCEPCION_IVA": ["PERCEPCION_IVA"],
        "RETENCION_IVA": ["RETENCION_IVA_SUFRIDA"],
        "PERCEPCION_IIBB": ["PERCEPCION_IIBB"],
        "RETENCION_IIBB": ["RETENCION_IIBB_SUFRIDA"],
        "PERCEPCION_GANANCIAS": ["PERCEPCION_GANANCIAS"],
        "RETENCION_GANANCIAS": ["RETENCION_GANANCIAS_SUFRIDA"],
        "PERCEPCION_MUNICIPAL": ["PERCEPCION_MUNICIPAL"],
        "PERCEPCION_OTROS_NACIONALES": ["PERCEPCION_OTROS_NACIONALES"],
        "IVA_NO_COMPUTABLE": ["IVA_NO_COMPUTABLE_MAYOR_COSTO"],
    }

    if uso_n in esperado_por_clave.get(concepto_clave, []):
        score += 150

    # Compatibilidad por nombre visible de cuenta.
    reglas_nombre = {
        "IVA_CREDITO": ["IVA CREDITO"],
        "PERCEPCION_IVA": ["PERCEPCIONES IVA", "PERCEPCION IVA"],
        "RETENCION_IVA": ["RETENCIONES IVA", "RETENCION IVA"],
        "PERCEPCION_IIBB": ["PERCEPCIONES IIBB", "PERCEPCION IIBB"],
        "RETENCION_IIBB": ["RETENCIONES IIBB", "RETENCION IIBB"],
        "PERCEPCION_GANANCIAS": ["PERCEPCIONES GANANCIAS", "PERCEPCION GANANCIAS"],
        "RETENCION_GANANCIAS": ["RETENCIONES GANANCIAS", "RETENCION GANANCIAS"],
        "PERCEPCION_MUNICIPAL": ["PERCEPCIONES MUNICIPALES", "PERCEPCION MUNICIPAL"],
        "PERCEPCION_OTROS_NACIONALES": ["PERCEPCIONES OTROS IMPUESTOS", "OTROS IMPUESTOS NACIONALES"],
        "IVA_NO_COMPUTABLE": ["IVA NO COMPUTABLE", "MAYOR COSTO"],
        "TRIBUTOS_NO_RECUPERABLES": ["IMPUESTOS", "TASAS", "TRIBUTOS"],
    }
    if any(p in nombre_n for p in reglas_nombre.get(concepto_clave, [])):
        score += 90

    if concepto_n and concepto_n in nombre_n:
        score += 50

    if concepto_clave.startswith(("IVA", "PERCEPCION", "RETENCION")) and codigo.startswith("1."):
        score += 35
    if concepto_clave == "TRIBUTOS_NO_RECUPERABLES" and codigo.startswith("6."):
        score += 35

    # Evitar confundir percepciones/retenciones sufridas con pasivos a pagar o a depositar.
    if any(p in nombre_n for p in ["A PAGAR", "A DEPOSITAR", "IVA DEBITO"]):
        score -= 120

    return score


def _sugerir_cuentas_concepto(
    concepto: str,
    clasificacion: dict[str, Any],
    cuentas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sugerencias = []
    clave = clasificacion["concepto_clave"]
    for cuenta in cuentas:
        score = _score_concepto_fiscal(clave, concepto, cuenta)
        if score >= UMBRAL_SUGERENCIA_FISCAL:
            sugerencias.append({
                "cuenta_empresa_id": _cuenta_id(cuenta),
                "codigo": _codigo(cuenta),
                "nombre": _nombre_cuenta(cuenta),
                "uso_operativo_sistema": _uso(cuenta),
                "score": score,
                "calidad": "FUERTE",
            })
    sugerencias.sort(key=lambda x: (-int(x["score"]), str(x["codigo"]), str(x["nombre"])))
    return sugerencias[:MAX_SUGERENCIAS]


# ======================================================
# LEGACY / ALERTAS / SALIDA
# ======================================================

def _buscar_codigos_legacy(ruta_compras_service: str | None) -> list[dict[str, Any]]:
    if not ruta_compras_service:
        return []
    ruta = Path(ruta_compras_service)
    if not ruta.exists():
        return []

    patron = re.compile(r'"(\d{7,})"')
    codigos = []
    for nro, linea in enumerate(ruta.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        for match in patron.finditer(linea):
            codigos.append({"linea": nro, "codigo": match.group(1), "texto": linea.strip()})
    return codigos


def _acciones_categoria(tiene_sugerencia_fuerte: bool) -> list[str]:
    acciones = [
        "editar_parametrizacion",
        "desactivar_categoria",
        "agregar_categoria_propia",
        "vincular_cuenta_plan_empresa",
        "crear_copiar_cuenta_en_plan_empresa_si_falta",
    ]
    if tiene_sugerencia_fuerte:
        return ["aceptar_sugerencia"] + acciones
    return acciones


def _acciones_concepto(tiene_sugerencia_fuerte: bool) -> list[str]:
    acciones = [
        "editar_parametrizacion",
        "desactivar_concepto",
        "vincular_cuenta_plan_empresa",
        "crear_copiar_cuenta_en_plan_empresa_si_falta",
    ]
    if tiene_sugerencia_fuerte:
        return ["aceptar_sugerencia"] + acciones
    return acciones


def _estado_parametrizacion(cuenta_actual_id: Any, sugerencias: list[dict[str, Any]]) -> str:
    try:
        if cuenta_actual_id not in (None, "", 0, "0"):
            return "CUENTA_PLAN_EMPRESA_VINCULADA"
    except Exception:
        pass
    if sugerencias:
        return "SUGERENCIA_FUERTE_DISPONIBLE"
    return "REQUIERE_DECISION_SIN_SUGERENCIA_FUERTE"


def diagnosticar_parametrizacion_asistida_compras(
    *,
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
    ruta_compras_service: str | None = "services/compras_service.py",
) -> dict[str, Any]:
    """
    Genera una matriz de parametrización asistida para Compras.

    No modifica datos. No cambia row_factory. No acepta sugerencias.
    """
    conexion, cerrar = _abrir_conexion(conn)
    try:
        tablas = {
            "categorias_compra_config": _tabla_existe(conexion, "categorias_compra_config"),
            "conceptos_fiscales_compra_config": _tabla_existe(conexion, "conceptos_fiscales_compra_config"),
            "plan_cuentas_empresa": _tabla_existe(conexion, "plan_cuentas_empresa"),
        }

        categorias_base = _leer_categorias(conexion)
        conceptos_base = _leer_conceptos_fiscales(conexion)
        cuentas = _leer_cuentas_plan_empresa(conexion, empresa_id)
        codigos_legacy = _buscar_codigos_legacy(ruta_compras_service)

        categorias = []
        grupos_cat: dict[str, dict[str, Any]] = {}
        categorias_bienes_cambio = 0
        categorias_cmv_detectadas = 0
        bienes_cambio_resultado_directo = 0
        categorias_con_sugerencia = 0
        categorias_sin_sugerencia = 0
        categorias_sin_vinculo = 0

        for fila in categorias_base:
            categoria = str(_valor(fila, "categoria", "nombre", default="")).strip()
            clasificacion = _clasificar_categoria(fila)
            sugerencias = _sugerir_cuentas_categoria(categoria, clasificacion, cuentas)
            sugerencias_cmv = _sugerir_cuentas_cmv_futura(cuentas) if clasificacion["es_bienes_de_cambio"] else []
            cuenta_actual_id = _valor(fila, "cuenta_sugerida_id", "cuenta_plan_empresa_id", default=None)

            estado = _estado_parametrizacion(cuenta_actual_id, sugerencias)
            if estado != "CUENTA_PLAN_EMPRESA_VINCULADA":
                categorias_sin_vinculo += 1
            if sugerencias:
                categorias_con_sugerencia += 1
            else:
                categorias_sin_sugerencia += 1
            if clasificacion["es_bienes_de_cambio"]:
                categorias_bienes_cambio += 1
            if clasificacion["parece_cmv"]:
                categorias_cmv_detectadas += 1
            if clasificacion["resultado_directo_bienes_cambio"]:
                bienes_cambio_resultado_directo += 1

            clave_grupo = clasificacion["tratamiento_clave"]
            if clave_grupo not in grupos_cat:
                grupos_cat[clave_grupo] = {
                    "tratamiento_clave": clave_grupo,
                    "tratamiento_etiqueta": clasificacion["tratamiento_etiqueta"],
                    "cantidad": 0,
                    "categorias": [],
                    "requieren_decision_usuario": 0,
                }
            grupos_cat[clave_grupo]["cantidad"] += 1
            grupos_cat[clave_grupo]["categorias"].append(categoria)
            if estado != "CUENTA_PLAN_EMPRESA_VINCULADA":
                grupos_cat[clave_grupo]["requieren_decision_usuario"] += 1

            categorias.append({
                "categoria_id": _valor(fila, "id", "categoria_id", default=None),
                "categoria": categoria,
                "tipo_categoria": str(_valor(fila, "tipo_categoria", default="")),
                "tratamiento_contable_actual": str(_valor(fila, "tratamiento_contable", "tratamiento", default="")),
                **clasificacion,
                "cuenta_sugerida_id_actual": cuenta_actual_id,
                "cuenta_actual_codigo": "",
                "cuenta_actual_nombre": "",
                "sugerencias_cuenta_plan_empresa": sugerencias,
                "sugerencias_cuenta_cmv_futura": sugerencias_cmv,
                "estado_parametrizacion": estado,
                "acciones_disponibles": _acciones_categoria(bool(sugerencias)),
                "decision_usuario_requerida": 1 if estado != "CUENTA_PLAN_EMPRESA_VINCULADA" else 0,
            })

        conceptos = []
        grupos_conceptos: dict[str, dict[str, Any]] = {}
        conceptos_con_sugerencia = 0
        conceptos_sin_sugerencia = 0
        conceptos_sin_vinculo = 0
        conceptos_informativos_sin_cuenta_directa = 0

        for fila in conceptos_base:
            concepto = str(_valor(fila, "concepto", "nombre", default="")).strip()
            clasificacion = _clasificar_concepto_fiscal(fila)
            requiere_cuenta_directa = _int_bool(clasificacion.get("requiere_cuenta_directa", 1))
            sugerencias = _sugerir_cuentas_concepto(concepto, clasificacion, cuentas) if requiere_cuenta_directa else []
            cuenta_actual_id = _valor(fila, "cuenta_sugerida_id", "cuenta_plan_empresa_id", default=None)
            estado = _estado_parametrizacion(cuenta_actual_id, sugerencias) if requiere_cuenta_directa else "INFORMATIVO_SIN_CUENTA_DIRECTA"

            if not requiere_cuenta_directa:
                conceptos_informativos_sin_cuenta_directa += 1
            if requiere_cuenta_directa and estado != "CUENTA_PLAN_EMPRESA_VINCULADA":
                conceptos_sin_vinculo += 1
            if requiere_cuenta_directa and sugerencias:
                conceptos_con_sugerencia += 1
            elif requiere_cuenta_directa:
                conceptos_sin_sugerencia += 1

            clave = clasificacion["concepto_clave"]
            if clave not in grupos_conceptos:
                grupos_conceptos[clave] = {
                    "concepto_clave": clave,
                    "concepto_etiqueta": clasificacion["concepto_etiqueta"],
                    "cantidad": 0,
                    "conceptos": [],
                    "requieren_decision_usuario": 0,
                }
            grupos_conceptos[clave]["cantidad"] += 1
            grupos_conceptos[clave]["conceptos"].append(concepto)
            if requiere_cuenta_directa and estado != "CUENTA_PLAN_EMPRESA_VINCULADA":
                grupos_conceptos[clave]["requieren_decision_usuario"] += 1

            conceptos.append({
                "concepto_id": _valor(fila, "id", "concepto_id", default=None),
                "concepto": concepto,
                "tratamiento_fiscal_actual": str(_valor(fila, "tratamiento_fiscal", "tratamiento", default="")),
                **clasificacion,
                "afecta_iva": _int_bool(_valor(fila, "afecta_iva", default=0)),
                "afecta_iibb": _int_bool(_valor(fila, "afecta_iibb", default=0)),
                "afecta_ganancias": _int_bool(_valor(fila, "afecta_ganancias", default=0)),
                "computable": _int_bool(_valor(fila, "computable", default=0)),
                "mayor_costo": _int_bool(_valor(fila, "mayor_costo", default=0)),
                "informativo": _int_bool(_valor(fila, "informativo", default=0)),
                "cuenta_sugerida_id_actual": cuenta_actual_id,
                "cuenta_actual_codigo": "",
                "cuenta_actual_nombre": "",
                "sugerencias_cuenta_plan_empresa": sugerencias,
                "estado_parametrizacion": estado,
                "acciones_disponibles": _acciones_concepto(bool(sugerencias)) if requiere_cuenta_directa else ["editar_parametrizacion", "desactivar_concepto"],
                "decision_usuario_requerida": 1 if requiere_cuenta_directa and estado != "CUENTA_PLAN_EMPRESA_VINCULADA" else 0,
            })

        alertas = []
        if categorias_sin_vinculo:
            alertas.append({
                "severidad": "ADVERTENCIA",
                "area": "Compras / Parametrización",
                "codigo": "CATEGORIAS_REQUIEREN_DECISION_USUARIO",
                "mensaje": f"Hay {categorias_sin_vinculo} categorías activas sin cuenta del Plan Empresa aceptada.",
                "recomendacion": "Revisar sugerencias fuertes, editar, desactivar o agregar categorías propias según la empresa.",
                "detalle": {"con_sugerencia_fuerte": categorias_con_sugerencia, "sin_sugerencia_fuerte": categorias_sin_sugerencia},
            })
        if conceptos_sin_vinculo:
            alertas.append({
                "severidad": "ADVERTENCIA",
                "area": "Compras / Fiscal",
                "codigo": "CONCEPTOS_FISCALES_REQUIEREN_DECISION_USUARIO",
                "mensaje": f"Hay {conceptos_sin_vinculo} conceptos fiscales sin cuenta del Plan Empresa aceptada.",
                "recomendacion": "Vincular créditos fiscales, percepciones, retenciones y tributos recuperables/no recuperables contra cuentas activas del Plan Empresa.",
                "detalle": {"con_sugerencia_fuerte": conceptos_con_sugerencia, "sin_sugerencia_fuerte": conceptos_sin_sugerencia},
            })
        if conceptos_informativos_sin_cuenta_directa:
            alertas.append({
                "severidad": "INFORMATIVO",
                "area": "Compras / Fiscal",
                "codigo": "BASES_EXENTAS_NO_GRAVADAS_SIN_CUENTA_DIRECTA",
                "mensaje": f"Hay {conceptos_informativos_sin_cuenta_directa} conceptos informativos que no requieren cuenta propia.",
                "recomendacion": "EXENTO y NO_GRAVADO siguen la cuenta de la compra principal; no aceptar una cuenta fiscal independiente por defecto.",
                "detalle": {},
            })
        if bienes_cambio_resultado_directo:
            alertas.append({
                "severidad": "ADVERTENCIA",
                "area": "Compras / Bienes de cambio y CMV",
                "codigo": "BIENES_CAMBIO_CON_RESULTADO_DIRECTO",
                "mensaje": f"Hay {bienes_cambio_resultado_directo} categorías de bienes de cambio marcadas también como resultado directo.",
                "recomendacion": "La compra de mercadería debería ir primero a bienes de cambio; el CMV se reconoce al vender o al cierre de inventario.",
                "detalle": {},
            })
        if categorias_bienes_cambio and not categorias_cmv_detectadas:
            alertas.append({
                "severidad": "INFORMATIVO",
                "area": "Compras / CMV futuro",
                "codigo": "CMV_FUTURO_REQUIERE_POLITICA",
                "mensaje": "Hay categorías de bienes de cambio y no hay categoría CMV detectada.",
                "recomendacion": "Definir en una etapa posterior si el CMV se calculará por inventario permanente, inventario periódico o ajuste manual de cierre.",
                "detalle": {"categorias_bienes_cambio": categorias_bienes_cambio},
            })
        if codigos_legacy:
            alertas.append({
                "severidad": "ADVERTENCIA",
                "area": "Compras / Código",
                "codigo": "COMPRAS_SERVICE_MANTIENE_CODIGOS_LEGACY",
                "mensaje": f"Se detectaron {len(codigos_legacy)} códigos contables hardcodeados en services/compras_service.py.",
                "recomendacion": "No generar asientos profesionales desde Compras hasta reemplazar esos defaults por parametrización contra Plan Empresa.",
                "detalle": {"muestras": codigos_legacy[:5]},
            })

        resumen = {
            "cuentas_plan_empresa_imputables_activas": len(cuentas),
            "categorias_activas": len(categorias_base),
            "categorias_sin_vinculo_plan_empresa": categorias_sin_vinculo,
            "categorias_con_sugerencia_fuerte": categorias_con_sugerencia,
            "categorias_sin_sugerencia_fuerte": categorias_sin_sugerencia,
            "categorias_bienes_de_cambio": categorias_bienes_cambio,
            "categorias_cmv_detectadas": categorias_cmv_detectadas,
            "bienes_cambio_resultado_directo": bienes_cambio_resultado_directo,
            "conceptos_fiscales_activos": len(conceptos_base),
            "conceptos_fiscales_sin_vinculo_plan_empresa": conceptos_sin_vinculo,
            "conceptos_fiscales_con_sugerencia_fuerte": conceptos_con_sugerencia,
            "conceptos_fiscales_sin_sugerencia_fuerte": conceptos_sin_sugerencia,
            "conceptos_informativos_sin_cuenta_directa": conceptos_informativos_sin_cuenta_directa,
            "codigos_legacy_en_compras_service": len(codigos_legacy),
            "alertas_agrupadas": len(alertas),
        }

        estado_general = "OK" if not categorias_sin_vinculo and not conceptos_sin_vinculo and not codigos_legacy else "REQUIERE_PARAMETRIZACION"

        return {
            "ok": True,
            "empresa_id": empresa_id,
            "estado_general": estado_general,
            "modo": "LECTURA_SIN_CAMBIOS",
            "regla_central": "Plan Maestro FF es fuente madre; Plan Empresa es parametrizable por empresa/usuario; Compras debe usar cuentas activas del Plan Empresa.",
            "tablas": tablas,
            "resumen": resumen,
            "alertas": alertas,
            "grupos_tratamiento_categorias": list(grupos_cat.values()),
            "grupos_conceptos_fiscales": list(grupos_conceptos.values()),
            "categorias": categorias,
            "conceptos_fiscales": conceptos,
            "codigos_legacy": codigos_legacy,
            "acciones_futuras": {
                "v2b": "Aceptar, editar, desactivar o agregar categorías/conceptos con auditoría y reversibilidad.",
                "v3": "Usar parametrización aceptada para imputar compras contra Plan Empresa.",
                "cmv": "Definir política de CMV futura sin registrar CMV al momento de comprar mercadería.",
            },
        }

    finally:
        if cerrar:
            conexion.close()