from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from typing import Any


MIGRATION_FILE = Path("migrations/021_plan_cuentas_maestro_ff.sql")


TABLAS_NUCLEO_MAESTRO = [
    "versiones_plan_cuentas",
    "versiones_reglas_contables",
    "plan_cuentas_maestro",
    "plan_cuentas_empresa",
    "usos_operativos_contables",
    "mapeos_contables_empresa",
    "eventos_operativos_contables",
    "plantillas_asientos",
    "plantillas_asientos_detalle",
    "categorias_compra_config",
    "conceptos_fiscales_compra_config",
    "reglas_contables",
    "reglas_fiscales",
    "reglas_presentacion_contable",
    "auditoria_plan_cuentas",
    "auditoria_configuracion_contable",
    "mapeo_comportamiento_uso_operativo",
]


MAPEO_COMPORTAMIENTOS_DEFAULT = {
    "CAJA": "CAJA_GENERAL",
    "BANCO": "BANCO_CUENTA_CORRIENTE",
    "CLIENTES": "CLIENTES_CC",
    "PROVEEDORES": "PROVEEDORES_CC",
    "IVA_CREDITO": "IVA_CREDITO_FISCAL",
    "IVA_DEBITO": "IVA_DEBITO_FISCAL",
    "CAPITAL_SOCIAL": "CAPITAL_SOCIAL",
    "SUELDOS_A_PAGAR": "SUELDOS_A_PAGAR",
    "CARGAS_SOCIALES_A_PAGAR": "CARGAS_SOCIALES_A_PAGAR",
    "OBRA_SOCIAL_A_PAGAR": "OBRA_SOCIAL_A_PAGAR",
    "SINDICATO_A_PAGAR": "SINDICATO_A_PAGAR",
    "ART_A_PAGAR": "ART_A_PAGAR",
    "SUELDOS_GASTO": "SUELDOS_GASTO",
    "CARGAS_SOCIALES_GASTO": "CARGAS_SOCIALES_GASTO",
}


USOS_OPERATIVOS_COMPLEMENTARIOS = [
    {
        "codigo": "CAPITAL_SOCIAL",
        "nombre": "Capital social",
        "descripcion": "Cuenta patrimonial para capital suscripto/integrado según corresponda.",
        "tipo_uso": "PATRIMONIO_NETO",
        "modulo_sugerido": "Contabilidad",
        "requiere_cuenta_imputable": 1,
        "permite_multiples_cuentas_por_empresa": 0,
        "visible_en_ui": 0,
    },
    {
        "codigo": "RESULTADOS_NO_ASIGNADOS",
        "nombre": "Resultados no asignados",
        "descripcion": "Cuenta patrimonial para resultados acumulados pendientes de asignación.",
        "tipo_uso": "PATRIMONIO_NETO",
        "modulo_sugerido": "Contabilidad",
        "requiere_cuenta_imputable": 1,
        "permite_multiples_cuentas_por_empresa": 0,
        "visible_en_ui": 0,
    },
    {
        "codigo": "RESERVA_LEGAL",
        "nombre": "Reserva legal",
        "descripcion": "Reserva legal dentro del patrimonio neto.",
        "tipo_uso": "PATRIMONIO_NETO",
        "modulo_sugerido": "Contabilidad",
        "requiere_cuenta_imputable": 1,
        "permite_multiples_cuentas_por_empresa": 0,
        "visible_en_ui": 0,
    },
    {
        "codigo": "AJUSTES_CAPITAL",
        "nombre": "Ajustes de capital",
        "descripcion": "Ajustes de capital dentro del patrimonio neto.",
        "tipo_uso": "PATRIMONIO_NETO",
        "modulo_sugerido": "Contabilidad",
        "requiere_cuenta_imputable": 1,
        "permite_multiples_cuentas_por_empresa": 0,
        "visible_en_ui": 0,
    },
]




def _conectar_default() -> sqlite3.Connection:
    from database import conectar

    return conectar()


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row


def _fetch_dicts(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    filas = cur.fetchall()
    if not filas:
        return []

    if isinstance(filas[0], sqlite3.Row):
        return [dict(fila) for fila in filas]

    columnas = [col[0] for col in cur.description]
    return [dict(zip(columnas, fila)) for fila in filas]


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (tabla,),
    ).fetchone() is not None


