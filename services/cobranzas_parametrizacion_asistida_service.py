from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


DB_DEFAULT = Path("data/contabilidad_ff.db")

FUENTES_PLAN = [
    {"tabla": "plan_cuentas_empresa", "nombre": "Plan Empresa", "prioridad": 1},
    {"tabla": "plan_cuentas_maestro", "nombre": "Plan Maestro FF", "prioridad": 2},
    {"tabla": "plan_cuentas_maestro_ff", "nombre": "Plan Maestro FF", "prioridad": 2},
]

USOS_CONTABLES_COBRANZAS = {
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
    "anticipos_de_clientes": {
        "nombre": "Anticipos de clientes",
        "patrones": [
            "ANTICIPOS DE CLIENTES",
            "ANTICIPO DE CLIENTES",
            "CLIENTES ANTICIPOS",
        ],
    },
    "saldos_a_favor_clientes": {
        "nombre": "Saldos a favor de clientes",
        "patrones": [
            "SALDOS A FAVOR DE CLIENTES",
            "SALDO A FAVOR DE CLIENTES",
            "CLIENTES SALDOS A FAVOR",
            "SALDO A FAVOR CLIENTES",
        ],
    },
    "retenciones_iva_sufridas": {
        "nombre": "Retenciones IVA sufridas",
        "patrones": [
            "RETENCIONES IVA SUFRIDAS",
            "RETENCION IVA SUFRIDA",
            "RETENCIONES IVA",
            "RETENCION IVA",
            "IVA RETENIDO",
        ],
    },
    "retenciones_iibb_sufridas": {
        "nombre": "Retenciones IIBB sufridas",
        "patrones": [
            "RETENCIONES IIBB SUFRIDAS",
            "RETENCION IIBB SUFRIDA",
            "RETENCIONES IIBB",
            "RETENCION IIBB",
            "INGRESOS BRUTOS RETENIDO",
            "IIBB RETENIDO",
        ],
    },
    "retenciones_ganancias_sufridas": {
        "nombre": "Retenciones Ganancias sufridas",
        "patrones": [
            "RETENCIONES GANANCIAS SUFRIDAS",
            "RETENCION GANANCIAS SUFRIDA",
            "RETENCIONES GANANCIAS",
            "RETENCION GANANCIAS",
            "GANANCIAS RETENIDO",
            "IMPUESTO A LAS GANANCIAS RETENIDO",
        ],
    },
    "diferencias_cobro": {
        "nombre": "Diferencias de cobro",
        "patrones": [
            "DIFERENCIAS DE COBRO",
            "DIFERENCIAS POR COBRANZAS",
            "DIFERENCIAS",
            "REDONDEO",
            "REDONDEOS",
        ],
    },
    "caja_efectivo": {
        "nombre": "Caja / efectivo",
        "patrones": [
            "CAJA",
            "CAJA PRINCIPAL",
            "CAJA GENERAL",
            "EFECTIVO",
        ],
    },
    "bancos": {
        "nombre": "Bancos / cuentas bancarias",
        "patrones": [
            "BANCO",
            "BANCOS",
            "CUENTA CORRIENTE BANCARIA",
            "CUENTA BANCARIA",
            "MACRO",
            "GALICIA",
            "NACION",
            "NACIÓN",
            "SANTANDER",
        ],
    },
    "valores_a_depositar": {
        "nombre": "Valores a depositar",
        "patrones": [
            "VALORES A DEPOSITAR",
            "CHEQUES A DEPOSITAR",
            "CHEQUES RECIBIDOS",
            "VALORES AL COBRO",
        ],
    },
    "tarjetas_billeteras_a_cobrar": {
        "nombre": "Tarjetas, billeteras y cupones a cobrar",
        "patrones": [
            "TARJETAS A COBRAR",
            "CUPONES A COBRAR",
            "CUPONES TARJETAS",
            "BILLETERAS A COBRAR",
            "MERCADO PAGO",
            "MERCADOPAGO",
        ],
    },
    "cuenta_puente_cobranzas": {
        "nombre": "Cuenta puente de cobranzas",
        "patrones": [
            "CUENTA PUENTE COBRANZAS",
            "COBRANZAS A IMPUTAR",
            "COBROS A IDENTIFICAR",
            "COBROS PENDIENTES DE IMPUTACION",
            "COBROS PENDIENTES DE IMPUTACIÓN",
        ],
    },
    "gastos_comisiones_cobro": {
        "nombre": "Gastos, comisiones o descuentos de cobro",
        "patrones": [
            "GASTOS BANCARIOS",
            "COMISIONES BANCARIAS",
            "COMISIONES POR COBRANZAS",
            "GASTOS DE COBRANZA",
            "DESCUENTOS TARJETAS",
        ],
    },
}

