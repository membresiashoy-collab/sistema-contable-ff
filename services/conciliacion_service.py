import json
import re
import unicodedata
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
# SUGERENCIAS Y CONCILIACIÓN AUTOMÁTICA SEGURA
# ======================================================

PALABRAS_RUIDO_CONCILIACION = {
    "TRANSFERENCIA", "TRANSF", "TRF", "PAGO", "PAGOS", "COBRO", "COBROS",
    "DEBITO", "DÉBITO", "CREDITO", "CRÉDITO", "ACREDITACION", "ACREDITACIÓN",
    "BANCO", "CUENTA", "CTA", "CBU", "CVU", "ALIAS", "ARS", "PESOS",
    "COMISION", "COMISIÓN", "IMP", "IMPUESTO", "IVA", "IIBB", "RET", "RETENCION",
    "RETENCIÓN", "SUC", "SUCURSAL", "ONLINE", "HOME", "BANKING", "INTERBANKING",
}


def _normalizar_texto_busqueda(valor):
    texto = _texto_upper(valor)

    if not texto:
        return ""

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _tokens_utiles(valor, largo_minimo=4):
    texto = _normalizar_texto_busqueda(valor)

    if not texto:
        return set()

    tokens = set()

    for token in texto.split():
        if len(token) < int(largo_minimo):
            continue

        if token in PALABRAS_RUIDO_CONCILIACION:
            continue

        tokens.add(token)

    return tokens


def _referencias_utiles(*valores):
    referencias = set()

    for valor in valores:
        texto = _normalizar_texto_busqueda(valor)

        if not texto:
            continue

        for token in texto.split():
            if len(token) >= 5 and any(c.isdigit() for c in token):
                referencias.add(token)

        compacto = re.sub(r"[^A-Z0-9]", "", texto)

        if len(compacto) >= 6 and any(c.isdigit() for c in compacto):
            referencias.add(compacto)

    return referencias


def _texto_banco_para_match(movimiento):
    return " ".join([
        _normalizar_texto_busqueda(movimiento.get("referencia")),
        _normalizar_texto_busqueda(movimiento.get("concepto")),
        _normalizar_texto_busqueda(movimiento.get("causal")),
        _normalizar_texto_busqueda(movimiento.get("banco")),
        _normalizar_texto_busqueda(movimiento.get("nombre_cuenta")),
    ]).strip()


def _texto_tesoreria_para_match(operacion):
    return " ".join([
        _normalizar_texto_busqueda(operacion.get("referencia_externa")),
        _normalizar_texto_busqueda(operacion.get("descripcion")),
        _normalizar_texto_busqueda(operacion.get("tercero_nombre")),
        _normalizar_texto_busqueda(operacion.get("tercero_cuit")),
        _normalizar_texto_busqueda(operacion.get("medio_pago")),
        _normalizar_texto_busqueda(operacion.get("cuenta_tesoreria")),
    ]).strip()


def _coincidencia_referencias(movimiento, operacion):
    refs_banco = _referencias_utiles(
        movimiento.get("referencia"),
        movimiento.get("concepto"),
        movimiento.get("causal"),
    )
    refs_tesoreria = _referencias_utiles(
        operacion.get("referencia_externa"),
        operacion.get("descripcion"),
        operacion.get("tercero_cuit"),
    )

    if not refs_banco or not refs_tesoreria:
        return {
            "score": 0,
            "motivo": "",
            "referencias_banco": sorted(refs_banco),
            "referencias_tesoreria": sorted(refs_tesoreria),
            "referencias_comunes": [],
        }

    comunes = set()

    for ref_banco in refs_banco:
        for ref_tesoreria in refs_tesoreria:
            if ref_banco == ref_tesoreria:
                comunes.add(ref_banco)
            elif len(ref_banco) >= 8 and len(ref_tesoreria) >= 8:
                if ref_banco in ref_tesoreria or ref_tesoreria in ref_banco:
                    comunes.add(ref_banco if len(ref_banco) <= len(ref_tesoreria) else ref_tesoreria)

    if not comunes:
        return {
            "score": 0,
            "motivo": "",
            "referencias_banco": sorted(refs_banco),
            "referencias_tesoreria": sorted(refs_tesoreria),
            "referencias_comunes": [],
        }

    return {
        "score": 30,
        "motivo": "referencia bancaria/externa coincidente",
        "referencias_banco": sorted(refs_banco),
        "referencias_tesoreria": sorted(refs_tesoreria),
        "referencias_comunes": sorted(comunes),
    }


