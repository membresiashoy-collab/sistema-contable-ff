import pandas as pd

from database import conectar, backup_base_datos


# ======================================================
# UTILIDADES INTERNAS
# ======================================================

def _texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _texto_upper(valor):
    return _texto(valor).upper()


def _confirmacion_valida(texto, esperado):
    return _texto_upper(texto) == _texto_upper(esperado)


def _tabla_existe(conn, tabla):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (tabla,),
    )
    return cur.fetchone() is not None


def _columnas_tabla(conn, tabla):
    if not _tabla_existe(conn, tabla):
        return []

    df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)
    return df["name"].tolist()


def _tiene_columna(conn, tabla, columna):
    return columna in _columnas_tabla(conn, tabla)


def _where_empresa(conn, tabla, empresa_id):
    if _tiene_columna(conn, tabla, "empresa_id"):
        return "empresa_id = ?", [empresa_id]
    return "1 = 1", []


def _contar(conn, tabla, where_sql="1 = 1", params=None):
    params = params or []

    if not _tabla_existe(conn, tabla):
        return 0

    df = pd.read_sql_query(
        f"SELECT COUNT(*) AS cantidad FROM {tabla} WHERE {where_sql}",
        conn,
        params=tuple(params),
    )

    if df.empty:
        return 0

    return int(df.iloc[0]["cantidad"] or 0)


def _delete(cur, tabla, where_sql="1 = 1", params=None):
    params = params or []

    if not _tabla_existe(cur.connection, tabla):
        return 0

    cur.execute(
        f"DELETE FROM {tabla} WHERE {where_sql}",
        tuple(params),
    )

    return int(cur.rowcount or 0)


def _ids(conn, tabla, where_sql="1 = 1", params=None):
    params = params or []

    if not _tabla_existe(conn, tabla):
        return []

    if "id" not in _columnas_tabla(conn, tabla):
        return []

    df = pd.read_sql_query(
        f"SELECT id FROM {tabla} WHERE {where_sql}",
        conn,
        params=tuple(params),
    )

    if df.empty:
        return []

    return [int(x) for x in df["id"].dropna().tolist()]


def _in_clause(valores):
    valores = [v for v in valores if v is not None]

    if not valores:
        return "IN (NULL)", []

    return f"IN ({', '.join(['?'] * len(valores))})", valores


def _resultado_base(accion):
    return {
        "ok": True,
        "accion": accion,
        "mensaje": "",
        "backup": "",
        "filas_borradas": 0,
        "detalle": [],
    }


def _sumar_resultado(resultado, tabla, cantidad):
    cantidad = int(cantidad or 0)

    resultado["detalle"].append(
        {
            "tabla": tabla,
            "filas_borradas": cantidad,
        }
    )

    resultado["filas_borradas"] += cantidad


def _crear_backup(motivo):
    return backup_base_datos(motivo) or ""


def _obtener_campo_ids(conn, tabla, campo, ids):
    if not ids:
        return []

    if not _tabla_existe(conn, tabla):
        return []

    if not _tiene_columna(conn, tabla, campo):
        return []

    in_sql, in_params = _in_clause([int(x) for x in ids])

    df = pd.read_sql_query(
        f"""
        SELECT {campo}
        FROM {tabla}
        WHERE id {in_sql}
          AND {campo} IS NOT NULL
        """,
        conn,
        params=tuple(in_params),
    )

    if df.empty:
        return []

    return df[campo].dropna().tolist()


def _obtener_tesoreria_ids(conn, tabla, ids):
    valores = _obtener_campo_ids(conn, tabla, "tesoreria_operacion_id", ids)
    return [int(x) for x in valores if x is not None]


def _obtener_referencias(conn, tabla, campo, ids):
    valores = _obtener_campo_ids(conn, tabla, campo, ids)
    return [_texto(x) for x in valores if _texto(x)]


def _borrar_si_existe(cur, resultado, tabla, where_sql="1 = 1", params=None):
    if not _tabla_existe(cur.connection, tabla):
        return

    _sumar_resultado(
        resultado,
        tabla,
        _delete(cur, tabla, where_sql, params or []),
    )


# ======================================================
# DEPENDENCIAS DE TESORERÍA / BANCO / CAJA
# ======================================================

