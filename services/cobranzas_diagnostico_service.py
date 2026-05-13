from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


DB_DEFAULT = Path("data/contabilidad_ff.db")

TABLAS_COBRANZAS_ESPERADAS = [
    "cobranzas",
    "cobranzas_imputaciones",
    "cobranzas_retenciones",
    "cobranzas_auditoria",
    "cuenta_corriente_clientes",
    "tesoreria_operaciones",
    "tesoreria_operaciones_componentes",
    "plan_cuentas_empresa",
]

TABLAS_APOYO_RELEVANTES = [
    "ventas_comprobantes",
    "clientes_configuracion",
    "cuentas_tesoreria",
    "tesoreria_cuentas",
    "caja_movimientos",
    "cajas_movimientos",
    "asientos_propuestos",
    "bandeja_asientos_propuestos",
]

TABLAS_ESTRUCTURALES_PENDIENTES = [
    "clientes",
    "recibos_emitidos",
    "cobranzas_aplicaciones",
    "cobranzas_anticipos_clientes",
    "cobranzas_diferencias",
]

PATRONES_IMPACTOS_DIRECTOS = {
    "libro_diario": [
        "INSERT INTO libro_diario",
        "_insertar_libro_diario",
        "_proximo_asiento_cur",
        "asiento_id",
        "asiento_reverso",
    ],
    "cuenta_corriente_clientes": [
        "INSERT INTO cuenta_corriente_clientes",
        "_insertar_cuenta_corriente_cliente",
        "cuenta_corriente_clientes",
    ],
    "tesoreria_operaciones": [
        "INSERT INTO tesoreria_operaciones",
        "_insertar_operacion_tesoreria_cobranza",
        "tesoreria_operaciones",
    ],
    "tesoreria_operaciones_componentes": [
        "INSERT INTO tesoreria_operaciones_componentes",
        "tesoreria_operaciones_componentes",
    ],
    "caja": [
        "cajas_service",
        "registrar_cobranza_efectivo_en_caja_cur",
        "anular_movimientos_caja_por_referencia_cur",
        "tipo_cuenta",
        "CAJA",
    ],
    "imputaciones": [
        "INSERT INTO cobranzas_imputaciones",
        "imputaciones_normalizadas",
        "obtener_comprobantes_pendientes_cliente",
    ],
    "retenciones": [
        "INSERT INTO cobranzas_retenciones",
        "retenciones_normalizadas",
        "importe_retenciones",
        "Retención IIBB",
        "Retención Ganancias",
        "Retención IVA",
    ],
    "auditoria": [
        "INSERT INTO cobranzas_auditoria",
        "_registrar_auditoria",
        "cobranzas_auditoria",
    ],
    "anulacion": [
        "def anular_cobranza",
        "UPDATE cobranzas",
        "motivo_anulacion",
        "asiento_reverso",
    ],
    "duplicados": [
        "_construir_fingerprint_cobranza",
        "fingerprint",
        "No se generaron",
    ],
}

PATRONES_UI = {
    "seleccion_cliente_con_saldo": [
        "obtener_clientes_con_saldo_pendiente",
        "Cliente",
        "Saldo",
    ],
    "seleccion_comprobantes_pendientes": [
        "obtener_comprobantes_pendientes_cliente",
        "Comprobantes pendientes",
        "cobranzas_editor_pendientes",
    ],
    "medios_pago_y_cuentas_compatibles": [
        "Medio de pago",
        "_filtrar_cuentas_por_medio",
        "_mostrar_impacto_cobranza",
    ],
    "retenciones_ui": [
        "Retención IIBB",
        "Retención Ganancias",
        "Retención IVA",
        "retenciones_total",
    ],
    "anulacion_ui": [
        "Anular cobranza",
        "Motivo de anulación",
        "permitir_conciliada",
    ],
}

