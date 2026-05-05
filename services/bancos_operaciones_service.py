import json

import pandas as pd

from database import conectar, ejecutar_query

from services.bancos_service import CONFIG_CONTABLE_DEFAULT
from services.iva_movimientos_fiscales_service import (
    ESTADO_ANULADO,
    ESTADO_BORRADOR,
    ESTADO_CONFIRMADO,
    asegurar_estructura_iva_movimientos_fiscales,
    registrar_movimiento_fiscal,
)


# ======================================================
# UTILIDADES INTERNAS
# ======================================================

def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def _numero(valor):
    try:
        if valor is None or pd.isna(valor):
            return 0.0
    except Exception:
        if valor is None:
            return 0.0

    try:
        return round(float(valor), 2)
    except Exception:
        return 0.0


def _serializar(valor):
    try:
        return json.dumps(valor, ensure_ascii=False, default=str)
    except Exception:
        return str(valor)


def _columnas_tabla(conn, tabla):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)
        return df["name"].tolist()
    except Exception:
        return []


def _tabla_tiene_columna(conn, tabla, columna):
    return columna in _columnas_tabla(conn, tabla)


def _registrar_auditoria_segura(
    usuario_id,
    empresa_id,
    modulo,
    accion,
    entidad,
    entidad_id,
    valor_anterior,
    valor_nuevo,
    motivo,
):
    if usuario_id is None:
        return

    try:
        from services.seguridad_service import registrar_auditoria

        registrar_auditoria(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo=modulo,
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            valor_anterior=_serializar(valor_anterior),
            valor_nuevo=_serializar(valor_nuevo),
            motivo=motivo,
        )
    except Exception:
        pass


def _obtener_movimiento(cur, empresa_id, movimiento_id):
    cur.execute(
        """
        SELECT *
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, movimiento_id),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [c[0] for c in cur.description]
    return dict(zip(columnas, fila))


def _obtener_conciliacion(cur, empresa_id, conciliacion_id):
    cur.execute(
        """
        SELECT *
        FROM bancos_conciliaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, conciliacion_id),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [c[0] for c in cur.description]
    return dict(zip(columnas, fila))


def _obtener_detalles_conciliacion(cur, empresa_id, conciliacion_id):
    cur.execute(
        """
        SELECT *
        FROM bancos_conciliaciones_detalle
        WHERE empresa_id = ?
          AND conciliacion_id = ?
        ORDER BY id
        """,
        (empresa_id, conciliacion_id),
    )

    filas = cur.fetchall()
    columnas = [c[0] for c in cur.description]

    return [dict(zip(columnas, fila)) for fila in filas]


def _actualizar_estado_movimiento(cur, empresa_id, movimiento_id):
    movimiento = _obtener_movimiento(cur, empresa_id, movimiento_id)

    if movimiento is None:
        return

    importe_total = abs(_numero(movimiento.get("importe")))
    importe_conciliado = _numero(movimiento.get("importe_conciliado"))
    importe_pendiente = max(round(importe_total - importe_conciliado, 2), 0.0)

    if importe_total <= 0:
        porcentaje = 0.0
    else:
        porcentaje = round((importe_conciliado / importe_total) * 100, 2)

    if importe_pendiente <= 0.01:
        estado = "CONCILIADO"
    elif importe_conciliado > 0:
        estado = "PARCIAL"
    else:
        estado = "PENDIENTE"

    cur.execute(
        """
        UPDATE bancos_movimientos
        SET importe_pendiente = ?,
            porcentaje_conciliado = ?,
            estado_conciliacion = ?
        WHERE empresa_id = ?
          AND id = ?
        """,
        (
            importe_pendiente,
            porcentaje,
            estado,
            empresa_id,
            movimiento_id,
        ),
    )


def _nombre_cuenta_banco_desde_movimiento(movimiento):
    banco = _texto(movimiento.get("banco"))
    nombre_cuenta = _texto(movimiento.get("nombre_cuenta"))

    if banco and nombre_cuenta:
        return f"{banco} - {nombre_cuenta}"

    if banco:
        return banco

    if nombre_cuenta:
        return nombre_cuenta

    return CONFIG_CONTABLE_DEFAULT["cuenta_banco"][1]


def _insertar_cuenta_corriente_cliente(
    cur,
    empresa_id,
    fecha,
    cliente,
    cuit,
    tipo,
    numero,
    debe,
    haber,
    origen,
    archivo,
):
    columnas = [
        "fecha",
        "cliente",
        "cuit",
        "tipo",
        "numero",
        "debe",
        "haber",
        "saldo",
        "origen",
        "archivo",
    ]

    valores = [
        fecha,
        cliente,
        cuit,
        tipo,
        numero,
        round(float(debe), 2),
        round(float(haber), 2),
        0,
        origen,
        archivo,
    ]

    if _tabla_tiene_columna(cur.connection, "cuenta_corriente_clientes", "empresa_id"):
        columnas.insert(0, "empresa_id")
        valores.insert(0, empresa_id)

    placeholders = ", ".join(["?"] * len(columnas))
    columnas_sql = ", ".join(columnas)

    cur.execute(
        f"""
        INSERT INTO cuenta_corriente_clientes
        ({columnas_sql})
        VALUES ({placeholders})
        """,
        tuple(valores),
    )


def _insertar_cuenta_corriente_proveedor(
    cur,
    empresa_id,
    fecha,
    proveedor,
    cuit,
    tipo,
    numero,
    debe,
    haber,
    origen,
    archivo,
):
    columnas = [
        "fecha",
        "proveedor",
        "cuit",
        "tipo",
        "numero",
        "debe",
        "haber",
        "saldo",
        "origen",
        "archivo",
    ]

    valores = [
        fecha,
        proveedor,
        cuit,
        tipo,
        numero,
        round(float(debe), 2),
        round(float(haber), 2),
        0,
        origen,
        archivo,
    ]

    if _tabla_tiene_columna(cur.connection, "cuenta_corriente_proveedores", "empresa_id"):
        columnas.insert(0, "empresa_id")
        valores.insert(0, empresa_id)

    placeholders = ", ".join(["?"] * len(columnas))
    columnas_sql = ", ".join(columnas)

    cur.execute(
        f"""
        INSERT INTO cuenta_corriente_proveedores
        ({columnas_sql})
        VALUES ({placeholders})
        """,
        tuple(valores),
    )


def _insertar_asiento_propuesto(
    cur,
    empresa_id,
    movimiento_id,
    conciliacion_id,
    fecha,
    cuenta_codigo,
    cuenta_nombre,
    debe,
    haber,
    glosa,
):
    cur.execute(
        """
        INSERT INTO bancos_asientos_propuestos
        (
            empresa_id,
            movimiento_banco_id,
            conciliacion_id,
            fecha,
            cuenta_codigo,
            cuenta_nombre,
            debe,
            haber,
            glosa,
            estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO')
        """,
        (
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            cuenta_codigo,
            cuenta_nombre,
            round(float(debe), 2),
            round(float(haber), 2),
            glosa,
        ),
    )