def _obtener_conciliacion_ids_por_tesoreria(conn, tesoreria_ids):
    if not tesoreria_ids:
        return []

    if not _tabla_existe(conn, "bancos_conciliaciones_detalle"):
        return []

    in_sql, in_params = _in_clause([int(x) for x in tesoreria_ids])

    df = pd.read_sql_query(
        f"""
        SELECT conciliacion_id
        FROM bancos_conciliaciones_detalle
        WHERE entidad_tabla = 'tesoreria_operaciones'
          AND entidad_id {in_sql}
        """,
        conn,
        params=tuple(in_params),
    )

    if df.empty:
        return []

    return [int(x) for x in df["conciliacion_id"].dropna().unique().tolist()]


def _borrar_conciliaciones_por_ids(cur, resultado, conciliacion_ids):
    conciliacion_ids = [int(x) for x in conciliacion_ids if x is not None]

    if not conciliacion_ids:
        return

    in_sql, in_params = _in_clause(conciliacion_ids)

    _borrar_si_existe(
        cur,
        resultado,
        "bancos_conciliaciones_detalle",
        f"conciliacion_id {in_sql}",
        in_params,
    )

    _borrar_si_existe(
        cur,
        resultado,
        "bancos_conciliaciones",
        f"id {in_sql}",
        in_params,
    )


def _borrar_tesoreria_por_ids(cur, resultado, tesoreria_ids):
    tesoreria_ids = [int(x) for x in tesoreria_ids if x is not None]

    if not tesoreria_ids:
        return

    in_sql, in_params = _in_clause(tesoreria_ids)

    _borrar_si_existe(
        cur,
        resultado,
        "tesoreria_operaciones_componentes",
        f"operacion_id {in_sql}",
        in_params,
    )

    _borrar_si_existe(
        cur,
        resultado,
        "tesoreria_auditoria",
        f"entidad = 'tesoreria_operaciones' AND entidad_id {in_sql}",
        [str(x) for x in tesoreria_ids],
    )

    _borrar_si_existe(
        cur,
        resultado,
        "tesoreria_operaciones_vinculos",
        f"operacion_origen_id {in_sql}",
        in_params,
    )

    _borrar_si_existe(
        cur,
        resultado,
        "tesoreria_operaciones_vinculos",
        f"operacion_destino_id {in_sql}",
        in_params,
    )

    _borrar_si_existe(
        cur,
        resultado,
        "tesoreria_operaciones",
        f"id {in_sql}",
        in_params,
    )


def _obtener_caja_movimiento_ids(conn, empresa_id, tipos=None, referencias=None, tesoreria_ids=None):
    if not _tabla_existe(conn, "caja_movimientos"):
        return []

    filtros_base = []
    params_base = []

    if _tiene_columna(conn, "caja_movimientos", "empresa_id"):
        filtros_base.append("empresa_id = ?")
        params_base.append(int(empresa_id))

    filtros_or = []
    params_or = []

    tipos = [_texto(x) for x in (tipos or []) if _texto(x)]
    referencias = [_texto(x) for x in (referencias or []) if _texto(x)]
    tesoreria_ids = [int(x) for x in (tesoreria_ids or []) if x is not None]

    if tipos and _tiene_columna(conn, "caja_movimientos", "tipo_movimiento"):
        in_sql, in_params = _in_clause(tipos)
        filtros_or.append(f"tipo_movimiento {in_sql}")
        params_or.extend(in_params)

    if referencias and _tiene_columna(conn, "caja_movimientos", "referencia"):
        in_sql, in_params = _in_clause(referencias)
        filtros_or.append(f"referencia {in_sql}")
        params_or.extend(in_params)

    if tesoreria_ids and _tiene_columna(conn, "caja_movimientos", "tesoreria_operacion_id"):
        in_sql, in_params = _in_clause(tesoreria_ids)
        filtros_or.append(f"tesoreria_operacion_id {in_sql}")
        params_or.extend(in_params)

    if not filtros_or:
        return []

    where_partes = filtros_base + ["(" + " OR ".join(filtros_or) + ")"]
    where_sql = " AND ".join(where_partes)

    df = pd.read_sql_query(
        f"""
        SELECT id
        FROM caja_movimientos
        WHERE {where_sql}
        """,
        conn,
        params=tuple(params_base + params_or),
    )

    if df.empty:
        return []

    return [int(x) for x in df["id"].dropna().tolist()]


