import hashlib
import json
from pathlib import Path

import pandas as pd

from database import conectar


def ejecutar_query(sql, params=()):
    """
    Helper local de Caja para consultas SELECT.

    En el proyecto, database.ejecutar_query puede devolver un cursor sqlite.
    Este módulo necesita DataFrames porque la UI y los resúmenes usan .empty,
    .iterrows(), columnas y sumatorias de pandas.
    """
    conn = conectar()

    try:
        return pd.read_sql_query(sql, conn, params=params)

    finally:
        conn.close()

from services.tesoreria_service import (
    inicializar_tesoreria,
    crear_cuenta_tesoreria,
    listar_cuentas_tesoreria,
)


# ======================================================
# CONSTANTES
# ======================================================

TIPOS_MOVIMIENTO_CAJA = {
    "INGRESO_MANUAL",
    "EGRESO_MANUAL",
    "COBRANZA_EFECTIVO",
    "PAGO_EFECTIVO",
    "DEPOSITO_CAJA_BANCO",
    "RETIRO_BANCO_CAJA",
    "TRANSFERENCIA_CAJA_CAJA",
    "TRANSFERENCIA_CAJA_BANCO",
    "TRANSFERENCIA_BANCO_CAJA",
    "AJUSTE_ARQUEO_SOBRANTE",
    "AJUSTE_ARQUEO_FALTANTE",
}

ESTADOS_MOVIMIENTO_CAJA = {
    "CONFIRMADO",
    "ANULADO",
}

CUENTA_CAJA_DEFAULT = ("1.1.01.01", "Caja")
CUENTA_BANCO_DEFAULT = ("1.1.02.01", "Bancos")
CUENTA_INGRESOS_A_CLASIFICAR = ("4.9.99.01", "Ingresos a clasificar")
CUENTA_EGRESOS_A_CLASIFICAR = ("5.9.99.01", "Egresos a clasificar")
CUENTA_SOBRANTES_CAJA = ("4.9.02.01", "Sobrantes de caja")
CUENTA_FALTANTES_CAJA = ("5.9.02.01", "Faltantes de caja")


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


def _ruta_migracion_caja():
    return Path(__file__).resolve().parents[1] / "migrations" / "010_caja_mvp.sql"


