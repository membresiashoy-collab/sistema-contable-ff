from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import sqlite3
from typing import Any, Iterable

from core.contabilidad_coherencia import (
    COMPORTAMIENTOS_CONTABLES,
    COMPORTAMIENTOS_CRITICOS,
    ORIGENES_ECONOMICOS_OPERATIVOS,
    DiagnosticoCoherencia,
    convertir_a_fecha,
    fecha_en_rango,
    formatear_fecha_argentina,
    normalizar_codigo,
    normalizar_fecha_iso,
    rangos_superpuestos,
    severidad_orden,
    validar_rango_ejercicio,
    SEVERIDAD_ADVERTENCIA,
    SEVERIDAD_ERROR,
    SEVERIDAD_INFO,
    SEVERIDAD_OK,
)


def _conectar_default() -> sqlite3.Connection:
    from database import conectar

    return conectar()


def _dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    return {columna[0]: row[indice] for indice, columna in enumerate(cursor.description)}


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row


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


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    return column_name in _columns(conn, table_name)


def _first_existing(columns: set[str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], sqlite3.Row):
        return [dict(row) for row in rows]
    return [_dict_factory(cursor, row) for row in rows]


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def aplicar_migracion_nucleo(conn: sqlite3.Connection | None = None) -> None:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contabilidad_cuentas_comportamiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                cuenta_id INTEGER,
                codigo_cuenta TEXT,
                comportamiento TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                origen TEXT NOT NULL DEFAULT 'MANUAL',
                observaciones TEXT,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contabilidad_cuentas_comportamiento_empresa
            ON contabilidad_cuentas_comportamiento(empresa_id, comportamiento, activo)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contabilidad_cuentas_comportamiento_cuenta
            ON contabilidad_cuentas_comportamiento(cuenta_id, codigo_cuenta)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contabilidad_origenes_economicos (
                codigo TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                modulo TEXT,
                descripcion TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contabilidad_diagnosticos_coherencia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                fecha_diagnostico TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                area TEXT NOT NULL,
                severidad TEXT NOT NULL,
                codigo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                detalle TEXT,
                referencia_tipo TEXT,
                referencia_id TEXT,
                resuelto INTEGER NOT NULL DEFAULT 0,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contabilidad_diagnosticos_empresa
            ON contabilidad_diagnosticos_coherencia(empresa_id, resuelto, severidad, area)
            """
        )

        for codigo, datos in ORIGENES_ECONOMICOS_OPERATIVOS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO contabilidad_origenes_economicos
                (codigo, nombre, modulo, descripcion, activo)
                VALUES (?, ?, ?, ?, 1)
                """,
                (codigo, datos["nombre"], datos["modulo"], datos["descripcion"]),
            )

        if _table_exists(conn, "plan_cuentas"):
            columnas_plan = _columns(conn, "plan_cuentas")
            columnas_a_agregar = {
                "comportamiento_contable": "TEXT",
                "requiere_auxiliar": "INTEGER NOT NULL DEFAULT 0",
                "permite_imputacion_operativa": "INTEGER NOT NULL DEFAULT 1",
                "modulo_origen_preferido": "TEXT",
            }
            for columna, definicion in columnas_a_agregar.items():
                if columna not in columnas_plan:
                    conn.execute(f"ALTER TABLE plan_cuentas ADD COLUMN {columna} {definicion}")

        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def diagnostico(
    area: str,
    severidad: str,
    codigo: str,
    titulo: str,
    detalle: str,
    referencia_tipo: str | None = None,
    referencia_id: int | str | None = None,
) -> DiagnosticoCoherencia:
    return DiagnosticoCoherencia(
        area=area,
        severidad=severidad,
        codigo=codigo,
        titulo=titulo,
        detalle=detalle,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
    )


def diagnosticar_ejercicios_contables(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []
    try:
        if not _table_exists(conn, "ejercicios_contables"):
            return [
                diagnostico(
                    "Ejercicios",
                    SEVERIDAD_ADVERTENCIA,
                    "EJERCICIOS_TABLA_INEXISTENTE",
                    "No existe la tabla de ejercicios contables",
                    "El núcleo no puede validar ejercicios hasta que exista la tabla ejercicios_contables.",
                ).as_dict()
            ]

        columnas = _columns(conn, "ejercicios_contables")
        col_id = _first_existing(columnas, ("id", "ejercicio_id")) or "rowid"
        col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
        col_inicio = _first_existing(columnas, ("fecha_inicio", "fecha_desde", "desde", "inicio"))
        col_fin = _first_existing(columnas, ("fecha_fin", "fecha_hasta", "hasta", "cierre", "fecha_cierre"))
        col_actual = _first_existing(columnas, ("es_actual", "actual", "ejercicio_actual", "vigente"))
        col_estado = _first_existing(columnas, ("estado", "activo"))

        if not col_inicio or not col_fin:
            return [
                diagnostico(
                    "Ejercicios",
                    SEVERIDAD_ERROR,
                    "EJERCICIOS_COLUMNAS_FECHA_FALTANTES",
                    "La tabla de ejercicios no tiene columnas de fecha reconocibles",
                    "Se esperaban columnas como fecha_inicio/fecha_fin o equivalentes.",
                ).as_dict()
            ]

        where = []
        params: list[Any] = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)
        sql = "SELECT rowid AS __rowid__, * FROM ejercicios_contables"
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = _fetch_dicts(conn, sql, tuple(params))

        ejercicios_validos: list[dict[str, Any]] = []
        for row in rows:
            row_id = row.get(col_id) if col_id != "rowid" else row.get("__rowid__")
            estado = str(row.get(col_estado, "")).upper() if col_estado else ""
            if estado in {"ANULADO", "ELIMINADO", "INACTIVO", "0"}:
                continue

            errores_rango = validar_rango_ejercicio(row.get(col_inicio), row.get(col_fin))
            for error in errores_rango:
                resultados.append(
                    diagnostico(
                        error.area,
                        error.severidad,
                        error.codigo,
                        error.titulo,
                        error.detalle,
                        "ejercicios_contables",
                        row_id,
                    )
                )
            if errores_rango:
                continue

            ejercicios_validos.append(
                {
                    "id": row_id,
                    "empresa_id": row.get(col_empresa) if col_empresa else None,
                    "fecha_inicio": normalizar_fecha_iso(row.get(col_inicio)),
                    "fecha_fin": normalizar_fecha_iso(row.get(col_fin)),
                    "es_actual": bool(row.get(col_actual)) if col_actual else False,
                    "estado": estado,
                }
            )

        grupos: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for ejercicio in ejercicios_validos:
            clave_empresa = ejercicio["empresa_id"] if ejercicio["empresa_id"] is not None else "SIN_EMPRESA"
            grupos[clave_empresa].append(ejercicio)

        for clave_empresa, ejercicios in grupos.items():
            actuales = [ejercicio for ejercicio in ejercicios if ejercicio["es_actual"]]
            if len(actuales) > 1:
                ids = ", ".join(str(ejercicio["id"]) for ejercicio in actuales)
                resultados.append(
                    diagnostico(
                        "Ejercicios",
                        SEVERIDAD_ERROR,
                        "EJERCICIOS_MULTIPLES_ACTUALES",
                        "Hay más de un ejercicio marcado como actual",
                        f"Empresa {clave_empresa}: ejercicios actuales detectados: {ids}.",
                        "ejercicios_contables",
                        ids,
                    )
                )

            ordenados = sorted(ejercicios, key=lambda item: (item["fecha_inicio"], item["fecha_fin"], str(item["id"])))
            for indice, ejercicio_a in enumerate(ordenados):
                for ejercicio_b in ordenados[indice + 1 :]:
                    if rangos_superpuestos(
                        ejercicio_a["fecha_inicio"],
                        ejercicio_a["fecha_fin"],
                        ejercicio_b["fecha_inicio"],
                        ejercicio_b["fecha_fin"],
                    ):
                        resultados.append(
                            diagnostico(
                                "Ejercicios",
                                SEVERIDAD_ERROR,
                                "EJERCICIOS_SUPERPUESTOS",
                                "Hay ejercicios contables superpuestos",
                                "Los ejercicios "
                                f"{ejercicio_a['id']} ({formatear_fecha_argentina(ejercicio_a['fecha_inicio'])} a {formatear_fecha_argentina(ejercicio_a['fecha_fin'])}) "
                                "y "
                                f"{ejercicio_b['id']} ({formatear_fecha_argentina(ejercicio_b['fecha_inicio'])} a {formatear_fecha_argentina(ejercicio_b['fecha_fin'])}) "
                                "se pisan entre sí.",
                                "ejercicios_contables",
                                f"{ejercicio_a['id']},{ejercicio_b['id']}",
                            )
                        )

        if not resultados:
            resultados.append(
                diagnostico(
                    "Ejercicios",
                    SEVERIDAD_OK,
                    "EJERCICIOS_OK",
                    "Ejercicios contables sin incoherencias críticas",
                    "No se detectaron rangos invertidos, ejercicios superpuestos ni múltiples ejercicios actuales.",
                )
            )

        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()