def _borrar_caja_movimientos_por_ids(cur, resultado, movimiento_ids):
    movimiento_ids = [int(x) for x in movimiento_ids if x is not None]

    if not movimiento_ids:
        return

    in_sql, in_params = _in_clause(movimiento_ids)

    _borrar_si_existe(
        cur,
        resultado,
        "caja_asientos",
        f"movimiento_caja_id {in_sql}",
        in_params,
    )

    _borrar_si_existe(
        cur,
        resultado,
        "caja_arqueos",
        f"movimiento_ajuste_id {in_sql}",
        in_params,
    )

    _borrar_si_existe(
        cur,
        resultado,
        "caja_auditoria",
        f"entidad = 'caja_movimientos' AND entidad_id {in_sql}",
        [str(x) for x in movimiento_ids],
    )

    _borrar_si_existe(
        cur,
        resultado,
        "caja_movimientos",
        f"id {in_sql}",
        in_params,
    )


# ======================================================
# DOCUMENTOS DE TESORERÍA OPCIONALES
# ======================================================

def _borrar_documentos_tesoreria(cur, resultado, origen_tabla, origen_ids, numeros):
    """
    Soporta futuras tablas físicas de documentos si existen.
    Hoy Recibos/OP se leen principalmente desde cobranzas/pagos,
    pero esta limpieza queda preparada para una tabla documental real.
    """

    tablas_posibles = [
        "documentos_tesoreria",
        "tesoreria_documentos",
        "documentos_emitidos",
    ]

    origen_ids = [int(x) for x in origen_ids if x is not None]
    numeros = [_texto(x) for x in numeros if _texto(x)]

    for tabla in tablas_posibles:
        conn = cur.connection

        if not _tabla_existe(conn, tabla):
            continue

        columnas = _columnas_tabla(conn, tabla)
        filtros = []
        params = []

        if "origen_tabla" in columnas and "origen_id" in columnas and origen_ids:
            in_sql, in_params = _in_clause(origen_ids)
            filtros.append(f"(origen_tabla = ? AND origen_id {in_sql})")
            params.append(origen_tabla)
            params.extend(in_params)

        if "numero" in columnas and numeros:
            in_sql, in_params = _in_clause(numeros)
            filtros.append(f"numero {in_sql}")
            params.extend(in_params)

        if "numero_documento" in columnas and numeros:
            in_sql, in_params = _in_clause(numeros)
            filtros.append(f"numero_documento {in_sql}")
            params.extend(in_params)

        if "numero_recibo" in columnas and numeros:
            in_sql, in_params = _in_clause(numeros)
            filtros.append(f"numero_recibo {in_sql}")
            params.extend(in_params)

        if "numero_orden_pago" in columnas and numeros:
            in_sql, in_params = _in_clause(numeros)
            filtros.append(f"numero_orden_pago {in_sql}")
            params.extend(in_params)

        if not filtros:
            continue

        _borrar_si_existe(
            cur,
            resultado,
            tabla,
            " OR ".join(filtros),
            params,
        )


# ======================================================
# DIAGNÓSTICO
# ======================================================

def diagnosticar_datos_demo(empresa_id=1):
    empresa_id = int(empresa_id or 1)

    tablas = [
        "historial_cargas",
        "ventas_comprobantes",
        "compras_comprobantes",
        "cuenta_corriente_clientes",
        "cuenta_corriente_proveedores",
        "cobranzas",
        "cobranzas_imputaciones",
        "cobranzas_retenciones",
        "pagos",
        "pagos_imputaciones",
        "pagos_retenciones",
        "tesoreria_operaciones",
        "tesoreria_operaciones_componentes",
        "tesoreria_operaciones_vinculos",
        "libro_diario",
        "bancos_movimientos",
        "bancos_conciliaciones",
        "bancos_conciliaciones_detalle",
        "caja_movimientos",
        "caja_asientos",
        "caja_arqueos",
        "caja_auditoria",
        "documentos_tesoreria",
        "tesoreria_documentos",
        "documentos_emitidos",
    ]

    conn = conectar()

    try:
        filas = []

        for tabla in tablas:
            existe = _tabla_existe(conn, tabla)

            if not existe:
                filas.append(
                    {
                        "tabla": tabla,
                        "existe": False,
                        "registros": 0,
                    }
                )
                continue

            where_sql, params = _where_empresa(conn, tabla, empresa_id)

            filas.append(
                {
                    "tabla": tabla,
                    "existe": True,
                    "registros": _contar(conn, tabla, where_sql, params),
                }
            )

        return pd.DataFrame(filas)

    finally:
        conn.close()


