from __future__ import annotations

import importlib
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ESTADO_OK = "OK"
ESTADO_REQUIERE_REVISION = "REQUIERE_REVISION"
ESTADO_REQUIERE_PARAMETRIZACION = "REQUIERE_PARAMETRIZACION"
ESTADO_CRITICO = "CRITICO"

SEVERIDAD_INFO = "INFO"
SEVERIDAD_ADVERTENCIA = "ADVERTENCIA"
SEVERIDAD_CRITICA = "CRITICA"

CASOS_REQUERIDOS = [
    "PAGO_FACTURA_TOTAL",
    "PAGO_FACTURA_PARCIAL",
    "PAGO_MULTIPLES_FACTURAS",
    "ANTICIPO_A_PROVEEDOR",
    "APLICACION_ANTICIPO_A_FACTURA",
    "RETENCION_IIBB",
    "RETENCION_GANANCIAS",
    "RETENCION_IVA",
    "RETENCION_SUSS",
    "DIFERENCIA_PAGO",
    "ORDEN_DE_PAGO",
    "PAGO_CAJA",
    "PAGO_BANCO_TESORERIA",
    "ANULACION_PAGO",
    "PROPUESTA_ASIENTO_FUTURA",
]

TABLAS_RELEVANTES = [
    "pagos",
    "pagos_imputaciones",
    "pagos_retenciones",
    "pagos_auditoria",
    "cuenta_corriente_proveedores",
    "compras_comprobantes",
    "tesoreria_operaciones",
    "tesoreria_operaciones_componentes",
    "caja_movimientos",
    "libro_diario",
    "asientos_propuestos",
]

COLUMNAS_ESPERADAS = {
    "pagos": [
        "id",
        "empresa_id",
        "fecha_pago",
        "numero_orden_pago",
        "proveedor",
        "cuit",
        "importe_pagado",
        "importe_retenciones",
        "importe_total_aplicado",
        "medio_pago",
        "cuenta_tesoreria_id",
        "tesoreria_operacion_id",
        "asiento_id",
        "estado",
        "motivo_anulacion",
    ],
    "pagos_imputaciones": [
        "id",
        "pago_id",
        "cuenta_corriente_id",
        "tipo",
        "numero",
        "importe_imputado",
    ],
    "pagos_retenciones": [
        "id",
        "pago_id",
        "tipo_retencion",
        "descripcion",
        "importe",
        "cuenta_contable_nombre",
    ],
    "cuenta_corriente_proveedores": [
        "id",
        "empresa_id",
        "proveedor",
        "cuit",
        "tipo",
        "numero",
        "debe",
        "haber",
        "saldo",
        "origen",
        "origen_id",
    ],
    "tesoreria_operaciones": [
        "id",
        "empresa_id",
        "fecha",
        "tipo_operacion",
        "tercero_tipo",
        "tercero_nombre",
        "importe",
        "estado",
        "origen",
        "origen_id",
    ],
    "libro_diario": [
        "id",
        "empresa_id",
        "fecha",
        "cuenta",
        "debe",
        "haber",
        "descripcion",
        "origen",
        "origen_id",
    ],
}