PARAMETRIZACIONES_COBRANZAS = [
    {
        "codigo": "COBRANZA_FACTURA_TOTAL",
        "nombre": "Cobranza total imputada a factura",
        "descripcion": "Cancela completamente un comprobante pendiente del cliente.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
        ],
        "alternativas": [
            {
                "rol": "medio_cobro",
                "nombre": "Cuenta de destino según medio de cobro",
                "usos": ["caja_efectivo", "bancos", "valores_a_depositar", "tarjetas_billeteras_a_cobrar"],
                "obligatorio": True,
            }
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": [],
    },
    {
        "codigo": "COBRANZA_FACTURA_PARCIAL",
        "nombre": "Cobranza parcial imputada a factura",
        "descripcion": "Reduce parcialmente el saldo pendiente de un comprobante.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
        ],
        "alternativas": [
            {
                "rol": "medio_cobro",
                "nombre": "Cuenta de destino según medio de cobro",
                "usos": ["caja_efectivo", "bancos", "valores_a_depositar", "tarjetas_billeteras_a_cobrar"],
                "obligatorio": True,
            }
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": [],
    },
    {
        "codigo": "ANTICIPO_CLIENTE",
        "nombre": "Anticipo de cliente",
        "descripcion": "Cobro recibido antes de identificar o devengar la venta. No debe reconocerse como ingreso ordinario.",
        "componentes": [
            {"rol": "pasivo", "uso": "anticipos_de_clientes", "obligatorio": True},
        ],
        "alternativas": [
            {
                "rol": "medio_cobro",
                "nombre": "Cuenta de destino según medio de cobro",
                "usos": ["caja_efectivo", "bancos", "valores_a_depositar", "tarjetas_billeteras_a_cobrar"],
                "obligatorio": True,
            }
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["aplicación futura contra factura", "tratamiento fiscal del comprobante emitido"],
    },
    {
        "codigo": "SALDO_A_FAVOR_CLIENTE",
        "nombre": "Saldo a favor de cliente",
        "descripcion": "Cobro en exceso, nota de crédito o aplicación futura que deja saldo negativo del cliente.",
        "componentes": [
            {"rol": "pasivo", "uso": "saldos_a_favor_clientes", "obligatorio": True},
        ],
        "alternativas": [],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["compensación futura", "devolución al cliente"],
    },
    {
        "codigo": "RETENCION_IVA_SUFRIDA",
        "nombre": "Retención IVA sufrida",
        "descripcion": "Crédito fiscal/impositivo por retención de IVA practicada por el cliente.",
        "componentes": [
            {"rol": "credito_fiscal", "uso": "retenciones_iva_sufridas", "obligatorio": True},
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
        ],
        "alternativas": [],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["vinculación con certificado de retención"],
    },
    {
        "codigo": "RETENCION_IIBB_SUFRIDA",
        "nombre": "Retención IIBB sufrida",
        "descripcion": "Crédito fiscal provincial por retención/percepción sufrida en la cobranza.",
        "componentes": [
            {"rol": "credito_fiscal", "uso": "retenciones_iibb_sufridas", "obligatorio": True},
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
        ],
        "alternativas": [],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["jurisdicción IIBB", "Convenio Multilateral"],
    },
    {
        "codigo": "RETENCION_GANANCIAS_SUFRIDA",
        "nombre": "Retención Ganancias sufrida",
        "descripcion": "Crédito impositivo por retención de Ganancias practicada por el cliente.",
        "componentes": [
            {"rol": "credito_fiscal", "uso": "retenciones_ganancias_sufridas", "obligatorio": True},
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
        ],
        "alternativas": [],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["vinculación con certificado de retención"],
    },
    {
        "codigo": "DIFERENCIA_COBRO",
        "nombre": "Diferencia de cobro",
        "descripcion": "Diferencia por redondeo, gasto bancario, comisión o ajuste menor no imputable a factura.",
        "componentes": [
            {"rol": "resultado_ajuste", "uso": "diferencias_cobro", "obligatorio": True},
            {"rol": "gasto_comision", "uso": "gastos_comisiones_cobro", "obligatorio": False},
        ],
        "alternativas": [],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["umbral de materialidad", "motivo obligatorio"],
    },
    {
        "codigo": "COBRO_NO_IDENTIFICADO",
        "nombre": "Cobro no identificado / pendiente de imputación",
        "descripcion": "Cobro bancario o de tesorería recibido sin identificación inmediata de cliente o factura.",
        "componentes": [
            {"rol": "puente", "uso": "cuenta_puente_cobranzas", "obligatorio": False},
        ],
        "alternativas": [
            {
                "rol": "medio_cobro",
                "nombre": "Cuenta de destino según medio de cobro",
                "usos": ["bancos", "caja_efectivo", "valores_a_depositar", "tarjetas_billeteras_a_cobrar"],
                "obligatorio": True,
            }
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["identificación posterior", "imputación contra cliente/factura"],
    },
    {
        "codigo": "ANULACION_COBRANZA",
        "nombre": "Anulación o reverso de cobranza",
        "descripcion": "Revierte cuenta corriente, tesorería/caja y asiento, conservando trazabilidad.",
        "componentes": [
            {"rol": "cliente", "uso": "deudores_por_ventas", "obligatorio": True},
        ],
        "alternativas": [
            {
                "rol": "medio_cobro_original",
                "nombre": "Cuenta de destino original según medio de cobro",
                "usos": ["caja_efectivo", "bancos", "valores_a_depositar", "tarjetas_billeteras_a_cobrar"],
                "obligatorio": True,
            }
        ],
        "requiere_bandeja": True,
        "requiere_revision_futura": ["bloqueo si está conciliada", "motivo obligatorio", "asiento reverso"],
    },
]


def generar_parametrizacion_asistida_cobranzas(
    db_path: str | Path | None = None,
    limite_sugerencias: int = 5,
) -> dict[str, Any]:
    """
    Cobranzas PRO v2A - Parametrización asistida contra Plan Empresa / Plan Maestro FF.

    Servicio de solo lectura:
    - no crea tablas;
    - no inserta mapeos;
    - no modifica cobranzas;
    - no impacta Caja/Banco/Tesorería;
    - no impacta cuenta corriente de clientes;
    - no genera asientos;
    - no toca la Bandeja.

    El objetivo es proponer una matriz de cuentas para una futura v2B auditada.
    """

    ruta_db = Path(db_path) if db_path is not None else DB_DEFAULT
    resultado: dict[str, Any] = {
        "modulo": "COBRANZAS",
        "etapa": "Cobranzas PRO v2A - Parametrización asistida de cobranzas",
        "estado": "SIN_EVALUAR",
        "db_path": str(ruta_db),
        "solo_lectura": True,
        "fuentes": [],
        "mapeos_contables_empresa": {},
        "parametrizaciones": [],
        "resumen": {},
        "hallazgos": [],
        "recomendaciones": [],
        "no_tocar_v2a": [
            "services/cobranzas_service.py",
            "modulos/cobranzas.py",
            "services/cajas_service.py",
            "services/bancos_operaciones_service.py",
            "services/ventas_service.py",
            "services/asientos_propuestos_service.py",
            "migrations/",
            "Libro Diario",
            "Bandeja",
        ],
        "siguiente_etapa_sugerida": "Cobranzas PRO v2B - Aceptación, edición y desactivación auditada de parametrizaciones de cobranzas",
    }

    if not ruta_db.exists():
        resultado["estado"] = "SIN_BASE"
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="CRITICO",
                codigo="COBRANZAS_PARAM_DB_NO_ENCONTRADA",
                titulo="No se encontró la base de datos.",
                detalle=f"No existe la base SQLite en {ruta_db}.",
                accion="Confirmar ruta de base antes de parametrizar Cobranzas.",
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
                codigo="COBRANZAS_PARAM_SIN_PLAN_CUENTAS",
                titulo="No se encontraron cuentas en Plan Empresa ni Plan Maestro FF.",
                detalle="La parametrización asistida necesita un plan de cuentas activo para sugerir cuentas.",
                accion="Revisar Plan Empresa / Plan Maestro FF antes de continuar.",
            )
        )
        _cerrar_resumen(resultado)
        return resultado

    sugerencias_por_uso = {
        uso: _buscar_sugerencias_para_uso(uso, cuentas, limite_sugerencias)
        for uso in USOS_CONTABLES_COBRANZAS
    }

    for definicion in PARAMETRIZACIONES_COBRANZAS:
        resultado["parametrizaciones"].append(
            _armar_fila_parametrizacion(definicion, sugerencias_por_uso)
        )

    _agregar_hallazgos_parametrizacion(resultado)
    _agregar_recomendaciones(resultado)
    resultado["estado"] = _calcular_estado(resultado)
    _cerrar_resumen(resultado)

    return resultado


