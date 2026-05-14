from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ESTADOS_CONCILIACION_BANCO_VALIDOS = {
    "PENDIENTE",
    "PARCIAL",
    "CONCILIADO",
    "NO_CONCILIABLE",
}

ESTADOS_CONTABLE_BANCO_VALIDOS = {
    "NO_CONTABILIZADO",
    "ASIENTO_PROPUESTO",
    "ASIENTO_PROPUESTO_AGRUPADO",
    "ASIENTO_CONTABILIZADO",
    "ASIENTO_CONFIRMADO",
    "CONTABILIZADO",
    "ANULADO",
}

ESTADOS_CONCILIACION_REGISTRO_VALIDOS = {
    "BORRADOR",
    "PENDIENTE",
    "CONFIRMADA",
    "PARCIAL",
    "ANULADA",
}

TIPOS_MOVIMIENTO_BANCO_REFERENCIA = {
    "GASTO_BANCARIO_GRAVADO",
    "IVA_CREDITO_FISCAL_BANCARIO",
    "PERCEPCION_IVA_BANCARIA",
    "RECAUDACION_IIBB",
    "IMPUESTO_DEBITOS_CREDITOS",
    "PAGO_IMPUESTOS",
    "TRANSFERENCIA_ENTRE_CUENTAS",
    "EFECTIVO_CAJA",
    "MOVIMIENTO_SOCIOS",
    "COBRO_POSIBLE",
    "PAGO_POSIBLE",
    "OTRO_GASTO_A_REVISAR",
    "A_REVISAR",
}

TIPOS_CONCILIACION_BANCARIA_REFERENCIA = {
    "TESORERIA_OPERACION",
    "COBRO_CLIENTE",
    "PAGO_PROVEEDOR",
    "PAGO_FISCAL",
}

USOS_OPERATIVOS_BANCO = {
    "BANCO",
    "BANCO_CUENTA_CORRIENTE",
    "BANCO_CAJA_AHORRO",
}

SEVERIDAD_ORDEN = {
    "OK": 0,
    "INFORMATIVO": 1,
    "ADVERTENCIA": 2,
    "CRITICO": 3,
}


REQUIRED_TABLES = (
    "bancos_cuentas",
    "bancos_importaciones",
    "bancos_movimientos",
    "bancos_conciliaciones",
    "bancos_conciliaciones_detalle",
    "bancos_grupos_fiscales",
    "bancos_asientos_propuestos",
    "plan_cuentas_empresa",
)


