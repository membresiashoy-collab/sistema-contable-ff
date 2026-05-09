from __future__ import annotations

from datetime import datetime
import re
import sqlite3
import unicodedata
from typing import Any

from core.contabilidad_coherencia import (
    COMPORTAMIENTOS_CONTABLES,
    COMPORTAMIENTOS_CRITICOS,
    comportamientos_para_selector,
    describir_comportamiento,
    normalizar_codigo,
    validar_comportamiento_contable,
)
from services.coherencia_contable_service import aplicar_migracion_nucleo


def _conectar_default() -> sqlite3.Connection:
    from database import conectar

    return conectar()


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row


def _fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _first_existing(columnas: set[str], candidatos: tuple[str, ...]) -> str | None:
    for candidato in candidatos:
        if candidato in columnas:
            return candidato
    return None


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _normalizar_importe_bool(valor: Any, default: bool = True) -> bool:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    texto = str(valor).strip().upper()
    if texto in {"0", "NO", "N", "FALSE", "FALSO"}:
        return False
    if texto in {"1", "SI", "SÍ", "S", "TRUE", "VERDADERO"}:
        return True
    return default


def _split_comportamientos(valor: Any) -> list[str]:
    if valor is None:
        return []
    partes = str(valor).replace(";", ",").replace("|", ",").split(",")
    resultado: list[str] = []
    for parte in partes:
        codigo = normalizar_codigo(parte)
        if codigo and codigo not in resultado:
            resultado.append(codigo)
    return resultado


def _join_comportamientos(comportamientos: list[str] | set[str]) -> str:
    ordenados = sorted({normalizar_codigo(item) for item in comportamientos if normalizar_codigo(item)})
    return ",".join(ordenados)


