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


def _tabla_existe(cur, tabla):
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (tabla,),
    )
    return cur.fetchone() is not None


def _columnas_tabla(cur, tabla):
    if not _tabla_existe(cur, tabla):
        return set()

    cur.execute(f"PRAGMA table_info({tabla})")
    return {fila[1] for fila in cur.fetchall()}


def _fila_a_dict(cur, fila):
    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _valor_activo(valor, default=True):
    if valor is None:
        return default

    if isinstance(valor, bool):
        return valor

    if isinstance(valor, (int, float)):
        return bool(valor)

    texto = _texto_upper(valor)

    if texto in {"0", "NO", "N", "FALSE", "FALSO", "INACTIVO", "INACTIVA", "BAJA", "ANULADO", "ANULADA", "ELIMINADO", "ELIMINADA"}:
        return False

    if texto in {"1", "SI", "SÍ", "S", "TRUE", "VERDADERO", "ACTIVO", "ACTIVA", "VIGENTE", "ALTA"}:
        return True

    return default


def _valor_imputable(valor, default=True):
    if valor is None:
        return default

    if isinstance(valor, bool):
        return valor

    if isinstance(valor, (int, float)):
        return int(valor) != 0

    texto = _texto_upper(valor)

    if texto in {"S", "SI", "SÍ", "1", "TRUE", "VERDADERO", "IMPUTABLE"}:
        return True

    if texto in {"N", "NO", "0", "FALSE", "FALSO", "NO_IMPUTABLE", "AGRUPADORA"}:
        return False

    return default


def _normalizar_uso_operativo(valor):
    texto = _texto_upper(valor)
    return texto.replace(" ", "_").replace("-", "_")


def _usos_esperados_tesoreria(tipo_cuenta):
    tipo = normalizar_tipo_cuenta(tipo_cuenta)

    if tipo == "CAJA":
        return {"CAJA", "CAJA_GENERAL", "FONDO_FIJO", "RECAUDACIONES_A_DEPOSITAR"}

    if tipo == "BANCO":
        return {"BANCO", "BANCO_CUENTA_CORRIENTE", "BANCO_CAJA_AHORRO"}

    if tipo == "BILLETERA":
        return {"BILLETERA", "BILLETERA_VIRTUAL"}

    if tipo == "TARJETA":
        return {"TARJETA", "TARJETA_COBROS", "TARJETA_PUENTE"}

    if tipo == "VALORES":
        return {"VALORES", "VALORES_A_DEPOSITAR", "CHEQUES", "ECHEQ"}

    return set()


def _obtener_cuenta_tesoreria_dict(cur, empresa_id, cuenta_tesoreria_id):
    cur.execute(
        """
        SELECT *
        FROM tesoreria_cuentas
        WHERE empresa_id = ?
          AND id = ?
        """,
        (int(empresa_id or 1), int(cuenta_tesoreria_id)),
    )

    return _fila_a_dict(cur, cur.fetchone())


def _obtener_cuenta_plan_empresa_dict(
    cur,
    empresa_id,
    cuenta_empresa_id=None,
    cuenta_codigo="",
):
    if not _tabla_existe(cur, "plan_cuentas_empresa"):
        return None

    columnas = _columnas_tabla(cur, "plan_cuentas_empresa")

    where = []
    params = []

    if "empresa_id" in columnas:
        where.append("empresa_id = ?")
        params.append(int(empresa_id or 1))

    if cuenta_empresa_id is not None:
        where.append("id = ?")
        params.append(int(cuenta_empresa_id))
    else:
        codigo = _texto(cuenta_codigo)
        if not codigo:
            return None
        where.append("codigo = ?")
        params.append(codigo)

    sql = "SELECT * FROM plan_cuentas_empresa"

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " LIMIT 1"

    cur.execute(sql, tuple(params))
    return _fila_a_dict(cur, cur.fetchone())