def diagnosticar_bancos(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Diagnóstico contable-operativo integral Banco/Caja PRO v1.

    Este servicio es deliberadamente de solo lectura:
    - no llama a inicializar_bancos();
    - no ejecuta migraciones;
    - no importa extractos;
    - no genera grupos fiscales;
    - no genera asientos propuestos;
    - no concilia, no desimputa y no actualiza movimientos.

    Si se pasa ``conexion`` usa esa conexión sin cerrarla. Si no se pasa,
    intenta obtener una conexión SQLite con helpers habituales del proyecto.
    """

    empresa_id = int(empresa_id or 1)
    cerrar_conexion = conexion is None
    con = conexion or _obtener_conexion()

    try:
        _configurar_conexion(con)

        diagnostico: Dict[str, Any] = {
            "empresa_id": empresa_id,
            "estado": "OK",
            "solo_lectura": True,
            "resumen": {
                "tablas_requeridas": len(REQUIRED_TABLES),
                "tablas_detectadas": 0,
                "cuentas_bancarias": 0,
                "cuentas_bancarias_sin_cuenta_contable": 0,
                "cuentas_bancarias_con_plan_incompatible": 0,
                "importaciones": 0,
                "importaciones_con_diferencia_saldo": 0,
                "importaciones_duplicadas_sin_movimientos": 0,
                "movimientos": 0,
                "movimientos_pendientes": 0,
                "movimientos_parciales": 0,
                "movimientos_conciliados": 0,
                "movimientos_sin_clave": 0,
                "movimientos_duplicados_potenciales": 0,
                "movimientos_con_saldo_pendiente_inconsistente": 0,
                "movimientos_con_estado_desconocido": 0,
                "movimientos_con_cuentas_plan_incompatibles": 0,
                "grupos_fiscales": 0,
                "grupos_fiscales_pendientes": 0,
                "asientos_propuestos": 0,
                "asientos_propuestos_desbalanceados": 0,
                "conciliaciones": 0,
                "conciliaciones_activas": 0,
                "conciliaciones_anuladas": 0,
                "conciliaciones_activas_sin_detalle": 0,
                "detalles_huerfanos": 0,
            },
            "tablas": {},
            "cuentas_bancarias": [],
            "importaciones": {
                "por_banco_cuenta": {},
                "con_diferencia_saldo": [],
                "duplicadas_sin_movimientos": [],
            },
            "movimientos": {
                "por_tipo": {},
                "por_estado_conciliacion": {},
                "por_estado_contable": {},
                "pendientes": [],
                "parciales": [],
                "sin_clave": [],
                "duplicados_potenciales": [],
                "saldo_pendiente_inconsistente": [],
                "estado_desconocido": [],
                "cuentas_plan_incompatibles": [],
            },
            "fiscal": {
                "grupos_por_estado": {},
                "grupos_pendientes": [],
                "total_iva_credito": 0.0,
                "total_percepcion_iva": 0.0,
                "total_percepcion_iibb": 0.0,
                "total_banco_fiscal": 0.0,
            },
            "asientos_propuestos": {
                "por_estado": {},
                "desbalanceados_por_movimiento": [],
            },
            "conciliaciones": {
                "por_tipo": {},
                "por_estado": {},
                "activas_sin_detalle": [],
                "detalles_huerfanos": [],
                "detalles_sin_movimiento": [],
            },
            "alertas": [],
            "recomendaciones": [],
        }

        for tabla in REQUIRED_TABLES:
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
                    codigo="BANCO_CAJA_TABLA_INEXISTENTE",
                    severidad="CRITICO" if tabla in {"bancos_movimientos", "bancos_importaciones"} else "ADVERTENCIA",
                    titulo=f"No existe la tabla {tabla}",
                    detalle=(
                        "El diagnóstico no ejecuta migraciones ni inicializaciones. "
                        "La ausencia debe resolverse desde la etapa operativa correspondiente."
                    ),
                    entidad=tabla,
                )

        plan_por_codigo = _leer_plan_empresa_por_codigo(con, empresa_id)
        cuentas = _leer_filas_empresa(con, "bancos_cuentas", empresa_id)
        importaciones = _leer_filas_empresa(con, "bancos_importaciones", empresa_id)
        movimientos = _leer_filas_empresa(con, "bancos_movimientos", empresa_id)
        grupos_fiscales = _leer_filas_empresa(con, "bancos_grupos_fiscales", empresa_id)
        asientos = _leer_filas_empresa(con, "bancos_asientos_propuestos", empresa_id)
        conciliaciones = _leer_filas_empresa(con, "bancos_conciliaciones", empresa_id)
        detalles = _leer_filas_empresa(con, "bancos_conciliaciones_detalle", empresa_id)

        diagnostico["resumen"]["cuentas_bancarias"] = len(cuentas)
        diagnostico["resumen"]["importaciones"] = len(importaciones)
        diagnostico["resumen"]["movimientos"] = len(movimientos)
        diagnostico["resumen"]["grupos_fiscales"] = len(grupos_fiscales)
        diagnostico["resumen"]["asientos_propuestos"] = len(asientos)
        diagnostico["resumen"]["conciliaciones"] = len(conciliaciones)

        _diagnosticar_cuentas_bancarias(diagnostico, cuentas, plan_por_codigo)
        _diagnosticar_importaciones(diagnostico, importaciones, movimientos)
        _diagnosticar_movimientos(diagnostico, movimientos, plan_por_codigo)
        _diagnosticar_fiscal(diagnostico, grupos_fiscales)
        _diagnosticar_asientos(diagnostico, asientos)
        _diagnosticar_conciliaciones(diagnostico, conciliaciones, detalles, movimientos)
        _agregar_recomendaciones(diagnostico)
        _actualizar_estado_general(diagnostico)

        return diagnostico
    finally:
        if cerrar_conexion:
            con.close()


def diagnosticar_banco_caja(empresa_id: int = 1, conexion: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Alias explícito para uso UI/futuro."""

    return diagnosticar_bancos(empresa_id=empresa_id, conexion=conexion)


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

    raise RuntimeError(
        "No se pudo obtener una conexión SQLite para diagnosticar Banco/Caja. "
        "Pase una conexión explícita con diagnosticar_bancos(..., conexion=con)."
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
        cur.execute(f"SELECT * FROM {_identificador_seguro(tabla)} WHERE empresa_id = ?", (empresa_id,))
    else:
        cur.execute(f"SELECT * FROM {_identificador_seguro(tabla)}")

    return [_fila_a_dict(fila) for fila in cur.fetchall()]


def _leer_plan_empresa_por_codigo(con: sqlite3.Connection, empresa_id: int) -> Dict[str, Dict[str, Any]]:
    filas = _leer_filas_empresa(con, "plan_cuentas_empresa", empresa_id)
    plan: Dict[str, Dict[str, Any]] = {}
    for fila in filas:
        codigo = _texto(fila.get("codigo") or fila.get("cuenta_codigo") or fila.get("cuenta"))
        if codigo:
            plan[codigo] = fila
    return plan


def _diagnosticar_cuentas_bancarias(
    diagnostico: Dict[str, Any],
    cuentas: Sequence[Dict[str, Any]],
    plan_por_codigo: Dict[str, Dict[str, Any]],
) -> None:
    vistas = []
    for cuenta in cuentas:
        cuenta_id = _obtener_id(cuenta)
        banco = _texto(cuenta.get("banco"))
        nombre_cuenta = _texto(cuenta.get("nombre_cuenta"))
        codigo = _texto(cuenta.get("cuenta_contable_codigo"))
        nombre_contable = _texto(cuenta.get("cuenta_contable_nombre"))
        plan = plan_por_codigo.get(codigo) if codigo else None
        estado_plan = "SIN_CUENTA_CONTABLE" if not codigo else "OK"

        vista = {
            "cuenta_bancaria_id": cuenta_id,
            "banco": banco,
            "nombre_cuenta": nombre_cuenta,
            "cuenta_contable_codigo": codigo,
            "cuenta_contable_nombre": nombre_contable,
            "plan_encontrado": plan is not None,
            "diagnostico_plan": estado_plan,
        }

        if not codigo:
            diagnostico["resumen"]["cuentas_bancarias_sin_cuenta_contable"] += 1
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CUENTA_SIN_CUENTA_CONTABLE",
                severidad="ADVERTENCIA",
                titulo="Cuenta bancaria sin cuenta contable vinculada",
                detalle=f"{banco} {nombre_cuenta} no tiene cuenta_contable_codigo.",
                entidad="bancos_cuentas",
                entidad_id=cuenta_id,
            )
        elif plan is None:
            vista["diagnostico_plan"] = "CUENTA_PLAN_NO_ENCONTRADA"
            diagnostico["resumen"]["cuentas_bancarias_con_plan_incompatible"] += 1
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CUENTA_PLAN_NO_ENCONTRADA",
                severidad="ADVERTENCIA",
                titulo="Cuenta contable bancaria no encontrada en Plan Empresa",
                detalle=f"{banco} {nombre_cuenta} apunta al código {codigo}, pero no existe en plan_cuentas_empresa.",
                entidad="bancos_cuentas",
                entidad_id=cuenta_id,
            )
        else:
            problemas = _validar_plan_banco(plan)
            if problemas:
                vista["diagnostico_plan"] = "CUENTA_PLAN_REQUIERE_REVISION"
                diagnostico["resumen"]["cuentas_bancarias_con_plan_incompatible"] += 1
                for problema in problemas:
                    _agregar_alerta(
                        diagnostico,
                        codigo=problema["codigo"],
                        severidad=problema["severidad"],
                        titulo=problema["titulo"],
                        detalle=f"{banco} {nombre_cuenta} está vinculada a {codigo}. {problema['detalle']}",
                        entidad="bancos_cuentas",
                        entidad_id=cuenta_id,
                    )

        vistas.append(vista)

    diagnostico["cuentas_bancarias"] = vistas


