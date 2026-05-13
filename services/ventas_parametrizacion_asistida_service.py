from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


DB_DEFAULT = Path("data/contabilidad_ff.db")

FUENTES_PLAN = [
    {
        "tabla": "plan_cuentas_empresa",
        "nombre": "Plan Empresa",
        "prioridad": 1,
    },
    {
        "tabla": "plan_cuentas_maestro",
        "nombre": "Plan Maestro FF",
        "prioridad": 2,
    },
    {
        "tabla": "plan_cuentas_maestro_ff",
        "nombre": "Plan Maestro FF",
        "prioridad": 2,
    },
]

USOS_CONTABLES_VENTAS = {
    "deudores_por_ventas": {
        "nombre": "Deudores por ventas / clientes",
        "patrones": [
            "DEUDORES POR VENTAS",
            "CLIENTES",
            "CUENTAS A COBRAR",
            "CREDITOS POR VENTAS",
            "CRÉDITOS POR VENTAS",
        ],
    },
    "deudores_exterior": {
        "nombre": "Deudores del exterior",
        "patrones": [
            "CLIENTES DEL EXTERIOR",
            "DEUDORES DEL EXTERIOR",
            "CREDITOS POR VENTAS AL EXTERIOR",
            "CRÉDITOS POR VENTAS AL EXTERIOR",
            "DEUDORES EXPORTACIONES",
        ],
    },
    "ventas_mercaderias": {
        "nombre": "Ventas de mercaderías",
        "patrones": [
            "VENTAS DE MERCADERIAS",
            "VENTAS DE MERCADERÍAS",
            "VENTA DE MERCADERIAS",
            "VENTA DE MERCADERÍAS",
            "VENTAS",
        ],
    },
    "ventas_servicios": {
        "nombre": "Ventas de servicios",
        "patrones": [
            "VENTAS DE SERVICIOS",
            "SERVICIOS PRESTADOS",
            "INGRESOS POR SERVICIOS",
            "HONORARIOS",
        ],
    },
    "ventas_exentas": {
        "nombre": "Ventas exentas",
        "patrones": [
            "VENTAS EXENTAS",
            "INGRESOS EXENTOS",
            "OPERACIONES EXENTAS",
        ],
    },
    "ventas_no_gravadas": {
        "nombre": "Ventas no gravadas",
        "patrones": [
            "VENTAS NO GRAVADAS",
            "INGRESOS NO GRAVADOS",
            "OPERACIONES NO GRAVADAS",
            "NO GRAVADO",
        ],
    },
    "exportacion_bienes": {
        "nombre": "Exportación de bienes",
        "patrones": [
            "EXPORTACION DE BIENES",
            "EXPORTACIÓN DE BIENES",
            "VENTAS AL EXTERIOR",
            "VENTAS DE EXPORTACION",
            "VENTAS DE EXPORTACIÓN",
        ],
    },
    "exportacion_servicios": {
        "nombre": "Exportación de servicios",
        "patrones": [
            "EXPORTACION DE SERVICIOS",
            "EXPORTACIÓN DE SERVICIOS",
            "SERVICIOS AL EXTERIOR",
            "SERVICIOS EXPORTACION",
            "SERVICIOS EXPORTACIÓN",
        ],
    },
    "iva_debito_fiscal": {
        "nombre": "IVA débito fiscal",
        "patrones": [
            "IVA DEBITO FISCAL",
            "IVA DÉBITO FISCAL",
            "IVA DEBITO",
            "IVA DÉBITO",
        ],
    },
    "anticipos_de_clientes": {
        "nombre": "Anticipos de clientes",
        "patrones": [
            "ANTICIPOS DE CLIENTES",
            "ANTICIPO DE CLIENTES",
            "CLIENTES ANTICIPOS",
        ],
    },
    "clientes_saldos_a_favor": {
        "nombre": "Saldos a favor de clientes",
        "patrones": [
            "SALDOS A FAVOR DE CLIENTES",
            "CLIENTES SALDOS A FAVOR",
            "SALDO A FAVOR CLIENTES",
        ],
    },
    "resultado_venta_bienes_uso": {
        "nombre": "Resultado por venta de bienes de uso",
        "patrones": [
            "RESULTADO VENTA BIENES DE USO",
            "RESULTADO POR VENTA DE BIENES DE USO",
            "VENTA BIENES DE USO",
            "BIENES DE USO",
        ],
    },
    "ventas_devoluciones_bonificaciones": {
        "nombre": "Devoluciones, bonificaciones o descuentos sobre ventas",
        "patrones": [
            "DEVOLUCIONES SOBRE VENTAS",
            "BONIFICACIONES SOBRE VENTAS",
            "DESCUENTOS SOBRE VENTAS",
            "NOTAS DE CREDITO",
            "NOTAS DE CRÉDITO",
            "DEVOLUCIONES",
            "BONIFICACIONES",
        ],
    },
    "ajustes_ventas_intereses_diferencias": {
        "nombre": "Ajustes, intereses, recargos o diferencias de ventas",
        "patrones": [
            "INTERESES",
            "RECARGOS",
            "DIFERENCIAS",
            "AJUSTES DE VENTAS",
            "DIFERENCIAS DE CAMBIO",
        ],
    },
}