def _crear_conciliacion(
    cur,
    empresa_id,
    movimiento,
    tipo_conciliacion,
    importe_imputado,
    observacion,
    usuario_id,
):
    importe_total = abs(_numero(movimiento.get("importe")))
    importe_pendiente = max(round(importe_total - float(importe_imputado), 2), 0.0)

    if importe_total <= 0:
        porcentaje = 0.0
    else:
        porcentaje = round((float(importe_imputado) / importe_total) * 100, 2)

    estado = "CONFIRMADA" if importe_pendiente <= 0.01 else "PARCIAL"

    cur.execute(
        """
        INSERT INTO bancos_conciliaciones
        (
            empresa_id,
            movimiento_banco_id,
            fecha,
            tipo_conciliacion,
            estado,
            importe_total,
            importe_imputado,
            importe_pendiente,
            porcentaje_conciliado,
            observacion,
            usuario_id,
            fecha_confirmacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            empresa_id,
            int(movimiento["id"]),
            movimiento.get("fecha"),
            tipo_conciliacion,
            estado,
            importe_total,
            round(float(importe_imputado), 2),
            importe_pendiente,
            porcentaje,
            observacion,
            usuario_id,
        ),
    )

    return int(cur.lastrowid)


def _revertir_detalles_cuenta_corriente(cur, empresa_id, conciliacion, detalles, motivo):
    fecha = _texto(conciliacion.get("fecha"))
    conciliacion_id = int(conciliacion["id"])
    archivo = f"DESIMPUTACION_BANCO_CONC_{conciliacion_id}"

    revertidos = {
        "clientes": 0,
        "proveedores": 0,
        "fiscales": 0,
    }

    for det in detalles:
        tipo_imputacion = _texto(det.get("tipo_imputacion")).upper()
        importe = _numero(det.get("importe_imputado"))

        if importe <= 0:
            continue

        tercero = _texto(det.get("tercero_nombre"))
        cuit = _texto(det.get("tercero_cuit"))
        comprobante = _texto(det.get("comprobante"))

        partes = comprobante.split(" ", 1)

        if len(partes) == 2:
            tipo, numero = partes
        else:
            tipo = tipo_imputacion
            numero = comprobante

        if tipo_imputacion == "COBRO_FACTURA_CLIENTE":
            _insertar_cuenta_corriente_cliente(
                cur=cur,
                empresa_id=empresa_id,
                fecha=fecha,
                cliente=tercero,
                cuit=cuit,
                tipo=tipo,
                numero=numero,
                debe=importe,
                haber=0,
                origen="BANCO_DESIMPUTACION",
                archivo=archivo,
            )
            revertidos["clientes"] += 1

        elif tipo_imputacion == "PAGO_FACTURA_PROVEEDOR":
            _insertar_cuenta_corriente_proveedor(
                cur=cur,
                empresa_id=empresa_id,
                fecha=fecha,
                proveedor=tercero,
                cuit=cuit,
                tipo=tipo,
                numero=numero,
                debe=0,
                haber=importe,
                origen="BANCO_DESIMPUTACION",
                archivo=archivo,
            )
            revertidos["proveedores"] += 1

        elif tipo_imputacion == "PAGO_FISCAL":
            revertidos["fiscales"] += 1

    return revertidos


def _desimputar_conciliacion_en_transaccion(
    cur,
    empresa_id,
    conciliacion_id,
    usuario_id=None,
    motivo="",
):
    conciliacion = _obtener_conciliacion(cur, empresa_id, conciliacion_id)

    if conciliacion is None:
        return {
            "ok": False,
            "mensaje": "No se encontró la conciliación indicada.",
            "conciliacion_id": conciliacion_id,
        }

    movimiento_id = int(conciliacion["movimiento_banco_id"])
    movimiento = _obtener_movimiento(cur, empresa_id, movimiento_id)
    detalles = _obtener_detalles_conciliacion(cur, empresa_id, conciliacion_id)

    revertidos = _revertir_detalles_cuenta_corriente(
        cur=cur,
        empresa_id=empresa_id,
        conciliacion=conciliacion,
        detalles=detalles,
        motivo=motivo,
    )

    cur.execute(
        """
        DELETE FROM bancos_asientos_propuestos
        WHERE empresa_id = ?
          AND conciliacion_id = ?
        """,
        (empresa_id, conciliacion_id),
    )
    asientos_eliminados = cur.rowcount

    cur.execute(
        """
        DELETE FROM bancos_conciliaciones_detalle
        WHERE empresa_id = ?
          AND conciliacion_id = ?
        """,
        (empresa_id, conciliacion_id),
    )
    detalles_eliminados = cur.rowcount

    cur.execute(
        """
        DELETE FROM bancos_conciliaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, conciliacion_id),
    )
    conciliaciones_eliminadas = cur.rowcount

    importe_imputado = _numero(conciliacion.get("importe_imputado"))

    cur.execute(
        """
        UPDATE bancos_movimientos
        SET importe_conciliado = MAX(ROUND(IFNULL(importe_conciliado, 0) - ?, 2), 0)
        WHERE empresa_id = ?
          AND id = ?
        """,
        (importe_imputado, empresa_id, movimiento_id),
    )

    _actualizar_estado_movimiento(cur, empresa_id, movimiento_id)

    return {
        "ok": True,
        "mensaje": "Conciliación desimputada correctamente.",
        "conciliacion_id": conciliacion_id,
        "movimiento_id": movimiento_id,
        "importe_revertido": importe_imputado,
        "revertidos": revertidos,
        "asientos_eliminados": asientos_eliminados,
        "detalles_eliminados": detalles_eliminados,
        "conciliaciones_eliminadas": conciliaciones_eliminadas,
        "valor_anterior": {
            "conciliacion": conciliacion,
            "movimiento": movimiento,
            "detalles": detalles,
        },
    }


# ======================================================
# CONSULTAS PARA UI
# ======================================================

def obtener_conciliaciones_bancarias(empresa_id=1):
    conn = conectar()

    try:
        df = pd.read_sql_query(
            """
            SELECT
                c.id,
                c.fecha,
                c.movimiento_banco_id,
                c.tipo_conciliacion,
                c.estado,
                c.importe_total,
                c.importe_imputado,
                c.importe_pendiente,
                c.porcentaje_conciliado,
                c.observacion,
                m.banco,
                m.nombre_cuenta,
                m.concepto,
                m.referencia,
                m.causal,
                m.archivo,
                m.importacion_id
            FROM bancos_conciliaciones c
            LEFT JOIN bancos_movimientos m
                   ON m.empresa_id = c.empresa_id
                  AND m.id = c.movimiento_banco_id
            WHERE c.empresa_id = ?
            ORDER BY c.fecha DESC, c.id DESC
            """,
            conn,
            params=(empresa_id,),
        )

        return df

    except Exception:
        return pd.DataFrame()

    finally:
        conn.close()


# ======================================================
# ELIMINACIÓN SEGURA / ADMINISTRATIVA DE IMPORTACIONES
# ======================================================