def _validar_plan_banco(plan: Dict[str, Any]) -> List[Dict[str, str]]:
    problemas: List[Dict[str, str]] = []
    estado = _texto_upper(plan.get("estado") or "ACTIVA")
    if estado in {"ANULADO", "ANULADA", "INACTIVO", "INACTIVA", "BAJA", "ELIMINADO", "ELIMINADA"}:
        problemas.append({
            "codigo": "BANCO_CAJA_CUENTA_PLAN_INACTIVA",
            "severidad": "ADVERTENCIA",
            "titulo": "Cuenta bancaria vinculada a cuenta contable inactiva",
            "detalle": "La cuenta del Plan Empresa no está activa.",
        })

    if not _es_imputable(plan.get("imputable"), default=True):
        problemas.append({
            "codigo": "BANCO_CAJA_CUENTA_PLAN_NO_IMPUTABLE",
            "severidad": "ADVERTENCIA",
            "titulo": "Cuenta bancaria vinculada a cuenta no imputable",
            "detalle": "Banco/Caja debe vincularse a una cuenta imputable.",
        })

    uso = _normalizar_uso_operativo(plan.get("uso_operativo_sistema"))
    nombre = _texto_upper(plan.get("nombre") or plan.get("detalle"))
    if uso and uso not in USOS_OPERATIVOS_BANCO and "BANCO" not in nombre:
        problemas.append({
            "codigo": "BANCO_CAJA_CUENTA_PLAN_USO_REVISAR",
            "severidad": "INFORMATIVO",
            "titulo": "Uso operativo de cuenta bancaria requiere revisión",
            "detalle": f"Uso operativo detectado: {uso or 'sin uso operativo'}.",
        })

    return problemas


