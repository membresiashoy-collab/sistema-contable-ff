from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIPOS_CUENTA_TESORERIA_VALIDOS = {
    "BANCO",
    "CAJA",
    "BILLETERA",
    "TARJETA",
    "VALORES",
}

TIPOS_OPERACION_TESORERIA_REFERENCIA = {
    "COBRANZA",
    "PAGO",
    "CAJA",
    "BANCO",
    "TRANSFERENCIA",
    "DEPOSITO",
    "RETIRO",
    "AJUSTE",
    "CONCILIACION",
    "OTRO",
}

ESTADOS_OPERACION_VALIDOS = {
    "CONFIRMADA",
    "BORRADOR",
    "ANULADA",
}

ESTADOS_CONCILIACION_VALIDOS = {
    "PENDIENTE",
    "SUGERIDA",
    "PARCIAL",
    "CONCILIADA",
    "NO_CONCILIABLE",
}

SEVERIDAD_ORDEN = {
    "OK": 0,
    "INFORMATIVO": 1,
    "ADVERTENCIA": 2,
    "CRITICO": 3,
}

COLUMNAS_ORIGEN_OPERATIVO = (
    "origen",
    "origen_modulo",
    "modulo_origen",
    "origen_tipo",
    "tipo_origen",
    "referencia_origen",
    "documento_origen",
    "comprobante_origen",
)

USOS_ESPERADOS_POR_TIPO_CUENTA = {
    "CAJA": {"CAJA", "CAJA_GENERAL", "FONDO_FIJO", "RECAUDACIONES_A_DEPOSITAR"},
    "BANCO": {"BANCO", "BANCO_CUENTA_CORRIENTE", "BANCO_CAJA_AHORRO"},
    "BILLETERA": {"BILLETERA", "BILLETERA_VIRTUAL"},
    "TARJETA": {"TARJETA", "TARJETA_COBROS", "TARJETA_PUENTE"},
    "VALORES": {"VALORES", "VALORES_A_DEPOSITAR", "CHEQUES", "ECHEQ"},
}


