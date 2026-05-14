from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIPOS_CUENTA_TESORERIA_VALIDOS = {
    "BANCO",
    "CAJA",
    "BILLETERA",
    "TARJETA",
    "VALORES",
}

TIPOS_MEDIO_PAGO_REFERENCIA = {
    "EFECTIVO": "CAJA",
    "TRANSFERENCIA": "BANCO",
    "DEBITO_AUTOMATICO": "BANCO",
    "CHEQUE": "VALORES",
    "ECHEQ": "VALORES",
    "TARJETA": "TARJETA",
    "BILLETERA": "BILLETERA",
    "MERCADO_PAGO": "BILLETERA",
    "MP": "BILLETERA",
    "OTRO": "OTRO",
}

USOS_ESPERADOS_POR_TIPO_CUENTA = {
    "CAJA": {"CAJA", "CAJA_GENERAL", "FONDO_FIJO", "RECAUDACIONES_A_DEPOSITAR"},
    "BANCO": {"BANCO", "BANCO_CUENTA_CORRIENTE", "BANCO_CAJA_AHORRO"},
    "BILLETERA": {"BILLETERA", "BILLETERA_VIRTUAL"},
    "TARJETA": {"TARJETA", "TARJETA_COBROS", "TARJETA_PUENTE"},
    "VALORES": {"VALORES", "VALORES_A_DEPOSITAR", "CHEQUES", "ECHEQ"},
}

PALABRAS_CLAVE_POR_TIPO_CUENTA = {
    "CAJA": {"CAJA", "EFECTIVO", "FONDO", "FIJO", "RECAUDACIONES"},
    "BANCO": {"BANCO", "BANCARIA", "BANCARIO", "CUENTA", "CORRIENTE", "AHORRO", "MACRO", "BBVA", "NACION", "SANTANDER", "GALICIA"},
    "BILLETERA": {"BILLETERA", "MERCADO", "PAGO", "WALLET", "VIRTUAL", "MP"},
    "TARJETA": {"TARJETA", "VISA", "MASTERCARD", "AMEX", "POSNET", "CUPON", "CUPONES"},
    "VALORES": {"VALORES", "CHEQUE", "CHEQUES", "ECHEQ", "DOCUMENTOS", "DEPOSITAR", "CARTERA"},
}

PALABRAS_EXCLUSION_TESORERIA = {
    "PROVEEDOR",
    "PROVEEDORES",
    "CLIENTE",
    "CLIENTES",
    "VENTA",
    "VENTAS",
    "COMPRA",
    "COMPRAS",
    "IVA",
    "IIBB",
    "GANANCIAS",
    "SUELDO",
    "SUELDOS",
    "CARGAS",
    "SOCIALES",
    "CAPITAL",
    "RESULTADO",
    "RESULTADOS",
    "GASTO",
    "GASTOS",
    "INGRESO",
    "INGRESOS",
    "MERCADERIA",
    "MERCADERIAS",
}

SEVERIDAD_ORDEN = {
    "OK": 0,
    "INFORMATIVO": 1,
    "ADVERTENCIA": 2,
    "CRITICO": 3,
}


class TesoreriaParametrizacionError(RuntimeError):
    pass