TIPOS_VENTA_PARAMETRIZABLES = [
    {
        "codigo": "VENTA_MERCADERIAS",
        "nombre": "Venta de mercaderías",
        "descripcion": "Venta ordinaria de bienes de cambio. No dispara CMV en esta etapa.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "ingreso", "uso": "ventas_mercaderias", "obligatorio": True},
            {"rol": "iva", "uso": "iva_debito_fiscal", "obligatorio": True},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["CMV / stock"],
    },
    {
        "codigo": "VENTA_SERVICIOS",
        "nombre": "Venta de servicios",
        "descripcion": "Ingreso por prestación de servicios.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "ingreso", "uso": "ventas_servicios", "obligatorio": True},
            {"rol": "iva", "uso": "iva_debito_fiscal", "obligatorio": True},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": [],
    },
    {
        "codigo": "VENTA_BIEN_USO",
        "nombre": "Venta de bienes de uso",
        "descripcion": "No debe mezclarse con ventas ordinarias. Requiere tratamiento de baja de activo y resultado.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "resultado", "uso": "resultado_venta_bienes_uso", "obligatorio": True},
            {"rol": "iva", "uso": "iva_debito_fiscal", "obligatorio": False, "condicional": "si la operación está gravada"},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["baja de activo", "valor residual", "resultado por venta"],
    },
    {
        "codigo": "VENTA_EXENTA",
        "nombre": "Venta exenta",
        "descripcion": "Ingreso sin IVA débito fiscal, con exposición fiscal separada.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "ingreso", "uso": "ventas_exentas", "obligatorio": True},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": [],
    },
    {
        "codigo": "VENTA_NO_GRAVADA",
        "nombre": "Venta no gravada",
        "descripcion": "Ingreso no alcanzado por IVA. Debe separarse de ventas exentas.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "ingreso", "uso": "ventas_no_gravadas", "obligatorio": True},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": [],
    },
    {
        "codigo": "EXPORTACION_BIENES",
        "nombre": "Exportación de bienes",
        "descripcion": "Venta al exterior separada de ventas locales.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_exterior", "obligatorio": True},
            {"rol": "ingreso", "uso": "exportacion_bienes", "obligatorio": True},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["tratamiento fiscal exportaciones", "moneda extranjera"],
    },
    {
        "codigo": "EXPORTACION_SERVICIOS",
        "nombre": "Exportación de servicios",
        "descripcion": "Servicios prestados al exterior, separados de ventas locales.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_exterior", "obligatorio": True},
            {"rol": "ingreso", "uso": "exportacion_servicios", "obligatorio": True},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["tratamiento fiscal exportaciones", "moneda extranjera"],
    },
    {
        "codigo": "NOTA_CREDITO",
        "nombre": "Nota de crédito",
        "descripcion": "Reduce o revierte venta, IVA débito y cuenta corriente según comprobante vinculado.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "contracuenta", "uso": "ventas_devoluciones_bonificaciones", "obligatorio": True},
            {"rol": "iva", "uso": "iva_debito_fiscal", "obligatorio": False, "condicional": "si el comprobante original estaba gravado"},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["vinculación con comprobante original"],
    },
    {
        "codigo": "NOTA_DEBITO",
        "nombre": "Nota de débito",
        "descripcion": "Aumenta la deuda del cliente por ajustes, intereses, recargos o diferencias.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
            {"rol": "ingreso_ajuste", "uso": "ajustes_ventas_intereses_diferencias", "obligatorio": True},
            {"rol": "iva", "uso": "iva_debito_fiscal", "obligatorio": False, "condicional": "según concepto facturado"},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["clasificación del concepto de ajuste"],
    },
    {
        "codigo": "ANTICIPO_CLIENTE",
        "nombre": "Anticipo de cliente",
        "descripcion": "No debe reconocerse como venta devengada hasta su aplicación. Debe tratarse como pasivo o saldo a favor.",
        "componentes": [
            {"rol": "pasivo", "uso": "anticipos_de_clientes", "obligatorio": True},
            {"rol": "saldo_a_favor", "uso": "clientes_saldos_a_favor", "obligatorio": False},
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["aplicación futura contra factura", "tratamiento fiscal del comprobante emitido"],
    },
]


