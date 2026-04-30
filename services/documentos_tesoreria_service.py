import html
from datetime import date

import pandas as pd

from database import conectar
from services import cobranzas_service, pagos_service


# ======================================================
# UTILIDADES BASE
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


def _fecha_iso(valor):
    if valor is None:
        return ""

    if isinstance(valor, date):
        return valor.isoformat()

    texto = _texto(valor)

    if not texto:
        return ""

    return texto[:10]


def _moneda(valor):
    numero = _numero(valor)
    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"


def _esc(valor):
    return html.escape(_texto(valor))


def _leer_sql(sql, params=()):
    conn = conectar()

    try:
        return pd.read_sql_query(sql, conn, params=params)

    finally:
        conn.close()


def _columnas_tabla(conn, tabla):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({tabla})", conn)
        return df["name"].tolist()
    except Exception:
        return []


def _tabla_tiene_columna(conn, tabla, columna):
    return columna in _columnas_tabla(conn, tabla)


def inicializar_documentos_tesoreria():
    """
    Inicializa las estructuras que ya generan Recibos y Órdenes de Pago.
    No crea tablas nuevas en esta etapa y no borra información.
    """

    cobranzas_service.inicializar_cobranzas()
    pagos_service.inicializar_pagos()
    return True


# ======================================================
# FILTROS / CATÁLOGOS
# ======================================================

def obtener_medios_pago_disponibles(empresa_id=1):
    inicializar_documentos_tesoreria()

    empresa_id = int(empresa_id or 1)

    return _leer_sql(
        """
        SELECT
            codigo,
            nombre,
            tipo
        FROM tesoreria_medios_pago
        WHERE empresa_id = ?
          AND activo = 1
        ORDER BY nombre
        """,
        (
            empresa_id,
        ),
    )


def _armar_filtros_documentos(
    columna_fecha,
    columna_numero,
    columna_tercero,
    columna_cuit,
    alias_medio,
    fecha_desde="",
    fecha_hasta="",
    tercero="",
    numero="",
    estado="",
    medio_pago_codigo="",
):
    filtros = []
    params = []

    fecha_desde = _fecha_iso(fecha_desde)
    fecha_hasta = _fecha_iso(fecha_hasta)
    tercero = _texto(tercero)
    numero = _texto(numero)
    estado = _texto_upper(estado)
    medio_pago_codigo = _texto_upper(medio_pago_codigo)

    if fecha_desde:
        filtros.append(f"date({columna_fecha}) >= date(?)")
        params.append(fecha_desde)

    if fecha_hasta:
        filtros.append(f"date({columna_fecha}) <= date(?)")
        params.append(fecha_hasta)

    if tercero:
        filtros.append(
            f"""
            (
                UPPER(COALESCE({columna_tercero}, '')) LIKE ?
                OR UPPER(COALESCE({columna_cuit}, '')) LIKE ?
            )
            """
        )
        busqueda = f"%{tercero.upper()}%"
        params.extend([busqueda, busqueda])

    if numero:
        filtros.append(f"UPPER(COALESCE({columna_numero}, '')) LIKE ?")
        params.append(f"%{numero.upper()}%")

    if estado and estado != "TODOS":
        filtros.append("UPPER(COALESCE(estado, '')) = ?")
        params.append(estado)

    if medio_pago_codigo and medio_pago_codigo != "TODOS":
        filtros.append(f"UPPER(COALESCE({alias_medio}.codigo, '')) = ?")
        params.append(medio_pago_codigo)

    if filtros:
        return " AND " + " AND ".join(filtros), params

    return "", params


# ======================================================
# LISTADOS
# ======================================================