def analizar_parametrizacion_tesoreria(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
    incluir_inactivas: bool = False,
    max_candidatos: int = 5,
) -> Dict[str, Any]:
    """
    Tesorería PRO v2A: parametrización asistida de cuentas y medios.

    Servicio de solo lectura. No ejecuta migraciones, no llama a servicios
    operativos, no crea cuentas, no vincula, no registra operaciones, no concilia
    y no audita. Su única responsabilidad es construir una matriz profesional de
    sugerencias para una futura aceptación auditada en v2B.
    """

    empresa_id = int(empresa_id or 1)
    max_candidatos = max(int(max_candidatos or 5), 1)
    cerrar_conexion = conexion is None
    con = conexion or _obtener_conexion()

    try:
        _configurar_conexion(con)

        resultado: Dict[str, Any] = {
            "empresa_id": empresa_id,
            "estado": "OK",
            "solo_lectura": True,
            "version": "TESORERIA_PRO_V2A_PARAMETRIZACION_ASISTIDA",
            "resumen": {
                "cuentas_tesoreria": 0,
                "cuentas_activas": 0,
                "cuentas_ya_vinculadas": 0,
                "cuentas_sin_vinculo": 0,
                "cuentas_con_sugerencia_alta": 0,
                "cuentas_con_sugerencia_media": 0,
                "cuentas_con_sugerencia_baja": 0,
                "cuentas_sin_sugerencia": 0,
                "cuentas_vinculadas_requieren_revision": 0,
                "medios_pago": 0,
                "medios_pago_activos": 0,
                "medios_pago_tipo_ok": 0,
                "medios_pago_requieren_revision": 0,
                "candidatos_plan_empresa": 0,
            },
            "tablas": {},
            "cuentas": [],
            "medios_pago": [],
            "matriz_por_tipo_cuenta": {},
            "alertas": [],
            "recomendaciones": [],
        }

        tablas_requeridas = (
            "tesoreria_cuentas",
            "tesoreria_medios_pago",
            "plan_cuentas_empresa",
        )
        for tabla in tablas_requeridas:
            existe = _tabla_existe(con, tabla)
            resultado["tablas"][tabla] = {
                "existe": existe,
                "columnas": _columnas_tabla(con, tabla) if existe else [],
            }
            if not existe:
                _agregar_alerta(
                    resultado,
                    codigo="TESORERIA_PARAM_TABLA_INEXISTENTE",
                    severidad="CRITICO" if tabla in {"tesoreria_cuentas", "plan_cuentas_empresa"} else "ADVERTENCIA",
                    titulo=f"No existe la tabla {tabla}",
                    detalle=(
                        "La parametrización asistida no inicializa tablas ni ejecuta migraciones. "
                        "Revise la estructura antes de avanzar."
                    ),
                    entidad=tabla,
                )

        cuentas = _leer_filas_empresa(con, "tesoreria_cuentas", empresa_id)
        medios = _leer_filas_empresa(con, "tesoreria_medios_pago", empresa_id)
        plan_empresa_todo = _leer_filas_empresa(con, "plan_cuentas_empresa", empresa_id)
        plan_empresa = _leer_plan_empresa_activo(con, empresa_id, incluir_inactivas=incluir_inactivas)
        plan_por_codigo = {_codigo_plan(fila): fila for fila in plan_empresa_todo if _codigo_plan(fila)}

        resultado["resumen"]["cuentas_tesoreria"] = len(cuentas)
        resultado["resumen"]["cuentas_activas"] = sum(1 for cuenta in cuentas if _es_activo(cuenta.get("activo"), True))
        resultado["resumen"]["medios_pago"] = len(medios)
        resultado["resumen"]["medios_pago_activos"] = sum(1 for medio in medios if _es_activo(medio.get("activo"), True))
        resultado["resumen"]["candidatos_plan_empresa"] = len(plan_empresa)

        _analizar_cuentas(resultado, cuentas, plan_empresa, plan_por_codigo, max_candidatos=max_candidatos)
        _analizar_medios_pago(resultado, medios)
        _armar_matriz_por_tipo(resultado)
        _agregar_recomendaciones(resultado)
        _actualizar_estado_general(resultado)

        return resultado
    finally:
        if cerrar_conexion:
            con.close()


