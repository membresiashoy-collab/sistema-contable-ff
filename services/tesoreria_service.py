import hashlib
import json
from pathlib import Path

import pandas as pd

from database import conectar, ejecutar_query


# ======================================================
# CONSTANTES
# ======================================================

TIPOS_CUENTA_TESORERIA = {
    "BANCO",
    "CAJA",
    "BILLETERA",
    "TARJETA",
    "VALORES",
    "OTRO",
}

TIPOS_OPERACION_TESORERIA = {
    "COBRANZA",
    "PAGO",
    "CAJA",
    "TRANSFERENCIA",
    "IMPUESTO",
    "AJUSTE",
    "OTRO",
}

ESTADOS_OPERACION = {
    "BORRADOR",
    "CONFIRMADA",
    "CONTABILIZADA",
    "ANULADA",
}

ESTADOS_CONCILIACION = {
    "PENDIENTE",
    "SUGERIDA",
    "PARCIAL",
    "CONCILIADA",
    "NO_CONCILIABLE",
}


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


def _ruta_migracion_tesoreria():
    return Path(__file__).resolve().parents[1] / "migrations" / "009_tesoreria_base.sql"


def _ejecutar_script_sql(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la migración de Tesorería: {ruta}")

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


def _registrar_auditoria(
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


def inicializar_tesoreria():
    """
    Crea la estructura base de Tesorería.

    Se ejecuta desde el servicio para no depender todavía de un runner
    automático de migraciones.
    """

    _ejecutar_script_sql(_ruta_migracion_tesoreria())
    return True


def normalizar_tipo_cuenta(tipo_cuenta):
    tipo = _texto_upper(tipo_cuenta)

    if tipo not in TIPOS_CUENTA_TESORERIA:
        raise ValueError(
            f"Tipo de cuenta de tesorería inválido: {tipo_cuenta}. "
            f"Permitidos: {', '.join(sorted(TIPOS_CUENTA_TESORERIA))}"
        )

    return tipo


def normalizar_tipo_operacion(tipo_operacion):
    tipo = _texto_upper(tipo_operacion)

    if tipo not in TIPOS_OPERACION_TESORERIA:
        raise ValueError(
            f"Tipo de operación de tesorería inválido: {tipo_operacion}. "
            f"Permitidos: {', '.join(sorted(TIPOS_OPERACION_TESORERIA))}"
        )

    return tipo


def normalizar_estado_operacion(estado):
    estado_norm = _texto_upper(estado or "CONFIRMADA")

    if estado_norm not in ESTADOS_OPERACION:
        raise ValueError(
            f"Estado de operación inválido: {estado}. "
            f"Permitidos: {', '.join(sorted(ESTADOS_OPERACION))}"
        )

    return estado_norm


def normalizar_estado_conciliacion(estado):
    estado_norm = _texto_upper(estado or "PENDIENTE")

    if estado_norm not in ESTADOS_CONCILIACION:
        raise ValueError(
            f"Estado de conciliación inválido: {estado}. "
            f"Permitidos: {', '.join(sorted(ESTADOS_CONCILIACION))}"
        )

    return estado_norm


def construir_fingerprint_operacion(
    empresa_id,
    tipo_operacion,
    fecha_operacion,
    cuenta_tesoreria_id,
    importe,
    tercero_cuit="",
    tercero_nombre="",
    referencia_externa="",
    origen_modulo="",
    origen_tabla="",
    origen_id=None,
):
    """
    Huella funcional para evitar duplicación de operaciones de Tesorería.

    No depende del nombre de archivo.
    Depende del hecho financiero registrado.
    """

    partes = [
        str(int(empresa_id or 1)),
        _texto_upper(tipo_operacion),
        _texto(fecha_operacion),
        str(cuenta_tesoreria_id or ""),
        f"{_numero(importe):.2f}",
        _texto_upper(tercero_cuit),
        _texto_upper(tercero_nombre),
        _texto_upper(referencia_externa),
        _texto_upper(origen_modulo),
        _texto_upper(origen_tabla),
        str(origen_id or ""),
    ]

    base = "|".join(partes)

    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _obtener_id_por_fingerprint(cur, empresa_id, fingerprint):
    if not fingerprint:
        return None

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

    if fila is None:
        return None

    return int(fila[0])


def _obtener_operacion_dict(cur, empresa_id, operacion_id):
    cur.execute(
        """
        SELECT *
        FROM tesoreria_operaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, operacion_id),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]

    return dict(zip(columnas, fila))


# ======================================================
# CUENTAS Y MEDIOS DE PAGO
# ======================================================

def crear_cuenta_tesoreria(
    empresa_id=1,
    tipo_cuenta="BANCO",
    nombre="",
    entidad="",
    numero_cuenta="",
    moneda="ARS",
    cuenta_contable_codigo="",
    cuenta_contable_nombre="",
    observacion="",
):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    tipo_cuenta = normalizar_tipo_cuenta(tipo_cuenta)
    nombre = _texto(nombre)

    if not nombre:
        raise ValueError("La cuenta de tesorería debe tener nombre.")

    conn = conectar()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id
            FROM tesoreria_cuentas
            WHERE empresa_id = ?
              AND tipo_cuenta = ?
              AND nombre = ?
            """,
            (empresa_id, tipo_cuenta, nombre),
        )

        existente = cur.fetchone()

        if existente:
            return {
                "ok": True,
                "creada": False,
                "cuenta_id": int(existente[0]),
                "mensaje": "La cuenta de tesorería ya existía.",
            }

        cur.execute(
            """
            INSERT INTO tesoreria_cuentas
            (
                empresa_id,
                tipo_cuenta,
                nombre,
                entidad,
                numero_cuenta,
                moneda,
                cuenta_contable_codigo,
                cuenta_contable_nombre,
                observacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                tipo_cuenta,
                nombre,
                _texto(entidad),
                _texto(numero_cuenta),
                _texto_upper(moneda or "ARS"),
                _texto(cuenta_contable_codigo),
                _texto(cuenta_contable_nombre),
                _texto(observacion),
            ),
        )

        cuenta_id = int(cur.lastrowid)

        _registrar_auditoria(
            cur,
            empresa_id=empresa_id,
            usuario_id=None,
            accion="CREAR",
            entidad="tesoreria_cuentas",
            entidad_id=cuenta_id,
            valor_nuevo={
                "tipo_cuenta": tipo_cuenta,
                "nombre": nombre,
                "entidad": entidad,
                "numero_cuenta": numero_cuenta,
            },
            motivo="Alta de cuenta de tesorería.",
        )

        conn.commit()

        return {
            "ok": True,
            "creada": True,
            "cuenta_id": cuenta_id,
            "mensaje": "Cuenta de tesorería creada.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def listar_cuentas_tesoreria(empresa_id=1, incluir_inactivas=False):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)

    if incluir_inactivas:
        return ejecutar_query(
            """
            SELECT *
            FROM tesoreria_cuentas
            WHERE empresa_id = ?
            ORDER BY tipo_cuenta, nombre
            """,
            (empresa_id,),
            fetch=True,
        )

    return ejecutar_query(
        """
        SELECT *
        FROM tesoreria_cuentas
        WHERE empresa_id = ?
          AND activo = 1
        ORDER BY tipo_cuenta, nombre
        """,
        (empresa_id,),
        fetch=True,
    )


def asegurar_medios_pago_basicos(empresa_id=1):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)

    medios = [
        ("EFECTIVO", "Efectivo", "EFECTIVO", 0),
        ("TRANSFERENCIA", "Transferencia bancaria", "BANCO", 1),
        ("CHEQUE", "Cheque", "VALORES", 1),
        ("ECHEQ", "E-Cheq", "VALORES", 1),
        ("TARJETA", "Tarjeta", "TARJETA", 1),
        ("BILLETERA", "Billetera virtual", "BILLETERA", 1),
        ("DEBITO_AUTOMATICO", "Débito automático", "BANCO", 1),
        ("OTRO", "Otro medio de pago", "OTRO", 0),
    ]

    conn = conectar()
    cur = conn.cursor()

    try:
        for codigo, nombre, tipo, requiere_referencia in medios:
            cur.execute(
                """
                INSERT OR IGNORE INTO tesoreria_medios_pago
                (
                    empresa_id,
                    codigo,
                    nombre,
                    tipo,
                    requiere_referencia,
                    activo
                )
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    empresa_id,
                    codigo,
                    nombre,
                    tipo,
                    requiere_referencia,
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return listar_medios_pago(empresa_id=empresa_id)


def listar_medios_pago(empresa_id=1, incluir_inactivos=False):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)

    if incluir_inactivos:
        return ejecutar_query(
            """
            SELECT *
            FROM tesoreria_medios_pago
            WHERE empresa_id = ?
            ORDER BY nombre
            """,
            (empresa_id,),
            fetch=True,
        )

    return ejecutar_query(
        """
        SELECT *
        FROM tesoreria_medios_pago
        WHERE empresa_id = ?
          AND activo = 1
        ORDER BY nombre
        """,
        (empresa_id,),
        fetch=True,
    )


def obtener_medio_pago_id(empresa_id=1, codigo="EFECTIVO", crear_si_no_existe=True):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    codigo = _texto_upper(codigo or "EFECTIVO")

    if crear_si_no_existe:
        asegurar_medios_pago_basicos(empresa_id=empresa_id)

    df = ejecutar_query(
        """
        SELECT id
        FROM tesoreria_medios_pago
        WHERE empresa_id = ?
          AND codigo = ?
          AND activo = 1
        """,
        (empresa_id, codigo),
        fetch=True,
    )

    if df.empty:
        return None

    return int(df.iloc[0]["id"])


# ======================================================
# OPERACIONES DE TESORERÍA
# ======================================================

def registrar_operacion_tesoreria(
    empresa_id=1,
    tipo_operacion="OTRO",
    subtipo="",
    fecha_operacion="",
    fecha_contable="",
    cuenta_tesoreria_id=None,
    medio_pago_id=None,
    tercero_tipo="",
    tercero_id=None,
    tercero_nombre="",
    tercero_cuit="",
    descripcion="",
    referencia_externa="",
    importe=0,
    moneda="ARS",
    estado="CONFIRMADA",
    estado_conciliacion="PENDIENTE",
    origen_modulo="",
    origen_tabla="",
    origen_id=None,
    asiento_id=None,
    usuario_id=None,
    fingerprint=None,
    componentes=None,
    permitir_duplicado=False,
):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    tipo_operacion = normalizar_tipo_operacion(tipo_operacion)
    estado = normalizar_estado_operacion(estado)
    estado_conciliacion = normalizar_estado_conciliacion(estado_conciliacion)

    fecha_operacion = _texto(fecha_operacion)

    if not fecha_operacion:
        raise ValueError("La operación de Tesorería debe tener fecha_operacion.")

    importe = _numero(importe)

    if abs(importe) <= 0.0:
        raise ValueError("La operación de Tesorería debe tener importe distinto de cero.")

    if fingerprint is None:
        fingerprint = construir_fingerprint_operacion(
            empresa_id=empresa_id,
            tipo_operacion=tipo_operacion,
            fecha_operacion=fecha_operacion,
            cuenta_tesoreria_id=cuenta_tesoreria_id,
            importe=importe,
            tercero_cuit=tercero_cuit,
            tercero_nombre=tercero_nombre,
            referencia_externa=referencia_externa,
            origen_modulo=origen_modulo,
            origen_tabla=origen_tabla,
            origen_id=origen_id,
        )

    importe_conciliado = 0.0
    importe_pendiente = abs(importe)

    conn = conectar()
    cur = conn.cursor()

    try:
        existente_id = _obtener_id_por_fingerprint(cur, empresa_id, fingerprint)

        if existente_id is not None and not permitir_duplicado:
            return {
                "ok": True,
                "creada": False,
                "duplicada": True,
                "operacion_id": existente_id,
                "mensaje": "Operación de Tesorería duplicada omitida por fingerprint.",
            }

        cur.execute(
            """
            INSERT INTO tesoreria_operaciones
            (
                empresa_id,
                tipo_operacion,
                subtipo,
                fecha_operacion,
                fecha_contable,
                cuenta_tesoreria_id,
                medio_pago_id,
                tercero_tipo,
                tercero_id,
                tercero_nombre,
                tercero_cuit,
                descripcion,
                referencia_externa,
                importe,
                moneda,
                estado,
                estado_conciliacion,
                importe_conciliado,
                importe_pendiente,
                asiento_id,
                origen_modulo,
                origen_tabla,
                origen_id,
                fingerprint,
                usuario_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                tipo_operacion,
                _texto(subtipo),
                fecha_operacion,
                _texto(fecha_contable) or fecha_operacion,
                cuenta_tesoreria_id,
                medio_pago_id,
                _texto_upper(tercero_tipo),
                tercero_id,
                _texto(tercero_nombre),
                _texto(tercero_cuit),
                _texto(descripcion),
                _texto(referencia_externa),
                importe,
                _texto_upper(moneda or "ARS"),
                estado,
                estado_conciliacion,
                importe_conciliado,
                importe_pendiente,
                asiento_id,
                _texto_upper(origen_modulo),
                _texto(origen_tabla),
                origen_id,
                fingerprint,
                usuario_id,
            ),
        )

        operacion_id = int(cur.lastrowid)

        for componente in componentes or []:
            cur.execute(
                """
                INSERT INTO tesoreria_operaciones_componentes
                (
                    empresa_id,
                    operacion_id,
                    tipo_componente,
                    cuenta_contable_codigo,
                    cuenta_contable_nombre,
                    importe,
                    descripcion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    operacion_id,
                    _texto_upper(componente.get("tipo_componente")),
                    _texto(componente.get("cuenta_contable_codigo")),
                    _texto(componente.get("cuenta_contable_nombre")),
                    _numero(componente.get("importe")),
                    _texto(componente.get("descripcion")),
                ),
            )

        _registrar_auditoria(
            cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CREAR",
            entidad="tesoreria_operaciones",
            entidad_id=operacion_id,
            valor_nuevo={
                "tipo_operacion": tipo_operacion,
                "fecha_operacion": fecha_operacion,
                "importe": importe,
                "estado": estado,
                "estado_conciliacion": estado_conciliacion,
            },
            motivo="Alta de operación de tesorería.",
        )

        conn.commit()

        return {
            "ok": True,
            "creada": True,
            "duplicada": False,
            "operacion_id": operacion_id,
            "mensaje": "Operación de Tesorería registrada.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def obtener_operacion_tesoreria(operacion_id, empresa_id=1):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    operacion_id = int(operacion_id)

    df = ejecutar_query(
        """
        SELECT *
        FROM tesoreria_operaciones
        WHERE empresa_id = ?
          AND id = ?
        """,
        (empresa_id, operacion_id),
        fetch=True,
    )

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def listar_operaciones_pendientes_conciliacion(
    empresa_id=1,
    cuenta_tesoreria_id=None,
    tipo_operacion=None,
):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)

    filtros = [
        "empresa_id = ?",
        "estado <> 'ANULADA'",
        "estado_conciliacion IN ('PENDIENTE', 'SUGERIDA', 'PARCIAL')",
    ]

    params = [empresa_id]

    if cuenta_tesoreria_id is not None:
        filtros.append("cuenta_tesoreria_id = ?")
        params.append(int(cuenta_tesoreria_id))

    if tipo_operacion:
        filtros.append("tipo_operacion = ?")
        params.append(normalizar_tipo_operacion(tipo_operacion))

    where_sql = " AND ".join(filtros)

    return ejecutar_query(
        f"""
        SELECT *
        FROM tesoreria_operaciones
        WHERE {where_sql}
        ORDER BY fecha_operacion, id
        """,
        tuple(params),
        fetch=True,
    )


def actualizar_estado_conciliacion_operacion(
    operacion_id,
    empresa_id=1,
    importe_conciliado=0,
    usuario_id=None,
):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    operacion_id = int(operacion_id)
    importe_conciliado = abs(_numero(importe_conciliado))

    conn = conectar()
    cur = conn.cursor()

    try:
        operacion = _obtener_operacion_dict(cur, empresa_id, operacion_id)

        if operacion is None:
            return {
                "ok": False,
                "mensaje": "No se encontró la operación de Tesorería.",
            }

        if operacion.get("estado") == "ANULADA":
            return {
                "ok": False,
                "mensaje": "No se puede conciliar una operación anulada.",
            }

        importe_total = abs(_numero(operacion.get("importe")))
        pendiente = max(round(importe_total - importe_conciliado, 2), 0.0)

        if pendiente <= 0.01:
            estado_conciliacion = "CONCILIADA"
            pendiente = 0.0
        elif importe_conciliado > 0:
            estado_conciliacion = "PARCIAL"
        else:
            estado_conciliacion = "PENDIENTE"

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
                pendiente,
                estado_conciliacion,
                empresa_id,
                operacion_id,
            ),
        )

        _registrar_auditoria(
            cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="ACTUALIZAR_CONCILIACION",
            entidad="tesoreria_operaciones",
            entidad_id=operacion_id,
            valor_anterior=operacion,
            valor_nuevo={
                "importe_conciliado": importe_conciliado,
                "importe_pendiente": pendiente,
                "estado_conciliacion": estado_conciliacion,
            },
            motivo="Actualización de estado de conciliación.",
        )

        conn.commit()

        return {
            "ok": True,
            "estado_conciliacion": estado_conciliacion,
            "importe_pendiente": pendiente,
            "mensaje": "Estado de conciliación actualizado.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def anular_operacion_tesoreria(
    operacion_id,
    empresa_id=1,
    usuario_id=None,
    motivo="",
    permitir_conciliada=False,
):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    operacion_id = int(operacion_id)
    motivo = _texto(motivo)

    if not motivo:
        return {
            "ok": False,
            "mensaje": "Para anular una operación se debe indicar un motivo.",
        }

    conn = conectar()
    cur = conn.cursor()

    try:
        operacion = _obtener_operacion_dict(cur, empresa_id, operacion_id)

        if operacion is None:
            return {
                "ok": False,
                "mensaje": "No se encontró la operación de Tesorería.",
            }

        if operacion.get("estado") == "ANULADA":
            return {
                "ok": True,
                "anulada": False,
                "mensaje": "La operación ya estaba anulada.",
            }

        if operacion.get("estado_conciliacion") == "CONCILIADA" and not permitir_conciliada:
            return {
                "ok": False,
                "mensaje": (
                    "La operación está conciliada. "
                    "Primero debe desconciliarse o anularse con permiso administrador."
                ),
            }

        cur.execute(
            """
            UPDATE tesoreria_operaciones
            SET estado = 'ANULADA',
                motivo_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                motivo,
                empresa_id,
                operacion_id,
            ),
        )

        _registrar_auditoria(
            cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="ANULAR",
            entidad="tesoreria_operaciones",
            entidad_id=operacion_id,
            valor_anterior=operacion,
            valor_nuevo={
                "estado": "ANULADA",
                "motivo_anulacion": motivo,
            },
            motivo=motivo,
        )

        conn.commit()

        return {
            "ok": True,
            "anulada": True,
            "mensaje": "Operación de Tesorería anulada.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()