def generar_parametrizacion_asistida_ventas(
    db_path: str | Path | None = None,
    limite_sugerencias: int = 5,
) -> dict[str, Any]:
    """
    Ventas PRO v2A - Parametrización asistida de tipos de venta contra Plan Empresa.

    Servicio de solo lectura:
    - no crea tablas;
    - no inserta mapeos;
    - no modifica ventas;
    - no genera asientos;
    - no impacta IVA ni cuenta corriente;
    - no reemplaza el flujo vigente de ventas.

    Devuelve una matriz de tipos de venta y cuentas sugeridas para decidir la v2B.
    """

    ruta_db = Path(db_path) if db_path is not None else DB_DEFAULT
    resultado: dict[str, Any] = {
        "modulo": "VENTAS",
        "etapa": "Ventas PRO v2A - Parametrización asistida de tipos de venta contra Plan Empresa",
        "estado": "SIN_EVALUAR",
        "db_path": str(ruta_db),
        "solo_lectura": True,
        "fuentes": [],
        "mapeos_contables_empresa": {},
        "tipos_venta": [],
        "resumen": {},
        "hallazgos": [],
        "recomendaciones": [],
        "no_tocar_v2a": [
            "services/ventas_service.py",
            "modulos/ventas.py",
            "services/iva_service.py",
            "services/cobranzas_service.py",
            "services/asientos_propuestos_service.py",
            "migrations/",
            "stock",
            "CMV",
        ],
        "siguiente_etapa_sugerida": "Ventas PRO v2B - Aceptación, edición y desactivación auditada de parametrizaciones de ventas",
    }

    if not ruta_db.exists():
        resultado["estado"] = "SIN_BASE"
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="VENTAS_PARAM_DB_NO_ENCONTRADA",
                titulo="No se encontró la base de datos.",
                detalle=f"No existe la base SQLite en {ruta_db}.",
                accion="Confirmar ruta de base antes de parametrizar Ventas.",
            )
        )
        _cerrar_resumen(resultado)
        return resultado

    with sqlite3.connect(ruta_db) as conn:
        conn.row_factory = sqlite3.Row

        fuentes = _leer_fuentes_plan(conn)
        resultado["fuentes"] = [
            {
                "tabla": fuente["tabla"],
                "nombre": fuente["nombre"],
                "existe": fuente["existe"],
                "registros": len(fuente["cuentas"]),
            }
            for fuente in fuentes
        ]
        resultado["mapeos_contables_empresa"] = _diagnosticar_mapeos_contables_empresa(conn)

    cuentas = [cuenta for fuente in fuentes for cuenta in fuente["cuentas"]]

    if not cuentas:
        resultado["estado"] = "CRITICO"
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="VENTAS_PARAM_SIN_PLAN_CUENTAS",
                titulo="No se encontraron cuentas en Plan Empresa ni Plan Maestro FF.",
                detalle="La parametrización asistida necesita un plan de cuentas activo para sugerir cuentas.",
                accion="Revisar seed/migración del Plan Maestro FF y Plan Empresa antes de continuar.",
            )
        )
        _cerrar_resumen(resultado)
        return resultado

    sugerencias_por_uso = {
        uso: _buscar_sugerencias_para_uso(uso, cuentas, limite_sugerencias)
        for uso in USOS_CONTABLES_VENTAS
    }

    for tipo in TIPOS_VENTA_PARAMETRIZABLES:
        resultado["tipos_venta"].append(
            _armar_fila_tipo_venta(tipo, sugerencias_por_uso)
        )

    _agregar_hallazgos_parametrizacion(resultado)
    _agregar_recomendaciones(resultado)
    resultado["estado"] = _calcular_estado(resultado)
    _cerrar_resumen(resultado)

    return resultado