def _ejecutar_script_sql(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la migración de Caja: {ruta}")

    sql = ruta.read_text(encoding="utf-8")

    conn = conectar()

    try:
        conn.executescript(sql)
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def _columnas_tabla(conn, tabla):
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({tabla})")
        filas = cur.fetchall()
        return [fila[1] for fila in filas]
    except Exception:
        return []


def _tabla_tiene_columna(conn, tabla, columna):
    return columna in _columnas_tabla(conn, tabla)


def _insertar_dinamico(cur, tabla, datos):
    columnas_existentes = set(_columnas_tabla(cur.connection, tabla))
    datos_filtrados = {
        clave: valor
        for clave, valor in datos.items()
        if clave in columnas_existentes
    }

    if not datos_filtrados:
        raise RuntimeError(f"No hay columnas compatibles para insertar en {tabla}.")

    columnas = list(datos_filtrados.keys())
    placeholders = ", ".join(["?"] * len(columnas))
    columnas_sql = ", ".join(columnas)
    valores = [datos_filtrados[col] for col in columnas]

    cur.execute(
        f"""
        INSERT INTO {tabla}
        ({columnas_sql})
        VALUES ({placeholders})
        """,
        tuple(valores),
    )

    return int(cur.lastrowid)


def _actualizar_dinamico(cur, tabla, filtros, datos):
    columnas_existentes = set(_columnas_tabla(cur.connection, tabla))

    datos_filtrados = {
        clave: valor
        for clave, valor in datos.items()
        if clave in columnas_existentes
    }

    filtros_filtrados = {
        clave: valor
        for clave, valor in filtros.items()
        if clave in columnas_existentes
    }

    if not datos_filtrados or not filtros_filtrados:
        return False

    set_sql = ", ".join([f"{columna} = ?" for columna in datos_filtrados.keys()])
    where_sql = " AND ".join([f"{columna} = ?" for columna in filtros_filtrados.keys()])
    valores = list(datos_filtrados.values()) + list(filtros_filtrados.values())

    cur.execute(
        f"""
        UPDATE {tabla}
        SET {set_sql}
        WHERE {where_sql}
        """,
        tuple(valores),
    )

    return True


def _hash_partes(*partes):
    base = "|".join([_texto(p) for p in partes])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _registrar_auditoria_caja(
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
    cur.execute(
        """
        INSERT INTO caja_auditoria
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
            int(empresa_id or 1),
            usuario_id,
            _texto_upper(accion),
            _texto(entidad),
            _texto(entidad_id),
            _serializar(valor_anterior),
            _serializar(valor_nuevo),
            _texto(motivo),
        ),
    )


def _obtener_cuenta_tesoreria(cur, empresa_id, cuenta_id):
    cur.execute(
        """
        SELECT *
        FROM tesoreria_cuentas
        WHERE empresa_id = ?
          AND id = ?
        """,
        (int(empresa_id or 1), int(cuenta_id)),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _validar_tipo_movimiento(tipo_movimiento):
    tipo = _texto_upper(tipo_movimiento)

    if tipo not in TIPOS_MOVIMIENTO_CAJA:
        raise ValueError(
            f"Tipo de movimiento de caja inválido: {tipo_movimiento}. "
            f"Permitidos: {', '.join(sorted(TIPOS_MOVIMIENTO_CAJA))}"
        )

    return tipo


def _validar_importe_positivo(importe):
    importe_num = _numero(importe)

    if importe_num <= 0:
        raise ValueError("El importe debe ser mayor a cero.")

    return importe_num


def _cuenta_contable_desde_cuenta_tesoreria(cuenta, default):
    if not cuenta:
        return default

    codigo = _texto(cuenta.get("cuenta_contable_codigo"))
    nombre = _texto(cuenta.get("cuenta_contable_nombre"))

    if codigo and nombre:
        return codigo, nombre

    if nombre:
        return default[0], nombre

    return default


def _insertar_asiento_linea(
    cur,
    empresa_id,
    movimiento_caja_id,
    arqueo_id,
    fecha,
    cuenta_codigo,
    cuenta_nombre,
    debe,
    haber,
    glosa,
    estado="PROPUESTO",
):
    cur.execute(
        """
        INSERT INTO caja_asientos
        (
            empresa_id,
            movimiento_caja_id,
            arqueo_id,
            fecha,
            cuenta_codigo,
            cuenta_nombre,
            debe,
            haber,
            glosa,
            estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id or 1),
            movimiento_caja_id,
            arqueo_id,
            _texto(fecha),
            _texto(cuenta_codigo),
            _texto(cuenta_nombre),
            _numero(debe),
            _numero(haber),
            _texto(glosa),
            _texto_upper(estado or "PROPUESTO"),
        ),
    )


def _crear_asiento_doble(
    cur,
    empresa_id,
    movimiento_caja_id,
    arqueo_id,
    fecha,
    debe_cuenta,
    haber_cuenta,
    importe,
    glosa,
):
    importe = _validar_importe_positivo(importe)

    _insertar_asiento_linea(
        cur=cur,
        empresa_id=empresa_id,
        movimiento_caja_id=movimiento_caja_id,
        arqueo_id=arqueo_id,
        fecha=fecha,
        cuenta_codigo=debe_cuenta[0],
        cuenta_nombre=debe_cuenta[1],
        debe=importe,
        haber=0,
        glosa=glosa,
    )

    _insertar_asiento_linea(
        cur=cur,
        empresa_id=empresa_id,
        movimiento_caja_id=movimiento_caja_id,
        arqueo_id=arqueo_id,
        fecha=fecha,
        cuenta_codigo=haber_cuenta[0],
        cuenta_nombre=haber_cuenta[1],
        debe=0,
        haber=importe,
        glosa=glosa,
    )


def _insertar_tesoreria_operacion(
    cur,
    empresa_id,
    tipo_operacion,
    fecha,
    cuenta_tesoreria_id,
    importe,
    descripcion,
    referencia_externa,
    origen_tabla,
    origen_id,
    estado_conciliacion,
    usuario_id=None,
    observacion="",
):
    empresa_id = int(empresa_id or 1)
    cuenta_tesoreria_id = int(cuenta_tesoreria_id)
    importe = _numero(importe)

    fingerprint = _hash_partes(
        empresa_id,
        tipo_operacion,
        fecha,
        cuenta_tesoreria_id,
        importe,
        referencia_externa,
        "CAJA",
        origen_tabla,
        origen_id,
    )

    columnas = set(_columnas_tabla(cur.connection, "tesoreria_operaciones"))

    if "fingerprint" in columnas:
        cur.execute(
            """
            SELECT id
            FROM tesoreria_operaciones
            WHERE empresa_id = ?
              AND fingerprint = ?
            """,
            (empresa_id, fingerprint),
        )

        fila = cur.fetchone()

        if fila:
            return int(fila[0])

    datos = {
        "empresa_id": empresa_id,
        "tipo_operacion": _texto_upper(tipo_operacion),
        "fecha": _texto(fecha),
        "fecha_operacion": _texto(fecha),
        "cuenta_tesoreria_id": cuenta_tesoreria_id,
        "importe": importe,
        "descripcion": _texto(descripcion),
        "concepto": _texto(descripcion),
        "detalle": _texto(descripcion),
        "referencia_externa": _texto(referencia_externa),
        "origen_modulo": "CAJA",
        "origen_tabla": _texto(origen_tabla),
        "origen_id": origen_id,
        "estado": "CONFIRMADA",
        "estado_operacion": "CONFIRMADA",
        "estado_conciliacion": _texto_upper(estado_conciliacion),
        "fingerprint": fingerprint,
        "usuario_id": usuario_id,
        "observacion": _texto(observacion),
    }

    return _insertar_dinamico(cur, "tesoreria_operaciones", datos)


def _anular_tesoreria_operacion(cur, empresa_id, operacion_id, motivo):
    if not operacion_id:
        return

    columnas = set(_columnas_tabla(cur.connection, "tesoreria_operaciones"))

    if not columnas:
        return

    if "estado_conciliacion" in columnas:
        cur.execute(
            """
            SELECT estado_conciliacion
            FROM tesoreria_operaciones
            WHERE empresa_id = ?
              AND id = ?
            """,
            (int(empresa_id or 1), int(operacion_id)),
        )

        fila = cur.fetchone()

        if fila and _texto_upper(fila[0]) in {"CONCILIADA", "PARCIAL"}:
            raise ValueError(
                "No se puede anular una operación de Caja con operación de Tesorería "
                "ya conciliada o parcialmente conciliada."
            )

    _actualizar_dinamico(
        cur,
        "tesoreria_operaciones",
        filtros={
            "empresa_id": int(empresa_id or 1),
            "id": int(operacion_id),
        },
        datos={
            "estado": "ANULADA",
            "estado_operacion": "ANULADA",
            "estado_conciliacion": "NO_CONCILIABLE",
            "observacion": f"Anulada desde Caja. Motivo: {_texto(motivo)}",
        },
    )


def _saldo_caja_cur(cur, empresa_id, caja_id):
    empresa_id = int(empresa_id or 1)
    caja_id = int(caja_id)

    cur.execute(
        """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN caja_id_origen = ? AND sentido_caja_origen = 'INGRESO' THEN importe
                    WHEN caja_id_origen = ? AND sentido_caja_origen = 'EGRESO' THEN -importe
                    WHEN caja_id_destino = ? THEN importe
                    ELSE 0
                END
            ), 0) AS saldo
        FROM caja_movimientos
        WHERE empresa_id = ?
          AND estado <> 'ANULADO'
        """,
        (caja_id, caja_id, caja_id, empresa_id),
    )

    fila = cur.fetchone()

    if not fila:
        return 0.0

    return _numero(fila[0])


def _obtener_movimiento_cur(cur, empresa_id, movimiento_id):
    cur.execute(
        """
        SELECT *
        FROM caja_movimientos
        WHERE empresa_id = ?
          AND id = ?
        """,
        (int(empresa_id or 1), int(movimiento_id)),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _insertar_movimiento_caja(
    cur,
    empresa_id,
    fecha,
    tipo_movimiento,
    caja_id_origen,
    caja_nombre_origen,
    caja_id_destino,
    caja_nombre_destino,
    cuenta_banco_id,
    cuenta_banco_nombre,
    concepto,
    referencia,
    observacion,
    importe,
    sentido_caja_origen,
    usuario_id,
    arqueo_id=None,
):
    empresa_id = int(empresa_id or 1)
    tipo_movimiento = _validar_tipo_movimiento(tipo_movimiento)
    importe = _validar_importe_positivo(importe)

    cur.execute(
        """
        INSERT INTO caja_movimientos
        (
            empresa_id,
            fecha,
            tipo_movimiento,
            caja_id_origen,
            caja_nombre_origen,
            caja_id_destino,
            caja_nombre_destino,
            cuenta_banco_id,
            cuenta_banco_nombre,
            concepto,
            referencia,
            observacion,
            importe,
            sentido_caja_origen,
            estado,
            usuario_id,
            arqueo_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMADO', ?, ?)
        """,
        (
            empresa_id,
            _texto(fecha),
            tipo_movimiento,
            caja_id_origen,
            _texto(caja_nombre_origen),
            caja_id_destino,
            _texto(caja_nombre_destino),
            cuenta_banco_id,
            _texto(cuenta_banco_nombre),
            _texto(concepto),
            _texto(referencia),
            _texto(observacion),
            importe,
            _texto_upper(sentido_caja_origen),
            usuario_id,
            arqueo_id,
        ),
    )

    movimiento_id = int(cur.lastrowid)

    fingerprint = _hash_partes(
        empresa_id,
        movimiento_id,
        fecha,
        tipo_movimiento,
        caja_id_origen,
        caja_id_destino,
        cuenta_banco_id,
        importe,
    )

    cur.execute(
        """
        UPDATE caja_movimientos
        SET fingerprint = ?
        WHERE empresa_id = ?
          AND id = ?
        """,
        (fingerprint, empresa_id, movimiento_id),
    )

    return movimiento_id


# ======================================================
# INICIALIZACIÓN
# ======================================================

def inicializar_cajas():
    inicializar_tesoreria()
    _ejecutar_script_sql(_ruta_migracion_caja())

    # No crear una Caja General duplicada si la empresa ya tiene una caja operativa.
    empresa_id_default = 1
    conn = conectar()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tesoreria_cuentas
            WHERE empresa_id = ?
              AND tipo_cuenta = 'CAJA'
              AND activo = 1
            """,
            (empresa_id_default,),
        )
        cantidad_cajas = int(cur.fetchone()[0] or 0)

    finally:
        conn.close()

    if cantidad_cajas == 0:
        crear_cuenta_tesoreria(
            empresa_id=empresa_id_default,
            tipo_cuenta="CAJA",
            nombre="Caja General",
            entidad="Efectivo",
            numero_cuenta="",
            moneda="ARS",
            cuenta_contable_codigo=CUENTA_CAJA_DEFAULT[0],
            cuenta_contable_nombre=CUENTA_CAJA_DEFAULT[1],
            observacion="Caja inicial creada automáticamente por el módulo Caja.",
        )

    return True



# ======================================================
# CAJAS CONFIGURABLES
# ======================================================

def crear_caja(
    empresa_id=1,
    nombre="",
    moneda="ARS",
    cuenta_contable_codigo=None,
    cuenta_contable_nombre=None,
    observacion="",
):
    inicializar_cajas()

    nombre = _texto(nombre)

    if not nombre:
        raise ValueError("La caja debe tener nombre.")

    return crear_cuenta_tesoreria(
        empresa_id=int(empresa_id or 1),
        tipo_cuenta="CAJA",
        nombre=nombre,
        entidad="Efectivo",
        numero_cuenta="",
        moneda=_texto_upper(moneda or "ARS"),
        cuenta_contable_codigo=_texto(cuenta_contable_codigo or CUENTA_CAJA_DEFAULT[0]),
        cuenta_contable_nombre=_texto(cuenta_contable_nombre or nombre),
        observacion=_texto(observacion),
    )


def listar_cajas(empresa_id=1, incluir_inactivas=False):
    inicializar_cajas()

    df = listar_cuentas_tesoreria(
        empresa_id=int(empresa_id or 1),
        incluir_inactivas=incluir_inactivas,
    )

    if df.empty:
        return df

    if "tipo_cuenta" not in df.columns:
        return pd.DataFrame()

    return df[df["tipo_cuenta"].astype(str).str.upper() == "CAJA"].copy()


def listar_cuentas_banco_tesoreria(empresa_id=1, incluir_inactivas=False):
    inicializar_cajas()

    df = listar_cuentas_tesoreria(
        empresa_id=int(empresa_id or 1),
        incluir_inactivas=incluir_inactivas,
    )

    if df.empty:
        return df

    if "tipo_cuenta" not in df.columns:
        return pd.DataFrame()

    return df[df["tipo_cuenta"].astype(str).str.upper() == "BANCO"].copy()


def obtener_saldos_cajas(empresa_id=1):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    cajas = listar_cajas(empresa_id=empresa_id)

    if cajas.empty:
        return pd.DataFrame()

    conn = conectar()
    cur = conn.cursor()

    try:
        filas = []

        for _, caja in cajas.iterrows():
            caja_id = int(caja["id"])
            saldo = _saldo_caja_cur(cur, empresa_id, caja_id)

            filas.append({
                "id": caja_id,
                "nombre": caja.get("nombre", ""),
                "moneda": caja.get("moneda", "ARS"),
                "cuenta_contable_codigo": caja.get("cuenta_contable_codigo", ""),
                "cuenta_contable_nombre": caja.get("cuenta_contable_nombre", ""),
                "saldo": saldo,
            })

        return pd.DataFrame(filas)

    finally:
        conn.close()


def obtener_resumen_caja(empresa_id=1):
    inicializar_cajas()

    saldos = obtener_saldos_cajas(empresa_id=empresa_id)
    movimientos = listar_movimientos_caja(empresa_id=empresa_id, limite=5000)
    arqueos = listar_arqueos_caja(empresa_id=empresa_id, limite=5000)

    total_saldo = 0.0 if saldos.empty else _numero(saldos["saldo"].sum())
    cantidad_cajas = 0 if saldos.empty else int(len(saldos))
    cantidad_movimientos = 0 if movimientos.empty else int(len(movimientos))
    cantidad_arqueos = 0 if arqueos.empty else int(len(arqueos))

    pendientes_conciliacion = listar_operaciones_tesoreria_caja(
        empresa_id=empresa_id,
        solo_pendientes=True,
    )

    return {
        "cantidad_cajas": cantidad_cajas,
        "saldo_total": total_saldo,
        "cantidad_movimientos": cantidad_movimientos,
        "cantidad_arqueos": cantidad_arqueos,
        "pendientes_conciliacion": 0 if pendientes_conciliacion.empty else int(len(pendientes_conciliacion)),
    }


# ======================================================
# MOVIMIENTOS MANUALES
# ======================================================

def registrar_movimiento_manual_caja(
    empresa_id=1,
    caja_id=None,
    fecha="",
    tipo="INGRESO",
    importe=0,
    concepto="",
    referencia="",
    observacion="",
    usuario_id=None,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    caja_id = int(caja_id)
    tipo_norm = _texto_upper(tipo)

    if tipo_norm not in {"INGRESO", "EGRESO"}:
        raise ValueError("El tipo manual debe ser INGRESO o EGRESO.")

    importe = _validar_importe_positivo(importe)

    if not _texto(fecha):
        raise ValueError("La fecha del movimiento es obligatoria.")

    if not _texto(concepto):
        raise ValueError("El concepto del movimiento es obligatorio.")

    conn = conectar()
    cur = conn.cursor()

    try:
        caja = _obtener_cuenta_tesoreria(cur, empresa_id, caja_id)

        if not caja or _texto_upper(caja.get("tipo_cuenta")) != "CAJA":
            raise ValueError("La caja seleccionada no existe o no es una cuenta tipo CAJA.")

        caja_cuenta = _cuenta_contable_desde_cuenta_tesoreria(caja, CUENTA_CAJA_DEFAULT)
        caja_nombre = _texto(caja.get("nombre"))

        if tipo_norm == "INGRESO":
            tipo_movimiento = "INGRESO_MANUAL"
            sentido = "INGRESO"
            importe_tesoreria = importe
            debe_cuenta = caja_cuenta
            haber_cuenta = CUENTA_INGRESOS_A_CLASIFICAR
            glosa = f"Ingreso manual de caja - {concepto}"
            estado_conciliacion = "NO_CONCILIABLE"

        else:
            tipo_movimiento = "EGRESO_MANUAL"
            sentido = "EGRESO"
            importe_tesoreria = -importe
            debe_cuenta = CUENTA_EGRESOS_A_CLASIFICAR
            haber_cuenta = caja_cuenta
            glosa = f"Egreso manual de caja - {concepto}"
            estado_conciliacion = "NO_CONCILIABLE"

        movimiento_id = _insertar_movimiento_caja(
            cur=cur,
            empresa_id=empresa_id,
            fecha=fecha,
            tipo_movimiento=tipo_movimiento,
            caja_id_origen=caja_id,
            caja_nombre_origen=caja_nombre,
            caja_id_destino=None,
            caja_nombre_destino="",
            cuenta_banco_id=None,
            cuenta_banco_nombre="",
            concepto=concepto,
            referencia=referencia,
            observacion=observacion,
            importe=importe,
            sentido_caja_origen=sentido,
            usuario_id=usuario_id,
        )

        operacion_id = _insertar_tesoreria_operacion(
            cur=cur,
            empresa_id=empresa_id,
            tipo_operacion="CAJA",
            fecha=fecha,
            cuenta_tesoreria_id=caja_id,
            importe=importe_tesoreria,
            descripcion=glosa,
            referencia_externa=f"CAJA-MANUAL-{movimiento_id}",
            origen_tabla="caja_movimientos",
            origen_id=movimiento_id,
            estado_conciliacion=estado_conciliacion,
            usuario_id=usuario_id,
            observacion="Movimiento manual de caja no conciliable contra extracto bancario.",
        )

        cur.execute(
            """
            UPDATE caja_movimientos
            SET tesoreria_operacion_id = ?
            WHERE empresa_id = ?
              AND id = ?
            """,
            (operacion_id, empresa_id, movimiento_id),
        )

        _crear_asiento_doble(
            cur=cur,
            empresa_id=empresa_id,
            movimiento_caja_id=movimiento_id,
            arqueo_id=None,
            fecha=fecha,
            debe_cuenta=debe_cuenta,
            haber_cuenta=haber_cuenta,
            importe=importe,
            glosa=glosa,
        )

        _registrar_auditoria_caja(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CREAR",
            entidad="caja_movimientos",
            entidad_id=movimiento_id,
            valor_nuevo={
                "tipo": tipo_movimiento,
                "caja": caja_nombre,
                "importe": importe,
                "concepto": concepto,
            },
            motivo="Registro manual de movimiento de caja.",
        )

        conn.commit()

        return {
            "ok": True,
            "movimiento_id": movimiento_id,
            "tesoreria_operacion_id": operacion_id,
            "mensaje": "Movimiento manual de caja registrado.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



# ======================================================
# INTEGRACIÓN AUTOMÁTICA CON COBRANZAS / PAGOS EN EFECTIVO
# ======================================================

def registrar_cobranza_efectivo_en_caja_cur(
    cur,
    empresa_id,
    caja_id,
    caja_nombre,
    fecha,
    cliente,
    cuit,
    importe,
    numero_recibo,
    cobranza_id,
    tesoreria_operacion_id=None,
    usuario_id=None,
):
    """
    Registra en Caja el ingreso físico de efectivo originado en una cobranza.

    No genera asiento en caja_asientos porque el asiento contable principal
    ya lo genera el módulo Cobranzas en libro_diario.
    """

    empresa_id = int(empresa_id or 1)
    caja_id = int(caja_id)
    importe = _validar_importe_positivo(importe)
    referencia = _texto(numero_recibo)

    if not referencia:
        referencia = f"COBRANZA-{cobranza_id}"

    cur.execute(
        """
        SELECT id
        FROM caja_movimientos
        WHERE empresa_id = ?
          AND tipo_movimiento = 'COBRANZA_EFECTIVO'
          AND referencia = ?
          AND estado <> 'ANULADO'
        LIMIT 1
        """,
        (empresa_id, referencia),
    )

    existente = cur.fetchone()

    if existente:
        return int(existente[0])

    concepto = f"Cobranza en efectivo {referencia}"

    if _texto(cliente):
        concepto += f" - {_texto(cliente)}"

    movimiento_id = _insertar_movimiento_caja(
        cur=cur,
        empresa_id=empresa_id,
        fecha=fecha,
        tipo_movimiento="COBRANZA_EFECTIVO",
        caja_id_origen=caja_id,
        caja_nombre_origen=caja_nombre,
        caja_id_destino=None,
        caja_nombre_destino="",
        cuenta_banco_id=None,
        cuenta_banco_nombre="",
        concepto=concepto,
        referencia=referencia,
        observacion=(
            "Movimiento automático generado desde Cobranzas. "
            "Solo registra el flujo físico de efectivo en Caja; "
            "el asiento contable principal está en Cobranzas."
        ),
        importe=importe,
        sentido_caja_origen="INGRESO",
        usuario_id=usuario_id,
    )

    cur.execute(
        """
        UPDATE caja_movimientos
        SET tesoreria_operacion_id = ?
        WHERE empresa_id = ?
          AND id = ?
        """,
        (tesoreria_operacion_id, empresa_id, movimiento_id),
    )

    _registrar_auditoria_caja(
        cur=cur,
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        accion="CREAR",
        entidad="caja_movimientos",
        entidad_id=movimiento_id,
        valor_nuevo={
            "tipo": "COBRANZA_EFECTIVO",
            "origen": "COBRANZAS",
            "cobranza_id": cobranza_id,
            "numero_recibo": numero_recibo,
            "cliente": cliente,
            "cuit": cuit,
            "importe": importe,
        },
        motivo="Ingreso automático de Caja por cobranza en efectivo.",
    )

    return movimiento_id


def registrar_pago_efectivo_en_caja_cur(
    cur,
    empresa_id,
    caja_id,
    caja_nombre,
    fecha,
    proveedor,
    cuit,
    importe,
    numero_orden_pago,
    pago_id,
    tesoreria_operacion_id=None,
    usuario_id=None,
):
    """
    Registra en Caja el egreso físico de efectivo originado en un pago.

    No genera asiento en caja_asientos porque el asiento contable principal
    ya lo genera el módulo Pagos en libro_diario.
    """

    empresa_id = int(empresa_id or 1)
    caja_id = int(caja_id)
    importe = _validar_importe_positivo(importe)
    referencia = _texto(numero_orden_pago)

    if not referencia:
        referencia = f"PAGO-{pago_id}"

    cur.execute(
        """
        SELECT id
        FROM caja_movimientos
        WHERE empresa_id = ?
          AND tipo_movimiento = 'PAGO_EFECTIVO'
          AND referencia = ?
          AND estado <> 'ANULADO'
        LIMIT 1
        """,
        (empresa_id, referencia),
    )

    existente = cur.fetchone()

    if existente:
        return int(existente[0])

    concepto = f"Pago en efectivo {referencia}"

    if _texto(proveedor):
        concepto += f" - {_texto(proveedor)}"

    movimiento_id = _insertar_movimiento_caja(
        cur=cur,
        empresa_id=empresa_id,
        fecha=fecha,
        tipo_movimiento="PAGO_EFECTIVO",
        caja_id_origen=caja_id,
        caja_nombre_origen=caja_nombre,
        caja_id_destino=None,
        caja_nombre_destino="",
        cuenta_banco_id=None,
        cuenta_banco_nombre="",
        concepto=concepto,
        referencia=referencia,
        observacion=(
            "Movimiento automático generado desde Pagos. "
            "Solo registra el flujo físico de efectivo en Caja; "
            "el asiento contable principal está en Pagos."
        ),
        importe=importe,
        sentido_caja_origen="EGRESO",
        usuario_id=usuario_id,
    )

    cur.execute(
        """
        UPDATE caja_movimientos
        SET tesoreria_operacion_id = ?
        WHERE empresa_id = ?
          AND id = ?
        """,
        (tesoreria_operacion_id, empresa_id, movimiento_id),
    )

    _registrar_auditoria_caja(
        cur=cur,
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        accion="CREAR",
        entidad="caja_movimientos",
        entidad_id=movimiento_id,
        valor_nuevo={
            "tipo": "PAGO_EFECTIVO",
            "origen": "PAGOS",
            "pago_id": pago_id,
            "numero_orden_pago": numero_orden_pago,
            "proveedor": proveedor,
            "cuit": cuit,
            "importe": importe,
        },
        motivo="Egreso automático de Caja por pago en efectivo.",
    )

    return movimiento_id


def anular_movimientos_caja_por_referencia_cur(
    cur,
    empresa_id,
    tipo_movimiento,
    referencia,
    motivo,
    usuario_id=None,
):
    """
    Anula lógicamente movimientos automáticos de Caja vinculados a recibos u órdenes de pago.
    No borra movimientos.
    """

    empresa_id = int(empresa_id or 1)
    tipo_movimiento = _texto_upper(tipo_movimiento)
    referencia = _texto(referencia)
    motivo = _texto(motivo)

    if not referencia:
        return 0

    cur.execute(
        """
        SELECT id
        FROM caja_movimientos
        WHERE empresa_id = ?
          AND tipo_movimiento = ?
          AND referencia = ?
          AND estado <> 'ANULADO'
        """,
        (empresa_id, tipo_movimiento, referencia),
    )

    filas = cur.fetchall()
    ids = [int(fila[0]) for fila in filas]

    if not ids:
        return 0

    placeholders = ", ".join(["?"] * len(ids))

    cur.execute(
        f"""
        UPDATE caja_movimientos
        SET estado = 'ANULADO',
            motivo_anulacion = ?,
            fecha_anulacion = CURRENT_TIMESTAMP
        WHERE empresa_id = ?
          AND id IN ({placeholders})
        """,
        tuple([motivo, empresa_id] + ids),
    )

    cur.execute(
        f"""
        UPDATE caja_asientos
        SET estado = 'ANULADO'
        WHERE empresa_id = ?
          AND movimiento_caja_id IN ({placeholders})
        """,
        tuple([empresa_id] + ids),
    )

    for movimiento_id in ids:
        _registrar_auditoria_caja(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="ANULAR",
            entidad="caja_movimientos",
            entidad_id=movimiento_id,
            valor_anterior={"estado": "CONFIRMADO"},
            valor_nuevo={"estado": "ANULADO", "motivo": motivo},
            motivo=motivo,
        )

    return len(ids)

# ======================================================
# TRANSFERENCIAS INTERNAS
# ======================================================

def registrar_transferencia_interna(
    empresa_id=1,
    cuenta_origen_id=None,
    cuenta_destino_id=None,
    fecha="",
    importe=0,
    concepto="",
    referencia="",
    observacion="",
    usuario_id=None,
    tipo_forzado=None,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    cuenta_origen_id = int(cuenta_origen_id)
    cuenta_destino_id = int(cuenta_destino_id)

    if cuenta_origen_id == cuenta_destino_id:
        raise ValueError("La cuenta origen y destino no pueden ser la misma.")

    if not _texto(fecha):
        raise ValueError("La fecha de la transferencia es obligatoria.")

    importe = _validar_importe_positivo(importe)

    if not _texto(concepto):
        concepto = "Transferencia interna"

    conn = conectar()
    cur = conn.cursor()

    try:
        origen = _obtener_cuenta_tesoreria(cur, empresa_id, cuenta_origen_id)
        destino = _obtener_cuenta_tesoreria(cur, empresa_id, cuenta_destino_id)

        if not origen:
            raise ValueError("La cuenta origen no existe.")

        if not destino:
            raise ValueError("La cuenta destino no existe.")

        tipo_origen = _texto_upper(origen.get("tipo_cuenta"))
        tipo_destino = _texto_upper(destino.get("tipo_cuenta"))

        if tipo_origen not in {"CAJA", "BANCO"} or tipo_destino not in {"CAJA", "BANCO"}:
            raise ValueError("Caja MVP permite transferencias internas entre cuentas tipo CAJA y BANCO.")

        if tipo_forzado:
            tipo_movimiento = _validar_tipo_movimiento(tipo_forzado)

        elif tipo_origen == "CAJA" and tipo_destino == "CAJA":
            tipo_movimiento = "TRANSFERENCIA_CAJA_CAJA"

        elif tipo_origen == "CAJA" and tipo_destino == "BANCO":
            tipo_movimiento = "TRANSFERENCIA_CAJA_BANCO"

        elif tipo_origen == "BANCO" and tipo_destino == "CAJA":
            tipo_movimiento = "TRANSFERENCIA_BANCO_CAJA"

        else:
            raise ValueError("Esta pantalla no registra transferencias Banco ↔ Banco.")

        origen_nombre = _texto(origen.get("nombre"))
        destino_nombre = _texto(destino.get("nombre"))

        caja_id_origen = cuenta_origen_id if tipo_origen == "CAJA" else None
        caja_nombre_origen = origen_nombre if tipo_origen == "CAJA" else ""

        caja_id_destino = cuenta_destino_id if tipo_destino == "CAJA" else None
        caja_nombre_destino = destino_nombre if tipo_destino == "CAJA" else ""

        cuenta_banco_id = None
        cuenta_banco_nombre = ""

        if tipo_origen == "BANCO":
            cuenta_banco_id = cuenta_origen_id
            cuenta_banco_nombre = origen_nombre

        elif tipo_destino == "BANCO":
            cuenta_banco_id = cuenta_destino_id
            cuenta_banco_nombre = destino_nombre

        movimiento_id = _insertar_movimiento_caja(
            cur=cur,
            empresa_id=empresa_id,
            fecha=fecha,
            tipo_movimiento=tipo_movimiento,
            caja_id_origen=caja_id_origen,
            caja_nombre_origen=caja_nombre_origen,
            caja_id_destino=caja_id_destino,
            caja_nombre_destino=caja_nombre_destino,
            cuenta_banco_id=cuenta_banco_id,
            cuenta_banco_nombre=cuenta_banco_nombre,
            concepto=concepto,
            referencia=referencia,
            observacion=observacion,
            importe=importe,
            sentido_caja_origen="EGRESO" if tipo_origen == "CAJA" else "NEUTRO",
            usuario_id=usuario_id,
        )

        operaciones = []

        descripcion_origen = (
            f"Transferencia interna - salida desde {origen_nombre} hacia {destino_nombre}. "
            "No registrar como nueva cobranza."
        )

        descripcion_destino = (
            f"Transferencia interna - ingreso en {destino_nombre} desde {origen_nombre}. "
            "No registrar como nueva cobranza."
        )

        estado_conciliacion_origen = "PENDIENTE" if tipo_origen == "BANCO" else "NO_CONCILIABLE"
        estado_conciliacion_destino = "PENDIENTE" if tipo_destino == "BANCO" else "NO_CONCILIABLE"

        operacion_origen_id = _insertar_tesoreria_operacion(
            cur=cur,
            empresa_id=empresa_id,
            tipo_operacion="TRANSFERENCIA",
            fecha=fecha,
            cuenta_tesoreria_id=cuenta_origen_id,
            importe=-importe,
            descripcion=descripcion_origen,
            referencia_externa=f"CAJA-TRANSFERENCIA-ORIGEN-{movimiento_id}",
            origen_tabla="caja_movimientos",
            origen_id=movimiento_id,
            estado_conciliacion=estado_conciliacion_origen,
            usuario_id=usuario_id,
            observacion=(
                "Transferencia interna generada desde Caja. "
                "Si aparece en extracto bancario debe conciliarse como transferencia propia, no como cobranza."
            ),
        )
        operaciones.append(operacion_origen_id)

        operacion_destino_id = _insertar_tesoreria_operacion(
            cur=cur,
            empresa_id=empresa_id,
            tipo_operacion="TRANSFERENCIA",
            fecha=fecha,
            cuenta_tesoreria_id=cuenta_destino_id,
            importe=importe,
            descripcion=descripcion_destino,
            referencia_externa=f"CAJA-TRANSFERENCIA-DESTINO-{movimiento_id}",
            origen_tabla="caja_movimientos",
            origen_id=movimiento_id,
            estado_conciliacion=estado_conciliacion_destino,
            usuario_id=usuario_id,
            observacion=(
                "Transferencia interna generada desde Caja. "
                "No debe tratarse como nueva cobranza ni como nuevo pago."
            ),
        )
        operaciones.append(operacion_destino_id)

        operacion_banco_id = None

        if tipo_origen == "BANCO":
            operacion_banco_id = operacion_origen_id
        elif tipo_destino == "BANCO":
            operacion_banco_id = operacion_destino_id

        cur.execute(
            """
            UPDATE caja_movimientos
            SET tesoreria_operacion_id = ?,
                tesoreria_operacion_banco_id = ?
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                operacion_origen_id,
                operacion_banco_id,
                empresa_id,
                movimiento_id,
            ),
        )

        cuenta_origen_contable = _cuenta_contable_desde_cuenta_tesoreria(
            origen,
            CUENTA_CAJA_DEFAULT if tipo_origen == "CAJA" else CUENTA_BANCO_DEFAULT,
        )
        cuenta_destino_contable = _cuenta_contable_desde_cuenta_tesoreria(
            destino,
            CUENTA_CAJA_DEFAULT if tipo_destino == "CAJA" else CUENTA_BANCO_DEFAULT,
        )

        glosa = (
            f"Transferencia interna {origen_nombre} → {destino_nombre} - "
            f"{concepto}"
        )

        _crear_asiento_doble(
            cur=cur,
            empresa_id=empresa_id,
            movimiento_caja_id=movimiento_id,
            arqueo_id=None,
            fecha=fecha,
            debe_cuenta=cuenta_destino_contable,
            haber_cuenta=cuenta_origen_contable,
            importe=importe,
            glosa=glosa,
        )

        _registrar_auditoria_caja(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CREAR",
            entidad="caja_movimientos",
            entidad_id=movimiento_id,
            valor_nuevo={
                "tipo": tipo_movimiento,
                "origen": origen_nombre,
                "destino": destino_nombre,
                "importe": importe,
                "operaciones_tesoreria": operaciones,
            },
            motivo="Registro de transferencia interna de Caja/Tesorería.",
        )

        conn.commit()

        return {
            "ok": True,
            "movimiento_id": movimiento_id,
            "tesoreria_operacion_id": operacion_origen_id,
            "tesoreria_operacion_banco_id": operacion_banco_id,
            "mensaje": "Transferencia interna registrada.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def registrar_deposito_caja_a_banco(
    empresa_id=1,
    caja_id=None,
    banco_cuenta_id=None,
    fecha="",
    importe=0,
    concepto="Depósito de efectivo en banco",
    referencia="",
    observacion="",
    usuario_id=None,
):
    return registrar_transferencia_interna(
        empresa_id=empresa_id,
        cuenta_origen_id=caja_id,
        cuenta_destino_id=banco_cuenta_id,
        fecha=fecha,
        importe=importe,
        concepto=concepto,
        referencia=referencia,
        observacion=(
            f"{_texto(observacion)} "
            "Depósito de efectivo Caja → Banco. No debe registrarse como nueva cobranza."
        ).strip(),
        usuario_id=usuario_id,
        tipo_forzado="DEPOSITO_CAJA_BANCO",
    )