def listar_recibos_emitidos(
    empresa_id=1,
    fecha_desde="",
    fecha_hasta="",
    tercero="",
    numero="",
    estado="",
    medio_pago_codigo="",
):
    inicializar_documentos_tesoreria()

    empresa_id = int(empresa_id or 1)

    filtros_extra, params_extra = _armar_filtros_documentos(
        columna_fecha="c.fecha_cobranza",
        columna_numero="c.numero_recibo",
        columna_tercero="c.cliente",
        columna_cuit="c.cuit",
        alias_medio="mp",
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tercero=tercero,
        numero=numero,
        estado=estado,
        medio_pago_codigo=medio_pago_codigo,
    )

    params = [empresa_id]
    params.extend(params_extra)

    return _leer_sql(
        f"""
        SELECT
            c.id AS documento_id,
            'RECIBO' AS tipo_documento,
            c.numero_recibo AS numero_documento,
            c.fecha_cobranza AS fecha,
            c.fecha_contable,
            c.cliente AS tercero_nombre,
            c.cuit AS tercero_cuit,
            tc.tipo_cuenta,
            tc.nombre AS cuenta_tesoreria,
            tc.entidad AS entidad_tesoreria,
            mp.codigo AS medio_pago_codigo,
            mp.nombre AS medio_pago,
            c.importe_recibido AS importe_movimiento,
            c.importe_retenciones,
            c.importe_total_aplicado,
            c.importe_imputado,
            c.importe_a_cuenta,
            c.referencia_externa,
            c.descripcion,
            c.estado,
            c.asiento_id,
            c.tesoreria_operacion_id,
            top.estado AS estado_tesoreria,
            top.estado_conciliacion,
            top.importe AS importe_tesoreria,
            c.motivo_anulacion,
            c.fecha_anulacion,
            c.fecha_creacion
        FROM cobranzas c
        LEFT JOIN tesoreria_cuentas tc
               ON tc.id = c.cuenta_tesoreria_id
              AND tc.empresa_id = c.empresa_id
        LEFT JOIN tesoreria_medios_pago mp
               ON mp.id = c.medio_pago_id
              AND mp.empresa_id = c.empresa_id
        LEFT JOIN tesoreria_operaciones top
               ON top.id = c.tesoreria_operacion_id
              AND top.empresa_id = c.empresa_id
        WHERE c.empresa_id = ?
        {filtros_extra}
        ORDER BY date(c.fecha_cobranza) DESC, c.id DESC
        """,
        tuple(params),
    )


def listar_ordenes_pago_emitidas(
    empresa_id=1,
    fecha_desde="",
    fecha_hasta="",
    tercero="",
    numero="",
    estado="",
    medio_pago_codigo="",
):
    inicializar_documentos_tesoreria()

    empresa_id = int(empresa_id or 1)

    filtros_extra, params_extra = _armar_filtros_documentos(
        columna_fecha="p.fecha_pago",
        columna_numero="p.numero_orden_pago",
        columna_tercero="p.proveedor",
        columna_cuit="p.cuit",
        alias_medio="mp",
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tercero=tercero,
        numero=numero,
        estado=estado,
        medio_pago_codigo=medio_pago_codigo,
    )

    params = [empresa_id]
    params.extend(params_extra)

    return _leer_sql(
        f"""
        SELECT
            p.id AS documento_id,
            'ORDEN_PAGO' AS tipo_documento,
            p.numero_orden_pago AS numero_documento,
            p.fecha_pago AS fecha,
            p.fecha_contable,
            p.proveedor AS tercero_nombre,
            p.cuit AS tercero_cuit,
            tc.tipo_cuenta,
            tc.nombre AS cuenta_tesoreria,
            tc.entidad AS entidad_tesoreria,
            mp.codigo AS medio_pago_codigo,
            mp.nombre AS medio_pago,
            p.importe_pagado AS importe_movimiento,
            p.importe_retenciones,
            p.importe_total_aplicado,
            p.importe_imputado,
            p.importe_a_cuenta,
            p.referencia_externa,
            p.descripcion,
            p.estado,
            p.asiento_id,
            p.tesoreria_operacion_id,
            top.estado AS estado_tesoreria,
            top.estado_conciliacion,
            top.importe AS importe_tesoreria,
            p.motivo_anulacion,
            p.fecha_anulacion,
            p.fecha_creacion
        FROM pagos p
        LEFT JOIN tesoreria_cuentas tc
               ON tc.id = p.cuenta_tesoreria_id
              AND tc.empresa_id = p.empresa_id
        LEFT JOIN tesoreria_medios_pago mp
               ON mp.id = p.medio_pago_id
              AND mp.empresa_id = p.empresa_id
        LEFT JOIN tesoreria_operaciones top
               ON top.id = p.tesoreria_operacion_id
              AND top.empresa_id = p.empresa_id
        WHERE p.empresa_id = ?
        {filtros_extra}
        ORDER BY date(p.fecha_pago) DESC, p.id DESC
        """,
        tuple(params),
    )


