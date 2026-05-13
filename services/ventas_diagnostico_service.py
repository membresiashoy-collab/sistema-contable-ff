from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


DB_DEFAULT = Path("data/contabilidad_ff.db")

TABLAS_OPERATIVAS_ESPERADAS = [
    "ventas_comprobantes",
    "cuenta_corriente_clientes",
    "clientes_configuracion",
    "cobranzas",
    "cobranzas_imputaciones",
    "cobranzas_retenciones",
    "iva_movimientos_fiscales",
    "plan_cuentas_empresa",
    "mapeos_contables_empresa",
]

TABLAS_ESTRUCTURALES_PENDIENTES = [
    "ventas_detalle",
    "ventas_items",
    "clientes",
    "ventas_clientes",
    "recibos_emitidos",
]

CUENTAS_HARDCODEADAS_VENTAS = [
    "DEUDORES POR VENTAS",
    "VENTAS",
    "IVA DEBITO FISCAL",
    "IVA DÉBITO FISCAL",
]

IMPACTOS_DIRECTOS_ESPERADOS = {
    "libro_diario": [
        "INSERT INTO libro_diario",
        "op_insert_libro_diario",
        "libro_diario",
    ],
    "ventas_comprobantes": [
        "INSERT INTO ventas_comprobantes",
        "op_insert_venta",
        "ventas_comprobantes",
    ],
    "cuenta_corriente_clientes": [
        "INSERT INTO cuenta_corriente_clientes",
        "op_insert_cta_cte_cliente",
        "cuenta_corriente_clientes",
    ],
    "comprobantes_procesados": [
        "INSERT INTO comprobantes_procesados",
        "op_insert_comprobante_procesado",
        "comprobantes_procesados",
    ],
}