def obtener_resumen_parametrizacion_ventas(parametrizacion: dict[str, Any]) -> dict[str, Any]:
    """
    Vista compacta para consola, tests o futura UI.
    """

    if "resumen" in parametrizacion and parametrizacion["resumen"]:
        return parametrizacion["resumen"]

    _cerrar_resumen(parametrizacion)
    return parametrizacion["resumen"]


def exportar_parametrizacion_ventas_como_texto(parametrizacion: dict[str, Any]) -> str:
    """
    Exportación simple en texto plano para revisión contable/técnica.
    """

    lineas = [
        f"Modulo: {parametrizacion.get('modulo', 'VENTAS')}",
        f"Etapa: {parametrizacion.get('etapa', '')}",
        f"Estado: {parametrizacion.get('estado', '')}",
        "",
        "Tipos de venta:",
    ]

    for tipo in parametrizacion.get("tipos_venta", []):
        lineas.append(
            f"- {tipo.get('codigo')} | {tipo.get('estado')} | "
            f"confianza {tipo.get('confianza_global')}"
        )
        faltantes = tipo.get("faltantes_obligatorios", [])
        if faltantes:
            lineas.append(f"  Faltantes obligatorios: {', '.join(faltantes)}")

    lineas.append("")
    lineas.append("Hallazgos:")
    for hallazgo in parametrizacion.get("hallazgos", []):
        lineas.append(
            f"- [{hallazgo.get('severidad')}] {hallazgo.get('codigo')}: "
            f"{hallazgo.get('titulo')} {hallazgo.get('detalle')}"
        )

    lineas.append("")
    lineas.append("Recomendaciones:")
    for recomendacion in parametrizacion.get("recomendaciones", []):
        lineas.append(f"- {recomendacion}")

    return "\n".join(lineas)