def _diagnosticar_importaciones(
    diagnostico: Dict[str, Any],
    importaciones: Sequence[Dict[str, Any]],
    movimientos: Sequence[Dict[str, Any]],
) -> None:
    movimientos_por_importacion = Counter(_entero(mov.get("importacion_id")) for mov in movimientos if _entero(mov.get("importacion_id")) > 0)
    por_banco_cuenta = Counter()

    for imp in importaciones:
        importacion_id = _obtener_id(imp)
        banco = _texto(imp.get("banco"))
        cuenta = _texto(imp.get("nombre_cuenta"))
        por_banco_cuenta[f"{banco} | {cuenta}"] += 1
        diferencia = abs(_numero(imp.get("diferencia_saldo")))
        procesados = _entero(imp.get("procesados"))
        duplicados = _entero(imp.get("duplicados"))
        movimientos_reales = movimientos_por_importacion.get(_entero(importacion_id), 0)

        vista = {
            "importacion_id": importacion_id,
            "fecha_carga": _texto(imp.get("fecha_carga")),
            "archivo": _texto(imp.get("nombre_archivo")),
            "banco": banco,
            "nombre_cuenta": cuenta,
            "procesados": procesados,
            "duplicados": duplicados,
            "movimientos_reales": movimientos_reales,
            "diferencia_saldo": _numero(imp.get("diferencia_saldo")),
        }

        if diferencia > 0.01:
            diagnostico["resumen"]["importaciones_con_diferencia_saldo"] += 1
            diagnostico["importaciones"]["con_diferencia_saldo"].append(vista)
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_IMPORTACION_DIFERENCIA_SALDO",
                severidad="ADVERTENCIA",
                titulo="Importación bancaria con diferencia de saldo",
                detalle=f"Importación {importacion_id} tiene diferencia de saldo {vista['diferencia_saldo']}.",
                entidad="bancos_importaciones",
                entidad_id=importacion_id,
            )

        if procesados == 0 and duplicados > 0:
            diagnostico["resumen"]["importaciones_duplicadas_sin_movimientos"] += 1
            diagnostico["importaciones"]["duplicadas_sin_movimientos"].append(vista)

        if procesados > 0 and movimientos_reales == 0:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_IMPORTACION_SIN_MOVIMIENTOS",
                severidad="ADVERTENCIA",
                titulo="Importación con procesados pero sin movimientos asociados",
                detalle=f"Importación {importacion_id} informa procesados={procesados}, pero no se leyeron movimientos vinculados.",
                entidad="bancos_importaciones",
                entidad_id=importacion_id,
            )

    diagnostico["importaciones"]["por_banco_cuenta"] = dict(por_banco_cuenta)


