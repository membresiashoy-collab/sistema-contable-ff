from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.ui import preparar_vista
from services import documentos_tesoreria_service as documentos_service


# ======================================================
# UTILIDADES VISUALES
# ======================================================

def _empresa_id():
    return int(st.session_state.get("empresa_id", 1) or 1)


def _moneda(valor):
    try:
        numero = round(float(valor or 0), 2)
    except Exception:
        numero = 0.0

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"


def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def _fecha_iso(valor):
    if isinstance(valor, date):
        return valor.isoformat()

    return _texto(valor)


def _sumar_columna(df, columna):
    if df is None or df.empty or columna not in df.columns:
        return 0.0

    return round(float(pd.to_numeric(df[columna], errors="coerce").fillna(0).sum()), 2)


def _fila_por_id(df, documento_id):
    if df is None or df.empty:
        return {}

    filas = df[df["documento_id"] == documento_id]

    if filas.empty:
        return {}

    return filas.iloc[0].to_dict()


def _formatear_opcion_documento(df, documento_id):
    fila = _fila_por_id(df, documento_id)

    numero = _texto(fila.get("numero_documento"))
    fecha = _texto(fila.get("fecha"))
    tercero = _texto(fila.get("tercero_nombre"))
    total = _moneda(fila.get("importe_total_aplicado"))
    estado = _texto(fila.get("estado"))

    return f"{numero} | {fecha} | {tercero} | {total} | {estado}"


def _mostrar_metricas_listado(df, etiqueta_movimiento):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Documentos", len(df) if df is not None else 0)

    with col2:
        st.metric(etiqueta_movimiento, _moneda(_sumar_columna(df, "importe_movimiento")))

    with col3:
        st.metric("Retenciones", _moneda(_sumar_columna(df, "importe_retenciones")))

    with col4:
        st.metric("Total aplicado", _moneda(_sumar_columna(df, "importe_total_aplicado")))


def _obtener_opciones_medios_pago(empresa_id):
    medios = documentos_service.obtener_medios_pago_disponibles(empresa_id=empresa_id)

    opciones = [("TODOS", "Todos los medios")]

    if medios is None or medios.empty:
        return opciones

    for _, fila in medios.iterrows():
        codigo = _texto(fila.get("codigo"))
        nombre = _texto(fila.get("nombre"))

        if codigo:
            opciones.append((codigo, nombre or codigo))

    return opciones


def _mostrar_filtros(prefijo, estados):
    empresa_id = _empresa_id()

    st.markdown("### Filtros")

    col_fecha, col_tercero, col_numero, col_estado, col_medio = st.columns([1.15, 1.4, 1.1, 1.05, 1.15])

    with col_fecha:
        filtrar_fechas = st.checkbox(
            "Filtrar por fecha",
            value=False,
            key=f"{prefijo}_filtrar_fechas",
        )

    fecha_desde = ""
    fecha_hasta = ""

    if filtrar_fechas:
        col_desde, col_hasta = st.columns(2)

        with col_desde:
            fecha_desde = st.date_input(
                "Desde",
                value=date.today().replace(month=1, day=1),
                key=f"{prefijo}_fecha_desde",
            )

        with col_hasta:
            fecha_hasta = st.date_input(
                "Hasta",
                value=date.today(),
                key=f"{prefijo}_fecha_hasta",
            )

    with col_tercero:
        tercero = st.text_input(
            "Cliente / proveedor / CUIT",
            key=f"{prefijo}_tercero",
            placeholder="Buscar por nombre o CUIT",
        )

    with col_numero:
        numero = st.text_input(
            "Número",
            key=f"{prefijo}_numero",
            placeholder="RC-... / OP-...",
        )

    with col_estado:
        estado_label = st.selectbox(
            "Estado",
            list(estados.keys()),
            key=f"{prefijo}_estado",
        )
        estado = estados[estado_label]

    with col_medio:
        opciones_medios = _obtener_opciones_medios_pago(empresa_id)
        labels_medios = [nombre for _, nombre in opciones_medios]
        codigos_por_label = {nombre: codigo for codigo, nombre in opciones_medios}

        medio_label = st.selectbox(
            "Medio de pago",
            labels_medios,
            key=f"{prefijo}_medio",
        )
        medio_pago_codigo = codigos_por_label.get(medio_label, "TODOS")

    return {
        "fecha_desde": _fecha_iso(fecha_desde),
        "fecha_hasta": _fecha_iso(fecha_hasta),
        "tercero": tercero,
        "numero": numero,
        "estado": estado,
        "medio_pago_codigo": medio_pago_codigo,
    }