TIPOS_VENTA_REQUERIDOS = [
    {
        "codigo": "VENTA_MERCADERIAS",
        "nombre": "Venta de mercaderías",
        "impacto_contable": "Ingreso por venta de bienes. El CMV queda fuera de esta etapa y deberá diagnosticarse en Stock/CMV.",
        "impacto_iva": "Puede generar IVA débito si la operación está gravada.",
        "impacto_cc": "Aumenta saldo a cobrar del cliente.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "ventas_mercaderias", "iva_debito_fiscal"],
        "estado_v1": "diagnosticar_parametrizacion",
    },
    {
        "codigo": "VENTA_SERVICIOS",
        "nombre": "Venta de servicios",
        "impacto_contable": "Ingreso por prestación de servicios.",
        "impacto_iva": "Puede generar IVA débito si la prestación está gravada.",
        "impacto_cc": "Aumenta saldo a cobrar del cliente.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "ventas_servicios", "iva_debito_fiscal"],
        "estado_v1": "diagnosticar_parametrizacion",
    },
    {
        "codigo": "VENTA_BIEN_USO",
        "nombre": "Venta de bienes de uso",
        "impacto_contable": "No debe mezclarse con ventas ordinarias. Requiere tratamiento específico de baja del activo y resultado.",
        "impacto_iva": "Puede generar IVA débito según el caso fiscal.",
        "impacto_cc": "Aumenta saldo a cobrar o cancela una operación puntual.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "resultado_venta_bienes_uso", "iva_debito_fiscal"],
        "estado_v1": "solo_diagnostico_no_implementar",
    },
    {
        "codigo": "VENTA_EXENTA",
        "nombre": "Venta exenta",
        "impacto_contable": "Ingreso operativo o específico sin débito fiscal directo.",
        "impacto_iva": "No genera IVA débito, pero debe quedar expuesta/controlada fiscalmente.",
        "impacto_cc": "Aumenta saldo a cobrar del cliente.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "ventas_exentas"],
        "estado_v1": "diagnosticar_parametrizacion",
    },
    {
        "codigo": "VENTA_NO_GRAVADA",
        "nombre": "Venta no gravada",
        "impacto_contable": "Ingreso o concepto no alcanzado por IVA.",
        "impacto_iva": "No genera IVA débito. Debe diferenciarse de exento.",
        "impacto_cc": "Aumenta saldo a cobrar del cliente.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "ventas_no_gravadas"],
        "estado_v1": "diagnosticar_parametrizacion",
    },
    {
        "codigo": "EXPORTACION_BIENES",
        "nombre": "Exportación de bienes",
        "impacto_contable": "Ingreso por exportación separado de ventas internas.",
        "impacto_iva": "Tratamiento fiscal diferenciado. No debe forzarse como venta local gravada.",
        "impacto_cc": "Puede generar cuenta corriente de cliente del exterior.",
        "cuentas_a_parametrizar": ["deudores_exterior", "exportacion_bienes"],
        "estado_v1": "diagnosticar_parametrizacion",
    },
    {
        "codigo": "EXPORTACION_SERVICIOS",
        "nombre": "Exportación de servicios",
        "impacto_contable": "Ingreso por exportación de servicios separado de ventas internas.",
        "impacto_iva": "Tratamiento fiscal diferenciado. No debe forzarse como venta local gravada.",
        "impacto_cc": "Puede generar cuenta corriente de cliente del exterior.",
        "cuentas_a_parametrizar": ["deudores_exterior", "exportacion_servicios"],
        "estado_v1": "diagnosticar_parametrizacion",
    },
    {
        "codigo": "NOTA_CREDITO",
        "nombre": "Nota de crédito",
        "impacto_contable": "Disminuye o revierte venta, IVA débito y cuenta corriente según comprobante vinculado.",
        "impacto_iva": "Reduce débito fiscal si corresponde.",
        "impacto_cc": "Disminuye saldo a cobrar o genera saldo a favor del cliente.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "ventas_devoluciones_bonificaciones", "iva_debito_fiscal"],
        "estado_v1": "diagnosticar_reglas",
    },
    {
        "codigo": "NOTA_DEBITO",
        "nombre": "Nota de débito",
        "impacto_contable": "Aumenta deuda del cliente por ajuste, interés, diferencia u otro concepto.",
        "impacto_iva": "Puede generar IVA débito según el concepto.",
        "impacto_cc": "Aumenta saldo a cobrar.",
        "cuentas_a_parametrizar": ["deudores_por_ventas", "ajustes_ventas_intereses_diferencias", "iva_debito_fiscal"],
        "estado_v1": "diagnosticar_reglas",
    },
    {
        "codigo": "ANTICIPO_CLIENTE",
        "nombre": "Anticipo de clientes",
        "impacto_contable": "No debe reconocerse como ingreso devengado si no existe venta asociada. Debe tratarse como pasivo hasta su aplicación.",
        "impacto_iva": "Debe analizarse según emisión/comprobante y normativa aplicable; no forzar como venta ordinaria.",
        "impacto_cc": "Genera saldo a favor del cliente o pasivo por anticipo.",
        "cuentas_a_parametrizar": ["anticipos_de_clientes", "clientes_saldos_a_favor"],
        "estado_v1": "diagnosticar_reglas",
    },
]

USOS_CONTABLES_VENTAS = {
    "deudores_por_ventas": [
        "DEUDORES POR VENTAS",
        "CLIENTES",
        "CUENTAS A COBRAR",
        "CRÉDITOS POR VENTAS",
        "CREDITOS POR VENTAS",
    ],
    "deudores_exterior": [
        "CLIENTES DEL EXTERIOR",
        "DEUDORES DEL EXTERIOR",
        "CRÉDITOS POR VENTAS AL EXTERIOR",
        "CREDITOS POR VENTAS AL EXTERIOR",
    ],
    "ventas_mercaderias": [
        "VENTAS DE MERCADER",
        "VENTA DE MERCADER",
        "VENTAS",
    ],
    "ventas_servicios": [
        "VENTAS DE SERVICIOS",
        "SERVICIOS PRESTADOS",
        "INGRESOS POR SERVICIOS",
        "HONORARIOS",
    ],
    "ventas_exentas": [
        "VENTAS EXENTAS",
        "INGRESOS EXENTOS",
    ],
    "ventas_no_gravadas": [
        "VENTAS NO GRAVADAS",
        "INGRESOS NO GRAVADOS",
    ],
    "exportacion_bienes": [
        "EXPORTACIÓN DE BIENES",
        "EXPORTACION DE BIENES",
        "VENTAS AL EXTERIOR",
    ],
    "exportacion_servicios": [
        "EXPORTACIÓN DE SERVICIOS",
        "EXPORTACION DE SERVICIOS",
        "SERVICIOS AL EXTERIOR",
    ],
    "iva_debito_fiscal": [
        "IVA DEBITO FISCAL",
        "IVA DÉBITO FISCAL",
        "IVA DEBITO",
        "IVA DÉBITO",
    ],
    "anticipos_de_clientes": [
        "ANTICIPOS DE CLIENTES",
        "ANTICIPO DE CLIENTES",
        "CLIENTES ANTICIPOS",
    ],
    "clientes_saldos_a_favor": [
        "SALDOS A FAVOR DE CLIENTES",
        "CLIENTES SALDOS A FAVOR",
    ],
    "resultado_venta_bienes_uso": [
        "RESULTADO VENTA BIENES DE USO",
        "RESULTADO POR VENTA DE BIENES DE USO",
        "VENTA BIENES DE USO",
    ],
    "ventas_devoluciones_bonificaciones": [
        "DEVOLUCIONES",
        "BONIFICACIONES",
        "DESCUENTOS SOBRE VENTAS",
        "NOTAS DE CREDITO",
        "NOTAS DE CRÉDITO",
    ],
    "ajustes_ventas_intereses_diferencias": [
        "INTERESES",
        "DIFERENCIAS",
        "AJUSTES DE VENTAS",
        "RECARGOS",
    ],
}