CASOS_COBRANZA_REQUERIDOS = [
    {
        "codigo": "COBRANZA_FACTURA_TOTAL",
        "nombre": "Cobranza total imputada a factura",
        "descripcion": "Cancela completamente un comprobante pendiente del cliente.",
        "requiere": ["cuenta_corriente_clientes", "imputaciones", "tesoreria_operaciones"],
        "riesgo_si_falta": "Puede quedar un cobro sin aplicar o una factura indebidamente pendiente.",
        "debe_ir_a_bandeja_futura": True,
    },
    {
        "codigo": "COBRANZA_FACTURA_PARCIAL",
        "nombre": "Cobranza parcial imputada a factura",
        "descripcion": "Reduce parcialmente el saldo pendiente de un comprobante.",
        "requiere": ["cuenta_corriente_clientes", "imputaciones", "tesoreria_operaciones"],
        "riesgo_si_falta": "Puede distorsionar antigüedad y saldo por comprobante.",
        "debe_ir_a_bandeja_futura": True,
    },
    {
        "codigo": "ANTICIPO_CLIENTE",
        "nombre": "Cobranza sin factura / anticipo de cliente",
        "descripcion": "Cobro recibido antes de la venta devengada o antes de identificar el comprobante.",
        "requiere": ["cuenta_corriente_clientes", "tesoreria_operaciones"],
        "riesgo_si_falta": "Puede imputarse erróneamente como menor crédito o como venta.",
        "debe_ir_a_bandeja_futura": True,
    },
    {
        "codigo": "RETENCIONES_SUFRIDAS",
        "nombre": "Retenciones sufridas en cobranzas",
        "descripcion": "Registra importes retenidos por el cliente como créditos fiscales o impositivos.",
        "requiere": ["retenciones", "libro_diario"],
        "riesgo_si_falta": "Puede no reconocerse el crédito fiscal/impositivo correspondiente.",
        "debe_ir_a_bandeja_futura": True,
    },
    {
        "codigo": "SALDO_A_FAVOR_CLIENTE",
        "nombre": "Saldo a favor del cliente",
        "descripcion": "Surge por cobros en exceso, notas de crédito o aplicaciones futuras.",
        "requiere": ["cuenta_corriente_clientes"],
        "riesgo_si_falta": "Puede quedar oculto como saldo negativo técnico sin clasificación.",
        "debe_ir_a_bandeja_futura": True,
    },
    {
        "codigo": "DIFERENCIA_COBRO",
        "nombre": "Diferencias de cobro",
        "descripcion": "Diferencias por redondeos, gastos bancarios, comisiones o diferencias no imputadas.",
        "requiere": ["tesoreria_operaciones", "cuenta_corriente_clientes"],
        "riesgo_si_falta": "Puede forzarse una imputación incorrecta contra factura.",
        "debe_ir_a_bandeja_futura": True,
    },
    {
        "codigo": "ANULACION_COBRANZA",
        "nombre": "Anulación/reverso de cobranza",
        "descripcion": "Revierte cuenta corriente, tesorería/caja y asiento, conservando trazabilidad.",
        "requiere": ["anulacion", "auditoria", "cuenta_corriente_clientes"],
        "riesgo_si_falta": "Puede romper conciliación, caja/banco y saldos de clientes.",
        "debe_ir_a_bandeja_futura": True,
    },
]

CUENTAS_SENSIBLES_COBRANZAS = {
    "deudores_por_ventas": [
        "DEUDORES POR VENTAS",
        "CLIENTES",
        "CUENTAS A COBRAR",
        "CREDITOS POR VENTAS",
        "CRÉDITOS POR VENTAS",
    ],
    "anticipos_de_clientes": [
        "ANTICIPOS DE CLIENTES",
        "ANTICIPO DE CLIENTES",
        "CLIENTES ANTICIPOS",
    ],
    "retenciones_iva_sufridas": [
        "RETENCIONES IVA",
        "RETENCION IVA",
        "RETENCIONES SUFRIDAS IVA",
        "IVA RETENIDO",
    ],
    "retenciones_iibb_sufridas": [
        "RETENCIONES IIBB",
        "RETENCION IIBB",
        "INGRESOS BRUTOS RETENIDO",
        "IIBB RETENIDO",
    ],
    "retenciones_ganancias_sufridas": [
        "RETENCIONES GANANCIAS",
        "RETENCION GANANCIAS",
        "GANANCIAS RETENIDO",
        "IMPUESTO A LAS GANANCIAS RETENIDO",
    ],
    "saldos_a_favor_clientes": [
        "SALDOS A FAVOR DE CLIENTES",
        "CLIENTES SALDOS A FAVOR",
        "SALDO A FAVOR CLIENTES",
    ],
    "diferencias_cobro": [
        "DIFERENCIAS DE COBRO",
        "DIFERENCIAS",
        "REDONDEO",
        "GASTOS BANCARIOS",
        "COMISIONES",
    ],
}