# ======================================================
# DETALLE
# ======================================================

def _obtener_asientos_documento(conn, empresa_id, origen_tabla, origen_id, asiento_id):
    if not asiento_id and not origen_id:
        return pd.DataFrame()

    columnas = _columnas_tabla(conn, "libro_diario")

    columnas_select = """
        id,
        id_asiento,
        fecha,
        cuenta,
        debe,
        haber,
        glosa,
        origen,
        archivo
    """

    if "comprobante_clave" in columnas:
        columnas_select += ", comprobante_clave"

    if "estado" in columnas:
        columnas_select += ", estado"

    if "fecha_creacion" in columnas:
        columnas_select += ", fecha_creacion"

    if "origen_tabla" in columnas and "origen_id" in columnas:
        filtros = [
            "origen_tabla = ?",
            "origen_id = ?",
        ]
        params = [origen_tabla, origen_id]

        if "empresa_id" in columnas:
            filtros.insert(0, "empresa_id = ?")
            params.insert(0, empresa_id)

        where_sql = " AND ".join(filtros)

        return pd.read_sql_query(
            f"""
            SELECT
                {columnas_select}
            FROM libro_diario
            WHERE {where_sql}
            ORDER BY id_asiento, id
            """,
            conn,
            params=tuple(params),
        )

    filtros = ["id_asiento = ?"]
    params = [asiento_id]

    if "empresa_id" in columnas:
        filtros.insert(0, "empresa_id = ?")
        params.insert(0, empresa_id)

    where_sql = " AND ".join(filtros)

    return pd.read_sql_query(
        f"""
        SELECT
            {columnas_select}
        FROM libro_diario
        WHERE {where_sql}
        ORDER BY id_asiento, id
        """,
        conn,
        params=tuple(params),
    )


def _obtener_operacion_tesoreria(conn, empresa_id, operacion_id):
    if not operacion_id:
        return pd.DataFrame(), pd.DataFrame()

    operacion = pd.read_sql_query(
        """
        SELECT
            top.id,
            top.tipo_operacion,
            top.subtipo,
            top.fecha_operacion,
            top.fecha_contable,
            tc.tipo_cuenta,
            tc.nombre AS cuenta_tesoreria,
            tc.entidad AS entidad_tesoreria,
            mp.codigo AS medio_pago_codigo,
            mp.nombre AS medio_pago,
            top.tercero_tipo,
            top.tercero_nombre,
            top.tercero_cuit,
            top.descripcion,
            top.referencia_externa,
            top.importe,
            top.moneda,
            top.estado,
            top.estado_conciliacion,
            top.importe_conciliado,
            top.importe_pendiente,
            top.origen_modulo,
            top.origen_tabla,
            top.origen_id,
            top.fecha_creacion
        FROM tesoreria_operaciones top
        LEFT JOIN tesoreria_cuentas tc
               ON tc.id = top.cuenta_tesoreria_id
              AND tc.empresa_id = top.empresa_id
        LEFT JOIN tesoreria_medios_pago mp
               ON mp.id = top.medio_pago_id
              AND mp.empresa_id = top.empresa_id
        WHERE top.empresa_id = ?
          AND top.id = ?
        """,
        conn,
        params=(
            empresa_id,
            operacion_id,
        ),
    )

    componentes = pd.read_sql_query(
        """
        SELECT
            tipo_componente,
            cuenta_contable_codigo,
            cuenta_contable_nombre,
            importe,
            descripcion,
            fecha_creacion
        FROM tesoreria_operaciones_componentes
        WHERE empresa_id = ?
          AND operacion_id = ?
        ORDER BY id
        """,
        conn,
        params=(
            empresa_id,
            operacion_id,
        ),
    )

    return operacion, componentes


