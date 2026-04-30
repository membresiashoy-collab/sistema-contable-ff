from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.ui import preparar_vista
from services import cobranzas_service
from services import documentos_tesoreria_service as documentos_service
from services import pagos_service


# ======================================================
# UTILIDADES
# ======================================================

def _empresa_id():
    return int(st.session_state.get("empresa_id", 1) or 1)


def _usuario_id():
    usuario = st.session_state.get("usuario") or {}

    try:
        return int(usuario.get("id"))
    except Exception:
        return None


def _usuario_es_administrador():
    usuario = st.session_state.get("usuario") or {}
    rol = str(usuario.get("rol", "")).strip().upper()
    return rol in {"ADMINISTRADOR", "ADMIN", "SUPERADMIN"}


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


def _fecha_iso(valor):
    if isinstance(valor, date):
        return valor.isoformat()

    return _texto(valor)


def _moneda(valor):
    try:
        numero = round(float(valor or 0), 2)
    except Exception:
        numero = 0.0

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"


def _sumar(df, columna):
    if df is None or df.empty or columna not in df.columns:
        return 0.0

    return round(
        float(pd.to_numeric(df[columna], errors="coerce").fillna(0).sum()),
        2,
    )


def _obtener_medios_pago():
    medios = documentos_service.obtener_medios_pago_disponibles(
        empresa_id=_empresa_id(),
    )

    opciones = [("TODOS", "Todos los medios")]

    if medios is None or medios.empty:
        return opciones

    for _, fila in medios.iterrows():
        codigo = _texto(fila.get("codigo"))
        nombre = _texto(fila.get("nombre"))

        if codigo:
            opciones.append((codigo, nombre or codigo))

    return opciones


# ======================================================
# FILTROS / LISTADOS
# ======================================================