def diagnosticar_cobranzas(
    db_path: str | Path | None = None,
    archivo_servicio_cobranzas: str | Path = "services/cobranzas_service.py",
    archivo_ui_cobranzas: str | Path = "modulos/cobranzas.py",
) -> dict[str, Any]:
    """
    Cobranzas PRO v1 - Diagnóstico contable-operativo.

    Servicio de solo lectura:
    - no crea tablas;
    - no modifica cobranzas;
    - no impacta Caja/Banco/Tesorería;
    - no impacta cuenta corriente de clientes;
    - no genera asientos;
    - no toca la Bandeja.

    El objetivo es identificar deuda técnica/contable antes de rediseñar Cobranzas.
    """

    ruta_db = Path(db_path) if db_path is not None else DB_DEFAULT
    ruta_servicio = Path(archivo_servicio_cobranzas)
    ruta_ui = Path(archivo_ui_cobranzas)

    diagnostico: dict[str, Any] = {
        "modulo": "COBRANZAS",
        "etapa": "Cobranzas PRO v1 - Diagnóstico contable-operativo",
        "estado": "SIN_EVALUAR",
        "db_path": str(ruta_db),
        "solo_lectura": True,
        "tablas": {},
        "archivos": {},
        "impactos_directos": {},
        "capacidades_ui": {},
        "casos_requeridos": [],
        "plan_empresa": {},
        "hallazgos": [],
        "recomendaciones": [],
        "no_tocar_v1": [
            "services/cobranzas_service.py",
            "modulos/cobranzas.py",
            "services/ventas_service.py",
            "modulos/ventas.py",
            "services/bancos_operaciones_service.py",
            "services/cajas_service.py",
            "services/asientos_propuestos_service.py",
            "migrations/",
        ],
        "siguiente_etapa_sugerida": "Cobranzas PRO v2A - Parametrización asistida de cobranzas, anticipos, retenciones y diferencias",
    }

    if not ruta_db.exists():
        diagnostico["estado"] = "SIN_BASE"
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="COBRANZAS_DB_NO_ENCONTRADA",
                titulo="No se encontró la base de datos.",
                detalle=f"No existe la base SQLite en {ruta_db}.",
                accion="Confirmar ruta de base antes de diagnosticar Cobranzas.",
            )
        )
        return diagnostico

    with sqlite3.connect(ruta_db) as conn:
        conn.row_factory = sqlite3.Row

        for tabla in TABLAS_COBRANZAS_ESPERADAS + TABLAS_APOYO_RELEVANTES + TABLAS_ESTRUCTURALES_PENDIENTES:
            diagnostico["tablas"][tabla] = _diagnosticar_tabla(conn, tabla)

        diagnostico["plan_empresa"] = _diagnosticar_plan_empresa(conn)

    diagnostico["archivos"]["services/cobranzas_service.py"] = _diagnosticar_archivo(ruta_servicio)
    diagnostico["archivos"]["modulos/cobranzas.py"] = _diagnosticar_archivo(ruta_ui)

    contenido_servicio = _leer_texto_seguro(ruta_servicio)
    contenido_ui = _leer_texto_seguro(ruta_ui)

    diagnostico["impactos_directos"] = _detectar_patrones(contenido_servicio, PATRONES_IMPACTOS_DIRECTOS)
    diagnostico["capacidades_ui"] = _detectar_patrones(contenido_ui, PATRONES_UI)
    diagnostico["casos_requeridos"] = _evaluar_casos_requeridos(diagnostico["impactos_directos"])

    _agregar_hallazgos_tablas(diagnostico)
    _agregar_hallazgos_codigo(diagnostico)
    _agregar_hallazgos_ui(diagnostico)
    _agregar_hallazgos_plan_empresa(diagnostico)
    _agregar_hallazgos_casos(diagnostico)
    _agregar_recomendaciones(diagnostico)

    diagnostico["estado"] = _calcular_estado(diagnostico["hallazgos"])
    return diagnostico