def diagnosticar_ventas(
    db_path: str | Path | None = None,
    archivo_servicio_ventas: str | Path = "services/ventas_service.py",
    archivo_ui_ventas: str | Path = "modulos/ventas.py",
) -> dict[str, Any]:
    """
    Diagnóstico contable-operativo de Ventas PRO v1.

    Es un servicio de solo lectura:
    - no crea tablas;
    - no modifica datos;
    - no genera asientos;
    - no impacta IVA;
    - no impacta cuenta corriente;
    - no usa la Bandeja.

    El objetivo es detectar deuda técnica y contable antes de rediseñar Ventas.
    """

    ruta_db = Path(db_path) if db_path is not None else DB_DEFAULT
    ruta_servicio = Path(archivo_servicio_ventas)
    ruta_ui = Path(archivo_ui_ventas)

    diagnostico: dict[str, Any] = {
        "modulo": "VENTAS",
        "etapa": "Ventas PRO v1 - Diagnóstico contable-operativo y clasificación de ventas",
        "estado": "SIN_EVALUAR",
        "db_path": str(ruta_db),
        "tablas": {},
        "archivos": {},
        "impactos_directos": {},
        "hardcodes_contables": [],
        "plan_empresa": {},
        "tipos_venta_requeridos": TIPOS_VENTA_REQUERIDOS,
        "hallazgos": [],
        "recomendaciones": [],
        "no_tocar_v1": [
            "services/ventas_service.py",
            "modulos/ventas.py",
            "services/iva_service.py",
            "services/cobranzas_service.py",
            "services/asientos_propuestos_service.py",
            "migrations/",
            "stock",
            "cmv",
        ],
        "siguiente_etapa_sugerida": "Ventas PRO v2A - Parametrización asistida de tipos de venta contra Plan Empresa",
    }

    if not ruta_db.exists():
        diagnostico["estado"] = "SIN_BASE"
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="VENTAS_DB_NO_ENCONTRADA",
                titulo="No se encontró la base de datos configurada.",
                detalle=f"No existe la base SQLite en {ruta_db}.",
                accion="Confirmar ruta de base antes de diagnosticar Ventas.",
            )
        )
        return diagnostico

    with sqlite3.connect(ruta_db) as conn:
        conn.row_factory = sqlite3.Row

        for tabla in TABLAS_OPERATIVAS_ESPERADAS + TABLAS_ESTRUCTURALES_PENDIENTES:
            diagnostico["tablas"][tabla] = _diagnosticar_tabla(conn, tabla)

        diagnostico["plan_empresa"] = _diagnosticar_plan_empresa(conn)

    diagnostico["archivos"]["services/ventas_service.py"] = _diagnosticar_archivo(ruta_servicio)
    diagnostico["archivos"]["modulos/ventas.py"] = _diagnosticar_archivo(ruta_ui)

    contenido_servicio = _leer_texto_seguro(ruta_servicio)
    contenido_ui = _leer_texto_seguro(ruta_ui)
    contenido_total = "\n".join([contenido_servicio, contenido_ui])

    diagnostico["hardcodes_contables"] = _detectar_hardcodes_contables(contenido_total)
    diagnostico["impactos_directos"] = _detectar_impactos_directos(contenido_total)

    _agregar_hallazgos_tablas(diagnostico)
    _agregar_hallazgos_codigo(diagnostico)
    _agregar_hallazgos_plan_empresa(diagnostico)
    _agregar_recomendaciones(diagnostico)
    diagnostico["estado"] = _calcular_estado(diagnostico["hallazgos"])

    return diagnostico