def _leer_fuentes_plan(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    fuentes = []

    for fuente_def in FUENTES_PLAN:
        tabla = fuente_def["tabla"]
        existe = _tabla_existe(conn, tabla)
        cuentas = _leer_cuentas(conn, tabla, fuente_def) if existe else []

        fuentes.append(
            {
                **fuente_def,
                "existe": existe,
                "cuentas": cuentas,
            }
        )

    return fuentes


def _leer_cuentas(
    conn: sqlite3.Connection,
    tabla: str,
    fuente_def: dict[str, Any],
) -> list[dict[str, Any]]:
    columnas = _columnas_tabla(conn, tabla)
    if not columnas:
        return []

    columnas_sql = ", ".join(f'"{col}"' for col in columnas)

    try:
        filas = conn.execute(f'SELECT {columnas_sql} FROM "{tabla}"').fetchall()
    except sqlite3.Error:
        return []

    cuentas = []
    for fila in filas:
        cuenta = {col: fila[col] for col in columnas}
        if not _cuenta_activa(cuenta):
            continue

        texto = _texto_cuenta(cuenta, columnas)
        cuentas.append(
            {
                "fuente": fuente_def["nombre"],
                "tabla": tabla,
                "prioridad_fuente": fuente_def["prioridad"],
                "id": cuenta.get("id"),
                "codigo": _primer_valor(cuenta, ["codigo", "codigo_cuenta", "cuenta_codigo", "numero", "nro_cuenta"]),
                "nombre": _primer_valor(cuenta, ["nombre", "cuenta", "descripcion", "denominacion"]),
                "rubro": _primer_valor(cuenta, ["rubro", "subrubro", "elemento"]),
                "uso_operativo": _primer_valor(cuenta, ["uso_operativo", "uso_contable", "comportamiento", "tipo_uso"]),
                "texto_busqueda": texto,
            }
        )

    return cuentas


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


def _columnas_tabla(conn: sqlite3.Connection, tabla: str) -> list[str]:
    try:
        filas = conn.execute(f'PRAGMA table_info("{tabla}")').fetchall()
    except sqlite3.Error:
        return []

    return [str(fila["name"] if isinstance(fila, sqlite3.Row) else fila[1]) for fila in filas]


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


def _texto_cuenta(cuenta: dict[str, Any], columnas: list[str]) -> str:
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
    cols = [col for col in preferidas if col in columnas]
    if not cols:
        cols = columnas

    return " | ".join(str(cuenta.get(col, "") or "") for col in cols)


def _primer_valor(cuenta: dict[str, Any], columnas: list[str]) -> Any:
    for col in columnas:
        valor = cuenta.get(col)
        if valor not in (None, ""):
            return valor
    return ""


def _diagnosticar_mapeos_contables_empresa(conn: sqlite3.Connection) -> dict[str, Any]:
    tabla = "mapeos_contables_empresa"
    if not _tabla_existe(conn, tabla):
        return {
            "existe": False,
            "registros": 0,
            "mensaje": "No existe tabla de mapeos contables de empresa.",
        }

    try:
        total = conn.execute(f'SELECT COUNT(*) AS cantidad FROM "{tabla}"').fetchone()["cantidad"]
    except sqlite3.Error:
        total = 0

    return {
        "existe": True,
        "registros": int(total),
        "mensaje": "Solo lectura. No se crean ni actualizan mapeos en v2A.",
    }


def _buscar_sugerencias_para_uso(
    uso: str,
    cuentas: list[dict[str, Any]],
    limite: int,
) -> list[dict[str, Any]]:
    definicion = USOS_CONTABLES_VENTAS[uso]
    patrones = definicion["patrones"]

    candidatas = []
    vistos = set()

    for cuenta in cuentas:
        score, patron = _puntuar_cuenta(cuenta, patrones)
        if score <= 0:
            continue

        clave = (cuenta.get("tabla"), cuenta.get("id"), cuenta.get("codigo"), cuenta.get("nombre"))
        if clave in vistos:
            continue
        vistos.add(clave)

        candidatas.append(
            {
                "uso": uso,
                "uso_nombre": definicion["nombre"],
                "fuente": cuenta.get("fuente"),
                "tabla": cuenta.get("tabla"),
                "id": cuenta.get("id"),
                "codigo": cuenta.get("codigo"),
                "nombre": cuenta.get("nombre"),
                "score": score,
                "confianza": _confianza(score),
                "patron_detectado": patron,
            }
        )

    candidatas.sort(
        key=lambda item: (
            item["score"],
            -1 * _prioridad_fuente(item.get("fuente")),
            str(item.get("codigo") or ""),
        ),
        reverse=True,
    )
    return candidatas[:limite]


def _prioridad_fuente(nombre_fuente: str | None) -> int:
    if nombre_fuente == "Plan Empresa":
        return 2
    if nombre_fuente == "Plan Maestro FF":
        return 1
    return 0


def _puntuar_cuenta(cuenta: dict[str, Any], patrones: list[str]) -> tuple[int, str]:
    texto = _normalizar(cuenta.get("texto_busqueda", ""))
    nombre = _normalizar(cuenta.get("nombre", ""))
    codigo = _normalizar(cuenta.get("codigo", ""))
    uso_operativo = _normalizar(cuenta.get("uso_operativo", ""))

    mejor_score = 0
    mejor_patron = ""

    for patron_original in patrones:
        patron = _normalizar(patron_original)
        if not patron:
            continue

        score = 0
        if patron == nombre:
            score = 100
        elif patron == codigo:
            score = 95
        elif patron == uso_operativo:
            score = 92
        elif patron in nombre:
            score = 88
        elif patron in texto:
            score = 80
        else:
            tokens = [tok for tok in patron.split() if len(tok) >= 4]
            if tokens and all(tok in texto for tok in tokens):
                score = 58

        if score > mejor_score:
            mejor_score = score
            mejor_patron = patron_original

    return mejor_score, mejor_patron


def _normalizar(valor: Any) -> str:
    texto = str(valor or "").strip().upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _confianza(score: int) -> str:
    if score >= 85:
        return "ALTA"
    if score >= 58:
        return "MEDIA"
    if score > 0:
        return "BAJA"
    return "NULA"


def _armar_fila_tipo_venta(
    tipo: dict[str, Any],
    sugerencias_por_uso: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    componentes = []
    faltantes_obligatorios = []
    faltantes_condicionales = []
    confianzas = []

    for componente in tipo["componentes"]:
        uso = componente["uso"]
        sugerencias = sugerencias_por_uso.get(uso, [])
        detectado = bool(sugerencias)
        mejor_confianza = sugerencias[0]["confianza"] if sugerencias else "NULA"

        if componente.get("obligatorio") and not detectado:
            faltantes_obligatorios.append(uso)
        elif componente.get("condicional") and not detectado:
            faltantes_condicionales.append(uso)

        if detectado:
            confianzas.append(mejor_confianza)

        componentes.append(
            {
                "rol": componente["rol"],
                "uso": uso,
                "uso_nombre": USOS_CONTABLES_VENTAS[uso]["nombre"],
                "obligatorio": bool(componente.get("obligatorio")),
                "condicional": componente.get("condicional", ""),
                "detectado": detectado,
                "confianza": mejor_confianza,
                "sugerencias": sugerencias,
            }
        )

    if faltantes_obligatorios:
        estado = "INCOMPLETO"
        confianza_global = "BAJA"
    elif any(conf == "MEDIA" for conf in confianzas):
        estado = "SUGERIDO_REVISAR"
        confianza_global = "MEDIA"
    else:
        estado = "SUGERIDO"
        confianza_global = "ALTA"

    return {
        "codigo": tipo["codigo"],
        "nombre": tipo["nombre"],
        "descripcion": tipo["descripcion"],
        "estado": estado,
        "confianza_global": confianza_global,
        "componentes": componentes,
        "faltantes_obligatorios": faltantes_obligatorios,
        "faltantes_condicionales": faltantes_condicionales,
        "requiere_bandeja": tipo["requiere_bandeja"],
        "requiere_revision_futura": tipo["requiere_revision_futura"],
    }


def _agregar_hallazgos_parametrizacion(resultado: dict[str, Any]) -> None:
    fuentes_existentes = [fuente for fuente in resultado.get("fuentes", []) if fuente.get("existe")]
    if not any(fuente.get("tabla") == "plan_cuentas_empresa" and fuente.get("registros", 0) > 0 for fuente in fuentes_existentes):
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="VENTAS_PARAM_PLAN_EMPRESA_SIN_CUENTAS",
                titulo="No se detectaron cuentas activas en Plan Empresa.",
                detalle="La sugerencia puede depender del Plan Maestro FF, pero la parametrización operativa debe quedar por empresa.",
                accion="Revisar Plan Empresa antes de aceptar parametrizaciones en v2B.",
            )
        )

    mapeos = resultado.get("mapeos_contables_empresa", {})
    if mapeos.get("existe") and mapeos.get("registros", 0) == 0:
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="VENTAS_PARAM_SIN_MAPEOS_EMPRESA",
                titulo="No hay mapeos contables de empresa registrados.",
                detalle="Es esperable en esta etapa. v2A solo sugiere; v2B deberá aceptar o editar.",
                accion="No crear mapeos automáticamente en v2A.",
            )
        )

    incompletos = [
        tipo for tipo in resultado.get("tipos_venta", [])
        if tipo.get("faltantes_obligatorios")
    ]
    if incompletos:
        detalle = "; ".join(
            f"{tipo['codigo']}: {', '.join(tipo['faltantes_obligatorios'])}"
            for tipo in incompletos
        )
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="VENTAS_PARAM_TIPOS_INCOMPLETOS",
                titulo="Hay tipos de venta sin cuentas obligatorias sugeridas.",
                detalle=detalle,
                accion="Preparar parametrización asistida y decisión de usuario en v2B.",
            )
        )

    condicionales = [
        tipo for tipo in resultado.get("tipos_venta", [])
        if tipo.get("faltantes_condicionales")
    ]
    if condicionales:
        detalle = "; ".join(
            f"{tipo['codigo']}: {', '.join(tipo['faltantes_condicionales'])}"
            for tipo in condicionales
        )
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="VENTAS_PARAM_CONDICIONALES_PENDIENTES",
                titulo="Hay cuentas condicionales no detectadas.",
                detalle=detalle,
                accion="No bloquea v2A. Revisar al implementar reglas por comprobante/concepto.",
            )
        )