def obtener_resumen_eliminacion_importacion_bancaria(importacion_id, empresa_id=1):
    importacion = ejecutar_query(
        """
        SELECT
            id,
            fecha_carga,
            banco,
            nombre_cuenta,
            nombre_archivo,
            formato_archivo,
            registros_detectados,
            procesados,
            duplicados,
            errores,
            saldo_inicial_extracto,
            total_debitos,
            total_creditos,
            saldo_final_extracto,
            saldo_final_calculado,
            diferencia_saldo,
            observacion
        FROM bancos_importaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, importacion_id),
        fetch=True,
    )

    if importacion.empty:
        return {
            "ok": False,
            "mensaje": "No se encontró la importación bancaria indicada.",
            "importacion": {},
            "movimientos": 0,
            "asientos_propuestos": 0,
            "grupos_fiscales": 0,
            "conciliaciones": 0,
            "conciliaciones_bloqueantes": 0,
            "movimientos_diario_confirmado": 0,
        }

    movimientos = ejecutar_query(
        """
        SELECT id, estado_contable
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND importacion_id = ?
        """,
        (empresa_id, importacion_id),
        fetch=True,
    )

    movimientos_ids = movimientos["id"].astype(int).tolist() if not movimientos.empty else []

    asientos_propuestos = 0
    conciliaciones = 0
    conciliaciones_bloqueantes = 0
    movimientos_diario_confirmado = 0

    if not movimientos.empty and "estado_contable" in movimientos.columns:
        estados_diario = {
            "CONFIRMADO_DIARIO",
            "DIARIO_CONFIRMADO",
            "ASIENTO_CONFIRMADO",
            "MAYORIZADO",
        }

        movimientos_diario_confirmado = len(
            movimientos[
                movimientos["estado_contable"]
                .fillna("")
                .astype(str)
                .str.upper()
                .isin(estados_diario)
            ]
        )

    if movimientos_ids:
        placeholders = ",".join(["?"] * len(movimientos_ids))

        asientos = ejecutar_query(
            f"""
            SELECT COUNT(*) AS cantidad
            FROM bancos_asientos_propuestos
            WHERE empresa_id = ?
              AND movimiento_banco_id IN ({placeholders})
            """,
            tuple([empresa_id] + movimientos_ids),
            fetch=True,
        )

        if not asientos.empty:
            asientos_propuestos = int(asientos.iloc[0]["cantidad"] or 0)

        conciliaciones_df = ejecutar_query(
            f"""
            SELECT id, estado
            FROM bancos_conciliaciones
            WHERE empresa_id = ?
              AND movimiento_banco_id IN ({placeholders})
            """,
            tuple([empresa_id] + movimientos_ids),
            fetch=True,
        )

        if not conciliaciones_df.empty:
            conciliaciones = len(conciliaciones_df)

            estados_eliminables = {"", "BORRADOR", "PENDIENTE", "ANULADA"}
            bloqueantes = conciliaciones_df[
                ~conciliaciones_df["estado"]
                .fillna("")
                .astype(str)
                .str.upper()
                .isin(estados_eliminables)
            ]

            conciliaciones_bloqueantes = len(bloqueantes)

    grupos = ejecutar_query(
        """
        SELECT COUNT(*) AS cantidad
        FROM bancos_grupos_fiscales
        WHERE empresa_id = ?
          AND importacion_id = ?
        """,
        (empresa_id, importacion_id),
        fetch=True,
    )

    grupos_fiscales = 0

    if not grupos.empty:
        grupos_fiscales = int(grupos.iloc[0]["cantidad"] or 0)

    return {
        "ok": True,
        "mensaje": "Resumen de eliminación generado correctamente.",
        "importacion": importacion.iloc[0].to_dict(),
        "movimientos": len(movimientos_ids),
        "asientos_propuestos": asientos_propuestos,
        "grupos_fiscales": grupos_fiscales,
        "conciliaciones": conciliaciones,
        "conciliaciones_bloqueantes": conciliaciones_bloqueantes,
        "movimientos_diario_confirmado": movimientos_diario_confirmado,
    }


def eliminar_importacion_bancaria(
    importacion_id,
    empresa_id=1,
    usuario_id=None,
    motivo="",
    forzar_eliminacion_admin=False,
):
    """
    Elimina una importación bancaria de forma controlada.

    Usuario común:
    - puede eliminar si no hay conciliaciones confirmadas/bloqueantes.

    Administrador:
    - puede forzar la eliminación del archivo completo, incluso con conciliaciones,
      siempre que todavía no haya impacto confirmado en Libro Diario.
    - la reversión interna desimputa, revierte cuenta corriente, borra asientos
      propuestos, conciliaciones, grupos fiscales, movimientos e importación.
    """

    resumen = obtener_resumen_eliminacion_importacion_bancaria(
        importacion_id=importacion_id,
        empresa_id=empresa_id,
    )

    if not resumen["ok"]:
        return resumen

    if int(resumen.get("movimientos_diario_confirmado", 0) or 0) > 0:
        return {
            "ok": False,
            "mensaje": (
                "No se puede eliminar la importación porque existen movimientos "
                "con impacto contable confirmado. En ese caso corresponde reversión "
                "contable, no borrado físico."
            ),
            "importacion_id": importacion_id,
            "resumen_previo": resumen,
        }

    if int(resumen.get("conciliaciones_bloqueantes", 0) or 0) > 0 and not forzar_eliminacion_admin:
        return {
            "ok": False,
            "mensaje": (
                "No se puede eliminar la importación porque tiene conciliaciones "
                "confirmadas. Un usuario administrador puede usar eliminación completa "
                "con reversión automática."
            ),
            "importacion_id": importacion_id,
            "resumen_previo": resumen,
        }

    conn = conectar()
    cur = conn.cursor()

    eliminados = {
        "importaciones": 0,
        "movimientos": 0,
        "asientos_propuestos": 0,
        "grupos_fiscales": 0,
        "conciliaciones": 0,
        "conciliaciones_detalle": 0,
        "conciliaciones_desimputadas": 0,
        "reversiones_cliente": 0,
        "reversiones_proveedor": 0,
        "reversiones_fiscales": 0,
    }

    try:
        cur.execute(
            """
            SELECT id
            FROM bancos_movimientos
            WHERE empresa_id = ?
              AND importacion_id = ?
            """,
            (empresa_id, importacion_id),
        )

        movimientos_ids = [int(row[0]) for row in cur.fetchall()]

        if movimientos_ids:
            placeholders_mov = ",".join(["?"] * len(movimientos_ids))

            cur.execute(
                f"""
                SELECT id
                FROM bancos_conciliaciones
                WHERE empresa_id = ?
                  AND movimiento_banco_id IN ({placeholders_mov})
                ORDER BY id
                """,
                tuple([empresa_id] + movimientos_ids),
            )

            conciliaciones_ids = [int(row[0]) for row in cur.fetchall()]

            for conciliacion_id in conciliaciones_ids:
                resultado_desimputacion = _desimputar_conciliacion_en_transaccion(
                    cur=cur,
                    empresa_id=empresa_id,
                    conciliacion_id=conciliacion_id,
                    usuario_id=usuario_id,
                    motivo=motivo or "Desimputación automática por eliminación de importación bancaria.",
                )

                if resultado_desimputacion.get("ok"):
                    eliminados["conciliaciones_desimputadas"] += 1
                    eliminados["asientos_propuestos"] += int(resultado_desimputacion.get("asientos_eliminados", 0) or 0)
                    eliminados["conciliaciones_detalle"] += int(resultado_desimputacion.get("detalles_eliminados", 0) or 0)
                    eliminados["conciliaciones"] += int(resultado_desimputacion.get("conciliaciones_eliminadas", 0) or 0)

                    revertidos = resultado_desimputacion.get("revertidos", {})
                    eliminados["reversiones_cliente"] += int(revertidos.get("clientes", 0) or 0)
                    eliminados["reversiones_proveedor"] += int(revertidos.get("proveedores", 0) or 0)
                    eliminados["reversiones_fiscales"] += int(revertidos.get("fiscales", 0) or 0)

            cur.execute(
                f"""
                DELETE FROM bancos_asientos_propuestos
                WHERE empresa_id = ?
                  AND movimiento_banco_id IN ({placeholders_mov})
                """,
                tuple([empresa_id] + movimientos_ids),
            )

            eliminados["asientos_propuestos"] += cur.rowcount

        cur.execute(
            """
            DELETE FROM bancos_grupos_fiscales
            WHERE empresa_id = ?
              AND importacion_id = ?
            """,
            (empresa_id, importacion_id),
        )
        eliminados["grupos_fiscales"] = cur.rowcount

        cur.execute(
            """
            DELETE FROM bancos_movimientos
            WHERE empresa_id = ?
              AND importacion_id = ?
            """,
            (empresa_id, importacion_id),
        )
        eliminados["movimientos"] = cur.rowcount

        cur.execute(
            """
            DELETE FROM bancos_importaciones
            WHERE empresa_id = ?
              AND id = ?
            """,
            (empresa_id, importacion_id),
        )
        eliminados["importaciones"] = cur.rowcount

        conn.commit()

        _registrar_auditoria_segura(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Banco / Caja",
            accion=(
                "Eliminar importación bancaria completa como administrador"
                if forzar_eliminacion_admin
                else "Eliminar importación bancaria"
            ),
            entidad="bancos_importaciones",
            entidad_id=importacion_id,
            valor_anterior=resumen,
            valor_nuevo=eliminados,
            motivo=motivo or "Eliminación controlada de importación bancaria.",
        )

        return {
            "ok": True,
            "mensaje": "Importación bancaria eliminada correctamente.",
            "importacion_id": importacion_id,
            "eliminados": eliminados,
            "resumen_previo": resumen,
        }

    except Exception as e:
        conn.rollback()

        return {
            "ok": False,
            "mensaje": f"No se pudo eliminar la importación bancaria: {e}",
            "importacion_id": importacion_id,
            "eliminados": eliminados,
            "resumen_previo": resumen,
        }

    finally:
        conn.close()


# ======================================================
# DESIMPUTACIÓN INDIVIDUAL
# ======================================================

def desimputar_conciliacion_bancaria(
    conciliacion_id,
    empresa_id=1,
    usuario_id=None,
    motivo="",
):
    conn = conectar()
    cur = conn.cursor()

    try:
        resultado = _desimputar_conciliacion_en_transaccion(
            cur=cur,
            empresa_id=empresa_id,
            conciliacion_id=conciliacion_id,
            usuario_id=usuario_id,
            motivo=motivo or "Desimputación manual de conciliación bancaria.",
        )

        if not resultado.get("ok"):
            conn.rollback()
            return resultado

        conn.commit()

        _registrar_auditoria_segura(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Banco / Caja",
            accion="Desimputar conciliación bancaria",
            entidad="bancos_conciliaciones",
            entidad_id=conciliacion_id,
            valor_anterior=resultado.get("valor_anterior", {}),
            valor_nuevo={
                "importe_revertido": resultado.get("importe_revertido"),
                "revertidos": resultado.get("revertidos"),
                "movimiento_id": resultado.get("movimiento_id"),
            },
            motivo=motivo or "Desimputación manual de conciliación bancaria.",
        )

        return resultado

    except Exception as e:
        conn.rollback()

        return {
            "ok": False,
            "mensaje": f"No se pudo desimputar la conciliación: {e}",
            "conciliacion_id": conciliacion_id,
        }

    finally:
        conn.close()


# ======================================================
# CUENTAS CORRIENTES PARA IMPUTACIÓN
# ======================================================

def obtener_clientes_con_saldo_pendiente(empresa_id=1):
    conn = conectar()

    try:
        filtro_empresa = ""
        params = []

        if _tabla_tiene_columna(conn, "cuenta_corriente_clientes", "empresa_id"):
            filtro_empresa = "WHERE empresa_id = ?"
            params.append(empresa_id)

        df = pd.read_sql_query(
            f"""
            SELECT
                cliente,
                cuit,
                SUM(debe) AS debe,
                SUM(haber) AS haber,
                ROUND(SUM(debe) - SUM(haber), 2) AS saldo
            FROM cuenta_corriente_clientes
            {filtro_empresa}
            GROUP BY cliente, cuit
            HAVING ROUND(SUM(debe) - SUM(haber), 2) > 0.01
            ORDER BY cliente
            """,
            conn,
            params=params,
        )

        return df

    except Exception:
        return pd.DataFrame()

    finally:
        conn.close()


def obtener_facturas_cliente_pendientes(cliente, cuit="", empresa_id=1):
    conn = conectar()

    try:
        condiciones = ["cliente = ?"]
        params = [cliente]

        if cuit:
            condiciones.append("IFNULL(cuit, '') = ?")
            params.append(cuit)

        if _tabla_tiene_columna(conn, "cuenta_corriente_clientes", "empresa_id"):
            condiciones.append("empresa_id = ?")
            params.append(empresa_id)

        where = " AND ".join(condiciones)

        df = pd.read_sql_query(
            f"""
            SELECT
                cliente,
                cuit,
                tipo,
                numero,
                MIN(fecha) AS fecha,
                SUM(debe) AS debe,
                SUM(haber) AS haber,
                ROUND(SUM(debe) - SUM(haber), 2) AS pendiente
            FROM cuenta_corriente_clientes
            WHERE {where}
            GROUP BY cliente, cuit, tipo, numero
            HAVING ROUND(SUM(debe) - SUM(haber), 2) > 0.01
            ORDER BY fecha, numero
            """,
            conn,
            params=params,
        )

        return df

    except Exception:
        return pd.DataFrame()

    finally:
        conn.close()


def obtener_proveedores_con_saldo_pendiente(empresa_id=1):
    conn = conectar()

    try:
        filtro_empresa = ""
        params = []

        if _tabla_tiene_columna(conn, "cuenta_corriente_proveedores", "empresa_id"):
            filtro_empresa = "WHERE empresa_id = ?"
            params.append(empresa_id)

        df = pd.read_sql_query(
            f"""
            SELECT
                proveedor,
                cuit,
                SUM(debe) AS debe,
                SUM(haber) AS haber,
                ROUND(SUM(haber) - SUM(debe), 2) AS saldo
            FROM cuenta_corriente_proveedores
            {filtro_empresa}
            GROUP BY proveedor, cuit
            HAVING ROUND(SUM(haber) - SUM(debe), 2) > 0.01
            ORDER BY proveedor
            """,
            conn,
            params=params,
        )

        return df

    except Exception:
        return pd.DataFrame()

    finally:
        conn.close()


def obtener_facturas_proveedor_pendientes(proveedor, cuit="", empresa_id=1):
    conn = conectar()

    try:
        condiciones = ["proveedor = ?"]
        params = [proveedor]

        if cuit:
            condiciones.append("IFNULL(cuit, '') = ?")
            params.append(cuit)

        if _tabla_tiene_columna(conn, "cuenta_corriente_proveedores", "empresa_id"):
            condiciones.append("empresa_id = ?")
            params.append(empresa_id)

        where = " AND ".join(condiciones)

        df = pd.read_sql_query(
            f"""
            SELECT
                proveedor,
                cuit,
                tipo,
                numero,
                MIN(fecha) AS fecha,
                SUM(debe) AS debe,
                SUM(haber) AS haber,
                ROUND(SUM(haber) - SUM(debe), 2) AS pendiente
            FROM cuenta_corriente_proveedores
            WHERE {where}
            GROUP BY proveedor, cuit, tipo, numero
            HAVING ROUND(SUM(haber) - SUM(debe), 2) > 0.01
            ORDER BY fecha, numero
            """,
            conn,
            params=params,
        )

        return df

    except Exception:
        return pd.DataFrame()

    finally:
        conn.close()


# ======================================================
# IMPUTACIONES MANUALES
# ======================================================

def registrar_imputacion_cobro(
    empresa_id,
    movimiento_id,
    cliente,
    cuit,
    detalles,
    usuario_id=None,
    observacion="",
):
    conn = conectar()
    cur = conn.cursor()

    try:
        movimiento = _obtener_movimiento(cur, empresa_id, movimiento_id)

        if movimiento is None:
            return {
                "ok": False,
                "mensaje": "No se encontró el movimiento bancario seleccionado.",
            }

        if _numero(movimiento.get("credito")) <= 0 and _numero(movimiento.get("importe")) <= 0:
            return {
                "ok": False,
                "mensaje": "El movimiento seleccionado no parece ser un cobro bancario.",
            }

        detalles_validos = []
        total_imputado = 0.0

        for det in detalles:
            importe = _numero(det.get("importe_imputado"))

            if importe <= 0:
                continue

            pendiente = _numero(det.get("pendiente"))

            if importe - pendiente > 0.01:
                return {
                    "ok": False,
                    "mensaje": f"La imputación supera el saldo pendiente del comprobante {det.get('tipo')} {det.get('numero')}.",
                }

            detalles_validos.append({
                **det,
                "importe_imputado": importe,
            })
            total_imputado += importe

        total_imputado = round(total_imputado, 2)

        if total_imputado <= 0:
            return {
                "ok": False,
                "mensaje": "No se indicó importe a imputar.",
            }

        disponible = _numero(movimiento.get("importe_pendiente"))

        if disponible <= 0:
            disponible = abs(_numero(movimiento.get("importe")))

        if total_imputado - disponible > 0.01:
            return {
                "ok": False,
                "mensaje": "El total imputado supera el importe pendiente del movimiento bancario.",
            }

        conciliacion_id = _crear_conciliacion(
            cur=cur,
            empresa_id=empresa_id,
            movimiento=movimiento,
            tipo_conciliacion="COBRO_CLIENTE",
            importe_imputado=total_imputado,
            observacion=observacion,
            usuario_id=usuario_id,
        )

        fecha = _texto(movimiento.get("fecha"))
        archivo = f"BANCO_MOV_{movimiento_id}"

        for det in detalles_validos:
            tipo = _texto(det.get("tipo"))
            numero = _texto(det.get("numero"))
            importe = _numero(det.get("importe_imputado"))

            _insertar_cuenta_corriente_cliente(
                cur=cur,
                empresa_id=empresa_id,
                fecha=fecha,
                cliente=cliente,
                cuit=cuit,
                tipo=tipo,
                numero=numero,
                debe=0,
                haber=importe,
                origen="BANCO",
                archivo=archivo,
            )

            cur.execute(
                """
                INSERT INTO bancos_conciliaciones_detalle
                (
                    conciliacion_id,
                    empresa_id,
                    movimiento_banco_id,
                    tipo_imputacion,
                    entidad_tabla,
                    entidad_id,
                    tercero_nombre,
                    tercero_cuit,
                    comprobante,
                    cuenta_codigo,
                    cuenta_nombre,
                    importe_imputado,
                    saldo_anterior,
                    saldo_posterior,
                    observacion
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conciliacion_id,
                    empresa_id,
                    movimiento_id,
                    "COBRO_FACTURA_CLIENTE",
                    "cuenta_corriente_clientes",
                    cliente,
                    cuit,
                    f"{tipo} {numero}",
                    CONFIG_CONTABLE_DEFAULT["cuenta_deudores"][0],
                    CONFIG_CONTABLE_DEFAULT["cuenta_deudores"][1],
                    importe,
                    _numero(det.get("pendiente")),
                    round(_numero(det.get("pendiente")) - importe, 2),
                    observacion,
                ),
            )

        cur.execute(
            """
            UPDATE bancos_movimientos
            SET importe_conciliado = ROUND(IFNULL(importe_conciliado, 0) + ?, 2)
            WHERE empresa_id = ?
              AND id = ?
            """,
            (total_imputado, empresa_id, movimiento_id),
        )

        _actualizar_estado_movimiento(cur, empresa_id, movimiento_id)

        cuenta_banco_nombre = _nombre_cuenta_banco_desde_movimiento(movimiento)
        glosa = f"Cobro Banco/Caja imputado a cliente {cliente}"

        _insertar_asiento_propuesto(
            cur,
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            CONFIG_CONTABLE_DEFAULT["cuenta_banco"][0],
            cuenta_banco_nombre,
            total_imputado,
            0,
            glosa,
        )

        _insertar_asiento_propuesto(
            cur,
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            CONFIG_CONTABLE_DEFAULT["cuenta_deudores"][0],
            CONFIG_CONTABLE_DEFAULT["cuenta_deudores"][1],
            0,
            total_imputado,
            glosa,
        )

        conn.commit()

        _registrar_auditoria_segura(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Banco / Caja",
            accion="Imputar cobro a cliente",
            entidad="bancos_conciliaciones",
            entidad_id=conciliacion_id,
            valor_anterior=movimiento,
            valor_nuevo={
                "cliente": cliente,
                "cuit": cuit,
                "detalles": detalles_validos,
                "total_imputado": total_imputado,
            },
            motivo=observacion or "Imputación manual de cobro bancario.",
        )

        return {
            "ok": True,
            "mensaje": "Cobro imputado correctamente.",
            "conciliacion_id": conciliacion_id,
            "total_imputado": total_imputado,
        }

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo imputar el cobro: {e}",
        }

    finally:
        conn.close()