def obtener_recibo_emitido(empresa_id=1, documento_id=None):
    inicializar_documentos_tesoreria()

    empresa_id = int(empresa_id or 1)

    if documento_id is None:
        return {
            "ok": False,
            "mensaje": "No se indicó el recibo a consultar.",
        }

    documento_id = int(documento_id)

    conn = conectar()

    try:
        cabecera = pd.read_sql_query(
            """
            SELECT
                c.id AS documento_id,
                'RECIBO' AS tipo_documento,
                c.numero_recibo AS numero_documento,
                c.fecha_cobranza AS fecha,
                c.fecha_contable,
                c.cliente AS tercero_nombre,
                c.cuit AS tercero_cuit,
                tc.tipo_cuenta,
                tc.nombre AS cuenta_tesoreria,
                tc.entidad AS entidad_tesoreria,
                mp.codigo AS medio_pago_codigo,
                mp.nombre AS medio_pago,
                c.importe_recibido AS importe_movimiento,
                c.importe_retenciones,
                c.importe_total_aplicado,
                c.importe_imputado,
                c.importe_a_cuenta,
                c.referencia_externa,
                c.descripcion,
                c.estado,
                c.asiento_id,
                c.tesoreria_operacion_id,
                top.estado AS estado_tesoreria,
                top.estado_conciliacion,
                c.motivo_anulacion,
                c.fecha_anulacion,
                c.fecha_creacion
            FROM cobranzas c
            LEFT JOIN tesoreria_cuentas tc
                   ON tc.id = c.cuenta_tesoreria_id
                  AND tc.empresa_id = c.empresa_id
            LEFT JOIN tesoreria_medios_pago mp
                   ON mp.id = c.medio_pago_id
                  AND mp.empresa_id = c.empresa_id
            LEFT JOIN tesoreria_operaciones top
                   ON top.id = c.tesoreria_operacion_id
                  AND top.empresa_id = c.empresa_id
            WHERE c.empresa_id = ?
              AND c.id = ?
            """,
            conn,
            params=(
                empresa_id,
                documento_id,
            ),
        )

        if cabecera.empty:
            return {
                "ok": False,
                "mensaje": "No se encontró el recibo emitido.",
            }

        imputaciones = pd.read_sql_query(
            """
            SELECT
                tipo_comprobante,
                numero_comprobante,
                importe_imputado,
                cuenta_corriente_id,
                fecha_creacion
            FROM cobranzas_imputaciones
            WHERE empresa_id = ?
              AND cobranza_id = ?
            ORDER BY id
            """,
            conn,
            params=(
                empresa_id,
                documento_id,
            ),
        )

        retenciones = pd.read_sql_query(
            """
            SELECT
                tipo_retencion,
                descripcion,
                cuenta_contable_codigo,
                cuenta_contable_nombre,
                importe,
                fecha_creacion
            FROM cobranzas_retenciones
            WHERE empresa_id = ?
              AND cobranza_id = ?
            ORDER BY id
            """,
            conn,
            params=(
                empresa_id,
                documento_id,
            ),
        )

        fila = cabecera.iloc[0].to_dict()

        asientos = _obtener_asientos_documento(
            conn=conn,
            empresa_id=empresa_id,
            origen_tabla="cobranzas",
            origen_id=documento_id,
            asiento_id=fila.get("asiento_id"),
        )

        operacion, componentes = _obtener_operacion_tesoreria(
            conn=conn,
            empresa_id=empresa_id,
            operacion_id=fila.get("tesoreria_operacion_id"),
        )

        return {
            "ok": True,
            "tipo": "RECIBO",
            "cabecera": fila,
            "imputaciones": imputaciones,
            "retenciones": retenciones,
            "asientos": asientos,
            "tesoreria_operacion": operacion,
            "tesoreria_componentes": componentes,
        }

    finally:
        conn.close()


