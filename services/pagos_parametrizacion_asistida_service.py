from __future__ import annotations

import importlib
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ESTADO_OK = "OK"
ESTADO_REQUIERE_PARAMETRIZACION = "REQUIERE_PARAMETRIZACION"
ESTADO_REQUIERE_REVISION = "REQUIERE_REVISION"
ESTADO_CRITICO = "CRITICO"

ESTADO_PARAM_SUGERIDA = "SUGERIDA"
ESTADO_PARAM_INCOMPLETA = "INCOMPLETA"
ESTADO_PARAM_A_REVISAR = "A_REVISAR"
ESTADO_PARAM_INFORMATIVA = "INFORMATIVA"

SEVERIDAD_INFO = "INFO"
SEVERIDAD_ADVERTENCIA = "ADVERTENCIA"
SEVERIDAD_CRITICA = "CRITICA"

TABLAS_PLAN_CANDIDATAS = [
    "plan_cuentas_empresa",
    "cuentas_contables_empresa",
    "plan_cuentas",
    "cuentas_contables",
    "plan_cuentas_maestro",
]

COLUMNAS_NOMBRE_CUENTA = [
    "nombre",
    "cuenta",
    "descripcion",
    "nombre_cuenta",
    "denominacion",
]

COLUMNAS_CODIGO_CUENTA = [
    "codigo",
    "codigo_cuenta",
    "codigo_contable",
]

COLUMNAS_USO_OPERATIVO = [
    "uso_operativo",
    "uso_operativo_contable",
    "uso_sistema",
    "uso_tecnico",
    "evento_operativo",
    "evento_operativo_contable",
]

COLUMNAS_HABILITADO = [
    "activo",
    "activa",
    "habilitado",
    "habilitada",
    "vigente",
]