def _diagnosticar_movimientos(
    diagnostico: Dict[str, Any],
    movimientos: Sequence[Dict[str, Any]],
    plan_por_codigo: Dict[str, Dict[str, Any]],
) -> None:
    por_tipo = Counter()
    por_estado_conc = Counter()
    por_estado_contable = Counter()
    por_clave = defaultdict(list)

    for mov in movimientos:
        mov_id = _obtener_id(mov)
        tipo = _texto_upper(mov.get("tipo_movimiento_sugerido") or "A_REVISAR")
        estado_conc = _texto_upper(mov.get("estado_conciliacion") or "PENDIENTE")
        estado_contable = _texto_upper(mov.get("estado_contable") or "NO_CONTABILIZADO")
        clave = _texto(mov.get("clave_movimiento"))
        importe = _numero(mov.get("importe"))
        conciliado = abs(_numero(mov.get("importe_conciliado")))
        pendiente = abs(_numero(mov.get("importe_pendiente")))
        pendiente_calculado = max(round(abs(importe) - conciliado, 2), 0.0)

        por_tipo[tipo] += 1
        por_estado_conc[estado_conc] += 1
        por_estado_contable[estado_contable] += 1
        if clave:
            por_clave[clave].append(mov)
        else:
            diagnostico["resumen"]["movimientos_sin_clave"] += 1
            diagnostico["movimientos"]["sin_clave"].append(_resumen_movimiento(mov))

        if estado_conc == "PENDIENTE":
            diagnostico["resumen"]["movimientos_pendientes"] += 1
            diagnostico["movimientos"]["pendientes"].append(_resumen_movimiento(mov))
        elif estado_conc == "PARCIAL":
            diagnostico["resumen"]["movimientos_parciales"] += 1
            diagnostico["movimientos"]["parciales"].append(_resumen_movimiento(mov))
        elif estado_conc == "CONCILIADO":
            diagnostico["resumen"]["movimientos_conciliados"] += 1

        if tipo and tipo not in TIPOS_MOVIMIENTO_BANCO_REFERENCIA:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_TIPO_MOVIMIENTO_DESCONOCIDO",
                severidad="INFORMATIVO",
                titulo="Tipo de movimiento bancario no reconocido por el diagnóstico",
                detalle=f"Movimiento {mov_id} tiene tipo {tipo}.",
                entidad="bancos_movimientos",
                entidad_id=mov_id,
            )

        if estado_conc not in ESTADOS_CONCILIACION_BANCO_VALIDOS:
            diagnostico["resumen"]["movimientos_con_estado_desconocido"] += 1
            diagnostico["movimientos"]["estado_desconocido"].append(_resumen_movimiento(mov))
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_ESTADO_CONCILIACION_DESCONOCIDO",
                severidad="ADVERTENCIA",
                titulo="Movimiento con estado de conciliación desconocido",
                detalle=f"Movimiento {mov_id} tiene estado_conciliacion={estado_conc}.",
                entidad="bancos_movimientos",
                entidad_id=mov_id,
            )

        if estado_contable not in ESTADOS_CONTABLE_BANCO_VALIDOS:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_ESTADO_CONTABLE_DESCONOCIDO",
                severidad="INFORMATIVO",
                titulo="Movimiento con estado contable no reconocido por el diagnóstico",
                detalle=f"Movimiento {mov_id} tiene estado_contable={estado_contable}.",
                entidad="bancos_movimientos",
                entidad_id=mov_id,
            )

        if abs(pendiente - pendiente_calculado) > 0.01:
            diagnostico["resumen"]["movimientos_con_saldo_pendiente_inconsistente"] += 1
            vista = _resumen_movimiento(mov)
            vista["pendiente_calculado"] = pendiente_calculado
            diagnostico["movimientos"]["saldo_pendiente_inconsistente"].append(vista)
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_MOVIMIENTO_PENDIENTE_INCONSISTENTE",
                severidad="ADVERTENCIA",
                titulo="Movimiento con importe pendiente inconsistente",
                detalle=f"Movimiento {mov_id}: pendiente={pendiente}, calculado={pendiente_calculado}.",
                entidad="bancos_movimientos",
                entidad_id=mov_id,
            )

        problemas_plan = _validar_cuentas_movimiento_en_plan(mov, plan_por_codigo)
        if problemas_plan:
            diagnostico["resumen"]["movimientos_con_cuentas_plan_incompatibles"] += 1
            vista = _resumen_movimiento(mov)
            vista["problemas_plan"] = problemas_plan
            diagnostico["movimientos"]["cuentas_plan_incompatibles"].append(vista)
            for problema in problemas_plan:
                _agregar_alerta(
                    diagnostico,
                    codigo=problema["codigo"],
                    severidad=problema["severidad"],
                    titulo=problema["titulo"],
                    detalle=f"Movimiento {mov_id}: {problema['detalle']}",
                    entidad="bancos_movimientos",
                    entidad_id=mov_id,
                )

        debito = _numero(mov.get("debito"))
        credito = _numero(mov.get("credito"))
        if importe < 0 and debito <= 0:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_MOVIMIENTO_SIGNO_DEBITO_REVISAR",
                severidad="INFORMATIVO",
                titulo="Movimiento negativo sin débito informado",
                detalle=f"Movimiento {mov_id} tiene importe negativo pero débito no positivo.",
                entidad="bancos_movimientos",
                entidad_id=mov_id,
            )
        if importe > 0 and credito <= 0:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_MOVIMIENTO_SIGNO_CREDITO_REVISAR",
                severidad="INFORMATIVO",
                titulo="Movimiento positivo sin crédito informado",
                detalle=f"Movimiento {mov_id} tiene importe positivo pero crédito no positivo.",
                entidad="bancos_movimientos",
                entidad_id=mov_id,
            )

    for clave, filas in por_clave.items():
        if len(filas) > 1:
            diagnostico["resumen"]["movimientos_duplicados_potenciales"] += len(filas)
            vista = {
                "clave_movimiento": clave,
                "cantidad": len(filas),
                "movimientos": [_resumen_movimiento(fila) for fila in filas],
            }
            diagnostico["movimientos"]["duplicados_potenciales"].append(vista)
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_MOVIMIENTO_DUPLICADO_POTENCIAL",
                severidad="ADVERTENCIA",
                titulo="Movimientos bancarios con clave duplicada potencial",
                detalle=f"La clave {clave} aparece {len(filas)} veces.",
                entidad="bancos_movimientos",
            )

    diagnostico["movimientos"]["por_tipo"] = dict(por_tipo)
    diagnostico["movimientos"]["por_estado_conciliacion"] = dict(por_estado_conc)
    diagnostico["movimientos"]["por_estado_contable"] = dict(por_estado_contable)