def registrar_imputacion_pago(
    empresa_id,
    movimiento_id,
    proveedor,
    cuit,
    detalles,
    usuario_id=None,
    observacion="",
):
    conn = conectar()
    cur = conn.cursor()

    try:
        movimiento = _obtener_movimiento(cur, empresa_id, movimiento_id)

        if movimiento is None:
            return {
                "ok": False,
                "mensaje": "No se encontró el movimiento bancario seleccionado.",
            }

        if _numero(movimiento.get("debito")) <= 0 and _numero(movimiento.get("importe")) >= 0:
            return {
                "ok": False,
                "mensaje": "El movimiento seleccionado no parece ser un pago bancario.",
            }

        detalles_validos = []
        total_imputado = 0.0

        for det in detalles:
            importe = _numero(det.get("importe_imputado"))

            if importe <= 0:
                continue

            pendiente = _numero(det.get("pendiente"))

            if importe - pendiente > 0.01:
                return {
                    "ok": False,
                    "mensaje": f"La imputación supera el saldo pendiente del comprobante {det.get('tipo')} {det.get('numero')}.",
                }

            detalles_validos.append({
                **det,
                "importe_imputado": importe,
            })
            total_imputado += importe

        total_imputado = round(total_imputado, 2)

        if total_imputado <= 0:
            return {
                "ok": False,
                "mensaje": "No se indicó importe a imputar.",
            }

        disponible = _numero(movimiento.get("importe_pendiente"))

        if disponible <= 0:
            disponible = abs(_numero(movimiento.get("importe")))

        if total_imputado - disponible > 0.01:
            return {
                "ok": False,
                "mensaje": "El total imputado supera el importe pendiente del movimiento bancario.",
            }

        conciliacion_id = _crear_conciliacion(
            cur=cur,
            empresa_id=empresa_id,
            movimiento=movimiento,
            tipo_conciliacion="PAGO_PROVEEDOR",
            importe_imputado=total_imputado,
            observacion=observacion,
            usuario_id=usuario_id,
        )

        fecha = _texto(movimiento.get("fecha"))
        archivo = f"BANCO_MOV_{movimiento_id}"

        for det in detalles_validos:
            tipo = _texto(det.get("tipo"))
            numero = _texto(det.get("numero"))
            importe = _numero(det.get("importe_imputado"))

            _insertar_cuenta_corriente_proveedor(
                cur=cur,
                empresa_id=empresa_id,
                fecha=fecha,
                proveedor=proveedor,
                cuit=cuit,
                tipo=tipo,
                numero=numero,
                debe=importe,
                haber=0,
                origen="BANCO",
                archivo=archivo,
            )

            cur.execute(
                """
                INSERT INTO bancos_conciliaciones_detalle
                (
                    conciliacion_id,
                    empresa_id,
                    movimiento_banco_id,
                    tipo_imputacion,
                    entidad_tabla,
                    entidad_id,
                    tercero_nombre,
                    tercero_cuit,
                    comprobante,
                    cuenta_codigo,
                    cuenta_nombre,
                    importe_imputado,
                    saldo_anterior,
                    saldo_posterior,
                    observacion
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conciliacion_id,
                    empresa_id,
                    movimiento_id,
                    "PAGO_FACTURA_PROVEEDOR",
                    "cuenta_corriente_proveedores",
                    proveedor,
                    cuit,
                    f"{tipo} {numero}",
                    CONFIG_CONTABLE_DEFAULT["cuenta_proveedores"][0],
                    CONFIG_CONTABLE_DEFAULT["cuenta_proveedores"][1],
                    importe,
                    _numero(det.get("pendiente")),
                    round(_numero(det.get("pendiente")) - importe, 2),
                    observacion,
                ),
            )

        cur.execute(
            """
            UPDATE bancos_movimientos
            SET importe_conciliado = ROUND(IFNULL(importe_conciliado, 0) + ?, 2)
            WHERE empresa_id = ?
              AND id = ?
            """,
            (total_imputado, empresa_id, movimiento_id),
        )

        _actualizar_estado_movimiento(cur, empresa_id, movimiento_id)

        cuenta_banco_nombre = _nombre_cuenta_banco_desde_movimiento(movimiento)
        glosa = f"Pago Banco/Caja imputado a proveedor {proveedor}"

        _insertar_asiento_propuesto(
            cur,
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            CONFIG_CONTABLE_DEFAULT["cuenta_proveedores"][0],
            CONFIG_CONTABLE_DEFAULT["cuenta_proveedores"][1],
            total_imputado,
            0,
            glosa,
        )

        _insertar_asiento_propuesto(
            cur,
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            CONFIG_CONTABLE_DEFAULT["cuenta_banco"][0],
            cuenta_banco_nombre,
            0,
            total_imputado,
            glosa,
        )

        conn.commit()

        _registrar_auditoria_segura(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Banco / Caja",
            accion="Imputar pago a proveedor",
            entidad="bancos_conciliaciones",
            entidad_id=conciliacion_id,
            valor_anterior=movimiento,
            valor_nuevo={
                "proveedor": proveedor,
                "cuit": cuit,
                "detalles": detalles_validos,
                "total_imputado": total_imputado,
            },
            motivo=observacion or "Imputación manual de pago bancario.",
        )

        return {
            "ok": True,
            "mensaje": "Pago imputado correctamente.",
            "conciliacion_id": conciliacion_id,
            "total_imputado": total_imputado,
        }

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo imputar el pago: {e}",
        }

    finally:
        conn.close()


def registrar_pago_fiscal(
    empresa_id,
    movimiento_id,
    impuesto,
    periodo,
    jurisdiccion,
    cuenta_codigo,
    cuenta_nombre,
    importe,
    usuario_id=None,
    observacion="",
):
    conn = conectar()
    cur = conn.cursor()

    try:
        movimiento = _obtener_movimiento(cur, empresa_id, movimiento_id)

        if movimiento is None:
            return {
                "ok": False,
                "mensaje": "No se encontró el movimiento bancario seleccionado.",
            }

        importe = _numero(importe)

        if importe <= 0:
            return {
                "ok": False,
                "mensaje": "El importe fiscal debe ser mayor a cero.",
            }

        disponible = _numero(movimiento.get("importe_pendiente"))

        if disponible <= 0:
            disponible = abs(_numero(movimiento.get("importe")))

        if importe - disponible > 0.01:
            return {
                "ok": False,
                "mensaje": "El importe fiscal supera el pendiente del movimiento bancario.",
            }

        observacion_final = (
            observacion
            or f"Pago fiscal {impuesto} período {periodo} jurisdicción {jurisdiccion}"
        )

        conciliacion_id = _crear_conciliacion(
            cur=cur,
            empresa_id=empresa_id,
            movimiento=movimiento,
            tipo_conciliacion="PAGO_FISCAL",
            importe_imputado=importe,
            observacion=observacion_final,
            usuario_id=usuario_id,
        )

        cur.execute(
            """
            INSERT INTO bancos_conciliaciones_detalle
            (
                conciliacion_id,
                empresa_id,
                movimiento_banco_id,
                tipo_imputacion,
                entidad_tabla,
                entidad_id,
                tercero_nombre,
                tercero_cuit,
                comprobante,
                cuenta_codigo,
                cuenta_nombre,
                importe_imputado,
                saldo_anterior,
                saldo_posterior,
                observacion
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conciliacion_id,
                empresa_id,
                movimiento_id,
                "PAGO_FISCAL",
                "obligacion_fiscal_manual",
                impuesto,
                "",
                f"{impuesto} {periodo} {jurisdiccion}",
                cuenta_codigo,
                cuenta_nombre,
                importe,
                importe,
                0,
                observacion_final,
            ),
        )

        cur.execute(
            """
            UPDATE bancos_movimientos
            SET importe_conciliado = ROUND(IFNULL(importe_conciliado, 0) + ?, 2)
            WHERE empresa_id = ?
              AND id = ?
            """,
            (importe, empresa_id, movimiento_id),
        )

        _actualizar_estado_movimiento(cur, empresa_id, movimiento_id)

        fecha = _texto(movimiento.get("fecha"))
        glosa = f"Pago fiscal Banco/Caja - {impuesto} - {periodo} - {jurisdiccion}"
        cuenta_banco_nombre = _nombre_cuenta_banco_desde_movimiento(movimiento)

        _insertar_asiento_propuesto(
            cur,
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            cuenta_codigo,
            cuenta_nombre,
            importe,
            0,
            glosa,
        )

        _insertar_asiento_propuesto(
            cur,
            empresa_id,
            movimiento_id,
            conciliacion_id,
            fecha,
            CONFIG_CONTABLE_DEFAULT["cuenta_banco"][0],
            cuenta_banco_nombre,
            0,
            importe,
            glosa,
        )

        conn.commit()

        _registrar_auditoria_segura(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Banco / Caja",
            accion="Imputar pago fiscal",
            entidad="bancos_conciliaciones",
            entidad_id=conciliacion_id,
            valor_anterior=movimiento,
            valor_nuevo={
                "impuesto": impuesto,
                "periodo": periodo,
                "jurisdiccion": jurisdiccion,
                "cuenta_codigo": cuenta_codigo,
                "cuenta_nombre": cuenta_nombre,
                "importe": importe,
            },
            motivo=observacion_final,
        )

        return {
            "ok": True,
            "mensaje": "Pago fiscal imputado correctamente.",
            "conciliacion_id": conciliacion_id,
            "total_imputado": importe,
        }

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudo imputar el pago fiscal: {e}",
        }

    finally:
        conn.close()