def _comportamientos_desde_plan(row: dict[str, Any], col_comportamiento: str | None) -> set[str]:
    if not col_comportamiento:
        return set()
    valor = row.get(col_comportamiento)
    if valor is None:
        return set()
    partes = str(valor).replace(";", ",").replace("|", ",").split(",")
    return {normalizar_codigo(parte) for parte in partes if normalizar_codigo(parte)}


def diagnosticar_plan_cuentas(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """
    Diagnóstico del Plan de Cuentas como fuente de verdad.

    Desde Plan de Cuentas PRO la clasificación vigente debe vivir en:
    - plan_cuentas.comportamiento_contable
    - plan_cuentas.permite_imputacion_operativa
    - plan_cuentas_detallado.imputable

    La tabla contabilidad_cuentas_comportamiento queda como compatibilidad/auditoría,
    no como fuente principal para crear o editar cuentas.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []
    try:
        if not _table_exists(conn, "plan_cuentas"):
            return [
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ERROR,
                    "PLAN_CUENTAS_INEXISTENTE",
                    "No existe el plan de cuentas",
                    "El núcleo de coherencia necesita un plan de cuentas para mapear usos operativos del sistema.",
                ).as_dict()
            ]

        aplicar_migracion_nucleo(conn)

        try:
            from services.plan_cuentas_service import diagnosticar_plan_cuentas_pro

            diagnostico_pro = diagnosticar_plan_cuentas_pro(empresa_id=empresa_id or 1, conn=conn)
        except Exception as exc:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ADVERTENCIA,
                    "PLAN_CUENTAS_PRO_NO_DISPONIBLE",
                    "No se pudo ejecutar el diagnóstico PRO del plan de cuentas",
                    f"Detalle técnico: {exc}",
                )
            )
            diagnostico_pro = None

        if diagnostico_pro:
            for item in diagnostico_pro.get("errores", []):
                resultados.append(
                    diagnostico(
                        "Plan de cuentas",
                        SEVERIDAD_ERROR,
                        "PLAN_CUENTA_NO_IMPUTABLE_CON_COMPORTAMIENTO",
                        "Hay cuentas no imputables con uso operativo asignado",
                        f"{item.get('codigo')} - {item.get('nombre')}: {item.get('problema')}. Acción sugerida: {item.get('accion')}",
                        "plan_cuentas",
                        item.get("codigo"),
                    )
                )
            for item in diagnostico_pro.get("advertencias", []):
                resultados.append(
                    diagnostico(
                        "Plan de cuentas",
                        SEVERIDAD_ADVERTENCIA,
                        "PLAN_COMPORTAMIENTO_POSIBLEMENTE_INCORRECTO",
                        "Hay usos operativos que conviene revisar desde el Plan de Cuentas",
                        f"{item.get('codigo')} - {item.get('nombre')}: {item.get('problema')}. Acción sugerida: {item.get('accion')}",
                        "plan_cuentas",
                        item.get("codigo"),
                    )
                )
            faltantes = diagnostico_pro.get("criticos_faltantes", [])
            if faltantes:
                resultados.append(
                    diagnostico(
                        "Plan de cuentas",
                        SEVERIDAD_ADVERTENCIA,
                        "PLAN_COMPORTAMIENTOS_CRITICOS_FALTANTES",
                        "Faltan usos operativos críticos en el Plan de Cuentas",
                        "No se detectó uso operativo en el Plan de Cuentas para: " + ", ".join(faltantes) + ".",
                    )
                )
            if diagnostico_pro.get("pendientes", 0):
                resultados.append(
                    diagnostico(
                        "Plan de cuentas",
                        SEVERIDAD_INFO,
                        "PLAN_CUENTAS_SIN_COMPORTAMIENTO",
                        "Hay cuentas imputables sin uso operativo opcional",
                        f"Se detectaron {diagnostico_pro.get('pendientes', 0)} cuentas imputables sin uso operativo del sistema. No todas requieren automatización: revise solo las cuentas críticas u operativas antes de cerrar el saneamiento del Plan Maestro FF.",
                    )
                )
            if not resultados:
                resultados.append(
                    diagnostico(
                        "Plan de cuentas",
                        SEVERIDAD_OK,
                        "PLAN_CUENTAS_PRO_OK",
                        "Plan de Cuentas coherente como fuente de verdad",
                        "No se detectaron cuentas no imputables con uso operativo ni usos operativos críticos faltantes.",
                    )
                )
            return [item.as_dict() for item in resultados]

        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()


def _buscar_ejercicio_para_fecha(conn: sqlite3.Connection, empresa_id: int | None, fecha: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "ejercicios_contables"):
        return None
    columnas = _columns(conn, "ejercicios_contables")
    col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
    col_inicio = _first_existing(columnas, ("fecha_inicio", "fecha_desde", "desde", "inicio"))
    col_fin = _first_existing(columnas, ("fecha_fin", "fecha_hasta", "hasta", "cierre", "fecha_cierre"))
    if not col_inicio or not col_fin:
        return None

    where = []
    params: list[Any] = []
    if empresa_id is not None and col_empresa:
        where.append(f"{col_empresa} = ?")
        params.append(empresa_id)
    sql = "SELECT rowid AS __rowid__, * FROM ejercicios_contables"
    if where:
        sql += " WHERE " + " AND ".join(where)
    for row in _fetch_dicts(conn, sql, tuple(params)):
        try:
            if fecha_en_rango(fecha, row.get(col_inicio), row.get(col_fin)):
                return row
        except ValueError:
            continue
    return None


def diagnosticar_libro_diario(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
    limite_revision: int = 5000,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []
    try:
        if not _table_exists(conn, "libro_diario"):
            return [
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_ADVERTENCIA,
                    "LIBRO_DIARIO_INEXISTENTE",
                    "No existe la tabla Libro Diario",
                    "Todavía no hay estructura de Libro Diario para validar trazabilidad y fechas.",
                ).as_dict()
            ]

        columnas = _columns(conn, "libro_diario")
        col_id = _first_existing(columnas, ("id", "asiento_id", "libro_diario_id")) or "rowid"
        col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
        col_fecha = _first_existing(columnas, ("fecha", "fecha_asiento", "fecha_contable"))
        col_ejercicio = _first_existing(columnas, ("ejercicio_id", "id_ejercicio"))
        col_origen = _first_existing(columnas, ("origen", "modulo_origen", "tipo_origen"))
        col_origen_tabla = _first_existing(columnas, ("origen_tabla", "tabla_origen"))
        col_origen_id = _first_existing(columnas, ("origen_id", "id_origen"))

        if not col_fecha:
            return [
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_ERROR,
                    "LIBRO_FECHA_FALTANTE",
                    "Libro Diario sin columna de fecha reconocible",
                    "Se esperaba una columna fecha, fecha_asiento o fecha_contable.",
                ).as_dict()
            ]

        where = []
        params: list[Any] = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)
        sql = "SELECT rowid AS __rowid__, * FROM libro_diario"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY __rowid__ DESC LIMIT ?"
        params.append(limite_revision)

        fechas_invalidas = []
        fechas_fuera_ejercicio = []
        sin_origen = 0
        trazabilidad_incompleta = 0
        rows = _fetch_dicts(conn, sql, tuple(params))
        for row in rows:
            row_id = row.get(col_id) if col_id != "rowid" else row.get("__rowid__")
            fecha = row.get(col_fecha)
            try:
                normalizar_fecha_iso(fecha)
            except ValueError:
                fechas_invalidas.append(row_id)
                continue

            if col_origen and not row.get(col_origen):
                sin_origen += 1
            elif col_origen and row.get(col_origen) and (col_origen_tabla or col_origen_id):
                tiene_origen_tabla = True if not col_origen_tabla else bool(row.get(col_origen_tabla))
                tiene_origen_id = True if not col_origen_id else row.get(col_origen_id) not in (None, "")
                if not (tiene_origen_tabla and tiene_origen_id):
                    trazabilidad_incompleta += 1

            if col_ejercicio and row.get(col_ejercicio) and _table_exists(conn, "ejercicios_contables"):
                ejercicio = _fetch_dicts(
                    conn,
                    "SELECT rowid AS __rowid__, * FROM ejercicios_contables WHERE rowid = ? OR id = ? LIMIT 1"
                    if _column_exists(conn, "ejercicios_contables", "id")
                    else "SELECT rowid AS __rowid__, * FROM ejercicios_contables WHERE rowid = ? LIMIT 1",
                    (row.get(col_ejercicio), row.get(col_ejercicio))
                    if _column_exists(conn, "ejercicios_contables", "id")
                    else (row.get(col_ejercicio),),
                )
                if ejercicio:
                    columnas_ej = _columns(conn, "ejercicios_contables")
                    col_inicio = _first_existing(columnas_ej, ("fecha_inicio", "fecha_desde", "desde", "inicio"))
                    col_fin = _first_existing(columnas_ej, ("fecha_fin", "fecha_hasta", "hasta", "cierre", "fecha_cierre"))
                    if col_inicio and col_fin:
                        try:
                            if not fecha_en_rango(fecha, ejercicio[0].get(col_inicio), ejercicio[0].get(col_fin)):
                                fechas_fuera_ejercicio.append(row_id)
                        except ValueError:
                            pass

        if fechas_invalidas:
            resultados.append(
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_ERROR,
                    "LIBRO_FECHAS_INVALIDAS",
                    "Hay asientos con fechas inválidas",
                    "Asientos afectados: " + ", ".join(map(str, fechas_invalidas[:20])) + ".",
                )
            )

        if fechas_fuera_ejercicio:
            resultados.append(
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_ERROR,
                    "LIBRO_FECHAS_FUERA_EJERCICIO",
                    "Hay asientos vinculados a ejercicios que no contienen su fecha",
                    "Asientos afectados: " + ", ".join(map(str, fechas_fuera_ejercicio[:20])) + ".",
                )
            )

        if sin_origen:
            resultados.append(
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_INFO,
                    "LIBRO_ASIENTOS_SIN_ORIGEN",
                    "Hay asientos sin origen trazable",
                    f"Se detectaron {sin_origen} asientos sin origen informado dentro de los últimos {len(rows)} revisados.",
                )
            )

        if trazabilidad_incompleta:
            resultados.append(
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_INFO,
                    "LIBRO_ASIENTOS_TRAZABILIDAD_HISTORICA_INCOMPLETA",
                    "Hay asientos históricos con trazabilidad técnica incompleta",
                    f"Se detectaron {trazabilidad_incompleta} asientos con origen informado pero sin origen_tabla u origen_id completo. No invalida la contabilidad histórica; queda como normalización técnica pendiente para auditoría y reversos controlados.",
                )
            )

        if not resultados:
            resultados.append(
                diagnostico(
                    "Libro Diario",
                    SEVERIDAD_OK,
                    "LIBRO_DIARIO_OK",
                    "Libro Diario sin inconsistencias críticas detectadas",
                    "No se detectaron fechas inválidas ni desvíos de ejercicio en la muestra revisada.",
                )
            )
        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()


def diagnosticar_inicio_contable_capital(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []
    try:
        tablas_capital = [
            tabla
            for tabla in ("capital_social", "socios_capital", "capital_integraciones", "capital_movimientos")
            if _table_exists(conn, tabla)
        ]
        if not tablas_capital:
            return [
                diagnostico(
                    "Inicio contable / Capital",
                    SEVERIDAD_INFO,
                    "CAPITAL_TABLAS_NO_DETECTADAS",
                    "No se detectaron tablas específicas de capital",
                    "La validación profunda de capital quedará activa cuando existan tablas de capital social o integraciones.",
                ).as_dict()
            ]

        for tabla in tablas_capital:
            columnas = _columns(conn, tabla)
            col_id = _first_existing(columnas, ("id", "capital_id", "movimiento_id")) or "rowid"
            col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
            col_estado = _first_existing(columnas, ("estado", "estado_capital", "estado_movimiento"))
            col_fecha = _first_existing(columnas, ("fecha", "fecha_asiento", "fecha_integracion", "fecha_suscripcion"))
            col_asiento = _first_existing(
                columnas,
                (
                    "asiento_origen_id",
                    "asiento_propuesto_id",
                    "propuesta_id",
                    "libro_diario_id",
                    "asiento_id",
                ),
            )

            where = []
            params: list[Any] = []
            if empresa_id is not None and col_empresa:
                where.append(f"{col_empresa} = ?")
                params.append(empresa_id)
            sql = f"SELECT rowid AS __rowid__, * FROM {tabla}"
            if where:
                sql += " WHERE " + " AND ".join(where)

            for row in _fetch_dicts(conn, sql, tuple(params)):
                row_id = row.get(col_id) if col_id != "rowid" else row.get("__rowid__")
                estado = str(row.get(col_estado, "")).upper() if col_estado else ""
                confirmado = estado in {"CONFIRMADO", "CONTABILIZADO", "CERRADO", "APROBADO"}
                if confirmado and col_asiento and not row.get(col_asiento):
                    resultados.append(
                        diagnostico(
                            "Inicio contable / Capital",
                            SEVERIDAD_ERROR,
                            "CAPITAL_CONFIRMADO_SIN_ASIENTO",
                            "Hay capital confirmado sin asiento o propuesta vinculada",
                            f"Registro {row_id} en {tabla} figura confirmado pero no tiene vínculo contable.",
                            tabla,
                            row_id,
                        )
                    )
                if col_fecha and row.get(col_fecha):
                    try:
                        fecha_iso = normalizar_fecha_iso(row.get(col_fecha))
                    except ValueError:
                        resultados.append(
                            diagnostico(
                                "Inicio contable / Capital",
                                SEVERIDAD_ERROR,
                                "CAPITAL_FECHA_INVALIDA",
                                "Hay registros de capital con fecha inválida",
                                f"Registro {row_id} en {tabla} tiene fecha no interpretable.",
                                tabla,
                                row_id,
                            )
                        )
                        continue
                    if fecha_iso and _buscar_ejercicio_para_fecha(conn, row.get(col_empresa) if col_empresa else empresa_id, fecha_iso) is None:
                        resultados.append(
                            diagnostico(
                                "Inicio contable / Capital",
                                SEVERIDAD_ADVERTENCIA,
                                "CAPITAL_FECHA_SIN_EJERCICIO",
                                "Hay movimientos de capital sin ejercicio contable compatible",
                                f"Registro {row_id} en {tabla} con fecha {formatear_fecha_argentina(fecha_iso)} no cae en ningún ejercicio detectado.",
                                tabla,
                                row_id,
                            )
                        )

        if not resultados:
            resultados.append(
                diagnostico(
                    "Inicio contable / Capital",
                    SEVERIDAD_OK,
                    "CAPITAL_OK",
                    "Inicio contable y capital sin incoherencias críticas detectadas",
                    "No se detectó capital confirmado sin vínculo contable ni fechas fuera de ejercicio.",
                )
            )
        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()




def _valor_activo(valor: Any, default: bool = True) -> bool:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    texto = str(valor).strip().upper()
    if texto in {"0", "NO", "N", "FALSE", "FALSO", "INACTIVO", "BAJA"}:
        return False
    if texto in {"1", "SI", "SÍ", "S", "TRUE", "VERDADERO", "ACTIVO", "ALTA"}:
        return True
    return default


def _clave_cuenta(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return texto


def _claves_busqueda_cuenta(valor: Any) -> set[str]:
    clave = _clave_cuenta(valor)
    if not clave:
        return set()
    claves = {clave, normalizar_codigo(clave)}
    solo_alnum = "".join(caracter for caracter in clave.upper() if caracter.isalnum())
    if solo_alnum:
        claves.add(solo_alnum)
    return {item for item in claves if item}


def _mapa_comportamientos_configurados(
    conn: sqlite3.Connection,
    empresa_id: int | None = None,
) -> dict[str, Any]:
    """
    Devuelve el mapa consolidado de comportamientos contables.

    La fuente principal es `contabilidad_cuentas_comportamiento`, pero también
    se respetan los comportamientos que ya estén sincronizados en
    `plan_cuentas.comportamiento_contable`. Esto permite que el diagnóstico use
    tanto la configuración nueva como bases anteriores o migradas.
    """
    aplicar_migracion_nucleo(conn)

    por_cuenta: dict[str, set[str]] = defaultdict(set)
    por_comportamiento: dict[str, set[str]] = defaultdict(set)
    cuentas_plan: dict[str, dict[str, Any]] = {}
    cuentas_plan_por_nombre: dict[str, dict[str, Any]] = {}

    if _table_exists(conn, "plan_cuentas"):
        columnas_plan = _columns(conn, "plan_cuentas")
        col_empresa = _first_existing(columnas_plan, ("empresa_id", "id_empresa"))
        col_codigo = _first_existing(columnas_plan, ("codigo", "codigo_cuenta", "cuenta_codigo", "cuenta"))
        col_nombre = _first_existing(columnas_plan, ("nombre", "nombre_cuenta", "descripcion", "detalle"))
        col_comportamiento = _first_existing(columnas_plan, ("comportamiento_contable", "comportamiento", "tipo_operativo"))
        col_activo = _first_existing(columnas_plan, ("activo", "vigente"))

        where = []
        params: list[Any] = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)
        if col_activo:
            where.append(f"COALESCE({col_activo}, 1) <> 0")
        sql = "SELECT rowid AS __rowid__, * FROM plan_cuentas"
        if where:
            sql += " WHERE " + " AND ".join(where)

        for row in _fetch_dicts(conn, sql, tuple(params)):
            codigo = _clave_cuenta(row.get(col_codigo)) if col_codigo else str(row.get("__rowid__"))
            nombre = str(row.get(col_nombre, "") or "").strip() if col_nombre else ""
            cuenta = {
                "codigo": codigo,
                "nombre": nombre,
                "rowid": row.get("__rowid__"),
                "empresa_id": row.get(col_empresa) if col_empresa else empresa_id,
            }
            for clave in _claves_busqueda_cuenta(codigo):
                cuentas_plan[clave] = cuenta
            if nombre:
                cuentas_plan_por_nombre[normalizar_codigo(nombre)] = cuenta

            for comportamiento in _comportamientos_desde_plan(row, col_comportamiento):
                if comportamiento in COMPORTAMIENTOS_CONTABLES:
                    for clave in _claves_busqueda_cuenta(codigo):
                        por_cuenta[clave].add(comportamiento)
                    por_comportamiento[comportamiento].add(codigo)

    # Compatibilidad: solo se consulta la tabla histórica si el Plan de Cuentas todavía no tiene comportamientos.
    # La fuente principal de verdad desde Plan de Cuentas PRO es plan_cuentas.comportamiento_contable.
    if not por_cuenta and _table_exists(conn, "contabilidad_cuentas_comportamiento"):
        columnas_map = _columns(conn, "contabilidad_cuentas_comportamiento")
        where_map = ["COALESCE(activo, 1) = 1"]
        params_map: list[Any] = []
        if empresa_id is not None and "empresa_id" in columnas_map:
            where_map.append("(empresa_id = ? OR empresa_id IS NULL)")
            params_map.append(empresa_id)
        sql_map = "SELECT * FROM contabilidad_cuentas_comportamiento WHERE " + " AND ".join(where_map)
        for row in _fetch_dicts(conn, sql_map, tuple(params_map)):
            comportamiento = normalizar_codigo(row.get("comportamiento"))
            codigo = _clave_cuenta(row.get("codigo_cuenta"))
            if not codigo or comportamiento not in COMPORTAMIENTOS_CONTABLES:
                continue
            for clave in _claves_busqueda_cuenta(codigo):
                por_cuenta[clave].add(comportamiento)
            por_comportamiento[comportamiento].add(codigo)

    return {
        "por_cuenta": por_cuenta,
        "por_comportamiento": por_comportamiento,
        "cuentas_plan": cuentas_plan,
        "cuentas_plan_por_nombre": cuentas_plan_por_nombre,
    }


def _comportamientos_de_cuenta(mapa: dict[str, Any], codigo_cuenta: Any, nombre_cuenta: Any = None) -> set[str]:
    comportamientos: set[str] = set()
    por_cuenta: dict[str, set[str]] = mapa.get("por_cuenta", {})
    for clave in _claves_busqueda_cuenta(codigo_cuenta):
        comportamientos.update(por_cuenta.get(clave, set()))

    if not comportamientos and nombre_cuenta:
        cuenta = mapa.get("cuentas_plan_por_nombre", {}).get(normalizar_codigo(nombre_cuenta))
        if cuenta:
            for clave in _claves_busqueda_cuenta(cuenta.get("codigo")):
                comportamientos.update(por_cuenta.get(clave, set()))
    return comportamientos


def _cuenta_tiene_comportamiento(
    mapa: dict[str, Any],
    codigo_cuenta: Any,
    comportamiento: str,
    nombre_cuenta: Any = None,
) -> bool:
    comportamiento_normalizado = normalizar_codigo(comportamiento)
    return comportamiento_normalizado in _comportamientos_de_cuenta(mapa, codigo_cuenta, nombre_cuenta)


def _cuenta_existe_en_plan(mapa: dict[str, Any], codigo_cuenta: Any) -> bool:
    if not _clave_cuenta(codigo_cuenta):
        return False
    cuentas_plan: dict[str, dict[str, Any]] = mapa.get("cuentas_plan", {})
    return any(clave in cuentas_plan for clave in _claves_busqueda_cuenta(codigo_cuenta))


def _descripcion_cuenta(codigo: Any, nombre: Any = None) -> str:
    codigo_txt = str(codigo or "").strip()
    nombre_txt = str(nombre or "").strip()
    if codigo_txt and nombre_txt:
        return f"{codigo_txt} - {nombre_txt}"
    return codigo_txt or nombre_txt or "Sin cuenta informada"


def diagnosticar_comportamientos_configurados(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
    limite_revision: int = 5000,
) -> list[dict[str, Any]]:
    """
    Diagnóstico inteligente basado en el uso operativo informado en el Plan de Cuentas.

    No modifica flujos operativos: solamente cruza el mapa contable configurado
    contra Tesorería, IVA, Capital e imputaciones recientes para detectar cuentas
    críticas mal clasificadas o sin clasificación.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []
    try:
        aplicar_migracion_nucleo(conn)
        mapa = _mapa_comportamientos_configurados(conn, empresa_id=empresa_id)

        if not mapa.get("por_cuenta"):
            resultados.append(
                diagnostico(
                    "Uso operativo del Plan de Cuentas",
                    SEVERIDAD_ADVERTENCIA,
                    "COMPORTAMIENTOS_SIN_CONFIGURACION",
                    "No hay usos operativos configurados",
                    "Configure al menos Caja, Banco, IVA crédito, IVA débito, Capital y cuentas vinculadas para que el diagnóstico pueda validar operaciones reales.",
                )
            )
            return [item.as_dict() for item in resultados]

        if _table_exists(conn, "contabilidad_cuentas_comportamiento"):
            columnas_map = _columns(conn, "contabilidad_cuentas_comportamiento")
            where_map = ["COALESCE(activo, 1) = 1"]
            params_map: list[Any] = []
            if empresa_id is not None and "empresa_id" in columnas_map:
                where_map.append("(empresa_id = ? OR empresa_id IS NULL)")
                params_map.append(empresa_id)
            mapeos_sin_cuenta = []
            cuenta_nombre_expr = "cuenta_nombre" if "cuenta_nombre" in columnas_map else "NULL AS cuenta_nombre"
            sql_map = f"SELECT id, codigo_cuenta, {cuenta_nombre_expr}, comportamiento FROM contabilidad_cuentas_comportamiento WHERE " + " AND ".join(where_map)
            for row in _fetch_dicts(conn, sql_map, tuple(params_map)):
                codigo = row.get("codigo_cuenta")
                comportamiento = normalizar_codigo(row.get("comportamiento"))
                if comportamiento not in COMPORTAMIENTOS_CONTABLES:
                    resultados.append(
                        diagnostico(
                            "Uso operativo del Plan de Cuentas",
                            SEVERIDAD_ERROR,
                            "COMPORTAMIENTO_CONFIGURADO_INVALIDO",
                            "Hay un uso operativo configurado no reconocido",
                            f"La cuenta {_descripcion_cuenta(codigo, row.get('cuenta_nombre'))} tiene el uso operativo {row.get('comportamiento')} que no pertenece al catálogo vigente.",
                            "contabilidad_cuentas_comportamiento",
                            row.get("id"),
                        )
                    )
                if codigo and not _cuenta_existe_en_plan(mapa, codigo):
                    mapeos_sin_cuenta.append(_descripcion_cuenta(codigo, row.get("cuenta_nombre")))
            if mapeos_sin_cuenta:
                resultados.append(
                    diagnostico(
                        "Uso operativo del Plan de Cuentas",
                        SEVERIDAD_ADVERTENCIA,
                        "COMPORTAMIENTO_CUENTA_NO_EXISTE_EN_PLAN",
                        "Hay usos operativos asignados a cuentas que no existen en el plan",
                        "Revise estos mapeos: " + "; ".join(mapeos_sin_cuenta[:15]) + ".",
                    )
                )

        if _table_exists(conn, "tesoreria_cuentas"):
            columnas_tes = _columns(conn, "tesoreria_cuentas")
            col_empresa = _first_existing(columnas_tes, ("empresa_id", "id_empresa"))
            col_tipo = _first_existing(columnas_tes, ("tipo_cuenta", "tipo"))
            col_nombre = _first_existing(columnas_tes, ("nombre", "nombre_cuenta", "descripcion"))
            col_codigo = _first_existing(columnas_tes, ("cuenta_contable_codigo", "codigo_cuenta", "cuenta_codigo"))
            col_cuenta_nombre = _first_existing(columnas_tes, ("cuenta_contable_nombre", "cuenta_nombre"))
            col_activo = _first_existing(columnas_tes, ("activo", "vigente"))
            if col_tipo and col_codigo:
                where = []
                params: list[Any] = []
                if empresa_id is not None and col_empresa:
                    where.append(f"{col_empresa} = ?")
                    params.append(empresa_id)
                if col_activo:
                    where.append(f"COALESCE({col_activo}, 1) <> 0")
                sql = "SELECT rowid AS __rowid__, * FROM tesoreria_cuentas"
                if where:
                    sql += " WHERE " + " AND ".join(where)
                cajas_sin_mapeo = []
                bancos_sin_mapeo = []
                cuentas_sin_codigo = []
                for row in _fetch_dicts(conn, sql, tuple(params)):
                    tipo = normalizar_codigo(row.get(col_tipo))
                    codigo = row.get(col_codigo)
                    nombre_operativo = row.get(col_nombre) if col_nombre else ""
                    nombre_contable = row.get(col_cuenta_nombre) if col_cuenta_nombre else ""
                    if tipo in {"CAJA", "EFECTIVO"}:
                        if not codigo:
                            cuentas_sin_codigo.append(f"Caja {nombre_operativo or row.get('__rowid__')}")
                        elif not _cuenta_tiene_comportamiento(mapa, codigo, "CAJA", nombre_contable):
                            cajas_sin_mapeo.append(_descripcion_cuenta(codigo, nombre_contable or nombre_operativo))
                    if tipo in {"BANCO", "CUENTA_BANCARIA", "CTA_CTE", "CUENTA_CORRIENTE"}:
                        if not codigo:
                            cuentas_sin_codigo.append(f"Banco {nombre_operativo or row.get('__rowid__')}")
                        elif not _cuenta_tiene_comportamiento(mapa, codigo, "BANCO", nombre_contable):
                            bancos_sin_mapeo.append(_descripcion_cuenta(codigo, nombre_contable or nombre_operativo))
                if cuentas_sin_codigo:
                    resultados.append(
                        diagnostico(
                            "Tesorería",
                            SEVERIDAD_ADVERTENCIA,
                            "TESORERIA_CUENTAS_SIN_CUENTA_CONTABLE",
                            "Hay cuentas de tesorería sin cuenta contable vinculada",
                            "Revise: " + "; ".join(cuentas_sin_codigo[:15]) + ".",
                        )
                    )
                if cajas_sin_mapeo:
                    resultados.append(
                        diagnostico(
                            "Tesorería",
                            SEVERIDAD_ADVERTENCIA,
                            "TESORERIA_CAJAS_SIN_COMPORTAMIENTO_CAJA",
                            "Hay cajas operativas sin uso operativo Caja",
                            "Cuentas afectadas: " + "; ".join(cajas_sin_mapeo[:15]) + ".",
                        )
                    )
                if bancos_sin_mapeo:
                    resultados.append(
                        diagnostico(
                            "Tesorería",
                            SEVERIDAD_ADVERTENCIA,
                            "TESORERIA_BANCOS_SIN_COMPORTAMIENTO_BANCO",
                            "Hay bancos operativos sin uso operativo Banco",
                            "Cuentas afectadas: " + "; ".join(bancos_sin_mapeo[:15]) + ".",
                        )
                    )

        if _table_exists(conn, "capital_social_empresa"):
            columnas_cap = _columns(conn, "capital_social_empresa")
            col_empresa = _first_existing(columnas_cap, ("empresa_id", "id_empresa"))
            col_estado = _first_existing(columnas_cap, ("estado", "estado_capital"))
            col_capital_codigo = _first_existing(columnas_cap, ("cuenta_capital_codigo", "cuenta_capital_social_codigo"))
            col_capital_nombre = _first_existing(columnas_cap, ("cuenta_capital_nombre", "cuenta_capital_social_nombre"))
            col_socios_codigo = _first_existing(columnas_cap, ("cuenta_socios_integracion_codigo", "cuenta_socios_codigo"))
            col_socios_nombre = _first_existing(columnas_cap, ("cuenta_socios_integracion_nombre", "cuenta_socios_nombre"))
            where = []
            params: list[Any] = []
            if empresa_id is not None and col_empresa:
                where.append(f"{col_empresa} = ?")
                params.append(empresa_id)
            if col_estado:
                where.append(f"COALESCE({col_estado}, '') NOT IN ('ANULADO', 'ELIMINADO', 'INACTIVO')")
            sql = "SELECT rowid AS __rowid__, * FROM capital_social_empresa"
            if where:
                sql += " WHERE " + " AND ".join(where)
            capital_sin_mapeo = []
            socios_sin_mapeo = []
            for row in _fetch_dicts(conn, sql, tuple(params)):
                if col_capital_codigo and row.get(col_capital_codigo):
                    if not _cuenta_tiene_comportamiento(mapa, row.get(col_capital_codigo), "CAPITAL_SOCIAL", row.get(col_capital_nombre) if col_capital_nombre else None):
                        capital_sin_mapeo.append(_descripcion_cuenta(row.get(col_capital_codigo), row.get(col_capital_nombre) if col_capital_nombre else None))
                if col_socios_codigo and row.get(col_socios_codigo):
                    if not _cuenta_tiene_comportamiento(mapa, row.get(col_socios_codigo), "SOCIOS_INTEGRACION", row.get(col_socios_nombre) if col_socios_nombre else None):
                        socios_sin_mapeo.append(_descripcion_cuenta(row.get(col_socios_codigo), row.get(col_socios_nombre) if col_socios_nombre else None))
            if capital_sin_mapeo:
                resultados.append(
                    diagnostico(
                        "Inicio contable / Capital",
                        SEVERIDAD_ADVERTENCIA,
                        "CAPITAL_CUENTA_CAPITAL_SIN_COMPORTAMIENTO",
                        "La cuenta de capital social no está marcada como Capital social",
                        "Cuentas afectadas: " + "; ".join(sorted(set(capital_sin_mapeo))[:15]) + ".",
                    )
                )
            if socios_sin_mapeo:
                resultados.append(
                    diagnostico(
                        "Inicio contable / Capital",
                        SEVERIDAD_ADVERTENCIA,
                        "CAPITAL_CUENTA_SOCIOS_SIN_COMPORTAMIENTO",
                        "La cuenta de socios por integración no está marcada como Socios / accionistas por integración",
                        "Cuentas afectadas: " + "; ".join(sorted(set(socios_sin_mapeo))[:15]) + ".",
                    )
                )

        if _table_exists(conn, "iva_cierres_asientos_propuestos"):
            columnas_iva = _columns(conn, "iva_cierres_asientos_propuestos")
            col_empresa = _first_existing(columnas_iva, ("empresa_id", "id_empresa"))
            col_estado = _first_existing(columnas_iva, ("estado", "estado_asiento"))
            col_codigo = _first_existing(columnas_iva, ("cuenta_codigo", "codigo_cuenta"))
            col_nombre = _first_existing(columnas_iva, ("cuenta_nombre", "nombre_cuenta"))
            if col_codigo:
                where = []
                params: list[Any] = []
                if empresa_id is not None and col_empresa:
                    where.append(f"{col_empresa} = ?")
                    params.append(empresa_id)
                if col_estado:
                    where.append(f"COALESCE({col_estado}, '') NOT IN ('ANULADO', 'RECHAZADO')")
                sql = "SELECT rowid AS __rowid__, * FROM iva_cierres_asientos_propuestos"
                if where:
                    sql += " WHERE " + " AND ".join(where)
                sql += " ORDER BY __rowid__ DESC LIMIT ?"
                params.append(limite_revision)
                iva_credito_sin_mapeo = []
                iva_debito_sin_mapeo = []
                for row in _fetch_dicts(conn, sql, tuple(params)):
                    codigo = row.get(col_codigo)
                    nombre = row.get(col_nombre) if col_nombre else ""
                    nombre_norm = normalizar_codigo(nombre)
                    if "IVA" not in nombre_norm:
                        continue
                    if "CREDITO" in nombre_norm and not _cuenta_tiene_comportamiento(mapa, codigo, "IVA_CREDITO", nombre):
                        iva_credito_sin_mapeo.append(_descripcion_cuenta(codigo, nombre))
                    if ("DEBITO" in nombre_norm or "PAGAR" in nombre_norm) and not _cuenta_tiene_comportamiento(mapa, codigo, "IVA_DEBITO", nombre):
                        iva_debito_sin_mapeo.append(_descripcion_cuenta(codigo, nombre))
                if iva_credito_sin_mapeo:
                    resultados.append(
                        diagnostico(
                            "IVA",
                            SEVERIDAD_ADVERTENCIA,
                            "IVA_CUENTA_CREDITO_SIN_COMPORTAMIENTO",
                            "Hay cuentas de IVA crédito usadas sin uso operativo IVA crédito",
                            "Cuentas afectadas: " + "; ".join(sorted(set(iva_credito_sin_mapeo))[:15]) + ".",
                        )
                    )
                if iva_debito_sin_mapeo:
                    resultados.append(
                        diagnostico(
                            "IVA",
                            SEVERIDAD_ADVERTENCIA,
                            "IVA_CUENTA_DEBITO_SIN_COMPORTAMIENTO",
                            "Hay cuentas de IVA débito o IVA a pagar usadas sin uso operativo IVA débito",
                            "Cuentas afectadas: " + "; ".join(sorted(set(iva_debito_sin_mapeo))[:15]) + ".",
                        )
                    )

        if not resultados:
            resultados.append(
                diagnostico(
                    "Uso operativo del Plan de Cuentas",
                    SEVERIDAD_OK,
                    "COMPORTAMIENTOS_OPERATIVOS_OK",
                    "Uso operativo del Plan de Cuentas coherentes con las áreas operativas revisadas",
                    "Tesorería, IVA y Capital no presentan desvíos de uso operativo en la muestra analizada.",
                )
            )

        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()


def _es_imputable_valor(valor: Any, default: bool = True) -> bool:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return int(valor) != 0
    texto = str(valor).strip().upper()
    if texto in {"S", "SI", "SÍ", "1", "TRUE", "VERDADERO", "IMPUTABLE"}:
        return True
    if texto in {"N", "NO", "0", "FALSE", "FALSO", "NO_IMPUTABLE", "AGRUPADORA"}:
        return False
    return default


def _lista_resumida(items: list[str], limite: int = 15) -> str:
    unicos = []
    vistos = set()
    for item in items:
        texto = str(item or "").strip()
        if not texto or texto in vistos:
            continue
        vistos.add(texto)
        unicos.append(texto)

    if not unicos:
        return ""

    visibles = unicos[:limite]
    texto = "; ".join(visibles)
    restantes = len(unicos) - len(visibles)
    if restantes > 0:
        texto += f"; y {restantes} más"
    return texto


def _agregar_cuenta_lookup(
    lookup_codigo: dict[str, dict[str, Any]],
    lookup_nombre: dict[str, dict[str, Any]],
    codigo: Any,
    nombre: Any,
    imputable: Any = True,
    fuente: str = "",
) -> None:
    codigo_txt = _clave_cuenta(codigo)
    nombre_txt = str(nombre or "").strip()
    info = {
        "codigo": codigo_txt,
        "nombre": nombre_txt,
        "imputable": _es_imputable_valor(imputable, True),
        "fuente": fuente,
    }

    if codigo_txt:
        for clave in _claves_busqueda_cuenta(codigo_txt):
            lookup_codigo[clave] = info

    if nombre_txt:
        lookup_nombre[normalizar_codigo(nombre_txt)] = info


def _lookup_cuentas_contables(conn: sqlite3.Connection, empresa_id: int | None = None) -> dict[str, Any]:
    lookup_codigo: dict[str, dict[str, Any]] = {}
    lookup_nombre: dict[str, dict[str, Any]] = {}

    if _table_exists(conn, "plan_cuentas_empresa"):
        columnas = _columns(conn, "plan_cuentas_empresa")
        where = []
        params: list[Any] = []

        if empresa_id is not None and "empresa_id" in columnas:
            where.append("empresa_id = ?")
            params.append(empresa_id)

        if "estado" in columnas:
            where.append("COALESCE(estado, 'ACTIVA') NOT IN ('ANULADO', 'ANULADA', 'INACTIVO', 'INACTIVA', 'BAJA', 'ELIMINADO', 'ELIMINADA')")

        sql = "SELECT * FROM plan_cuentas_empresa"
        if where:
            sql += " WHERE " + " AND ".join(where)

        for row in _fetch_dicts(conn, sql, tuple(params)):
            _agregar_cuenta_lookup(
                lookup_codigo,
                lookup_nombre,
                row.get("codigo"),
                row.get("nombre"),
                row.get("imputable", 1),
                "plan_cuentas_empresa",
            )

    if _table_exists(conn, "plan_cuentas_detallado"):
        columnas = _columns(conn, "plan_cuentas_detallado")
        col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
        where = []
        params = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)

        sql = "SELECT * FROM plan_cuentas_detallado"
        if where:
            sql += " WHERE " + " AND ".join(where)

        for row in _fetch_dicts(conn, sql, tuple(params)):
            _agregar_cuenta_lookup(
                lookup_codigo,
                lookup_nombre,
                row.get("cuenta"),
                row.get("detalle"),
                row.get("imputable", "S"),
                "plan_cuentas_detallado",
            )

    if _table_exists(conn, "plan_cuentas"):
        columnas = _columns(conn, "plan_cuentas")
        col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
        where = []
        params = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)

        sql = "SELECT * FROM plan_cuentas"
        if where:
            sql += " WHERE " + " AND ".join(where)

        for row in _fetch_dicts(conn, sql, tuple(params)):
            _agregar_cuenta_lookup(
                lookup_codigo,
                lookup_nombre,
                row.get("codigo"),
                row.get("nombre"),
                row.get("imputable", 1),
                "plan_cuentas",
            )

    return {
        "por_codigo": lookup_codigo,
        "por_nombre": lookup_nombre,
    }