PATRONES_CODIGO = {
    "inserta_pagos": r"INSERT\s+INTO\s+pagos\b",
    "actualiza_pagos": r"UPDATE\s+pagos\b",
    "inserta_pagos_imputaciones": r"INSERT\s+INTO\s+pagos_imputaciones\b",
    "inserta_pagos_retenciones": r"INSERT\s+INTO\s+pagos_retenciones\b",
    "inserta_pagos_auditoria": r"INSERT\s+INTO\s+pagos_auditoria\b",
    "inserta_cuenta_corriente_proveedores": r"INSERT\s+INTO\s+cuenta_corriente_proveedores\b",
    "inserta_tesoreria_operaciones": r"INSERT\s+INTO\s+tesoreria_operaciones\b",
    "inserta_componentes_tesoreria": r"INSERT\s+INTO\s+tesoreria_operaciones_componentes\b",
    "inserta_libro_diario": r"INSERT\s+INTO\s+libro_diario\b",
    "usa_asientos_propuestos": r"\basientos_propuestos\b|\bbandeja\b|propuesta_asiento",
    "usa_cajas_service": r"\bcajas_service\b",
    "usa_tesoreria_service": r"\btesoreria_service\b",
    "hardcode_cuenta_proveedores": r"CUENTA_PROVEEDORES\s*=\s*[\"']PROVEEDORES[\"']",
    "hardcode_retenciones_default": r"CUENTAS_RETENCIONES_DEFAULT|RETENCIONES\s+IIBB\s+A\s+DEPOSITAR|RETENCIONES\s+GANANCIAS\s+A\s+DEPOSITAR|RETENCIONES\s+IVA\s+A\s+DEPOSITAR",
    "menciona_anticipo": r"\banticipo\b|\banticipos\b",
    "menciona_diferencia": r"\bdiferencia\b|\bajuste\b",
    "menciona_anulacion": r"\banulaci[oó]n\b|\banular\b|\breverso\b",
    "menciona_orden_pago": r"orden[_\s-]?de[_\s-]?pago|numero_orden_pago|OP-",
    "ui_crea_caja_banco": r"Crear\s+Caja\s+principal|Crear\s+Banco\s+principal|Caja\s+principal|Banco\s+principal",
    "ui_muestra_asiento": r"Asiento:\s*\*\*|asiento_id|Asiento reverso",
}