def obtener_resumen_parametrizacion_cobranzas(parametrizacion: dict[str, Any]) -> dict[str, Any]:
    if "resumen" in parametrizacion and parametrizacion["resumen"]:
        return parametrizacion["resumen"]

    _cerrar_resumen(parametrizacion)
    return parametrizacion["resumen"]


def exportar_parametrizacion_cobranzas_como_texto(parametrizacion: dict[str, Any]) -> str:
    lineas = [
        f"Modulo: {parametrizacion.get('modulo', 'COBRANZAS')}",
        f"Etapa: {parametrizacion.get('etapa', '')}",
        f"Estado: {parametrizacion.get('estado', '')}",
        "",
        "Parametrizaciones:",
    ]

    for item in parametrizacion.get("parametrizaciones", []):
        lineas.append(
            f"- {item.get('codigo')} | {item.get('estado')} | "
            f"confianza {item.get('confianza_global')}"
        )

        faltantes = item.get("faltantes_obligatorios", []) + item.get("faltantes_alternativas", [])
        if faltantes:
            lineas.append(f"  Faltantes: {', '.join(faltantes)}")

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
    definicion = USOS_CONTABLES_COBRANZAS[uso]
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
            _prioridad_fuente(item.get("fuente")),
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


def _armar_fila_parametrizacion(
    definicion: dict[str, Any],
    sugerencias_por_uso: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    componentes = []
    alternativas = []
    faltantes_obligatorios = []
    faltantes_alternativas = []
    confianzas = []

    for componente in definicion.get("componentes", []):
        uso = componente["uso"]
        sugerencias = sugerencias_por_uso.get(uso, [])
        detectado = bool(sugerencias)
        mejor_confianza = sugerencias[0]["confianza"] if sugerencias else "NULA"

        if componente.get("obligatorio") and not detectado:
            faltantes_obligatorios.append(uso)

        if detectado:
            confianzas.append(mejor_confianza)

        componentes.append(
            {
                "rol": componente["rol"],
                "uso": uso,
                "uso_nombre": USOS_CONTABLES_COBRANZAS[uso]["nombre"],
                "obligatorio": bool(componente.get("obligatorio")),
                "detectado": detectado,
                "confianza": mejor_confianza,
                "sugerencias": sugerencias,
            }
        )

    for grupo in definicion.get("alternativas", []):
        usos = grupo.get("usos", [])
        opciones = []
        detectado_grupo = False

        for uso in usos:
            sugerencias = sugerencias_por_uso.get(uso, [])
            detectado = bool(sugerencias)
            if detectado:
                detectado_grupo = True
                confianzas.append(sugerencias[0]["confianza"])

            opciones.append(
                {
                    "uso": uso,
                    "uso_nombre": USOS_CONTABLES_COBRANZAS[uso]["nombre"],
                    "detectado": detectado,
                    "confianza": sugerencias[0]["confianza"] if sugerencias else "NULA",
                    "sugerencias": sugerencias,
                }
            )

        if grupo.get("obligatorio") and not detectado_grupo:
            faltantes_alternativas.append(grupo["rol"])

        alternativas.append(
            {
                "rol": grupo["rol"],
                "nombre": grupo["nombre"],
                "obligatorio": bool(grupo.get("obligatorio")),
                "detectado": detectado_grupo,
                "opciones": opciones,
            }
        )

    if faltantes_obligatorios or faltantes_alternativas:
        estado = "INCOMPLETO"
        confianza_global = "BAJA"
    elif any(conf == "MEDIA" for conf in confianzas):
        estado = "SUGERIDO_REVISAR"
        confianza_global = "MEDIA"
    else:
        estado = "SUGERIDO"
        confianza_global = "ALTA"

    return {
        "codigo": definicion["codigo"],
        "nombre": definicion["nombre"],
        "descripcion": definicion["descripcion"],
        "estado": estado,
        "confianza_global": confianza_global,
        "componentes": componentes,
        "alternativas": alternativas,
        "faltantes_obligatorios": faltantes_obligatorios,
        "faltantes_alternativas": faltantes_alternativas,
        "requiere_bandeja": definicion["requiere_bandeja"],
        "requiere_revision_futura": definicion["requiere_revision_futura"],
    }


def _agregar_hallazgos_parametrizacion(resultado: dict[str, Any]) -> None:
    fuentes = resultado.get("fuentes", [])

    if not any(f["tabla"] == "plan_cuentas_empresa" and f.get("registros", 0) > 0 for f in fuentes):
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="COBRANZAS_PARAM_PLAN_EMPRESA_SIN_CUENTAS",
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
                codigo="COBRANZAS_PARAM_SIN_MAPEOS_EMPRESA",
                titulo="No hay mapeos contables de empresa registrados.",
                detalle="Es esperable en esta etapa. v2A solo sugiere; v2B deberá aceptar o editar.",
                accion="No crear mapeos automáticamente en v2A.",
            )
        )

    incompletos = [
        item for item in resultado.get("parametrizaciones", [])
        if item.get("faltantes_obligatorios") or item.get("faltantes_alternativas")
    ]
    if incompletos:
        detalle = "; ".join(
            f"{item['codigo']}: "
            f"{', '.join(item.get('faltantes_obligatorios', []) + item.get('faltantes_alternativas', []))}"
            for item in incompletos
        )
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="ADVERTENCIA",
                codigo="COBRANZAS_PARAM_INCOMPLETAS",
                titulo="Hay parametrizaciones de cobranzas incompletas.",
                detalle=detalle,
                accion="Preparar aceptación/edición auditada en v2B antes de tocar el flujo operativo.",
            )
        )

    revisar = [
        item for item in resultado.get("parametrizaciones", [])
        if item.get("estado") == "SUGERIDO_REVISAR"
    ]
    if revisar:
        detalle = ", ".join(item["codigo"] for item in revisar)
        resultado["hallazgos"].append(
            _hallazgo(
                severidad="INFO",
                codigo="COBRANZAS_PARAM_REQUIERE_REVISION",
                titulo="Hay parametrizaciones con confianza media.",
                detalle=detalle,
                accion="Revisar manualmente antes de aceptar en v2B.",
            )
        )