def _coincidencia_texto(movimiento, operacion):
    texto_banco = _texto_banco_para_match(movimiento)
    texto_tesoreria = _texto_tesoreria_para_match(operacion)

    tokens_banco = _tokens_utiles(texto_banco)
    tokens_tesoreria = _tokens_utiles(texto_tesoreria)
    comunes = tokens_banco.intersection(tokens_tesoreria)

    score = 0
    motivos = []

    if comunes:
        score += min(18, len(comunes) * 4)
        motivos.append("coincidencia de concepto/tercero")

    tercero_cuit = re.sub(r"\D+", "", _texto(operacion.get("tercero_cuit")))
    texto_banco_digitos = re.sub(r"\D+", "", _texto_banco_para_match(movimiento))

    if tercero_cuit and len(tercero_cuit) >= 8 and tercero_cuit in texto_banco_digitos:
        score += 16
        motivos.append("CUIT del tercero encontrado en movimiento bancario")

    tercero_nombre_tokens = _tokens_utiles(operacion.get("tercero_nombre"), largo_minimo=5)

    if tercero_nombre_tokens and tercero_nombre_tokens.intersection(tokens_banco):
        score += 10
        motivos.append("nombre del tercero encontrado en banco")

    return {
        "score": min(score, 28),
        "motivo": "; ".join(motivos),
        "tokens_comunes": sorted(comunes),
    }


def _coincidencia_tipo_operacion(movimiento, operacion):
    importe_banco = _numero(movimiento.get("importe"))
    tipo_operacion = _texto_upper(operacion.get("tipo_operacion"))
    subtipo = _texto_upper(operacion.get("subtipo"))
    origen_modulo = _texto_upper(operacion.get("origen_modulo"))

    if importe_banco > 0 and tipo_operacion in {"COBRANZA", "INGRESO"}:
        return {"score": 8, "motivo": "crédito bancario contra cobranza/ingreso"}

    if importe_banco < 0 and tipo_operacion in {"PAGO", "EGRESO", "IMPUESTO", "TRANSFERENCIA"}:
        return {"score": 8, "motivo": "débito bancario contra egreso/pago"}

    if importe_banco < 0 and ("PAGO" in subtipo or "PAGO" in origen_modulo):
        return {"score": 6, "motivo": "débito bancario asociado a pago"}

    if importe_banco > 0 and ("COBRANZA" in subtipo or "COBRANZA" in origen_modulo):
        return {"score": 6, "motivo": "crédito bancario asociado a cobranza"}

    return {"score": 0, "motivo": ""}


def _clasificar_sugerencia(score, diferencia_importe, score_referencia, score_texto):
    if score >= 90 and diferencia_importe <= 0.01 and (score_referencia > 0 or score_texto >= 14):
        return "AUTOMATICA_SEGURA"

    if score >= 75:
        return "REVISION_ALTA"

    if score >= 60:
        return "REVISION_MEDIA"

    return "REVISION_BAJA"


