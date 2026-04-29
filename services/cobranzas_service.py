import hashlib
import json
from pathlib import Path

import pandas as pd

from database import conectar, ejecutar_query
from services import tesoreria_service, cajas_service


# ======================================================
# CONSTANTES
# ======================================================

CUENTA_DEUDORES_VENTAS = "DEUDORES POR VENTAS"

CUENTAS_RETENCIONES_DEFAULT = {
    "IIBB": "RETENCIONES IIBB SUFRIDAS",
    "GANANCIAS": "RETENCIONES GANANCIAS SUFRIDAS",
    "IVA": "RETENCIONES IVA SUFRIDAS",
    "SUSS": "RETENCIONES SUSS SUFRIDAS",
    "OTRA": "OTRAS RETENCIONES SUFRIDAS",
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


def _ruta_migracion_cobranzas():
    return Path(__file__).resolve().parents[1] / "migrations" / "010_cobranzas.sql"


def _ejecutar_script_sql(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la migración de Cobranzas: {ruta}")

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


def inicializar_cobranzas():
    """
    Inicializa la estructura de Cobranzas y asegura Tesorería.
    No borra datos.
    """

    tesoreria_service.inicializar_tesoreria()
    _ejecutar_script_sql(_ruta_migracion_cobranzas())
    return True


def _columnas_tabla(conn, tabla):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)
        return df["name"].tolist()
    except Exception:
        return []


def _tabla_tiene_columna(conn, tabla, columna):
    return columna in _columnas_tabla(conn, tabla)


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
        INSERT INTO cobranzas_auditoria
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


def _proximo_asiento_cur(cur):
    cur.execute("""
        SELECT MAX(id_asiento)
        FROM libro_diario
    """)

    valor = cur.fetchone()[0]

    if valor is None:
        return 1

    return int(valor) + 1


def _insertar_libro_diario(
    cur,
    empresa_id,
    asiento_id,
    fecha,
    cuenta,
    debe,
    haber,
    glosa,
    origen,
    archivo="",
    origen_tabla="",
    origen_id=None,
    comprobante_clave="",
    estado="CONTABILIZADO",
    usuario_id=None,
):
    columnas = [
        "id_asiento",
        "fecha",
        "cuenta",
        "debe",
        "haber",
        "glosa",
        "origen",
        "archivo",
    ]

    valores = [
        asiento_id,
        fecha,
        cuenta,
        round(float(debe), 2),
        round(float(haber), 2),
        glosa,
        origen,
        archivo,
    ]

    columnas_extra = {
        "empresa_id": empresa_id,
        "origen_tabla": origen_tabla,
        "origen_id": origen_id,
        "comprobante_clave": comprobante_clave,
        "estado": estado,
        "usuario_creacion": usuario_id,
    }

    for columna, valor in columnas_extra.items():
        if _tabla_tiene_columna(cur.connection, "libro_diario", columna):
            columnas.append(columna)
            valores.append(valor)

    placeholders = ", ".join(["?"] * len(columnas))
    columnas_sql = ", ".join(columnas)

    cur.execute(
        f"""
        INSERT INTO libro_diario
        ({columnas_sql})
        VALUES ({placeholders})
        """,
        tuple(valores),
    )


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


def _obtener_medio_pago_id_cur(cur, empresa_id, codigo):
    codigo = _texto_upper(codigo or "EFECTIVO")

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

    for cod, nombre, tipo, requiere_referencia in medios:
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
                cod,
                nombre,
                tipo,
                requiere_referencia,
            ),
        )

    cur.execute(
        """
        SELECT id
        FROM tesoreria_medios_pago
        WHERE empresa_id = ?
          AND codigo = ?
          AND activo = 1
        """,
        (
            empresa_id,
            codigo,
        ),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    return int(fila[0])


def _obtener_cuenta_tesoreria(cur, empresa_id, cuenta_tesoreria_id):
    cur.execute(
        """
        SELECT *
        FROM tesoreria_cuentas
        WHERE empresa_id = ?
          AND id = ?
          AND activo = 1
        """,
        (
            empresa_id,
            cuenta_tesoreria_id,
        ),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _nombre_cuenta_contable_tesoreria(cuenta):
    if not cuenta:
        return "CAJA"

    cuenta_contable = _texto(cuenta.get("cuenta_contable_nombre"))

    if cuenta_contable:
        return cuenta_contable

    tipo = _texto_upper(cuenta.get("tipo_cuenta"))
    nombre = _texto(cuenta.get("nombre"))

    if tipo == "BANCO":
        entidad = _texto(cuenta.get("entidad"))
        if entidad and nombre:
            return f"{entidad} - {nombre}"
        if nombre:
            return nombre
        return "BANCO"

    if tipo == "CAJA":
        return nombre or "CAJA"

    return nombre or tipo or "TESORERIA"


def _construir_fingerprint_cobranza(
    empresa_id,
    fecha_cobranza,
    cliente,
    cuit,
    cuenta_tesoreria_id,
    importe_recibido,
    importe_retenciones,
    referencia_externa,
    imputaciones,
):
    partes_imputaciones = []

    for imp in imputaciones or []:
        partes_imputaciones.append(
            "|".join([
                _texto_upper(imp.get("tipo_comprobante")),
                _texto_upper(imp.get("numero_comprobante")),
                f"{_numero(imp.get('importe_imputado')):.2f}",
            ])
        )

    base = "|".join([
        str(int(empresa_id or 1)),
        _texto(fecha_cobranza),
        _texto_upper(cliente),
        _texto_upper(cuit),
        str(cuenta_tesoreria_id or ""),
        f"{_numero(importe_recibido):.2f}",
        f"{_numero(importe_retenciones):.2f}",
        _texto_upper(referencia_externa),
        "||".join(partes_imputaciones),
    ])

    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _insertar_operacion_tesoreria_cobranza(
    cur,
    empresa_id,
    cobranza_id,
    fecha_cobranza,
    fecha_contable,
    cuenta_tesoreria_id,
    medio_pago_id,
    cliente,
    cuit,
    descripcion,
    referencia_externa,
    importe_recibido,
    usuario_id,
    componentes,
):
    fingerprint = tesoreria_service.construir_fingerprint_operacion(
        empresa_id=empresa_id,
        tipo_operacion="COBRANZA",
        fecha_operacion=fecha_cobranza,
        cuenta_tesoreria_id=cuenta_tesoreria_id,
        importe=importe_recibido,
        tercero_cuit=cuit,
        tercero_nombre=cliente,
        referencia_externa=referencia_externa,
        origen_modulo="COBRANZAS",
        origen_tabla="cobranzas",
        origen_id=cobranza_id,
    )

    cur.execute(
        """
        SELECT id
        FROM tesoreria_operaciones
        WHERE empresa_id = ?
          AND fingerprint = ?
        """,
        (
            empresa_id,
            fingerprint,
        ),
    )

    existente = cur.fetchone()

    if existente:
        return int(existente[0])

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
            origen_modulo,
            origen_tabla,
            origen_id,
            fingerprint,
            usuario_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id,
            "COBRANZA",
            "COBRO_CLIENTE",
            fecha_cobranza,
            fecha_contable or fecha_cobranza,
            cuenta_tesoreria_id,
            medio_pago_id,
            "CLIENTE",
            cliente,
            cuit,
            descripcion,
            referencia_externa,
            importe_recibido,
            "ARS",
            "CONFIRMADA",
            "PENDIENTE",
            0,
            abs(importe_recibido),
            "COBRANZAS",
            "cobranzas",
            cobranza_id,
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

    return operacion_id


def _obtener_cobranza_dict(cur, empresa_id, cobranza_id):
    cur.execute(
        """
        SELECT *
        FROM cobranzas
        WHERE empresa_id = ?
          AND id = ?
        """,
        (
            empresa_id,
            cobranza_id,
        ),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


# ======================================================
# CONSULTAS CUENTA CORRIENTE
# ======================================================

def obtener_clientes_con_saldo_pendiente(empresa_id=1):
    inicializar_cobranzas()

    empresa_id = int(empresa_id or 1)

    return ejecutar_query(
        """
        SELECT
            cliente,
            cuit,
            COUNT(*) AS movimientos,
            ROUND(SUM(debe), 2) AS debe,
            ROUND(SUM(haber), 2) AS haber,
            ROUND(SUM(debe - haber), 2) AS saldo
        FROM cuenta_corriente_clientes
        WHERE empresa_id = ?
        GROUP BY cliente, cuit
        HAVING ROUND(SUM(debe - haber), 2) > 0.01
        ORDER BY ROUND(SUM(debe - haber), 2) DESC, cliente
        """,
        (
            empresa_id,
        ),
        fetch=True,
    )


def obtener_comprobantes_pendientes_cliente(empresa_id=1, cliente="", cuit=""):
    inicializar_cobranzas()

    empresa_id = int(empresa_id or 1)
    cliente = _texto(cliente)
    cuit = _texto(cuit)

    filtros = ["empresa_id = ?"]
    params = [empresa_id]

    if cuit:
        filtros.append("cuit = ?")
        params.append(cuit)
    else:
        filtros.append("cliente = ?")
        params.append(cliente)

    where_sql = " AND ".join(filtros)

    return ejecutar_query(
        f"""
        SELECT
            MIN(id) AS cuenta_corriente_id,
            MIN(fecha) AS fecha,
            cliente,
            cuit,
            tipo AS tipo_comprobante,
            numero AS numero_comprobante,
            ROUND(SUM(debe), 2) AS debe,
            ROUND(SUM(haber), 2) AS haber,
            ROUND(SUM(debe - haber), 2) AS saldo
        FROM cuenta_corriente_clientes
        WHERE {where_sql}
        GROUP BY cliente, cuit, tipo, numero
        HAVING ROUND(SUM(debe - haber), 2) > 0.01
        ORDER BY MIN(fecha), numero
        """,
        tuple(params),
        fetch=True,
    )


def obtener_cuentas_cobranza(empresa_id=1):
    inicializar_cobranzas()

    empresa_id = int(empresa_id or 1)

    return ejecutar_query(
        """
        SELECT
            id,
            tipo_cuenta,
            nombre,
            entidad,
            numero_cuenta,
            moneda,
            cuenta_contable_nombre
        FROM tesoreria_cuentas
        WHERE empresa_id = ?
          AND activo = 1
          AND tipo_cuenta IN ('BANCO', 'CAJA', 'BILLETERA', 'VALORES')
        ORDER BY tipo_cuenta, nombre
        """,
        (
            empresa_id,
        ),
        fetch=True,
    )


def obtener_historial_cobranzas(empresa_id=1, incluir_anuladas=True):
    inicializar_cobranzas()

    empresa_id = int(empresa_id or 1)

    if incluir_anuladas:
        filtro_estado = ""
        params = (empresa_id,)
    else:
        filtro_estado = "AND c.estado <> 'ANULADA'"
        params = (empresa_id,)

    return ejecutar_query(
        f"""
        SELECT
            c.id,
            c.numero_recibo,
            c.fecha_cobranza,
            c.cliente,
            c.cuit,
            tc.tipo_cuenta,
            tc.nombre AS cuenta_tesoreria,
            mp.nombre AS medio_pago,
            c.importe_recibido,
            c.importe_retenciones,
            c.importe_total_aplicado,
            c.importe_imputado,
            c.importe_a_cuenta,
            c.referencia_externa,
            c.estado,
            c.asiento_id,
            c.tesoreria_operacion_id,
            c.fecha_creacion
        FROM cobranzas c
        LEFT JOIN tesoreria_cuentas tc
               ON tc.id = c.cuenta_tesoreria_id
              AND tc.empresa_id = c.empresa_id
        LEFT JOIN tesoreria_medios_pago mp
               ON mp.id = c.medio_pago_id
              AND mp.empresa_id = c.empresa_id
        WHERE c.empresa_id = ?
        {filtro_estado}
        ORDER BY c.id DESC
        """,
        params,
        fetch=True,
    )


# ======================================================
# REGISTRO PRINCIPAL
# ======================================================

def registrar_cobranza(
    empresa_id=1,
    fecha_cobranza="",
    fecha_contable="",
    cliente="",
    cuit="",
    cuenta_tesoreria_id=None,
    medio_pago_codigo="EFECTIVO",
    importe_recibido=0,
    referencia_externa="",
    descripcion="",
    imputaciones=None,
    retenciones=None,
    usuario_id=None,
):
    inicializar_cobranzas()

    empresa_id = int(empresa_id or 1)
    fecha_cobranza = _texto(fecha_cobranza)
    fecha_contable = _texto(fecha_contable) or fecha_cobranza
    cliente = _texto(cliente)
    cuit = _texto(cuit)
    referencia_externa = _texto(referencia_externa)
    descripcion = _texto(descripcion)
    medio_pago_codigo = _texto_upper(medio_pago_codigo or "EFECTIVO")

    if not fecha_cobranza:
        return {
            "ok": False,
            "mensaje": "La cobranza debe tener fecha.",
        }

    if not cliente and not cuit:
        return {
            "ok": False,
            "mensaje": "La cobranza debe tener cliente o CUIT.",
        }

    if cuenta_tesoreria_id is None:
        return {
            "ok": False,
            "mensaje": "La cobranza debe tener cuenta de destino.",
        }

    importe_recibido = _numero(importe_recibido)

    retenciones_normalizadas = []

    for ret in retenciones or []:
        importe_ret = _numero(ret.get("importe"))
        if importe_ret <= 0:
            continue

        tipo_retencion = _texto_upper(ret.get("tipo_retencion") or ret.get("tipo") or "OTRA")
        cuenta_nombre = _texto(ret.get("cuenta_contable_nombre"))

        if not cuenta_nombre:
            cuenta_nombre = CUENTAS_RETENCIONES_DEFAULT.get(tipo_retencion, CUENTAS_RETENCIONES_DEFAULT["OTRA"])

        retenciones_normalizadas.append({
            "tipo_retencion": tipo_retencion,
            "descripcion": _texto(ret.get("descripcion")) or tipo_retencion,
            "cuenta_contable_codigo": _texto(ret.get("cuenta_contable_codigo")),
            "cuenta_contable_nombre": cuenta_nombre,
            "importe": importe_ret,
        })

    importe_retenciones = round(sum(r["importe"] for r in retenciones_normalizadas), 2)
    importe_total_aplicado = round(importe_recibido + importe_retenciones, 2)

    if importe_total_aplicado <= 0:
        return {
            "ok": False,
            "mensaje": "La cobranza debe tener importe recibido o retenciones.",
        }

    imputaciones_normalizadas = []

    for imp in imputaciones or []:
        importe_imp = _numero(imp.get("importe_imputado") or imp.get("importe"))
        if importe_imp <= 0:
            continue

        imputaciones_normalizadas.append({
            "cuenta_corriente_id": imp.get("cuenta_corriente_id"),
            "tipo_comprobante": _texto(imp.get("tipo_comprobante") or imp.get("tipo")),
            "numero_comprobante": _texto(imp.get("numero_comprobante") or imp.get("numero")),
            "importe_imputado": importe_imp,
        })

    importe_imputado = round(sum(i["importe_imputado"] for i in imputaciones_normalizadas), 2)

    if importe_imputado - importe_total_aplicado > 0.01:
        return {
            "ok": False,
            "mensaje": (
                "El importe imputado no puede superar el total aplicado "
                "(importe recibido + retenciones)."
            ),
        }

    importe_a_cuenta = round(max(importe_total_aplicado - importe_imputado, 0), 2)

    fingerprint = _construir_fingerprint_cobranza(
        empresa_id=empresa_id,
        fecha_cobranza=fecha_cobranza,
        cliente=cliente,
        cuit=cuit,
        cuenta_tesoreria_id=cuenta_tesoreria_id,
        importe_recibido=importe_recibido,
        importe_retenciones=importe_retenciones,
        referencia_externa=referencia_externa,
        imputaciones=imputaciones_normalizadas,
    )

    if medio_pago_codigo == "EFECTIVO":
        cajas_service.inicializar_cajas()

    conn = conectar()
    cur = conn.cursor()

    try:
        cuenta = _obtener_cuenta_tesoreria(cur, empresa_id, cuenta_tesoreria_id)

        if cuenta is None:
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "No se encontró la cuenta de Tesorería seleccionada.",
            }

        tipo_cuenta_tesoreria = _texto_upper(cuenta.get("tipo_cuenta"))

        if medio_pago_codigo == "EFECTIVO" and tipo_cuenta_tesoreria != "CAJA":
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "El medio de pago EFECTIVO debe usar una cuenta tipo CAJA.",
            }

        if medio_pago_codigo != "EFECTIVO" and tipo_cuenta_tesoreria == "CAJA":
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "Solo las cobranzas en EFECTIVO pueden ingresar a una cuenta tipo CAJA. Tarjeta, billetera y transferencia deben ir a Banco/Tesorería o cuenta puente.",
            }

        medio_pago_id = _obtener_medio_pago_id_cur(cur, empresa_id, medio_pago_codigo)

        if medio_pago_id is None:
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "No se encontró el medio de pago seleccionado.",
            }

        cur.execute(
            """
            SELECT id
            FROM cobranzas
            WHERE empresa_id = ?
              AND fingerprint = ?
            """,
            (
                empresa_id,
                fingerprint,
            ),
        )

        existente = cur.fetchone()

        if existente:
            conn.rollback()
            return {
                "ok": True,
                "creada": False,
                "duplicada": True,
                "cobranza_id": int(existente[0]),
                "mensaje": "Cobranza duplicada omitida por fingerprint.",
            }

        cur.execute(
            """
            INSERT INTO cobranzas
            (
                empresa_id,
                fecha_cobranza,
                fecha_contable,
                cliente,
                cuit,
                cuenta_tesoreria_id,
                medio_pago_id,
                importe_recibido,
                importe_retenciones,
                importe_total_aplicado,
                importe_imputado,
                importe_a_cuenta,
                referencia_externa,
                descripcion,
                estado,
                usuario_id,
                fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMADA', ?, ?)
            """,
            (
                empresa_id,
                fecha_cobranza,
                fecha_contable,
                cliente,
                cuit,
                cuenta_tesoreria_id,
                medio_pago_id,
                importe_recibido,
                importe_retenciones,
                importe_total_aplicado,
                importe_imputado,
                importe_a_cuenta,
                referencia_externa,
                descripcion,
                usuario_id,
                fingerprint,
            ),
        )

        cobranza_id = int(cur.lastrowid)
        numero_recibo = f"RC-{cobranza_id:08d}"

        cur.execute(
            """
            UPDATE cobranzas
            SET numero_recibo = ?
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                numero_recibo,
                empresa_id,
                cobranza_id,
            ),
        )

        for imp in imputaciones_normalizadas:
            cur.execute(
                """
                INSERT INTO cobranzas_imputaciones
                (
                    empresa_id,
                    cobranza_id,
                    cuenta_corriente_id,
                    tipo_comprobante,
                    numero_comprobante,
                    importe_imputado
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    cobranza_id,
                    imp.get("cuenta_corriente_id"),
                    imp["tipo_comprobante"],
                    imp["numero_comprobante"],
                    imp["importe_imputado"],
                ),
            )

        for ret in retenciones_normalizadas:
            cur.execute(
                """
                INSERT INTO cobranzas_retenciones
                (
                    empresa_id,
                    cobranza_id,
                    tipo_retencion,
                    descripcion,
                    cuenta_contable_codigo,
                    cuenta_contable_nombre,
                    importe
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    cobranza_id,
                    ret["tipo_retencion"],
                    ret["descripcion"],
                    ret["cuenta_contable_codigo"],
                    ret["cuenta_contable_nombre"],
                    ret["importe"],
                ),
            )

        _insertar_cuenta_corriente_cliente(
            cur=cur,
            empresa_id=empresa_id,
            fecha=fecha_cobranza,
            cliente=cliente,
            cuit=cuit,
            tipo="COBRANZA",
            numero=numero_recibo,
            debe=0,
            haber=importe_total_aplicado,
            origen="COBRANZAS",
            archivo="",
        )

        asiento_id = _proximo_asiento_cur(cur)
        cuenta_tesoreria_nombre = _nombre_cuenta_contable_tesoreria(cuenta)

        glosa = descripcion or f"Cobranza {numero_recibo} - {cliente}"
        comprobante_clave = f"COBRANZA|{numero_recibo}"

        if importe_recibido > 0:
            _insertar_libro_diario(
                cur=cur,
                empresa_id=empresa_id,
                asiento_id=asiento_id,
                fecha=fecha_contable,
                cuenta=cuenta_tesoreria_nombre,
                debe=importe_recibido,
                haber=0,
                glosa=glosa,
                origen="COBRANZAS",
                origen_tabla="cobranzas",
                origen_id=cobranza_id,
                comprobante_clave=comprobante_clave,
                usuario_id=usuario_id,
            )

        for ret in retenciones_normalizadas:
            _insertar_libro_diario(
                cur=cur,
                empresa_id=empresa_id,
                asiento_id=asiento_id,
                fecha=fecha_contable,
                cuenta=ret["cuenta_contable_nombre"],
                debe=ret["importe"],
                haber=0,
                glosa=glosa,
                origen="COBRANZAS",
                origen_tabla="cobranzas",
                origen_id=cobranza_id,
                comprobante_clave=comprobante_clave,
                usuario_id=usuario_id,
            )

        _insertar_libro_diario(
            cur=cur,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            fecha=fecha_contable,
            cuenta=CUENTA_DEUDORES_VENTAS,
            debe=0,
            haber=importe_total_aplicado,
            glosa=glosa,
            origen="COBRANZAS",
            origen_tabla="cobranzas",
            origen_id=cobranza_id,
            comprobante_clave=comprobante_clave,
            usuario_id=usuario_id,
        )

        componentes_tesoreria = []

        for ret in retenciones_normalizadas:
            componentes_tesoreria.append({
                "tipo_componente": "RETENCION_SUFRIDA",
                "cuenta_contable_codigo": ret["cuenta_contable_codigo"],
                "cuenta_contable_nombre": ret["cuenta_contable_nombre"],
                "importe": ret["importe"],
                "descripcion": ret["descripcion"],
            })

        tesoreria_operacion_id = None

        if importe_recibido > 0:
            tesoreria_operacion_id = _insertar_operacion_tesoreria_cobranza(
                cur=cur,
                empresa_id=empresa_id,
                cobranza_id=cobranza_id,
                fecha_cobranza=fecha_cobranza,
                fecha_contable=fecha_contable,
                cuenta_tesoreria_id=cuenta_tesoreria_id,
                medio_pago_id=medio_pago_id,
                cliente=cliente,
                cuit=cuit,
                descripcion=glosa,
                referencia_externa=referencia_externa,
                importe_recibido=importe_recibido,
                usuario_id=usuario_id,
                componentes=componentes_tesoreria,
            )

        caja_movimiento_id = None

        if importe_recibido > 0 and medio_pago_codigo == "EFECTIVO":
            caja_movimiento_id = cajas_service.registrar_cobranza_efectivo_en_caja_cur(
                cur=cur,
                empresa_id=empresa_id,
                caja_id=cuenta_tesoreria_id,
                caja_nombre=_texto(cuenta.get("nombre")) or "Caja",
                fecha=fecha_cobranza,
                cliente=cliente,
                cuit=cuit,
                importe=importe_recibido,
                numero_recibo=numero_recibo,
                cobranza_id=cobranza_id,
                tesoreria_operacion_id=tesoreria_operacion_id,
                usuario_id=usuario_id,
            )

        cur.execute(
            """
            UPDATE cobranzas
            SET asiento_id = ?,
                tesoreria_operacion_id = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                asiento_id,
                tesoreria_operacion_id,
                empresa_id,
                cobranza_id,
            ),
        )


        _registrar_auditoria(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CREAR",
            entidad="cobranzas",
            entidad_id=cobranza_id,
            valor_nuevo={
                "numero_recibo": numero_recibo,
                "cliente": cliente,
                "cuit": cuit,
                "importe_recibido": importe_recibido,
                "importe_retenciones": importe_retenciones,
                "importe_total_aplicado": importe_total_aplicado,
                "importe_imputado": importe_imputado,
                "importe_a_cuenta": importe_a_cuenta,
                "asiento_id": asiento_id,
                "tesoreria_operacion_id": tesoreria_operacion_id,
                "caja_movimiento_id": caja_movimiento_id,
            },
            motivo="Alta de cobranza.",
        )

        conn.commit()

        return {
            "ok": True,
            "creada": True,
            "duplicada": False,
            "cobranza_id": cobranza_id,
            "numero_recibo": numero_recibo,
            "asiento_id": asiento_id,
            "tesoreria_operacion_id": tesoreria_operacion_id,
            "caja_movimiento_id": caja_movimiento_id,
            "importe_recibido": importe_recibido,
            "importe_retenciones": importe_retenciones,
            "importe_total_aplicado": importe_total_aplicado,
            "importe_imputado": importe_imputado,
            "importe_a_cuenta": importe_a_cuenta,
            "mensaje": "Cobranza registrada correctamente.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ======================================================
# ANULACIÓN CONTROLADA
# ======================================================

def anular_cobranza(
    cobranza_id,
    empresa_id=1,
    usuario_id=None,
    motivo="",
    permitir_conciliada=False,
):
    inicializar_cobranzas()

    empresa_id = int(empresa_id or 1)
    cobranza_id = int(cobranza_id)
    motivo = _texto(motivo)

    if not motivo:
        return {
            "ok": False,
            "mensaje": "Para anular una cobranza se debe indicar un motivo.",
        }

    conn = conectar()
    cur = conn.cursor()

    try:
        cobranza = _obtener_cobranza_dict(cur, empresa_id, cobranza_id)

        if cobranza is None:
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "No se encontró la cobranza.",
            }

        if cobranza.get("estado") == "ANULADA":
            conn.rollback()
            return {
                "ok": True,
                "anulada": False,
                "mensaje": "La cobranza ya estaba anulada.",
            }

        tesoreria_operacion_id = cobranza.get("tesoreria_operacion_id")

        if tesoreria_operacion_id:
            cur.execute(
                """
                SELECT estado_conciliacion
                FROM tesoreria_operaciones
                WHERE empresa_id = ?
                  AND id = ?
                """,
                (
                    empresa_id,
                    tesoreria_operacion_id,
                ),
            )

            fila = cur.fetchone()

            if fila and fila[0] == "CONCILIADA" and not permitir_conciliada:
                conn.rollback()
                return {
                    "ok": False,
                    "mensaje": (
                        "La cobranza está conciliada. "
                        "Primero debe desconciliarse o anularse con permiso administrador."
                    ),
                }

        fecha = _texto(cobranza.get("fecha_contable")) or _texto(cobranza.get("fecha_cobranza"))
        cliente = _texto(cobranza.get("cliente"))
        cuit = _texto(cobranza.get("cuit"))
        numero_recibo = _texto(cobranza.get("numero_recibo"))
        importe_recibido = _numero(cobranza.get("importe_recibido"))
        importe_total_aplicado = _numero(cobranza.get("importe_total_aplicado"))

        cur.execute(
            """
            SELECT *
            FROM cobranzas_retenciones
            WHERE empresa_id = ?
              AND cobranza_id = ?
            ORDER BY id
            """,
            (
                empresa_id,
                cobranza_id,
            ),
        )

        filas_retenciones = cur.fetchall()
        columnas_retenciones = [col[0] for col in cur.description]
        retenciones = [dict(zip(columnas_retenciones, fila)) for fila in filas_retenciones]

        cur.execute(
            """
            SELECT *
            FROM tesoreria_cuentas
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                empresa_id,
                cobranza.get("cuenta_tesoreria_id"),
            ),
        )

        fila_cuenta = cur.fetchone()

        if fila_cuenta:
            columnas_cuenta = [col[0] for col in cur.description]
            cuenta = dict(zip(columnas_cuenta, fila_cuenta))
        else:
            cuenta = {}

        cuenta_tesoreria_nombre = _nombre_cuenta_contable_tesoreria(cuenta)

        asiento_reverso = _proximo_asiento_cur(cur)
        glosa = f"Anulación cobranza {numero_recibo} - {cliente}"
        comprobante_clave = f"ANULA|COBRANZA|{numero_recibo}"

        _insertar_cuenta_corriente_cliente(
            cur=cur,
            empresa_id=empresa_id,
            fecha=fecha,
            cliente=cliente,
            cuit=cuit,
            tipo="ANULACION COBRANZA",
            numero=numero_recibo,
            debe=importe_total_aplicado,
            haber=0,
            origen="COBRANZAS",
            archivo="",
        )

        _insertar_libro_diario(
            cur=cur,
            empresa_id=empresa_id,
            asiento_id=asiento_reverso,
            fecha=fecha,
            cuenta=CUENTA_DEUDORES_VENTAS,
            debe=importe_total_aplicado,
            haber=0,
            glosa=glosa,
            origen="COBRANZAS",
            origen_tabla="cobranzas",
            origen_id=cobranza_id,
            comprobante_clave=comprobante_clave,
            usuario_id=usuario_id,
        )

        if importe_recibido > 0:
            _insertar_libro_diario(
                cur=cur,
                empresa_id=empresa_id,
                asiento_id=asiento_reverso,
                fecha=fecha,
                cuenta=cuenta_tesoreria_nombre,
                debe=0,
                haber=importe_recibido,
                glosa=glosa,
                origen="COBRANZAS",
                origen_tabla="cobranzas",
                origen_id=cobranza_id,
                comprobante_clave=comprobante_clave,
                usuario_id=usuario_id,
            )

        for ret in retenciones:
            _insertar_libro_diario(
                cur=cur,
                empresa_id=empresa_id,
                asiento_id=asiento_reverso,
                fecha=fecha,
                cuenta=_texto(ret.get("cuenta_contable_nombre")) or CUENTAS_RETENCIONES_DEFAULT["OTRA"],
                debe=0,
                haber=_numero(ret.get("importe")),
                glosa=glosa,
                origen="COBRANZAS",
                origen_tabla="cobranzas",
                origen_id=cobranza_id,
                comprobante_clave=comprobante_clave,
                usuario_id=usuario_id,
            )

        cur.execute(
            """
            UPDATE cobranzas
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
                cobranza_id,
            ),
        )

        if tesoreria_operacion_id:
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
                    tesoreria_operacion_id,
                ),
            )

        # Anula el movimiento automático de Caja vinculado al recibo,
        # solo si la cobranza original había ingresado por una cuenta tipo CAJA.
        numero_recibo_caja = _texto(cobranza.get("numero_recibo"))
        cuenta_tesoreria_id_caja = cobranza.get("cuenta_tesoreria_id")

        if numero_recibo_caja and cuenta_tesoreria_id_caja:
            cuenta_caja = _obtener_cuenta_tesoreria(
                cur,
                empresa_id,
                cuenta_tesoreria_id_caja,
            )

            if cuenta_caja is not None and _texto_upper(cuenta_caja.get("tipo_cuenta")) == "CAJA":
                cajas_service.anular_movimientos_caja_por_referencia_cur(
                    cur=cur,
                    empresa_id=empresa_id,
                    tipo_movimiento="COBRANZA_EFECTIVO",
                    referencia=numero_recibo_caja,
                    motivo=motivo,
                    usuario_id=usuario_id,
                )

        _registrar_auditoria(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="ANULAR",
            entidad="cobranzas",
            entidad_id=cobranza_id,
            valor_anterior=cobranza,
            valor_nuevo={
                "estado": "ANULADA",
                "motivo_anulacion": motivo,
                "asiento_reverso": asiento_reverso,
            },
            motivo=motivo,
        )

        conn.commit()

        return {
            "ok": True,
            "anulada": True,
            "asiento_reverso": asiento_reverso,
            "mensaje": "Cobranza anulada correctamente.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()