def diagnosticar_tesoreria(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Diagnóstico integral de Tesorería PRO v1.

    Este servicio es deliberadamente de solo lectura:
    - no ejecuta migraciones;
    - no llama a inicializar_tesoreria();
    - no crea medios de pago;
    - no crea ni vincula cuentas;
    - no registra, concilia ni anula operaciones.

    Si se pasa ``conexion`` usa esa conexión sin cerrarla.
    Si no se pasa, intenta abrir una conexión de lectura usando helpers conocidos
    del proyecto y, como último recurso, rutas SQLite habituales del repositorio.
    """

    empresa_id = int(empresa_id or 1)
    cerrar_conexion = conexion is None
    con = conexion or _obtener_conexion()

    try:
        _configurar_conexion(con)

        diagnostico: Dict[str, Any] = {
            "empresa_id": empresa_id,
            "estado": "OK",
            "resumen": {
                "tablas_requeridas": 5,
                "tablas_detectadas": 0,
                "cuentas_tesoreria": 0,
                "cuentas_activas": 0,
                "cuentas_sin_cuenta_contable": 0,
                "cuentas_con_plan_incompatible": 0,
                "medios_pago": 0,
                "medios_pago_activos": 0,
                "operaciones": 0,
                "operaciones_confirmadas": 0,
                "operaciones_pendientes_conciliacion": 0,
                "operaciones_conciliadas": 0,
                "operaciones_no_conciliables": 0,
                "operaciones_anuladas": 0,
                "operaciones_sin_componentes": 0,
                "operaciones_sin_fingerprint": 0,
                "operaciones_duplicadas_potenciales": 0,
            },
            "tablas": {},
            "cuentas_tesoreria": [],
            "medios_pago": [],
            "operaciones": {
                "totales_por_tipo": {},
                "totales_por_estado": {},
                "totales_por_conciliacion": {},
                "pendientes_conciliacion": [],
                "anuladas": [],
                "sin_componentes": [],
                "sin_fingerprint": [],
                "duplicadas_potenciales": [],
                "sin_origen": [],
            },
            "componentes": {
                "total": 0,
                "operaciones_con_componentes": 0,
                "operaciones_sin_componentes": 0,
            },
            "origenes_operativos": {},
            "alertas": [],
            "recomendaciones": [],
            "solo_lectura": True,
        }

        tablas_requeridas = (
            "tesoreria_cuentas",
            "tesoreria_medios_pago",
            "tesoreria_operaciones",
            "tesoreria_operaciones_componentes",
            "plan_cuentas_empresa",
        )

        for tabla in tablas_requeridas:
            existe = _tabla_existe(con, tabla)
            diagnostico["tablas"][tabla] = {
                "existe": existe,
                "columnas": _columnas_tabla(con, tabla) if existe else [],
            }
            if existe:
                diagnostico["resumen"]["tablas_detectadas"] += 1
            else:
                _agregar_alerta(
                    diagnostico,
                    codigo="TESORERIA_TABLA_INEXISTENTE",
                    severidad="CRITICO" if tabla in {"tesoreria_cuentas", "tesoreria_operaciones"} else "ADVERTENCIA",
                    titulo=f"No existe la tabla {tabla}",
                    detalle=(
                        "El diagnóstico no ejecuta migraciones ni inicializaciones. "
                        "La ausencia de esta tabla debe resolverse fuera de Tesorería PRO v1."
                    ),
                    entidad=tabla,
                )

        plan_por_codigo = _leer_plan_empresa_por_codigo(con, empresa_id)
        cuentas = _leer_cuentas_tesoreria(con, empresa_id)
        medios = _leer_medios_pago(con, empresa_id)
        operaciones = _leer_operaciones_tesoreria(con, empresa_id)
        componentes_por_operacion, total_componentes = _leer_componentes_por_operacion(con, empresa_id)

        diagnostico["resumen"]["cuentas_tesoreria"] = len(cuentas)
        diagnostico["resumen"]["cuentas_activas"] = sum(1 for cuenta in cuentas if _es_activo(cuenta.get("activo"), default=True))
        diagnostico["resumen"]["medios_pago"] = len(medios)
        diagnostico["resumen"]["medios_pago_activos"] = sum(1 for medio in medios if _es_activo(medio.get("activo"), default=True))
        diagnostico["resumen"]["operaciones"] = len(operaciones)
        diagnostico["componentes"]["total"] = total_componentes

        _diagnosticar_cuentas(diagnostico, cuentas, plan_por_codigo)
        _diagnosticar_medios_pago(diagnostico, medios)
        _diagnosticar_operaciones(diagnostico, operaciones, componentes_por_operacion)
        _diagnosticar_origenes(diagnostico, operaciones)
        _agregar_recomendaciones(diagnostico)
        _actualizar_estado_general(diagnostico)

        return diagnostico
    finally:
        if cerrar_conexion:
            con.close()


def obtener_alertas_tesoreria(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Devuelve únicamente las alertas del diagnóstico de Tesorería."""
    return diagnosticar_tesoreria(empresa_id=empresa_id, conexion=conexion).get("alertas", [])


def obtener_resumen_tesoreria(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Devuelve únicamente el resumen del diagnóstico de Tesorería."""
    return diagnosticar_tesoreria(empresa_id=empresa_id, conexion=conexion).get("resumen", {})


def _obtener_conexion() -> sqlite3.Connection:
    """
    Intenta integrarse con helpers habituales del proyecto sin acoplar el servicio
    a un módulo operativo. Si no encuentra helper, usa rutas SQLite frecuentes.
    """

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

    raise RuntimeError(
        "No se pudo obtener una conexión SQLite para diagnosticar Tesorería. "
        "Pase una conexión explícita con diagnosticar_tesoreria(..., conexion=con)."
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


def _leer_plan_empresa_por_codigo(con: sqlite3.Connection, empresa_id: int) -> Dict[str, Dict[str, Any]]:
    filas = _leer_filas_empresa(con, "plan_cuentas_empresa", empresa_id)
    plan = {}
    for fila in filas:
        codigo = _texto(fila.get("codigo") or fila.get("cuenta_codigo"))
        if codigo:
            plan[codigo] = fila
    return plan


def _leer_cuentas_tesoreria(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    return _leer_filas_empresa(con, "tesoreria_cuentas", empresa_id)


def _leer_medios_pago(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    return _leer_filas_empresa(con, "tesoreria_medios_pago", empresa_id)


def _leer_operaciones_tesoreria(con: sqlite3.Connection, empresa_id: int) -> List[Dict[str, Any]]:
    return _leer_filas_empresa(con, "tesoreria_operaciones", empresa_id)


def _leer_componentes_por_operacion(con: sqlite3.Connection, empresa_id: int) -> Tuple[Dict[int, int], int]:
    filas = _leer_filas_empresa(con, "tesoreria_operaciones_componentes", empresa_id)
    conteo = defaultdict(int)

    for fila in filas:
        operacion_id = _obtener_id_operacion_desde_componente(fila)
        if operacion_id is not None:
            conteo[int(operacion_id)] += 1

    return dict(conteo), len(filas)


def _diagnosticar_cuentas(
    diagnostico: Dict[str, Any],
    cuentas: Sequence[Dict[str, Any]],
    plan_por_codigo: Dict[str, Dict[str, Any]],
) -> None:
    for cuenta in cuentas:
        tipo = _texto_upper(cuenta.get("tipo_cuenta"))
        codigo = _texto(cuenta.get("cuenta_contable_codigo"))
        nombre = _texto(cuenta.get("nombre"))
        activa = _es_activo(cuenta.get("activo"), default=True)
        plan = plan_por_codigo.get(codigo) if codigo else None

        item = {
            "cuenta_tesoreria_id": _obtener_id(cuenta),
            "tipo_cuenta": tipo,
            "nombre": nombre,
            "activo": activa,
            "cuenta_contable_codigo": codigo,
            "cuenta_contable_nombre": _texto(cuenta.get("cuenta_contable_nombre")),
            "plan_encontrado": plan is not None,
            "diagnostico_plan": "SIN_CUENTA_CONTABLE" if not codigo else "OK",
        }

        if tipo and tipo not in TIPOS_CUENTA_TESORERIA_VALIDOS:
            item["diagnostico_plan"] = "TIPO_CUENTA_DESCONOCIDO"
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_TIPO_CUENTA_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Cuenta de Tesorería con tipo no reconocido",
                detalle=f"La cuenta {nombre or item['cuenta_tesoreria_id']} tiene tipo {tipo}.",
                entidad="tesoreria_cuentas",
                entidad_id=item["cuenta_tesoreria_id"],
            )

        if activa and not codigo:
            diagnostico["resumen"]["cuentas_sin_cuenta_contable"] += 1
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_CUENTA_SIN_CUENTA_CONTABLE",
                severidad="ADVERTENCIA",
                titulo="Cuenta activa de Tesorería sin cuenta contable vinculada",
                detalle=(
                    f"La cuenta {nombre or item['cuenta_tesoreria_id']} está activa "
                    "pero no tiene cuenta_contable_codigo."
                ),
                entidad="tesoreria_cuentas",
                entidad_id=item["cuenta_tesoreria_id"],
            )

        if codigo and plan is None:
            item["diagnostico_plan"] = "CUENTA_PLAN_NO_ENCONTRADA"
            diagnostico["resumen"]["cuentas_con_plan_incompatible"] += 1
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_CUENTA_PLAN_NO_ENCONTRADA",
                severidad="ADVERTENCIA",
                titulo="Cuenta contable vinculada no encontrada en Plan Empresa",
                detalle=(
                    f"La cuenta de Tesorería {nombre or item['cuenta_tesoreria_id']} "
                    f"apunta al código {codigo}, pero no se encontró en plan_cuentas_empresa."
                ),
                entidad="tesoreria_cuentas",
                entidad_id=item["cuenta_tesoreria_id"],
            )

        if plan is not None:
            problemas = _validar_plan_para_cuenta_tesoreria(plan, tipo)
            if problemas:
                item["diagnostico_plan"] = "CUENTA_PLAN_REQUIERE_REVISION"
                diagnostico["resumen"]["cuentas_con_plan_incompatible"] += 1
                for problema in problemas:
                    _agregar_alerta(
                        diagnostico,
                        codigo=problema["codigo"],
                        severidad=problema["severidad"],
                        titulo=problema["titulo"],
                        detalle=(
                            f"La cuenta de Tesorería {nombre or item['cuenta_tesoreria_id']} "
                            f"está vinculada a {codigo}. {problema['detalle']}"
                        ),
                        entidad="tesoreria_cuentas",
                        entidad_id=item["cuenta_tesoreria_id"],
                    )

        diagnostico["cuentas_tesoreria"].append(item)


def _validar_plan_para_cuenta_tesoreria(plan: Dict[str, Any], tipo_cuenta: str) -> List[Dict[str, str]]:
    problemas: List[Dict[str, str]] = []

    estado = _texto_upper(plan.get("estado") or "ACTIVA")
    if estado in {"ANULADO", "ANULADA", "INACTIVO", "INACTIVA", "BAJA", "ELIMINADO", "ELIMINADA"}:
        problemas.append(
            {
                "codigo": "TESORERIA_CUENTA_CONTABLE_INACTIVA",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta contable vinculada inactiva o anulada",
                "detalle": "La cuenta del Plan Empresa no está activa.",
            }
        )

    if not _es_imputable(plan.get("imputable"), default=True):
        problemas.append(
            {
                "codigo": "TESORERIA_CUENTA_CONTABLE_NO_IMPUTABLE",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta contable vinculada no imputable",
                "detalle": "Tesorería debería vincularse a cuentas imputables/específicas.",
            }
        )

    uso = _normalizar_uso_operativo(plan.get("uso_operativo_sistema"))
    usos_esperados = USOS_ESPERADOS_POR_TIPO_CUENTA.get(tipo_cuenta, set())
    if uso and usos_esperados and uso not in usos_esperados:
        problemas.append(
            {
                "codigo": "TESORERIA_CUENTA_TIPO_INCOMPATIBLE_PLAN",
                "severidad": "INFORMATIVO",
                "titulo": "Uso operativo del Plan Empresa no coincide con el tipo de Tesorería",
                "detalle": (
                    f"Uso operativo detectado: {uso}. "
                    f"Usos esperados para {tipo_cuenta}: {', '.join(sorted(usos_esperados))}."
                ),
            }
        )

    return problemas


def _diagnosticar_medios_pago(diagnostico: Dict[str, Any], medios: Sequence[Dict[str, Any]]) -> None:
    codigos = Counter()

    for medio in medios:
        codigo = _texto_upper(medio.get("codigo"))
        activo = _es_activo(medio.get("activo"), default=True)
        tipo_cuenta = _texto_upper(medio.get("tipo_cuenta") or medio.get("tipo_cuenta_tesoreria"))

        item = {
            "medio_pago_id": _obtener_id(medio),
            "codigo": codigo,
            "nombre": _texto(medio.get("nombre")),
            "tipo_cuenta": tipo_cuenta,
            "activo": activo,
        }
        diagnostico["medios_pago"].append(item)

        if codigo:
            codigos[codigo] += 1

        if activo and tipo_cuenta and tipo_cuenta not in TIPOS_CUENTA_TESORERIA_VALIDOS and tipo_cuenta != "OTRO":
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_MEDIO_PAGO_TIPO_CUENTA_DESCONOCIDO",
                severidad="INFORMATIVO",
                titulo="Medio de pago con tipo de cuenta no reconocido",
                detalle=f"El medio {codigo or item['medio_pago_id']} usa tipo {tipo_cuenta}.",
                entidad="tesoreria_medios_pago",
                entidad_id=item["medio_pago_id"],
            )

        if not activo:
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_MEDIO_PAGO_INACTIVO",
                severidad="INFORMATIVO",
                titulo="Medio de pago inactivo",
                detalle=f"El medio {codigo or item['medio_pago_id']} figura inactivo.",
                entidad="tesoreria_medios_pago",
                entidad_id=item["medio_pago_id"],
            )

    for codigo, cantidad in codigos.items():
        if cantidad > 1:
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_MEDIO_PAGO_DUPLICADO",
                severidad="ADVERTENCIA",
                titulo="Código de medio de pago duplicado",
                detalle=f"El código {codigo} aparece {cantidad} veces.",
                entidad="tesoreria_medios_pago",
            )


def _diagnosticar_operaciones(
    diagnostico: Dict[str, Any],
    operaciones: Sequence[Dict[str, Any]],
    componentes_por_operacion: Dict[int, int],
) -> None:
    tipos = Counter()
    estados = Counter()
    conciliaciones = Counter()
    fingerprints = defaultdict(list)

    for operacion in operaciones:
        operacion_id = _obtener_id(operacion)
        tipo = _texto_upper(operacion.get("tipo_operacion"))
        estado = _texto_upper(operacion.get("estado") or "CONFIRMADA")
        estado_conciliacion = _texto_upper(operacion.get("estado_conciliacion") or "PENDIENTE")
        fingerprint = _texto(operacion.get("fingerprint") or operacion.get("huella") or operacion.get("hash_operacion"))
        cantidad_componentes = componentes_por_operacion.get(int(operacion_id or 0), 0)

        tipos[tipo or "SIN_TIPO"] += 1
        estados[estado or "SIN_ESTADO"] += 1
        conciliaciones[estado_conciliacion or "SIN_ESTADO_CONCILIACION"] += 1

        if fingerprint:
            fingerprints[fingerprint].append(operacion_id)

        if estado == "CONFIRMADA":
            diagnostico["resumen"]["operaciones_confirmadas"] += 1

        if estado == "ANULADA":
            diagnostico["resumen"]["operaciones_anuladas"] += 1
            anulada = _resumen_operacion(operacion)
            diagnostico["operaciones"]["anuladas"].append(anulada)
            if not _texto(operacion.get("motivo_anulacion")):
                _agregar_alerta(
                    diagnostico,
                    codigo="TESORERIA_OPERACION_ANULADA_SIN_MOTIVO",
                    severidad="ADVERTENCIA",
                    titulo="Operación anulada sin motivo visible",
                    detalle=f"La operación {operacion_id} está anulada pero no expone motivo_anulacion.",
                    entidad="tesoreria_operaciones",
                    entidad_id=operacion_id,
                )

        if estado_conciliacion in {"PENDIENTE", "SUGERIDA", "PARCIAL"} and estado != "ANULADA":
            diagnostico["resumen"]["operaciones_pendientes_conciliacion"] += 1
            diagnostico["operaciones"]["pendientes_conciliacion"].append(_resumen_operacion(operacion))

        if estado_conciliacion == "CONCILIADA":
            diagnostico["resumen"]["operaciones_conciliadas"] += 1

        if estado_conciliacion == "NO_CONCILIABLE":
            diagnostico["resumen"]["operaciones_no_conciliables"] += 1

        if tipo and tipo not in TIPOS_OPERACION_TESORERIA_REFERENCIA:
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_TIPO_OPERACION_NO_CATALOGADO_DIAGNOSTICO",
                severidad="INFORMATIVO",
                titulo="Tipo de operación no catalogado por el diagnóstico",
                detalle=f"La operación {operacion_id} tiene tipo {tipo}. Revise si debe incorporarse al catálogo diagnóstico.",
                entidad="tesoreria_operaciones",
                entidad_id=operacion_id,
            )

        if estado and estado not in ESTADOS_OPERACION_VALIDOS:
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_ESTADO_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Estado de operación no reconocido",
                detalle=f"La operación {operacion_id} tiene estado {estado}.",
                entidad="tesoreria_operaciones",
                entidad_id=operacion_id,
            )

        if estado_conciliacion and estado_conciliacion not in ESTADOS_CONCILIACION_VALIDOS:
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_CONCILIACION_ESTADO_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Estado de conciliación no reconocido",
                detalle=f"La operación {operacion_id} tiene estado_conciliacion {estado_conciliacion}.",
                entidad="tesoreria_operaciones",
                entidad_id=operacion_id,
            )

        if cantidad_componentes <= 0 and estado != "ANULADA":
            diagnostico["resumen"]["operaciones_sin_componentes"] += 1
            diagnostico["operaciones"]["sin_componentes"].append(_resumen_operacion(operacion))
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_OPERACION_SIN_COMPONENTES",
                severidad="INFORMATIVO",
                titulo="Operación sin componentes contables auxiliares",
                detalle=(
                    f"La operación {operacion_id} no tiene componentes en tesoreria_operaciones_componentes. "
                    "Puede ser válido en registros antiguos, pero debe revisarse antes de futura Bandeja."
                ),
                entidad="tesoreria_operaciones",
                entidad_id=operacion_id,
            )

        if not fingerprint and estado != "ANULADA":
            diagnostico["resumen"]["operaciones_sin_fingerprint"] += 1
            diagnostico["operaciones"]["sin_fingerprint"].append(_resumen_operacion(operacion))
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_OPERACION_SIN_FINGERPRINT",
                severidad="INFORMATIVO",
                titulo="Operación sin fingerprint operativo",
                detalle=(
                    f"La operación {operacion_id} no expone fingerprint. "
                    "Esto puede dificultar controles de duplicidad."
                ),
                entidad="tesoreria_operaciones",
                entidad_id=operacion_id,
            )

    duplicadas = {
        fingerprint: ids
        for fingerprint, ids in fingerprints.items()
        if len([x for x in ids if x is not None]) > 1
    }

    for fingerprint, ids in duplicadas.items():
        diagnostico["resumen"]["operaciones_duplicadas_potenciales"] += len(ids)
        diagnostico["operaciones"]["duplicadas_potenciales"].append(
            {
                "fingerprint": fingerprint,
                "operaciones_ids": ids,
                "cantidad": len(ids),
            }
        )
        _agregar_alerta(
            diagnostico,
            codigo="TESORERIA_OPERACION_DUPLICADA_POTENCIAL",
            severidad="ADVERTENCIA",
            titulo="Potencial duplicidad de operaciones por fingerprint",
            detalle=f"El fingerprint {fingerprint} aparece en operaciones {ids}.",
            entidad="tesoreria_operaciones",
        )

    diagnostico["operaciones"]["totales_por_tipo"] = dict(sorted(tipos.items()))
    diagnostico["operaciones"]["totales_por_estado"] = dict(sorted(estados.items()))
    diagnostico["operaciones"]["totales_por_conciliacion"] = dict(sorted(conciliaciones.items()))
    diagnostico["componentes"]["operaciones_con_componentes"] = len(
        [op for op in operaciones if componentes_por_operacion.get(int(_obtener_id(op) or 0), 0) > 0]
    )
    diagnostico["componentes"]["operaciones_sin_componentes"] = diagnostico["resumen"]["operaciones_sin_componentes"]


def _diagnosticar_origenes(diagnostico: Dict[str, Any], operaciones: Sequence[Dict[str, Any]]) -> None:
    origenes = Counter()

    for operacion in operaciones:
        origen = _detectar_origen_operativo(operacion)
        estado = _texto_upper(operacion.get("estado") or "CONFIRMADA")

        if origen:
            origenes[origen] += 1
        elif estado != "ANULADA":
            diagnostico["operaciones"]["sin_origen"].append(_resumen_operacion(operacion))
            _agregar_alerta(
                diagnostico,
                codigo="TESORERIA_OPERACION_SIN_ORIGEN",
                severidad="INFORMATIVO",
                titulo="Operación sin origen operativo explícito",
                detalle=(
                    f"La operación {_obtener_id(operacion)} no expone columnas de origen reconocibles. "
                    "Antes de integrar Bandeja conviene preservar origen, módulo y referencia."
                ),
                entidad="tesoreria_operaciones",
                entidad_id=_obtener_id(operacion),
            )

    diagnostico["origenes_operativos"] = dict(sorted(origenes.items()))


def _detectar_origen_operativo(operacion: Dict[str, Any]) -> str:
    for columna in COLUMNAS_ORIGEN_OPERATIVO:
        valor = _texto_upper(operacion.get(columna))
        if valor:
            return valor

    return ""


def _agregar_recomendaciones(diagnostico: Dict[str, Any]) -> None:
    resumen = diagnostico["resumen"]
    recomendaciones = diagnostico["recomendaciones"]

    if resumen["cuentas_sin_cuenta_contable"] > 0:
        recomendaciones.append(
            "Vincular cuentas activas de Tesorería al Plan Empresa antes de permitir impacto contable automático."
        )

    if resumen["cuentas_con_plan_incompatible"] > 0:
        recomendaciones.append(
            "Revisar cuentas de Tesorería vinculadas a cuentas inactivas, no imputables o no encontradas en Plan Empresa."
        )

    if resumen["operaciones_pendientes_conciliacion"] > 0:
        recomendaciones.append(
            "Mantener separada la conciliación bancaria de la registración contable hasta resolver pendientes."
        )

    if resumen["operaciones_sin_componentes"] > 0:
        recomendaciones.append(
            "Antes de futura Bandeja, definir si las operaciones históricas sin componentes deben quedar como informativas o reconstruirse."
        )

    if resumen["operaciones_sin_fingerprint"] > 0:
        recomendaciones.append(
            "Normalizar fingerprint/origen en nuevas operaciones para reducir riesgo de duplicidad."
        )

    if not recomendaciones:
        recomendaciones.append(
            "No se detectaron riesgos críticos en la lectura inicial. La siguiente etapa podría parametrizar reglas sin tocar operatoria."
        )


def _actualizar_estado_general(diagnostico: Dict[str, Any]) -> None:
    max_severidad = "OK"
    for alerta in diagnostico.get("alertas", []):
        severidad = alerta.get("severidad", "OK")
        if SEVERIDAD_ORDEN.get(severidad, 0) > SEVERIDAD_ORDEN.get(max_severidad, 0):
            max_severidad = severidad

    if max_severidad == "CRITICO":
        diagnostico["estado"] = "CRITICO"
    elif max_severidad == "ADVERTENCIA":
        diagnostico["estado"] = "REQUIERE_REVISION"
    elif max_severidad == "INFORMATIVO":
        diagnostico["estado"] = "OK_CON_OBSERVACIONES"
    else:
        diagnostico["estado"] = "OK"


def _agregar_alerta(
    diagnostico: Dict[str, Any],
    codigo: str,
    severidad: str,
    titulo: str,
    detalle: str,
    entidad: str = "",
    entidad_id: Any = None,
) -> None:
    diagnostico["alertas"].append(
        {
            "codigo": codigo,
            "severidad": severidad,
            "titulo": titulo,
            "detalle": detalle,
            "entidad": entidad,
            "entidad_id": entidad_id,
        }
    )


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
            valor = valor.replace(".", "").replace(",", ".") if "," in valor else valor
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


def _obtener_id(fila: Dict[str, Any]) -> Any:
    for clave in ("id", "operacion_id", "cuenta_id", "cuenta_tesoreria_id", "medio_pago_id"):
        if clave in fila and fila.get(clave) is not None:
            return fila.get(clave)
    return None


def _obtener_id_operacion_desde_componente(fila: Dict[str, Any]) -> Optional[int]:
    for clave in ("operacion_id", "tesoreria_operacion_id", "operacion_tesoreria_id"):
        valor = fila.get(clave)
        if valor is not None:
            try:
                return int(valor)
            except Exception:
                return None
    return None


def _resumen_operacion(operacion: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "operacion_id": _obtener_id(operacion),
        "fecha": _texto(operacion.get("fecha")),
        "tipo_operacion": _texto_upper(operacion.get("tipo_operacion")),
        "descripcion": _texto(operacion.get("descripcion") or operacion.get("detalle")),
        "importe": _numero(operacion.get("importe") or operacion.get("monto") or operacion.get("total")),
        "estado": _texto_upper(operacion.get("estado") or "CONFIRMADA"),
        "estado_conciliacion": _texto_upper(operacion.get("estado_conciliacion") or "PENDIENTE"),
        "cuenta_tesoreria_id": operacion.get("cuenta_tesoreria_id"),
        "medio_pago_id": operacion.get("medio_pago_id"),
        "fingerprint": _texto(operacion.get("fingerprint") or operacion.get("huella") or operacion.get("hash_operacion")),
    }