def obtener_orden_pago_emitida(empresa_id=1, documento_id=None):
    inicializar_documentos_tesoreria()

    empresa_id = int(empresa_id or 1)

    if documento_id is None:
        return {
            "ok": False,
            "mensaje": "No se indicó la orden de pago a consultar.",
        }

    documento_id = int(documento_id)

    conn = conectar()

    try:
        cabecera = pd.read_sql_query(
            """
            SELECT
                p.id AS documento_id,
                'ORDEN_PAGO' AS tipo_documento,
                p.numero_orden_pago AS numero_documento,
                p.fecha_pago AS fecha,
                p.fecha_contable,
                p.proveedor AS tercero_nombre,
                p.cuit AS tercero_cuit,
                tc.tipo_cuenta,
                tc.nombre AS cuenta_tesoreria,
                tc.entidad AS entidad_tesoreria,
                mp.codigo AS medio_pago_codigo,
                mp.nombre AS medio_pago,
                p.importe_pagado AS importe_movimiento,
                p.importe_retenciones,
                p.importe_total_aplicado,
                p.importe_imputado,
                p.importe_a_cuenta,
                p.referencia_externa,
                p.descripcion,
                p.estado,
                p.asiento_id,
                p.tesoreria_operacion_id,
                top.estado AS estado_tesoreria,
                top.estado_conciliacion,
                p.motivo_anulacion,
                p.fecha_anulacion,
                p.fecha_creacion
            FROM pagos p
            LEFT JOIN tesoreria_cuentas tc
                   ON tc.id = p.cuenta_tesoreria_id
                  AND tc.empresa_id = p.empresa_id
            LEFT JOIN tesoreria_medios_pago mp
                   ON mp.id = p.medio_pago_id
                  AND mp.empresa_id = p.empresa_id
            LEFT JOIN tesoreria_operaciones top
                   ON top.id = p.tesoreria_operacion_id
                  AND top.empresa_id = p.empresa_id
            WHERE p.empresa_id = ?
              AND p.id = ?
            """,
            conn,
            params=(
                empresa_id,
                documento_id,
            ),
        )

        if cabecera.empty:
            return {
                "ok": False,
                "mensaje": "No se encontró la orden de pago emitida.",
            }

        imputaciones = pd.read_sql_query(
            """
            SELECT
                tipo_comprobante,
                numero_comprobante,
                importe_imputado,
                cuenta_corriente_id,
                fecha_creacion
            FROM pagos_imputaciones
            WHERE empresa_id = ?
              AND pago_id = ?
            ORDER BY id
            """,
            conn,
            params=(
                empresa_id,
                documento_id,
            ),
        )

        retenciones = pd.read_sql_query(
            """
            SELECT
                tipo_retencion,
                descripcion,
                cuenta_contable_codigo,
                cuenta_contable_nombre,
                importe,
                fecha_creacion
            FROM pagos_retenciones
            WHERE empresa_id = ?
              AND pago_id = ?
            ORDER BY id
            """,
            conn,
            params=(
                empresa_id,
                documento_id,
            ),
        )

        fila = cabecera.iloc[0].to_dict()

        asientos = _obtener_asientos_documento(
            conn=conn,
            empresa_id=empresa_id,
            origen_tabla="pagos",
            origen_id=documento_id,
            asiento_id=fila.get("asiento_id"),
        )

        operacion, componentes = _obtener_operacion_tesoreria(
            conn=conn,
            empresa_id=empresa_id,
            operacion_id=fila.get("tesoreria_operacion_id"),
        )

        return {
            "ok": True,
            "tipo": "ORDEN_PAGO",
            "cabecera": fila,
            "imputaciones": imputaciones,
            "retenciones": retenciones,
            "asientos": asientos,
            "tesoreria_operacion": operacion,
            "tesoreria_componentes": componentes,
        }

    finally:
        conn.close()