def _validar_cuentas_movimiento_en_plan(
    mov: Dict[str, Any],
    plan_por_codigo: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    problemas: List[Dict[str, str]] = []
    for lado, codigo_clave, nombre_clave in (
        ("Debe", "cuenta_debe_codigo", "cuenta_debe_nombre"),
        ("Haber", "cuenta_haber_codigo", "cuenta_haber_nombre"),
    ):
        codigo = _texto(mov.get(codigo_clave))
        if not codigo:
            continue
        plan = plan_por_codigo.get(codigo)
        if plan is None:
            problemas.append({
                "codigo": "BANCO_CAJA_MOVIMIENTO_CUENTA_PLAN_NO_ENCONTRADA",
                "severidad": "INFORMATIVO",
                "titulo": "Cuenta sugerida del movimiento no encontrada en Plan Empresa",
                "detalle": f"Cuenta {lado} {codigo} - {_texto(mov.get(nombre_clave))} no existe en plan_cuentas_empresa.",
            })
            continue
        estado = _texto_upper(plan.get("estado") or "ACTIVA")
        if estado in {"ANULADO", "ANULADA", "INACTIVO", "INACTIVA", "BAJA", "ELIMINADO", "ELIMINADA"}:
            problemas.append({
                "codigo": "BANCO_CAJA_MOVIMIENTO_CUENTA_PLAN_INACTIVA",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta sugerida del movimiento está inactiva",
                "detalle": f"Cuenta {lado} {codigo} no está activa.",
            })
        if not _es_imputable(plan.get("imputable"), default=True):
            problemas.append({
                "codigo": "BANCO_CAJA_MOVIMIENTO_CUENTA_PLAN_NO_IMPUTABLE",
                "severidad": "ADVERTENCIA",
                "titulo": "Cuenta sugerida del movimiento no es imputable",
                "detalle": f"Cuenta {lado} {codigo} no es imputable.",
            })
    return problemas


def _diagnosticar_fiscal(diagnostico: Dict[str, Any], grupos: Sequence[Dict[str, Any]]) -> None:
    por_estado = Counter()
    total_iva_credito = 0.0
    total_percepcion_iva = 0.0
    total_percepcion_iibb = 0.0
    total_banco = 0.0

    for grupo in grupos:
        grupo_id = _obtener_id(grupo)
        estado = _texto_upper(grupo.get("estado_revision") or "PENDIENTE")
        por_estado[estado] += 1
        iva_credito = _numero(grupo.get("iva_credito_21")) + _numero(grupo.get("iva_credito_105")) + _numero(grupo.get("iva_sin_base"))
        percepcion_iva = _numero(grupo.get("percepcion_iva"))
        percepcion_iibb = _numero(grupo.get("percepcion_iibb"))
        total = _numero(grupo.get("total_banco"))
        total_iva_credito += iva_credito
        total_percepcion_iva += percepcion_iva
        total_percepcion_iibb += percepcion_iibb
        total_banco += total

        vista = {
            "grupo_fiscal_id": grupo_id,
            "fecha": _texto(grupo.get("fecha")),
            "banco": _texto(grupo.get("banco")),
            "nombre_cuenta": _texto(grupo.get("nombre_cuenta")),
            "estado_revision": estado,
            "iva_credito": round(iva_credito, 2),
            "percepcion_iva": round(percepcion_iva, 2),
            "percepcion_iibb": round(percepcion_iibb, 2),
            "total_banco": round(total, 2),
        }

        if estado in {"PENDIENTE", "REVISAR_ALICUOTA", "REVISAR_DIFERENCIA", "IVA_SIN_BASE", "BASE_SIN_IVA"}:
            diagnostico["resumen"]["grupos_fiscales_pendientes"] += 1
            diagnostico["fiscal"]["grupos_pendientes"].append(vista)

    diagnostico["fiscal"]["grupos_por_estado"] = dict(por_estado)
    diagnostico["fiscal"]["total_iva_credito"] = round(total_iva_credito, 2)
    diagnostico["fiscal"]["total_percepcion_iva"] = round(total_percepcion_iva, 2)
    diagnostico["fiscal"]["total_percepcion_iibb"] = round(total_percepcion_iibb, 2)
    diagnostico["fiscal"]["total_banco_fiscal"] = round(total_banco, 2)


def _diagnosticar_asientos(diagnostico: Dict[str, Any], asientos: Sequence[Dict[str, Any]]) -> None:
    por_estado = Counter()
    por_movimiento: Dict[int, Dict[str, float]] = defaultdict(lambda: {"debe": 0.0, "haber": 0.0, "lineas": 0})

    for asiento in asientos:
        estado = _texto_upper(asiento.get("estado") or "PROPUESTO")
        por_estado[estado] += 1
        movimiento_id = _entero(asiento.get("movimiento_banco_id"))
        if movimiento_id > 0:
            por_movimiento[movimiento_id]["debe"] += _numero(asiento.get("debe"))
            por_movimiento[movimiento_id]["haber"] += _numero(asiento.get("haber"))
            por_movimiento[movimiento_id]["lineas"] += 1

    for movimiento_id, totales in por_movimiento.items():
        diferencia = round(totales["debe"] - totales["haber"], 2)
        if abs(diferencia) > 0.01:
            diagnostico["resumen"]["asientos_propuestos_desbalanceados"] += 1
            vista = {
                "movimiento_banco_id": movimiento_id,
                "lineas": int(totales["lineas"]),
                "debe": round(totales["debe"], 2),
                "haber": round(totales["haber"], 2),
                "diferencia": diferencia,
            }
            diagnostico["asientos_propuestos"]["desbalanceados_por_movimiento"].append(vista)
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_ASIENTO_PROPUESTO_DESBALANCEADO",
                severidad="ADVERTENCIA",
                titulo="Asiento propuesto bancario desbalanceado",
                detalle=f"Movimiento {movimiento_id}: debe={vista['debe']}, haber={vista['haber']}.",
                entidad="bancos_asientos_propuestos",
            )

    diagnostico["asientos_propuestos"]["por_estado"] = dict(por_estado)