# ======================================================
# LIMPIEZA LIBRO DIARIO
# ======================================================

def limpiar_libro_diario_admin(empresa_id=1, confirmar_texto=""):
    empresa_id = int(empresa_id or 1)

    if not _confirmacion_valida(confirmar_texto, "LIMPIAR DIARIO"):
        return {
            "ok": False,
            "mensaje": "Confirmación inválida. Escribí LIMPIAR DIARIO.",
            "backup": "",
            "filas_borradas": 0,
            "detalle": [],
        }

    resultado = _resultado_base("limpiar_libro_diario")
    resultado["backup"] = _crear_backup("antes_limpiar_libro_diario")

    conn = conectar()
    cur = conn.cursor()

    try:
        where_sql, params = _where_empresa(conn, "libro_diario", empresa_id)

        _borrar_si_existe(
            cur,
            resultado,
            "libro_diario",
            where_sql,
            params,
        )

        conn.commit()

        resultado["mensaje"] = (
            f"Libro Diario limpiado correctamente. "
            f"Filas borradas: {resultado['filas_borradas']}."
        )
        return resultado

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo limpiar Libro Diario: {e}",
            "backup": resultado["backup"],
            "filas_borradas": 0,
            "detalle": resultado["detalle"],
        }

    finally:
        conn.close()


# ======================================================
# LIMPIEZA COBRANZAS / RECIBOS
# ======================================================

def limpiar_cobranzas_recibos_admin(empresa_id=1, confirmar_texto=""):
    empresa_id = int(empresa_id or 1)

    if not _confirmacion_valida(confirmar_texto, "BORRAR RECIBOS"):
        return {
            "ok": False,
            "mensaje": "Confirmación inválida. Escribí BORRAR RECIBOS.",
            "backup": "",
            "filas_borradas": 0,
            "detalle": [],
        }

    resultado = _resultado_base("limpiar_cobranzas_recibos")
    resultado["backup"] = _crear_backup("antes_borrar_recibos_cobranzas")

    conn = conectar()
    cur = conn.cursor()

    try:
        where_sql, params = _where_empresa(conn, "cobranzas", empresa_id)
        cobranza_ids = _ids(conn, "cobranzas", where_sql, params)

        tesoreria_ids = _obtener_tesoreria_ids(conn, "cobranzas", cobranza_ids)
        numeros_recibo = _obtener_referencias(conn, "cobranzas", "numero_recibo", cobranza_ids)

        conciliacion_ids = _obtener_conciliacion_ids_por_tesoreria(conn, tesoreria_ids)
        _borrar_conciliaciones_por_ids(cur, resultado, conciliacion_ids)

        caja_ids = _obtener_caja_movimiento_ids(
            conn,
            empresa_id=empresa_id,
            tipos=["COBRANZA_EFECTIVO"],
            referencias=numeros_recibo,
            tesoreria_ids=tesoreria_ids,
        )
        _borrar_caja_movimientos_por_ids(cur, resultado, caja_ids)

        _borrar_documentos_tesoreria(
            cur,
            resultado,
            origen_tabla="cobranzas",
            origen_ids=cobranza_ids,
            numeros=numeros_recibo,
        )

        _borrar_tesoreria_por_ids(cur, resultado, tesoreria_ids)

        if cobranza_ids:
            in_sql, in_params = _in_clause(cobranza_ids)

            _borrar_si_existe(
                cur,
                resultado,
                "cobranzas_imputaciones",
                f"cobranza_id {in_sql}",
                in_params,
            )

            _borrar_si_existe(
                cur,
                resultado,
                "cobranzas_retenciones",
                f"cobranza_id {in_sql}",
                in_params,
            )

            _borrar_si_existe(
                cur,
                resultado,
                "libro_diario",
                "origen_tabla = 'cobranzas' OR origen = 'COBRANZAS'",
            )

            _borrar_si_existe(
                cur,
                resultado,
                "cuenta_corriente_clientes",
                "origen = 'COBRANZAS'",
            )

            _borrar_si_existe(
                cur,
                resultado,
                "cobranzas_auditoria",
                "entidad = 'cobranzas'",
            )

            _borrar_si_existe(
                cur,
                resultado,
                "cobranzas",
                f"id {in_sql}",
                in_params,
            )

        conn.commit()

        resultado["mensaje"] = (
            f"Cobranzas / Recibos eliminados correctamente. "
            f"Filas borradas: {resultado['filas_borradas']}."
        )
        return resultado

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudieron eliminar recibos/cobranzas: {e}",
            "backup": resultado["backup"],
            "filas_borradas": 0,
            "detalle": resultado["detalle"],
        }

    finally:
        conn.close()


