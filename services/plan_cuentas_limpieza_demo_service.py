from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from database import conectar

CONFIRMACION_LIMPIEZA_DEMO = "LIMPIAR PLAN DEMO"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _fetch_dicts(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def _count_table(
    conn: sqlite3.Connection,
    table_name: str,
    where_sql: str = "",
    params: tuple[Any, ...] = (),
) -> int:
    if not _table_exists(conn, table_name):
        return 0
    sql = f"SELECT COUNT(*) FROM {table_name}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    return int(conn.execute(sql, params).fetchone()[0] or 0)


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def _registrar_auditoria(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    usuario: str,
    accion: str,
    entidad: str,
    entidad_id: str,
    valor_anterior: dict[str, Any],
    valor_nuevo: dict[str, Any],
    motivo: str,
) -> None:
    if not _table_exists(conn, "auditoria_cambios"):
        return

    columnas = _columns(conn, "auditoria_cambios")

    valores = {
        "fecha": _now_iso(),
        "usuario_id": None,
        "empresa_id": empresa_id,
        "modulo": "Plan de Cuentas",
        "accion": accion,
        "entidad": entidad,
        "entidad_id": entidad_id,
        "valor_anterior": _json_dump(valor_anterior),
        "valor_nuevo": _json_dump(valor_nuevo),
        "motivo": motivo,
    }

    campos = [campo for campo in valores if campo in columnas]
    placeholders = ", ".join("?" for _ in campos)

    conn.execute(
        f"""
        INSERT INTO auditoria_cambios ({", ".join(campos)})
        VALUES ({placeholders})
        """,
        tuple(valores[campo] for campo in campos),
    )


def _crear_backup_tabla_demo(
    conn: sqlite3.Connection,
    *,
    tabla: str,
    empresa_id: int,
    sufijo: str,
) -> str | None:
    if not _table_exists(conn, tabla):
        return None

    columnas = _columns(conn, tabla)
    backup = f"backup_demo_{tabla}_{sufijo}"

    if "empresa_id" in columnas:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {backup} AS
            SELECT *
            FROM {tabla}
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )
    else:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {backup} AS
            SELECT *
            FROM {tabla}
            """
        )

    return backup


def _crear_backups_demo(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
) -> list[str]:
    sufijo = datetime.now().strftime("%Y%m%d_%H%M%S")
    tablas = [
        "plan_cuentas_empresa",
        "mapeos_contables_empresa",
        "categorias_compra_config",
        "conceptos_fiscales_compra_config",
    ]

    backups: list[str] = []
    for tabla in tablas:
        backup = _crear_backup_tabla_demo(
            conn,
            tabla=tabla,
            empresa_id=empresa_id,
            sufijo=sufijo,
        )
        if backup:
            backups.append(backup)

    return backups


def _ids_plan_empresa_actual(conn: sqlite3.Connection, *, empresa_id: int) -> list[int]:
    if not _table_exists(conn, "plan_cuentas_empresa"):
        return []

    return [
        int(row["id"])
        for row in _fetch_dicts(
            conn,
            """
            SELECT id
            FROM plan_cuentas_empresa
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )
        if row.get("id") is not None
    ]


def _placeholders(ids: list[int]) -> str:
    return ", ".join("?" for _ in ids)



def _q(nombre: str) -> str:
    return '"' + str(nombre).replace('"', '""') + '"'