def registrar_retiro_banco_a_caja(
    empresa_id=1,
    banco_cuenta_id=None,
    caja_id=None,
    fecha="",
    importe=0,
    concepto="Retiro de efectivo del banco",
    referencia="",
    observacion="",
    usuario_id=None,
):
    return registrar_transferencia_interna(
        empresa_id=empresa_id,
        cuenta_origen_id=banco_cuenta_id,
        cuenta_destino_id=caja_id,
        fecha=fecha,
        importe=importe,
        concepto=concepto,
        referencia=referencia,
        observacion=(
            f"{_texto(observacion)} "
            "Retiro Banco → Caja. No debe registrarse como egreso definitivo."
        ).strip(),
        usuario_id=usuario_id,
        tipo_forzado="RETIRO_BANCO_CAJA",
    )


# ======================================================
# ARQUEOS
# ======================================================

def registrar_arqueo_caja(
    empresa_id=1,
    caja_id=None,
    fecha="",
    efectivo_contado=0,
    observacion="",
    usuario_id=None,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    caja_id = int(caja_id)

    if not _texto(fecha):
        raise ValueError("La fecha del arqueo es obligatoria.")

    efectivo_contado = _numero(efectivo_contado)

    if efectivo_contado < 0:
        raise ValueError("El efectivo contado no puede ser negativo.")

    conn = conectar()
    cur = conn.cursor()

    try:
        caja = _obtener_cuenta_tesoreria(cur, empresa_id, caja_id)

        if not caja or _texto_upper(caja.get("tipo_cuenta")) != "CAJA":
            raise ValueError("La caja seleccionada no existe o no es una cuenta tipo CAJA.")

        caja_nombre = _texto(caja.get("nombre"))
        caja_cuenta = _cuenta_contable_desde_cuenta_tesoreria(caja, CUENTA_CAJA_DEFAULT)

        saldo_sistema = _saldo_caja_cur(cur, empresa_id, caja_id)
        diferencia = _numero(efectivo_contado - saldo_sistema)

        if abs(diferencia) <= 0.01:
            tipo_diferencia = "SIN_DIFERENCIA"
            estado = "CUADRADO"

        elif diferencia > 0:
            tipo_diferencia = "SOBRANTE"
            estado = "CON_DIFERENCIA_AJUSTADA"

        else:
            tipo_diferencia = "FALTANTE"
            estado = "CON_DIFERENCIA_AJUSTADA"

        cur.execute(
            """
            INSERT INTO caja_arqueos
            (
                empresa_id,
                caja_id,
                caja_nombre,
                fecha,
                saldo_sistema,
                efectivo_contado,
                diferencia,
                tipo_diferencia,
                estado,
                observacion,
                usuario_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                caja_id,
                caja_nombre,
                _texto(fecha),
                saldo_sistema,
                efectivo_contado,
                diferencia,
                tipo_diferencia,
                estado,
                _texto(observacion),
                usuario_id,
            ),
        )

        arqueo_id = int(cur.lastrowid)
        movimiento_ajuste_id = None

        if tipo_diferencia in {"SOBRANTE", "FALTANTE"}:
            importe_ajuste = abs(diferencia)

            if tipo_diferencia == "SOBRANTE":
                tipo_movimiento = "AJUSTE_ARQUEO_SOBRANTE"
                sentido = "INGRESO"
                debe_cuenta = caja_cuenta
                haber_cuenta = CUENTA_SOBRANTES_CAJA
                importe_tesoreria = importe_ajuste
                concepto = f"Sobrante de arqueo #{arqueo_id}"

            else:
                tipo_movimiento = "AJUSTE_ARQUEO_FALTANTE"
                sentido = "EGRESO"
                debe_cuenta = CUENTA_FALTANTES_CAJA
                haber_cuenta = caja_cuenta
                importe_tesoreria = -importe_ajuste
                concepto = f"Faltante de arqueo #{arqueo_id}"

            movimiento_ajuste_id = _insertar_movimiento_caja(
                cur=cur,
                empresa_id=empresa_id,
                fecha=fecha,
                tipo_movimiento=tipo_movimiento,
                caja_id_origen=caja_id,
                caja_nombre_origen=caja_nombre,
                caja_id_destino=None,
                caja_nombre_destino="",
                cuenta_banco_id=None,
                cuenta_banco_nombre="",
                concepto=concepto,
                referencia=f"ARQUEO-{arqueo_id}",
                observacion=observacion,
                importe=importe_ajuste,
                sentido_caja_origen=sentido,
                usuario_id=usuario_id,
                arqueo_id=arqueo_id,
            )

            operacion_id = _insertar_tesoreria_operacion(
                cur=cur,
                empresa_id=empresa_id,
                tipo_operacion="AJUSTE",
                fecha=fecha,
                cuenta_tesoreria_id=caja_id,
                importe=importe_tesoreria,
                descripcion=concepto,
                referencia_externa=f"CAJA-ARQUEO-{arqueo_id}",
                origen_tabla="caja_arqueos",
                origen_id=arqueo_id,
                estado_conciliacion="NO_CONCILIABLE",
                usuario_id=usuario_id,
                observacion="Ajuste por diferencia de arqueo de caja.",
            )

            cur.execute(
                """
                UPDATE caja_movimientos
                SET tesoreria_operacion_id = ?
                WHERE empresa_id = ?
                  AND id = ?
                """,
                (operacion_id, empresa_id, movimiento_ajuste_id),
            )

            _crear_asiento_doble(
                cur=cur,
                empresa_id=empresa_id,
                movimiento_caja_id=movimiento_ajuste_id,
                arqueo_id=arqueo_id,
                fecha=fecha,
                debe_cuenta=debe_cuenta,
                haber_cuenta=haber_cuenta,
                importe=importe_ajuste,
                glosa=concepto,
            )

            cur.execute(
                """
                UPDATE caja_arqueos
                SET movimiento_ajuste_id = ?
                WHERE empresa_id = ?
                  AND id = ?
                """,
                (movimiento_ajuste_id, empresa_id, arqueo_id),
            )

        _registrar_auditoria_caja(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CREAR",
            entidad="caja_arqueos",
            entidad_id=arqueo_id,
            valor_nuevo={
                "caja": caja_nombre,
                "saldo_sistema": saldo_sistema,
                "efectivo_contado": efectivo_contado,
                "diferencia": diferencia,
                "tipo_diferencia": tipo_diferencia,
            },
            motivo="Registro de arqueo de caja.",
        )

        conn.commit()

        return {
            "ok": True,
            "arqueo_id": arqueo_id,
            "movimiento_ajuste_id": movimiento_ajuste_id,
            "saldo_sistema": saldo_sistema,
            "efectivo_contado": efectivo_contado,
            "diferencia": diferencia,
            "tipo_diferencia": tipo_diferencia,
            "mensaje": "Arqueo registrado.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ======================================================
# ANULACIONES
# ======================================================

def anular_movimiento_caja(
    empresa_id=1,
    movimiento_id=None,
    motivo="",
    usuario_id=None,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    movimiento_id = int(movimiento_id)
    motivo = _texto(motivo)

    if not motivo:
        raise ValueError("Para anular un movimiento de caja tenés que indicar un motivo.")

    conn = conectar()
    cur = conn.cursor()

    try:
        movimiento = _obtener_movimiento_cur(cur, empresa_id, movimiento_id)

        if not movimiento:
            raise ValueError("No existe el movimiento de caja seleccionado.")

        if _texto_upper(movimiento.get("estado")) == "ANULADO":
            raise ValueError("El movimiento ya estaba anulado.")

        _anular_tesoreria_operacion(
            cur=cur,
            empresa_id=empresa_id,
            operacion_id=movimiento.get("tesoreria_operacion_id"),
            motivo=motivo,
        )

        _anular_tesoreria_operacion(
            cur=cur,
            empresa_id=empresa_id,
            operacion_id=movimiento.get("tesoreria_operacion_banco_id"),
            motivo=motivo,
        )

        cur.execute(
            """
            UPDATE caja_movimientos
            SET estado = 'ANULADO',
                motivo_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ?
              AND id = ?
            """,
            (motivo, empresa_id, movimiento_id),
        )

        cur.execute(
            """
            UPDATE caja_asientos
            SET estado = 'ANULADO'
            WHERE empresa_id = ?
              AND movimiento_caja_id = ?
              AND estado <> 'ANULADO'
            """,
            (empresa_id, movimiento_id),
        )

        if movimiento.get("arqueo_id"):
            cur.execute(
                """
                UPDATE caja_arqueos
                SET estado = 'ANULADO',
                    motivo_anulacion = ?,
                    fecha_anulacion = CURRENT_TIMESTAMP
                WHERE empresa_id = ?
                  AND id = ?
                """,
                (motivo, empresa_id, int(movimiento["arqueo_id"])),
            )

        _registrar_auditoria_caja(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="ANULAR",
            entidad="caja_movimientos",
            entidad_id=movimiento_id,
            valor_anterior=movimiento,
            valor_nuevo={"estado": "ANULADO", "motivo": motivo},
            motivo=motivo,
        )

        conn.commit()

        return {
            "ok": True,
            "movimiento_id": movimiento_id,
            "mensaje": "Movimiento de caja anulado con motivo.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ======================================================
# CONSULTAS
# ======================================================

def listar_movimientos_caja(
    empresa_id=1,
    caja_id=None,
    estado=None,
    limite=500,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    filtros = ["empresa_id = ?"]
    params = [empresa_id]

    if caja_id:
        filtros.append("(caja_id_origen = ? OR caja_id_destino = ?)")
        params.extend([int(caja_id), int(caja_id)])

    if estado:
        filtros.append("estado = ?")
        params.append(_texto_upper(estado))

    where_sql = " AND ".join(filtros)

    return ejecutar_query(
        f"""
        SELECT
            id,
            fecha,
            tipo_movimiento,
            caja_nombre_origen,
            caja_nombre_destino,
            cuenta_banco_nombre,
            concepto,
            referencia,
            observacion,
            importe,
            sentido_caja_origen,
            estado,
            motivo_anulacion,
            tesoreria_operacion_id,
            tesoreria_operacion_banco_id,
            arqueo_id,
            fecha_creacion
        FROM caja_movimientos
        WHERE {where_sql}
        ORDER BY fecha DESC, id DESC
        LIMIT ?
        """,
        tuple(params + [int(limite or 500)]),
    )


def listar_arqueos_caja(
    empresa_id=1,
    caja_id=None,
    limite=500,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    filtros = ["empresa_id = ?"]
    params = [empresa_id]

    if caja_id:
        filtros.append("caja_id = ?")
        params.append(int(caja_id))

    where_sql = " AND ".join(filtros)

    return ejecutar_query(
        f"""
        SELECT
            id,
            fecha,
            caja_nombre,
            saldo_sistema,
            efectivo_contado,
            diferencia,
            tipo_diferencia,
            estado,
            movimiento_ajuste_id,
            observacion,
            motivo_anulacion,
            fecha_creacion
        FROM caja_arqueos
        WHERE {where_sql}
        ORDER BY fecha DESC, id DESC
        LIMIT ?
        """,
        tuple(params + [int(limite or 500)]),
    )


def listar_asientos_caja(
    empresa_id=1,
    movimiento_caja_id=None,
    arqueo_id=None,
    limite=1000,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)
    filtros = ["empresa_id = ?"]
    params = [empresa_id]

    if movimiento_caja_id:
        filtros.append("movimiento_caja_id = ?")
        params.append(int(movimiento_caja_id))

    if arqueo_id:
        filtros.append("arqueo_id = ?")
        params.append(int(arqueo_id))

    where_sql = " AND ".join(filtros)

    return ejecutar_query(
        f"""
        SELECT
            id,
            movimiento_caja_id,
            arqueo_id,
            fecha,
            cuenta_codigo,
            cuenta_nombre,
            debe,
            haber,
            glosa,
            estado,
            fecha_creacion
        FROM caja_asientos
        WHERE {where_sql}
        ORDER BY fecha DESC, id DESC
        LIMIT ?
        """,
        tuple(params + [int(limite or 1000)]),
    )


def listar_operaciones_tesoreria_caja(
    empresa_id=1,
    solo_pendientes=False,
    limite=500,
):
    inicializar_cajas()

    empresa_id = int(empresa_id or 1)

    conn = conectar()

    try:
        columnas = set(_columnas_tabla(conn, "tesoreria_operaciones"))

        if not columnas or "empresa_id" not in columnas:
            return pd.DataFrame()

        filtros = ["empresa_id = ?"]
        params = [empresa_id]

        if "origen_modulo" in columnas:
            filtros.append("origen_modulo = 'CAJA'")

        if solo_pendientes and "estado_conciliacion" in columnas:
            filtros.append("estado_conciliacion = 'PENDIENTE'")

        fecha_col = "fecha_operacion" if "fecha_operacion" in columnas else "fecha" if "fecha" in columnas else "id"

        select_cols = [
            col
            for col in [
                "id",
                "fecha_operacion",
                "fecha",
                "tipo_operacion",
                "cuenta_tesoreria_id",
                "importe",
                "descripcion",
                "concepto",
                "referencia_externa",
                "estado",
                "estado_operacion",
                "estado_conciliacion",
                "origen_tabla",
                "origen_id",
                "observacion",
            ]
            if col in columnas
        ]

        if not select_cols:
            select_cols = ["*"]

        where_sql = " AND ".join(filtros)

        return pd.read_sql_query(
            f"""
            SELECT {", ".join(select_cols)}
            FROM tesoreria_operaciones
            WHERE {where_sql}
            ORDER BY {fecha_col} DESC, id DESC
            LIMIT ?
            """,
            conn,
            params=tuple(params + [int(limite or 500)]),
        )

    finally:
        conn.close()


def obtener_auditoria_caja(empresa_id=1, limite=500):
    inicializar_cajas()

    return ejecutar_query(
        """
        SELECT
            fecha,
            accion,
            entidad,
            entidad_id,
            motivo,
            valor_anterior,
            valor_nuevo
        FROM caja_auditoria
        WHERE empresa_id = ?
        ORDER BY fecha DESC, id DESC
        LIMIT ?
        """,
        (int(empresa_id or 1), int(limite or 500)),
    )