def _puntuar_sugerencia(movimiento, operacion, tolerancia_importe=1.0, dias_maximos=None):
    """
    Puntúa una posible conciliación Banco/Tesorería.

    Regla funcional:
    - El importe pendiente y el signo financiero son condiciones duras.
    - La referencia bancaria, el concepto y el tercero elevan la confianza.
    - La fecha nunca bloquea: solo suma confianza si ayuda.
    - Las diferencias de fecha altas quedan explicadas para revisión asistida.
    """

    importe_banco = _numero(movimiento.get("importe"))
    importe_operacion = _numero(operacion.get("importe"))

    if _signo(importe_banco) == 0 or _signo(importe_operacion) == 0:
        return None

    if _signo(importe_banco) != _signo(importe_operacion):
        return None

    pendiente_banco = _numero(movimiento.get("importe_pendiente"))
    pendiente_operacion = _numero(operacion.get("importe_pendiente"))

    if pendiente_banco <= 0:
        pendiente_banco = abs(importe_banco)

    if pendiente_operacion <= 0:
        pendiente_operacion = abs(importe_operacion)

    diferencia_importe = abs(abs(pendiente_banco) - abs(pendiente_operacion))

    if diferencia_importe > float(tolerancia_importe):
        return None

    dias = _dias_entre(movimiento.get("fecha"), operacion.get("fecha_operacion"))

    score = 0
    motivos = []

    score += 18
    motivos.append("mismo signo financiero")

    if diferencia_importe <= 0.01:
        score += 34
        motivos.append("importe exacto pendiente")
    elif diferencia_importe <= 0.10:
        score += 28
        motivos.append("importe con diferencia mínima")
    elif diferencia_importe <= float(tolerancia_importe):
        score += 22
        motivos.append("importe dentro de tolerancia")

    referencia = _coincidencia_referencias(movimiento, operacion)

    if referencia["score"]:
        score += referencia["score"]
        motivos.append(referencia["motivo"])

    texto = _coincidencia_texto(movimiento, operacion)

    if texto["score"]:
        score += texto["score"]
        motivos.append(texto["motivo"])

    tipo = _coincidencia_tipo_operacion(movimiento, operacion)

    if tipo["score"]:
        score += tipo["score"]
        motivos.append(tipo["motivo"])

    if dias == 0:
        score += 8
        motivos.append("misma fecha")
    elif dias <= 1:
        score += 6
        motivos.append("fecha cercana hasta 1 día")
    elif dias <= 3:
        score += 4
        motivos.append("fecha cercana hasta 3 días")
    elif dias <= 7:
        score += 2
        motivos.append("fecha cercana hasta 7 días")
    else:
        motivos.append(f"fecha distante: {dias} días; no bloquea, solo baja confianza")

    score = min(int(score), 100)
    clasificacion = _clasificar_sugerencia(
        score=score,
        diferencia_importe=diferencia_importe,
        score_referencia=int(referencia["score"]),
        score_texto=int(texto["score"]),
    )

    if score >= 85:
        confianza = "Alta"
    elif score >= 65:
        confianza = "Media"
    else:
        confianza = "Baja"

    return {
        "score": score,
        "confianza": confianza,
        "clasificacion": clasificacion,
        "motivo": "; ".join(m for m in motivos if m),
        "diferencia_importe": round(diferencia_importe, 2),
        "diferencia_dias": dias,
        "importe_sugerido": round(min(abs(pendiente_banco), abs(pendiente_operacion)), 2),
        "referencias_comunes": referencia.get("referencias_comunes", []),
        "tokens_comunes": texto.get("tokens_comunes", []),
        "score_referencia": int(referencia["score"]),
        "score_texto": int(texto["score"]),
    }


def _marcar_ambiguedades_sugerencias(df):
    if df.empty:
        return df

    df = df.copy()

    df["cantidad_candidatos_movimiento"] = df.groupby("movimiento_banco_id")["operacion_tesoreria_id"].transform("count")
    df["cantidad_candidatos_operacion"] = df.groupby("operacion_tesoreria_id")["movimiento_banco_id"].transform("count")
    df["mejor_score_movimiento"] = df.groupby("movimiento_banco_id")["score"].transform("max")
    df["mejor_score_operacion"] = df.groupby("operacion_tesoreria_id")["score"].transform("max")

    segundos_movimiento = {}

    for movimiento_id, grupo in df.groupby("movimiento_banco_id"):
        scores = sorted(grupo["score"].astype(int).tolist(), reverse=True)
        segundos_movimiento[movimiento_id] = scores[1] if len(scores) > 1 else None

    segundos_operacion = {}

    for operacion_id, grupo in df.groupby("operacion_tesoreria_id"):
        scores = sorted(grupo["score"].astype(int).tolist(), reverse=True)
        segundos_operacion[operacion_id] = scores[1] if len(scores) > 1 else None

    df["segundo_score_movimiento"] = df["movimiento_banco_id"].map(segundos_movimiento)
    df["segundo_score_operacion"] = df["operacion_tesoreria_id"].map(segundos_operacion)

    def _resolver_fila(row):
        score = int(row.get("score") or 0)
        clasificacion = _texto_upper(row.get("clasificacion"))
        segundo_mov = row.get("segundo_score_movimiento")
        segundo_ope = row.get("segundo_score_operacion")

        margen_mov = 999 if pd.isna(segundo_mov) or segundo_mov is None else score - int(segundo_mov)
        margen_ope = 999 if pd.isna(segundo_ope) or segundo_ope is None else score - int(segundo_ope)

        unica_movimiento = int(row.get("cantidad_candidatos_movimiento") or 0) == 1 or margen_mov >= 10
        unica_operacion = int(row.get("cantidad_candidatos_operacion") or 0) == 1 or margen_ope >= 10
        es_auto = clasificacion == "AUTOMATICA_SEGURA" and unica_movimiento and unica_operacion

        if es_auto:
            accion = "CONCILIAR_AUTOMATICAMENTE"
            ambigua = False
            motivo_control = "coincidencia única y fuerte"
        else:
            accion = "REVISION_ASISTIDA"
            ambigua = not (unica_movimiento and unica_operacion)

            if ambigua:
                motivo_control = "hay más de un candidato posible para el movimiento u operación"
            elif clasificacion == "AUTOMATICA_SEGURA":
                motivo_control = "coincidencia fuerte, pero requiere revisión por control de unicidad"
            else:
                motivo_control = "confianza insuficiente para conciliación automática"

        return pd.Series({
            "es_candidato_auto": bool(es_auto),
            "ambigua": bool(ambigua),
            "accion_recomendada": accion,
            "motivo_control": motivo_control,
            "margen_score_movimiento": margen_mov,
            "margen_score_operacion": margen_ope,
        })

    controles = df.apply(_resolver_fila, axis=1)
    df = pd.concat([df, controles], axis=1)
    return df