def _columna_notnull(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    for row in conn.execute(f"PRAGMA table_info({_q(table_name)})").fetchall():
        if str(row[1]) == str(column_name):
            return bool(int(row[3] or 0))
    return False


def _campos_auditoria_update(
    conn: sqlite3.Connection,
    *,
    tabla: str,
    usuario: str,
    motivo: str,
) -> tuple[str, list[Any]]:
    columnas = _columns(conn, tabla)
    sets: list[str] = []
    params: list[Any] = []
    ahora = _now_iso()

    if "motivo_estado" in columnas:
        sets.append(f"{_q('motivo_estado')} = ?")
        params.append(motivo)
    if "usuario_ultima_modificacion" in columnas:
        sets.append(f"{_q('usuario_ultima_modificacion')} = ?")
        params.append(usuario)
    if "fecha_ultima_modificacion" in columnas:
        sets.append(f"{_q('fecha_ultima_modificacion')} = ?")
        params.append(ahora)
    if "actualizado_en" in columnas:
        sets.append(f"{_q('actualizado_en')} = ?")
        params.append(ahora)

    if not sets:
        return "", []

    return ", " + ", ".join(sets), params


def _referencias_fk_hacia_plan_empresa(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    referencias: list[dict[str, Any]] = []

    tablas = [
        str(row["name"])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]

    for tabla in tablas:
        try:
            fks = conn.execute(f"PRAGMA foreign_key_list({_q(tabla)})").fetchall()
        except Exception:
            continue

        for fk in fks:
            item = dict(fk)
            tabla_padre = str(item.get("table") or "")
            if tabla_padre != "plan_cuentas_empresa":
                continue

            referencias.append(
                {
                    "tabla": tabla,
                    "columna": str(item.get("from") or ""),
                    "tabla_padre": tabla_padre,
                    "columna_padre": str(item.get("to") or "id"),
                    "on_delete": str(item.get("on_delete") or "NO ACTION"),
                }
            )

    return referencias


def _limpiar_referencias_fk_genericas(
    conn: sqlite3.Connection,
    *,
    cuenta_ids: list[int],
    usuario: str,
    motivo: str,
) -> dict[str, Any]:
    resumen = {
        "referencias_fk_genericas_limpiadas": 0,
        "referencias_fk_genericas_detalle": [],
    }

    if not cuenta_ids:
        return resumen

    ph = _placeholders(cuenta_ids)

    tablas_delete_seguras = {
        "mapeos_contables_empresa",
        "contabilidad_cuentas_comportamiento",
    }

    for ref in _referencias_fk_hacia_plan_empresa(conn):
        tabla = ref["tabla"]
        columna = ref["columna"]

        if not tabla or not columna:
            continue

        if not _table_exists(conn, tabla):
            continue

        columnas = _columns(conn, tabla)
        if columna not in columnas:
            continue

        cantidad = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {_q(tabla)}
                WHERE {_q(columna)} IN ({ph})
                """,
                tuple(cuenta_ids),
            ).fetchone()[0] or 0
        )

        if cantidad <= 0:
            continue

        if tabla == "plan_cuentas_empresa":
            if not _columna_notnull(conn, tabla, columna):
                cur = conn.execute(
                    f"""
                    UPDATE {_q(tabla)}
                       SET {_q(columna)} = NULL
                     WHERE {_q(columna)} IN ({ph})
                    """,
                    tuple(cuenta_ids),
                )
                afectadas = int(cur.rowcount or 0)
            else:
                afectadas = 0

        elif tabla in tablas_delete_seguras:
            cur = conn.execute(
                f"""
                DELETE FROM {_q(tabla)}
                WHERE {_q(columna)} IN ({ph})
                """,
                tuple(cuenta_ids),
            )
            afectadas = int(cur.rowcount or 0)

        elif not _columna_notnull(conn, tabla, columna):
            extra_sql, extra_params = _campos_auditoria_update(
                conn,
                tabla=tabla,
                usuario=usuario,
                motivo=motivo,
            )
            cur = conn.execute(
                f"""
                UPDATE {_q(tabla)}
                   SET {_q(columna)} = NULL
                       {extra_sql}
                 WHERE {_q(columna)} IN ({ph})
                """,
                (*extra_params, *cuenta_ids),
            )
            afectadas = int(cur.rowcount or 0)

        else:
            raise RuntimeError(
                "La limpieza demo no puede borrar el Plan de Cuentas porque existe "
                f"una referencia obligatoria desde {tabla}.{columna}. "
                "Debe definirse una regla explícita para limpiar esa tabla antes de eliminar cuentas."
            )

        resumen["referencias_fk_genericas_limpiadas"] += afectadas
        resumen["referencias_fk_genericas_detalle"].append(
            {
                "tabla": tabla,
                "columna": columna,
                "filas_detectadas": cantidad,
                "filas_limpiadas": afectadas,
            }
        )

    return resumen


def _limpiar_referencias_dependientes(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    cuenta_ids: list[int],
    usuario: str,
    motivo: str,
) -> dict[str, Any]:
    resumen = {
        "mapeos_eliminados": 0,
        "categorias_cuenta_sugerida_limpiadas": 0,
        "categorias_contrapartida_limpiadas": 0,
        "conceptos_fiscales_limpiados": 0,
        "referencias_fk_genericas_limpiadas": 0,
        "referencias_fk_genericas_detalle": [],
    }

    if not cuenta_ids:
        return resumen

    ph = _placeholders(cuenta_ids)

    if _table_exists(conn, "mapeos_contables_empresa"):
        columnas = _columns(conn, "mapeos_contables_empresa")
        if "cuenta_empresa_id" in columnas:
            cur = conn.execute(
                f"""
                DELETE FROM mapeos_contables_empresa
                WHERE cuenta_empresa_id IN ({ph})
                """,
                tuple(cuenta_ids),
            )
            resumen["mapeos_eliminados"] = int(cur.rowcount or 0)

    if _table_exists(conn, "categorias_compra_config"):
        columnas = _columns(conn, "categorias_compra_config")
        extra_sql, extra_params = _campos_auditoria_update(
            conn,
            tabla="categorias_compra_config",
            usuario=usuario,
            motivo=motivo,
        )

        if "cuenta_sugerida_id" in columnas:
            cur = conn.execute(
                f"""
                UPDATE categorias_compra_config
                   SET cuenta_sugerida_id = NULL
                       {extra_sql}
                 WHERE cuenta_sugerida_id IN ({ph})
                """,
                (*extra_params, *cuenta_ids),
            )
            resumen["categorias_cuenta_sugerida_limpiadas"] = int(cur.rowcount or 0)

        if "cuenta_contrapartida_sugerida_id" in columnas:
            cur = conn.execute(
                f"""
                UPDATE categorias_compra_config
                   SET cuenta_contrapartida_sugerida_id = NULL
                       {extra_sql}
                 WHERE cuenta_contrapartida_sugerida_id IN ({ph})
                """,
                (*extra_params, *cuenta_ids),
            )
            resumen["categorias_contrapartida_limpiadas"] = int(cur.rowcount or 0)

    if _table_exists(conn, "conceptos_fiscales_compra_config"):
        columnas = _columns(conn, "conceptos_fiscales_compra_config")
        extra_sql, extra_params = _campos_auditoria_update(
            conn,
            tabla="conceptos_fiscales_compra_config",
            usuario=usuario,
            motivo=motivo,
        )

        if "cuenta_sugerida_id" in columnas:
            cur = conn.execute(
                f"""
                UPDATE conceptos_fiscales_compra_config
                   SET cuenta_sugerida_id = NULL
                       {extra_sql}
                 WHERE cuenta_sugerida_id IN ({ph})
                """,
                (*extra_params, *cuenta_ids),
            )
            resumen["conceptos_fiscales_limpiados"] = int(cur.rowcount or 0)

    genericas = _limpiar_referencias_fk_genericas(
        conn,
        cuenta_ids=cuenta_ids,
        usuario=usuario,
        motivo=motivo,
    )

    resumen["referencias_fk_genericas_limpiadas"] = int(
        genericas.get("referencias_fk_genericas_limpiadas", 0) or 0
    )
    resumen["referencias_fk_genericas_detalle"] = genericas.get(
        "referencias_fk_genericas_detalle",
        [],
    )

    return resumen


def _cuentas_maestro_activas(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "plan_cuentas_maestro"):
        return []

    columnas = _columns(conn, "plan_cuentas_maestro")
    estado_sql = "WHERE COALESCE(estado, 'ACTIVA') = 'ACTIVA'" if "estado" in columnas else ""

    return _fetch_dicts(
        conn,
        f"""
        SELECT *
        FROM plan_cuentas_maestro
        {estado_sql}
        ORDER BY orden, codigo
        """,
    )


def _reconstruir_plan_empresa_desde_maestro(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    usuario: str,
    motivo: str,
) -> int:
    if not _table_exists(conn, "plan_cuentas_empresa"):
        raise RuntimeError("No existe la tabla plan_cuentas_empresa.")

    if not _table_exists(conn, "plan_cuentas_maestro"):
        raise RuntimeError("No existe la tabla plan_cuentas_maestro.")

    columnas_empresa = _columns(conn, "plan_cuentas_empresa")
    cuentas_maestro = _cuentas_maestro_activas(conn)

    if not cuentas_maestro:
        raise RuntimeError("No hay cuentas activas en plan_cuentas_maestro para reconstruir el plan demo.")

    insertadas = 0
    ahora = _now_iso()

    campos_posibles = [
        "empresa_id",
        "cuenta_maestro_id",
        "codigo",
        "nombre",
        "codigo_madre",
        "nivel",
        "orden",
        "imputable",
        "requiere_auxiliar",
        "tipo_auxiliar",
        "ajustable",
        "estado",
        "es_cuenta_modelo",
        "es_cuenta_especifica_empresa",
        "cuenta_modelo_origen_id",
        "banco_nombre",
        "numero_cuenta",
        "moneda",
        "alias",
        "cbu",
        "uso_operativo_sistema",
        "vigencia_desde",
        "vigencia_hasta",
        "motivo_estado",
        "usuario_ultima_modificacion",
        "fecha_ultima_modificacion",
        "actualizado_en",
    ]

    campos_insert = [campo for campo in campos_posibles if campo in columnas_empresa]

    for cuenta in cuentas_maestro:
        valores = {
            "empresa_id": empresa_id,
            "cuenta_maestro_id": cuenta.get("id"),
            "codigo": cuenta.get("codigo"),
            "nombre": cuenta.get("nombre"),
            "codigo_madre": cuenta.get("codigo_madre"),
            "nivel": cuenta.get("nivel", 1),
            "orden": cuenta.get("orden", 0),
            "imputable": cuenta.get("imputable", 0),
            "requiere_auxiliar": cuenta.get("requiere_auxiliar", 0),
            "tipo_auxiliar": cuenta.get("tipo_auxiliar"),
            "ajustable": cuenta.get("ajustable", 0),
            "estado": "ACTIVA",
            "es_cuenta_modelo": cuenta.get("es_cuenta_modelo", 0),
            "es_cuenta_especifica_empresa": 0,
            "cuenta_modelo_origen_id": None,
            "banco_nombre": None,
            "numero_cuenta": None,
            "moneda": None,
            "alias": None,
            "cbu": None,
            "uso_operativo_sistema": cuenta.get("uso_operativo_sistema"),
            "vigencia_desde": cuenta.get("vigencia_desde"),
            "vigencia_hasta": cuenta.get("vigencia_hasta"),
            "motivo_estado": motivo,
            "usuario_ultima_modificacion": usuario,
            "fecha_ultima_modificacion": ahora,
            "actualizado_en": ahora,
        }

        placeholders = ", ".join("?" for _ in campos_insert)

        conn.execute(
            f"""
            INSERT INTO plan_cuentas_empresa ({", ".join(campos_insert)})
            VALUES ({placeholders})
            """,
            tuple(valores[campo] for campo in campos_insert),
        )
        insertadas += 1

    return insertadas


def previsualizar_limpieza_plan_cuentas_demo(
    *,
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    cerrar = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)

    try:
        total_empresa = _count_table(conn, "plan_cuentas_empresa", "empresa_id = ?", (empresa_id,))
        total_maestro = _count_table(
            conn,
            "plan_cuentas_maestro",
            "COALESCE(estado, 'ACTIVA') = 'ACTIVA'",
        )

        cuentas_no_vinculadas = 0
        cuentas_vinculadas = 0
        cuentas_especificas = 0

        if _table_exists(conn, "plan_cuentas_empresa"):
            columnas = _columns(conn, "plan_cuentas_empresa")
            if "cuenta_maestro_id" in columnas:
                cuentas_no_vinculadas = _count_table(
                    conn,
                    "plan_cuentas_empresa",
                    "empresa_id = ? AND cuenta_maestro_id IS NULL",
                    (empresa_id,),
                )
                cuentas_vinculadas = _count_table(
                    conn,
                    "plan_cuentas_empresa",
                    "empresa_id = ? AND cuenta_maestro_id IS NOT NULL",
                    (empresa_id,),
                )
            if "es_cuenta_especifica_empresa" in columnas:
                cuentas_especificas = _count_table(
                    conn,
                    "plan_cuentas_empresa",
                    "empresa_id = ? AND COALESCE(es_cuenta_especifica_empresa, 0) = 1",
                    (empresa_id,),
                )

        return {
            "ok": True,
            "empresa_id": empresa_id,
            "total_plan_empresa_actual": total_empresa,
            "total_plan_maestro_activo": total_maestro,
            "cuentas_vinculadas_al_maestro": cuentas_vinculadas,
            "cuentas_no_vinculadas": cuentas_no_vinculadas,
            "cuentas_especificas_empresa": cuentas_especificas,
            "accion_demo": (
                "La limpieza demo eliminará el plan de empresa actual y lo reconstruirá "
                "desde el Plan Maestro FF activo."
            ),
            "confirmacion_requerida": CONFIRMACION_LIMPIEZA_DEMO,
        }
    finally:
        if cerrar:
            conn.close()


def limpiar_plan_cuentas_demo_desde_maestro(
    *,
    empresa_id: int = 1,
    confirmacion: str,
    usuario: str = "sistema",
    motivo: str = "Limpieza radical demo: reconstrucción desde Plan Maestro FF",
    crear_backup: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if confirmacion != CONFIRMACION_LIMPIEZA_DEMO:
        raise ValueError(
            f"Confirmación inválida. Para ejecutar esta limpieza demo debe escribir: "
            f"{CONFIRMACION_LIMPIEZA_DEMO!r}."
        )

    motivo_limpio = str(motivo or "").strip()
    if not motivo_limpio:
        raise ValueError("El motivo es obligatorio para limpiar el Plan de Cuentas demo.")

    cerrar = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)

    try:
        conn.execute("PRAGMA foreign_keys = ON")

        preview_antes = previsualizar_limpieza_plan_cuentas_demo(
            empresa_id=empresa_id,
            conn=conn,
        )

        cuenta_ids = _ids_plan_empresa_actual(conn, empresa_id=empresa_id)
        cuentas_antes = len(cuenta_ids)

        backups = _crear_backups_demo(conn, empresa_id=empresa_id) if crear_backup else []

        referencias = _limpiar_referencias_dependientes(
            conn,
            empresa_id=empresa_id,
            cuenta_ids=cuenta_ids,
            usuario=usuario,
            motivo=motivo_limpio,
        )

        cuentas_eliminadas = 0
        if _table_exists(conn, "plan_cuentas_empresa"):
            cur = conn.execute(
                """
                DELETE FROM plan_cuentas_empresa
                WHERE empresa_id = ?
                """,
                (empresa_id,),
            )
            cuentas_eliminadas = int(cur.rowcount or 0)

        cuentas_reconstruidas = _reconstruir_plan_empresa_desde_maestro(
            conn,
            empresa_id=empresa_id,
            usuario=usuario,
            motivo=motivo_limpio,
        )

        preview_despues = previsualizar_limpieza_plan_cuentas_demo(
            empresa_id=empresa_id,
            conn=conn,
        )

        resultado = {
            "ok": True,
            "empresa_id": empresa_id,
            "modo": "DEMO_RADICAL",
            "backups": backups,
            "cuentas_antes": cuentas_antes,
            "cuentas_eliminadas": cuentas_eliminadas,
            "cuentas_reconstruidas": cuentas_reconstruidas,
            **referencias,
            "preview_antes": preview_antes,
            "preview_despues": preview_despues,
            "motivo": motivo_limpio,
        }

        _registrar_auditoria(
            conn,
            empresa_id=empresa_id,
            usuario=usuario,
            accion="LIMPIEZA_DEMO_PLAN_CUENTAS",
            entidad="plan_cuentas_empresa",
            entidad_id=str(empresa_id),
            valor_anterior=preview_antes,
            valor_nuevo=resultado,
            motivo=motivo_limpio,
        )

        conn.commit()
        return resultado

    except Exception:
        conn.rollback()
        raise
    finally:
        if cerrar:
            conn.close()