def _columnas(conn: sqlite3.Connection, tabla: str) -> set[str]:
    if not _tabla_existe(conn, tabla):
        return set()
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _limpiar(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _upper(valor: Any) -> str:
    return _limpiar(valor).upper()


def _bool_int(valor: Any, default: int = 0) -> int:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return 1 if valor else 0

    texto = _upper(valor)
    if texto in {"S", "SI", "SÍ", "Y", "YES", "TRUE", "1", "ACTIVO"}:
        return 1
    if texto in {"N", "NO", "FALSE", "0", "INACTIVO", "ANULADO"}:
        return 0
    return default


def _json(valor: Any) -> str:
    try:
        return json.dumps(valor, ensure_ascii=False, default=str)
    except Exception:
        return str(valor)


def _normalizar_codigo(valor: Any) -> str:
    texto = _upper(valor)
    texto = texto.replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
    texto = texto.replace("Ñ", "N")
    texto = texto.replace("-", "_").replace(" ", "_").replace("/", "_")
    while "__" in texto:
        texto = texto.replace("__", "_")
    return texto.strip("_")


def _to_int(valor: Any, default: int = 0) -> int:
    try:
        if valor is None or valor == "":
            return default
        return int(float(valor))
    except Exception:
        return default


def aplicar_migracion_021(
    conn: sqlite3.Connection | None = None,
    ruta_migracion: str | Path | None = None,
) -> dict[str, Any]:
    """
    Aplica la migración 021 de manera idempotente.

    No borra tablas actuales.
    No modifica movimientos.
    Solo asegura la nueva arquitectura de Plan Maestro FF.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    ruta = Path(ruta_migracion) if ruta_migracion else MIGRATION_FILE

    try:
        if not ruta.exists():
            return {
                "ok": False,
                "error": f"No existe la migración esperada: {ruta}",
            }

        sql = ruta.read_text(encoding="utf-8")
        conn.executescript(sql)

        if propia:
            conn.commit()

        return {
            "ok": True,
            "tablas": validar_estructura_maestro(conn=conn)["tablas"],
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


def asegurar_estructura_maestro(conn: sqlite3.Connection | None = None) -> None:
    """
    Asegura que la estructura nueva exista y completa usos críticos
    que pueden haber quedado fuera de la migración inicial.

    Es idempotente: puede llamarse muchas veces sin duplicar datos.
    """
    resultado = aplicar_migracion_021(conn=conn)
    if not resultado.get("ok"):
        raise RuntimeError(resultado.get("error", "No se pudo asegurar estructura del Plan Maestro FF."))

    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        _asegurar_usos_operativos_complementarios(conn)
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def _asegurar_usos_operativos_complementarios(conn: sqlite3.Connection) -> None:
    if not _tabla_existe(conn, "usos_operativos_contables"):
        return

    for uso in USOS_OPERATIVOS_COMPLEMENTARIOS:
        conn.execute(
            """
            INSERT INTO usos_operativos_contables
            (codigo, nombre, descripcion, tipo_uso, modulo_sugerido,
             requiere_cuenta_imputable, permite_multiples_cuentas_por_empresa,
             visible_en_ui, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(codigo) DO UPDATE SET
                nombre = excluded.nombre,
                descripcion = excluded.descripcion,
                tipo_uso = excluded.tipo_uso,
                modulo_sugerido = excluded.modulo_sugerido,
                requiere_cuenta_imputable = excluded.requiere_cuenta_imputable,
                permite_multiples_cuentas_por_empresa = excluded.permite_multiples_cuentas_por_empresa,
                visible_en_ui = excluded.visible_en_ui,
                activo = 1,
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (
                uso["codigo"],
                uso["nombre"],
                uso["descripcion"],
                uso["tipo_uso"],
                uso["modulo_sugerido"],
                int(uso["requiere_cuenta_imputable"]),
                int(uso["permite_multiples_cuentas_por_empresa"]),
                int(uso["visible_en_ui"]),
            ),
        )



def validar_estructura_maestro(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        tablas = {}
        faltantes = []

        for tabla in TABLAS_NUCLEO_MAESTRO:
            existe = _tabla_existe(conn, tabla)
            total = None
            if existe:
                try:
                    total = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                except Exception:
                    total = None
            else:
                faltantes.append(tabla)

            tablas[tabla] = {
                "existe": existe,
                "filas": total,
            }

        return {
            "ok": not faltantes,
            "faltantes": faltantes,
            "tablas": tablas,
        }
    finally:
        if propia:
            conn.close()


def listar_usos_operativos(
    conn: sqlite3.Connection | None = None,
    solo_activos: bool = True,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        where = "WHERE activo = 1" if solo_activos else ""
        return _fetch_dicts(
            conn,
            f"""
            SELECT id, codigo, nombre, descripcion, tipo_uso, modulo_sugerido,
                   requiere_cuenta_imputable, permite_multiples_cuentas_por_empresa,
                   visible_en_ui, activo
            FROM usos_operativos_contables
            {where}
            ORDER BY tipo_uso, codigo
            """,
        )
    finally:
        if propia:
            conn.close()


def obtener_uso_operativo(
    codigo: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    codigo = _normalizar_codigo(codigo)

    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        filas = _fetch_dicts(
            conn,
            """
            SELECT *
            FROM usos_operativos_contables
            WHERE codigo = ?
            LIMIT 1
            """,
            (codigo,),
        )
        return filas[0] if filas else None
    finally:
        if propia:
            conn.close()


def listar_eventos_operativos(
    conn: sqlite3.Connection | None = None,
    solo_activos: bool = True,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        where = "WHERE activo = 1" if solo_activos else ""
        return _fetch_dicts(
            conn,
            f"""
            SELECT id, codigo, nombre, modulo_origen, descripcion,
                   genera_asiento, requiere_revision, activo
            FROM eventos_operativos_contables
            {where}
            ORDER BY modulo_origen, codigo
            """,
        )
    finally:
        if propia:
            conn.close()


def uso_operativo_desde_comportamiento(
    comportamiento: str,
    conn: sqlite3.Connection | None = None,
) -> str:
    comportamiento = _normalizar_codigo(comportamiento)
    if not comportamiento:
        return ""

    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)

        fila = conn.execute(
            """
            SELECT uso_operativo_codigo
            FROM mapeo_comportamiento_uso_operativo
            WHERE comportamiento_contable = ?
              AND activo = 1
            LIMIT 1
            """,
            (comportamiento,),
        ).fetchone()

        if fila:
            return str(fila["uso_operativo_codigo"])

        return MAPEO_COMPORTAMIENTOS_DEFAULT.get(comportamiento, "")
    finally:
        if propia:
            conn.close()


def registrar_auditoria_plan(
    *,
    empresa_id: int | None,
    cuenta_empresa_id: int | None = None,
    cuenta_maestro_id: int | None = None,
    evento: str,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
    motivo: str = "",
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        conn.execute(
            """
            INSERT INTO auditoria_plan_cuentas
            (empresa_id, cuenta_empresa_id, cuenta_maestro_id, evento,
             valor_anterior, valor_nuevo, motivo, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                cuenta_empresa_id,
                cuenta_maestro_id,
                evento,
                "" if valor_anterior is None else _json(valor_anterior),
                "" if valor_nuevo is None else _json(valor_nuevo),
                motivo,
                usuario,
            ),
        )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def registrar_auditoria_configuracion(
    *,
    empresa_id: int | None,
    entidad: str,
    entidad_id: int | None,
    evento: str,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
    motivo: str = "",
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        conn.execute(
            """
            INSERT INTO auditoria_configuracion_contable
            (empresa_id, entidad, entidad_id, evento,
             valor_anterior, valor_nuevo, motivo, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                entidad,
                entidad_id,
                evento,
                "" if valor_anterior is None else _json(valor_anterior),
                "" if valor_nuevo is None else _json(valor_nuevo),
                motivo,
                usuario,
            ),
        )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def _obtener_plan_actual(conn: sqlite3.Connection, empresa_id: int) -> list[dict[str, Any]]:
    if not _tabla_existe(conn, "plan_cuentas") and not _tabla_existe(conn, "plan_cuentas_detallado"):
        return []

    columnas_plan = _columnas(conn, "plan_cuentas")
    columnas_detalle = _columnas(conn, "plan_cuentas_detallado")

    if "plan_cuentas" not in _tablas(conn):
        return []

    empresa_sql_plan = "COALESCE(p.empresa_id, 1) = ?" if "empresa_id" in columnas_plan else "1 = 1"
    empresa_sql_detalle = "COALESCE(d.empresa_id, 1) = COALESCE(p.empresa_id, 1)" if "empresa_id" in columnas_detalle else "1 = 1"
    params: list[Any] = []
    if "empresa_id" in columnas_plan:
        params.append(empresa_id)

    sql = f"""
        SELECT
            p.rowid AS plan_rowid,
            p.codigo AS codigo,
            p.nombre AS nombre,
            COALESCE(d.imputable, 'S') AS imputable,
            COALESCE(d.ajustable, 'N') AS ajustable,
            COALESCE(d.tipo, 'D') AS tipo,
            COALESCE(d.madre, '') AS madre,
            COALESCE(d.nivel, 1) AS nivel,
            COALESCE(d.orden, 0) AS orden,
            COALESCE(p.comportamiento_contable, '') AS comportamiento_contable,
            COALESCE(p.requiere_auxiliar, 0) AS requiere_auxiliar,
            COALESCE(p.permite_imputacion_operativa, 1) AS permite_imputacion_operativa,
            COALESCE(p.modulo_origen_preferido, '') AS modulo_origen_preferido
        FROM plan_cuentas p
        LEFT JOIN plan_cuentas_detallado d
          ON d.cuenta = p.codigo
         AND {empresa_sql_detalle}
        WHERE {empresa_sql_plan}

        UNION

        SELECT
            p.rowid AS plan_rowid,
            d.cuenta AS codigo,
            d.detalle AS nombre,
            COALESCE(d.imputable, 'S') AS imputable,
            COALESCE(d.ajustable, 'N') AS ajustable,
            COALESCE(d.tipo, 'D') AS tipo,
            COALESCE(d.madre, '') AS madre,
            COALESCE(d.nivel, 1) AS nivel,
            COALESCE(d.orden, 0) AS orden,
            COALESCE(p.comportamiento_contable, '') AS comportamiento_contable,
            COALESCE(p.requiere_auxiliar, 0) AS requiere_auxiliar,
            COALESCE(p.permite_imputacion_operativa, 1) AS permite_imputacion_operativa,
            COALESCE(p.modulo_origen_preferido, '') AS modulo_origen_preferido
        FROM plan_cuentas_detallado d
        LEFT JOIN plan_cuentas p
          ON p.codigo = d.cuenta
         AND COALESCE(p.empresa_id, 1) = COALESCE(d.empresa_id, 1)
        WHERE {"COALESCE(d.empresa_id, 1) = ?" if "empresa_id" in columnas_detalle else "1 = 1"}
        ORDER BY orden, codigo
    """

    if "empresa_id" in columnas_detalle:
        params.append(empresa_id)

    filas = _fetch_dicts(conn, sql, tuple(params))
    salida: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for fila in filas:
        codigo = _limpiar(fila.get("codigo"))
        nombre = _limpiar(fila.get("nombre"))
        if not codigo or not nombre or codigo in vistos:
            continue

        vistos.add(codigo)
        salida.append(fila)

    return salida


def _tablas(conn: sqlite3.Connection) -> set[str]:
    return {
        fila[0]
        for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def _tipo_a_elemento(tipo: Any, codigo: Any, nombre: Any) -> str:
    tipo = _upper(tipo)
    codigo_txt = _limpiar(codigo)

    if tipo == "A" or codigo_txt.startswith("1"):
        return "ACTIVO"
    if tipo == "P" or codigo_txt.startswith("2"):
        return "PASIVO"
    if tipo == "PN" or codigo_txt.startswith("3"):
        return "PATRIMONIO_NETO"
    if codigo_txt.startswith("4"):
        return "INGRESOS"
    if codigo_txt.startswith("5"):
        return "COSTOS"
    if tipo == "R" or codigo_txt.startswith("6"):
        return "EGRESOS_GASTOS_PERDIDAS"

    nombre_norm = _normalizar_codigo(nombre)
    if "RECPAM" in nombre_norm:
        return "RECPAM"

    return "SIN_CLASIFICAR"


def _clasificacion_por_codigo(codigo: Any, elemento: str) -> str:
    codigo_txt = _limpiar(codigo)

    if elemento in {"ACTIVO", "PASIVO"}:
        if codigo_txt.startswith("1.") or codigo_txt.startswith("2."):
            partes = codigo_txt.split(".")
            if len(partes) >= 2 and partes[1] in {"1", "2", "3", "4", "5", "6"}:
                # El plan anterior no siempre separa corriente/no corriente.
                # Se mantiene una clasificación prudente para no forzar presentación definitiva.
                return "CORRIENTE" if partes[1] in {"1", "2", "3", "5", "6"} else "NO_CORRIENTE"
        return "CORRIENTE"

    return "NO_APLICA"


def _saldo_normal_por_elemento(elemento: str, nombre: Any) -> str:
    nombre_norm = _normalizar_codigo(nombre)

    if elemento == "ACTIVO":
        if any(pal in nombre_norm for pal in ["AMORTIZACION_ACUMULADA", "PREVISION", "INTERESES_POSITIVOS_A_DEVENGAR"]):
            return "ACREEDOR"
        return "DEUDOR"

    if elemento in {"PASIVO", "PATRIMONIO_NETO", "INGRESOS"}:
        return "ACREEDOR"

    if elemento in {"COSTOS", "EGRESOS_GASTOS_PERDIDAS"}:
        return "DEUDOR"

    if elemento == "RECPAM":
        return "SEGUN_NATURALEZA"

    return "NO_APLICA"


def _significados_saldo(elemento: str, nombre: Any, saldo_normal: str) -> dict[str, Any]:
    nombre_norm = _normalizar_codigo(nombre)
    permite_deudor = 1 if saldo_normal in {"DEUDOR", "SEGUN_NATURALEZA"} else 0
    permite_acreedor = 1 if saldo_normal in {"ACREEDOR", "SEGUN_NATURALEZA"} else 0
    significado_normal = "Naturaleza contable de la cuenta según su rubro."

    significado_deudor = ""
    significado_acreedor = ""
    tratamiento = "PERMITIR"
    alertar = 0
    requiere_reclasificacion = 0

    if "BANCO" in nombre_norm or "CUENTA_CORRIENTE" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 1
        significado_normal = "Representa fondos disponibles en cuentas bancarias."
        significado_deudor = "Fondos disponibles en la cuenta bancaria."
        significado_acreedor = "Puede representar giro en descubierto, sobregiro o deuda bancaria pendiente de reclasificación."
        tratamiento = "ADVERTIR_RECLASIFICAR"
        alertar = 1
        requiere_reclasificacion = 1

    elif "CAJA" in nombre_norm or "EFECTIVO" in nombre_norm or "FONDO_FIJO" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 0
        significado_normal = "Representa dinero físico disponible."
        significado_deudor = "Dinero físico disponible o fondo fijo existente."
        significado_acreedor = "Indicaría posible error operativo, egreso no respaldado o falta de registración de ingresos."
        tratamiento = "ALERTA_FUERTE"
        alertar = 1

    elif "PROVEEDORES" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 1
        significado_normal = "Representa deudas comerciales pendientes de pago."
        significado_deudor = "Puede representar anticipos a proveedores, pagos en exceso o notas de crédito pendientes."
        significado_acreedor = "Representa deuda comercial pendiente con proveedores."
        tratamiento = "ADVERTIR_RECLASIFICAR"
        alertar = 1
        requiere_reclasificacion = 1

    elif "DEUDORES_POR_VENTAS" in nombre_norm or "CLIENTES" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 1
        significado_normal = "Representa créditos pendientes de cobro por ventas."
        significado_deudor = "Representa importes a cobrar a clientes."
        significado_acreedor = "Puede representar anticipos de clientes, cobros en exceso o notas de crédito pendientes."
        tratamiento = "ADVERTIR_RECLASIFICAR"
        alertar = 1
        requiere_reclasificacion = 1

    elif "IVA_CREDITO" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 1
        significado_normal = "Representa crédito fiscal computable a favor de la empresa."
        significado_deudor = "Crédito fiscal computable a favor de la empresa."
        significado_acreedor = "Puede indicar ajuste, rectificativa, compensación mal aplicada o error de imputación."
        tratamiento = "ALERTA_FUERTE"
        alertar = 1

    elif "IVA_DEBITO" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 1
        significado_normal = "Representa débito fiscal generado por ventas gravadas."
        significado_deudor = "Puede surgir por notas de crédito, rectificativas o ajustes fiscales."
        significado_acreedor = "Débito fiscal generado por ventas gravadas."
        tratamiento = "ADVERTIR"
        alertar = 1

    elif "RECPAM" in nombre_norm:
        permite_deudor = 1
        permite_acreedor = 1
        significado_normal = "Resultado por exposición al cambio en el poder adquisitivo de la moneda."
        significado_deudor = "Pérdida por exposición al cambio en el poder adquisitivo de la moneda."
        significado_acreedor = "Ganancia por exposición al cambio en el poder adquisitivo de la moneda."
        tratamiento = "PERMITIR"

    elif "AMORTIZACION_ACUMULADA" in nombre_norm or "PREVISION" in nombre_norm:
        permite_deudor = 0
        permite_acreedor = 1
        significado_normal = "Cuenta regularizadora que disminuye el valor del activo relacionado."
        significado_deudor = "Puede indicar reversión mal registrada o error de imputación."
        significado_acreedor = "Saldo regularizador del activo vinculado."
        tratamiento = "ALERTA_FUERTE"
        alertar = 1

    elif saldo_normal == "DEUDOR":
        significado_deudor = "Saldo propio de una cuenta de naturaleza deudora."
        significado_acreedor = "Saldo invertido que debe analizarse según la operación que lo originó."
        alertar = 1
        tratamiento = "ADVERTIR"

    elif saldo_normal == "ACREEDOR":
        significado_deudor = "Saldo invertido que debe analizarse según la operación que lo originó."
        significado_acreedor = "Saldo propio de una cuenta de naturaleza acreedora."
        alertar = 1
        tratamiento = "ADVERTIR"

    return {
        "significado_saldo_normal": significado_normal,
        "permite_saldo_deudor": permite_deudor,
        "significado_saldo_deudor": significado_deudor,
        "permite_saldo_acreedor": permite_acreedor,
        "significado_saldo_acreedor": significado_acreedor,
        "alertar_saldo_invertido": alertar,
        "tratamiento_saldo_invertido": tratamiento,
        "requiere_reclasificacion_saldo_invertido": requiere_reclasificacion,
    }


def migrar_plan_actual_a_plan_empresa(
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str = "Migración inicial desde plan_cuentas/plan_cuentas_detallado hacia Plan Maestro FF",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Copia el plan actual hacia plan_cuentas_empresa.

    No borra ni modifica plan_cuentas ni plan_cuentas_detallado.
    No modifica Libro Diario ni comprobantes.
    Puede ejecutarse más de una vez sin duplicar cuentas por empresa/código.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)

        cuentas = _obtener_plan_actual(conn, empresa_id)
        migradas = 0
        mapeos = 0

        for cuenta in cuentas:
            codigo = _limpiar(cuenta.get("codigo"))
            nombre = _limpiar(cuenta.get("nombre"))
            if not codigo or not nombre:
                continue

            imputable = 1 if _upper(cuenta.get("imputable")) == "S" else 0
            ajustable = 1 if _upper(cuenta.get("ajustable")) == "S" else 0
            comportamiento = _normalizar_codigo(cuenta.get("comportamiento_contable"))
            uso_operativo = uso_operativo_desde_comportamiento(comportamiento, conn=conn) if comportamiento else ""

            anterior = conn.execute(
                """
                SELECT id, nombre, uso_operativo_sistema, estado
                FROM plan_cuentas_empresa
                WHERE empresa_id = ?
                  AND codigo = ?
                LIMIT 1
                """,
                (empresa_id, codigo),
            ).fetchone()

            conn.execute(
                """
                INSERT INTO plan_cuentas_empresa
                (empresa_id, codigo, nombre, codigo_madre, nivel, orden, imputable,
                 requiere_auxiliar, tipo_auxiliar, ajustable, estado, es_cuenta_modelo,
                 es_cuenta_especifica_empresa, uso_operativo_sistema, motivo_estado,
                 usuario_ultima_modificacion, fecha_ultima_modificacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVA', 0, 0, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(empresa_id, codigo) DO UPDATE SET
                    nombre = excluded.nombre,
                    codigo_madre = excluded.codigo_madre,
                    nivel = excluded.nivel,
                    orden = excluded.orden,
                    imputable = excluded.imputable,
                    requiere_auxiliar = excluded.requiere_auxiliar,
                    ajustable = excluded.ajustable,
                    uso_operativo_sistema = CASE
                        WHEN excluded.uso_operativo_sistema <> '' THEN excluded.uso_operativo_sistema
                        ELSE plan_cuentas_empresa.uso_operativo_sistema
                    END,
                    usuario_ultima_modificacion = excluded.usuario_ultima_modificacion,
                    fecha_ultima_modificacion = CURRENT_TIMESTAMP
                """,
                (
                    empresa_id,
                    codigo,
                    nombre,
                    _limpiar(cuenta.get("madre")),
                    _to_int(cuenta.get("nivel"), 1),
                    _to_int(cuenta.get("orden"), 0),
                    imputable,
                    _bool_int(cuenta.get("requiere_auxiliar"), 0),
                    "",
                    ajustable,
                    uso_operativo,
                    motivo,
                    usuario,
                ),
            )

            fila_empresa = conn.execute(
                """
                SELECT id
                FROM plan_cuentas_empresa
                WHERE empresa_id = ?
                  AND codigo = ?
                LIMIT 1
                """,
                (empresa_id, codigo),
            ).fetchone()

            cuenta_empresa_id = int(fila_empresa["id"])
            migradas += 1

            registrar_auditoria_plan(
                empresa_id=empresa_id,
                cuenta_empresa_id=cuenta_empresa_id,
                evento="CUENTA_EMPRESA_MIGRADA",
                valor_anterior=dict(anterior) if anterior else None,
                valor_nuevo={
                    "codigo": codigo,
                    "nombre": nombre,
                    "uso_operativo_sistema": uso_operativo,
                },
                motivo=motivo,
                usuario=usuario,
                conn=conn,
            )

            if uso_operativo:
                resultado_mapeo = crear_o_actualizar_mapeo_contable(
                    empresa_id=empresa_id,
                    uso_operativo_codigo=uso_operativo,
                    cuenta_empresa_id=cuenta_empresa_id,
                    modulo=_limpiar(cuenta.get("modulo_origen_preferido")),
                    evento_operativo="",
                    motivo="Mapeo creado desde migración de comportamiento_contable",
                    usuario=usuario,
                    conn=conn,
                )
                if resultado_mapeo.get("ok"):
                    mapeos += 1

        if propia:
            conn.commit()

        return {
            "ok": True,
            "cuentas_detectadas": len(cuentas),
            "cuentas_migradas": migradas,
            "mapeos_creados_o_actualizados": mapeos,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


def listar_plan_empresa(
    *,
    empresa_id: int = 1,
    solo_activas: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        where = "AND estado = 'ACTIVA'" if solo_activas else ""
        return _fetch_dicts(
            conn,
            f"""
            SELECT id, empresa_id, cuenta_maestro_id, codigo, nombre, codigo_madre,
                   nivel, orden, imputable, requiere_auxiliar, ajustable, estado,
                   es_cuenta_modelo, es_cuenta_especifica_empresa, cuenta_modelo_origen_id,
                   banco_nombre, numero_cuenta, moneda, alias, cbu, uso_operativo_sistema,
                   vigencia_desde, vigencia_hasta, motivo_estado
            FROM plan_cuentas_empresa
            WHERE empresa_id = ?
            {where}
            ORDER BY orden, codigo
            """,
            (empresa_id,),
        )
    finally:
        if propia:
            conn.close()


def crear_o_actualizar_mapeo_contable(
    *,
    empresa_id: int,
    uso_operativo_codigo: str,
    cuenta_empresa_id: int,
    modulo: str = "",
    evento_operativo: str = "",
    vigencia_desde: str | None = None,
    vigencia_hasta: str | None = None,
    motivo: str = "",
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)

        uso = obtener_uso_operativo(uso_operativo_codigo, conn=conn)
        if not uso:
            return {
                "ok": False,
                "error": f"No existe el uso operativo {uso_operativo_codigo}.",
            }

        cuenta = conn.execute(
            """
            SELECT id, imputable, estado, nombre
            FROM plan_cuentas_empresa
            WHERE id = ?
              AND empresa_id = ?
            LIMIT 1
            """,
            (cuenta_empresa_id, empresa_id),
        ).fetchone()

        if not cuenta:
            return {
                "ok": False,
                "error": "La cuenta empresa indicada no existe.",
            }

        if int(uso["requiere_cuenta_imputable"] or 0) == 1 and int(cuenta["imputable"] or 0) != 1:
            return {
                "ok": False,
                "error": "El uso operativo requiere una cuenta imputable.",
            }

        if str(cuenta["estado"]).upper() != "ACTIVA":
            return {
                "ok": False,
                "error": "La cuenta empresa no está activa.",
            }

        existe = conn.execute(
            """
            SELECT id
            FROM mapeos_contables_empresa
            WHERE empresa_id = ?
              AND uso_operativo_id = ?
              AND cuenta_empresa_id = ?
              AND COALESCE(modulo, '') = ?
              AND COALESCE(evento_operativo, '') = ?
              AND estado = 'ACTIVO'
            LIMIT 1
            """,
            (
                empresa_id,
                int(uso["id"]),
                cuenta_empresa_id,
                _limpiar(modulo),
                _limpiar(evento_operativo),
            ),
        ).fetchone()

        if existe:
            conn.execute(
                """
                UPDATE mapeos_contables_empresa
                   SET vigencia_desde = COALESCE(?, vigencia_desde),
                       vigencia_hasta = ?,
                       motivo = ?,
                       usuario = ?
                 WHERE id = ?
                """,
                (vigencia_desde, vigencia_hasta, motivo, usuario, int(existe["id"])),
            )
            mapeo_id = int(existe["id"])
            evento = "MAPEO_CONTABLE_ACTUALIZADO"
        else:
            conn.execute(
                """
                INSERT INTO mapeos_contables_empresa
                (empresa_id, uso_operativo_id, cuenta_empresa_id, modulo, evento_operativo,
                 vigencia_desde, vigencia_hasta, estado, motivo, usuario)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?, ?)
                """,
                (
                    empresa_id,
                    int(uso["id"]),
                    cuenta_empresa_id,
                    _limpiar(modulo),
                    _limpiar(evento_operativo),
                    vigencia_desde,
                    vigencia_hasta,
                    motivo,
                    usuario,
                ),
            )
            mapeo_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            evento = "MAPEO_CONTABLE_CREADO"

        registrar_auditoria_configuracion(
            empresa_id=empresa_id,
            entidad="mapeos_contables_empresa",
            entidad_id=mapeo_id,
            evento=evento,
            valor_nuevo={
                "uso_operativo_codigo": uso_operativo_codigo,
                "cuenta_empresa_id": cuenta_empresa_id,
                "modulo": modulo,
                "evento_operativo": evento_operativo,
            },
            motivo=motivo,
            usuario=usuario,
            conn=conn,
        )

        if propia:
            conn.commit()

        return {
            "ok": True,
            "mapeo_id": mapeo_id,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


def listar_mapeos_empresa(
    *,
    empresa_id: int = 1,
    solo_activos: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)
        where_estado = "AND m.estado = 'ACTIVO'" if solo_activos else ""
        return _fetch_dicts(
            conn,
            f"""
            SELECT
                m.id,
                m.empresa_id,
                u.codigo AS uso_operativo_codigo,
                u.nombre AS uso_operativo_nombre,
                c.codigo AS cuenta_codigo,
                c.nombre AS cuenta_nombre,
                m.modulo,
                m.evento_operativo,
                m.vigencia_desde,
                m.vigencia_hasta,
                m.estado,
                m.motivo,
                m.usuario,
                m.fecha_alta
            FROM mapeos_contables_empresa m
            JOIN usos_operativos_contables u ON u.id = m.uso_operativo_id
            JOIN plan_cuentas_empresa c ON c.id = m.cuenta_empresa_id
            WHERE m.empresa_id = ?
            {where_estado}
            ORDER BY u.codigo, c.codigo
            """,
            (empresa_id,),
        )
    finally:
        if propia:
            conn.close()


def _buscar_cuenta_empresa_id_por_codigo(
    conn: sqlite3.Connection,
    empresa_id: int,
    codigo: str,
) -> int | None:
    if not codigo:
        return None
    fila = conn.execute(
        """
        SELECT id
        FROM plan_cuentas_empresa
        WHERE empresa_id = ?
          AND codigo = ?
        LIMIT 1
        """,
        (empresa_id, codigo),
    ).fetchone()
    if not fila:
        return None
    return int(fila["id"])


def migrar_categorias_compra_actuales(
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str = "Migración desde categorias_compra hacia categorias_compra_config",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Migra categorías actuales hacia la configuración nueva.

    Es idempotente: si se ejecuta más de una vez, actualiza la categoría
    activa existente para la misma empresa/categoría en lugar de duplicarla.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)

        if not _tabla_existe(conn, "categorias_compra"):
            return {"ok": True, "migradas": 0, "actualizadas": 0, "mensaje": "No existe categorias_compra."}

        columnas = _columnas(conn, "categorias_compra")
        where = "WHERE COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas else ""
        params = (empresa_id,) if "empresa_id" in columnas else ()

        filas = _fetch_dicts(
            conn,
            f"""
            SELECT *
            FROM categorias_compra
            {where}
            ORDER BY categoria
            """,
            params,
        )

        migradas = 0
        actualizadas = 0

        for fila in filas:
            categoria = _limpiar(fila.get("categoria"))
            if not categoria:
                continue

            tipo_categoria = _normalizar_codigo(fila.get("tipo_categoria"))
            cuenta_codigo = _limpiar(fila.get("cuenta_codigo"))
            proveedor_codigo = _limpiar(fila.get("cuenta_proveedor_codigo"))

            uso_principal = _uso_operativo_sugerido_para_categoria(tipo_categoria, cuenta_codigo, categoria)
            uso_contrapartida = "PROVEEDORES_CC"

            uso_principal_id = _id_uso(conn, uso_principal)
            uso_contrapartida_id = _id_uso(conn, uso_contrapartida)

            cuenta_sugerida_id = _buscar_cuenta_empresa_id_por_codigo(conn, empresa_id, cuenta_codigo)
            cuenta_contrapartida_id = _buscar_cuenta_empresa_id_por_codigo(conn, empresa_id, proveedor_codigo)

            tratamiento = _tratamiento_categoria(tipo_categoria, categoria)

            payload = {
                "empresa_id": empresa_id,
                "categoria": categoria,
                "descripcion": categoria,
                "tipo_categoria": tipo_categoria,
                "tratamiento_contable": tratamiento,
                "uso_operativo_principal_id": uso_principal_id,
                "uso_operativo_contrapartida_id": uso_contrapartida_id,
                "cuenta_sugerida_id": cuenta_sugerida_id,
                "cuenta_contrapartida_sugerida_id": cuenta_contrapartida_id,
                "requiere_revision": 1 if tipo_categoria in {"REVISION", "ESPECIAL"} else 0,
                "afecta_inventario": 1 if tipo_categoria in {"BIENES_CAMBIO", "IMPORTACION"} else 0,
                "afecta_bienes_uso": 1 if tipo_categoria == "BIENES_USO" else 0,
                "afecta_resultado": 1 if tipo_categoria not in {"BIENES_USO", "BIENES_CAMBIO"} else 0,
            }

            existente = conn.execute(
                """
                SELECT *
                FROM categorias_compra_config
                WHERE empresa_id = ?
                  AND categoria = ?
                  AND estado <> 'ANULADA'
                ORDER BY id
                LIMIT 1
                """,
                (empresa_id, categoria),
            ).fetchone()

            if existente:
                entidad_id = int(existente["id"])
                conn.execute(
                    """
                    UPDATE categorias_compra_config
                       SET descripcion = ?,
                           tipo_categoria = ?,
                           tratamiento_contable = ?,
                           uso_operativo_principal_id = ?,
                           uso_operativo_contrapartida_id = ?,
                           cuenta_sugerida_id = ?,
                           cuenta_contrapartida_sugerida_id = ?,
                           requiere_auxiliar = 0,
                           requiere_revision = ?,
                           afecta_inventario = ?,
                           afecta_bienes_uso = ?,
                           afecta_resultado = ?,
                           afecta_iva = 1,
                           estado = 'ACTIVA',
                           motivo_estado = ?,
                           usuario_ultima_modificacion = ?,
                           fecha_ultima_modificacion = CURRENT_TIMESTAMP,
                           actualizado_en = CURRENT_TIMESTAMP
                     WHERE id = ?
                    """,
                    (
                        payload["descripcion"],
                        payload["tipo_categoria"],
                        payload["tratamiento_contable"],
                        payload["uso_operativo_principal_id"],
                        payload["uso_operativo_contrapartida_id"],
                        payload["cuenta_sugerida_id"],
                        payload["cuenta_contrapartida_sugerida_id"],
                        payload["requiere_revision"],
                        payload["afecta_inventario"],
                        payload["afecta_bienes_uso"],
                        payload["afecta_resultado"],
                        motivo,
                        usuario,
                        entidad_id,
                    ),
                )
                actualizadas += 1
                evento = "CATEGORIA_COMPRA_ACTUALIZADA_MIGRACION"
                valor_anterior = dict(existente)
            else:
                conn.execute(
                    """
                    INSERT INTO categorias_compra_config
                    (empresa_id, categoria, descripcion, tipo_categoria, tratamiento_contable,
                     uso_operativo_principal_id, uso_operativo_contrapartida_id,
                     cuenta_sugerida_id, cuenta_contrapartida_sugerida_id,
                     requiere_auxiliar, requiere_revision, afecta_inventario,
                     afecta_bienes_uso, afecta_resultado, afecta_iva,
                     estado, vigencia_desde, motivo_estado, usuario_ultima_modificacion,
                     fecha_ultima_modificacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 1,
                            'ACTIVA', NULL, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        empresa_id,
                        categoria,
                        payload["descripcion"],
                        payload["tipo_categoria"],
                        payload["tratamiento_contable"],
                        payload["uso_operativo_principal_id"],
                        payload["uso_operativo_contrapartida_id"],
                        payload["cuenta_sugerida_id"],
                        payload["cuenta_contrapartida_sugerida_id"],
                        payload["requiere_revision"],
                        payload["afecta_inventario"],
                        payload["afecta_bienes_uso"],
                        payload["afecta_resultado"],
                        motivo,
                        usuario,
                    ),
                )
                entidad_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                migradas += 1
                evento = "CATEGORIA_COMPRA_MIGRADA"
                valor_anterior = dict(fila)

            registrar_auditoria_configuracion(
                empresa_id=empresa_id,
                entidad="categorias_compra_config",
                entidad_id=entidad_id,
                evento=evento,
                valor_anterior=valor_anterior,
                valor_nuevo={
                    "categoria": categoria,
                    "uso_operativo_principal": uso_principal,
                    "tratamiento_contable": tratamiento,
                },
                motivo=motivo,
                usuario=usuario,
                conn=conn,
            )

        if propia:
            conn.commit()

        return {
            "ok": True,
            "detectadas": len(filas),
            "migradas": migradas,
            "actualizadas": actualizadas,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


def _id_uso(conn: sqlite3.Connection, codigo: str) -> int | None:
    if not codigo:
        return None
    fila = conn.execute(
        """
        SELECT id
        FROM usos_operativos_contables
        WHERE codigo = ?
        LIMIT 1
        """,
        (_normalizar_codigo(codigo),),
    ).fetchone()
    if not fila:
        return None
    return int(fila["id"])


def _uso_operativo_sugerido_para_categoria(tipo_categoria: str, cuenta_codigo: str, categoria: str) -> str:
    tipo = _normalizar_codigo(tipo_categoria)
    categoria_norm = _normalizar_codigo(categoria)

    if tipo == "BIENES_USO":
        if "RODADO" in categoria_norm:
            return "BIENES_USO_RODADOS"
        if "MUEBLES" in categoria_norm or "UTILES" in categoria_norm:
            return "BIENES_USO_MUEBLES_UTILES"
        if "COMPUT" in categoria_norm or "INFORMATIC" in categoria_norm:
            return "BIENES_USO_EQUIPOS_COMPUTACION"
        if "MAQUIN" in categoria_norm:
            return "BIENES_USO_MAQUINARIAS"
        if "INSTAL" in categoria_norm:
            return "BIENES_USO_INSTALACIONES"

    if tipo == "BIENES_CAMBIO":
        if "MATERIA" in categoria_norm:
            return "MATERIAS_PRIMAS"
        if "INSUMO" in categoria_norm:
            return "INSUMOS_PRODUCTIVOS"
        return "MERCADERIAS_REVENTA"

    if "ALQUILER" in categoria_norm:
        return "ALQUILERES"
    if "HONORARIO" in categoria_norm:
        return "HONORARIOS_PROFESIONALES"
    if "BANCO" in categoria_norm:
        return "GASTOS_BANCARIOS"
    if "COMBUST" in categoria_norm:
        return "COMBUSTIBLES_LUBRICANTES"
    if "FLETE" in categoria_norm:
        return "FLETES_LOGISTICA"
    if "SEGURO" in categoria_norm:
        return "SEGUROS"
    if "PUBLICIDAD" in categoria_norm:
        return "PUBLICIDAD_MARKETING"
    if "SERVICIO_PUBLICO" in categoria_norm or "ENERGIA" in categoria_norm:
        return "SERVICIOS_PUBLICOS"
    if "LIMPIEZA" in categoria_norm:
        return "LIMPIEZA_SEGURIDAD"
    if "REPAR" in categoria_norm or "MANTEN" in categoria_norm:
        return "REPARACIONES_MANTENIMIENTO"
    if "SUELDO" in categoria_norm:
        return "SUELDOS_GASTO"
    if "CARGAS_SOCIALES" in categoria_norm:
        return "CARGAS_SOCIALES_GASTO"
    if "ART" == categoria_norm:
        return "ART_GASTO"
    if "MERCADERIA" in categoria_norm:
        return "COMPRAS_MERCADERIAS"

    return "SERVICIOS_CONTRATADOS"


def _tratamiento_categoria(tipo_categoria: str, categoria: str) -> str:
    tipo = _normalizar_codigo(tipo_categoria)
    categoria_norm = _normalizar_codigo(categoria)

    if tipo == "BIENES_USO":
        return "ACTIVA_BIEN_USO"
    if tipo == "BIENES_CAMBIO":
        return "ACTIVA_INVENTARIO"
    if tipo == "PRORRATEO":
        return "GASTO_SUJETO_PRORRATEO"
    if tipo in {"EXENTO_NO_GRAVADO"}:
        return "MAYOR_COSTO_NO_GRAVADO"
    if tipo in {"IMPORTACION"}:
        return "IMPORTACION_REQUIERE_REVISION"
    if tipo in {"REVISION", "ESPECIAL"}:
        return "REQUIERE_REVISION"
    if "MERCADERIA" in categoria_norm:
        return "COMPRA_DIRECTA"
    return "GASTO_RESULTADO"


def migrar_conceptos_fiscales_compra_actuales(
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    motivo: str = "Migración desde conceptos_fiscales_compra hacia conceptos_fiscales_compra_config",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Migra conceptos fiscales actuales hacia la configuración nueva.

    Es idempotente: si se ejecuta más de una vez, actualiza el concepto
    activo existente para la misma empresa/concepto en lugar de duplicarlo.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)

        if not _tabla_existe(conn, "conceptos_fiscales_compra"):
            return {"ok": True, "migrados": 0, "actualizados": 0, "mensaje": "No existe conceptos_fiscales_compra."}

        columnas = _columnas(conn, "conceptos_fiscales_compra")
        where = "WHERE COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas else ""
        params = (empresa_id,) if "empresa_id" in columnas else ()

        filas = _fetch_dicts(
            conn,
            f"""
            SELECT *
            FROM conceptos_fiscales_compra
            {where}
            ORDER BY concepto
            """,
            params,
        )

        migrados = 0
        actualizados = 0

        for fila in filas:
            concepto = _limpiar(fila.get("concepto"))
            if not concepto:
                continue

            tratamiento = _normalizar_codigo(fila.get("tratamiento"))
            cuenta_codigo = _limpiar(fila.get("cuenta_codigo"))
            uso_operativo = _uso_operativo_sugerido_para_concepto(concepto, tratamiento)
            uso_id = _id_uso(conn, uso_operativo)
            cuenta_sugerida_id = _buscar_cuenta_empresa_id_por_codigo(conn, empresa_id, cuenta_codigo)

            flags = _flags_fiscales(concepto, tratamiento)

            existente = conn.execute(
                """
                SELECT *
                FROM conceptos_fiscales_compra_config
                WHERE empresa_id = ?
                  AND concepto = ?
                  AND estado <> 'ANULADO'
                ORDER BY id
                LIMIT 1
                """,
                (empresa_id, concepto),
            ).fetchone()

            if existente:
                entidad_id = int(existente["id"])
                conn.execute(
                    """
                    UPDATE conceptos_fiscales_compra_config
                       SET descripcion = ?,
                           tratamiento_fiscal = ?,
                           uso_operativo_id = ?,
                           cuenta_sugerida_id = ?,
                           afecta_iva = ?,
                           afecta_iibb = ?,
                           afecta_ganancias = ?,
                           computable = ?,
                           mayor_costo = ?,
                           informativo = ?,
                           requiere_periodo_fiscal = ?,
                           permite_diferir_periodo = ?,
                           estado = 'ACTIVO',
                           motivo_estado = ?,
                           usuario_ultima_modificacion = ?,
                           fecha_ultima_modificacion = CURRENT_TIMESTAMP,
                           actualizado_en = CURRENT_TIMESTAMP
                     WHERE id = ?
                    """,
                    (
                        concepto,
                        tratamiento,
                        uso_id,
                        cuenta_sugerida_id,
                        flags["afecta_iva"],
                        flags["afecta_iibb"],
                        flags["afecta_ganancias"],
                        flags["computable"],
                        flags["mayor_costo"],
                        flags["informativo"],
                        flags["requiere_periodo_fiscal"],
                        flags["permite_diferir_periodo"],
                        motivo,
                        usuario,
                        entidad_id,
                    ),
                )
                actualizados += 1
                evento = "CONCEPTO_FISCAL_COMPRA_ACTUALIZADO_MIGRACION"
                valor_anterior = dict(existente)
            else:
                conn.execute(
                    """
                    INSERT INTO conceptos_fiscales_compra_config
                    (empresa_id, concepto, descripcion, tratamiento_fiscal, uso_operativo_id,
                     cuenta_sugerida_id, afecta_iva, afecta_iibb, afecta_ganancias,
                     computable, mayor_costo, informativo, requiere_periodo_fiscal,
                     permite_diferir_periodo, estado, vigencia_desde, motivo_estado,
                     usuario_ultima_modificacion, fecha_ultima_modificacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO', NULL, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        empresa_id,
                        concepto,
                        concepto,
                        tratamiento,
                        uso_id,
                        cuenta_sugerida_id,
                        flags["afecta_iva"],
                        flags["afecta_iibb"],
                        flags["afecta_ganancias"],
                        flags["computable"],
                        flags["mayor_costo"],
                        flags["informativo"],
                        flags["requiere_periodo_fiscal"],
                        flags["permite_diferir_periodo"],
                        motivo,
                        usuario,
                    ),
                )
                entidad_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                migrados += 1
                evento = "CONCEPTO_FISCAL_COMPRA_MIGRADO"
                valor_anterior = dict(fila)

            registrar_auditoria_configuracion(
                empresa_id=empresa_id,
                entidad="conceptos_fiscales_compra_config",
                entidad_id=entidad_id,
                evento=evento,
                valor_anterior=valor_anterior,
                valor_nuevo={
                    "concepto": concepto,
                    "uso_operativo": uso_operativo,
                    "tratamiento_fiscal": tratamiento,
                    **flags,
                },
                motivo=motivo,
                usuario=usuario,
                conn=conn,
            )

        if propia:
            conn.commit()

        return {
            "ok": True,
            "detectados": len(filas),
            "migrados": migrados,
            "actualizados": actualizados,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()


def _uso_operativo_sugerido_para_concepto(concepto: str, tratamiento: str) -> str:
    concepto_norm = _normalizar_codigo(concepto)
    tratamiento_norm = _normalizar_codigo(tratamiento)

    if "IVA_CREDITO" in concepto_norm or tratamiento_norm == "CREDITO_FISCAL":
        return "IVA_CREDITO_FISCAL"
    if "IVA_NO_COMPUTABLE" in concepto_norm or tratamiento_norm in {"MAYOR_COSTO_GASTO", "NO_COMPUTABLE"}:
        return "IVA_NO_COMPUTABLE_MAYOR_COSTO"
    if "PERCEPCION_IVA" in concepto_norm or concepto_norm == "PERCEPCION_IVA":
        return "PERCEPCION_IVA"
    if "RETENCION_IVA" in concepto_norm:
        return "RETENCION_IVA_SUFRIDA"
    if "PERCEPCION_IIBB" in concepto_norm:
        return "PERCEPCION_IIBB"
    if "RETENCION_IIBB" in concepto_norm:
        return "RETENCION_IIBB_SUFRIDA"
    if "GANANCIAS" in concepto_norm:
        return "PERCEPCION_GANANCIAS"
    if "MUNICIPAL" in concepto_norm:
        return "PERCEPCION_MUNICIPAL"
    if "OTROS_IMP" in concepto_norm:
        return "PERCEPCION_OTROS_NACIONALES"
    return "IVA_NO_COMPUTABLE_MAYOR_COSTO"


def _flags_fiscales(concepto: str, tratamiento: str) -> dict[str, int]:
    concepto_norm = _normalizar_codigo(concepto)
    tratamiento_norm = _normalizar_codigo(tratamiento)

    afecta_iva = 1 if "IVA" in concepto_norm or tratamiento_norm in {"CREDITO_FISCAL"} else 0
    afecta_iibb = 1 if "IIBB" in concepto_norm else 0
    afecta_ganancias = 1 if "GANANCIAS" in concepto_norm else 0

    computable = 1 if tratamiento_norm in {
        "CREDITO_FISCAL",
        "PERCEPCION_COMPUTABLE",
        "RETENCION_COMPUTABLE",
    } else 0

    mayor_costo = 1 if tratamiento_norm in {
        "MAYOR_COSTO",
        "MAYOR_COSTO_GASTO",
        "NO_COMPUTABLE",
    } else 0

    requiere_periodo = 1 if computable else 0
    permite_diferir = 1 if tratamiento_norm in {"PERCEPCION_COMPUTABLE", "RETENCION_COMPUTABLE"} else 0

    return {
        "afecta_iva": afecta_iva,
        "afecta_iibb": afecta_iibb,
        "afecta_ganancias": afecta_ganancias,
        "computable": computable,
        "mayor_costo": mayor_costo,
        "informativo": 0,
        "requiere_periodo_fiscal": requiere_periodo,
        "permite_diferir_periodo": permite_diferir,
    }


def migrar_configuracion_contable_actual(
    *,
    empresa_id: int = 1,
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Ejecuta la primera migración lógica hacia la arquitectura nueva.

    No borra configuraciones actuales.
    Crea copias en las nuevas tablas configurables.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)

    try:
        asegurar_estructura_maestro(conn)

        resultado_plan = migrar_plan_actual_a_plan_empresa(
            empresa_id=empresa_id,
            usuario=usuario,
            conn=conn,
        )
        if not resultado_plan.get("ok"):
            raise RuntimeError(resultado_plan.get("error", "Error migrando plan actual."))

        resultado_categorias = migrar_categorias_compra_actuales(
            empresa_id=empresa_id,
            usuario=usuario,
            conn=conn,
        )
        if not resultado_categorias.get("ok"):
            raise RuntimeError(resultado_categorias.get("error", "Error migrando categorías de compra."))

        resultado_conceptos = migrar_conceptos_fiscales_compra_actuales(
            empresa_id=empresa_id,
            usuario=usuario,
            conn=conn,
        )
        if not resultado_conceptos.get("ok"):
            raise RuntimeError(resultado_conceptos.get("error", "Error migrando conceptos fiscales."))

        if propia:
            conn.commit()

        return {
            "ok": True,
            "plan": resultado_plan,
            "categorias": resultado_categorias,
            "conceptos_fiscales": resultado_conceptos,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        if propia:
            conn.close()