def generar_sugerencias_conciliacion(
    empresa_id=1,
    tolerancia_importe=1.0,
    dias_maximos=None,
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
                "clasificacion": puntaje["clasificacion"],
                "motivo": puntaje["motivo"],
                "diferencia_importe": puntaje["diferencia_importe"],
                "diferencia_dias": puntaje["diferencia_dias"],
                "importe_sugerido": puntaje["importe_sugerido"],
                "score_referencia": puntaje["score_referencia"],
                "score_texto": puntaje["score_texto"],
                "referencias_comunes": ", ".join(puntaje.get("referencias_comunes") or []),
                "tokens_comunes": ", ".join(puntaje.get("tokens_comunes") or []),
                "fecha_banco": mov.get("fecha"),
                "banco": mov.get("banco"),
                "cuenta_banco": mov.get("nombre_cuenta"),
                "concepto_banco": mov.get("concepto"),
                "referencia_banco": mov.get("referencia"),
                "causal_banco": mov.get("causal"),
                "importe_banco": _numero(mov.get("importe")),
                "pendiente_banco": _numero(mov.get("importe_pendiente")),
                "fecha_tesoreria": ope.get("fecha_operacion"),
                "tipo_operacion": ope.get("tipo_operacion"),
                "subtipo": ope.get("subtipo"),
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

    df = _marcar_ambiguedades_sugerencias(df)

    df = df.sort_values(
        by=[
            "es_candidato_auto",
            "score",
            "diferencia_importe",
            "ambigua",
            "diferencia_dias",
        ],
        ascending=[False, False, True, True, True],
    ).head(int(limite))

    return df.reset_index(drop=True)


def ejecutar_conciliacion_automatica_segura(
    empresa_id=1,
    usuario_id=None,
    tolerancia_importe=0.01,
    score_minimo=90,
    limite=500,
):
    """
    Ejecuta conciliaciones automáticas solo cuando el candidato es único y fuerte.

    Seguridad aplicada:
    - Importe pendiente igual dentro de tolerancia estricta.
    - Signo financiero coincidente.
    - Score mínimo alto.
    - Referencia/concepto/tercero deben sostener la coincidencia.
    - Si un banco u operación tiene más de un candidato competitivo, pasa a revisión asistida.
    """

    sugerencias = generar_sugerencias_conciliacion(
        empresa_id=empresa_id,
        tolerancia_importe=tolerancia_importe,
        dias_maximos=None,
        limite=limite,
        confianza_minima="Media",
    )

    resultado = {
        "ok": True,
        "mensaje": "Conciliación automática segura finalizada.",
        "conciliadas": 0,
        "revision_asistida": 0,
        "errores": 0,
        "detalle_conciliadas": [],
        "detalle_revision": [],
        "detalle_errores": [],
    }

    if sugerencias.empty:
        resultado["mensaje"] = "No se encontraron candidatos para conciliación automática."
        return resultado

    usadas_movimientos = set()
    usadas_operaciones = set()

    candidatas = sugerencias[
        (sugerencias["es_candidato_auto"] == True)  # noqa: E712
        & (sugerencias["score"].astype(int) >= int(score_minimo))
        & (sugerencias["diferencia_importe"].astype(float) <= float(tolerancia_importe))
    ].copy()

    candidatas = candidatas.sort_values(
        by=["score", "diferencia_importe", "diferencia_dias"],
        ascending=[False, True, True],
    )

    for _, fila in candidatas.iterrows():
        movimiento_banco_id = int(fila["movimiento_banco_id"])
        operacion_tesoreria_id = int(fila["operacion_tesoreria_id"])

        if movimiento_banco_id in usadas_movimientos or operacion_tesoreria_id in usadas_operaciones:
            resultado["revision_asistida"] += 1
            resultado["detalle_revision"].append({
                "movimiento_banco_id": movimiento_banco_id,
                "operacion_tesoreria_id": operacion_tesoreria_id,
                "score": int(fila["score"]),
                "motivo": "candidato fuerte omitido porque el movimiento u operación ya fue conciliado en esta corrida",
            })
            continue

        observacion = (
            "Conciliación automática segura Banco/Tesorería. "
            f"Score {int(fila['score'])}. "
            f"Motivo: {_texto(fila.get('motivo'))}. "
            "La fecha no fue condición bloqueante; solo sumó confianza si correspondía."
        )

        confirmar = confirmar_conciliacion_tesoreria(
            empresa_id=empresa_id,
            movimiento_banco_id=movimiento_banco_id,
            operacion_tesoreria_id=operacion_tesoreria_id,
            importe_conciliar=float(fila["importe_sugerido"]),
            usuario_id=usuario_id,
            observacion=observacion,
        )

        if confirmar.get("ok"):
            usadas_movimientos.add(movimiento_banco_id)
            usadas_operaciones.add(operacion_tesoreria_id)
            resultado["conciliadas"] += 1
            resultado["detalle_conciliadas"].append({
                "conciliacion_id": confirmar.get("conciliacion_id"),
                "movimiento_banco_id": movimiento_banco_id,
                "operacion_tesoreria_id": operacion_tesoreria_id,
                "importe_conciliado": confirmar.get("importe_conciliado"),
                "score": int(fila["score"]),
                "motivo": _texto(fila.get("motivo")),
            })
        else:
            resultado["errores"] += 1
            resultado["detalle_errores"].append({
                "movimiento_banco_id": movimiento_banco_id,
                "operacion_tesoreria_id": operacion_tesoreria_id,
                "score": int(fila["score"]),
                "mensaje": confirmar.get("mensaje"),
            })

    movimientos_auto = set(candidatas["movimiento_banco_id"].astype(int).tolist()) if not candidatas.empty else set()
    operaciones_auto = set(candidatas["operacion_tesoreria_id"].astype(int).tolist()) if not candidatas.empty else set()

    revision = sugerencias[
        ~(
            sugerencias["movimiento_banco_id"].astype(int).isin(movimientos_auto)
            & sugerencias["operacion_tesoreria_id"].astype(int).isin(operaciones_auto)
            & (sugerencias["es_candidato_auto"] == True)  # noqa: E712
        )
    ].copy()

    resultado["revision_asistida"] += int(len(revision))

    for _, fila in revision.head(100).iterrows():
        resultado["detalle_revision"].append({
            "movimiento_banco_id": int(fila["movimiento_banco_id"]),
            "operacion_tesoreria_id": int(fila["operacion_tesoreria_id"]),
            "score": int(fila["score"]),
            "confianza": fila.get("confianza"),
            "clasificacion": fila.get("clasificacion"),
            "accion_recomendada": fila.get("accion_recomendada"),
            "motivo_control": fila.get("motivo_control"),
            "motivo": fila.get("motivo"),
        })

    if resultado["errores"]:
        resultado["ok"] = False
        resultado["mensaje"] = "Conciliación automática segura finalizada con errores parciales."

    return resultado


# Compatibilidad semántica para llamadas desde UI/tests futuros.
def conciliar_automaticamente_seguro(*args, **kwargs):
    return ejecutar_conciliacion_automatica_segura(*args, **kwargs)

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