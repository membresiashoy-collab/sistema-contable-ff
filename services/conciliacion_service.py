import json
from datetime import datetime

import pandas as pd

from database import conectar
from services.bancos_service import inicializar_bancos
from services.tesoreria_service import inicializar_tesoreria


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


def _texto_upper(valor):
    return _texto(valor).upper()


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


def _fecha(valor):
    fecha = pd.to_datetime(valor, errors="coerce")

    if pd.isna(fecha):
        return None

    return fecha.date()


def _dias_entre(fecha_a, fecha_b):
    fa = _fecha(fecha_a)
    fb = _fecha(fecha_b)

    if fa is None or fb is None:
        return 9999

    return abs((fa - fb).days)


def _signo(valor):
    numero = _numero(valor)

    if numero > 0:
        return 1

    if numero < 0:
        return -1

    return 0


def _tabla_existe(conn, tabla):
    try:
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
    except Exception:
        return False


def _obtener_fila(cur, sql, params):
    cur.execute(sql, params)
    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [c[0] for c in cur.description]
    return dict(zip(columnas, fila))


def _obtener_movimiento_banco(cur, empresa_id, movimiento_banco_id):
    return _obtener_fila(
        cur,
        """
        SELECT *
        FROM bancos_movimientos
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, movimiento_banco_id),
    )


def _obtener_operacion_tesoreria(cur, empresa_id, operacion_tesoreria_id):
    return _obtener_fila(
        cur,
        """
        SELECT *
        FROM tesoreria_operaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, operacion_tesoreria_id),
    )


def _obtener_conciliacion(cur, empresa_id, conciliacion_id):
    return _obtener_fila(
        cur,
        """
        SELECT *
        FROM bancos_conciliaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, conciliacion_id),
    )


def _actualizar_estado_banco(cur, empresa_id, movimiento_banco_id):
    movimiento = _obtener_movimiento_banco(cur, empresa_id, movimiento_banco_id)

    if movimiento is None:
        return

    importe_total = abs(_numero(movimiento.get("importe")))
    importe_conciliado = abs(_numero(movimiento.get("importe_conciliado")))
    importe_pendiente = max(round(importe_total - importe_conciliado, 2), 0.0)

    if importe_total <= 0:
        porcentaje = 0.0
    else:
        porcentaje = round((importe_conciliado / importe_total) * 100, 2)

    if importe_pendiente <= 0.01:
        estado = "CONCILIADO"
        importe_pendiente = 0.0
        porcentaje = 100.0 if importe_total > 0 else 0.0
    elif importe_conciliado > 0:
        estado = "PARCIAL"
    else:
        estado = "PENDIENTE"

    cur.execute(
        """
        UPDATE bancos_movimientos
        SET importe_conciliado = ?,
            importe_pendiente = ?,
            porcentaje_conciliado = ?,
            estado_conciliacion = ?
        WHERE empresa_id = ?
          AND id = ?
        """,
        (
            importe_conciliado,
            importe_pendiente,
            porcentaje,
            estado,
            empresa_id,
            movimiento_banco_id,
        ),
    )


def _actualizar_estado_tesoreria(cur, empresa_id, operacion_tesoreria_id):
    operacion = _obtener_operacion_tesoreria(cur, empresa_id, operacion_tesoreria_id)

    if operacion is None:
        return

    importe_total = abs(_numero(operacion.get("importe")))
    importe_conciliado = abs(_numero(operacion.get("importe_conciliado")))
    importe_pendiente = max(round(importe_total - importe_conciliado, 2), 0.0)

    if importe_pendiente <= 0.01:
        estado = "CONCILIADA"
        importe_pendiente = 0.0
    elif importe_conciliado > 0:
        estado = "PARCIAL"
    else:
        estado = "PENDIENTE"

    # Referencia funcional: estado_conciliacion = 'CONCILIADA'
    cur.execute(
        """
        UPDATE tesoreria_operaciones
        SET importe_conciliado = ?,
            importe_pendiente = ?,
            estado_conciliacion = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE empresa_id = ?
          AND id = ?
        """,
        (
            importe_conciliado,
            importe_pendiente,
            estado,
            empresa_id,
            operacion_tesoreria_id,
        ),
    )


def _registrar_tesoreria_auditoria(
    cur,
    empresa_id,
    usuario_id,
    accion,
    entidad,
    entidad_id,
    valor_anterior=None,
    valor_nuevo=None,
    motivo="",
):
    try:
        cur.execute(
            """
            INSERT INTO tesoreria_auditoria
            (
                empresa_id,
                usuario_id,
                accion,
                entidad,
                entidad_id,
                valor_anterior,
                valor_nuevo,
                motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                usuario_id,
                accion,
                entidad,
                str(entidad_id) if entidad_id is not None else "",
                _serializar(valor_anterior),
                _serializar(valor_nuevo),
                motivo,
            ),
        )
    except Exception:
        pass