def _agregar_recomendaciones(resultado: dict[str, Any]) -> None:
    resultado["recomendaciones"].extend(
        [
            "Mantener v2A como matriz de sugerencias de solo lectura.",
            "No modificar services/ventas_service.py hasta tener aceptación auditada de parametrizaciones.",
            "La cuenta sugerida debe provenir primero del Plan Empresa; el Plan Maestro FF solo debe ayudar como fuente madre/modelo.",
            "El tipo de venta debe definirse por operación, comprobante y concepto vendido; el cliente solo puede sugerir defaults.",
            "No incorporar CMV/Stock todavía: venta de mercaderías solo queda marcada para diagnóstico futuro.",
            "Anticipos de clientes no deben tratarse como venta devengada sin aplicación a comprobante.",
            "Notas de crédito y débito deben vincularse a reglas y comprobante original en una etapa posterior.",
            "La salida futura debe ir a asiento propuesto y Bandeja, no directo a Libro Diario.",
        ]
    )


def _calcular_estado(resultado: dict[str, Any]) -> str:
    hallazgos = resultado.get("hallazgos", [])

    if any(h.get("severidad") == "CRITICO" for h in hallazgos):
        return "CRITICO"

    if any(tipo.get("faltantes_obligatorios") for tipo in resultado.get("tipos_venta", [])):
        return "REQUIERE_PARAMETRIZACION"

    if any(h.get("severidad") == "ADVERTENCIA" for h in hallazgos):
        return "REQUIERE_REVISION"

    return "OK_PARAMETRIZACION_ASISTIDA"