def _mostrar_filtros(prefijo, estados):
    st.markdown("#### Filtros")

    usar_fecha = st.checkbox(
        "Filtrar por fecha",
        value=False,
        key=f"{prefijo}_usar_fecha",
    )

    fecha_desde = ""
    fecha_hasta = ""

    if usar_fecha:
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

    col1, col2, col3 = st.columns([1.4, 1.0, 1.1])

    with col1:
        tercero = st.text_input(
            "Cliente / proveedor / CUIT",
            key=f"{prefijo}_tercero",
            placeholder="Buscar por nombre o CUIT",
        )

    with col2:
        numero = st.text_input(
            "Número",
            key=f"{prefijo}_numero",
            placeholder="RC-... / OP-...",
        )

    with col3:
        estado_label = st.selectbox(
            "Estado",
            list(estados.keys()),
            key=f"{prefijo}_estado",
        )
        estado = estados[estado_label]

    opciones_medios = _obtener_medios_pago()
    labels = [nombre for _, nombre in opciones_medios]
    codigos = {nombre: codigo for codigo, nombre in opciones_medios}

    medio_label = st.selectbox(
        "Medio de pago",
        labels,
        key=f"{prefijo}_medio_pago",
    )

    return {
        "fecha_desde": _fecha_iso(fecha_desde),
        "fecha_hasta": _fecha_iso(fecha_hasta),
        "tercero": tercero,
        "numero": numero,
        "estado": estado,
        "medio_pago_codigo": codigos.get(medio_label, "TODOS"),
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

    vista = vista.rename(
        columns={
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
    )

    for columna in ["Importe mov.", "Retenciones", "Total aplicado", "A cuenta"]:
        if columna in vista.columns:
            vista[columna] = vista[columna].apply(_moneda)

    return preparar_vista(vista)


def _mostrar_metricas(df, etiqueta_movimiento):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Documentos", len(df) if df is not None else 0)

    with col2:
        st.metric(etiqueta_movimiento, _moneda(_sumar(df, "importe_movimiento")))

    with col3:
        st.metric("Retenciones", _moneda(_sumar(df, "importe_retenciones")))

    with col4:
        st.metric("Total aplicado", _moneda(_sumar(df, "importe_total_aplicado")))


def _fila_por_id(df, documento_id):
    if df is None or df.empty:
        return {}

    filas = df[df["documento_id"].astype(int) == int(documento_id)]

    if filas.empty:
        return {}

    return filas.iloc[0].to_dict()


def _formato_opcion(df, documento_id):
    fila = _fila_por_id(df, documento_id)

    numero = _texto(fila.get("numero_documento"))
    fecha = _texto(fila.get("fecha"))
    tercero = _texto(fila.get("tercero_nombre"))
    total = _moneda(fila.get("importe_total_aplicado"))
    estado = _texto(fila.get("estado"))

    return f"{numero} | {fecha} | {tercero} | {total} | {estado}"


# ======================================================
# DETALLE / HTML
# ======================================================

def _mostrar_tabla(titulo, df, columnas=None, columnas_monetarias=None):
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
    conciliacion = _texto(cabecera.get("estado_conciliacion"))

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
        f"Tercero: {_texto(cabecera.get('tercero_nombre'))} | "
        f"CUIT: {_texto(cabecera.get('tercero_cuit'))} | "
        f"Medio: {_texto(cabecera.get('medio_pago'))} | "
        f"Cuenta: {_texto(cabecera.get('cuenta_tesoreria'))} | "
        f"Conciliación: {conciliacion or 'Sin operación conciliable'}"
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

    with st.expander("Vista imprimible en pantalla", expanded=False):
        components.html(
            html,
            height=720,
            scrolling=True,
        )


# ======================================================
# ANULACIÓN CONTROLADA
# ======================================================

def _mostrar_anulacion_controlada(detalle, tipo_documento, prefijo):
    cabecera = detalle.get("cabecera") or {}

    documento_id = cabecera.get("documento_id")
    numero = _texto(cabecera.get("numero_documento"))
    estado = _texto_upper(cabecera.get("estado"))
    estado_conciliacion = _texto_upper(cabecera.get("estado_conciliacion"))

    usuario_es_admin = _usuario_es_administrador()

    if tipo_documento == "RECIBO":
        titulo = "Anular recibo por error humano"
        texto_documento = "recibo"
        funcion_anulacion = cobranzas_service.anular_cobranza
        parametro_permiso = "permitir_conciliada"
    else:
        titulo = "Anular orden de pago por error humano"
        texto_documento = "orden de pago"
        funcion_anulacion = pagos_service.anular_pago
        parametro_permiso = "permitir_conciliado"

    st.markdown(f"#### {titulo}")

    st.info(
        "Esta acción no borra físicamente el documento. "
        "Conserva trazabilidad y utiliza la anulación controlada del módulo de origen."
    )

    if estado in {"ANULADA", "ANULADO"}:
        st.warning(f"El {texto_documento} ya está anulado.")
        return

    if estado_conciliacion == "CONCILIADA" and not usuario_es_admin:
        st.error(
            "Este documento está conciliado. "
            "Un usuario común no puede anularlo desde esta pantalla. "
            "Primero debe desconciliarse o intervenir un administrador."
        )
        return

    if estado_conciliacion == "CONCILIADA" and usuario_es_admin:
        st.warning(
            "Este documento está conciliado. "
            "Como administrador, podés forzar la anulación, pero debe quedar un motivo claro."
        )

    with st.form(f"{prefijo}_form_anulacion"):
        motivo = st.text_area(
            "Motivo obligatorio",
            key=f"{prefijo}_motivo_anulacion",
            placeholder="Ejemplo: Error humano de carga, recibo emitido al cliente equivocado, importe mal cargado...",
            height=90,
        )

        confirmar = st.checkbox(
            f"Confirmo que quiero anular el {texto_documento} {numero}. Entiendo que no se borra: queda trazabilidad y reversión.",
            key=f"{prefijo}_confirmar_anulacion",
        )

        enviar = st.form_submit_button(
            titulo,
            use_container_width=True,
        )

    if not enviar:
        return

    motivo = _texto(motivo)

    if not motivo:
        st.warning("Para anular se debe indicar un motivo.")
        return

    if not confirmar:
        st.warning("Para continuar tenés que marcar la confirmación.")
        return

    kwargs = {
        "empresa_id": _empresa_id(),
        "usuario_id": _usuario_id(),
        "motivo": motivo,
        parametro_permiso: usuario_es_admin,
    }

    resultado = funcion_anulacion(
        documento_id,
        **kwargs,
    )

    if resultado.get("ok"):
        st.success(resultado.get("mensaje", "Documento anulado correctamente."))
        st.rerun()
    else:
        st.error(resultado.get("mensaje", "No se pudo anular el documento."))


def _mostrar_detalle(detalle, tipo_documento, etiqueta_movimiento, prefijo):
    if not detalle.get("ok"):
        st.error(detalle.get("mensaje", "No se pudo obtener el detalle."))
        return

    cabecera = detalle.get("cabecera") or {}

    _mostrar_cabecera_detalle(cabecera, etiqueta_movimiento)
    _mostrar_descarga_html(detalle, tipo_documento)

    st.divider()

    _mostrar_tabla(
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

    _mostrar_tabla(
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

    _mostrar_tabla(
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

    _mostrar_tabla(
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

    _mostrar_tabla(
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

    st.divider()

    _mostrar_anulacion_controlada(
        detalle=detalle,
        tipo_documento=tipo_documento,
        prefijo=f"{prefijo}_anulacion",
    )


# ======================================================
# COMPONENTE RECIBOS
# ======================================================

def mostrar_recibos_emitidos_integrado():
    documentos_service.inicializar_documentos_tesoreria()

    st.markdown("## Recibos emitidos")
    st.caption(
        "Consulta, impresión simple y anulación controlada de recibos generados desde Cobranzas. "
        "No genera movimientos nuevos y no borra información."
    )

    filtros = _mostrar_filtros(
        prefijo="recibos_emitidos_integrado",
        estados={
            "Todos": "TODOS",
            "Confirmadas": "CONFIRMADA",
            "Anuladas": "ANULADA",
        },
    )

    df = documentos_service.listar_recibos_emitidos(
        empresa_id=_empresa_id(),
        **filtros,
    )

    _mostrar_metricas(df, "Importe recibido")

    if df.empty:
        st.info("No hay recibos emitidos para los filtros seleccionados.")
        return

    st.markdown("### Listado")
    st.dataframe(
        _vista_listado(df),
        use_container_width=True,
    )

    st.divider()

    opciones = df["documento_id"].astype(int).tolist()

    documento_id = st.selectbox(
        "Seleccionar recibo para ver detalle / imprimir / anular",
        opciones,
        format_func=lambda doc_id: _formato_opcion(df, doc_id),
        key="recibos_emitidos_integrado_documento_id",
    )

    detalle = documentos_service.obtener_recibo_emitido(
        empresa_id=_empresa_id(),
        documento_id=documento_id,
    )

    _mostrar_detalle(
        detalle=detalle,
        tipo_documento="RECIBO",
        etiqueta_movimiento="Importe recibido",
        prefijo="recibos_emitidos_integrado",
    )


# ======================================================
# COMPONENTE ÓRDENES DE PAGO
# ======================================================

def mostrar_ordenes_pago_emitidas_integrado():
    documentos_service.inicializar_documentos_tesoreria()

    st.markdown("## Órdenes de pago emitidas")
    st.caption(
        "Consulta, impresión simple y anulación controlada de órdenes de pago generadas desde Pagos. "
        "No genera movimientos nuevos y no borra información."
    )

    filtros = _mostrar_filtros(
        prefijo="ordenes_pago_emitidas_integrado",
        estados={
            "Todos": "TODOS",
            "Confirmadas": "CONFIRMADO",
            "Anuladas": "ANULADO",
        },
    )

    df = documentos_service.listar_ordenes_pago_emitidas(
        empresa_id=_empresa_id(),
        **filtros,
    )

    _mostrar_metricas(df, "Importe pagado")

    if df.empty:
        st.info("No hay órdenes de pago emitidas para los filtros seleccionados.")
        return

    st.markdown("### Listado")
    st.dataframe(
        _vista_listado(df),
        use_container_width=True,
    )

    st.divider()

    opciones = df["documento_id"].astype(int).tolist()

    documento_id = st.selectbox(
        "Seleccionar orden de pago para ver detalle / imprimir / anular",
        opciones,
        format_func=lambda doc_id: _formato_opcion(df, doc_id),
        key="ordenes_pago_emitidas_integrado_documento_id",
    )

    detalle = documentos_service.obtener_orden_pago_emitida(
        empresa_id=_empresa_id(),
        documento_id=documento_id,
    )

    _mostrar_detalle(
        detalle=detalle,
        tipo_documento="ORDEN_PAGO",
        etiqueta_movimiento="Importe pagado",
        prefijo="ordenes_pago_emitidas_integrado",
    )