PARAMETRIZACIONES_REQUERIDAS = [
    {
        "codigo": "PROVEEDORES",
        "nombre": "Deuda con proveedores por facturas pendientes",
        "naturaleza": "PASIVO",
        "tipo": "CUENTA_CONTABLE",
        "requiere_cuenta": True,
        "criticidad": "ALTA",
        "impacto": "Cuenta corriente proveedores, cancelacion de facturas y asiento futuro.",
        "keywords_fuertes": ["proveedores", "deudas comerciales", "cuentas por pagar", "acreedores comerciales"],
        "keywords_debiles": ["deudas", "comerciales", "acreedores"],
    },
    {
        "codigo": "ANTICIPO_A_PROVEEDOR",
        "nombre": "Anticipos entregados a proveedores",
        "naturaleza": "ACTIVO",
        "tipo": "CUENTA_CONTABLE",
        "requiere_cuenta": True,
        "criticidad": "ALTA",
        "impacto": "Pago sin factura; no debe registrarse como gasto ni cancelar deuda inexistente.",
        "keywords_fuertes": ["anticipos a proveedores", "anticipo a proveedores", "anticipos proveedores", "proveedores anticipos"],
        "keywords_debiles": ["anticipos", "otros creditos"],
    },
    {
        "codigo": "PAGO_CAJA",
        "nombre": "Salida de fondos por Caja",
        "naturaleza": "ACTIVO",
        "tipo": "MEDIO_PAGO",
        "requiere_cuenta": True,
        "criticidad": "MEDIA",
        "impacto": "Pagos en efectivo con movimiento automatico o futuro de Caja.",
        "keywords_fuertes": ["caja", "caja principal", "caja general", "fondos fijos"],
        "keywords_debiles": ["efectivo", "disponibilidades"],
    },
    {
        "codigo": "PAGO_BANCO",
        "nombre": "Salida de fondos por Banco/Tesoreria",
        "naturaleza": "ACTIVO",
        "tipo": "MEDIO_PAGO",
        "requiere_cuenta": True,
        "criticidad": "MEDIA",
        "impacto": "Pagos por transferencia, debito, cheque, eCheq, billetera o tarjeta.",
        "keywords_fuertes": ["banco", "bancos", "cuenta corriente bancaria", "macro", "galicia", "santander", "nacion"],
        "keywords_debiles": ["disponibilidades", "tesoreria", "valores", "billetera"],
    },
    {
        "codigo": "RETENCION_IIBB",
        "nombre": "Retenciones IIBB practicadas a proveedores",
        "naturaleza": "PASIVO_FISCAL",
        "tipo": "RETENCION",
        "requiere_cuenta": True,
        "criticidad": "ALTA",
        "impacto": "Importe retenido a ingresar/informar segun jurisdiccion.",
        "keywords_fuertes": ["retenciones iibb a depositar", "retencion iibb a depositar", "retenciones ingresos brutos", "retencion ingresos brutos"],
        "keywords_debiles": ["iibb", "ingresos brutos", "retenciones", "cargas fiscales"],
    },
    {
        "codigo": "RETENCION_GANANCIAS",
        "nombre": "Retenciones Ganancias practicadas a proveedores",
        "naturaleza": "PASIVO_FISCAL",
        "tipo": "RETENCION",
        "requiere_cuenta": True,
        "criticidad": "ALTA",
        "impacto": "Retencion nacional practicada en el pago o puesta a disposicion.",
        "keywords_fuertes": ["retenciones ganancias a depositar", "retencion ganancias a depositar", "retenciones impuesto a las ganancias", "retencion impuesto a las ganancias"],
        "keywords_debiles": ["ganancias", "retenciones", "cargas fiscales"],
    },
    {
        "codigo": "RETENCION_IVA",
        "nombre": "Retenciones IVA practicadas a proveedores",
        "naturaleza": "PASIVO_FISCAL",
        "tipo": "RETENCION",
        "requiere_cuenta": True,
        "criticidad": "ALTA",
        "impacto": "Retencion IVA practicada; no debe mezclarse con IVA credito fiscal.",
        "keywords_fuertes": ["retenciones iva a depositar", "retencion iva a depositar", "retenciones iva", "retencion iva"],
        "keywords_debiles": ["iva", "retenciones", "cargas fiscales"],
    },
    {
        "codigo": "RETENCION_SUSS",
        "nombre": "Retenciones SUSS practicadas a proveedores",
        "naturaleza": "PASIVO_FISCAL",
        "tipo": "RETENCION",
        "requiere_cuenta": True,
        "criticidad": "MEDIA",
        "impacto": "Retencion previsional/laboral aplicable segun actividad/regimen.",
        "keywords_fuertes": ["retenciones suss a depositar", "retencion suss a depositar", "retenciones seguridad social", "retencion seguridad social"],
        "keywords_debiles": ["suss", "seguridad social", "retenciones", "cargas sociales"],
    },
    {
        "codigo": "OTRAS_RETENCIONES",
        "nombre": "Otras retenciones practicadas",
        "naturaleza": "PASIVO_FISCAL",
        "tipo": "RETENCION",
        "requiere_cuenta": True,
        "criticidad": "MEDIA",
        "impacto": "Retenciones no estandarizadas; requieren clasificacion antes de operar.",
        "keywords_fuertes": ["otras retenciones a depositar", "otras retenciones", "retenciones a depositar"],
        "keywords_debiles": ["retenciones", "cargas fiscales"],
    },
    {
        "codigo": "DIFERENCIA_PAGO",
        "nombre": "Diferencias de pago, redondeos y ajustes",
        "naturaleza": "RESULTADO",
        "tipo": "AJUSTE",
        "requiere_cuenta": True,
        "criticidad": "MEDIA",
        "impacto": "Diferencias menores; no deben confundirse con retenciones ni anticipos.",
        "keywords_fuertes": ["diferencia de pago", "diferencias de pago", "redondeos", "ajustes por redondeo", "diferencias de cambio"],
        "keywords_debiles": ["diferencia", "ajuste", "resultado financiero", "gastos bancarios"],
    },
    {
        "codigo": "ANULACION_PAGO",
        "nombre": "Reverso por anulacion de pago",
        "naturaleza": "REVERSO",
        "tipo": "CONTROL_OPERATIVO",
        "requiere_cuenta": False,
        "criticidad": "ALTA",
        "impacto": "Debe usar las mismas cuentas del pago original y conservar auditoria.",
        "keywords_fuertes": [],
        "keywords_debiles": [],
    },
    {
        "codigo": "ORDEN_DE_PAGO",
        "nombre": "Orden de pago como documento operativo",
        "naturaleza": "DOCUMENTAL",
        "tipo": "CONTROL_OPERATIVO",
        "requiere_cuenta": False,
        "criticidad": "MEDIA",
        "impacto": "No requiere cuenta directa; debe vincular pago, proveedor, imputaciones y retenciones.",
        "keywords_fuertes": [],
        "keywords_debiles": [],
    },
    {
        "codigo": "PROPUESTA_ASIENTO_PAGO",
        "nombre": "Propuesta futura de asiento de pago",
        "naturaleza": "BANDEJA",
        "tipo": "CONTROL_CONTABLE",
        "requiere_cuenta": False,
        "criticidad": "ALTA",
        "impacto": "Debe reemplazar gradualmente el asiento definitivo directo por una propuesta revisable.",
        "keywords_fuertes": [],
        "keywords_debiles": [],
    },
]