def obtener_documento_emitido(tipo_documento, empresa_id=1, documento_id=None):
    tipo_documento = _texto_upper(tipo_documento)

    if tipo_documento in {"RECIBO", "COBRANZA", "RC"}:
        return obtener_recibo_emitido(
            empresa_id=empresa_id,
            documento_id=documento_id,
        )

    if tipo_documento in {"ORDEN_PAGO", "PAGO", "OP"}:
        return obtener_orden_pago_emitida(
            empresa_id=empresa_id,
            documento_id=documento_id,
        )

    return {
        "ok": False,
        "mensaje": "Tipo de documento no reconocido.",
    }


# ======================================================
# HTML IMPRIMIBLE
# ======================================================

def _tabla_html(df, columnas, titulos, columnas_monetarias=None):
    columnas_monetarias = set(columnas_monetarias or [])

    if df is None or df.empty:
        return '<p class="muted">Sin registros para mostrar.</p>'

    encabezado = "".join(f"<th>{_esc(titulo)}</th>" for titulo in titulos)

    filas_html = []

    for _, fila in df.iterrows():
        celdas = []

        for columna in columnas:
            valor = fila.get(columna, "")

            if columna in columnas_monetarias:
                valor = _moneda(valor)
            else:
                valor = _texto(valor)

            celdas.append(f"<td>{_esc(valor)}</td>")

        filas_html.append("<tr>" + "".join(celdas) + "</tr>")

    return f"""
    <table>
        <thead>
            <tr>{encabezado}</tr>
        </thead>
        <tbody>
            {''.join(filas_html)}
        </tbody>
    </table>
    """


def _estado_badge(estado):
    estado = _texto_upper(estado)

    if estado in {"ANULADA", "ANULADO"}:
        clase = "danger"
    elif estado in {"CONFIRMADA", "CONFIRMADO"}:
        clase = "ok"
    else:
        clase = "neutral"

    return f'<span class="badge {clase}">{_esc(estado or "SIN ESTADO")}</span>'