# ======================================================
# INTEGRACIÓN BANCO FISCAL -> IVA PRO
# ======================================================

ORIGEN_IVA_BANCO = "BANCO"
ORIGEN_TABLA_GRUPOS_FISCALES = "bancos_grupos_fiscales"

TIPOS_CONCEPTO_BANCO_IVA = {
    "IVA_CREDITO": "IVA crédito fiscal bancario",
    "IVA_NO_COMPUTABLE": "IVA bancario pendiente/no computable",
    "PERCEPCION_IVA": "Percepción IVA bancaria",
    "PERCEPCION_IIBB_INFORMATIVA": "Percepción IIBB bancaria informativa",
    "OTRO": "Otros tributos bancarios informativos",
}


def _fecha_anio_mes(fecha):
    texto = _texto(fecha)

    try:
        if (
            len(texto) == 10
            and texto[4] == "-"
            and texto[7] == "-"
            and texto[:4].isdigit()
            and texto[5:7].isdigit()
            and texto[8:10].isdigit()
        ):
            f = pd.to_datetime(texto, format="%Y-%m-%d", errors="raise")
        else:
            f = pd.to_datetime(fecha, errors="raise", dayfirst=True)

        return int(f.year), int(f.month), f.strftime("%Y-%m-%d")
    except Exception:
        return None, None, _texto(fecha)