def _diagnosticar_conciliaciones(
    diagnostico: Dict[str, Any],
    conciliaciones: Sequence[Dict[str, Any]],
    detalles: Sequence[Dict[str, Any]],
    movimientos: Sequence[Dict[str, Any]],
) -> None:
    por_tipo = Counter()
    por_estado = Counter()
    detalles_por_conciliacion = defaultdict(list)
    conciliaciones_por_id = {_entero(_obtener_id(conc)): conc for conc in conciliaciones if _entero(_obtener_id(conc)) > 0}
    movimientos_por_id = {_entero(_obtener_id(mov)): mov for mov in movimientos if _entero(_obtener_id(mov)) > 0}

    for detalle in detalles:
        conciliacion_id = _entero(detalle.get("conciliacion_id"))
        detalles_por_conciliacion[conciliacion_id].append(detalle)
        if conciliacion_id <= 0 or conciliacion_id not in conciliaciones_por_id:
            diagnostico["resumen"]["detalles_huerfanos"] += 1
            diagnostico["conciliaciones"]["detalles_huerfanos"].append(_resumen_detalle_conciliacion(detalle))
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CONCILIACION_DETALLE_HUERFANO",
                severidad="ADVERTENCIA",
                titulo="Detalle de conciliación sin conciliación cabecera",
                detalle=f"Detalle { _obtener_id(detalle) } apunta a conciliación {conciliacion_id} inexistente.",
                entidad="bancos_conciliaciones_detalle",
                entidad_id=_obtener_id(detalle),
            )

        movimiento_id = _entero(detalle.get("movimiento_banco_id"))
        if movimiento_id > 0 and movimiento_id not in movimientos_por_id:
            diagnostico["conciliaciones"]["detalles_sin_movimiento"].append(_resumen_detalle_conciliacion(detalle))
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CONCILIACION_DETALLE_SIN_MOVIMIENTO",
                severidad="ADVERTENCIA",
                titulo="Detalle de conciliación apunta a movimiento bancario inexistente",
                detalle=f"Detalle { _obtener_id(detalle) } apunta al movimiento {movimiento_id}.",
                entidad="bancos_conciliaciones_detalle",
                entidad_id=_obtener_id(detalle),
            )

    for conciliacion in conciliaciones:
        conciliacion_id = _entero(_obtener_id(conciliacion))
        tipo = _texto_upper(conciliacion.get("tipo_conciliacion"))
        estado = _texto_upper(conciliacion.get("estado") or "BORRADOR")
        por_tipo[tipo] += 1
        por_estado[estado] += 1

        if estado == "ANULADA":
            diagnostico["resumen"]["conciliaciones_anuladas"] += 1
        else:
            diagnostico["resumen"]["conciliaciones_activas"] += 1

        if estado not in ESTADOS_CONCILIACION_REGISTRO_VALIDOS:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CONCILIACION_ESTADO_DESCONOCIDO",
                severidad="INFORMATIVO",
                titulo="Conciliación con estado no reconocido",
                detalle=f"Conciliación {conciliacion_id} tiene estado={estado}.",
                entidad="bancos_conciliaciones",
                entidad_id=conciliacion_id,
            )

        if tipo and tipo not in TIPOS_CONCILIACION_BANCARIA_REFERENCIA:
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CONCILIACION_TIPO_REVISAR",
                severidad="INFORMATIVO",
                titulo="Tipo de conciliación bancaria no reconocido por el diagnóstico",
                detalle=f"Conciliación {conciliacion_id} tiene tipo={tipo}.",
                entidad="bancos_conciliaciones",
                entidad_id=conciliacion_id,
            )

        if estado != "ANULADA" and not detalles_por_conciliacion.get(conciliacion_id):
            diagnostico["resumen"]["conciliaciones_activas_sin_detalle"] += 1
            vista = _resumen_conciliacion(conciliacion)
            diagnostico["conciliaciones"]["activas_sin_detalle"].append(vista)
            _agregar_alerta(
                diagnostico,
                codigo="BANCO_CAJA_CONCILIACION_ACTIVA_SIN_DETALLE",
                severidad="ADVERTENCIA",
                titulo="Conciliación activa sin detalle",
                detalle=f"Conciliación {conciliacion_id} no tiene detalles asociados.",
                entidad="bancos_conciliaciones",
                entidad_id=conciliacion_id,
            )

    diagnostico["conciliaciones"]["por_tipo"] = dict(por_tipo)
    diagnostico["conciliaciones"]["por_estado"] = dict(por_estado)