def diagnosticar_pagos(empresa_id: int = 1, conn: Optional[sqlite3.Connection] = None, base_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """
    Diagnóstico contable-operativo de Pagos PRO v1.

    Es deliberadamente de solo lectura:
    - no crea tablas;
    - no inserta;
    - no actualiza;
    - no borra;
    - no invoca la lógica operativa de pagos.

    Puede trabajar con una conexión SQLite explícita o, si no se pasa conexión,
    intenta usar una conexión de la aplicación de forma tolerante.
    """

    conexion_propia = False
    if conn is None and base_path is None:
        conn = _obtener_conexion_por_defecto()
        conexion_propia = conn is not None

    try:
        base = Path(base_path) if base_path is not None else Path.cwd()
        codigo = _diagnosticar_codigo(base)
        estructura = _diagnosticar_estructura(conn) if conn is not None else _estructura_sin_conexion()
        datos = _diagnosticar_datos(conn, empresa_id) if conn is not None else _datos_sin_conexion()

        casos = _diagnosticar_casos(estructura, codigo)
        impactos = _diagnosticar_impactos(estructura, codigo)
        alertas = _diagnosticar_alertas(estructura, codigo, casos)
        recomendaciones = _recomendaciones(alertas, casos)

        conteo_casos = _contar_casos(casos)
        estado = _determinar_estado(alertas, conteo_casos)

        return {
            "modulo": "Pagos PRO v1",
            "tipo": "diagnostico_contable_operativo",
            "empresa_id": empresa_id,
            "estado": estado,
            "resumen": {
                "casos_requeridos": len(CASOS_REQUERIDOS),
                "casos_soportados_base": conteo_casos["SOPORTADO_BASE"],
                "casos_a_revisar": conteo_casos["A_REVISAR"],
                "casos_incompletos": conteo_casos["INCOMPLETO"],
                "alertas_criticas": sum(1 for alerta in alertas if alerta["severidad"] == SEVERIDAD_CRITICA),
                "alertas_advertencia": sum(1 for alerta in alertas if alerta["severidad"] == SEVERIDAD_ADVERTENCIA),
                "alertas_info": sum(1 for alerta in alertas if alerta["severidad"] == SEVERIDAD_INFO),
            },
            "casos": casos,
            "impactos_directos": impactos,
            "estructura": estructura,
            "datos": datos,
            "codigo": codigo,
            "alertas": alertas,
            "recomendaciones": recomendaciones,
            "proxima_etapa_sugerida": "Pagos PRO v2A - Parametrizacion asistida de pagos" if estado != ESTADO_CRITICO else "Corregir bases criticas antes de parametrizar Pagos",
            "no_tocar_en_v1": [
                "services/pagos_service.py",
                "modulos/pagos.py",
                "migrations/",
                "Caja",
                "Banco/Caja",
                "Compras",
                "Libro Diario",
                "Bandeja de asientos",
            ],
        }
    finally:
        if conexion_propia and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def diagnosticar_pagos_proveedores(empresa_id: int = 1, conn: Optional[sqlite3.Connection] = None, base_path: Optional[Path | str] = None) -> Dict[str, Any]:
    return diagnosticar_pagos(empresa_id=empresa_id, conn=conn, base_path=base_path)


def _obtener_conexion_por_defecto() -> Optional[sqlite3.Connection]:
    candidatos = [
        ("core.database", ["get_connection", "obtener_conexion", "conectar"]),
        ("core.db", ["get_connection", "obtener_conexion", "conectar"]),
        ("database", ["get_connection", "obtener_conexion", "conectar"]),
    ]
    for modulo_nombre, funciones in candidatos:
        try:
            modulo = importlib.import_module(modulo_nombre)
        except Exception:
            continue

        for funcion_nombre in funciones:
            funcion = getattr(modulo, funcion_nombre, None)
            if callable(funcion):
                try:
                    conexion = funcion()
                    if isinstance(conexion, sqlite3.Connection):
                        return conexion
                except Exception:
                    continue

    return None


def _diagnosticar_codigo(base_path: Path) -> Dict[str, Any]:
    archivos = [
        base_path / "services" / "pagos_service.py",
        base_path / "modulos" / "pagos.py",
    ]

    textos = {}
    archivos_leidos = []
    archivos_faltantes = []

    for archivo in archivos:
        if archivo.exists():
            try:
                texto = archivo.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                texto = ""
            textos[str(archivo.relative_to(base_path))] = texto
            archivos_leidos.append(str(archivo.relative_to(base_path)))
        else:
            archivos_faltantes.append(str(archivo.relative_to(base_path)))

    indicadores = {}
    ocurrencias = {}

    for nombre_patron, patron in PATRONES_CODIGO.items():
        regex = re.compile(patron, re.IGNORECASE | re.MULTILINE)
        matches = []
        for nombre_archivo, texto in textos.items():
            for numero_linea, linea in enumerate(texto.splitlines(), start=1):
                if regex.search(linea):
                    matches.append({
                        "archivo": nombre_archivo,
                        "linea": numero_linea,
                        "texto": linea.strip()[:220],
                    })
        indicadores[nombre_patron] = bool(matches)
        ocurrencias[nombre_patron] = matches[:20]

    return {
        "archivos_leidos": archivos_leidos,
        "archivos_faltantes": archivos_faltantes,
        "indicadores": indicadores,
        "ocurrencias": ocurrencias,
    }


def _diagnosticar_estructura(conn: sqlite3.Connection) -> Dict[str, Any]:
    tablas_existentes = _listar_tablas(conn)
    tablas = {}

    for tabla in TABLAS_RELEVANTES:
        existe = tabla in tablas_existentes
        columnas = _columnas_tabla(conn, tabla) if existe else []
        esperadas = COLUMNAS_ESPERADAS.get(tabla, [])
        faltantes = [col for col in esperadas if col not in columnas]

        tablas[tabla] = {
            "existe": existe,
            "columnas": columnas,
            "columnas_esperadas": esperadas,
            "columnas_faltantes": faltantes,
        }

    return {
        "conexion_disponible": True,
        "tablas_detectadas": sorted(tablas_existentes),
        "tablas_relevantes": tablas,
        "tablas_faltantes": [tabla for tabla in TABLAS_RELEVANTES if tabla not in tablas_existentes],
    }


def _diagnosticar_datos(conn: sqlite3.Connection, empresa_id: int) -> Dict[str, Any]:
    datos = {}
    for tabla in TABLAS_RELEVANTES:
        if not _tabla_existe(conn, tabla):
            datos[tabla] = {"existe": False, "filas": None, "filas_empresa": None}
            continue

        columnas = _columnas_tabla(conn, tabla)
        filas = _contar_filas(conn, tabla)
        filas_empresa = _contar_filas_empresa(conn, tabla, empresa_id) if "empresa_id" in columnas else None
        datos[tabla] = {
            "existe": True,
            "filas": filas,
            "filas_empresa": filas_empresa,
        }

    return datos


def _estructura_sin_conexion() -> Dict[str, Any]:
    return {
        "conexion_disponible": False,
        "tablas_detectadas": [],
        "tablas_relevantes": {
            tabla: {
                "existe": None,
                "columnas": [],
                "columnas_esperadas": COLUMNAS_ESPERADAS.get(tabla, []),
                "columnas_faltantes": COLUMNAS_ESPERADAS.get(tabla, []),
            }
            for tabla in TABLAS_RELEVANTES
        },
        "tablas_faltantes": TABLAS_RELEVANTES[:],
    }


def _datos_sin_conexion() -> Dict[str, Any]:
    return {
        tabla: {"existe": None, "filas": None, "filas_empresa": None}
        for tabla in TABLAS_RELEVANTES
    }


def _diagnosticar_casos(estructura: Dict[str, Any], codigo: Dict[str, Any]) -> List[Dict[str, Any]]:
    ind = codigo["indicadores"]
    tablas = estructura["tablas_relevantes"]

    tiene_pagos = _existe_tabla(tablas, "pagos") or ind["inserta_pagos"]
    tiene_imputaciones = _existe_tabla(tablas, "pagos_imputaciones") or ind["inserta_pagos_imputaciones"]
    tiene_retenciones = _existe_tabla(tablas, "pagos_retenciones") or ind["inserta_pagos_retenciones"]
    tiene_cc = _existe_tabla(tablas, "cuenta_corriente_proveedores") or ind["inserta_cuenta_corriente_proveedores"]
    tiene_tesoreria = _existe_tabla(tablas, "tesoreria_operaciones") or ind["inserta_tesoreria_operaciones"]
    tiene_libro = _existe_tabla(tablas, "libro_diario") or ind["inserta_libro_diario"]

    casos = [
        _caso(
            "PAGO_FACTURA_TOTAL",
            "Pago total de una factura de proveedor",
            "SOPORTADO_BASE" if tiene_pagos and tiene_imputaciones and tiene_cc else "INCOMPLETO",
            "Se requiere pagos + imputaciones + cuenta corriente proveedores.",
        ),
        _caso(
            "PAGO_FACTURA_PARCIAL",
            "Pago parcial de factura de proveedor",
            "SOPORTADO_BASE" if tiene_pagos and tiene_imputaciones and tiene_cc else "INCOMPLETO",
            "La imputacion por importe permite pago parcial si el flujo lo valida.",
        ),
        _caso(
            "PAGO_MULTIPLES_FACTURAS",
            "Pago aplicado a multiples comprobantes del mismo proveedor",
            "SOPORTADO_BASE" if tiene_pagos and tiene_imputaciones else "INCOMPLETO",
            "La existencia de pagos_imputaciones permite multiples lineas por pago.",
        ),
        _caso(
            "ANTICIPO_A_PROVEEDOR",
            "Pago sin factura, como anticipo a proveedor",
            "A_REVISAR" if ind["menciona_anticipo"] else "INCOMPLETO",
            "Debe distinguir anticipo de gasto y de cancelacion de factura.",
        ),
        _caso(
            "APLICACION_ANTICIPO_A_FACTURA",
            "Aplicacion posterior de anticipo contra factura",
            "A_REVISAR" if ind["menciona_anticipo"] and tiene_imputaciones else "INCOMPLETO",
            "Requiere trazabilidad entre anticipo y factura aplicada.",
        ),
        _caso(
            "RETENCION_IIBB",
            "Retencion IIBB practicada en pago",
            "SOPORTADO_BASE" if tiene_retenciones else "INCOMPLETO",
            "Debe parametrizar cuenta contable y jurisdiccion en etapas futuras.",
        ),
        _caso(
            "RETENCION_GANANCIAS",
            "Retencion Ganancias practicada en pago",
            "SOPORTADO_BASE" if tiene_retenciones else "INCOMPLETO",
            "Debe parametrizar regimen y cuenta contable en etapas futuras.",
        ),
        _caso(
            "RETENCION_IVA",
            "Retencion IVA practicada en pago",
            "SOPORTADO_BASE" if tiene_retenciones else "INCOMPLETO",
            "Debe parametrizar regimen y cuenta contable en etapas futuras.",
        ),
        _caso(
            "RETENCION_SUSS",
            "Retencion SUSS practicada en pago",
            "SOPORTADO_BASE" if tiene_retenciones else "INCOMPLETO",
            "Debe parametrizar regimen y cuenta contable en etapas futuras.",
        ),
        _caso(
            "DIFERENCIA_PAGO",
            "Diferencias de pago, redondeos o ajustes",
            "A_REVISAR" if ind["menciona_diferencia"] else "INCOMPLETO",
            "No debe mezclarse con retenciones ni anticipos.",
        ),
        _caso(
            "ORDEN_DE_PAGO",
            "Orden de pago emitida y consultable",
            "SOPORTADO_BASE" if ind["menciona_orden_pago"] or _tabla_tiene_columna(tablas, "pagos", "numero_orden_pago") else "INCOMPLETO",
            "Debe conservarse incluso si el pago se anula.",
        ),
        _caso(
            "PAGO_CAJA",
            "Pago en efectivo con impacto en Caja",
            "SOPORTADO_BASE" if ind["usa_cajas_service"] else "A_REVISAR",
            "Debe mantener la regla: solo EFECTIVO impacta Caja.",
        ),
        _caso(
            "PAGO_BANCO_TESORERIA",
            "Pago por banco, billetera, tarjeta, cheque o eCheq",
            "SOPORTADO_BASE" if tiene_tesoreria else "INCOMPLETO",
            "Debe quedar conciliable o controlable en Tesoreria/Banco.",
        ),
        _caso(
            "ANULACION_PAGO",
            "Anulacion logica con reverso operativo/contable",
            "SOPORTADO_BASE" if ind["menciona_anulacion"] and tiene_pagos else "INCOMPLETO",
            "Debe bloquear o advertir si ya esta conciliado/contabilizado.",
        ),
        _caso(
            "PROPUESTA_ASIENTO_FUTURA",
            "Preparacion para futura Bandeja de asientos",
            "A_REVISAR" if tiene_libro and not ind["usa_asientos_propuestos"] else ("SOPORTADO_BASE" if ind["usa_asientos_propuestos"] else "INCOMPLETO"),
            "El objetivo futuro deberia ser propuesta revisable antes del Libro Diario.",
        ),
    ]

    return casos


def _diagnosticar_impactos(estructura: Dict[str, Any], codigo: Dict[str, Any]) -> List[Dict[str, Any]]:
    ind = codigo["indicadores"]
    tablas = estructura["tablas_relevantes"]

    impactos = []

    def agregar(area: str, estado: str, detalle: str) -> None:
        impactos.append({"area": area, "estado": estado, "detalle": detalle})

    agregar("Proveedores", "DIRECTO", "Pagos opera por proveedor/CUIT y saldos pendientes.")
    agregar("Cuenta corriente proveedores", "DIRECTO" if _existe_tabla(tablas, "cuenta_corriente_proveedores") or ind["inserta_cuenta_corriente_proveedores"] else "A_REVISAR", "Cancela o revierte saldos mediante cuenta corriente de proveedores.")
    agregar("Facturas pendientes", "DIRECTO" if ind["inserta_pagos_imputaciones"] or _existe_tabla(tablas, "pagos_imputaciones") else "A_REVISAR", "Imputa pagos contra comprobantes pendientes.")
    agregar("Retenciones practicadas", "DIRECTO" if ind["inserta_pagos_retenciones"] or _existe_tabla(tablas, "pagos_retenciones") else "INCOMPLETO", "Registra retenciones practicadas al proveedor.")
    agregar("Tesoreria/Banco", "DIRECTO" if ind["inserta_tesoreria_operaciones"] or _existe_tabla(tablas, "tesoreria_operaciones") else "A_REVISAR", "Registra operacion de salida o control bancario/tesoreria.")
    agregar("Caja", "DIRECTO" if ind["usa_cajas_service"] else "A_REVISAR", "Solo deberia impactar Caja cuando el medio de pago es efectivo.")
    agregar("Libro Diario", "DIRECTO" if ind["inserta_libro_diario"] else "A_REVISAR", "Actualmente puede generar asiento definitivo desde el flujo de pago.")
    agregar("Bandeja de asientos", "INCOMPLETO" if not ind["usa_asientos_propuestos"] else "DIRECTO", "No debe saltearse Bandeja en la arquitectura PRO futura.")
    agregar("Auditoria y anulaciones", "DIRECTO" if ind["inserta_pagos_auditoria"] or ind["menciona_anulacion"] else "A_REVISAR", "Debe conservar trazabilidad y reversos, no borrar fisicamente.")
    agregar("Anticipos a proveedores", "INCOMPLETO" if not ind["menciona_anticipo"] else "A_REVISAR", "Debe existir como naturaleza separada de factura/gasto.")

    return impactos


def _diagnosticar_alertas(estructura: Dict[str, Any], codigo: Dict[str, Any], casos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ind = codigo["indicadores"]
    tablas = estructura["tablas_relevantes"]

    alertas = []

    if estructura["conexion_disponible"] is False:
        alertas.append(_alerta(
            "PAGOS_DIAGNOSTICO_SIN_CONEXION_DB",
            SEVERIDAD_ADVERTENCIA,
            "No se recibio conexion a la base de datos.",
            "El diagnostico se limita a inspeccion estatica del codigo.",
        ))

    if not _existe_tabla(tablas, "pagos") and not ind["inserta_pagos"]:
        alertas.append(_alerta(
            "PAGOS_TABLA_PRINCIPAL_NO_DETECTADA",
            SEVERIDAD_CRITICA,
            "No se detecta tabla principal de pagos.",
            "Sin tabla pagos no se puede auditar ni parametrizar el modulo.",
        ))

    if ind["inserta_libro_diario"]:
        alertas.append(_alerta(
            "PAGOS_GENERA_LIBRO_DIARIO_DIRECTO",
            SEVERIDAD_ADVERTENCIA,
            "El flujo actual inserta directamente en Libro Diario.",
            "Para la arquitectura PRO futura conviene pasar por Bandeja de asientos antes del asiento definitivo.",
        ))

    if ind["hardcode_cuenta_proveedores"] or ind["hardcode_retenciones_default"]:
        alertas.append(_alerta(
            "PAGOS_CUENTAS_CONTABLES_HARDCODEADAS",
            SEVERIDAD_ADVERTENCIA,
            "Se detectan cuentas contables hardcodeadas para proveedores o retenciones.",
            "Debe migrarse a parametrizacion por empresa vinculada al Plan de Cuentas Empresa / Plan Maestro FF.",
        ))

    if ind["ui_crea_caja_banco"]:
        alertas.append(_alerta(
            "PAGOS_UI_CREA_CUENTAS_TESORERIA_BASICAS",
            SEVERIDAD_ADVERTENCIA,
            "La UI contiene creacion rapida de Caja/Banco principal.",
            "Conviene revisar que no genere cuentas contables genericas fuera del Plan Empresa.",
        ))

    if not ind["menciona_anticipo"]:
        alertas.append(_alerta(
            "PAGOS_ANTICIPOS_PROVEEDORES_NO_DETECTADOS",
            SEVERIDAD_ADVERTENCIA,
            "No se detecta tratamiento explicito de anticipos a proveedores.",
            "Debe separarse de pagos aplicados a facturas para evitar imputarlo como gasto o cancelar deuda inexistente.",
        ))

    if not ind["usa_asientos_propuestos"]:
        alertas.append(_alerta(
            "PAGOS_SIN_BANDEJA_ASIENTOS",
            SEVERIDAD_ADVERTENCIA,
            "No se detecta integracion con asientos propuestos o Bandeja.",
            "La futura etapa deberia preparar propuestas contables revisables, no asientos definitivos directos.",
        ))

    if ind["inserta_pagos_retenciones"] and ind["hardcode_retenciones_default"]:
        alertas.append(_alerta(
            "PAGOS_RETENCIONES_NO_PARAMETRIZADAS",
            SEVERIDAD_ADVERTENCIA,
            "Las retenciones existen pero sus cuentas por defecto parecen fijas.",
            "Debe parametrizarse por impuesto, regimen, jurisdiccion y empresa.",
        ))

    if _cantidad_incompletos(casos) > 0:
        alertas.append(_alerta(
            "PAGOS_CASOS_OPERATIVOS_INCOMPLETOS",
            SEVERIDAD_INFO,
            "Hay casos operativos requeridos que no aparecen completamente soportados.",
            "Usar el detalle de casos para priorizar v2A/v2B.",
        ))

    return alertas


def _recomendaciones(alertas: List[Dict[str, Any]], casos: List[Dict[str, Any]]) -> List[str]:
    recomendaciones = [
        "Mantener Pagos PRO v1 como diagnostico aislado de solo lectura.",
        "No tocar services/pagos_service.py ni modulos/pagos.py hasta cerrar la matriz de riesgos.",
        "Separar conceptualmente pago aplicado a factura, anticipo a proveedor, retenciones practicadas y diferencia de pago.",
        "Diseniar la futura parametrizacion contra Plan de Cuentas Empresa, usando Plan Maestro FF solo como fuente madre.",
        "Preparar futura integracion con Bandeja de asientos para evitar asientos definitivos directos desde Pagos.",
    ]

    if any(alerta["codigo"] == "PAGOS_GENERA_LIBRO_DIARIO_DIRECTO" for alerta in alertas):
        recomendaciones.append("Priorizar en etapa futura el reemplazo gradual de asiento directo por propuesta de asiento revisable.")

    if any(alerta["codigo"] == "PAGOS_ANTICIPOS_PROVEEDORES_NO_DETECTADOS" for alerta in alertas):
        recomendaciones.append("Agregar en etapa futura una matriz especifica para anticipos a proveedores y su aplicacion posterior a facturas.")

    if any(alerta["codigo"] == "PAGOS_RETENCIONES_NO_PARAMETRIZADAS" for alerta in alertas):
        recomendaciones.append("Agregar matriz de retenciones practicadas por impuesto/regimen/jurisdiccion/cuenta contable antes de modificar calculo operativo.")

    return recomendaciones


def _contar_casos(casos: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    estados = {"SOPORTADO_BASE": 0, "A_REVISAR": 0, "INCOMPLETO": 0}
    for caso in casos:
        estado = caso.get("estado")
        if estado in estados:
            estados[estado] += 1
    return estados


def _determinar_estado(alertas: Sequence[Dict[str, Any]], conteo_casos: Dict[str, int]) -> str:
    if any(alerta.get("severidad") == SEVERIDAD_CRITICA for alerta in alertas):
        return ESTADO_CRITICO
    if conteo_casos.get("INCOMPLETO", 0) > 0:
        return ESTADO_REQUIERE_REVISION
    if any(alerta.get("severidad") == SEVERIDAD_ADVERTENCIA for alerta in alertas):
        return ESTADO_REQUIERE_PARAMETRIZACION
    return ESTADO_OK


def _cantidad_incompletos(casos: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for caso in casos if caso.get("estado") == "INCOMPLETO")


def _caso(codigo: str, nombre: str, estado: str, detalle: str) -> Dict[str, Any]:
    return {
        "codigo": codigo,
        "nombre": nombre,
        "estado": estado,
        "detalle": detalle,
    }


def _alerta(codigo: str, severidad: str, titulo: str, detalle: str) -> Dict[str, str]:
    return {
        "codigo": codigo,
        "severidad": severidad,
        "titulo": titulo,
        "detalle": detalle,
    }


def _existe_tabla(tablas: Dict[str, Any], tabla: str) -> bool:
    info = tablas.get(tabla, {})
    return info.get("existe") is True


def _tabla_tiene_columna(tablas: Dict[str, Any], tabla: str, columna: str) -> bool:
    info = tablas.get(tabla, {})
    return columna in (info.get("columnas") or [])


def _listar_tablas(conn: sqlite3.Connection) -> set[str]:
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        return {str(row[0]) for row in cur.fetchall()}
    except Exception:
        return set()


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
            (tabla,),
        )
        return cur.fetchone() is not None
    except Exception:
        return False


def _columnas_tabla(conn: sqlite3.Connection, tabla: str) -> List[str]:
    try:
        cur = conn.execute(f"PRAGMA table_info({_quote_identifier(tabla)})")
        return [str(row[1]) for row in cur.fetchall()]
    except Exception:
        return []


def _contar_filas(conn: sqlite3.Connection, tabla: str) -> Optional[int]:
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(tabla)}")
        fila = cur.fetchone()
        return int(fila[0]) if fila else 0
    except Exception:
        return None


def _contar_filas_empresa(conn: sqlite3.Connection, tabla: str, empresa_id: int) -> Optional[int]:
    try:
        cur = conn.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(tabla)} WHERE empresa_id = ?",
            (empresa_id,),
        )
        fila = cur.fetchone()
        return int(fila[0]) if fila else 0
    except Exception:
        return None


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'