# ======================================================
# LIMPIEZA PAGOS / ÓRDENES
# ======================================================

def limpiar_pagos_ordenes_admin(empresa_id=1, confirmar_texto=""):
    empresa_id = int(empresa_id or 1)

    if not _confirmacion_valida(confirmar_texto, "BORRAR ORDENES"):
        return {
            "ok": False,
            "mensaje": "Confirmación inválida. Escribí BORRAR ORDENES.",
            "backup": "",
            "filas_borradas": 0,
            "detalle": [],
        }

    resultado = _resultado_base("limpiar_pagos_ordenes")
    resultado["backup"] = _crear_backup("antes_borrar_ordenes_pagos")

    conn = conectar()
    cur = conn.cursor()

    try:
        where_sql, params = _where_empresa(conn, "pagos", empresa_id)
        pago_ids = _ids(conn, "pagos", where_sql, params)

        tesoreria_ids = _obtener_tesoreria_ids(conn, "pagos", pago_ids)
        numeros_orden = _obtener_referencias(conn, "pagos", "numero_orden_pago", pago_ids)

        conciliacion_ids = _obtener_conciliacion_ids_por_tesoreria(conn, tesoreria_ids)
        _borrar_conciliaciones_por_ids(cur, resultado, conciliacion_ids)

        caja_ids = _obtener_caja_movimiento_ids(
            conn,
            empresa_id=empresa_id,
            tipos=["PAGO_EFECTIVO"],
            referencias=numeros_orden,
            tesoreria_ids=tesoreria_ids,
        )
        _borrar_caja_movimientos_por_ids(cur, resultado, caja_ids)

        _borrar_documentos_tesoreria(
            cur,
            resultado,
            origen_tabla="pagos",
            origen_ids=pago_ids,
            numeros=numeros_orden,
        )

        _borrar_tesoreria_por_ids(cur, resultado, tesoreria_ids)

        if pago_ids:
            in_sql, in_params = _in_clause(pago_ids)

            _borrar_si_existe(
                cur,
                resultado,
                "pagos_imputaciones",
                f"pago_id {in_sql}",
                in_params,
            )

            _borrar_si_existe(
                cur,
                resultado,
                "pagos_retenciones",
                f"pago_id {in_sql}",
                in_params,
            )

            _borrar_si_existe(
                cur,
                resultado,
                "libro_diario",
                "origen_tabla = 'pagos' OR origen = 'PAGOS'",
            )

            _borrar_si_existe(
                cur,
                resultado,
                "cuenta_corriente_proveedores",
                "origen = 'PAGOS'",
            )

            _borrar_si_existe(
                cur,
                resultado,
                "pagos_auditoria",
                "entidad = 'pagos'",
            )

            _borrar_si_existe(
                cur,
                resultado,
                "pagos",
                f"id {in_sql}",
                in_params,
            )

        conn.commit()

        resultado["mensaje"] = (
            f"Pagos / Órdenes eliminados correctamente. "
            f"Filas borradas: {resultado['filas_borradas']}."
        )
        return resultado

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudieron eliminar pagos/órdenes: {e}",
            "backup": resultado["backup"],
            "filas_borradas": 0,
            "detalle": resultado["detalle"],
        }

    finally:
        conn.close()