def _validar_cuenta_plan_para_tesoreria(cuenta_plan, tipo_cuenta):
    if not cuenta_plan:
        return {
            "ok": False,
            "mensaje": "No se encontró la cuenta contable en el Plan de Cuentas empresa.",
            "advertencias": [],
        }

    advertencias = []

    estado = _texto_upper(cuenta_plan.get("estado") or "ACTIVA")
    if estado in {"ANULADO", "ANULADA", "INACTIVO", "INACTIVA", "BAJA", "ELIMINADO", "ELIMINADA"}:
        return {
            "ok": False,
            "mensaje": "La cuenta contable seleccionada no está activa en el Plan de Cuentas empresa.",
            "advertencias": [],
        }

    if not _valor_imputable(cuenta_plan.get("imputable"), default=True):
        return {
            "ok": False,
            "mensaje": "La cuenta contable seleccionada no es imputable. Tesorería debe vincularse a una cuenta imputable.",
            "advertencias": [],
        }

    uso = _normalizar_uso_operativo(cuenta_plan.get("uso_operativo_sistema"))
    usos_esperados = _usos_esperados_tesoreria(tipo_cuenta)

    if uso and usos_esperados and uso not in usos_esperados:
        advertencias.append(
            "La cuenta elegida está activa e imputable, pero su uso operativo no coincide exactamente "
            f"con el tipo de cuenta de Tesorería ({normalizar_tipo_cuenta(tipo_cuenta)}). "
            "Revise si corresponde desde el Plan de Cuentas."
        )

    return {
        "ok": True,
        "mensaje": "Cuenta contable válida para vincular Tesorería.",
        "advertencias": advertencias,
    }


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


def obtener_cuenta_tesoreria(cuenta_tesoreria_id, empresa_id=1):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    cuenta_tesoreria_id = int(cuenta_tesoreria_id)

    conn = conectar()
    cur = conn.cursor()

    try:
        return _obtener_cuenta_tesoreria_dict(cur, empresa_id, cuenta_tesoreria_id)

    finally:
        conn.close()


def listar_cuentas_tesoreria_sin_cuenta_contable(empresa_id=1):
    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)

    return ejecutar_query(
        """
        SELECT *
        FROM tesoreria_cuentas
        WHERE empresa_id = ?
          AND activo = 1
          AND COALESCE(TRIM(cuenta_contable_codigo), '') = ''
        ORDER BY tipo_cuenta, nombre
        """,
        (empresa_id,),
        fetch=True,
    )


def listar_cuentas_plan_empresa_para_tesoreria(
    empresa_id=1,
    tipo_cuenta=None,
    solo_imputables=True,
    solo_activas=True,
):
    empresa_id = int(empresa_id or 1)

    conn = conectar()
    cur = conn.cursor()

    try:
        if not _tabla_existe(cur, "plan_cuentas_empresa"):
            return pd.DataFrame()

        columnas = _columnas_tabla(cur, "plan_cuentas_empresa")

        requeridas = {"id", "codigo", "nombre"}
        if not requeridas.issubset(columnas):
            return pd.DataFrame()

        where = []
        params = []

        if "empresa_id" in columnas:
            where.append("empresa_id = ?")
            params.append(empresa_id)

        if solo_activas and "estado" in columnas:
            where.append("COALESCE(estado, 'ACTIVA') NOT IN ('ANULADO', 'ANULADA', 'INACTIVO', 'INACTIVA', 'BAJA', 'ELIMINADO', 'ELIMINADA')")

        if solo_imputables and "imputable" in columnas:
            where.append("COALESCE(imputable, 1) = 1")

        if tipo_cuenta:
            tipo = normalizar_tipo_cuenta(tipo_cuenta)
            usos = sorted(_usos_esperados_tesoreria(tipo))
            palabras = {
                "CAJA": ["CAJA", "FONDO FIJO", "RECAUDACIONES"],
                "BANCO": ["BANCO", "CUENTA CORRIENTE", "CAJA DE AHORRO"],
                "BILLETERA": ["BILLETERA", "MERCADO PAGO", "WALLET"],
                "TARJETA": ["TARJETA"],
                "VALORES": ["VALORES", "CHEQUE", "ECHEQ", "DOCUMENTOS"],
                "OTRO": [],
            }.get(tipo, [])

            filtros_tipo = []

            if "uso_operativo_sistema" in columnas and usos:
                placeholders = ", ".join("?" for _ in usos)
                filtros_tipo.append(f"UPPER(COALESCE(uso_operativo_sistema, '')) IN ({placeholders})")
                params.extend(usos)

            for palabra in palabras:
                filtros_tipo.append("UPPER(COALESCE(nombre, '')) LIKE ?")
                params.append(f"%{palabra}%")

            if filtros_tipo:
                where.append("(" + " OR ".join(filtros_tipo) + ")")

        columnas_select = [
            "id",
            "codigo",
            "nombre",
        ]

        for columna in [
            "imputable",
            "estado",
            "cuenta_maestro_id",
            "uso_operativo_sistema",
            "es_cuenta_modelo",
            "es_cuenta_especifica_empresa",
            "banco_nombre",
            "numero_cuenta",
            "moneda",
            "alias",
            "cbu",
        ]:
            if columna in columnas:
                columnas_select.append(columna)

        sql = "SELECT " + ", ".join(columnas_select) + " FROM plan_cuentas_empresa"

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY codigo, nombre"

        return pd.read_sql_query(sql, conn, params=tuple(params))

    finally:
        conn.close()


