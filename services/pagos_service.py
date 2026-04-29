import hashlib
import json
from pathlib import Path

import pandas as pd

from database import conectar, ejecutar_query
from services import tesoreria_service, cajas_service


# ======================================================
# CONSTANTES
# ======================================================

CUENTA_PROVEEDORES = "PROVEEDORES"

CUENTAS_RETENCIONES_DEFAULT = {
    "IIBB": "RETENCIONES IIBB A DEPOSITAR",
    "GANANCIAS": "RETENCIONES GANANCIAS A DEPOSITAR",
    "IVA": "RETENCIONES IVA A DEPOSITAR",
    "SUSS": "RETENCIONES SUSS A DEPOSITAR",
    "OTRA": "OTRAS RETENCIONES A DEPOSITAR",
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


def _ruta_migracion_pagos():
    return Path(__file__).resolve().parents[1] / "migrations" / "011_pagos.sql"


def _ejecutar_script_sql(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la migración de Pagos: {ruta}")

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


def inicializar_pagos():
    """
    Inicializa la estructura de Pagos y asegura Tesorería.
    No borra datos.
    """

    tesoreria_service.inicializar_tesoreria()
    _ejecutar_script_sql(_ruta_migracion_pagos())
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
        INSERT INTO pagos_auditoria
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


def _obtener_medio_pago_id_cur(cur, empresa_id, codigo):
    codigo = _texto_upper(codigo or "TRANSFERENCIA")

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
        return "BANCO"

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


def _construir_fingerprint_pago(
    empresa_id,
    fecha_pago,
    proveedor,
    cuit,
    cuenta_tesoreria_id,
    importe_pagado,
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
        _texto(fecha_pago),
        _texto_upper(proveedor),
        _texto_upper(cuit),
        str(cuenta_tesoreria_id or ""),
        f"{_numero(importe_pagado):.2f}",
        f"{_numero(importe_retenciones):.2f}",
        _texto_upper(referencia_externa),
        "||".join(partes_imputaciones),
    ])

    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _insertar_operacion_tesoreria_pago(
    cur,
    empresa_id,
    pago_id,
    fecha_pago,
    fecha_contable,
    cuenta_tesoreria_id,
    medio_pago_id,
    proveedor,
    cuit,
    descripcion,
    referencia_externa,
    importe_pagado,
    usuario_id,
    componentes,
):
    importe_tesoreria = -abs(_numero(importe_pagado))

    fingerprint = tesoreria_service.construir_fingerprint_operacion(
        empresa_id=empresa_id,
        tipo_operacion="PAGO",
        fecha_operacion=fecha_pago,
        cuenta_tesoreria_id=cuenta_tesoreria_id,
        importe=importe_tesoreria,
        tercero_cuit=cuit,
        tercero_nombre=proveedor,
        referencia_externa=referencia_externa,
        origen_modulo="PAGOS",
        origen_tabla="pagos",
        origen_id=pago_id,
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
            "PAGO",
            "PAGO_PROVEEDOR",
            fecha_pago,
            fecha_contable or fecha_pago,
            cuenta_tesoreria_id,
            medio_pago_id,
            "PROVEEDOR",
            proveedor,
            cuit,
            descripcion,
            referencia_externa,
            importe_tesoreria,
            "ARS",
            "CONFIRMADA",
            "PENDIENTE",
            0,
            abs(importe_tesoreria),
            "PAGOS",
            "pagos",
            pago_id,
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


def _obtener_pago_dict(cur, empresa_id, pago_id):
    cur.execute(
        """
        SELECT *
        FROM pagos
        WHERE empresa_id = ?
          AND id = ?
        """,
        (
            empresa_id,
            pago_id,
        ),
    )

    fila = cur.fetchone()

    if fila is None:
        return None

    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


# ======================================================
# CONSULTAS CUENTA CORRIENTE PROVEEDORES
# ======================================================

def obtener_proveedores_con_saldo_pendiente(empresa_id=1):
    inicializar_pagos()

    empresa_id = int(empresa_id or 1)

    return ejecutar_query(
        """
        SELECT
            proveedor,
            cuit,
            COUNT(*) AS movimientos,
            ROUND(SUM(debe), 2) AS debe,
            ROUND(SUM(haber), 2) AS haber,
            ROUND(SUM(haber - debe), 2) AS saldo
        FROM cuenta_corriente_proveedores
        WHERE empresa_id = ?
        GROUP BY proveedor, cuit
        HAVING ROUND(SUM(haber - debe), 2) > 0.01
        ORDER BY ROUND(SUM(haber - debe), 2) DESC, proveedor
        """,
        (
            empresa_id,
        ),
        fetch=True,
    )


def obtener_comprobantes_pendientes_proveedor(empresa_id=1, proveedor="", cuit=""):
    inicializar_pagos()

    empresa_id = int(empresa_id or 1)
    proveedor = _texto(proveedor)
    cuit = _texto(cuit)

    filtros = ["empresa_id = ?"]
    params = [empresa_id]

    if cuit:
        filtros.append("cuit = ?")
        params.append(cuit)
    else:
        filtros.append("proveedor = ?")
        params.append(proveedor)

    where_sql = " AND ".join(filtros)

    return ejecutar_query(
        f"""
        SELECT
            MIN(id) AS cuenta_corriente_id,
            MIN(fecha) AS fecha,
            proveedor,
            cuit,
            tipo AS tipo_comprobante,
            numero AS numero_comprobante,
            ROUND(SUM(debe), 2) AS debe,
            ROUND(SUM(haber), 2) AS haber,
            ROUND(SUM(haber - debe), 2) AS saldo
        FROM cuenta_corriente_proveedores
        WHERE {where_sql}
        GROUP BY proveedor, cuit, tipo, numero
        HAVING ROUND(SUM(haber - debe), 2) > 0.01
        ORDER BY MIN(fecha), numero
        """,
        tuple(params),
        fetch=True,
    )


def obtener_cuentas_pago(empresa_id=1):
    inicializar_pagos()

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


def obtener_historial_pagos(empresa_id=1, incluir_anulados=True):
    inicializar_pagos()

    empresa_id = int(empresa_id or 1)

    if incluir_anulados:
        filtro_estado = ""
        params = (empresa_id,)
    else:
        filtro_estado = "AND p.estado <> 'ANULADO'"
        params = (empresa_id,)

    return ejecutar_query(
        f"""
        SELECT
            p.id,
            p.numero_orden_pago,
            p.fecha_pago,
            p.proveedor,
            p.cuit,
            tc.tipo_cuenta,
            tc.nombre AS cuenta_tesoreria,
            mp.nombre AS medio_pago,
            p.importe_pagado,
            p.importe_retenciones,
            p.importe_total_aplicado,
            p.importe_imputado,
            p.importe_a_cuenta,
            p.referencia_externa,
            p.estado,
            p.asiento_id,
            p.tesoreria_operacion_id,
            p.fecha_creacion
        FROM pagos p
        LEFT JOIN tesoreria_cuentas tc
               ON tc.id = p.cuenta_tesoreria_id
              AND tc.empresa_id = p.empresa_id
        LEFT JOIN tesoreria_medios_pago mp
               ON mp.id = p.medio_pago_id
              AND mp.empresa_id = p.empresa_id
        WHERE p.empresa_id = ?
        {filtro_estado}
        ORDER BY p.id DESC
        """,
        params,
        fetch=True,
    )


# ======================================================
# REGISTRO PRINCIPAL
# ======================================================

def registrar_pago(
    empresa_id=1,
    fecha_pago="",
    fecha_contable="",
    proveedor="",
    cuit="",
    cuenta_tesoreria_id=None,
    medio_pago_codigo="TRANSFERENCIA",
    importe_pagado=0,
    referencia_externa="",
    descripcion="",
    imputaciones=None,
    retenciones=None,
    usuario_id=None,
):
    inicializar_pagos()

    empresa_id = int(empresa_id or 1)
    fecha_pago = _texto(fecha_pago)
    fecha_contable = _texto(fecha_contable) or fecha_pago
    proveedor = _texto(proveedor)
    cuit = _texto(cuit)
    referencia_externa = _texto(referencia_externa)
    descripcion = _texto(descripcion)
    medio_pago_codigo = _texto_upper(medio_pago_codigo or "TRANSFERENCIA")

    if not fecha_pago:
        return {
            "ok": False,
            "mensaje": "El pago debe tener fecha.",
        }

    if not proveedor and not cuit:
        return {
            "ok": False,
            "mensaje": "El pago debe tener proveedor o CUIT.",
        }

    if cuenta_tesoreria_id is None:
        return {
            "ok": False,
            "mensaje": "El pago debe tener cuenta de origen.",
        }

    importe_pagado = _numero(importe_pagado)

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
    importe_total_aplicado = round(importe_pagado + importe_retenciones, 2)

    if importe_total_aplicado <= 0:
        return {
            "ok": False,
            "mensaje": "El pago debe tener importe pagado o retenciones.",
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
                "(importe pagado + retenciones)."
            ),
        }

    importe_a_cuenta = round(max(importe_total_aplicado - importe_imputado, 0), 2)

    fingerprint = _construir_fingerprint_pago(
        empresa_id=empresa_id,
        fecha_pago=fecha_pago,
        proveedor=proveedor,
        cuit=cuit,
        cuenta_tesoreria_id=cuenta_tesoreria_id,
        importe_pagado=importe_pagado,
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
                "mensaje": "El medio de pago EFECTIVO debe salir de una cuenta tipo CAJA.",
            }

        if medio_pago_codigo != "EFECTIVO" and tipo_cuenta_tesoreria == "CAJA":
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "Solo los pagos en EFECTIVO pueden salir de una cuenta tipo CAJA. Tarjeta, billetera y transferencia deben salir de Banco/Tesorería o cuenta puente.",
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
            FROM pagos
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
                "pago_id": int(existente[0]),
                "mensaje": "Pago duplicado omitido por fingerprint.",
            }

        cur.execute(
            """
            INSERT INTO pagos
            (
                empresa_id,
                fecha_pago,
                fecha_contable,
                proveedor,
                cuit,
                cuenta_tesoreria_id,
                medio_pago_id,
                importe_pagado,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMADO', ?, ?)
            """,
            (
                empresa_id,
                fecha_pago,
                fecha_contable,
                proveedor,
                cuit,
                cuenta_tesoreria_id,
                medio_pago_id,
                importe_pagado,
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

        pago_id = int(cur.lastrowid)
        numero_orden_pago = f"OP-{pago_id:08d}"

        cur.execute(
            """
            UPDATE pagos
            SET numero_orden_pago = ?
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                numero_orden_pago,
                empresa_id,
                pago_id,
            ),
        )

        for imp in imputaciones_normalizadas:
            cur.execute(
                """
                INSERT INTO pagos_imputaciones
                (
                    empresa_id,
                    pago_id,
                    cuenta_corriente_id,
                    tipo_comprobante,
                    numero_comprobante,
                    importe_imputado
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    pago_id,
                    imp.get("cuenta_corriente_id"),
                    imp["tipo_comprobante"],
                    imp["numero_comprobante"],
                    imp["importe_imputado"],
                ),
            )

        for ret in retenciones_normalizadas:
            cur.execute(
                """
                INSERT INTO pagos_retenciones
                (
                    empresa_id,
                    pago_id,
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
                    pago_id,
                    ret["tipo_retencion"],
                    ret["descripcion"],
                    ret["cuenta_contable_codigo"],
                    ret["cuenta_contable_nombre"],
                    ret["importe"],
                ),
            )

        _insertar_cuenta_corriente_proveedor(
            cur=cur,
            empresa_id=empresa_id,
            fecha=fecha_pago,
            proveedor=proveedor,
            cuit=cuit,
            tipo="PAGO",
            numero=numero_orden_pago,
            debe=importe_total_aplicado,
            haber=0,
            origen="PAGOS",
            archivo="",
        )

        asiento_id = _proximo_asiento_cur(cur)
        cuenta_tesoreria_nombre = _nombre_cuenta_contable_tesoreria(cuenta)

        glosa = descripcion or f"Pago {numero_orden_pago} - {proveedor}"
        comprobante_clave = f"PAGO|{numero_orden_pago}"

        _insertar_libro_diario(
            cur=cur,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            fecha=fecha_contable,
            cuenta=CUENTA_PROVEEDORES,
            debe=importe_total_aplicado,
            haber=0,
            glosa=glosa,
            origen="PAGOS",
            origen_tabla="pagos",
            origen_id=pago_id,
            comprobante_clave=comprobante_clave,
            usuario_id=usuario_id,
        )

        if importe_pagado > 0:
            _insertar_libro_diario(
                cur=cur,
                empresa_id=empresa_id,
                asiento_id=asiento_id,
                fecha=fecha_contable,
                cuenta=cuenta_tesoreria_nombre,
                debe=0,
                haber=importe_pagado,
                glosa=glosa,
                origen="PAGOS",
                origen_tabla="pagos",
                origen_id=pago_id,
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
                debe=0,
                haber=ret["importe"],
                glosa=glosa,
                origen="PAGOS",
                origen_tabla="pagos",
                origen_id=pago_id,
                comprobante_clave=comprobante_clave,
                usuario_id=usuario_id,
            )

        componentes_tesoreria = []

        for ret in retenciones_normalizadas:
            componentes_tesoreria.append({
                "tipo_componente": "RETENCION_PRACTICADA",
                "cuenta_contable_codigo": ret["cuenta_contable_codigo"],
                "cuenta_contable_nombre": ret["cuenta_contable_nombre"],
                "importe": ret["importe"],
                "descripcion": ret["descripcion"],
            })

        tesoreria_operacion_id = None

        if importe_pagado > 0:
            tesoreria_operacion_id = _insertar_operacion_tesoreria_pago(
                cur=cur,
                empresa_id=empresa_id,
                pago_id=pago_id,
                fecha_pago=fecha_pago,
                fecha_contable=fecha_contable,
                cuenta_tesoreria_id=cuenta_tesoreria_id,
                medio_pago_id=medio_pago_id,
                proveedor=proveedor,
                cuit=cuit,
                descripcion=glosa,
                referencia_externa=referencia_externa,
                importe_pagado=importe_pagado,
                usuario_id=usuario_id,
                componentes=componentes_tesoreria,
            )

        pago_caja_movimiento_id = None

        if importe_pagado > 0 and medio_pago_codigo == "EFECTIVO":
            pago_caja_movimiento_id = cajas_service.registrar_pago_efectivo_en_caja_cur(
                cur=cur,
                empresa_id=empresa_id,
                caja_id=cuenta_tesoreria_id,
                caja_nombre=_texto(cuenta.get("nombre")) or "Caja",
                fecha=fecha_pago,
                proveedor=proveedor,
                cuit=cuit,
                importe=importe_pagado,
                numero_orden_pago=numero_orden_pago,
                pago_id=pago_id,
                tesoreria_operacion_id=tesoreria_operacion_id,
                usuario_id=usuario_id,
            )

        cur.execute(
            """
            UPDATE pagos
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
                pago_id,
            ),
        )


        _registrar_auditoria(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="CREAR",
            entidad="pagos",
            entidad_id=pago_id,
            valor_nuevo={
                "numero_orden_pago": numero_orden_pago,
                "proveedor": proveedor,
                "cuit": cuit,
                "importe_pagado": importe_pagado,
                "importe_retenciones": importe_retenciones,
                "importe_total_aplicado": importe_total_aplicado,
                "importe_imputado": importe_imputado,
                "importe_a_cuenta": importe_a_cuenta,
                "asiento_id": asiento_id,
                "tesoreria_operacion_id": tesoreria_operacion_id,
                "caja_movimiento_id": pago_caja_movimiento_id,
            },
            motivo="Alta de pago.",
        )

        conn.commit()

        return {
            "ok": True,
            "creada": True,
            "duplicada": False,
            "pago_id": pago_id,
            "numero_orden_pago": numero_orden_pago,
            "asiento_id": asiento_id,
            "tesoreria_operacion_id": tesoreria_operacion_id,
            "caja_movimiento_id": pago_caja_movimiento_id,
            "importe_pagado": importe_pagado,
            "importe_retenciones": importe_retenciones,
            "importe_total_aplicado": importe_total_aplicado,
            "importe_imputado": importe_imputado,
            "importe_a_cuenta": importe_a_cuenta,
            "mensaje": "Pago registrado correctamente.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ======================================================
# ANULACIÓN CONTROLADA
# ======================================================

def anular_pago(
    pago_id,
    empresa_id=1,
    usuario_id=None,
    motivo="",
    permitir_conciliado=False,
):
    inicializar_pagos()

    empresa_id = int(empresa_id or 1)
    pago_id = int(pago_id)
    motivo = _texto(motivo)

    if not motivo:
        return {
            "ok": False,
            "mensaje": "Para anular un pago se debe indicar un motivo.",
        }

    conn = conectar()
    cur = conn.cursor()

    try:
        pago = _obtener_pago_dict(cur, empresa_id, pago_id)

        if pago is None:
            conn.rollback()
            return {
                "ok": False,
                "mensaje": "No se encontró el pago.",
            }

        if pago.get("estado") == "ANULADO":
            conn.rollback()
            return {
                "ok": True,
                "anulado": False,
                "mensaje": "El pago ya estaba anulado.",
            }

        tesoreria_operacion_id = pago.get("tesoreria_operacion_id")

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

            if fila and fila[0] == "CONCILIADA" and not permitir_conciliado:
                conn.rollback()
                return {
                    "ok": False,
                    "mensaje": (
                        "El pago está conciliado. "
                        "Primero debe desconciliarse o anularse con permiso administrador."
                    ),
                }

        fecha = _texto(pago.get("fecha_contable")) or _texto(pago.get("fecha_pago"))
        proveedor = _texto(pago.get("proveedor"))
        cuit = _texto(pago.get("cuit"))
        numero_orden_pago = _texto(pago.get("numero_orden_pago"))
        importe_pagado = _numero(pago.get("importe_pagado"))
        importe_total_aplicado = _numero(pago.get("importe_total_aplicado"))

        cur.execute(
            """
            SELECT *
            FROM pagos_retenciones
            WHERE empresa_id = ?
              AND pago_id = ?
            ORDER BY id
            """,
            (
                empresa_id,
                pago_id,
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
                pago.get("cuenta_tesoreria_id"),
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
        glosa = f"Anulación pago {numero_orden_pago} - {proveedor}"
        comprobante_clave = f"ANULA|PAGO|{numero_orden_pago}"

        _insertar_cuenta_corriente_proveedor(
            cur=cur,
            empresa_id=empresa_id,
            fecha=fecha,
            proveedor=proveedor,
            cuit=cuit,
            tipo="ANULACION PAGO",
            numero=numero_orden_pago,
            debe=0,
            haber=importe_total_aplicado,
            origen="PAGOS",
            archivo="",
        )

        if importe_pagado > 0:
            _insertar_libro_diario(
                cur=cur,
                empresa_id=empresa_id,
                asiento_id=asiento_reverso,
                fecha=fecha,
                cuenta=cuenta_tesoreria_nombre,
                debe=importe_pagado,
                haber=0,
                glosa=glosa,
                origen="PAGOS",
                origen_tabla="pagos",
                origen_id=pago_id,
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
                debe=_numero(ret.get("importe")),
                haber=0,
                glosa=glosa,
                origen="PAGOS",
                origen_tabla="pagos",
                origen_id=pago_id,
                comprobante_clave=comprobante_clave,
                usuario_id=usuario_id,
            )

        _insertar_libro_diario(
            cur=cur,
            empresa_id=empresa_id,
            asiento_id=asiento_reverso,
            fecha=fecha,
            cuenta=CUENTA_PROVEEDORES,
            debe=0,
            haber=importe_total_aplicado,
            glosa=glosa,
            origen="PAGOS",
            origen_tabla="pagos",
            origen_id=pago_id,
            comprobante_clave=comprobante_clave,
            usuario_id=usuario_id,
        )

        cur.execute(
            """
            UPDATE pagos
            SET estado = 'ANULADO',
                motivo_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ?
              AND id = ?
            """,
            (
                motivo,
                empresa_id,
                pago_id,
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

        # Anula el movimiento automático de Caja vinculado a la orden de pago,
        # solo si el pago original había salido por una cuenta tipo CAJA.
        numero_orden_pago_caja = _texto(pago.get("numero_orden_pago"))
        cuenta_tesoreria_id_caja = pago.get("cuenta_tesoreria_id")

        if numero_orden_pago_caja and cuenta_tesoreria_id_caja:
            cuenta_caja = _obtener_cuenta_tesoreria(
                cur,
                empresa_id,
                cuenta_tesoreria_id_caja,
            )

            if cuenta_caja is not None and _texto_upper(cuenta_caja.get("tipo_cuenta")) == "CAJA":
                cajas_service.anular_movimientos_caja_por_referencia_cur(
                    cur=cur,
                    empresa_id=empresa_id,
                    tipo_movimiento="PAGO_EFECTIVO",
                    referencia=numero_orden_pago_caja,
                    motivo=motivo,
                    usuario_id=usuario_id,
                )

        _registrar_auditoria(
            cur=cur,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion="ANULAR",
            entidad="pagos",
            entidad_id=pago_id,
            valor_anterior=pago,
            valor_nuevo={
                "estado": "ANULADO",
                "motivo_anulacion": motivo,
                "asiento_reverso": asiento_reverso,
            },
            motivo=motivo,
        )

        conn.commit()

        return {
            "ok": True,
            "anulado": True,
            "asiento_reverso": asiento_reverso,
            "mensaje": "Pago anulado correctamente.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()