def _row_get(row, columna, default=0):
    try:
        return row.get(columna, default)
    except Exception:
        return default


def _sumar_columnas(row, columnas):
    total = 0.0

    for columna in columnas:
        total += _numero(_row_get(row, columna, 0))

    return round(total, 2)


def _obtener_fiscales_iva_generados(conn, empresa_id):
    asegurar_estructura_iva_movimientos_fiscales()

    try:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                origen_id,
                tipo_concepto,
                estado,
                IFNULL(incluido_en_posicion, 1) AS incluido_en_posicion,
                IFNULL(incluido_en_portal_iva, 0) AS incluido_en_portal_iva
            FROM iva_movimientos_fiscales
            WHERE empresa_id = ?
              AND origen = ?
              AND origen_tabla = ?
              AND estado <> ?
            """,
            conn,
            params=(
                empresa_id,
                ORIGEN_IVA_BANCO,
                ORIGEN_TABLA_GRUPOS_FISCALES,
                ESTADO_ANULADO,
            ),
        )
    except Exception:
        return {}

    generados = {}

    if df.empty:
        return generados

    for _, fila in df.iterrows():
        origen_id = _normalizar_entero_dict(fila, "origen_id")
        tipo_concepto = _texto(fila.get("tipo_concepto")).upper()

        if origen_id <= 0 or not tipo_concepto:
            continue

        generados[(origen_id, tipo_concepto)] = {
            "iva_movimiento_id": int(fila.get("id")),
            "estado_iva": _texto(fila.get("estado")),
            "incluido_en_posicion": int(fila.get("incluido_en_posicion") or 0),
            "incluido_en_portal_iva": int(fila.get("incluido_en_portal_iva") or 0),
        }

    return generados


def _normalizar_entero_dict(dic, clave, default=0):
    try:
        return int(float(dic.get(clave, default) or default))
    except Exception:
        return default


def _armar_candidatos_iva_desde_grupo(row):
    grupo_id = _normalizar_entero_dict(row, "id")
    importacion_id = _normalizar_entero_dict(row, "importacion_id")
    movimiento_banco_id = _normalizar_entero_dict(row, "movimiento_banco_id")

    anio, mes, fecha = _fecha_anio_mes(row.get("fecha"))

    if not anio or not mes:
        return []

    banco = _texto(row.get("banco"))
    cuenta = _texto(row.get("nombre_cuenta"))
    referencia = _texto(row.get("referencia"))
    causal = _texto(row.get("causal"))
    concepto = _texto(row.get("concepto"))
    motivo = _texto(row.get("motivo"))
    confianza = _texto(row.get("confianza"))

    descripcion_base = " | ".join([
        item for item in [
            f"Banco {banco}" if banco else "Banco",
            cuenta,
            f"Ref {referencia}" if referencia else "",
            f"Causal {causal}" if causal else "",
            concepto[:120],
        ]
        if item
    ])

    if not descripcion_base:
        descripcion_base = f"Control fiscal bancario grupo #{grupo_id}"

    total_iva_credito = _sumar_columnas(row, ["iva_credito_21", "iva_credito_105"])
    iva_sin_base = _numero(row.get("iva_sin_base"))
    percepcion_iva = _numero(row.get("percepcion_iva"))
    percepcion_iibb = _numero(row.get("percepcion_iibb"))
    impuesto_debitos_creditos = _numero(row.get("impuesto_debitos_creditos"))
    base_gasto_bancario = _numero(row.get("base_gasto_bancario"))

    candidatos = []

    def agregar(tipo_concepto, importe, campos):
        importe = _numero(importe)

        if importe <= 0:
            return

        candidatos.append({
            "grupo_fiscal_id": grupo_id,
            "movimiento_banco_id": movimiento_banco_id or None,
            "importacion_id": importacion_id or None,
            "anio": anio,
            "mes": mes,
            "periodo": f"{anio}-{mes:02d}",
            "fecha": fecha,
            "origen": ORIGEN_IVA_BANCO,
            "origen_tabla": ORIGEN_TABLA_GRUPOS_FISCALES,
            "origen_id": grupo_id,
            "tipo_concepto": tipo_concepto,
            "tipo_concepto_visible": TIPOS_CONCEPTO_BANCO_IVA.get(tipo_concepto, tipo_concepto),
            "descripcion": f"{TIPOS_CONCEPTO_BANCO_IVA.get(tipo_concepto, tipo_concepto)} - {descripcion_base}",
            "contraparte": banco,
            "cuit": "",
            "comprobante_codigo": "",
            "comprobante_tipo": "EXTRACTO_BANCARIO",
            "punto_venta": "",
            "numero": str(referencia or grupo_id),
            "neto_gravado": _numero(campos.get("neto_gravado", 0)),
            "iva_debito": _numero(campos.get("iva_debito", 0)),
            "credito_fiscal_computable": _numero(campos.get("credito_fiscal_computable", 0)),
            "iva_no_computable": _numero(campos.get("iva_no_computable", 0)),
            "percepcion_iva": _numero(campos.get("percepcion_iva", 0)),
            "retencion_iva": _numero(campos.get("retencion_iva", 0)),
            "percepcion_iibb_informativa": _numero(campos.get("percepcion_iibb_informativa", 0)),
            "otros_tributos": _numero(campos.get("otros_tributos", 0)),
            "total": importe,
            "banco": banco,
            "nombre_cuenta": cuenta,
            "referencia": referencia,
            "causal": causal,
            "concepto_banco": concepto,
            "confianza": confianza,
            "motivo": motivo,
        })

    agregar(
        "IVA_CREDITO",
        total_iva_credito,
        {
            "neto_gravado": base_gasto_bancario,
            "credito_fiscal_computable": total_iva_credito,
        },
    )

    agregar(
        "IVA_NO_COMPUTABLE",
        iva_sin_base,
        {
            "iva_no_computable": iva_sin_base,
        },
    )

    agregar(
        "PERCEPCION_IVA",
        percepcion_iva,
        {
            "percepcion_iva": percepcion_iva,
        },
    )

    agregar(
        "PERCEPCION_IIBB_INFORMATIVA",
        percepcion_iibb,
        {
            "percepcion_iibb_informativa": percepcion_iibb,
        },
    )

    agregar(
        "OTRO",
        impuesto_debitos_creditos,
        {
            "otros_tributos": impuesto_debitos_creditos,
        },
    )

    return candidatos


def obtener_vista_previa_movimientos_fiscales_banco_iva(
    empresa_id=1,
    anio=None,
    mes=None,
    incluir_generados=True,
):
    """
    Devuelve los conceptos fiscales bancarios convertibles en movimientos IVA.

    No graba datos.
    Permite que la UI muestre una vista previa antes de generar.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    conn = conectar()

    try:
        if not _tabla_tiene_columna(conn, "bancos_grupos_fiscales", "id"):
            return pd.DataFrame()

        df_grupos = pd.read_sql_query(
            """
            SELECT *
            FROM bancos_grupos_fiscales
            WHERE empresa_id = ?
            ORDER BY fecha DESC, id DESC
            """,
            conn,
            params=(empresa_id,),
        )

        if df_grupos.empty:
            return pd.DataFrame()

        generados = _obtener_fiscales_iva_generados(conn, empresa_id)
        candidatos = []

        for _, row in df_grupos.iterrows():
            for candidato in _armar_candidatos_iva_desde_grupo(row.to_dict()):
                clave = (
                    int(candidato.get("grupo_fiscal_id") or 0),
                    _texto(candidato.get("tipo_concepto")).upper(),
                )

                generado = generados.get(clave)

                candidato["ya_generado_iva"] = generado is not None
                candidato["iva_movimiento_id"] = generado.get("iva_movimiento_id") if generado else None
                candidato["estado_iva"] = generado.get("estado_iva") if generado else "PENDIENTE"
                candidato["incluido_en_posicion_actual"] = generado.get("incluido_en_posicion") if generado else 0
                candidato["incluido_en_portal_iva_actual"] = generado.get("incluido_en_portal_iva") if generado else 0

                if not incluir_generados and candidato["ya_generado_iva"]:
                    continue

                candidatos.append(candidato)

        df = pd.DataFrame(candidatos)

        if df.empty:
            return df

        if anio is not None:
            df = df[df["anio"].astype(int) == int(anio)]

        if mes is not None:
            df = df[df["mes"].astype(int) == int(mes)]

        columnas_monetarias = [
            "neto_gravado",
            "iva_debito",
            "credito_fiscal_computable",
            "iva_no_computable",
            "percepcion_iva",
            "retencion_iva",
            "percepcion_iibb_informativa",
            "otros_tributos",
            "total",
        ]

        for columna in columnas_monetarias:
            if columna in df.columns:
                df[columna] = pd.to_numeric(df[columna], errors="coerce").fillna(0).round(2)

        return df.reset_index(drop=True)

    except Exception:
        return pd.DataFrame()

    finally:
        conn.close()