def obtener_resumen_diagnostico_ventas(diagnostico: dict[str, Any]) -> dict[str, Any]:
    """
    Devuelve una vista compacta para UI o logs.
    """

    hallazgos = diagnostico.get("hallazgos", [])
    tablas = diagnostico.get("tablas", {})
    plan = diagnostico.get("plan_empresa", {})

    return {
        "estado": diagnostico.get("estado"),
        "tablas_existentes": sum(1 for info in tablas.values() if info.get("existe")),
        "tablas_faltantes": [nombre for nombre, info in tablas.items() if not info.get("existe")],
        "hardcodes_contables": len(diagnostico.get("hardcodes_contables", [])),
        "impactos_directos_detectados": [
            nombre for nombre, info in diagnostico.get("impactos_directos", {}).items() if info.get("detectado")
        ],
        "usos_contables_detectados": plan.get("usos_detectados", {}),
        "hallazgos_criticos": sum(1 for h in hallazgos if h.get("severidad") == "CRITICO"),
        "hallazgos_advertencia": sum(1 for h in hallazgos if h.get("severidad") == "ADVERTENCIA"),
        "hallazgos_info": sum(1 for h in hallazgos if h.get("severidad") == "INFO"),
    }


def exportar_diagnostico_ventas_como_texto(diagnostico: dict[str, Any]) -> str:
    """
    Exportación simple en texto plano para revisión técnica/contable.
    No requiere pandas ni dependencias externas.
    """

    lineas = [
        f"Modulo: {diagnostico.get('modulo', 'VENTAS')}",
        f"Etapa: {diagnostico.get('etapa', '')}",
        f"Estado: {diagnostico.get('estado', '')}",
        "",
        "Hallazgos:",
    ]

    for hallazgo in diagnostico.get("hallazgos", []):
        lineas.append(
            f"- [{hallazgo.get('severidad')}] {hallazgo.get('codigo')}: "
            f"{hallazgo.get('titulo')} {hallazgo.get('detalle')}"
        )

    lineas.append("")
    lineas.append("Recomendaciones:")
    for recomendacion in diagnostico.get("recomendaciones", []):
        lineas.append(f"- {recomendacion}")

    lineas.append("")
    lineas.append("Tipos de venta requeridos:")
    for tipo in diagnostico.get("tipos_venta_requeridos", []):
        lineas.append(f"- {tipo.get('codigo')}: {tipo.get('nombre')}")

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
        return [str(fila["name"] if isinstance(fila, sqlite3.Row) else fila[1]) for fila in filas]
    except sqlite3.Error:
        return []


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


def _detectar_hardcodes_contables(contenido: str) -> list[dict[str, Any]]:
    hallados = []
    for cuenta in CUENTAS_HARDCODEADAS_VENTAS:
        patron = re.escape(cuenta)
        ocurrencias = [m.start() for m in re.finditer(patron, contenido, flags=re.IGNORECASE)]
        if ocurrencias:
            hallados.append(
                {
                    "cuenta": cuenta,
                    "ocurrencias": len(ocurrencias),
                    "riesgo": "Cuenta contable fija en código. Debe migrar a parametrización por Plan Empresa.",
                }
            )
    return hallados


def _detectar_impactos_directos(contenido: str) -> dict[str, dict[str, Any]]:
    impactos: dict[str, dict[str, Any]] = {}

    for impacto, patrones in IMPACTOS_DIRECTOS_ESPERADOS.items():
        encontrados = []
        for patron in patrones:
            if re.search(re.escape(patron), contenido, flags=re.IGNORECASE):
                encontrados.append(patron)

        impactos[impacto] = {
            "detectado": bool(encontrados),
            "patrones": encontrados,
            "riesgo": _riesgo_impacto_directo(impacto) if encontrados else "",
        }

    return impactos