def _generar_html_documento(detalle, titulo, subtitulo, etiqueta_movimiento):
    cabecera = detalle.get("cabecera") or {}

    imputaciones = detalle.get("imputaciones")
    retenciones = detalle.get("retenciones")
    asientos = detalle.get("asientos")
    operacion = detalle.get("tesoreria_operacion")
    componentes = detalle.get("tesoreria_componentes")

    numero = _texto(cabecera.get("numero_documento"))
    estado = _texto(cabecera.get("estado"))

    motivo_anulacion = _texto(cabecera.get("motivo_anulacion"))

    bloque_anulacion = ""

    if motivo_anulacion:
        bloque_anulacion = f"""
        <div class="warning">
            <strong>Motivo de anulación:</strong> {_esc(motivo_anulacion)}
        </div>
        """

    html_imputaciones = _tabla_html(
        imputaciones,
        columnas=[
            "tipo_comprobante",
            "numero_comprobante",
            "importe_imputado",
        ],
        titulos=[
            "Tipo",
            "Comprobante",
            "Importe imputado",
        ],
        columnas_monetarias={"importe_imputado"},
    )

    html_retenciones = _tabla_html(
        retenciones,
        columnas=[
            "tipo_retencion",
            "descripcion",
            "cuenta_contable_nombre",
            "importe",
        ],
        titulos=[
            "Tipo",
            "Descripción",
            "Cuenta contable",
            "Importe",
        ],
        columnas_monetarias={"importe"},
    )

    html_asientos = _tabla_html(
        asientos,
        columnas=[
            "id_asiento",
            "fecha",
            "cuenta",
            "debe",
            "haber",
            "glosa",
            "estado",
        ],
        titulos=[
            "Asiento",
            "Fecha",
            "Cuenta",
            "Debe",
            "Haber",
            "Glosa",
            "Estado",
        ],
        columnas_monetarias={"debe", "haber"},
    )

    html_operacion = _tabla_html(
        operacion,
        columnas=[
            "id",
            "tipo_operacion",
            "subtipo",
            "fecha_operacion",
            "cuenta_tesoreria",
            "medio_pago",
            "importe",
            "estado",
            "estado_conciliacion",
        ],
        titulos=[
            "ID",
            "Tipo",
            "Subtipo",
            "Fecha",
            "Cuenta",
            "Medio",
            "Importe",
            "Estado",
            "Conciliación",
        ],
        columnas_monetarias={"importe"},
    )

    html_componentes = _tabla_html(
        componentes,
        columnas=[
            "tipo_componente",
            "cuenta_contable_nombre",
            "importe",
            "descripcion",
        ],
        titulos=[
            "Tipo",
            "Cuenta contable",
            "Importe",
            "Descripción",
        ],
        columnas_monetarias={"importe"},
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{_esc(titulo)} {_esc(numero)}</title>
<style>
    body {{
        font-family: Arial, Helvetica, sans-serif;
        margin: 28px;
        color: #111827;
        background: #ffffff;
    }}

    .toolbar {{
        margin-bottom: 18px;
    }}

    button {{
        border: 1px solid #111827;
        background: #111827;
        color: #ffffff;
        padding: 10px 16px;
        border-radius: 999px;
        cursor: pointer;
        font-weight: 700;
    }}

    .documento {{
        border: 1px solid #d1d5db;
        border-radius: 18px;
        padding: 24px;
    }}

    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        border-bottom: 2px solid #111827;
        padding-bottom: 16px;
        margin-bottom: 18px;
        gap: 16px;
    }}

    h1 {{
        margin: 0;
        font-size: 30px;
        letter-spacing: -0.04em;
    }}

    h2 {{
        margin-top: 28px;
        font-size: 18px;
        border-bottom: 1px solid #e5e7eb;
        padding-bottom: 8px;
    }}

    .subtitle {{
        color: #4b5563;
        margin-top: 6px;
        font-size: 14px;
    }}

    .number {{
        font-size: 22px;
        font-weight: 800;
        text-align: right;
    }}

    .badge {{
        display: inline-block;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 800;
        margin-top: 8px;
    }}

    .badge.ok {{
        background: #dcfce7;
        color: #166534;
    }}

    .badge.danger {{
        background: #fee2e2;
        color: #991b1b;
    }}

    .badge.neutral {{
        background: #e5e7eb;
        color: #374151;
    }}

    .grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 18px;
    }}

    .box {{
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 12px;
        min-height: 62px;
    }}

    .label {{
        color: #6b7280;
        font-size: 12px;
        margin-bottom: 6px;
    }}

    .value {{
        font-size: 14px;
        font-weight: 700;
    }}

    .total {{
        font-size: 20px;
        font-weight: 900;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        font-size: 13px;
    }}

    th {{
        background: #f3f4f6;
        text-align: left;
        border: 1px solid #e5e7eb;
        padding: 8px;
    }}

    td {{
        border: 1px solid #e5e7eb;
        padding: 8px;
        vertical-align: top;
    }}

    .muted {{
        color: #6b7280;
        font-size: 13px;
    }}

    .warning {{
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
        border-radius: 14px;
        padding: 12px;
        margin-bottom: 16px;
    }}

    .footer {{
        margin-top: 32px;
        color: #6b7280;
        font-size: 12px;
        border-top: 1px solid #e5e7eb;
        padding-top: 12px;
    }}

    @media print {{
        .toolbar {{
            display: none;
        }}

        body {{
            margin: 0;
        }}

        .documento {{
            border: none;
            border-radius: 0;
            padding: 0;
        }}
    }}