def generar_movimientos_fiscales_banco_iva(
    empresa_id=1,
    selecciones=None,
    anio=None,
    mes=None,
    estado=ESTADO_BORRADOR,
    incluido_en_posicion=False,
    incluido_en_portal_iva=False,
    motivo_no_inclusion="",
    usuario="",
    usuario_id=None,
):
    """
    Genera movimientos fiscales IVA desde Control fiscal bancario.

    selecciones:
    - Lista de dicts con grupo_fiscal_id y tipo_concepto.
    - Si viene vacía/None, no genera nada para evitar acciones masivas accidentales.
    """
    asegurar_estructura_iva_movimientos_fiscales()

    estado = _texto(estado).upper() or ESTADO_BORRADOR

    if estado not in {ESTADO_BORRADOR, ESTADO_CONFIRMADO}:
        return {
            "ok": False,
            "mensaje": "El estado inicial debe ser BORRADOR o CONFIRMADO.",
            "creados": 0,
            "omitidos": 0,
            "errores": [],
        }

    selecciones = selecciones or []

    if not selecciones:
        return {
            "ok": False,
            "mensaje": "Seleccioná al menos un concepto fiscal bancario para generar.",
            "creados": 0,
            "omitidos": 0,
            "errores": [],
        }

    claves_seleccionadas = {
        (
            int(sel.get("grupo_fiscal_id") or sel.get("origen_id") or 0),
            _texto(sel.get("tipo_concepto")).upper(),
        )
        for sel in selecciones
    }

    preview = obtener_vista_previa_movimientos_fiscales_banco_iva(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
        incluir_generados=True,
    )

    if preview.empty:
        return {
            "ok": False,
            "mensaje": "No hay conceptos fiscales bancarios disponibles para generar en IVA.",
            "creados": 0,
            "omitidos": 0,
            "errores": [],
        }

    creados = []
    omitidos = []
    errores = []

    for _, row in preview.iterrows():
        clave = (
            int(row.get("grupo_fiscal_id") or 0),
            _texto(row.get("tipo_concepto")).upper(),
        )

        if clave not in claves_seleccionadas:
            continue

        if bool(row.get("ya_generado_iva")):
            omitidos.append({
                "grupo_fiscal_id": clave[0],
                "tipo_concepto": clave[1],
                "motivo": "Ya existe movimiento fiscal IVA activo para este origen/concepto.",
            })
            continue

        try:
            movimiento = registrar_movimiento_fiscal(
                empresa_id=empresa_id,
                anio=int(row.get("anio")),
                mes=int(row.get("mes")),
                fecha=row.get("fecha"),
                origen=ORIGEN_IVA_BANCO,
                tipo_concepto=row.get("tipo_concepto"),
                descripcion=row.get("descripcion"),
                contraparte=row.get("contraparte"),
                cuit=row.get("cuit"),
                comprobante_codigo=row.get("comprobante_codigo"),
                comprobante_tipo=row.get("comprobante_tipo"),
                punto_venta=row.get("punto_venta"),
                numero=row.get("numero"),
                neto_gravado=row.get("neto_gravado"),
                iva_debito=row.get("iva_debito"),
                credito_fiscal_computable=row.get("credito_fiscal_computable"),
                iva_no_computable=row.get("iva_no_computable"),
                percepcion_iva=row.get("percepcion_iva"),
                retencion_iva=row.get("retencion_iva"),
                percepcion_iibb_informativa=row.get("percepcion_iibb_informativa"),
                otros_tributos=row.get("otros_tributos"),
                total=row.get("total"),
                estado=estado,
                incluido_en_posicion=bool(incluido_en_posicion),
                incluido_en_portal_iva=bool(incluido_en_portal_iva),
                periodo_declaracion=row.get("periodo") if incluido_en_portal_iva else "",
                motivo_no_inclusion=motivo_no_inclusion,
                usuario_inclusion_posicion=usuario,
                usuario_declaracion_portal=usuario,
                origen_tabla=ORIGEN_TABLA_GRUPOS_FISCALES,
                origen_id=int(row.get("grupo_fiscal_id")),
                observacion=(
                    "Generado desde Banco/Caja > Control fiscal bancario. "
                    f"Grupo fiscal #{int(row.get('grupo_fiscal_id'))}. "
                    f"Movimiento bancario vinculado: {row.get('movimiento_banco_id') or 'sin vínculo directo'}."
                ),
                usuario=usuario,
            )

            creados.append({
                "grupo_fiscal_id": clave[0],
                "tipo_concepto": clave[1],
                "iva_movimiento_id": movimiento.get("id") if movimiento else None,
                "total": _numero(row.get("total")),
            })

        except Exception as exc:
            errores.append({
                "grupo_fiscal_id": clave[0],
                "tipo_concepto": clave[1],
                "error": str(exc),
            })

    ok = len(errores) == 0

    if creados:
        mensaje = f"Se generaron {len(creados)} movimientos fiscales IVA desde Banco/Caja."
    elif omitidos and not errores:
        mensaje = "No se generaron movimientos nuevos: los conceptos seleccionados ya estaban enviados a IVA."
    else:
        mensaje = "No se pudieron generar movimientos fiscales IVA."

    _registrar_auditoria_segura(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        modulo="Banco / Caja",
        accion="Generar movimientos fiscales IVA desde Banco",
        entidad="iva_movimientos_fiscales",
        entidad_id="BANCO_FISCAL_IVA",
        valor_anterior={"selecciones": list(claves_seleccionadas)},
        valor_nuevo={"creados": creados, "omitidos": omitidos, "errores": errores},
        motivo="Integración Banco Fiscal -> IVA PRO.",
    )

    return {
        "ok": ok,
        "mensaje": mensaje,
        "creados": len(creados),
        "omitidos": len(omitidos),
        "errores": errores,
        "detalle_creados": creados,
        "detalle_omitidos": omitidos,
    }