def _riesgo_impacto_directo(impacto: str) -> str:
    riesgos = {
        "libro_diario": "Ventas genera asientos definitivos sin pasar por Bandeja.",
        "ventas_comprobantes": "Ventas registra comprobantes directamente. Esto puede mantenerse, pero debe separarse de contabilización.",
        "cuenta_corriente_clientes": "Ventas impacta cuenta corriente directamente. Debe revisarse junto con anticipos, notas y cobranzas.",
        "comprobantes_procesados": "Control de duplicados vigente. Debe conservarse o migrarse sin perder trazabilidad.",
    }
    return riesgos.get(impacto, "Impacto directo detectado.")


def _diagnosticar_plan_empresa(conn: sqlite3.Connection) -> dict[str, Any]:
    tabla = "plan_cuentas_empresa"
    if not _tabla_existe(conn, tabla):
        return {
            "existe": False,
            "registros": 0,
            "usos_detectados": {},
            "usos_pendientes": list(USOS_CONTABLES_VENTAS.keys()),
            "coincidencias": {},
        }

    columnas = _columnas_tabla(conn, tabla)
    columnas_texto = _columnas_texto_probables(columnas)
    filas = _leer_filas_plan_empresa(conn, tabla, columnas)

    coincidencias: dict[str, list[dict[str, Any]]] = {}
    usos_detectados: dict[str, bool] = {}

    for uso, patrones in USOS_CONTABLES_VENTAS.items():
        coincidencias[uso] = []
        for fila in filas:
            texto_fila = " | ".join(str(fila.get(col, "") or "") for col in columnas_texto).upper()
            if any(patron.upper() in texto_fila for patron in patrones):
                coincidencias[uso].append(
                    {
                        "id": fila.get("id"),
                        "codigo": fila.get("codigo") or fila.get("codigo_cuenta") or fila.get("cuenta_codigo"),
                        "nombre": fila.get("nombre") or fila.get("cuenta") or fila.get("descripcion"),
                        "activa": fila.get("activa"),
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


def _columnas_texto_probables(columnas: list[str]) -> list[str]:
    preferidas = [
        "codigo",
        "codigo_cuenta",
        "cuenta_codigo",
        "nombre",
        "cuenta",
        "descripcion",
        "rubro",
        "subrubro",
        "uso_operativo",
        "uso_contable",
        "tipo",
    ]

    seleccionadas = [col for col in preferidas if col in columnas]
    if seleccionadas:
        return seleccionadas

    return columnas


def _leer_filas_plan_empresa(
    conn: sqlite3.Connection,
    tabla: str,
    columnas: list[str],
    limite: int = 2000,
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
            resultado.append({col: fila[col] for col in columnas})
        else:
            resultado.append({col: fila[idx] for idx, col in enumerate(columnas)})
    return resultado


def _agregar_hallazgos_tablas(diagnostico: dict[str, Any]) -> None:
    tablas = diagnostico.get("tablas", {})

    for tabla in TABLAS_OPERATIVAS_ESPERADAS:
        info = tablas.get(tabla, {})
        if not info.get("existe"):
            diagnostico["hallazgos"].append(
                _hallazgo(
                    severidad="ADVERTENCIA",
                    codigo=f"VENTAS_TABLA_OPERATIVA_FALTANTE_{tabla.upper()}",
                    titulo=f"Falta tabla operativa esperada: {tabla}.",
                    detalle="Puede limitar el diagnóstico integral de Ventas.",
                    accion="Confirmar si la tabla debe crearse, migrarse o reemplazarse en una etapa posterior.",
                )
            )

    for tabla in TABLAS_ESTRUCTURALES_PENDIENTES:
        info = tablas.get(tabla, {})
        if not info.get("existe"):
            diagnostico["hallazgos"].append(
                _hallazgo(
                    severidad="INFO",
                    codigo=f"VENTAS_TABLA_ESTRUCTURAL_PENDIENTE_{tabla.upper()}",
                    titulo=f"Tabla estructural pendiente: {tabla}.",
                    detalle="No se crea en v1. Queda como insumo para el rediseño profesional de Ventas.",
                    accion="Evaluar en Ventas PRO v2/v3 según prioridad.",
                )
            )

    ventas = tablas.get("ventas_comprobantes", {})
    if ventas.get("existe") and ventas.get("registros") == 0:
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="VENTAS_DEMO_SIN_COMPROBANTES",
                titulo="La base no tiene comprobantes de ventas cargados.",
                detalle="Es una buena condición para rediseñar sin arrastrar historia operativa demo.",
                accion="Mantener la etapa como diagnóstico antes de reprocesar ventas.",
            )
        )


def _agregar_hallazgos_codigo(diagnostico: dict[str, Any]) -> None:
    if diagnostico.get("hardcodes_contables"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="VENTAS_CUENTAS_HARDCODEADAS",
                titulo="Ventas usa cuentas contables fijas en código.",
                detalle="Se detectaron cuentas como DEUDORES POR VENTAS, VENTAS o IVA DEBITO FISCAL.",
                accion="Migrar en etapa posterior a parametrización contra Plan Empresa.",
            )
        )

    impactos = diagnostico.get("impactos_directos", {})
    if impactos.get("libro_diario", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="VENTAS_ASIENTO_DIRECTO_LIBRO_DIARIO",
                titulo="Ventas genera asientos directamente en Libro Diario.",
                detalle="La arquitectura PRO debe tender a asiento propuesto y Bandeja antes del Libro Diario.",
                accion="No modificar todavía. Diseñar migración controlada para no duplicar asientos.",
            )
        )

    if impactos.get("cuenta_corriente_clientes", {}).get("detectado"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="VENTAS_IMPACTA_CUENTA_CORRIENTE_CLIENTES",
                titulo="Ventas impacta cuenta corriente de clientes.",
                detalle="Debe conservar trazabilidad, pero distinguir facturas, notas, anticipos y aplicaciones futuras.",
                accion="Revisar junto con Cobranzas antes de cambiar la lógica.",
            )
        )