def _registrar_auditoria_seguridad(
    usuario_id,
    empresa_id,
    accion,
    entidad,
    entidad_id,
    valor_anterior=None,
    valor_nuevo=None,
    motivo="",
):
    if usuario_id is None:
        return

    try:
        from services.seguridad_service import registrar_auditoria

        registrar_auditoria(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            modulo="Conciliación",
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            valor_anterior=_serializar(valor_anterior),
            valor_nuevo=_serializar(valor_nuevo),
            motivo=motivo,
        )
    except Exception:
        pass


def _asegurar_permisos_conciliacion():
    conn = conectar()

    try:
        if not _tabla_existe(conn, "permisos") or not _tabla_existe(conn, "rol_permisos"):
            return

        permisos = [
            ("conciliacion.ver", "Ver módulo Conciliación", "Conciliación"),
            ("conciliacion.confirmar", "Confirmar conciliaciones", "Conciliación"),
            ("conciliacion.desconciliar", "Desconciliar operaciones", "Conciliación"),
        ]

        for permiso, descripcion, modulo in permisos:
            conn.execute(
                """
                INSERT OR IGNORE INTO permisos (permiso, descripcion, modulo)
                VALUES (?, ?, ?)
                """,
                (permiso, descripcion, modulo),
            )

        for rol in ["ADMINISTRADOR", "CONTADOR", "AUXILIAR"]:
            for permiso, _, _ in permisos:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO rol_permisos (rol, permiso)
                    VALUES (?, ?)
                    """,
                    (rol, permiso),
                )

        conn.commit()

    except Exception:
        conn.rollback()

    finally:
        conn.close()


# ======================================================
# INICIALIZACIÓN
# ======================================================

def inicializar_conciliacion():
    """
    Inicializa Conciliación usando las estructuras de Banco y Tesorería.

    No crea una verdad paralela:
    - Banco conserva el extracto.
    - Tesorería conserva el hecho financiero.
    - Conciliación vincula ambos con trazabilidad.
    """

    inicializar_bancos()
    inicializar_tesoreria()
    _asegurar_permisos_conciliacion()
    return True


# ======================================================
# CONSULTAS BASE
# ======================================================

def obtener_resumen_conciliacion(empresa_id=1):
    inicializar_conciliacion()
    conn = conectar()

    try:
        bancos = pd.read_sql_query(
            """
            SELECT
                COUNT(*) AS movimientos,
                SUM(CASE WHEN estado_conciliacion = 'CONCILIADO' THEN 1 ELSE 0 END) AS conciliados,
                SUM(CASE WHEN estado_conciliacion = 'PARCIAL' THEN 1 ELSE 0 END) AS parciales,
                SUM(CASE WHEN estado_conciliacion = 'PENDIENTE' THEN 1 ELSE 0 END) AS pendientes,
                ROUND(SUM(ABS(IFNULL(importe, 0))), 2) AS importe_total,
                ROUND(SUM(ABS(IFNULL(importe_conciliado, 0))), 2) AS importe_conciliado,
                ROUND(SUM(ABS(IFNULL(importe_pendiente, 0))), 2) AS importe_pendiente
            FROM bancos_movimientos
            WHERE empresa_id = ?
            """,
            conn,
            params=(empresa_id,),
        )

        tesoreria = pd.read_sql_query(
            """
            SELECT
                COUNT(*) AS operaciones,
                SUM(CASE WHEN estado_conciliacion = 'CONCILIADA' THEN 1 ELSE 0 END) AS conciliadas,
                SUM(CASE WHEN estado_conciliacion = 'PARCIAL' THEN 1 ELSE 0 END) AS parciales,
                SUM(CASE WHEN estado_conciliacion IN ('PENDIENTE', 'SUGERIDA') THEN 1 ELSE 0 END) AS pendientes,
                ROUND(SUM(ABS(IFNULL(importe, 0))), 2) AS importe_total,
                ROUND(SUM(ABS(IFNULL(importe_conciliado, 0))), 2) AS importe_conciliado,
                ROUND(SUM(ABS(IFNULL(importe_pendiente, 0))), 2) AS importe_pendiente
            FROM tesoreria_operaciones
            WHERE empresa_id = ?
              AND estado <> 'ANULADA'
            """,
            conn,
            params=(empresa_id,),
        )

        conciliaciones = pd.read_sql_query(
            """
            SELECT
                COUNT(*) AS conciliaciones,
                SUM(CASE WHEN estado = 'ANULADA' THEN 1 ELSE 0 END) AS anuladas,
                ROUND(SUM(CASE WHEN estado <> 'ANULADA' THEN IFNULL(importe_imputado, 0) ELSE 0 END), 2) AS importe_activo
            FROM bancos_conciliaciones
            WHERE empresa_id = ?
              AND tipo_conciliacion = 'TESORERIA_OPERACION'
            """,
            conn,
            params=(empresa_id,),
        )

        return {
            "bancos": bancos.iloc[0].to_dict() if not bancos.empty else {},
            "tesoreria": tesoreria.iloc[0].to_dict() if not tesoreria.empty else {},
            "conciliaciones": conciliaciones.iloc[0].to_dict() if not conciliaciones.empty else {},
        }

    finally:
        conn.close()


def obtener_movimientos_bancarios_pendientes(
    empresa_id=1,
    banco=None,
    fecha_desde=None,
    fecha_hasta=None,
    solo_con_pendiente=True,
):
    inicializar_conciliacion()
    conn = conectar()

    try:
        filtros = ["empresa_id = ?"]
        params = [empresa_id]

        if solo_con_pendiente:
            filtros.append("estado_conciliacion IN ('PENDIENTE', 'PARCIAL')")
            filtros.append("ABS(IFNULL(importe_pendiente, ABS(importe))) > 0.01")

        if banco:
            filtros.append("banco = ?")
            params.append(banco)

        if fecha_desde:
            filtros.append("fecha >= ?")
            params.append(fecha_desde)

        if fecha_hasta:
            filtros.append("fecha <= ?")
            params.append(fecha_hasta)

        where_sql = " AND ".join(filtros)

        return pd.read_sql_query(
            f"""
            SELECT
                id,
                empresa_id,
                importacion_id,
                banco,
                nombre_cuenta,
                fecha,
                anio,
                mes,
                referencia,
                causal,
                concepto,
                importe,
                debito,
                credito,
                saldo,
                importe_conciliado,
                importe_pendiente,
                porcentaje_conciliado,
                tipo_movimiento_sugerido,
                confianza_sugerencia,
                motivo_sugerencia,
                estado_conciliacion,
                estado_contable,
                archivo,
                fecha_carga
            FROM bancos_movimientos
            WHERE {where_sql}
            ORDER BY fecha, id
            """,
            conn,
            params=tuple(params),
        )

    finally:
        conn.close()


def obtener_operaciones_tesoreria_pendientes(
    empresa_id=1,
    tipo_cuenta=None,
    fecha_desde=None,
    fecha_hasta=None,
    solo_con_pendiente=True,
):
    inicializar_conciliacion()
    conn = conectar()

    try:
        filtros = [
            "o.empresa_id = ?",
            "o.estado <> 'ANULADA'",
        ]
        params = [empresa_id]

        if solo_con_pendiente:
            filtros.append("o.estado_conciliacion IN ('PENDIENTE', 'SUGERIDA', 'PARCIAL')")
            filtros.append("ABS(IFNULL(o.importe_pendiente, ABS(o.importe))) > 0.01")

        if tipo_cuenta:
            filtros.append("IFNULL(c.tipo_cuenta, '') = ?")
            params.append(tipo_cuenta)

        if fecha_desde:
            filtros.append("o.fecha_operacion >= ?")
            params.append(fecha_desde)

        if fecha_hasta:
            filtros.append("o.fecha_operacion <= ?")
            params.append(fecha_hasta)

        where_sql = " AND ".join(filtros)

        return pd.read_sql_query(
            f"""
            SELECT
                o.id,
                o.empresa_id,
                o.tipo_operacion,
                o.subtipo,
                o.fecha_operacion,
                o.fecha_contable,
                o.cuenta_tesoreria_id,
                c.tipo_cuenta,
                c.nombre AS cuenta_tesoreria,
                c.entidad AS entidad_cuenta,
                c.numero_cuenta,
                o.medio_pago_id,
                mp.codigo AS medio_pago_codigo,
                mp.nombre AS medio_pago,
                o.tercero_tipo,
                o.tercero_id,
                o.tercero_nombre,
                o.tercero_cuit,
                o.descripcion,
                o.referencia_externa,
                o.importe,
                o.moneda,
                o.estado,
                o.estado_conciliacion,
                o.importe_conciliado,
                o.importe_pendiente,
                o.origen_modulo,
                o.origen_tabla,
                o.origen_id,
                o.fecha_creacion
            FROM tesoreria_operaciones o
            LEFT JOIN tesoreria_cuentas c
                   ON c.empresa_id = o.empresa_id
                  AND c.id = o.cuenta_tesoreria_id
            LEFT JOIN tesoreria_medios_pago mp
                   ON mp.empresa_id = o.empresa_id
                  AND mp.id = o.medio_pago_id
            WHERE {where_sql}
            ORDER BY o.fecha_operacion, o.id
            """,
            conn,
            params=tuple(params),
        )

    finally:
        conn.close()


def obtener_conciliaciones_tesoreria(empresa_id=1, incluir_anuladas=False):
    inicializar_conciliacion()
    conn = conectar()

    try:
        filtro_estado = ""

        if not incluir_anuladas:
            filtro_estado = "AND c.estado <> 'ANULADA'"

        return pd.read_sql_query(
            f"""
            SELECT
                c.id AS conciliacion_id,
                c.fecha,
                c.estado,
                c.importe_total,
                c.importe_imputado,
                c.importe_pendiente,
                c.porcentaje_conciliado,
                c.observacion,
                c.usuario_id,
                c.fecha_creacion,
                c.fecha_confirmacion,
                m.id AS movimiento_banco_id,
                m.banco,
                m.nombre_cuenta,
                m.referencia,
                m.causal,
                m.concepto AS concepto_banco,
                m.importe AS importe_banco,
                m.estado_conciliacion AS estado_banco,
                d.id AS detalle_id,
                d.entidad_id AS operacion_tesoreria_id,
                d.tercero_nombre,
                d.tercero_cuit,
                d.comprobante,
                d.observacion AS observacion_detalle,
                o.tipo_operacion,
                o.fecha_operacion,
                o.descripcion AS descripcion_tesoreria,
                o.referencia_externa,
                o.importe AS importe_tesoreria,
                o.estado_conciliacion AS estado_tesoreria,
                o.origen_modulo,
                o.origen_tabla,
                o.origen_id
            FROM bancos_conciliaciones c
            LEFT JOIN bancos_movimientos m
                   ON m.empresa_id = c.empresa_id
                  AND m.id = c.movimiento_banco_id
            LEFT JOIN bancos_conciliaciones_detalle d
                   ON d.empresa_id = c.empresa_id
                  AND d.conciliacion_id = c.id
                  AND d.entidad_tabla = 'tesoreria_operaciones'
            LEFT JOIN tesoreria_operaciones o
                   ON o.empresa_id = c.empresa_id
                  AND o.id = d.entidad_id
            WHERE c.empresa_id = ?
              AND c.tipo_conciliacion = 'TESORERIA_OPERACION'
              {filtro_estado}
            ORDER BY c.fecha_confirmacion DESC, c.id DESC
            """,
            conn,
            params=(empresa_id,),
        )

    finally:
        conn.close()


# ======================================================
# SUGERENCIAS
# ======================================================

def _puntuar_sugerencia(movimiento, operacion, tolerancia_importe=1.0, dias_maximos=7):
    importe_banco = _numero(movimiento.get("importe"))
    importe_operacion = _numero(operacion.get("importe"))

    if _signo(importe_banco) == 0 or _signo(importe_operacion) == 0:
        return None

    if _signo(importe_banco) != _signo(importe_operacion):
        return None

    pendiente_banco = _numero(movimiento.get("importe_pendiente")) or abs(importe_banco)
    pendiente_operacion = _numero(operacion.get("importe_pendiente")) or abs(importe_operacion)
    diferencia_importe = abs(abs(pendiente_banco) - abs(pendiente_operacion))

    if diferencia_importe > float(tolerancia_importe):
        return None

    dias = _dias_entre(movimiento.get("fecha"), operacion.get("fecha_operacion"))

    if dias > int(dias_maximos):
        return None

    score = 0
    motivos = []

    score += 20
    motivos.append("mismo signo financiero")

    if diferencia_importe <= 0.01:
        score += 35
        motivos.append("importe exacto")
    elif diferencia_importe <= float(tolerancia_importe):
        score += 25
        motivos.append("importe dentro de tolerancia")

    if dias == 0:
        score += 20
        motivos.append("misma fecha")
    elif dias <= 1:
        score += 15
        motivos.append("fecha cercana hasta 1 día")
    elif dias <= 3:
        score += 10
        motivos.append("fecha cercana hasta 3 días")
    else:
        score += 5
        motivos.append("fecha dentro del rango")

    texto_banco = " ".join([
        _texto_upper(movimiento.get("concepto")),
        _texto_upper(movimiento.get("referencia")),
        _texto_upper(movimiento.get("causal")),
    ])

    texto_tesoreria = " ".join([
        _texto_upper(operacion.get("descripcion")),
        _texto_upper(operacion.get("referencia_externa")),
        _texto_upper(operacion.get("tercero_nombre")),
        _texto_upper(operacion.get("tercero_cuit")),
    ])

    referencia = _texto_upper(operacion.get("referencia_externa"))

    if referencia and referencia in texto_banco:
        score += 15
        motivos.append("referencia externa encontrada en banco")

    tokens_banco = {t for t in texto_banco.split() if len(t) >= 4}
    tokens_tesoreria = {t for t in texto_tesoreria.split() if len(t) >= 4}
    interseccion = tokens_banco.intersection(tokens_tesoreria)

    if interseccion:
        score += min(10, len(interseccion) * 2)
        motivos.append("coincidencia de texto/tercero")

    tipo_operacion = _texto_upper(operacion.get("tipo_operacion"))

    if importe_banco > 0 and tipo_operacion == "COBRANZA":
        score += 10
        motivos.append("crédito bancario contra cobranza")

    if importe_banco < 0 and tipo_operacion in {"PAGO", "IMPUESTO", "TRANSFERENCIA", "CAJA"}:
        score += 10
        motivos.append("débito bancario contra egreso de tesorería")

    score = min(score, 100)

    if score >= 85:
        confianza = "Alta"
    elif score >= 65:
        confianza = "Media"
    else:
        confianza = "Baja"

    return {
        "score": score,
        "confianza": confianza,
        "motivo": "; ".join(motivos),
        "diferencia_importe": round(diferencia_importe, 2),
        "diferencia_dias": dias,
        "importe_sugerido": round(min(abs(pendiente_banco), abs(pendiente_operacion)), 2),
    }


def generar_sugerencias_conciliacion(
    empresa_id=1,
    tolerancia_importe=1.0,
    dias_maximos=7,
    limite=200,
    confianza_minima="Media",
):
    inicializar_conciliacion()

    movimientos = obtener_movimientos_bancarios_pendientes(empresa_id=empresa_id)
    operaciones = obtener_operaciones_tesoreria_pendientes(empresa_id=empresa_id)

    if movimientos.empty or operaciones.empty:
        return pd.DataFrame()

    minimo_por_confianza = {
        "Alta": 85,
        "Media": 65,
        "Baja": 0,
    }.get(_texto(confianza_minima).title(), 65)

    sugerencias = []

    for _, mov in movimientos.iterrows():
        for _, ope in operaciones.iterrows():
            puntaje = _puntuar_sugerencia(
                mov,
                ope,
                tolerancia_importe=tolerancia_importe,
                dias_maximos=dias_maximos,
            )

            if puntaje is None:
                continue

            if int(puntaje["score"]) < minimo_por_confianza:
                continue

            sugerencias.append({
                "movimiento_banco_id": int(mov["id"]),
                "operacion_tesoreria_id": int(ope["id"]),
                "score": int(puntaje["score"]),
                "confianza": puntaje["confianza"],
                "motivo": puntaje["motivo"],
                "diferencia_importe": puntaje["diferencia_importe"],
                "diferencia_dias": puntaje["diferencia_dias"],
                "importe_sugerido": puntaje["importe_sugerido"],
                "fecha_banco": mov.get("fecha"),
                "banco": mov.get("banco"),
                "cuenta_banco": mov.get("nombre_cuenta"),
                "concepto_banco": mov.get("concepto"),
                "referencia_banco": mov.get("referencia"),
                "importe_banco": _numero(mov.get("importe")),
                "pendiente_banco": _numero(mov.get("importe_pendiente")),
                "fecha_tesoreria": ope.get("fecha_operacion"),
                "tipo_operacion": ope.get("tipo_operacion"),
                "cuenta_tesoreria": ope.get("cuenta_tesoreria"),
                "medio_pago": ope.get("medio_pago"),
                "tercero_nombre": ope.get("tercero_nombre"),
                "tercero_cuit": ope.get("tercero_cuit"),
                "descripcion_tesoreria": ope.get("descripcion"),
                "referencia_externa": ope.get("referencia_externa"),
                "importe_tesoreria": _numero(ope.get("importe")),
                "pendiente_tesoreria": _numero(ope.get("importe_pendiente")),
                "origen_modulo": ope.get("origen_modulo"),
                "origen_tabla": ope.get("origen_tabla"),
                "origen_id": ope.get("origen_id"),
            })

    df = pd.DataFrame(sugerencias)

    if df.empty:
        return df

    df = df.sort_values(
        by=["score", "diferencia_importe", "diferencia_dias"],
        ascending=[False, True, True],
    ).head(int(limite))

    return df.reset_index(drop=True)


# ======================================================
# CONFIRMACIÓN Y DESCONCILIACIÓN
# ======================================================

def confirmar_conciliacion_tesoreria(
    empresa_id,
    movimiento_banco_id,
    operacion_tesoreria_id,
    importe_conciliar=None,
    usuario_id=None,
    observacion="",
):
    inicializar_conciliacion()

    empresa_id = int(empresa_id or 1)
    movimiento_banco_id = int(movimiento_banco_id)
    operacion_tesoreria_id = int(operacion_tesoreria_id)
    observacion = _texto(observacion) or "Conciliación de movimiento bancario contra operación de Tesorería."

    conn = conectar()
    cur = conn.cursor()

    try:
        movimiento = _obtener_movimiento_banco(cur, empresa_id, movimiento_banco_id)
        operacion = _obtener_operacion_tesoreria(cur, empresa_id, operacion_tesoreria_id)

        if movimiento is None:
            return {"ok": False, "mensaje": "No se encontró el movimiento bancario."}

        if operacion is None:
            return {"ok": False, "mensaje": "No se encontró la operación de Tesorería."}

        if _texto_upper(operacion.get("estado")) == "ANULADA":
            return {"ok": False, "mensaje": "No se puede conciliar una operación de Tesorería anulada."}

        if _signo(movimiento.get("importe")) != _signo(operacion.get("importe")):
            return {
                "ok": False,
                "mensaje": (
                    "El signo financiero no coincide: un crédito bancario debe conciliarse "
                    "con una cobranza/ingreso y un débito con un pago/egreso."
                ),
            }

        pendiente_banco = _numero(movimiento.get("importe_pendiente"))
        pendiente_tesoreria = _numero(operacion.get("importe_pendiente"))

        if pendiente_banco <= 0:
            pendiente_banco = abs(_numero(movimiento.get("importe")))

        if pendiente_tesoreria <= 0:
            pendiente_tesoreria = abs(_numero(operacion.get("importe")))

        if importe_conciliar is None:
            importe = min(pendiente_banco, pendiente_tesoreria)
        else:
            importe = abs(_numero(importe_conciliar))

        if importe <= 0:
            return {"ok": False, "mensaje": "El importe a conciliar debe ser mayor a cero."}

        if importe - pendiente_banco > 0.01:
            return {"ok": False, "mensaje": "El importe supera el pendiente del movimiento bancario."}

        if importe - pendiente_tesoreria > 0.01:
            return {"ok": False, "mensaje": "El importe supera el pendiente de la operación de Tesorería."}

        importe_total_banco = abs(_numero(movimiento.get("importe")))
        banco_conciliado_nuevo = round(abs(_numero(movimiento.get("importe_conciliado"))) + importe, 2)
        banco_pendiente_nuevo = max(round(importe_total_banco - banco_conciliado_nuevo, 2), 0.0)

        if importe_total_banco > 0:
            banco_porcentaje = round((banco_conciliado_nuevo / importe_total_banco) * 100, 2)
        else:
            banco_porcentaje = 0.0

        estado_conciliacion = "CONFIRMADA" if banco_pendiente_nuevo <= 0.01 else "PARCIAL"

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
            VALUES (?, ?, ?, 'TESORERIA_OPERACION', ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                empresa_id,
                movimiento_banco_id,
                movimiento.get("fecha"),
                estado_conciliacion,
                importe_total_banco,
                importe,
                banco_pendiente_nuevo,
                banco_porcentaje,
                observacion,
                usuario_id,
            ),
        )

        conciliacion_id = int(cur.lastrowid)

        saldo_anterior_tesoreria = pendiente_tesoreria
        saldo_posterior_tesoreria = max(round(pendiente_tesoreria - importe, 2), 0.0)

        comprobante = _texto(operacion.get("referencia_externa"))

        if not comprobante:
            comprobante = f"TESORERIA {operacion_tesoreria_id}"

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
            VALUES (?, ?, ?, 'TESORERIA_OPERACION', 'tesoreria_operaciones', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conciliacion_id,
                empresa_id,
                movimiento_banco_id,
                operacion_tesoreria_id,
                _texto(operacion.get("tercero_nombre")),
                _texto(operacion.get("tercero_cuit")),
                comprobante,
                "",
                _texto(operacion.get("descripcion")),
                importe,
                saldo_anterior_tesoreria,
                saldo_posterior_tesoreria,
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
            (importe, empresa_id, movimiento_banco_id),
        )

        cur.execute(
            """
            UPDATE tesoreria_operaciones
            SET importe_conciliado = ROUND(IFNULL(importe_conciliado, 0) + ?, 2)
            WHERE empresa_id = ?
              AND id = ?
            """,
            (importe, empresa_id, operacion_tesoreria_id),
        )

        _actualizar_estado_banco(cur, empresa_id, movimiento_banco_id)
        _actualizar_estado_tesoreria(cur, empresa_id, operacion_tesoreria_id)

        _registrar_tesoreria_auditoria(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CONCILIAR",
            entidad="tesoreria_operaciones",
            entidad_id=operacion_tesoreria_id,
            valor_anterior=operacion,
            valor_nuevo={
                "conciliacion_id": conciliacion_id,
                "movimiento_banco_id": movimiento_banco_id,
                "importe_conciliado": importe,
            },
            motivo=observacion,
        )

        conn.commit()

        _registrar_auditoria_seguridad(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            accion="Confirmar conciliación Tesorería/Banco",
            entidad="bancos_conciliaciones",
            entidad_id=conciliacion_id,
            valor_anterior={"movimiento": movimiento, "operacion": operacion},
            valor_nuevo={
                "conciliacion_id": conciliacion_id,
                "movimiento_banco_id": movimiento_banco_id,
                "operacion_tesoreria_id": operacion_tesoreria_id,
                "importe": importe,
            },
            motivo=observacion,
        )

        return {
            "ok": True,
            "mensaje": "Conciliación confirmada correctamente.",
            "conciliacion_id": conciliacion_id,
            "movimiento_banco_id": movimiento_banco_id,
            "operacion_tesoreria_id": operacion_tesoreria_id,
            "importe_conciliado": importe,
        }

    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo confirmar la conciliación: {e}"}

    finally:
        conn.close()


def desconciliar_conciliacion_tesoreria(
    conciliacion_id,
    empresa_id=1,
    usuario_id=None,
    motivo="",
):
    inicializar_conciliacion()

    empresa_id = int(empresa_id or 1)
    conciliacion_id = int(conciliacion_id)
    motivo = _texto(motivo)

    if not motivo:
        return {"ok": False, "mensaje": "Para desconciliar se debe indicar un motivo."}

    conn = conectar()
    cur = conn.cursor()

    try:
        conciliacion = _obtener_conciliacion(cur, empresa_id, conciliacion_id)

        if conciliacion is None:
            return {"ok": False, "mensaje": "No se encontró la conciliación indicada."}

        if _texto_upper(conciliacion.get("tipo_conciliacion")) != "TESORERIA_OPERACION":
            return {
                "ok": False,
                "mensaje": (
                    "Esta opción solo desconcilia vínculos Banco/Tesorería. "
                    "Para imputaciones de clientes, proveedores o fiscales usá la desimputación de Banco."
                ),
            }

        if _texto_upper(conciliacion.get("estado")) == "ANULADA":
            return {
                "ok": True,
                "mensaje": "La conciliación ya estaba anulada.",
                "anulada": False,
            }

        detalle = _obtener_fila(
            cur,
            """
            SELECT *
            FROM bancos_conciliaciones_detalle
            WHERE empresa_id = ?
              AND conciliacion_id = ?
              AND entidad_tabla = 'tesoreria_operaciones'
            ORDER BY id
            LIMIT 1
            """,
            (empresa_id, conciliacion_id),
        )

        if detalle is None:
            return {"ok": False, "mensaje": "La conciliación no tiene detalle de operación de Tesorería."}

        movimiento_banco_id = int(conciliacion["movimiento_banco_id"])
        operacion_tesoreria_id = int(detalle["entidad_id"])
        importe = abs(_numero(conciliacion.get("importe_imputado")))

        movimiento = _obtener_movimiento_banco(cur, empresa_id, movimiento_banco_id)
        operacion = _obtener_operacion_tesoreria(cur, empresa_id, operacion_tesoreria_id)

        cur.execute(
            """
            UPDATE bancos_movimientos
            SET importe_conciliado = MAX(ROUND(IFNULL(importe_conciliado, 0) - ?, 2), 0)
            WHERE empresa_id = ?
              AND id = ?
            """,
            (importe, empresa_id, movimiento_banco_id),
        )

        cur.execute(
            """
            UPDATE tesoreria_operaciones
            SET importe_conciliado = MAX(ROUND(IFNULL(importe_conciliado, 0) - ?, 2), 0)
            WHERE empresa_id = ?
              AND id = ?
            """,
            (importe, empresa_id, operacion_tesoreria_id),
        )

        _actualizar_estado_banco(cur, empresa_id, movimiento_banco_id)
        _actualizar_estado_tesoreria(cur, empresa_id, operacion_tesoreria_id)

        observacion_anulada = (
            f"{_texto(conciliacion.get('observacion'))}\n"
            f"DESCONCILIADA {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Motivo: {motivo}"
        ).strip()

        cur.execute(
            """
            UPDATE bancos_conciliaciones
            SET estado = 'ANULADA',
                observacion = ?
            WHERE empresa_id = ?
              AND id = ?
            """,
            (observacion_anulada, empresa_id, conciliacion_id),
        )

        _registrar_tesoreria_auditoria(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="DESCONCILIAR",
            entidad="tesoreria_operaciones",
            entidad_id=operacion_tesoreria_id,
            valor_anterior={
                "conciliacion": conciliacion,
                "detalle": detalle,
                "movimiento": movimiento,
                "operacion": operacion,
            },
            valor_nuevo={
                "conciliacion_id": conciliacion_id,
                "importe_revertido": importe,
                "estado_conciliacion": "ANULADA",
            },
            motivo=motivo,
        )

        conn.commit()

        _registrar_auditoria_seguridad(
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            accion="Desconciliar Tesorería/Banco",
            entidad="bancos_conciliaciones",
            entidad_id=conciliacion_id,
            valor_anterior={"conciliacion": conciliacion, "detalle": detalle},
            valor_nuevo={"estado": "ANULADA", "importe_revertido": importe},
            motivo=motivo,
        )

        return {
            "ok": True,
            "mensaje": "Conciliación desconciliada correctamente.",
            "anulada": True,
            "conciliacion_id": conciliacion_id,
            "movimiento_banco_id": movimiento_banco_id,
            "operacion_tesoreria_id": operacion_tesoreria_id,
            "importe_revertido": importe,
        }

    except Exception as e:
        conn.rollback()
        return {"ok": False, "mensaje": f"No se pudo desconciliar: {e}"}

    finally:
        conn.close()