def _cerrar_resumen(resultado: dict[str, Any]) -> None:
    tipos = resultado.get("tipos_venta", [])
    hallazgos = resultado.get("hallazgos", [])

    resultado["resumen"] = {
        "estado": resultado.get("estado"),
        "tipos_venta_total": len(tipos),
        "tipos_sugeridos": sum(1 for tipo in tipos if tipo.get("estado") == "SUGERIDO"),
        "tipos_revisar": sum(1 for tipo in tipos if tipo.get("estado") == "SUGERIDO_REVISAR"),
        "tipos_incompletos": sum(1 for tipo in tipos if tipo.get("estado") == "INCOMPLETO"),
        "tipos_incompletos_codigos": [
            tipo.get("codigo") for tipo in tipos if tipo.get("estado") == "INCOMPLETO"
        ],
        "hallazgos_criticos": sum(1 for h in hallazgos if h.get("severidad") == "CRITICO"),
        "hallazgos_advertencia": sum(1 for h in hallazgos if h.get("severidad") == "ADVERTENCIA"),
        "hallazgos_info": sum(1 for h in hallazgos if h.get("severidad") == "INFO"),
        "mapeos_contables_empresa": resultado.get("mapeos_contables_empresa", {}),
        "fuentes": resultado.get("fuentes", []),
    }


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


# Alias claros para futura UI sin acoplarse al nombre interno.
generar_matriz_parametrizacion_ventas = generar_parametrizacion_asistida_ventas
diagnosticar_parametrizacion_ventas = generar_parametrizacion_asistida_ventas