def obtener_resumen_diagnostico_cobranzas(diagnostico: dict[str, Any]) -> dict[str, Any]:
    hallazgos = diagnostico.get("hallazgos", [])
    tablas = diagnostico.get("tablas", {})
    impactos = diagnostico.get("impactos_directos", {})
    capacidades_ui = diagnostico.get("capacidades_ui", {})
    casos = diagnostico.get("casos_requeridos", [])

    return {
        "estado": diagnostico.get("estado"),
        "tablas_existentes": sum(1 for info in tablas.values() if info.get("existe")),
        "tablas_faltantes": [nombre for nombre, info in tablas.items() if not info.get("existe")],
        "impactos_directos_detectados": [
            nombre for nombre, info in impactos.items() if info.get("detectado")
        ],
        "capacidades_ui_detectadas": [
            nombre for nombre, info in capacidades_ui.items() if info.get("detectado")
        ],
        "casos_requeridos_total": len(casos),
        "casos_soportados": sum(1 for caso in casos if caso.get("estado") == "SOPORTADO_BASE"),
        "casos_a_revisar": sum(1 for caso in casos if caso.get("estado") == "REQUIERE_REVISION"),
        "casos_incompletos": sum(1 for caso in casos if caso.get("estado") == "INCOMPLETO"),
        "casos_incompletos_codigos": [
            caso.get("codigo") for caso in casos if caso.get("estado") == "INCOMPLETO"
        ],
        "usos_contables_detectados": diagnostico.get("plan_empresa", {}).get("usos_detectados", {}),
        "usos_contables_pendientes": diagnostico.get("plan_empresa", {}).get("usos_pendientes", []),
        "hallazgos_criticos": sum(1 for h in hallazgos if h.get("severidad") == "CRITICO"),
        "hallazgos_advertencia": sum(1 for h in hallazgos if h.get("severidad") == "ADVERTENCIA"),
        "hallazgos_info": sum(1 for h in hallazgos if h.get("severidad") == "INFO"),
    }


def exportar_diagnostico_cobranzas_como_texto(diagnostico: dict[str, Any]) -> str:
    lineas = [
        f"Modulo: {diagnostico.get('modulo', 'COBRANZAS')}",
        f"Etapa: {diagnostico.get('etapa', '')}",
        f"Estado: {diagnostico.get('estado', '')}",
        "",
        "Impactos directos detectados:",
    ]

    for nombre, info in diagnostico.get("impactos_directos", {}).items():
        if info.get("detectado"):
            lineas.append(f"- {nombre}: {', '.join(info.get('patrones', []))}")

    lineas.append("")
    lineas.append("Casos requeridos:")
    for caso in diagnostico.get("casos_requeridos", []):
        lineas.append(
            f"- {caso.get('codigo')} | {caso.get('estado')} | "
            f"faltantes: {', '.join(caso.get('faltantes', [])) or 'sin faltantes'}"
        )

    lineas.append("")
    lineas.append("Hallazgos:")
    for hallazgo in diagnostico.get("hallazgos", []):
        lineas.append(
            f"- [{hallazgo.get('severidad')}] {hallazgo.get('codigo')}: "
            f"{hallazgo.get('titulo')} {hallazgo.get('detalle')}"
        )

    lineas.append("")
    lineas.append("Recomendaciones:")
    for recomendacion in diagnostico.get("recomendaciones", []):
        lineas.append(f"- {recomendacion}")

    return "\n".join(lineas)