def _vista_listado(df):
    if df is None or df.empty:
        return pd.DataFrame()

    columnas = [
        "numero_documento",
        "fecha",
        "tercero_nombre",
        "tercero_cuit",
        "medio_pago",
        "cuenta_tesoreria",
        "importe_movimiento",
        "importe_retenciones",
        "importe_total_aplicado",
        "importe_a_cuenta",
        "estado",
        "estado_conciliacion",
        "asiento_id",
        "tesoreria_operacion_id",
    ]

    columnas = [col for col in columnas if col in df.columns]

    vista = df[columnas].copy()

    renombres = {
        "numero_documento": "Número",
        "fecha": "Fecha",
        "tercero_nombre": "Cliente / Proveedor",
        "tercero_cuit": "CUIT",
        "medio_pago": "Medio de pago",
        "cuenta_tesoreria": "Cuenta Tesorería",
        "importe_movimiento": "Importe mov.",
        "importe_retenciones": "Retenciones",
        "importe_total_aplicado": "Total aplicado",
        "importe_a_cuenta": "A cuenta",
        "estado": "Estado",
        "estado_conciliacion": "Conciliación",
        "asiento_id": "Asiento",
        "tesoreria_operacion_id": "Op. Tesorería",
    }

    vista = vista.rename(columns=renombres)

    for columna in ["Importe mov.", "Retenciones", "Total aplicado", "A cuenta"]:
        if columna in vista.columns:
            vista[columna] = vista[columna].apply(_moneda)

    return preparar_vista(vista)


def _mostrar_tabla_detalle(titulo, df, columnas=None, columnas_monetarias=None):
    st.markdown(f"#### {titulo}")

    if df is None or df.empty:
        st.caption("Sin registros para mostrar.")
        return

    vista = df.copy()

    if columnas:
        columnas_existentes = [col for col in columnas if col in vista.columns]
        vista = vista[columnas_existentes]

    for columna in columnas_monetarias or []:
        if columna in vista.columns:
            vista[columna] = vista[columna].apply(_moneda)

    st.dataframe(
        preparar_vista(vista),
        use_container_width=True,
    )


def _mostrar_cabecera_detalle(cabecera, etiqueta_movimiento):
    numero = _texto(cabecera.get("numero_documento"))
    estado = _texto(cabecera.get("estado"))
    tercero = _texto(cabecera.get("tercero_nombre"))
    cuit = _texto(cabecera.get("tercero_cuit"))

    st.markdown(f"### {numero}")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Estado", estado or "Sin estado")

    with col2:
        st.metric(etiqueta_movimiento, _moneda(cabecera.get("importe_movimiento")))

    with col3:
        st.metric("Retenciones", _moneda(cabecera.get("importe_retenciones")))

    with col4:
        st.metric("Total aplicado", _moneda(cabecera.get("importe_total_aplicado")))

    st.caption(
        f"Fecha: {_texto(cabecera.get('fecha'))} | "
        f"Tercero: {tercero} | "
        f"CUIT: {cuit} | "
        f"Medio: {_texto(cabecera.get('medio_pago'))} | "
        f"Cuenta: {_texto(cabecera.get('cuenta_tesoreria'))}"
    )

    motivo = _texto(cabecera.get("motivo_anulacion"))

    if motivo:
        st.warning(f"Documento anulado. Motivo: {motivo}")


def _mostrar_descarga_html(detalle, tipo_documento):
    if tipo_documento == "RECIBO":
        html = documentos_service.generar_html_recibo_emitido(detalle)
        etiqueta = "Descargar recibo HTML imprimible"
    else:
        html = documentos_service.generar_html_orden_pago_emitida(detalle)
        etiqueta = "Descargar orden de pago HTML imprimible"

    nombre_archivo = documentos_service.nombre_archivo_html(detalle)

    col1, col2 = st.columns([1, 2])

    with col1:
        st.download_button(
            etiqueta,
            data=html,
            file_name=nombre_archivo,
            mime="text/html",
            use_container_width=True,
        )

    with col2:
        st.info(
            "Primera etapa: se descarga un HTML imprimible. "
            "Abrilo en el navegador y usá Imprimir / Guardar como PDF."
        )

    with st.expander("Ver vista imprimible en pantalla", expanded=False):
        components.html(
            html,
            height=760,
            scrolling=True,
        )


