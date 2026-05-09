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
                    "El núcleo de coherencia necesita un plan de cuentas para mapear comportamientos contables.",
                ).as_dict()
            ]

        aplicar_migracion_nucleo(conn)

        columnas = _columns(conn, "plan_cuentas")
        col_id = _first_existing(columnas, ("id", "cuenta_id")) or "rowid"
        col_empresa = _first_existing(columnas, ("empresa_id", "id_empresa"))
        col_codigo = _first_existing(columnas, ("codigo", "codigo_cuenta", "cuenta_codigo"))
        col_nombre = _first_existing(columnas, ("nombre", "nombre_cuenta", "descripcion"))
        col_comportamiento = _first_existing(columnas, ("comportamiento_contable", "comportamiento", "tipo_operativo"))
        col_imputable = _first_existing(columnas, ("imputable", "recibe_movimientos", "permite_imputacion", "permite_imputacion_operativa"))

        where = []
        params: list[Any] = []
        if empresa_id is not None and col_empresa:
            where.append(f"{col_empresa} = ?")
            params.append(empresa_id)
        sql = "SELECT rowid AS __rowid__, * FROM plan_cuentas"
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = _fetch_dicts(conn, sql, tuple(params))

        comportamientos_detectados: set[str] = set()
        cuentas_imputables_sin_comportamiento = 0
        cuentas_con_comportamiento_invalido: list[str] = []

        for row in rows:
            row_id = row.get(col_id) if col_id != "rowid" else row.get("__rowid__")
            codigo = row.get(col_codigo, row_id) if col_codigo else row_id
            nombre = row.get(col_nombre, "") if col_nombre else ""
            comportamientos = _comportamientos_desde_plan(row, col_comportamiento)
            for comportamiento in comportamientos:
                if comportamiento in COMPORTAMIENTOS_CONTABLES:
                    comportamientos_detectados.add(comportamiento)
                else:
                    cuentas_con_comportamiento_invalido.append(f"{codigo} {nombre}".strip())

            imputable = True
            if col_imputable:
                valor_imputable = row.get(col_imputable)
                imputable = valor_imputable not in (0, "0", "NO", "No", "no", False)
            if imputable and not comportamientos:
                cuentas_imputables_sin_comportamiento += 1

        if _table_exists(conn, "contabilidad_cuentas_comportamiento"):
            columnas_map = _columns(conn, "contabilidad_cuentas_comportamiento")
            where_map = ["activo = 1"]
            params_map: list[Any] = []
            if empresa_id is not None and "empresa_id" in columnas_map:
                where_map.append("(empresa_id = ? OR empresa_id IS NULL)")
                params_map.append(empresa_id)
            sql_map = "SELECT comportamiento FROM contabilidad_cuentas_comportamiento WHERE " + " AND ".join(where_map)
            for row in _fetch_dicts(conn, sql_map, tuple(params_map)):
                comportamiento = normalizar_codigo(row.get("comportamiento"))
                if comportamiento in COMPORTAMIENTOS_CONTABLES:
                    comportamientos_detectados.add(comportamiento)

        faltantes = [codigo for codigo in COMPORTAMIENTOS_CRITICOS if codigo not in comportamientos_detectados]
        if faltantes:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ADVERTENCIA,
                    "PLAN_COMPORTAMIENTOS_CRITICOS_FALTANTES",
                    "Faltan comportamientos contables críticos",
                    "No se detectó mapeo para: " + ", ".join(faltantes) + ".",
                )
            )

        if cuentas_imputables_sin_comportamiento:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_INFO,
                    "PLAN_CUENTAS_SIN_COMPORTAMIENTO",
                    "Hay cuentas imputables sin comportamiento operativo",
                    f"Se detectaron {cuentas_imputables_sin_comportamiento} cuentas imputables sin clasificación de comportamiento contable.",
                )
            )

        if cuentas_con_comportamiento_invalido:
            ejemplos = "; ".join(cuentas_con_comportamiento_invalido[:10])
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_ERROR,
                    "PLAN_COMPORTAMIENTO_INVALIDO",
                    "Hay cuentas con comportamiento contable no reconocido",
                    f"Ejemplos: {ejemplos}.",
                )
            )

        if not resultados:
            resultados.append(
                diagnostico(
                    "Plan de cuentas",
                    SEVERIDAD_OK,
                    "PLAN_CUENTAS_OK",
                    "Plan de cuentas con comportamientos mínimos cubiertos",
                    "Se detectaron los comportamientos críticos necesarios para la coherencia operativa.",
                )
            )
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