# ======================================================
# LIMPIEZA BANCO
# ======================================================

def limpiar_banco_demo_admin(empresa_id=1, confirmar_texto=""):
    empresa_id = int(empresa_id or 1)

    if not _confirmacion_valida(confirmar_texto, "BORRAR BANCO"):
        return {
            "ok": False,
            "mensaje": "Confirmación inválida. Escribí BORRAR BANCO.",
            "backup": "",
            "filas_borradas": 0,
            "detalle": [],
        }

    resultado = _resultado_base("limpiar_banco")
    resultado["backup"] = _crear_backup("antes_borrar_banco_demo")

    conn = conectar()
    cur = conn.cursor()

    try:
        tablas = [
            "bancos_conciliaciones_detalle",
            "bancos_conciliaciones",
            "bancos_asientos_propuestos",
            "bancos_movimientos",
            "bancos_importaciones",
        ]

        for tabla in tablas:
            if not _tabla_existe(conn, tabla):
                continue

            where_sql, params = _where_empresa(conn, tabla, empresa_id)
            _borrar_si_existe(cur, resultado, tabla, where_sql, params)

        conn.commit()

        resultado["mensaje"] = (
            f"Banco demo eliminado correctamente. "
            f"Filas borradas: {resultado['filas_borradas']}."
        )
        return resultado

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo limpiar Banco demo: {e}",
            "backup": resultado["backup"],
            "filas_borradas": 0,
            "detalle": resultado["detalle"],
        }

    finally:
        conn.close()


# ======================================================
# LIMPIEZA DEMO GENERAL
# ======================================================

def limpiar_demo_operativa_admin(empresa_id=1, confirmar_texto=""):
    empresa_id = int(empresa_id or 1)

    if not _confirmacion_valida(confirmar_texto, "LIMPIAR DEMO"):
        return {
            "ok": False,
            "mensaje": "Confirmación inválida. Escribí LIMPIAR DEMO.",
            "backup": "",
            "filas_borradas": 0,
            "detalle": [],
        }

    resultado = _resultado_base("limpiar_demo_operativa")
    resultado["backup"] = _crear_backup("antes_limpiar_demo_operativa")

    conn = conectar()
    cur = conn.cursor()

    try:
        orden_tablas = [
            "bancos_conciliaciones_detalle",
            "bancos_conciliaciones",
            "bancos_asientos_propuestos",
            "bancos_movimientos",
            "bancos_importaciones",

            "caja_asientos",
            "caja_arqueos",
            "caja_auditoria",
            "caja_movimientos",

            "documentos_tesoreria",
            "tesoreria_documentos",
            "documentos_emitidos",

            "cobranzas_imputaciones",
            "cobranzas_retenciones",
            "cobranzas_auditoria",

            "pagos_imputaciones",
            "pagos_retenciones",
            "pagos_auditoria",

            "tesoreria_operaciones_componentes",
            "tesoreria_operaciones_vinculos",
            "tesoreria_auditoria",
            "tesoreria_operaciones",

            "cuenta_corriente_clientes",
            "cuenta_corriente_proveedores",
            "libro_diario",

            "cobranzas",
            "pagos",

            "ventas_comprobantes",
            "compras_comprobantes",
            "comprobantes_procesados",
            "errores_carga",
            "advertencias_carga",
            "historial_cargas",
        ]

        for tabla in orden_tablas:
            if not _tabla_existe(conn, tabla):
                continue

            where_sql, params = _where_empresa(conn, tabla, empresa_id)
            _borrar_si_existe(cur, resultado, tabla, where_sql, params)

        conn.commit()

        resultado["mensaje"] = (
            f"Demo operativa limpiada correctamente. "
            f"Filas borradas: {resultado['filas_borradas']}."
        )
        return resultado

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo limpiar demo operativa: {e}",
            "backup": resultado["backup"],
            "filas_borradas": 0,
            "detalle": resultado["detalle"],
        }

    finally:
        conn.close()