def obtener_matriz_parametrizacion_tesoreria(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    return analizar_parametrizacion_tesoreria(empresa_id=empresa_id, conexion=conexion).get("cuentas", [])


def obtener_alertas_parametrizacion_tesoreria(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    return analizar_parametrizacion_tesoreria(empresa_id=empresa_id, conexion=conexion).get("alertas", [])


def obtener_resumen_parametrizacion_tesoreria(
    empresa_id: int = 1,
    conexion: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    return analizar_parametrizacion_tesoreria(empresa_id=empresa_id, conexion=conexion).get("resumen", {})


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

    raise TesoreriaParametrizacionError(
        "No se pudo obtener una conexión SQLite para parametrización asistida de Tesorería. "
        "Pase una conexión explícita con analizar_parametrizacion_tesoreria(..., conexion=con)."
    )


def _configurar_conexion(con: sqlite3.Connection) -> None:
    try:
        con.row_factory = sqlite3.Row
    except Exception:
        pass


def _tabla_existe(con: sqlite3.Connection, tabla: str) -> bool:
    cur = con.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (tabla,),
    )
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
        cur.execute(
            f"SELECT * FROM {_identificador_seguro(tabla)} WHERE empresa_id = ?",
            (empresa_id,),
        )
    else:
        cur.execute(f"SELECT * FROM {_identificador_seguro(tabla)}")

    return [_fila_a_dict(fila) for fila in cur.fetchall()]


def _leer_plan_empresa_activo(
    con: sqlite3.Connection,
    empresa_id: int,
    incluir_inactivas: bool = False,
) -> List[Dict[str, Any]]:
    filas = _leer_filas_empresa(con, "plan_cuentas_empresa", empresa_id)
    candidatos = []

    for fila in filas:
        if not incluir_inactivas and not _cuenta_plan_activa(fila):
            continue
        if not _es_imputable(fila.get("imputable"), default=True):
            continue
        if _codigo_plan(fila) and _nombre_plan(fila):
            candidatos.append(fila)

    return candidatos


def _analizar_cuentas(
    resultado: Dict[str, Any],
    cuentas: Sequence[Dict[str, Any]],
    plan_empresa: Sequence[Dict[str, Any]],
    plan_por_codigo: Dict[str, Dict[str, Any]],
    max_candidatos: int,
) -> None:
    for cuenta in cuentas:
        tipo = _texto_upper(cuenta.get("tipo_cuenta"))
        cuenta_id = _obtener_id(cuenta)
        activa = _es_activo(cuenta.get("activo"), True)
        codigo_actual = _texto(cuenta.get("cuenta_contable_codigo") or cuenta.get("cuenta_codigo"))
        plan_actual = plan_por_codigo.get(codigo_actual) if codigo_actual else None
        candidatos = _buscar_candidatos_para_cuenta(cuenta, plan_empresa, max_candidatos=max_candidatos)
        sugerencia = candidatos[0] if candidatos else _sugerencia_vacia()
        diagnostico = "INACTIVA" if not activa else "SIN_VINCULO"
        requiere_revision = False

        if codigo_actual:
            resultado["resumen"]["cuentas_ya_vinculadas"] += 1
            validacion = _validar_vinculo_existente(cuenta, plan_actual)
            diagnostico = validacion["diagnostico"]
            requiere_revision = validacion["requiere_revision"]
            for alerta in validacion["alertas"]:
                _agregar_alerta(resultado, **alerta)
        else:
            resultado["resumen"]["cuentas_sin_vinculo"] += 1
            if sugerencia["confianza"] == "ALTA":
                resultado["resumen"]["cuentas_con_sugerencia_alta"] += 1
            elif sugerencia["confianza"] == "MEDIA":
                resultado["resumen"]["cuentas_con_sugerencia_media"] += 1
            elif sugerencia["confianza"] == "BAJA":
                resultado["resumen"]["cuentas_con_sugerencia_baja"] += 1
            else:
                resultado["resumen"]["cuentas_sin_sugerencia"] += 1

            if activa and sugerencia["confianza"] in {"ALTA", "MEDIA"}:
                _agregar_alerta(
                    resultado,
                    codigo="TESORERIA_PARAM_CUENTA_SIN_VINCULO_CON_SUGERENCIA",
                    severidad="INFORMATIVO",
                    titulo="Cuenta de Tesorería sin vínculo con sugerencia disponible",
                    detalle=(
                        f"La cuenta { _texto(cuenta.get('nombre')) or cuenta_id } puede vincularse tentativamente "
                        f"a {sugerencia.get('codigo')} - {sugerencia.get('nombre')} "
                        f"con confianza {sugerencia.get('confianza')}."
                    ),
                    entidad="tesoreria_cuentas",
                    entidad_id=cuenta_id,
                )
            elif activa and sugerencia["confianza"] == "NULA":
                _agregar_alerta(
                    resultado,
                    codigo="TESORERIA_PARAM_CUENTA_SIN_SUGERENCIA",
                    severidad="ADVERTENCIA",
                    titulo="Cuenta de Tesorería sin vínculo y sin sugerencia confiable",
                    detalle=(
                        f"La cuenta { _texto(cuenta.get('nombre')) or cuenta_id } no tiene cuenta contable "
                        "vinculada y no se encontró una candidata clara en Plan Empresa."
                    ),
                    entidad="tesoreria_cuentas",
                    entidad_id=cuenta_id,
                )

        if requiere_revision:
            resultado["resumen"]["cuentas_vinculadas_requieren_revision"] += 1

        item = {
            "cuenta_tesoreria_id": cuenta_id,
            "tipo_cuenta": tipo,
            "nombre": _texto(cuenta.get("nombre")),
            "entidad": _texto(cuenta.get("entidad") or cuenta.get("banco") or cuenta.get("banco_nombre")),
            "numero_cuenta": _texto(cuenta.get("numero_cuenta")),
            "moneda": _texto_upper(cuenta.get("moneda") or "ARS"),
            "activo": activa,
            "cuenta_contable_codigo_actual": codigo_actual,
            "cuenta_contable_nombre_actual": _texto(cuenta.get("cuenta_contable_nombre")),
            "diagnostico": diagnostico,
            "requiere_revision": requiere_revision,
            "sugerencia": sugerencia,
            "candidatos": candidatos,
        }
        resultado["cuentas"].append(item)

        if tipo and tipo not in TIPOS_CUENTA_TESORERIA_VALIDOS:
            _agregar_alerta(
                resultado,
                codigo="TESORERIA_PARAM_TIPO_CUENTA_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Tipo de cuenta de Tesorería no reconocido",
                detalle=f"La cuenta {item['nombre'] or cuenta_id} tiene tipo {tipo}.",
                entidad="tesoreria_cuentas",
                entidad_id=cuenta_id,
            )


def _validar_vinculo_existente(cuenta: Dict[str, Any], plan_actual: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cuenta_id = _obtener_id(cuenta)
    tipo = _texto_upper(cuenta.get("tipo_cuenta"))
    codigo_actual = _texto(cuenta.get("cuenta_contable_codigo") or cuenta.get("cuenta_codigo"))
    alertas: List[Dict[str, Any]] = []

    if plan_actual is None:
        alertas.append(
            {
                "codigo": "TESORERIA_PARAM_VINCULO_NO_ENCONTRADO_PLAN",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta vinculada no encontrada en Plan Empresa",
                "detalle": f"La cuenta de Tesorería apunta a {codigo_actual}, pero esa cuenta no existe como cuenta imputable activa del Plan Empresa.",
                "entidad": "tesoreria_cuentas",
                "entidad_id": cuenta_id,
            }
        )
        return {"diagnostico": "VINCULO_REVISAR", "requiere_revision": True, "alertas": alertas}

    if not _cuenta_plan_activa(plan_actual):
        alertas.append(
            {
                "codigo": "TESORERIA_PARAM_VINCULO_INACTIVO",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta vinculada inactiva o anulada",
                "detalle": f"La cuenta {codigo_actual} vinculada a Tesorería no está activa.",
                "entidad": "tesoreria_cuentas",
                "entidad_id": cuenta_id,
            }
        )

    if not _es_imputable(plan_actual.get("imputable"), default=True):
        alertas.append(
            {
                "codigo": "TESORERIA_PARAM_VINCULO_NO_IMPUTABLE",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta vinculada no imputable",
                "detalle": f"La cuenta {codigo_actual} vinculada a Tesorería no es imputable.",
                "entidad": "tesoreria_cuentas",
                "entidad_id": cuenta_id,
            }
        )

    uso = _normalizar_uso_operativo(plan_actual.get("uso_operativo_sistema"))
    usos_esperados = USOS_ESPERADOS_POR_TIPO_CUENTA.get(tipo, set())
    if usos_esperados and uso and uso not in usos_esperados:
        alertas.append(
            {
                "codigo": "TESORERIA_PARAM_VINCULO_USO_REVISAR",
                "severidad": "INFORMATIVO",
                "titulo": "Cuenta vinculada con uso operativo distinto al tipo de Tesorería",
                "detalle": f"La cuenta {codigo_actual} tiene uso {uso}; para {tipo} se esperaba {', '.join(sorted(usos_esperados))}.",
                "entidad": "tesoreria_cuentas",
                "entidad_id": cuenta_id,
            }
        )

    if alertas:
        return {"diagnostico": "VINCULO_REVISAR", "requiere_revision": True, "alertas": alertas}

    return {"diagnostico": "VINCULADA_OK", "requiere_revision": False, "alertas": alertas}


def _buscar_candidatos_para_cuenta(
    cuenta: Dict[str, Any],
    plan_empresa: Sequence[Dict[str, Any]],
    max_candidatos: int,
) -> List[Dict[str, Any]]:
    evaluados = []
    for plan in plan_empresa:
        sugerencia = _puntuar_candidata(cuenta, plan)
        if sugerencia["puntaje"] > 0:
            evaluados.append(sugerencia)

    evaluados.sort(key=lambda item: (-item["puntaje"], item.get("codigo", "")))
    return evaluados[:max_candidatos]


def _puntuar_candidata(cuenta: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    tipo = _texto_upper(cuenta.get("tipo_cuenta"))
    uso = _normalizar_uso_operativo(plan.get("uso_operativo_sistema"))
    codigo = _codigo_plan(plan)
    nombre = _nombre_plan(plan)
    texto_cuenta = _texto_busqueda(
        cuenta.get("nombre"),
        cuenta.get("entidad"),
        cuenta.get("banco"),
        cuenta.get("banco_nombre"),
        cuenta.get("numero_cuenta"),
        cuenta.get("moneda"),
        tipo,
    )
    texto_plan = _texto_busqueda(
        codigo,
        nombre,
        plan.get("nombre_cuenta"),
        plan.get("banco_nombre"),
        plan.get("numero_cuenta"),
        uso,
    )

    puntaje = 0
    motivos: List[str] = []

    usos_esperados = USOS_ESPERADOS_POR_TIPO_CUENTA.get(tipo, set())
    if uso and usos_esperados and uso in usos_esperados:
        puntaje += 65
        motivos.append(f"uso operativo compatible: {uso}")
    elif uso and tipo in TIPOS_CUENTA_TESORERIA_VALIDOS:
        puntaje -= 20
        motivos.append(f"uso operativo diferente: {uso}")

    palabras_tipo = PALABRAS_CLAVE_POR_TIPO_CUENTA.get(tipo, set())
    coincidencias_tipo = sorted(palabra for palabra in palabras_tipo if palabra in texto_plan)
    if coincidencias_tipo:
        incremento = min(20, len(coincidencias_tipo) * 6)
        puntaje += incremento
        motivos.append("palabras compatibles en Plan Empresa: " + ", ".join(coincidencias_tipo[:4]))

    coincidencias_texto = _coincidencias_relevantes(texto_cuenta, texto_plan)
    if coincidencias_texto:
        incremento = min(18, len(coincidencias_texto) * 4)
        puntaje += incremento
        motivos.append("coincidencias con la cuenta operativa: " + ", ".join(coincidencias_texto[:5]))

    if _texto(cuenta.get("numero_cuenta")) and _texto(cuenta.get("numero_cuenta")) == _texto(plan.get("numero_cuenta")):
        puntaje += 20
        motivos.append("coincide número de cuenta")

    if _texto_upper(cuenta.get("entidad")) and _texto_upper(cuenta.get("entidad")) in _texto_upper(plan.get("banco_nombre") or nombre):
        puntaje += 12
        motivos.append("coincide entidad/banco")

    exclusiones = sorted(palabra for palabra in PALABRAS_EXCLUSION_TESORERIA if palabra in texto_plan)
    if exclusiones and not (tipo == "TARJETA" and "TARJETA" in texto_plan):
        puntaje -= min(35, len(exclusiones) * 10)
        motivos.append("contiene términos no propios de Tesorería: " + ", ".join(exclusiones[:4]))

    if not _cuenta_plan_activa(plan):
        puntaje -= 40
        motivos.append("cuenta del Plan Empresa inactiva")

    if not _es_imputable(plan.get("imputable"), default=True):
        puntaje -= 50
        motivos.append("cuenta del Plan Empresa no imputable")

    puntaje = max(0, min(100, puntaje))
    confianza = _confianza_por_puntaje(puntaje)

    return {
        "cuenta_empresa_id": _obtener_id(plan),
        "codigo": codigo,
        "nombre": nombre,
        "uso_operativo_sistema": uso,
        "puntaje": puntaje,
        "confianza": confianza,
        "motivo": "; ".join(motivos) if motivos else "Sin coincidencias suficientes.",
    }


def _analizar_medios_pago(resultado: Dict[str, Any], medios: Sequence[Dict[str, Any]]) -> None:
    codigos = Counter()

    for medio in medios:
        medio_id = _obtener_id(medio)
        codigo = _texto_upper(medio.get("codigo"))
        nombre = _texto(medio.get("nombre"))
        tipo_actual = _texto_upper(medio.get("tipo_cuenta") or medio.get("tipo_cuenta_tesoreria"))
        activo = _es_activo(medio.get("activo"), True)
        tipo_sugerido = _sugerir_tipo_cuenta_medio(codigo, nombre)
        diagnostico = "OK"
        requiere_revision = False

        if codigo:
            codigos[codigo] += 1

        if activo and tipo_sugerido and tipo_sugerido != "OTRO" and tipo_actual != tipo_sugerido:
            diagnostico = "REVISAR_TIPO_CUENTA"
            requiere_revision = True
            resultado["resumen"]["medios_pago_requieren_revision"] += 1
            _agregar_alerta(
                resultado,
                codigo="TESORERIA_PARAM_MEDIO_PAGO_TIPO_REVISAR",
                severidad="INFORMATIVO",
                titulo="Medio de pago con tipo de cuenta a revisar",
                detalle=f"El medio {codigo or nombre or medio_id} figura como {tipo_actual or 'SIN_TIPO'} y se sugiere {tipo_sugerido}.",
                entidad="tesoreria_medios_pago",
                entidad_id=medio_id,
            )
        elif activo:
            resultado["resumen"]["medios_pago_tipo_ok"] += 1

        if tipo_actual and tipo_actual not in TIPOS_CUENTA_TESORERIA_VALIDOS and tipo_actual != "OTRO":
            diagnostico = "TIPO_DESCONOCIDO"
            requiere_revision = True
            _agregar_alerta(
                resultado,
                codigo="TESORERIA_PARAM_MEDIO_PAGO_TIPO_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Medio de pago con tipo de cuenta desconocido",
                detalle=f"El medio {codigo or nombre or medio_id} usa tipo {tipo_actual}.",
                entidad="tesoreria_medios_pago",
                entidad_id=medio_id,
            )

        resultado["medios_pago"].append(
            {
                "medio_pago_id": medio_id,
                "codigo": codigo,
                "nombre": nombre,
                "tipo_cuenta_actual": tipo_actual,
                "tipo_cuenta_sugerido": tipo_sugerido,
                "activo": activo,
                "diagnostico": diagnostico,
                "requiere_revision": requiere_revision,
            }
        )

    for codigo, cantidad in codigos.items():
        if cantidad > 1:
            _agregar_alerta(
                resultado,
                codigo="TESORERIA_PARAM_MEDIO_PAGO_DUPLICADO",
                severidad="ADVERTENCIA",
                titulo="Medio de pago duplicado",
                detalle=f"El código {codigo} aparece {cantidad} veces en tesoreria_medios_pago.",
                entidad="tesoreria_medios_pago",
            )


def _sugerir_tipo_cuenta_medio(codigo: str, nombre: str) -> str:
    codigo_norm = _texto_upper(codigo).replace(" ", "_").replace("-", "_")
    if codigo_norm in TIPOS_MEDIO_PAGO_REFERENCIA:
        return TIPOS_MEDIO_PAGO_REFERENCIA[codigo_norm]

    texto = _texto_busqueda(codigo, nombre)
    if "EFECTIVO" in texto or "CASH" in texto:
        return "CAJA"
    if "TRANSFER" in texto or "BANCO" in texto or "CBU" in texto or "ALIAS" in texto or "DEBITO" in texto:
        return "BANCO"
    if "ECHEQ" in texto or "CHEQUE" in texto:
        return "VALORES"
    if "BILLETERA" in texto or "MERCADO" in texto or "WALLET" in texto:
        return "BILLETERA"
    if "TARJETA" in texto or "VISA" in texto or "MASTERCARD" in texto or "POSNET" in texto:
        return "TARJETA"
    return "OTRO"


def _armar_matriz_por_tipo(resultado: Dict[str, Any]) -> None:
    matriz: Dict[str, Dict[str, Any]] = {}
    for tipo in sorted(TIPOS_CUENTA_TESORERIA_VALIDOS):
        matriz[tipo] = {
            "cuentas": 0,
            "sin_vinculo": 0,
            "vinculadas_ok": 0,
            "requieren_revision": 0,
            "sugerencias_alta": 0,
            "sugerencias_media": 0,
            "sugerencias_baja": 0,
            "sin_sugerencia": 0,
        }

    for item in resultado.get("cuentas", []):
        tipo = item.get("tipo_cuenta") or "SIN_TIPO"
        matriz.setdefault(
            tipo,
            {
                "cuentas": 0,
                "sin_vinculo": 0,
                "vinculadas_ok": 0,
                "requieren_revision": 0,
                "sugerencias_alta": 0,
                "sugerencias_media": 0,
                "sugerencias_baja": 0,
                "sin_sugerencia": 0,
            },
        )
        matriz[tipo]["cuentas"] += 1
        if item.get("diagnostico") == "VINCULADA_OK":
            matriz[tipo]["vinculadas_ok"] += 1
        if item.get("requiere_revision"):
            matriz[tipo]["requieren_revision"] += 1
        if not item.get("cuenta_contable_codigo_actual"):
            matriz[tipo]["sin_vinculo"] += 1
            confianza = item.get("sugerencia", {}).get("confianza")
            if confianza == "ALTA":
                matriz[tipo]["sugerencias_alta"] += 1
            elif confianza == "MEDIA":
                matriz[tipo]["sugerencias_media"] += 1
            elif confianza == "BAJA":
                matriz[tipo]["sugerencias_baja"] += 1
            else:
                matriz[tipo]["sin_sugerencia"] += 1

    resultado["matriz_por_tipo_cuenta"] = matriz


def _agregar_recomendaciones(resultado: Dict[str, Any]) -> None:
    resumen = resultado["resumen"]
    recomendaciones = resultado["recomendaciones"]

    if resumen["cuentas_sin_vinculo"] > 0:
        recomendaciones.append(
            "Revisar la matriz de sugerencias y dejar para v2B la aceptación auditada de vínculos entre Tesorería y Plan Empresa."
        )

    if resumen["cuentas_vinculadas_requieren_revision"] > 0:
        recomendaciones.append(
            "Corregir vínculos existentes que apunten a cuentas inexistentes, inactivas, no imputables o con uso operativo dudoso antes de automatizar asientos."
        )

    if resumen["medios_pago_requieren_revision"] > 0:
        recomendaciones.append(
            "Normalizar tipo de cuenta sugerido de medios de pago antes de usar Tesorería como capa común de Cobranzas, Pagos, Caja y Banco/Caja."
        )

    if resumen["cuentas_con_sugerencia_alta"] > 0:
        recomendaciones.append(
            "Las sugerencias de confianza alta pueden proponerse primero en v2B, pero siempre con confirmación del usuario y auditoría."
        )

    if not recomendaciones:
        recomendaciones.append(
            "No se detectaron parametrizaciones pendientes relevantes. La siguiente etapa podría preparar aceptación auditada sin tocar movimientos."
        )


def _actualizar_estado_general(resultado: Dict[str, Any]) -> None:
    max_severidad = "OK"
    for alerta in resultado.get("alertas", []):
        severidad = alerta.get("severidad", "OK")
        if SEVERIDAD_ORDEN.get(severidad, 0) > SEVERIDAD_ORDEN.get(max_severidad, 0):
            max_severidad = severidad

    if max_severidad == "CRITICO":
        resultado["estado"] = "CRITICO"
    elif max_severidad == "ADVERTENCIA":
        resultado["estado"] = "REQUIERE_REVISION"
    elif max_severidad == "INFORMATIVO":
        resultado["estado"] = "OK_CON_OBSERVACIONES"
    else:
        resultado["estado"] = "OK"


def _agregar_alerta(
    resultado: Dict[str, Any],
    codigo: str,
    severidad: str,
    titulo: str,
    detalle: str,
    entidad: str = "",
    entidad_id: Any = None,
) -> None:
    resultado["alertas"].append(
        {
            "codigo": codigo,
            "severidad": severidad,
            "titulo": titulo,
            "detalle": detalle,
            "entidad": entidad,
            "entidad_id": entidad_id,
        }
    )


def _sugerencia_vacia() -> Dict[str, Any]:
    return {
        "cuenta_empresa_id": None,
        "codigo": "",
        "nombre": "",
        "uso_operativo_sistema": "",
        "puntaje": 0,
        "confianza": "NULA",
        "motivo": "No se encontró candidata confiable en el Plan Empresa.",
    }


def _confianza_por_puntaje(puntaje: int) -> str:
    if puntaje >= 75:
        return "ALTA"
    if puntaje >= 50:
        return "MEDIA"
    if puntaje >= 25:
        return "BAJA"
    return "NULA"


def _coincidencias_relevantes(texto_cuenta: str, texto_plan: str) -> List[str]:
    stopwords = {
        "DE",
        "DEL",
        "LA",
        "EL",
        "Y",
        "A",
        "EN",
        "POR",
        "PARA",
        "CUENTA",
        "CTA",
        "GENERAL",
        "PRINCIPAL",
        "ARS",
    }
    tokens = []
    for token in texto_cuenta.split():
        token = token.strip(".,;:/_-()[]{}")
        if len(token) < 3 or token in stopwords:
            continue
        if token in texto_plan and token not in tokens:
            tokens.append(token)
    return tokens


def _texto_busqueda(*valores: Any) -> str:
    partes = [_texto_upper(valor) for valor in valores if _texto(valor)]
    texto = " ".join(partes)
    for caracter in ".,;:/_-()[]{}#":
        texto = texto.replace(caracter, " ")
    return " ".join(texto.split())


def _cuenta_plan_activa(plan: Dict[str, Any]) -> bool:
    estado = _texto_upper(plan.get("estado") or "ACTIVA")
    if estado in {"ANULADO", "ANULADA", "INACTIVO", "INACTIVA", "BAJA", "ELIMINADO", "ELIMINADA"}:
        return False
    return True


def _codigo_plan(plan: Dict[str, Any]) -> str:
    return _texto(plan.get("codigo") or plan.get("cuenta_codigo") or plan.get("codigo_cuenta"))


def _nombre_plan(plan: Dict[str, Any]) -> str:
    return _texto(plan.get("nombre") or plan.get("cuenta_nombre") or plan.get("nombre_cuenta"))


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


def _obtener_id(fila: Dict[str, Any]) -> Any:
    for clave in ("id", "cuenta_id", "cuenta_tesoreria_id", "medio_pago_id", "cuenta_empresa_id"):
        if clave in fila and fila.get(clave) is not None:
            return fila.get(clave)
    return None