def vincular_cuenta_tesoreria_a_plan_empresa(
    cuenta_tesoreria_id,
    empresa_id=1,
    cuenta_empresa_id=None,
    cuenta_codigo="",
    usuario_id=None,
    motivo="",
):
    """
    Vincula una cuenta operativa de Tesorería con una cuenta imputable del
    Plan de Cuentas empresa.

    Esta función no crea asientos, no toca movimientos y no modifica módulos
    operativos. Solo completa la relación contable de la cuenta operativa para
    que Cobranzas, Pagos, Caja, Banco y Conciliación usen una cuenta real del
    Plan Maestro FF / Plan empresa.
    """

    inicializar_tesoreria()

    empresa_id = int(empresa_id or 1)
    cuenta_tesoreria_id = int(cuenta_tesoreria_id)
    motivo = _texto(motivo) or "Vinculación de cuenta de Tesorería al Plan de Cuentas empresa."

    conn = conectar()
    cur = conn.cursor()

    try:
        cuenta_tesoreria = _obtener_cuenta_tesoreria_dict(cur, empresa_id, cuenta_tesoreria_id)

        if cuenta_tesoreria is None:
            return {
                "ok": False,
                "mensaje": "No se encontró la cuenta de Tesorería.",
            }

        if not _valor_activo(cuenta_tesoreria.get("activo"), default=True):
            return {
                "ok": False,
                "mensaje": "No se puede vincular una cuenta de Tesorería inactiva.",
            }

        cuenta_plan = _obtener_cuenta_plan_empresa_dict(
            cur,
            empresa_id=empresa_id,
            cuenta_empresa_id=cuenta_empresa_id,
            cuenta_codigo=cuenta_codigo,
        )

        validacion = _validar_cuenta_plan_para_tesoreria(
            cuenta_plan,
            cuenta_tesoreria.get("tipo_cuenta"),
        )

        if not validacion["ok"]:
            return {
                "ok": False,
                "mensaje": validacion["mensaje"],
            }

        codigo = _texto(cuenta_plan.get("codigo"))
        nombre = _texto(cuenta_plan.get("nombre"))

        if not codigo or not nombre:
            return {
                "ok": False,
                "mensaje": "La cuenta del Plan de Cuentas empresa debe tener código y nombre.",
            }

        if (
            _texto(cuenta_tesoreria.get("cuenta_contable_codigo")) == codigo
            and _texto(cuenta_tesoreria.get("cuenta_contable_nombre")) == nombre
        ):
            return {
                "ok": True,
                "actualizada": False,
                "cuenta_tesoreria_id": cuenta_tesoreria_id,
                "cuenta_contable_codigo": codigo,
                "cuenta_contable_nombre": nombre,
                "advertencias": validacion.get("advertencias", []),
                "mensaje": "La cuenta de Tesorería ya estaba vinculada a esa cuenta contable.",
            }

        cur.execute(
            """
            UPDATE tesoreria_cuentas
            SET cuenta_contable_codigo = ?,
                cuenta_contable_nombre = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                codigo,
                nombre,
                empresa_id,
                cuenta_tesoreria_id,
            ),
        )

        cuenta_actualizada = dict(cuenta_tesoreria)
        cuenta_actualizada["cuenta_contable_codigo"] = codigo
        cuenta_actualizada["cuenta_contable_nombre"] = nombre

        _registrar_auditoria(
            cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="VINCULAR_CUENTA_CONTABLE",
            entidad="tesoreria_cuentas",
            entidad_id=cuenta_tesoreria_id,
            valor_anterior=cuenta_tesoreria,
            valor_nuevo=cuenta_actualizada,
            motivo=motivo,
        )

        conn.commit()

        return {
            "ok": True,
            "actualizada": True,
            "cuenta_tesoreria_id": cuenta_tesoreria_id,
            "cuenta_contable_codigo": codigo,
            "cuenta_contable_nombre": nombre,
            "advertencias": validacion.get("advertencias", []),
            "mensaje": "Cuenta de Tesorería vinculada al Plan de Cuentas empresa.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


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