def _diagnosticar_tabla(conn: sqlite3.Connection, tabla: str) -> dict[str, Any]:
    existe = _tabla_existe(conn, tabla)
    if not existe:
        return {
            "existe": False,
            "registros": None,
            "columnas": [],
        }

    return {
        "existe": True,
        "registros": _contar_registros(conn, tabla),
        "columnas": _columnas_tabla(conn, tabla),
    }


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    fila = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (tabla,),
    ).fetchone()
    return fila is not None


def _contar_registros(conn: sqlite3.Connection, tabla: str) -> int:
    try:
        fila = conn.execute(f'SELECT COUNT(*) AS cantidad FROM "{tabla}"').fetchone()
        return int(fila["cantidad"] if isinstance(fila, sqlite3.Row) else fila[0])
    except sqlite3.Error:
        return 0


def _columnas_tabla(conn: sqlite3.Connection, tabla: str) -> list[str]:
    try:
        filas = conn.execute(f'PRAGMA table_info("{tabla}")').fetchall()
    except sqlite3.Error:
        return []

    return [str(fila["name"] if isinstance(fila, sqlite3.Row) else fila[1]) for fila in filas]


def _diagnosticar_archivo(ruta: Path) -> dict[str, Any]:
    if not ruta.exists():
        return {
            "existe": False,
            "lineas": 0,
            "path": str(ruta),
        }

    contenido = _leer_texto_seguro(ruta)
    return {
        "existe": True,
        "lineas": len(contenido.splitlines()),
        "path": str(ruta),
    }


def _leer_texto_seguro(ruta: Path) -> str:
    try:
        return ruta.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ruta.read_text(encoding="latin-1")
    except FileNotFoundError:
        return ""