def _mostrar_detalle_documento(detalle, tipo_documento, etiqueta_movimiento):
    if not detalle.get("ok"):
        st.error(detalle.get("mensaje", "No se pudo obtener el detalle."))
        return

    cabecera = detalle.get("cabecera") or {}

    _mostrar_cabecera_detalle(cabecera, etiqueta_movimiento)
    _mostrar_descarga_html(detalle, tipo_documento)

    st.divider()

    _mostrar_tabla_detalle(
        "Comprobantes imputados",
        detalle.get("imputaciones"),
        columnas=[
            "tipo_comprobante",
            "numero_comprobante",
            "importe_imputado",
            "cuenta_corriente_id",
            "fecha_creacion",
        ],
        columnas_monetarias=["importe_imputado"],
    )

    _mostrar_tabla_detalle(
        "Retenciones",
        detalle.get("retenciones"),
        columnas=[
            "tipo_retencion",
            "descripcion",
            "cuenta_contable_codigo",
            "cuenta_contable_nombre",
            "importe",
            "fecha_creacion",
        ],
        columnas_monetarias=["importe"],
    )

    _mostrar_tabla_detalle(
        "Asiento contable vinculado",
        detalle.get("asientos"),
        columnas=[
            "id_asiento",
            "fecha",
            "cuenta",
            "debe",
            "haber",
            "glosa",
            "origen",
            "comprobante_clave",
            "estado",
        ],
        columnas_monetarias=["debe", "haber"],
    )

    _mostrar_tabla_detalle(
        "Operación de Tesorería",
        detalle.get("tesoreria_operacion"),
        columnas=[
            "id",
            "tipo_operacion",
            "subtipo",
            "fecha_operacion",
            "cuenta_tesoreria",
            "medio_pago",
            "tercero_nombre",
            "importe",
            "estado",
            "estado_conciliacion",
            "importe_conciliado",
            "importe_pendiente",
        ],
        columnas_monetarias=["importe", "importe_conciliado", "importe_pendiente"],
    )

    _mostrar_tabla_detalle(
        "Componentes de Tesorería",
        detalle.get("tesoreria_componentes"),
        columnas=[
            "tipo_componente",
            "cuenta_contable_codigo",
            "cuenta_contable_nombre",
            "importe",
            "descripcion",
            "fecha_creacion",
        ],
        columnas_monetarias=["importe"],
    )


# ======================================================
# RECIBOS
# ======================================================

def _mostrar_recibos_emitidos():
    empresa_id = _empresa_id()

    st.markdown("## Recibos emitidos")
    st.caption(
        "Consulta de recibos generados desde Cobranzas. "
        "No modifica registraciones ni impacta Caja."
    )

    filtros = _mostrar_filtros(
        prefijo="doc_recibos",
        estados={
            "Todos": "TODOS",
            "Confirmadas": "CONFIRMADA",
            "Anuladas": "ANULADA",
        },
    )

    df = documentos_service.listar_recibos_emitidos(
        empresa_id=empresa_id,
        **filtros,
    )

    _mostrar_metricas_listado(df, "Importe recibido")

    st.markdown("### Listado")

    if df.empty:
        st.info("No hay recibos emitidos para los filtros seleccionados.")
        return

    st.dataframe(
        _vista_listado(df),
        use_container_width=True,
    )

    st.divider()

    opciones = df["documento_id"].astype(int).tolist()

    documento_id = st.selectbox(
        "Seleccionar recibo para ver detalle / imprimir",
        opciones,
        format_func=lambda doc_id: _formatear_opcion_documento(df, doc_id),
        key="doc_recibos_documento_id",
    )

    detalle = documentos_service.obtener_recibo_emitido(
        empresa_id=empresa_id,
        documento_id=documento_id,
    )

    _mostrar_detalle_documento(
        detalle=detalle,
        tipo_documento="RECIBO",
        etiqueta_movimiento="Importe recibido",
    )


# ======================================================
# ÓRDENES DE PAGO
# ======================================================

def _mostrar_ordenes_pago_emitidas():
    empresa_id = _empresa_id()

    st.markdown("## Órdenes de pago emitidas")
    st.caption(
        "Consulta de órdenes de pago generadas desde Pagos. "
        "Incluye imputaciones, retenciones practicadas, asiento y Tesorería."
    )

    filtros = _mostrar_filtros(
        prefijo="doc_ordenes_pago",
        estados={
            "Todos": "TODOS",
            "Confirmadas": "CONFIRMADO",
            "Anuladas": "ANULADO",
        },
    )

    df = documentos_service.listar_ordenes_pago_emitidas(
        empresa_id=empresa_id,
        **filtros,
    )

    _mostrar_metricas_listado(df, "Importe pagado")

    st.markdown("### Listado")

    if df.empty:
        st.info("No hay órdenes de pago emitidas para los filtros seleccionados.")
        return

    st.dataframe(
        _vista_listado(df),
        use_container_width=True,
    )

    st.divider()

    opciones = df["documento_id"].astype(int).tolist()

    documento_id = st.selectbox(
        "Seleccionar orden de pago para ver detalle / imprimir",
        opciones,
        format_func=lambda doc_id: _formatear_opcion_documento(df, doc_id),
        key="doc_ordenes_pago_documento_id",
    )

    detalle = documentos_service.obtener_orden_pago_emitida(
        empresa_id=empresa_id,
        documento_id=documento_id,
    )

    _mostrar_detalle_documento(
        detalle=detalle,
        tipo_documento="ORDEN_PAGO",
        etiqueta_movimiento="Importe pagado",
    )


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_documentos_tesoreria():
    documentos_service.inicializar_documentos_tesoreria()

    st.info(
        "Esta pantalla muestra documentos ya emitidos por Cobranzas y Pagos. "
        "No genera movimientos nuevos, no borra información y no toca la vista de Caja."
    )

    tab_recibos, tab_ordenes = st.tabs(
        [
            "Recibos emitidos",
            "Órdenes de pago",
        ]
    )

    with tab_recibos:
        _mostrar_recibos_emitidos()

    with tab_ordenes:
        _mostrar_ordenes_pago_emitidas()