def _agregar_recomendaciones(diagnostico: Dict[str, Any]) -> None:
    resumen = diagnostico["resumen"]
    recomendaciones = diagnostico["recomendaciones"]

    if resumen["cuentas_bancarias_sin_cuenta_contable"] > 0:
        recomendaciones.append(
            "Vincular cuentas bancarias activas al Plan Empresa antes de habilitar aceptación auditada o Bandeja."
        )

    if resumen["importaciones_con_diferencia_saldo"] > 0:
        recomendaciones.append(
            "Revisar importaciones con diferencias de saldo antes de usar sus movimientos para conciliación o IVA."
        )

    if resumen["movimientos_con_saldo_pendiente_inconsistente"] > 0:
        recomendaciones.append(
            "Normalizar importes conciliados/pendientes de movimientos bancarios antes de conciliaciones automáticas."
        )

    if resumen["conciliaciones_activas_sin_detalle"] > 0 or resumen["detalles_huerfanos"] > 0:
        recomendaciones.append(
            "Revisar trazabilidad de conciliaciones bancarias antes de permitir desimputación o confirmación masiva."
        )

    if resumen["asientos_propuestos_desbalanceados"] > 0:
        recomendaciones.append(
            "No enviar asientos bancarios a Bandeja hasta resolver propuestas desbalanceadas."
        )

    if not recomendaciones:
        recomendaciones.append(
            "No se detectaron bloqueos críticos en el diagnóstico. La etapa v2A puede trabajar con sugerencias de parametrización de solo lectura."
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
            texto = valor.strip()
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            valor = texto
        return float(valor)
    except Exception:
        return 0.0


def _entero(valor: Any) -> int:
    try:
        return int(valor or 0)
    except Exception:
        return 0


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
    for clave in ("id", "movimiento_id", "importacion_id", "conciliacion_id", "cuenta_id"):
        if clave in fila and fila.get(clave) is not None:
            return fila.get(clave)
    return None


def _resumen_movimiento(mov: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "movimiento_banco_id": _obtener_id(mov),
        "importacion_id": mov.get("importacion_id"),
        "fecha": _texto(mov.get("fecha")),
        "banco": _texto(mov.get("banco")),
        "nombre_cuenta": _texto(mov.get("nombre_cuenta")),
        "concepto": _texto(mov.get("concepto")),
        "referencia": _texto(mov.get("referencia")),
        "importe": _numero(mov.get("importe")),
        "importe_conciliado": _numero(mov.get("importe_conciliado")),
        "importe_pendiente": _numero(mov.get("importe_pendiente")),
        "tipo_movimiento_sugerido": _texto_upper(mov.get("tipo_movimiento_sugerido")),
        "estado_conciliacion": _texto_upper(mov.get("estado_conciliacion")),
        "estado_contable": _texto_upper(mov.get("estado_contable")),
        "clave_movimiento": _texto(mov.get("clave_movimiento")),
    }


def _resumen_conciliacion(conciliacion: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "conciliacion_id": _obtener_id(conciliacion),
        "movimiento_banco_id": conciliacion.get("movimiento_banco_id"),
        "fecha": _texto(conciliacion.get("fecha")),
        "tipo_conciliacion": _texto_upper(conciliacion.get("tipo_conciliacion")),
        "estado": _texto_upper(conciliacion.get("estado")),
        "importe_total": _numero(conciliacion.get("importe_total")),
        "importe_imputado": _numero(conciliacion.get("importe_imputado")),
        "importe_pendiente": _numero(conciliacion.get("importe_pendiente")),
    }


def _resumen_detalle_conciliacion(detalle: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "detalle_id": _obtener_id(detalle),
        "conciliacion_id": detalle.get("conciliacion_id"),
        "movimiento_banco_id": detalle.get("movimiento_banco_id"),
        "entidad_tabla": _texto(detalle.get("entidad_tabla")),
        "entidad_id": detalle.get("entidad_id"),
        "cuenta_codigo": _texto(detalle.get("cuenta_codigo")),
        "cuenta_nombre": _texto(detalle.get("cuenta_nombre")),
        "importe_imputado": _numero(detalle.get("importe_imputado")),
    }