def _detectar_patrones(contenido: str, definiciones: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    resultado = {}
    for nombre, patrones in definiciones.items():
        encontrados = []
        for patron in patrones:
            if re.search(re.escape(patron), contenido, flags=re.IGNORECASE):
                encontrados.append(patron)

        resultado[nombre] = {
            "detectado": bool(encontrados),
            "patrones": encontrados,
        }

    return resultado


def _evaluar_casos_requeridos(impactos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    casos = []

    for caso in CASOS_COBRANZA_REQUERIDOS:
        faltantes = [
            requisito
            for requisito in caso["requiere"]
            if not impactos.get(requisito, {}).get("detectado")
        ]

        if faltantes:
            estado = "INCOMPLETO"
        elif caso["codigo"] in {"ANTICIPO_CLIENTE", "SALDO_A_FAVOR_CLIENTE", "DIFERENCIA_COBRO"}:
            estado = "REQUIERE_REVISION"
        else:
            estado = "SOPORTADO_BASE"

        casos.append(
            {
                **caso,
                "estado": estado,
                "faltantes": faltantes,
            }
        )

    return casos


def _diagnosticar_plan_empresa(conn: sqlite3.Connection) -> dict[str, Any]:
    tabla = "plan_cuentas_empresa"
    if not _tabla_existe(conn, tabla):
        return {
            "existe": False,
            "registros": 0,
            "usos_detectados": {},
            "usos_pendientes": list(CUENTAS_SENSIBLES_COBRANZAS.keys()),
            "coincidencias": {},
        }

    columnas = _columnas_tabla(conn, tabla)
    filas = _leer_filas_plan_empresa(conn, tabla, columnas)
    columnas_texto = _columnas_texto_probables(columnas)

    coincidencias: dict[str, list[dict[str, Any]]] = {}
    usos_detectados: dict[str, bool] = {}

    for uso, patrones in CUENTAS_SENSIBLES_COBRANZAS.items():
        coincidencias[uso] = []

        for fila in filas:
            texto_fila = " | ".join(str(fila.get(col, "") or "") for col in columnas_texto).upper()
            if any(patron.upper() in texto_fila for patron in patrones):
                coincidencias[uso].append(
                    {
                        "id": fila.get("id"),
                        "codigo": fila.get("codigo") or fila.get("codigo_cuenta") or fila.get("cuenta_codigo"),
                        "nombre": fila.get("nombre") or fila.get("cuenta") or fila.get("descripcion"),
                        "activa": fila.get("activa") if "activa" in fila else fila.get("activo"),
                    }
                )

        usos_detectados[uso] = bool(coincidencias[uso])

    usos_pendientes = [uso for uso, detectado in usos_detectados.items() if not detectado]

    return {
        "existe": True,
        "registros": len(filas),
        "columnas": columnas,
        "columnas_texto_analizadas": columnas_texto,
        "usos_detectados": usos_detectados,
        "usos_pendientes": usos_pendientes,
        "coincidencias": coincidencias,
    }


def _leer_filas_plan_empresa(
    conn: sqlite3.Connection,
    tabla: str,
    columnas: list[str],
    limite: int = 3000,
) -> list[dict[str, Any]]:
    if not columnas:
        return []

    columnas_sql = ", ".join(f'"{col}"' for col in columnas)
    try:
        filas = conn.execute(
            f'SELECT {columnas_sql} FROM "{tabla}" LIMIT ?',
            (limite,),
        ).fetchall()
    except sqlite3.Error:
        return []

    resultado = []
    for fila in filas:
        if isinstance(fila, sqlite3.Row):
            item = {col: fila[col] for col in columnas}
        else:
            item = {col: fila[idx] for idx, col in enumerate(columnas)}

        if _cuenta_activa(item):
            resultado.append(item)

    return resultado


def _cuenta_activa(cuenta: dict[str, Any]) -> bool:
    for campo in ("activa", "activo", "habilitada", "habilitado"):
        if campo in cuenta and cuenta[campo] is not None:
            valor = str(cuenta[campo]).strip().upper()
            return valor not in {"0", "FALSE", "NO", "N", "INACTIVA", "INACTIVO", "ANULADA", "ANULADO"}

    for campo in ("estado", "status"):
        if campo in cuenta and cuenta[campo] is not None:
            valor = str(cuenta[campo]).strip().upper()
            if valor in {"INACTIVA", "INACTIVO", "ANULADA", "ANULADO", "BAJA"}:
                return False

    return True


def _columnas_texto_probables(columnas: list[str]) -> list[str]:
    preferidas = [
        "codigo",
        "codigo_cuenta",
        "cuenta_codigo",
        "nombre",
        "cuenta",
        "descripcion",
        "denominacion",
        "rubro",
        "subrubro",
        "elemento",
        "uso_operativo",
        "uso_contable",
        "comportamiento",
        "tipo",
    ]

    seleccionadas = [col for col in preferidas if col in columnas]
    if seleccionadas:
        return seleccionadas

    return columnas


def _agregar_hallazgos_tablas(diagnostico: dict[str, Any]) -> None:
    tablas = diagnostico.get("tablas", {})

    for tabla in TABLAS_COBRANZAS_ESPERADAS:
        info = tablas.get(tabla, {})
        if not info.get("existe"):
            diagnostico["hallazgos"].append(
                _hallazgo(
                    severidad="ADVERTENCIA",
                    codigo=f"COBRANZAS_TABLA_ESPERADA_FALTANTE_{tabla.upper()}",
                    titulo=f"Falta tabla esperada: {tabla}.",
                    detalle="Puede limitar el diagnóstico integral de Cobranzas.",
                    accion="Confirmar si la tabla debe crearse, migrarse o reemplazarse en una etapa posterior.",
                )
            )

    for tabla in TABLAS_ESTRUCTURALES_PENDIENTES:
        info = tablas.get(tabla, {})
        if not info.get("existe"):
            diagnostico["hallazgos"].append(
                _hallazgo(
                    severidad="INFO",
                    codigo=f"COBRANZAS_TABLA_ESTRUCTURAL_PENDIENTE_{tabla.upper()}",
                    titulo=f"Tabla estructural pendiente: {tabla}.",
                    detalle="No se crea en v1. Queda como insumo para arquitectura profesional de Cobranzas.",
                    accion="Evaluar en v2/v3 según diseño de recibos, anticipos y aplicaciones.",
                )
            )

    cobranzas = tablas.get("cobranzas", {})
    if cobranzas.get("existe") and cobranzas.get("registros") == 0:
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_DEMO_SIN_MOVIMIENTOS",
                titulo="La base no tiene cobranzas cargadas.",
                detalle="Es una buena condición para diagnosticar sin arrastrar historia operativa demo.",
                accion="Mantener esta etapa como solo lectura antes de rediseñar flujo.",
            )
        )