</style>
</head>
<body>
    <div class="toolbar">
        <button onclick="window.print()">Imprimir / Guardar como PDF</button>
    </div>

    <div class="documento">
        <div class="header">
            <div>
                <h1>{_esc(titulo)}</h1>
                <div class="subtitle">{_esc(subtitulo)}</div>
            </div>
            <div>
                <div class="number">{_esc(numero)}</div>
                {_estado_badge(estado)}
            </div>
        </div>

        {bloque_anulacion}

        <div class="grid">
            <div class="box">
                <div class="label">Fecha</div>
                <div class="value">{_esc(cabecera.get("fecha"))}</div>
            </div>
            <div class="box">
                <div class="label">Fecha contable</div>
                <div class="value">{_esc(cabecera.get("fecha_contable"))}</div>
            </div>
            <div class="box">
                <div class="label">Tercero</div>
                <div class="value">{_esc(cabecera.get("tercero_nombre"))}</div>
            </div>
            <div class="box">
                <div class="label">CUIT</div>
                <div class="value">{_esc(cabecera.get("tercero_cuit"))}</div>
            </div>

            <div class="box">
                <div class="label">Medio de pago</div>
                <div class="value">{_esc(cabecera.get("medio_pago"))}</div>
            </div>
            <div class="box">
                <div class="label">Cuenta de Tesorería</div>
                <div class="value">{_esc(cabecera.get("cuenta_tesoreria"))}</div>
            </div>
            <div class="box">
                <div class="label">{_esc(etiqueta_movimiento)}</div>
                <div class="value">{_esc(_moneda(cabecera.get("importe_movimiento")))}</div>
            </div>
            <div class="box">
                <div class="label">Total aplicado</div>
                <div class="value total">{_esc(_moneda(cabecera.get("importe_total_aplicado")))}</div>
            </div>

            <div class="box">
                <div class="label">Retenciones</div>
                <div class="value">{_esc(_moneda(cabecera.get("importe_retenciones")))}</div>
            </div>
            <div class="box">
                <div class="label">Importe imputado</div>
                <div class="value">{_esc(_moneda(cabecera.get("importe_imputado")))}</div>
            </div>
            <div class="box">
                <div class="label">Importe a cuenta</div>
                <div class="value">{_esc(_moneda(cabecera.get("importe_a_cuenta")))}</div>
            </div>
            <div class="box">
                <div class="label">Referencia externa</div>
                <div class="value">{_esc(cabecera.get("referencia_externa"))}</div>
            </div>
        </div>

        <h2>Comprobantes imputados</h2>
        {html_imputaciones}

        <h2>Retenciones</h2>
        {html_retenciones}

        <h2>Asiento contable vinculado</h2>
        {html_asientos}

        <h2>Operación de Tesorería</h2>
        {html_operacion}

        <h2>Componentes de Tesorería</h2>
        {html_componentes}

        <div class="footer">
            Documento generado desde Sistema Contable FF. La información surge de las registraciones de Cobranzas/Pagos, Libro Diario y Tesorería.
        </div>
    </div>
</body>
</html>
"""


def generar_html_recibo_emitido(detalle):
    return _generar_html_documento(
        detalle=detalle,
        titulo="Recibo emitido",
        subtitulo="Comprobante interno de cobranza a cliente",
        etiqueta_movimiento="Importe recibido",
    )


def generar_html_orden_pago_emitida(detalle):
    return _generar_html_documento(
        detalle=detalle,
        titulo="Orden de pago",
        subtitulo="Comprobante interno de pago a proveedor",
        etiqueta_movimiento="Importe pagado",
    )


def nombre_archivo_html(detalle):
    cabecera = detalle.get("cabecera") or {}
    numero = _texto(cabecera.get("numero_documento")) or "documento"
    numero = numero.replace("/", "-").replace("\\", "-").replace(" ", "_")
    return f"{numero}.html"