def _agregar_recomendaciones(resultado: dict[str, Any]) -> None:
    resultado["recomendaciones"].extend(
        [
            "Mantener v2A como matriz de sugerencias de solo lectura.",
            "No modificar services/cobranzas_service.py hasta tener aceptación auditada de parametrizaciones.",
            "Las cuentas operativas deben provenir del Plan Empresa; el Plan Maestro FF solo debe ayudar como fuente madre/modelo.",
            "Separar cancelación de factura, anticipo, saldo a favor, retenciones y diferencias de cobro.",
            "No tocar Caja/Banco/Tesorería en v2A; solo diagnosticar cuentas sugeridas.",
            "No crear tablas nuevas en v2A.",
            "La salida futura debe ir a asiento propuesto y Bandeja antes del Libro Diario.",
            "Retenciones sufridas deben parametrizarse por impuesto y, en IIBB, luego por jurisdicción si corresponde.",
            "Cobros no identificados deben tratarse como cuenta puente hasta su aplicación posterior.",
        ]
    )


def _calcular_estado(resultado: dict[str, Any]) -> str:
    hallazgos = resultado.get("hallazgos", [])

    if any(h.get("severidad") == "CRITICO" for h in hallazgos):
        return "CRITICO"

    if any(
        item.get("faltantes_obligatorios") or item.get("faltantes_alternativas")
        for item in resultado.get("parametrizaciones", [])
    ):
        return "REQUIERE_PARAMETRIZACION"

    if any(h.get("severidad") == "ADVERTENCIA" for h in hallazgos):
        return "REQUIERE_REVISION"

    return "OK_PARAMETRIZACION_ASISTIDA"


def _cerrar_resumen(resultado: dict[str, Any]) -> None:
    items = resultado.get("parametrizaciones", [])
    hallazgos = resultado.get("hallazgos", [])

    resultado["resumen"] = {
        "estado": resultado.get("estado"),
        "parametrizaciones_total": len(items),
        "parametrizaciones_sugeridas": sum(1 for item in items if item.get("estado") == "SUGERIDO"),
        "parametrizaciones_revisar": sum(1 for item in items if item.get("estado") == "SUGERIDO_REVISAR"),
        "parametrizaciones_incompletas": sum(1 for item in items if item.get("estado") == "INCOMPLETO"),
        "parametrizaciones_incompletas_codigos": [
            item.get("codigo") for item in items if item.get("estado") == "INCOMPLETO"
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
generar_matriz_parametrizacion_cobranzas = generar_parametrizacion_asistida_cobranzas
diagnosticar_parametrizacion_cobranzas = generar_parametrizacion_asistida_cobranzas