def _agregar_hallazgos_codigo(diagnostico: dict[str, Any]) -> None:
    impactos = diagnostico.get("impactos_directos", {})

    if impactos.get("libro_diario", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="COBRANZAS_ASIENTO_DIRECTO_LIBRO_DIARIO",
                titulo="Cobranzas genera asientos directamente en Libro Diario.",
                detalle="La arquitectura PRO debe tender a asiento propuesto y Bandeja antes del Libro Diario.",
                accion="No modificar todavía. Diseñar migración controlada para no duplicar asientos.",
            )
        )

    if impactos.get("cuenta_corriente_clientes", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_IMPACTA_CUENTA_CORRIENTE_CLIENTES",
                titulo="Cobranzas impacta cuenta corriente de clientes.",
                detalle="Debe distinguir cancelaciones, anticipos, saldos a favor y diferencias.",
                accion="Revisar reglas antes de tocar el flujo vigente.",
            )
        )

    if impactos.get("tesoreria_operaciones", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_IMPACTA_TESORERIA",
                titulo="Cobranzas impacta Tesorería/Banco.",
                detalle="Debe conservar trazabilidad con medio de pago y cuenta de destino.",
                accion="No tocar Banco/Caja en v1.",
            )
        )

    if impactos.get("caja", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_IMPACTA_CAJA_EFECTIVO",
                titulo="Cobranzas impacta Caja para operaciones en efectivo.",
                detalle="La regla vigente de EFECTIVO -> Caja debe preservarse.",
                accion="No modificar integración Caja/Cobranzas en v1.",
            )
        )

    if impactos.get("retenciones", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_SOPORTA_RETENCIONES",
                titulo="Cobranzas registra retenciones sufridas.",
                detalle="Debe parametrizarse luego la cuenta contable por tipo de retención.",
                accion="Preparar Cobranzas v2A para retenciones IVA/IIBB/Ganancias contra Plan Empresa.",
            )
        )


def _agregar_hallazgos_ui(diagnostico: dict[str, Any]) -> None:
    capacidades = diagnostico.get("capacidades_ui", {})

    requeridas = [
        "seleccion_cliente_con_saldo",
        "seleccion_comprobantes_pendientes",
        "medios_pago_y_cuentas_compatibles",
        "retenciones_ui",
        "anulacion_ui",
    ]
    faltantes = [cap for cap in requeridas if not capacidades.get(cap, {}).get("detectado")]

    if faltantes:
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="COBRANZAS_UI_CAPACIDADES_NO_DETECTADAS",
                titulo="Hay capacidades operativas no detectadas en UI de Cobranzas.",
                detalle=", ".join(faltantes),
                accion="Revisar UI antes de avanzar a aceptación/parametrización.",
            )
        )