# ======================================================
# ASIENTOS AGRUPADOS
# ======================================================

TIPOS_ASIENTO_AGRUPADO_BANCO = [
    "GASTO_BANCARIO_GRAVADO",
    "IVA_CREDITO_FISCAL_BANCARIO",
    "PERCEPCION_IVA_BANCARIA",
    "RECAUDACION_IIBB",
    "IMPUESTO_DEBITOS_CREDITOS",
]


def regenerar_asientos_bancarios_agrupados(importacion_id, empresa_id=1, usuario_id=None):
    conn = conectar()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT *
            FROM bancos_movimientos
            WHERE empresa_id = ?
              AND importacion_id = ?
              AND tipo_movimiento_sugerido IN (
                  'GASTO_BANCARIO_GRAVADO',
                  'IVA_CREDITO_FISCAL_BANCARIO',
                  'PERCEPCION_IVA_BANCARIA',
                  'RECAUDACION_IIBB',
                  'IMPUESTO_DEBITOS_CREDITOS'
              )
              AND debito > 0
            ORDER BY fecha, referencia, causal, id
            """,
            (empresa_id, importacion_id),
        )

        filas = cur.fetchall()

        if not filas:
            return {
                "ok": True,
                "mensaje": "No había movimientos para agrupar.",
                "grupos": 0,
                "lineas": 0,
            }

        columnas = [c[0] for c in cur.description]
        movimientos = [dict(zip(columnas, fila)) for fila in filas]
        movimientos_ids = [int(m["id"]) for m in movimientos]

        placeholders = ",".join(["?"] * len(movimientos_ids))

        cur.execute(
            f"""
            DELETE FROM bancos_asientos_propuestos
            WHERE empresa_id = ?
              AND conciliacion_id IS NULL
              AND movimiento_banco_id IN ({placeholders})
              AND estado = 'PROPUESTO'
            """,
            tuple([empresa_id] + movimientos_ids),
        )

        grupos = {}

        for mov in movimientos:
            clave = (
                mov.get("fecha"),
                mov.get("referencia") or "",
                mov.get("causal") or "",
                mov.get("banco") or "",
                mov.get("nombre_cuenta") or "",
            )

            grupos.setdefault(clave, []).append(mov)

        lineas = 0

        for clave, grupo in grupos.items():
            fecha, referencia, causal, banco, nombre_cuenta = clave
            total_haber = 0.0
            acumulado_debe = {}
            movimiento_principal_id = int(grupo[0]["id"])
            cuenta_banco_nombre = _nombre_cuenta_banco_desde_movimiento(grupo[0])

            for mov in grupo:
                monto = abs(_numero(mov.get("debito")))
                total_haber += monto

                cuenta_codigo = _texto(mov.get("cuenta_debe_codigo"))
                cuenta_nombre = _texto(mov.get("cuenta_debe_nombre"))

                if not cuenta_codigo:
                    cuenta_codigo = CONFIG_CONTABLE_DEFAULT["cuenta_otros_gastos_revisar"][0]

                if not cuenta_nombre:
                    cuenta_nombre = CONFIG_CONTABLE_DEFAULT["cuenta_otros_gastos_revisar"][1]

                acumulado_debe.setdefault((cuenta_codigo, cuenta_nombre), 0.0)
                acumulado_debe[(cuenta_codigo, cuenta_nombre)] += monto

            glosa = (
                "Asiento agrupado Banco/Caja - "
                f"{fecha} - {banco} - {nombre_cuenta} - Ref {referencia} - Causal {causal}"
            )

            for (cuenta_codigo, cuenta_nombre), monto in acumulado_debe.items():
                if monto <= 0:
                    continue

                _insertar_asiento_propuesto(
                    cur,
                    empresa_id,
                    movimiento_principal_id,
                    None,
                    fecha,
                    cuenta_codigo,
                    cuenta_nombre,
                    round(monto, 2),
                    0,
                    glosa,
                )
                lineas += 1

            if total_haber > 0:
                _insertar_asiento_propuesto(
                    cur,
                    empresa_id,
                    movimiento_principal_id,
                    None,
                    fecha,
                    CONFIG_CONTABLE_DEFAULT["cuenta_banco"][0],
                    cuenta_banco_nombre,
                    0,
                    round(total_haber, 2),
                    glosa,
                )
                lineas += 1

            for mov in grupo:
                cur.execute(
                    """
                    UPDATE bancos_movimientos
                    SET estado_contable = 'ASIENTO_PROPUESTO_AGRUPADO'
                    WHERE empresa_id = ?
                      AND id = ?
                    """,
                    (empresa_id, int(mov["id"])),
                )

        conn.commit()

        _registrar_auditoria_segura(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Banco / Caja",
            accion="Regenerar asientos bancarios agrupados",
            entidad="bancos_importaciones",
            entidad_id=importacion_id,
            valor_anterior={"importacion_id": importacion_id},
            valor_nuevo={"grupos": len(grupos), "lineas": lineas},
            motivo="Agrupación por operación bancaria.",
        )

        return {
            "ok": True,
            "mensaje": "Asientos bancarios agrupados generados correctamente.",
            "grupos": len(grupos),
            "lineas": lineas,
        }

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "mensaje": f"No se pudieron regenerar los asientos agrupados: {e}",
            "grupos": 0,
            "lineas": 0,
        }

    finally:
        conn.close()