def _agregar_columna_si_falta(conn: sqlite3.Connection, tabla: str, columna: str, definicion: str) -> None:
    if columna not in _columns(conn, tabla):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def migrar_configuracion_comportamientos(conn: sqlite3.Connection | None = None) -> None:
    """
    Asegura la estructura de configuración de comportamientos contables.

    La migración es incremental y segura: no borra datos, no reescribe el plan
    de cuentas y mantiene compatibilidad con bases anteriores que ya tenían la
    tabla creada por el núcleo de coherencia contable.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        aplicar_migracion_nucleo(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contabilidad_cuentas_comportamiento_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                mapeo_id INTEGER,
                codigo_cuenta TEXT,
                comportamiento TEXT,
                evento TEXT NOT NULL,
                detalle TEXT,
                usuario TEXT,
                fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contabilidad_comportamientos_eventos_empresa
            ON contabilidad_cuentas_comportamiento_eventos(empresa_id, fecha_evento)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contabilidad_comportamientos_eventos_cuenta
            ON contabilidad_cuentas_comportamiento_eventos(empresa_id, codigo_cuenta, comportamiento)
            """
        )

        if _table_exists(conn, "contabilidad_cuentas_comportamiento"):
            columnas_a_agregar = {
                "cuenta_nombre": "TEXT",
                "usuario_creacion": "TEXT",
                "usuario_actualizacion": "TEXT",
                "usuario_baja": "TEXT",
                "fecha_baja": "TEXT",
                "motivo_baja": "TEXT",
            }
            for columna, definicion in columnas_a_agregar.items():
                _agregar_columna_si_falta(conn, "contabilidad_cuentas_comportamiento", columna, definicion)

        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def _registrar_evento(
    conn: sqlite3.Connection,
    *,
    empresa_id: int | None,
    mapeo_id: int | None,
    codigo_cuenta: str,
    comportamiento: str,
    evento: str,
    detalle: str,
    usuario: str | None,
) -> None:
    migrar_configuracion_comportamientos(conn)
    conn.execute(
        """
        INSERT INTO contabilidad_cuentas_comportamiento_eventos
        (empresa_id, mapeo_id, codigo_cuenta, comportamiento, evento, detalle, usuario, fecha_evento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (empresa_id, mapeo_id, codigo_cuenta, comportamiento, evento, detalle, usuario, _now_iso()),
    )


def _datos_plan_cuentas(conn: sqlite3.Connection) -> dict[str, str | None]:
    if not _table_exists(conn, "plan_cuentas"):
        return {}
    columnas = _columns(conn, "plan_cuentas")
    return {
        "empresa": _first_existing(columnas, ("empresa_id", "id_empresa")),
        "codigo": _first_existing(columnas, ("codigo", "codigo_cuenta", "cuenta_codigo", "cuenta")),
        "nombre": _first_existing(columnas, ("nombre", "nombre_cuenta", "descripcion", "detalle")),
        "comportamiento": _first_existing(columnas, ("comportamiento_contable", "comportamiento", "tipo_operativo")),
        "imputable": _first_existing(columnas, ("imputable", "recibe_movimientos", "permite_imputacion", "permite_imputacion_operativa")),
        "requiere_auxiliar": _first_existing(columnas, ("requiere_auxiliar", "auxiliar_obligatorio")),
        "permite_imputacion": _first_existing(columnas, ("permite_imputacion_operativa", "permite_imputacion")),
        "modulo_preferido": _first_existing(columnas, ("modulo_origen_preferido", "modulo_preferido")),
    }


def _obtener_cuenta_plan(
    conn: sqlite3.Connection,
    *,
    empresa_id: int | None,
    codigo_cuenta: str,
) -> dict[str, Any] | None:
    datos = _datos_plan_cuentas(conn)
    col_codigo = datos.get("codigo")
    if not col_codigo:
        return None

    where = [f"{col_codigo} = ?"]
    params: list[Any] = [codigo_cuenta]
    if empresa_id is not None and datos.get("empresa"):
        where.append(f"{datos['empresa']} = ?")
        params.append(empresa_id)

    sql = "SELECT rowid AS __rowid__, * FROM plan_cuentas WHERE " + " AND ".join(where) + " LIMIT 1"
    filas = _fetch_dicts(conn, sql, tuple(params))
    return filas[0] if filas else None


def listar_mapeos_comportamientos(
    empresa_id: int | None = None,
    *,
    incluir_inactivos: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        where = []
        params: list[Any] = []
        if empresa_id is not None:
            where.append("(empresa_id = ? OR empresa_id IS NULL)")
            params.append(empresa_id)
        if not incluir_inactivos:
            where.append("activo = 1")
        sql = """
            SELECT
                id,
                empresa_id,
                cuenta_id,
                codigo_cuenta,
                cuenta_nombre,
                comportamiento,
                activo,
                origen,
                observaciones,
                creado_en,
                actualizado_en,
                usuario_creacion,
                usuario_actualizacion,
                fecha_baja,
                motivo_baja
            FROM contabilidad_cuentas_comportamiento
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY activo DESC, comportamiento, codigo_cuenta"
        filas = _fetch_dicts(conn, sql, tuple(params))
        for fila in filas:
            datos = describir_comportamiento(fila.get("comportamiento")) or {}
            fila["comportamiento_nombre"] = datos.get("nombre", fila.get("comportamiento"))
            fila["naturaleza"] = datos.get("naturaleza", "")
            fila["activo_bool"] = bool(fila.get("activo"))
        return filas
    finally:
        if propia:
            conn.close()


def listar_cuentas_plan(
    empresa_id: int | None = None,
    *,
    filtro: str | None = None,
    solo_imputables: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        if not _table_exists(conn, "plan_cuentas"):
            return []

        datos = _datos_plan_cuentas(conn)
        col_empresa = datos.get("empresa")
        col_codigo = datos.get("codigo")
        col_nombre = datos.get("nombre")
        if not col_codigo:
            return []

        where = []
        params: list[Any] = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)
        if filtro:
            where.append(f"(UPPER({col_codigo}) LIKE ? OR UPPER(COALESCE({col_nombre}, '')) LIKE ?)")
            patron = f"%{str(filtro).upper()}%"
            params.extend([patron, patron])

        select_cols = [
            "rowid AS cuenta_id",
            f"{col_codigo} AS codigo_cuenta",
            f"COALESCE({col_nombre}, '') AS nombre_cuenta" if col_nombre else "'' AS nombre_cuenta",
        ]
        if col_empresa:
            select_cols.append(f"{col_empresa} AS empresa_id")
        else:
            select_cols.append("NULL AS empresa_id")
        if datos.get("comportamiento"):
            select_cols.append(f"{datos['comportamiento']} AS comportamiento_plan")
        else:
            select_cols.append("NULL AS comportamiento_plan")
        if datos.get("imputable"):
            select_cols.append(f"{datos['imputable']} AS imputable_raw")
        else:
            select_cols.append("NULL AS imputable_raw")
        if datos.get("requiere_auxiliar"):
            select_cols.append(f"{datos['requiere_auxiliar']} AS requiere_auxiliar_raw")
        else:
            select_cols.append("NULL AS requiere_auxiliar_raw")
        if datos.get("permite_imputacion"):
            select_cols.append(f"{datos['permite_imputacion']} AS permite_imputacion_raw")
        else:
            select_cols.append("NULL AS permite_imputacion_raw")
        if datos.get("modulo_preferido"):
            select_cols.append(f"{datos['modulo_preferido']} AS modulo_origen_preferido")
        else:
            select_cols.append("NULL AS modulo_origen_preferido")

        sql = "SELECT " + ", ".join(select_cols) + " FROM plan_cuentas"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {col_codigo}"

        cuentas = _fetch_dicts(conn, sql, tuple(params))
        mapeos = listar_mapeos_comportamientos(empresa_id=empresa_id, conn=conn)
        mapeos_por_codigo: dict[str, list[dict[str, Any]]] = {}
        for mapeo in mapeos:
            codigo = str(mapeo.get("codigo_cuenta") or "").strip()
            if codigo:
                mapeos_por_codigo.setdefault(codigo, []).append(mapeo)

        resultado: list[dict[str, Any]] = []
        for cuenta in cuentas:
            codigo = str(cuenta.get("codigo_cuenta") or "").strip()
            comportamiento_plan = _split_comportamientos(cuenta.get("comportamiento_plan"))
            comportamientos_mapeados = [m["comportamiento"] for m in mapeos_por_codigo.get(codigo, [])]
            comportamientos = []
            for item in comportamientos_mapeados + comportamiento_plan:
                item_norm = normalizar_codigo(item)
                if item_norm and item_norm not in comportamientos:
                    comportamientos.append(item_norm)

            imputable = _normalizar_importe_bool(cuenta.get("imputable_raw"), default=True)
            fila = {
                "cuenta_id": cuenta.get("cuenta_id"),
                "empresa_id": cuenta.get("empresa_id"),
                "codigo_cuenta": codigo,
                "nombre_cuenta": cuenta.get("nombre_cuenta") or "",
                "imputable": imputable,
                "requiere_auxiliar": _normalizar_importe_bool(cuenta.get("requiere_auxiliar_raw"), default=False),
                "permite_imputacion_operativa": _normalizar_importe_bool(cuenta.get("permite_imputacion_raw"), default=True),
                "modulo_origen_preferido": cuenta.get("modulo_origen_preferido") or "",
                "comportamientos": comportamientos,
                "comportamientos_texto": _join_comportamientos(comportamientos),
                "cantidad_comportamientos": len(comportamientos),
            }
            if solo_imputables and not imputable:
                continue
            resultado.append(fila)
        return resultado
    finally:
        if propia:
            conn.close()


def obtener_resumen_configuracion_comportamientos(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        cuentas = listar_cuentas_plan(empresa_id=empresa_id, conn=conn)
        mapeos = listar_mapeos_comportamientos(empresa_id=empresa_id, conn=conn)
        detectados = {normalizar_codigo(m.get("comportamiento")) for m in mapeos if m.get("activo") == 1}
        for cuenta in cuentas:
            detectados.update(cuenta.get("comportamientos") or [])
        faltantes = [codigo for codigo in COMPORTAMIENTOS_CRITICOS if codigo not in detectados]
        cuentas_con_mapeo = [cuenta for cuenta in cuentas if cuenta.get("cantidad_comportamientos", 0) > 0]
        return {
            "total_cuentas": len(cuentas),
            "cuentas_con_mapeo": len(cuentas_con_mapeo),
            "cuentas_sin_mapeo": max(len(cuentas) - len(cuentas_con_mapeo), 0),
            "mapeos_activos": len([m for m in mapeos if m.get("activo") == 1]),
            "comportamientos_detectados": len(detectados),
            "criticos_total": len(COMPORTAMIENTOS_CRITICOS),
            "criticos_cubiertos": len(COMPORTAMIENTOS_CRITICOS) - len(faltantes),
            "criticos_faltantes": faltantes,
            "criticos_faltantes_texto": ", ".join(faltantes),
        }
    finally:
        if propia:
            conn.close()


_REGLAS_SUGERENCIA: list[tuple[str, tuple[str, ...], str]] = [
    ("CAJA", (r"\bCAJA\b", r"FONDO FIJO", r"EFECTIVO"), "Alta"),
    ("BANCO", (r"\bBANCO\b", r"\bBCO\b", r"CUENTA CORRIENTE", r"CTA CTE", r"CBU", r"MERCADO PAGO"), "Alta"),
    ("IVA_CREDITO", (r"IVA.*CREDITO", r"CREDITO.*FISCAL", r"IVA COMPRAS"), "Alta"),
    ("IVA_DEBITO", (r"IVA.*DEBITO", r"DEBITO.*FISCAL", r"IVA VENTAS"), "Alta"),
    ("CAPITAL_SOCIAL", (r"CAPITAL SOCIAL", r"CAPITAL SUSCRIPTO", r"ACCIONES EN CIRCULACION"), "Alta"),
    ("SOCIOS_INTEGRACION", (r"SOCIOS.*INTEGR", r"ACCIONISTAS.*INTEGR", r"INTEGRACION.*CAPITAL", r"APORTES A INTEGRAR"), "Media"),
    ("APORTE_IRREVOCABLE", (r"APORTE.*IRREVOCABLE", r"APORTES.*FUTURA CAPITALIZACION"), "Alta"),
    ("PRESTAMO_SOCIO", (r"PRESTAMO.*SOCIO", r"SOCIO.*PRESTAMO", r"DEUDA.*SOCIO"), "Media"),
    ("CUENTA_PARTICULAR_SOCIO", (r"CUENTA PARTICULAR.*SOCIO", r"SOCIO.*CUENTA PARTICULAR", r"RETIRO.*SOCIO"), "Media"),
    ("SUELDOS_GASTO", (r"SUELDOS Y JORNALES", r"REMUNERACIONES", r"HABERES"), "Alta"),
    ("SUELDOS_A_PAGAR", (r"SUELDOS A PAGAR", r"REMUNERACIONES A PAGAR", r"HABERES A PAGAR"), "Alta"),
    ("CARGAS_SOCIALES_GASTO", (r"CARGAS SOCIALES$", r"CONTRIBUCIONES PATRONALES", r"SEGURIDAD SOCIAL GASTO"), "Media"),
    ("CARGAS_SOCIALES_A_PAGAR", (r"CARGAS SOCIALES A PAGAR", r"SIPA A PAGAR", r"931 A PAGAR"), "Alta"),
    ("ART_A_PAGAR", (r"ART A PAGAR", r"ASEGURADORA.*RIESGO"), "Alta"),
    ("OBRA_SOCIAL_A_PAGAR", (r"OBRA SOCIAL A PAGAR", r"OSDE A PAGAR", r"O\.S\. A PAGAR"), "Alta"),
    ("SINDICATO_A_PAGAR", (r"SINDICATO A PAGAR", r"SEC A PAGAR", r"FAECYS A PAGAR"), "Media"),
]


def sugerir_comportamiento_para_cuenta(codigo_cuenta: Any, nombre_cuenta: Any) -> dict[str, Any] | None:
    texto = _normalizar_texto(f"{codigo_cuenta or ''} {nombre_cuenta or ''}")
    if not texto:
        return None

    for comportamiento, patrones, confianza in _REGLAS_SUGERENCIA:
        for patron in patrones:
            if re.search(patron, texto):
                datos = describir_comportamiento(comportamiento) or {}
                return {
                    "codigo_cuenta": str(codigo_cuenta or "").strip(),
                    "nombre_cuenta": str(nombre_cuenta or "").strip(),
                    "comportamiento": comportamiento,
                    "comportamiento_nombre": datos.get("nombre", comportamiento),
                    "naturaleza": datos.get("naturaleza", ""),
                    "confianza": confianza,
                    "motivo": f"Sugerido por coincidencia con patrón: {patron}",
                }
    return None


def listar_sugerencias_comportamientos(
    empresa_id: int | None = None,
    *,
    incluir_ya_mapeadas: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        cuentas = listar_cuentas_plan(empresa_id=empresa_id, conn=conn)
        sugerencias: list[dict[str, Any]] = []
        for cuenta in cuentas:
            sugerencia = sugerir_comportamiento_para_cuenta(cuenta.get("codigo_cuenta"), cuenta.get("nombre_cuenta"))
            if not sugerencia:
                continue
            ya_mapeados = set(cuenta.get("comportamientos") or [])
            if sugerencia["comportamiento"] in ya_mapeados and not incluir_ya_mapeadas:
                continue
            sugerencia["ya_mapeado"] = sugerencia["comportamiento"] in ya_mapeados
            sugerencias.append(sugerencia)
        sugerencias.sort(key=lambda item: (item.get("ya_mapeado", False), item.get("confianza") != "Alta", item.get("codigo_cuenta", "")))
        return sugerencias
    finally:
        if propia:
            conn.close()


def _sincronizar_plan_cuenta_desde_mapeos(
    conn: sqlite3.Connection,
    *,
    empresa_id: int | None,
    codigo_cuenta: str,
) -> None:
    if not _table_exists(conn, "plan_cuentas"):
        return
    datos = _datos_plan_cuentas(conn)
    col_codigo = datos.get("codigo")
    col_empresa = datos.get("empresa")
    col_comportamiento = datos.get("comportamiento")
    if not col_codigo or not col_comportamiento:
        return

    where = ["activo = 1", "codigo_cuenta = ?"]
    params: list[Any] = [codigo_cuenta]
    if empresa_id is not None:
        where.append("(empresa_id = ? OR empresa_id IS NULL)")
        params.append(empresa_id)
    sql = "SELECT comportamiento FROM contabilidad_cuentas_comportamiento WHERE " + " AND ".join(where)
    activos = [normalizar_codigo(row["comportamiento"]) for row in _fetch_dicts(conn, sql, tuple(params))]
    texto = _join_comportamientos(activos)

    update_where = [f"{col_codigo} = ?"]
    update_params: list[Any] = [texto, codigo_cuenta]
    if empresa_id is not None and col_empresa:
        update_where.append(f"{col_empresa} = ?")
        update_params.append(empresa_id)
    conn.execute(
        f"UPDATE plan_cuentas SET {col_comportamiento} = ? WHERE " + " AND ".join(update_where),
        tuple(update_params),
    )


def guardar_comportamiento_cuenta(
    *,
    empresa_id: int | None,
    codigo_cuenta: str,
    comportamiento: str,
    usuario: str | None = None,
    observaciones: str | None = None,
    origen: str = "MANUAL",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        codigo_cuenta = str(codigo_cuenta or "").strip()
        comportamiento = normalizar_codigo(comportamiento)
        if not codigo_cuenta:
            return {"ok": False, "mensaje": "Debés seleccionar una cuenta del plan de cuentas."}
        if not validar_comportamiento_contable(comportamiento):
            return {"ok": False, "mensaje": f"Comportamiento no reconocido: {comportamiento}."}

        cuenta = _obtener_cuenta_plan(conn, empresa_id=empresa_id, codigo_cuenta=codigo_cuenta)
        if cuenta is None:
            return {"ok": False, "mensaje": f"No se encontró la cuenta {codigo_cuenta} en el plan de cuentas."}

        datos_plan = _datos_plan_cuentas(conn)
        cuenta_id = cuenta.get("__rowid__")
        cuenta_nombre = cuenta.get(datos_plan.get("nombre")) if datos_plan.get("nombre") else ""

        existente = _fetch_dicts(
            conn,
            """
            SELECT *
            FROM contabilidad_cuentas_comportamiento
            WHERE codigo_cuenta = ?
              AND comportamiento = ?
              AND COALESCE(empresa_id, -1) = COALESCE(?, -1)
            ORDER BY activo DESC, id DESC
            LIMIT 1
            """,
            (codigo_cuenta, comportamiento, empresa_id),
        )

        if existente and existente[0].get("activo") == 1:
            return {
                "ok": True,
                "mensaje": "La cuenta ya tenía ese comportamiento activo.",
                "mapeo_id": existente[0].get("id"),
                "sin_cambios": True,
            }

        if existente:
            mapeo_id = existente[0]["id"]
            conn.execute(
                """
                UPDATE contabilidad_cuentas_comportamiento
                SET activo = 1,
                    cuenta_id = ?,
                    cuenta_nombre = ?,
                    origen = ?,
                    observaciones = ?,
                    usuario_actualizacion = ?,
                    actualizado_en = ?,
                    fecha_baja = NULL,
                    usuario_baja = NULL,
                    motivo_baja = NULL
                WHERE id = ?
                """,
                (cuenta_id, cuenta_nombre, origen, observaciones, usuario, _now_iso(), mapeo_id),
            )
            evento = "REACTIVADO"
            detalle = "Se reactivó un comportamiento contable previamente dado de baja."
        else:
            cursor = conn.execute(
                """
                INSERT INTO contabilidad_cuentas_comportamiento
                (empresa_id, cuenta_id, codigo_cuenta, cuenta_nombre, comportamiento, activo, origen, observaciones, creado_en, usuario_creacion)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (empresa_id, cuenta_id, codigo_cuenta, cuenta_nombre, comportamiento, origen, observaciones, _now_iso(), usuario),
            )
            mapeo_id = cursor.lastrowid
            evento = "ALTA"
            detalle = "Se asignó un comportamiento contable a la cuenta."

        _sincronizar_plan_cuenta_desde_mapeos(conn, empresa_id=empresa_id, codigo_cuenta=codigo_cuenta)
        _registrar_evento(
            conn,
            empresa_id=empresa_id,
            mapeo_id=mapeo_id,
            codigo_cuenta=codigo_cuenta,
            comportamiento=comportamiento,
            evento=evento,
            detalle=detalle,
            usuario=usuario,
        )
        if propia:
            conn.commit()
        datos = describir_comportamiento(comportamiento) or {}
        return {
            "ok": True,
            "mensaje": f"Cuenta {codigo_cuenta} configurada como {datos.get('nombre', comportamiento)}.",
            "mapeo_id": mapeo_id,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        raise exc
    finally:
        if propia:
            conn.close()


def desactivar_comportamiento_cuenta(
    *,
    empresa_id: int | None,
    mapeo_id: int | None = None,
    codigo_cuenta: str | None = None,
    comportamiento: str | None = None,
    usuario: str | None = None,
    motivo: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        where = ["activo = 1"]
        params: list[Any] = []
        if mapeo_id is not None:
            where.append("id = ?")
            params.append(mapeo_id)
        else:
            codigo_cuenta = str(codigo_cuenta or "").strip()
            comportamiento = normalizar_codigo(comportamiento)
            if not codigo_cuenta or not comportamiento:
                return {"ok": False, "mensaje": "Falta indicar la cuenta y el comportamiento a desactivar."}
            where.append("codigo_cuenta = ?")
            where.append("comportamiento = ?")
            params.extend([codigo_cuenta, comportamiento])
            if empresa_id is not None:
                where.append("COALESCE(empresa_id, -1) = COALESCE(?, -1)")
                params.append(empresa_id)

        filas = _fetch_dicts(
            conn,
            "SELECT * FROM contabilidad_cuentas_comportamiento WHERE " + " AND ".join(where),
            tuple(params),
        )
        if not filas:
            return {"ok": False, "mensaje": "No se encontró un comportamiento activo para desactivar."}

        ahora = _now_iso()
        for fila in filas:
            conn.execute(
                """
                UPDATE contabilidad_cuentas_comportamiento
                SET activo = 0,
                    fecha_baja = ?,
                    usuario_baja = ?,
                    motivo_baja = ?,
                    usuario_actualizacion = ?,
                    actualizado_en = ?
                WHERE id = ?
                """,
                (ahora, usuario, motivo, usuario, ahora, fila["id"]),
            )
            _sincronizar_plan_cuenta_desde_mapeos(
                conn,
                empresa_id=fila.get("empresa_id") if fila.get("empresa_id") is not None else empresa_id,
                codigo_cuenta=fila.get("codigo_cuenta"),
            )
            _registrar_evento(
                conn,
                empresa_id=fila.get("empresa_id") if fila.get("empresa_id") is not None else empresa_id,
                mapeo_id=fila.get("id"),
                codigo_cuenta=fila.get("codigo_cuenta"),
                comportamiento=fila.get("comportamiento"),
                evento="BAJA",
                detalle=motivo or "Se desactivó el comportamiento contable de la cuenta.",
                usuario=usuario,
            )
        if propia:
            conn.commit()
        return {"ok": True, "mensaje": f"Se desactivaron {len(filas)} comportamiento(s).", "cantidad": len(filas)}
    except Exception as exc:
        if propia:
            conn.rollback()
        raise exc
    finally:
        if propia:
            conn.close()


def aplicar_sugerencias_comportamientos(
    *,
    empresa_id: int | None,
    sugerencias: list[dict[str, Any]],
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        procesadas = 0
        errores: list[str] = []
        for sugerencia in sugerencias:
            resultado = guardar_comportamiento_cuenta(
                empresa_id=empresa_id,
                codigo_cuenta=sugerencia.get("codigo_cuenta"),
                comportamiento=sugerencia.get("comportamiento"),
                usuario=usuario,
                observaciones=sugerencia.get("motivo") or "Aplicado desde sugerencia automática.",
                origen="SUGERENCIA",
                conn=conn,
            )
            if resultado.get("ok"):
                procesadas += 1
            else:
                errores.append(resultado.get("mensaje", "Error sin detalle."))
        if propia:
            conn.commit()
        return {"ok": not errores, "procesadas": procesadas, "errores": errores}
    except Exception as exc:
        if propia:
            conn.rollback()
        raise exc
    finally:
        if propia:
            conn.close()


def listar_eventos_comportamientos(
    empresa_id: int | None = None,
    *,
    limite: int = 100,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        where = []
        params: list[Any] = []
        if empresa_id is not None:
            where.append("(empresa_id = ? OR empresa_id IS NULL)")
            params.append(empresa_id)
        sql = """
            SELECT id, empresa_id, mapeo_id, codigo_cuenta, comportamiento, evento, detalle, usuario, fecha_evento
            FROM contabilidad_cuentas_comportamiento_eventos
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY fecha_evento DESC, id DESC LIMIT ?"
        params.append(max(int(limite or 100), 1))
        return _fetch_dicts(conn, sql, tuple(params))
    finally:
        if propia:
            conn.close()


def listar_catalogo_comportamientos() -> list[dict[str, Any]]:
    return comportamientos_para_selector()