PATRONES_LEGACY = {
    "CUENTA_PROVEEDORES_HARDCODEADA": r"CUENTA_PROVEEDORES\s*=\s*[\"']PROVEEDORES[\"']",
    "RETENCIONES_DEFAULT_HARDCODEADAS": r"CUENTAS_RETENCIONES_DEFAULT|RETENCIONES\s+IIBB\s+A\s+DEPOSITAR|RETENCIONES\s+GANANCIAS\s+A\s+DEPOSITAR|RETENCIONES\s+IVA\s+A\s+DEPOSITAR|RETENCIONES\s+SUSS\s+A\s+DEPOSITAR",
    "LIBRO_DIARIO_DIRECTO": r"INSERT\s+INTO\s+libro_diario\b",
    "TESORERIA_DIRECTA": r"INSERT\s+INTO\s+tesoreria_operaciones\b",
    "CAJA_DIRECTA": r"registrar_pago_efectivo_en_caja|anular_movimientos_caja",
    "BANDEJA_EXPLICITA": r"\basientos_propuestos\b|\bbandeja\b|propuesta_asiento",
}


def obtener_parametrizacion_asistida_pagos(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
    base_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Pagos PRO v2A - Parametrizacion asistida de pagos.

    Servicio aislado y de solo lectura:
    - no crea tablas;
    - no inserta;
    - no actualiza;
    - no borra;
    - no modifica el flujo operativo actual de Pagos;
    - no acepta parametrizaciones; eso queda para v2B.

    Devuelve una matriz de sugerencias contra Plan Empresa / Plan Maestro FF.
    """

    conexion_propia = False
    if conn is None and base_path is None:
        conn = _obtener_conexion_por_defecto()
        conexion_propia = conn is not None

    try:
        base = Path(base_path) if base_path is not None else Path.cwd()
        cuentas = _obtener_cuentas_plan(conn, empresa_id) if conn is not None else []
        codigo = _diagnosticar_codigo_pagos(base)
        matriz = _construir_matriz(cuentas)
        alertas = _construir_alertas(matriz, codigo, cuentas, conn is not None)
        resumen = _resumen_matriz(matriz, alertas)
        estado = _determinar_estado(resumen, alertas)

        return {
            "modulo": "Pagos PRO v2A",
            "tipo": "parametrizacion_asistida",
            "empresa_id": empresa_id,
            "estado": estado,
            "resumen": resumen,
            "matriz": matriz,
            "alertas": alertas,
            "codigo_legacy": codigo,
            "cuentas_plan_detectadas": len(cuentas),
            "fuente_cuentas": _fuente_cuentas(cuentas),
            "modo": "solo_lectura",
            "proxima_etapa_sugerida": "Pagos PRO v2B - aceptacion, edicion y desactivacion auditada de parametrizaciones",
            "no_tocar_en_v2a": [
                "services/pagos_service.py",
                "modulos/pagos.py",
                "Caja",
                "Banco/Caja",
                "Compras",
                "Libro Diario",
                "Bandeja de asientos",
                "migrations",
            ],
        }
    finally:
        if conexion_propia and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def diagnosticar_parametrizacion_pagos(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
    base_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    return obtener_parametrizacion_asistida_pagos(
        empresa_id=empresa_id,
        conn=conn,
        base_path=base_path,
    )


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
            if not callable(funcion):
                continue
            try:
                conn = funcion()
            except Exception:
                continue
            if isinstance(conn, sqlite3.Connection):
                return conn

    return None


def _obtener_cuentas_plan(conn: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    tablas = _listar_tablas(conn)
    cuentas: List[Dict[str, Any]] = []

    for tabla in TABLAS_PLAN_CANDIDATAS:
        if tabla not in tablas:
            continue

        columnas = _columnas_tabla(conn, tabla)
        if not columnas:
            continue

        col_nombre = _primera_columna(columnas, COLUMNAS_NOMBRE_CUENTA)
        if not col_nombre:
            continue

        col_codigo = _primera_columna(columnas, COLUMNAS_CODIGO_CUENTA)
        col_uso = _primera_columna(columnas, COLUMNAS_USO_OPERATIVO)
        col_activo = _primera_columna(columnas, COLUMNAS_HABILITADO)
        col_empresa = "empresa_id" if "empresa_id" in columnas else None
        col_id = "id" if "id" in columnas else None

        select_cols = []
        aliases = []
        for alias, col in [
            ("id", col_id),
            ("codigo", col_codigo),
            ("nombre", col_nombre),
            ("uso_operativo", col_uso),
            ("activo", col_activo),
        ]:
            if col:
                select_cols.append(_quote_identifier(col))
            else:
                select_cols.append("NULL")
            aliases.append(alias)

        sql = f"SELECT {', '.join(select_cols)} FROM {_quote_identifier(tabla)}"
        params: List[Any] = []

        if col_empresa:
            sql += f" WHERE {_quote_identifier(col_empresa)} = ? OR {_quote_identifier(col_empresa)} IS NULL"
            params.append(empresa_id)

        try:
            cur = conn.execute(sql, params)
            filas = cur.fetchall()
        except Exception:
            continue

        for fila in filas:
            item = dict(zip(aliases, fila))
            if not _cuenta_activa(item.get("activo")):
                continue

            nombre = _texto(item.get("nombre"))
            if not nombre:
                continue

            cuenta = {
                "tabla": tabla,
                "id": item.get("id"),
                "codigo": _texto(item.get("codigo")),
                "nombre": nombre,
                "uso_operativo": _texto(item.get("uso_operativo")),
                "texto_busqueda": _normalizar(" ".join([
                    _texto(item.get("codigo")),
                    nombre,
                    _texto(item.get("uso_operativo")),
                    tabla,
                ])),
            }
            cuentas.append(cuenta)

        if cuentas:
            return cuentas

    return cuentas


def _construir_matriz(cuentas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    matriz = []

    for definicion in PARAMETRIZACIONES_REQUERIDAS:
        if not definicion["requiere_cuenta"]:
            matriz.append({
                "codigo": definicion["codigo"],
                "nombre": definicion["nombre"],
                "tipo": definicion["tipo"],
                "naturaleza": definicion["naturaleza"],
                "criticidad": definicion["criticidad"],
                "estado": ESTADO_PARAM_INFORMATIVA,
                "cuenta_sugerida": None,
                "confianza": "NO_APLICA",
                "puntaje": 0,
                "motivo": "No requiere cuenta directa en v2A; se resuelve con reglas del pago original o control documental.",
                "impacto": definicion["impacto"],
            })
            continue

        sugerencia, confianza, puntaje = _buscar_cuenta_sugerida(definicion, cuentas)

        if sugerencia and confianza in {"ALTA", "MEDIA"}:
            estado = ESTADO_PARAM_SUGERIDA
            motivo = "Cuenta sugerida desde Plan Empresa / Plan Maestro FF por coincidencia semantica."
        elif sugerencia:
            estado = ESTADO_PARAM_A_REVISAR
            motivo = "Existe una coincidencia debil; requiere revision profesional antes de aceptar."
        else:
            estado = ESTADO_PARAM_INCOMPLETA
            motivo = "No se encontro cuenta suficientemente relacionada en el Plan Empresa disponible."

        matriz.append({
            "codigo": definicion["codigo"],
            "nombre": definicion["nombre"],
            "tipo": definicion["tipo"],
            "naturaleza": definicion["naturaleza"],
            "criticidad": definicion["criticity"] if "criticity" in definicion else definicion["criticidad"],
            "estado": estado,
            "cuenta_sugerida": sugerencia,
            "confianza": confianza,
            "puntaje": puntaje,
            "motivo": motivo,
            "impacto": definicion["impacto"],
        })

    return matriz


def _buscar_cuenta_sugerida(definicion: Dict[str, Any], cuentas: Sequence[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str, int]:
    mejor: Optional[Dict[str, Any]] = None
    mejor_puntaje = 0

    fuertes = [_normalizar(x) for x in definicion.get("keywords_fuertes", [])]
    debiles = [_normalizar(x) for x in definicion.get("keywords_debiles", [])]

    for cuenta in cuentas:
        texto = cuenta.get("texto_busqueda") or _normalizar(" ".join([
            _texto(cuenta.get("codigo")),
            _texto(cuenta.get("nombre")),
            _texto(cuenta.get("uso_operativo")),
        ]))

        puntaje = 0
        for keyword in fuertes:
            if keyword and keyword in texto:
                puntaje += 10
        for keyword in debiles:
            if keyword and keyword in texto:
                puntaje += 3

        if _normalizar(definicion["codigo"]) in texto:
            puntaje += 5

        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor = cuenta

    if mejor is None:
        return None, "SIN_SUGERENCIA", 0

    sugerencia = {
        "tabla": mejor.get("tabla"),
        "id": mejor.get("id"),
        "codigo": mejor.get("codigo"),
        "nombre": mejor.get("nombre"),
        "uso_operativo": mejor.get("uso_operativo"),
    }

    if mejor_puntaje >= 10:
        return sugerencia, "ALTA", mejor_puntaje
    if mejor_puntaje >= 6:
        return sugerencia, "MEDIA", mejor_puntaje
    if mejor_puntaje >= 3:
        return sugerencia, "BAJA", mejor_puntaje

    return None, "SIN_SUGERENCIA", 0


def _diagnosticar_codigo_pagos(base_path: Path) -> Dict[str, Any]:
    archivos = [
        base_path / "services" / "pagos_service.py",
        base_path / "modulos" / "pagos.py",
    ]

    textos: Dict[str, str] = {}
    archivos_leidos = []
    archivos_faltantes = []

    for archivo in archivos:
        try:
            rel = str(archivo.relative_to(base_path))
        except Exception:
            rel = str(archivo)

        if not archivo.exists():
            archivos_faltantes.append(rel)
            continue

        try:
            textos[rel] = archivo.read_text(encoding="utf-8", errors="ignore")
            archivos_leidos.append(rel)
        except Exception:
            textos[rel] = ""
            archivos_leidos.append(rel)

    hallazgos = {}
    ocurrencias = {}

    for codigo, patron in PATRONES_LEGACY.items():
        regex = re.compile(patron, re.IGNORECASE | re.MULTILINE)
        matches = []

        for archivo, texto in textos.items():
            for numero_linea, linea in enumerate(texto.splitlines(), start=1):
                if regex.search(linea):
                    matches.append({
                        "archivo": archivo,
                        "linea": numero_linea,
                        "texto": linea.strip()[:220],
                    })

        if codigo == "BANDEJA_EXPLICITA":
            hallazgos["SIN_BANDEJA_EXPLICITA"] = not bool(matches)
            ocurrencias["SIN_BANDEJA_EXPLICITA"] = [] if matches else [{
                "archivo": "services/pagos_service.py / modulos/pagos.py",
                "linea": None,
                "texto": "No se detectaron referencias claras a Bandeja/asientos_propuestos/propuesta_asiento.",
            }]
        else:
            hallazgos[codigo] = bool(matches)
            ocurrencias[codigo] = matches[:20]

    return {
        "archivos_leidos": archivos_leidos,
        "archivos_faltantes": archivos_faltantes,
        "hallazgos": hallazgos,
        "ocurrencias": ocurrencias,
    }


def _construir_alertas(
    matriz: Sequence[Dict[str, Any]],
    codigo: Dict[str, Any],
    cuentas: Sequence[Dict[str, Any]],
    conexion_disponible: bool,
) -> List[Dict[str, Any]]:
    alertas: List[Dict[str, Any]] = []
    hallazgos = codigo.get("hallazgos", {})

    if not conexion_disponible:
        alertas.append(_alerta(
            "PAGOS_PARAMETRIZACION_SIN_CONEXION_DB",
            SEVERIDAD_ADVERTENCIA,
            "No se recibio conexion a la base de datos.",
            "La matriz puede diagnosticar codigo, pero no sugerir cuentas reales del Plan Empresa.",
        ))

    if conexion_disponible and not cuentas:
        alertas.append(_alerta(
            "PAGOS_PLAN_EMPRESA_NO_DETECTADO",
            SEVERIDAD_CRITICA,
            "No se detectaron cuentas activas del Plan Empresa / Plan Maestro FF.",
            "Sin cuentas disponibles no se puede parametrizar Pagos profesionalmente.",
        ))

    incompletas = [fila["codigo"] for fila in matriz if fila["estado"] == ESTADO_PARAM_INCOMPLETA]
    if incompletas:
        alertas.append(_alerta(
            "PAGOS_PARAMETRIZACIONES_INCOMPLETAS",
            SEVERIDAD_ADVERTENCIA,
            "Hay parametrizaciones requeridas sin cuenta sugerida.",
            "Revisar: " + ", ".join(incompletas),
        ))

    revisar = [fila["codigo"] for fila in matriz if fila["estado"] == ESTADO_PARAM_A_REVISAR]
    if revisar:
        alertas.append(_alerta(
            "PAGOS_PARAMETRIZACIONES_A_REVISAR",
            SEVERIDAD_INFO,
            "Hay sugerencias debiles que requieren revision profesional.",
            "Revisar: " + ", ".join(revisar),
        ))

    if hallazgos.get("CUENTA_PROVEEDORES_HARDCODEADA") or hallazgos.get("RETENCIONES_DEFAULT_HARDCODEADAS"):
        alertas.append(_alerta(
            "PAGOS_LEGACY_CUENTAS_HARDCODEADAS",
            SEVERIDAD_ADVERTENCIA,
            "El flujo operativo actual contiene cuentas hardcodeadas.",
            "v2A solo diagnostica; v2B debera permitir aceptar/editar parametrizaciones antes de reemplazar defaults.",
        ))

    if hallazgos.get("LIBRO_DIARIO_DIRECTO"):
        alertas.append(_alerta(
            "PAGOS_LEGACY_ASIENTO_DIRECTO",
            SEVERIDAD_ADVERTENCIA,
            "El flujo operativo actual genera Libro Diario directo.",
            "La arquitectura futura debe pasar por Bandeja de asientos o propuestas revisables.",
        ))

    if hallazgos.get("SIN_BANDEJA_EXPLICITA"):
        alertas.append(_alerta(
            "PAGOS_SIN_BANDEJA_EXPLICITA",
            SEVERIDAD_ADVERTENCIA,
            "No se detecta integracion explicita con Bandeja de asientos.",
            "Mantener como pendiente antes de tocar pagos_service.py.",
        ))

    return alertas


def _resumen_matriz(matriz: Sequence[Dict[str, Any]], alertas: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "parametrizaciones": len(matriz),
        "sugeridas": sum(1 for fila in matriz if fila["estado"] == ESTADO_PARAM_SUGERIDA),
        "incompletas": sum(1 for fila in matriz if fila["estado"] == ESTADO_PARAM_INCOMPLETA),
        "a_revisar": sum(1 for fila in matriz if fila["estado"] == ESTADO_PARAM_A_REVISAR),
        "informativas": sum(1 for fila in matriz if fila["estado"] == ESTADO_PARAM_INFORMATIVA),
        "alertas_criticas": sum(1 for alerta in alertas if alerta["severidad"] == SEVERIDAD_CRITICA),
        "alertas_advertencia": sum(1 for alerta in alertas if alerta["severidad"] == SEVERIDAD_ADVERTENCIA),
    }


def _determinar_estado(resumen: Dict[str, Any], alertas: Sequence[Dict[str, Any]]) -> str:
    if resumen["alertas_criticas"] > 0:
        return ESTADO_CRITICO
    if resumen["incompletas"] > 0 or resumen["a_revisar"] > 0:
        return ESTADO_REQUIERE_PARAMETRIZACION
    if any(alerta["severidad"] == SEVERIDAD_ADVERTENCIA for alerta in alertas):
        return ESTADO_REQUIERE_REVISION
    return ESTADO_OK


def _fuente_cuentas(cuentas: Sequence[Dict[str, Any]]) -> Optional[str]:
    if not cuentas:
        return None
    return _texto(cuentas[0].get("tabla")) or None


def _alerta(codigo: str, severidad: str, titulo: str, detalle: str) -> Dict[str, str]:
    return {
        "codigo": codigo,
        "severidad": severidad,
        "titulo": titulo,
        "detalle": detalle,
    }


def _listar_tablas(conn: sqlite3.Connection) -> set[str]:
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        return {str(row[0]) for row in cur.fetchall()}
    except Exception:
        return set()


def _columnas_tabla(conn: sqlite3.Connection, tabla: str) -> List[str]:
    try:
        cur = conn.execute(f"PRAGMA table_info({_quote_identifier(tabla)})")
        return [str(row[1]) for row in cur.fetchall()]
    except Exception:
        return []


def _primera_columna(columnas: Sequence[str], candidatas: Sequence[str]) -> Optional[str]:
    columnas_normalizadas = {_normalizar(col): col for col in columnas}
    for candidata in candidatas:
        encontrada = columnas_normalizadas.get(_normalizar(candidata))
        if encontrada:
            return encontrada
    return None


def _cuenta_activa(valor: Any) -> bool:
    if valor is None:
        return True
    texto = _normalizar(valor)
    if texto in {"", "1", "true", "si", "s", "activo", "activa", "vigente", "habilitado", "habilitada"}:
        return True
    if texto in {"0", "false", "no", "n", "inactivo", "inactiva", "baja", "deshabilitado", "deshabilitada"}:
        return False
    return True


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar(valor: Any) -> str:
    texto = _texto(valor).lower()
    reemplazos = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()