def _buscar_cuenta_lookup(mapa: dict[str, Any], codigo: Any, nombre: Any = None) -> dict[str, Any] | None:
    por_codigo: dict[str, dict[str, Any]] = mapa.get("por_codigo", {})
    for clave in _claves_busqueda_cuenta(codigo):
        if clave in por_codigo:
            return por_codigo[clave]

    nombre_txt = str(nombre or "").strip()
    if nombre_txt:
        return mapa.get("por_nombre", {}).get(normalizar_codigo(nombre_txt))

    return None


def diagnosticar_vinculacion_plan_maestro(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """
    Controla que las cuentas operativas de la empresa apunten al Plan Maestro FF.

    No modifica cuentas. Separa el diagnóstico para evitar ruido:
    - cuentas imputables heredadas o sin vínculo, que requieren saneamiento real;
    - cuentas agrupadoras heredadas, que son pendientes estructurales;
    - vínculos rotos, que sí son errores técnicos a corregir.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []

    try:
        if not _table_exists(conn, "plan_cuentas_empresa") or not _table_exists(conn, "plan_cuentas_maestro"):
            return []

        columnas_empresa = _columns(conn, "plan_cuentas_empresa")
        columnas_maestro = _columns(conn, "plan_cuentas_maestro")

        requeridas_empresa = {"codigo", "nombre", "cuenta_maestro_id"}
        requeridas_maestro = {"id", "codigo", "nombre"}

        if not requeridas_empresa.issubset(columnas_empresa) or not requeridas_maestro.issubset(columnas_maestro):
            return []

        where = []
        params: list[Any] = []

        if empresa_id is not None and "empresa_id" in columnas_empresa:
            where.append("e.empresa_id = ?")
            params.append(empresa_id)

        if "estado" in columnas_empresa:
            where.append("COALESCE(e.estado, 'ACTIVA') NOT IN ('ANULADO', 'ANULADA', 'INACTIVO', 'INACTIVA', 'BAJA', 'ELIMINADO', 'ELIMINADA')")

        imputable_expr = "e.imputable AS imputable" if "imputable" in columnas_empresa else "1 AS imputable"
        estado_expr = "e.estado AS estado" if "estado" in columnas_empresa else "'ACTIVA' AS estado"
        estado_maestro_codigo = "AND COALESCE(m_codigo.estado, 'ACTIVA') = 'ACTIVA'" if "estado" in columnas_maestro else ""

        sql = f"""
            SELECT
                e.id AS cuenta_empresa_id,
                e.codigo AS codigo_empresa,
                e.nombre AS nombre_empresa,
                e.cuenta_maestro_id,
                {imputable_expr},
                {estado_expr},
                m_id.id AS maestro_id_vinculado,
                m_id.codigo AS codigo_maestro_vinculado,
                m_id.nombre AS nombre_maestro_vinculado,
                m_codigo.id AS maestro_id_por_codigo,
                m_codigo.nombre AS nombre_maestro_por_codigo
            FROM plan_cuentas_empresa e
            LEFT JOIN plan_cuentas_maestro m_id
              ON m_id.id = e.cuenta_maestro_id
            LEFT JOIN plan_cuentas_maestro m_codigo
              ON m_codigo.codigo = e.codigo
             {estado_maestro_codigo}
        """
        if where:
            sql += " WHERE " + " AND ".join(where)

        filas = _fetch_dicts(conn, sql, tuple(params))

        vinculos_inconsistentes = []
        heredadas_imputables_mismo_codigo = []
        heredadas_agrupadoras_mismo_codigo = []
        imputables_sin_vinculo = []
        agrupadoras_sin_vinculo = []

        for row in filas:
            descripcion = _descripcion_cuenta(row.get("codigo_empresa"), row.get("nombre_empresa"))
            cuenta_maestro_id = row.get("cuenta_maestro_id")
            es_imputable = _es_imputable_valor(row.get("imputable"), default=True)

            if cuenta_maestro_id and not row.get("maestro_id_vinculado"):
                vinculos_inconsistentes.append(descripcion)
                continue

            if cuenta_maestro_id:
                continue

            if row.get("maestro_id_por_codigo"):
                detalle = f"{descripcion} coincide con {row.get('nombre_maestro_por_codigo')}"
                if es_imputable:
                    heredadas_imputables_mismo_codigo.append(detalle)
                else:
                    heredadas_agrupadoras_mismo_codigo.append(detalle)
                continue

            if es_imputable:
                imputables_sin_vinculo.append(descripcion)
            else:
                agrupadoras_sin_vinculo.append(descripcion)

        if vinculos_inconsistentes:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ERROR,
                    "PLAN_CUENTAS_EMPRESA_VINCULO_INCONSISTENTE",
                    "Hay cuentas vinculadas a una cuenta maestra inexistente",
                    "Cuentas afectadas: " + _lista_resumida(vinculos_inconsistentes) + ". Revise el vínculo desde Configuración → Plan de Cuentas.",
                    "plan_cuentas_empresa",
                )
            )

        if heredadas_imputables_mismo_codigo:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ADVERTENCIA,
                    "PLAN_CUENTAS_EMPRESA_IMPUTABLES_HEREDADAS_PENDIENTES",
                    "Hay cuentas imputables heredadas pendientes de vincular al Plan Maestro",
                    "Cuentas afectadas: "
                    + _lista_resumida(heredadas_imputables_mismo_codigo)
                    + ". Deben vincularse al Plan Maestro FF para dejar de operar como heredadas.",
                    "plan_cuentas_empresa",
                )
            )

        if heredadas_agrupadoras_mismo_codigo:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_INFO,
                    "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_HEREDADAS_PENDIENTES",
                    "Hay cuentas agrupadoras heredadas pendientes de ordenar",
                    "Cuentas afectadas: "
                    + _lista_resumida(heredadas_agrupadoras_mismo_codigo)
                    + ". No deberían recibir movimientos; quedan como pendiente estructural para vincular, inactivar o reemplazar sin romper historia.",
                    "plan_cuentas_empresa",
                )
            )

        if imputables_sin_vinculo:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ADVERTENCIA,
                    "PLAN_CUENTAS_EMPRESA_IMPUTABLES_SIN_VINCULO_MAESTRO",
                    "Hay cuentas imputables de empresa sin vínculo con el Plan Maestro",
                    "Cuentas afectadas: "
                    + _lista_resumida(imputables_sin_vinculo)
                    + ". Defina si corresponde vincularlas al Plan Maestro FF, convertirlas en cuentas específicas creadas desde una cuenta modelo o inactivarlas lógicamente con auditoría.",
                    "plan_cuentas_empresa",
                )
            )

        if agrupadoras_sin_vinculo:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_INFO,
                    "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_SIN_VINCULO_MAESTRO",
                    "Hay cuentas agrupadoras heredadas sin vínculo con el Plan Maestro",
                    "Cuentas afectadas: "
                    + _lista_resumida(agrupadoras_sin_vinculo)
                    + ". No son una urgencia operativa si no reciben movimientos, pero deben sanearse para cortar de raíz el ruido de cuentas heredadas.",
                    "plan_cuentas_empresa",
                )
            )

        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()

def diagnosticar_asientos_propuestos_plan_cuentas(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
    limite_revision: int = 5000,
) -> list[dict[str, Any]]:
    """
    Controla las cuentas usadas en la Bandeja de asientos propuestos.

    Esta validación es más confiable que revisar Libro Diario por código porque
    asientos_propuestos_detalle sí guarda cuenta_codigo y cuenta_nombre.
    """
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    resultados: list[DiagnosticoCoherencia] = []

    try:
        if not _table_exists(conn, "asientos_propuestos") or not _table_exists(conn, "asientos_propuestos_detalle"):
            return []

        mapa_cuentas = _lookup_cuentas_contables(conn, empresa_id=empresa_id)

        if not mapa_cuentas.get("por_codigo") and not mapa_cuentas.get("por_nombre"):
            return []

        columnas_asientos = _columns(conn, "asientos_propuestos")
        where = ["COALESCE(a.estado, '') NOT IN ('ANULADO', 'RECHAZADO', 'REVERTIDO')"]
        params: list[Any] = []

        if empresa_id is not None and "empresa_id" in columnas_asientos:
            where.append("a.empresa_id = ?")
            params.append(empresa_id)

        sql = """
            SELECT
                a.id AS asiento_propuesto_id,
                a.estado AS estado_asiento,
                d.id AS detalle_id,
                d.renglon,
                d.cuenta_codigo,
                d.cuenta_nombre
            FROM asientos_propuestos_detalle d
            JOIN asientos_propuestos a
              ON a.id = d.asiento_propuesto_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.id DESC, d.renglon ASC LIMIT ?"
        params.append(limite_revision)

        cuentas_no_reconocidas = []
        cuentas_no_imputables = []
        lineas_sin_codigo = []

        for row in _fetch_dicts(conn, sql, tuple(params)):
            codigo = row.get("cuenta_codigo")
            nombre = row.get("cuenta_nombre")
            descripcion = f"Propuesta {row.get('asiento_propuesto_id')} renglón {row.get('renglon')}: {_descripcion_cuenta(codigo, nombre)}"

            cuenta = _buscar_cuenta_lookup(mapa_cuentas, codigo, nombre)

            if not _clave_cuenta(codigo):
                lineas_sin_codigo.append(descripcion)
                if cuenta:
                    continue

            if not cuenta:
                cuentas_no_reconocidas.append(descripcion)
                continue

            if not cuenta.get("imputable", True):
                cuentas_no_imputables.append(descripcion)

        if cuentas_no_reconocidas:
            resultados.append(
                diagnostico(
                    "Bandeja de asientos",
                    SEVERIDAD_ERROR,
                    "ASIENTOS_PROPUESTOS_CUENTA_NO_RECONOCIDA",
                    "Hay propuestas contables con cuentas no reconocidas en el Plan de Cuentas",
                    "Revise: " + _lista_resumida(cuentas_no_reconocidas) + ". No conviene contabilizar propuestas con cuentas inexistentes o no vinculadas.",
                    "asientos_propuestos_detalle",
                )
            )

        if cuentas_no_imputables:
            resultados.append(
                diagnostico(
                    "Bandeja de asientos",
                    SEVERIDAD_ERROR,
                    "ASIENTOS_PROPUESTOS_CUENTA_NO_IMPUTABLE",
                    "Hay propuestas contables usando cuentas no imputables",
                    "Revise: " + _lista_resumida(cuentas_no_imputables) + ". Una cuenta agrupadora/no imputable no debería recibir movimientos.",
                    "asientos_propuestos_detalle",
                )
            )

        if lineas_sin_codigo:
            resultados.append(
                diagnostico(
                    "Bandeja de asientos",
                    SEVERIDAD_ADVERTENCIA,
                    "ASIENTOS_PROPUESTOS_LINEA_SIN_CODIGO_CUENTA",
                    "Hay líneas de propuestas sin código de cuenta",
                    "Revise: " + _lista_resumida(lineas_sin_codigo) + ". Para controles futuros de saldo normal y trazabilidad conviene que cada línea tenga código.",
                    "asientos_propuestos_detalle",
                )
            )

        return [item.as_dict() for item in resultados]
    finally:
        if propia:
            conn.close()

def diagnosticar_nucleo_coherencia(
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
    guardar: bool = False,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        aplicar_migracion_nucleo(conn)
        diagnosticos: list[dict[str, Any]] = []
        diagnosticos.extend(diagnosticar_ejercicios_contables(empresa_id=empresa_id, conn=conn))
        diagnosticos.extend(diagnosticar_plan_cuentas(empresa_id=empresa_id, conn=conn))
        diagnosticos.extend(diagnosticar_vinculacion_plan_maestro(empresa_id=empresa_id, conn=conn))
        diagnosticos.extend(diagnosticar_asientos_propuestos_plan_cuentas(empresa_id=empresa_id, conn=conn))
        diagnosticos.extend(diagnosticar_comportamientos_configurados(empresa_id=empresa_id, conn=conn))
        diagnosticos.extend(diagnosticar_inicio_contable_capital(empresa_id=empresa_id, conn=conn))
        diagnosticos.extend(diagnosticar_libro_diario(empresa_id=empresa_id, conn=conn))
        diagnosticos.sort(key=lambda item: (severidad_orden(item.get("severidad", "")), item.get("area", ""), item.get("codigo", "")))
        if guardar:
            guardar_diagnosticos(diagnosticos, empresa_id=empresa_id, conn=conn)
        if propia:
            conn.commit()
        return diagnosticos
    finally:
        if propia:
            conn.close()


def guardar_diagnosticos(
    diagnosticos: list[dict[str, Any]],
    empresa_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        aplicar_migracion_nucleo(conn)
        conn.execute(
            """
            UPDATE contabilidad_diagnosticos_coherencia
            SET resuelto = 1
            WHERE COALESCE(empresa_id, -1) = COALESCE(?, -1)
              AND resuelto = 0
            """,
            (empresa_id,),
        )
        fecha = _now_iso()
        for item in diagnosticos:
            conn.execute(
                """
                INSERT INTO contabilidad_diagnosticos_coherencia
                (empresa_id, fecha_diagnostico, area, severidad, codigo, titulo, detalle, referencia_tipo, referencia_id, resuelto)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    empresa_id,
                    fecha,
                    item.get("area"),
                    item.get("severidad"),
                    item.get("codigo"),
                    item.get("titulo"),
                    item.get("detalle"),
                    item.get("referencia_tipo"),
                    None if item.get("referencia_id") is None else str(item.get("referencia_id")),
                ),
            )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def resumen_diagnostico(diagnosticos: list[dict[str, Any]]) -> dict[str, int]:
    resumen = {
        SEVERIDAD_ERROR: 0,
        SEVERIDAD_ADVERTENCIA: 0,
        SEVERIDAD_INFO: 0,
        SEVERIDAD_OK: 0,
        "TOTAL": 0,
    }
    for item in diagnosticos:
        severidad = item.get("severidad")
        if severidad not in resumen:
            resumen[severidad] = 0
        resumen[severidad] += 1
        resumen["TOTAL"] += 1
    return resumen


def listar_comportamientos_contables() -> list[dict[str, Any]]:
    return [
        {
            "codigo": codigo,
            "nombre": datos["nombre"],
            "naturaleza": datos["naturaleza"],
            "descripcion": datos["descripcion"],
        }
        for codigo, datos in COMPORTAMIENTOS_CONTABLES.items()
    ]


def listar_origenes_economicos() -> list[dict[str, Any]]:
    return [
        {
            "codigo": codigo,
            "nombre": datos["nombre"],
            "modulo": datos["modulo"],
            "descripcion": datos["descripcion"],
        }
        for codigo, datos in ORIGENES_ECONOMICOS_OPERATIVOS.items()
    ]