def _agregar_hallazgos_plan_empresa(diagnostico: dict[str, Any]) -> None:
    plan = diagnostico.get("plan_empresa", {})

    if not plan.get("existe"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="COBRANZAS_PLAN_EMPRESA_NO_EXISTE",
                titulo="No existe plan_cuentas_empresa.",
                detalle="Cobranzas PRO requiere Plan Empresa como base de parametrización.",
                accion="Resolver Plan Empresa antes de parametrizar Cobranzas.",
            )
        )
        return

    pendientes = plan.get("usos_pendientes", [])
    sensibles = [
        "anticipos_de_clientes",
        "retenciones_iva_sufridas",
        "retenciones_iibb_sufridas",
        "retenciones_ganancias_sufridas",
        "saldos_a_favor_clientes",
        "diferencias_cobro",
    ]
    pendientes_sensibles = [uso for uso in pendientes if uso in sensibles]

    if pendientes_sensibles:
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="COBRANZAS_USOS_CONTABLES_SENSIBLES_NO_DETECTADOS",
                titulo="Hay usos contables sensibles de Cobranzas sin cuenta detectada en Plan Empresa.",
                detalle=", ".join(pendientes_sensibles),
                accion="Preparar parametrización asistida de cobranzas contra Plan Empresa.",
            )
        )


def _agregar_hallazgos_casos(diagnostico: dict[str, Any]) -> None:
    incompletos = [
        caso for caso in diagnostico.get("casos_requeridos", [])
        if caso.get("estado") == "INCOMPLETO"
    ]
    revisar = [
        caso for caso in diagnostico.get("casos_requeridos", [])
        if caso.get("estado") == "REQUIERE_REVISION"
    ]

    if incompletos:
        detalle = "; ".join(
            f"{caso['codigo']}: {', '.join(caso['faltantes'])}"
            for caso in incompletos
        )
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="COBRANZAS_CASOS_INCOMPLETOS",
                titulo="Hay casos de cobranza sin soporte base detectado.",
                detalle=detalle,
                accion="No implementar flujo nuevo hasta cubrir casos mínimos.",
            )
        )

    if revisar:
        detalle = ", ".join(caso["codigo"] for caso in revisar)
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_CASOS_REQUIEREN_REGLAS",
                titulo="Hay casos soportados parcialmente que requieren reglas contables explícitas.",
                detalle=detalle,
                accion="Definir reglas de anticipos, saldos a favor y diferencias antes de automatizar asientos.",
            )
        )


def _agregar_recomendaciones(diagnostico: dict[str, Any]) -> None:
    diagnostico["recomendaciones"].extend(
        [
            "Mantener services/cobranzas_service.py sin cambios en v1 para no romper la operatoria vigente.",
            "No modificar Caja/Banco/Tesorería en esta etapa.",
            "Separar en una etapa futura el registro operativo de la cobranza de la generación de asiento contable.",
            "La arquitectura futura debe enviar propuestas a Bandeja antes de Libro Diario.",
            "Distinguir cancelación de factura, cobro parcial, anticipo, saldo a favor y diferencia de cobro.",
            "Parametrizar retenciones sufridas por tipo contra Plan Empresa antes de automatizar asientos definitivos.",
            "Preservar la regla vigente: solo EFECTIVO impacta Caja; medios no efectivos van por Tesorería/Banco/cuenta puente.",
            "No crear tablas nuevas en v1. Primero cerrar diagnóstico y matriz de parametrización.",
        ]
    )


def _calcular_estado(hallazgos: list[dict[str, Any]]) -> str:
    if any(h.get("severidad") == "CRITICO" for h in hallazgos):
        return "CRITICO"

    if any(h.get("severidad") == "ADVERTENCIA" for h in hallazgos):
        return "REQUIERE_REVISION"

    return "OK_DIAGNOSTICO"


def _hallazgo(
    severidad: str,
    codigo: str,
    titulo: str,
    detalle: str,
    accion: str,
) -> dict[str, str]:
    return {
        "severidad": severidad,
        "codigo": codigo,
        "titulo": titulo,
        "detalle": detalle,
        "accion": accion,
    }


# Alias claros para futura UI sin acoplarse a nombres internos.
generar_diagnostico_cobranzas = diagnosticar_cobranzas
diagnosticar_estado_cobranzas = diagnosticar_cobranzas