def _agregar_hallazgos_plan_empresa(diagnostico: dict[str, Any]) -> None:
    plan = diagnostico.get("plan_empresa", {})

    if not plan.get("existe"):
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="VENTAS_PLAN_EMPRESA_NO_EXISTE",
                titulo="No existe plan_cuentas_empresa.",
                detalle="Ventas PRO requiere Plan Empresa como base de parametrización.",
                accion="Resolver Plan Empresa antes de parametrizar Ventas.",
            )
        )
        return

    pendientes = plan.get("usos_pendientes", [])
    usos_sensibles = {
        "deudores_por_ventas",
        "ventas_mercaderias",
        "ventas_servicios",
        "iva_debito_fiscal",
        "anticipos_de_clientes",
    }

    pendientes_sensibles = [uso for uso in pendientes if uso in usos_sensibles]
    if pendientes_sensibles:
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="VENTAS_USOS_CONTABLES_SENSIBLES_NO_DETECTADOS",
                titulo="Hay usos contables sensibles de Ventas sin cuenta detectada en Plan Empresa.",
                detalle=", ".join(pendientes_sensibles),
                accion="En Ventas PRO v2A sugerir parametrización desde Plan Maestro FF/Plan Empresa.",
            )
        )

    pendientes_especiales = [uso for uso in pendientes if uso not in usos_sensibles]
    if pendientes_especiales:
        diagnostico["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="VENTAS_USOS_CONTABLES_ESPECIALES_PENDIENTES",
                titulo="Hay usos contables especiales de Ventas pendientes de parametrización.",
                detalle=", ".join(pendientes_especiales),
                accion="No bloquear v1. Preparar matriz para exportaciones, notas, exentos/no gravados y bienes de uso.",
            )
        )


def _agregar_recomendaciones(diagnostico: dict[str, Any]) -> None:
    diagnostico["recomendaciones"].extend(
        [
            "Mantener services/ventas_service.py sin cambios en v1 para evitar romper la importación vigente.",
            "No generar migraciones todavía: primero confirmar matriz de tipos de venta y cuentas necesarias.",
            "Separar el futuro flujo entre comprobante/importación, clasificación, IVA, cuenta corriente y asiento propuesto.",
            "El tipo de venta debe depender de la operación/concepto/comprobante; el cliente solo puede sugerir defaults.",
            "No incorporar Stock/CMV en esta etapa. Venta de mercaderías debe quedar marcada para diagnóstico futuro de CMV.",
            "No enviar ventas directo al Libro Diario en la arquitectura PRO futura; pasar por Bandeja con trazabilidad.",
            "Preparar Ventas PRO v2A como parametrización asistida de tipos de venta contra Plan Empresa.",
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


# Alias explícitos para facilitar uso desde UI futura sin acoplar nombres internos.
generar_diagnostico_ventas = diagnosticar_ventas
diagnosticar_estado_ventas = diagnosticar_ventas