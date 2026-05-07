import pandas as pd
import streamlit as st

from services.iva_service import (
    calcular_posicion_iva_periodo,
    etiqueta_resultado_saldo,
    formato_moneda,
    generar_papel_trabajo_excel_iva,
    nombre_archivo_papel_trabajo_iva,
    obtener_periodos_disponibles_iva,
    obtener_periodos_disponibles_movimientos_fiscales_iva,
    obtener_resumen_posiciones_iva,
)

from services.iva_movimientos_fiscales_service import (
    ESTADO_ANULADO,
    ESTADO_BORRADOR,
    ESTADO_CONFIRMADO,
    anular_movimiento_fiscal,
    confirmar_movimiento_fiscal,
    listar_eventos_movimiento,
    listar_movimientos_fiscales,
    opciones_origenes,
    opciones_tipos_concepto,
    registrar_movimiento_fiscal,
    validar_movimiento_fiscal_dict,
)


# ======================================================
# MÓDULO IVA PRO
# Etapa 1: Posición mensual
# Etapa 2: Movimientos fiscales adicionales
# ======================================================
#
# Criterio:
# - No modifica Ventas.
# - No modifica Compras.
# - No modifica Banco/Caja.
# - No modifica Cobranzas/Pagos.
# - No modifica Conciliación.
# - Lee información fiscal ya persistida y arma papel de trabajo mensual.
# - Permite registrar movimientos fiscales adicionales controlados.
#
# Nota de diseño:
# Los movimientos fiscales adicionales sirven para conceptos que no nacen
# directamente de Ventas/Compras, por ejemplo:
# - IVA de comisiones bancarias.
# - Percepciones IVA bancarias.
# - Retenciones IVA sufridas.
# - Saldos anteriores.
# - Saldos de libre disponibilidad aplicados.
# - Pagos a cuenta.
# - Ajustes técnicos controlados.
#
# Banco fiscal se integrará más adelante desde Banco/Conciliación.
# Por ahora se permite carga manual controlada con origen y trazabilidad.


TIPOS_CONCEPTO_IVA_OPERATIVOS = {
    "IVA_DEBITO",
    "IVA_CREDITO",
    "IVA_NO_COMPUTABLE",
    "PERCEPCION_IVA",
    "RETENCION_IVA",
    "SALDO_TECNICO_ANTERIOR",
    "SALDO_LIBRE_DISPONIBILIDAD",
    "PAGO_A_CUENTA",
    "AJUSTE_SALDO",
}

TIPOS_CONCEPTO_SOLO_CONTROL = {
    "PERCEPCION_IIBB_INFORMATIVA",
    "OTRO",
}


def _separar_movimientos_operativos_e_informativos(df):
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()

    if "tipo_concepto" not in df.columns:
        return df.copy(), pd.DataFrame()

    tipos = df["tipo_concepto"].astype(str).str.strip().str.upper()
    operativo = df[tipos.isin(TIPOS_CONCEPTO_IVA_OPERATIVOS)].copy()
    informativo = df[~tipos.isin(TIPOS_CONCEPTO_IVA_OPERATIVOS)].copy()
    return operativo, informativo


# ======================================================
# HELPERS UI
# ======================================================

def _obtener_empresa_id_actual():
    """
    Obtiene empresa_id desde session_state de manera defensiva.
    Mantiene compatibilidad con distintas claves usadas durante la evolución del sistema.
    """
    posibles_claves_directas = [
        "empresa_id",
        "empresa_actual_id",
        "empresa_seleccionada_id",
        "id_empresa",
    ]

    for clave in posibles_claves_directas:
        valor = st.session_state.get(clave)
        try:
            if valor is not None and int(valor) > 0:
                return int(valor)
        except Exception:
            pass

    posibles_objetos = [
        "empresa_actual",
        "empresa_seleccionada",
        "empresa",
    ]

    for clave in posibles_objetos:
        empresa = st.session_state.get(clave)

        if isinstance(empresa, dict):
            for subclave in ["id", "empresa_id", "id_empresa"]:
                try:
                    valor = empresa.get(subclave)
                    if valor is not None and int(valor) > 0:
                        return int(valor)
                except Exception:
                    pass

    return 1


def _obtener_nombre_empresa_actual():
    posibles_objetos = [
        "empresa_actual",
        "empresa_seleccionada",
        "empresa",
    ]

    for clave in posibles_objetos:
        empresa = st.session_state.get(clave)

        if isinstance(empresa, dict):
            for subclave in ["razon_social", "nombre", "empresa", "descripcion"]:
                valor = empresa.get(subclave)
                if valor:
                    return str(valor).strip()

    for clave in ["empresa_nombre", "razon_social_empresa", "nombre_empresa"]:
        valor = st.session_state.get(clave)
        if valor:
            return str(valor).strip()

    return "Empresa actual"


def _obtener_usuario_actual():
    posibles = [
        "usuario",
        "usuario_actual",
        "user",
        "username",
        "email",
    ]

    for clave in posibles:
        valor = st.session_state.get(clave)

        if isinstance(valor, dict):
            for subclave in ["email", "nombre", "usuario", "username"]:
                dato = valor.get(subclave)
                if dato:
                    return str(dato).strip()

        if valor:
            return str(valor).strip()

    return "sistema"


def _float(valor, default=0.0):
    try:
        if valor is None:
            return default
        return float(valor)
    except Exception:
        return default


def _int(valor, default=0):
    try:
        if valor is None:
            return default
        return int(float(valor))
    except Exception:
        return default


def _mes_nombre(mes):
    nombres = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }

    return nombres.get(_int(mes), f"Mes {mes}")


def _periodo_largo(anio, mes):
    return f"{_mes_nombre(mes)} {anio}"


def _mostrar_dataframe(df, altura=420):
    """
    Wrapper defensivo para mantener compatibilidad entre versiones de Streamlit.
    """
    if df is None or df.empty:
        st.info("No hay datos para mostrar.")
        return

    try:
        st.dataframe(
            df,
            hide_index=True,
            width="stretch",
            height=altura,
        )
    except TypeError:
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            height=altura,
        )


def _boton_accion(label, key, tipo="secondary"):
    try:
        return st.button(label, key=key, type=tipo, use_container_width=True)
    except TypeError:
        return st.button(label, key=key)


def _descargar_excel(data, file_name, label="Descargar papel de trabajo Excel"):
    try:
        st.download_button(
            label=label,
            data=data,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except TypeError:
        st.download_button(
            label=label,
            data=data,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def _aplicar_busqueda(df, texto_busqueda):
    if df is None or df.empty:
        return pd.DataFrame()

    texto_busqueda = str(texto_busqueda or "").strip().lower()

    if not texto_busqueda:
        return df.copy()

    df_texto = df.astype(str).apply(
        lambda col: col.str.lower(),
        axis=0,
    )

    mascara = df_texto.apply(
        lambda row: row.str.contains(texto_busqueda, na=False).any(),
        axis=1,
    )

    return df[mascara].copy()


def _redondear_columnas_monetarias(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    posibles = [
        "neto_ventas",
        "iva_debito_fiscal_ventas",
        "iva_debito_fiscal",
        "total_ventas",

        "neto_compras",
        "iva_total_compras",
        "credito_fiscal_computable_compras",
        "credito_fiscal_computable",
        "iva_no_computable_compras",
        "iva_no_computable",
        "percepciones_iva_compras",
        "percepciones_iva",
        "percepciones_iibb_compras_informativas",
        "percepciones_iibb_informativas",
        "total_compras",

        "neto_movimientos_fiscales",
        "iva_debito_adicional",
        "credito_fiscal_computable_adicional",
        "iva_no_computable_adicional",
        "percepciones_iva_adicionales",
        "retenciones_iva_sufridas",
        "percepciones_iibb_adicionales_informativas",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
        "otros_tributos_adicionales",
        "total_movimientos_fiscales",

        "saldo_tecnico_iva",
        "percepciones_iva_sufridas",
        "saldo_preliminar_periodo",

        "neto",
        "iva_debito",
        "iva_credito",
        "percepcion_iva",
        "retencion_iva",
        "percepcion_iibb_informativa",
        "total",

        "neto_original",
        "iva_original",
        "iva_total_original",
        "credito_fiscal_computable_original",
        "iva_no_computable_original",
        "percepcion_iva_original",
        "percepcion_iibb_original",
        "total_original",

        "neto_gravado",
        "otros_tributos",
    ]

    for columna in posibles:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce").fillna(0).round(2)

    return df


def _renombrar_columnas(df):
    if df is None or df.empty:
        return pd.DataFrame()

    nombres = {
        "empresa_id": "Empresa ID",
        "anio": "Año",
        "mes": "Mes",
        "periodo": "Período",

        "origen": "Origen",
        "tipo_concepto": "Tipo concepto",
        "descripcion": "Descripción",
        "estado": "Estado",
        "id": "ID",
        "fecha": "Fecha",
        "codigo": "Código",
        "tipo": "Tipo",
        "punto_venta": "Punto venta",
        "numero": "Número",
        "cliente": "Cliente",
        "proveedor": "Proveedor",
        "contraparte": "Contraparte",
        "cuit": "CUIT",
        "categoria_compra": "Categoría compra",
        "archivo": "Archivo",

        "neto_ventas": "Neto ventas",
        "iva_debito_fiscal_ventas": "IVA débito ventas",
        "iva_debito_fiscal": "IVA débito fiscal",
        "total_ventas": "Total ventas",

        "neto_compras": "Neto compras",
        "iva_total_compras": "IVA total compras",
        "credito_fiscal_computable_compras": "Crédito fiscal compras",
        "credito_fiscal_computable": "Crédito fiscal computable",
        "iva_no_computable_compras": "IVA no computable compras",
        "iva_no_computable": "IVA no computable",
        "percepciones_iva_compras": "Percepciones IVA compras",
        "percepciones_iva": "Percepciones IVA",
        "percepciones_iibb_compras_informativas": "Percepciones IIBB compras informativas",
        "percepciones_iibb_informativas": "Percepciones IIBB informativas",
        "total_compras": "Total compras",

        "neto_movimientos_fiscales": "Neto mov. fiscales",
        "iva_debito_adicional": "IVA débito adicional",
        "credito_fiscal_computable_adicional": "Crédito fiscal adicional",
        "iva_no_computable_adicional": "IVA no computable adicional",
        "percepciones_iva_adicionales": "Percepciones IVA adicionales",
        "retenciones_iva_sufridas": "Retenciones IVA sufridas",
        "percepciones_iibb_adicionales_informativas": "Percepciones IIBB adicionales informativas",
        "saldo_tecnico_anterior": "Saldo técnico anterior",
        "saldo_libre_disponibilidad": "Saldo libre disponibilidad",
        "pago_a_cuenta": "Pago a cuenta",
        "otros_tributos_adicionales": "Otros tributos adicionales",
        "total_movimientos_fiscales": "Total mov. fiscales",

        "saldo_tecnico_iva": "Saldo técnico IVA",
        "percepciones_iva_sufridas": "Percepciones IVA sufridas",
        "saldo_preliminar_periodo": "Saldo preliminar período",

        "cantidad_ventas": "Cant. ventas",
        "cantidad_compras": "Cant. compras",
        "cantidad_movimientos_fiscales": "Cant. mov. fiscales",
        "cantidad_total": "Cant. total",
        "cantidad": "Cantidad",

        "neto": "Neto",
        "iva_debito": "IVA débito",
        "iva_credito": "IVA crédito",
        "percepcion_iva": "Percepción IVA",
        "retencion_iva": "Retención IVA",
        "percepcion_iibb_informativa": "Percepción IIBB informativa",
        "total": "Total",

        "neto_original": "Neto original",
        "iva_original": "IVA original",
        "iva_total_original": "IVA total original",
        "credito_fiscal_computable_original": "Crédito fiscal original",
        "iva_no_computable_original": "IVA no computable original",
        "percepcion_iva_original": "Percepción IVA original",
        "percepcion_iibb_original": "Percepción IIBB original",
        "total_original": "Total original",
        "signo_fiscal": "Signo fiscal",

        "neto_gravado": "Neto gravado",
        "otros_tributos": "Otros tributos",
        "observacion": "Observación",
        "usuario": "Usuario",
        "fecha_carga": "Fecha carga",
        "fecha_confirmacion": "Fecha confirmación",
        "fecha_anulacion": "Fecha anulación",
        "motivo_anulacion": "Motivo anulación",
        "origen_tabla": "Origen tabla",
        "origen_id": "Origen ID",
        "comprobante_codigo": "Código comp.",
        "comprobante_tipo": "Tipo comp.",
    }

    return df.rename(columns=nombres)


def _preparar_df_ui(df):
    return _renombrar_columnas(_redondear_columnas_monetarias(df))


def _selector_periodo(periodos, key_prefix):
    """
    Permite seleccionar período disponible. Si no hay períodos, permite selección manual.
    """
    if periodos is None or periodos.empty:
        st.warning(
            "No se detectaron períodos con movimientos en Ventas, Compras o movimientos fiscales. "
            "Podés seleccionar un período manualmente para revisar si hay datos pendientes."
        )

        col1, col2 = st.columns(2)

        with col1:
            anio = st.number_input(
                "Año",
                min_value=2000,
                max_value=2100,
                value=2025,
                step=1,
                key=f"{key_prefix}_anio_manual",
            )

        with col2:
            mes = st.number_input(
                "Mes",
                min_value=1,
                max_value=12,
                value=1,
                step=1,
                key=f"{key_prefix}_mes_manual",
            )

        return int(anio), int(mes)

    periodos = periodos.copy().reset_index(drop=True)

    opciones = list(periodos.index)

    def _label(indice):
        row = periodos.loc[indice]
        anio = _int(row.get("anio"))
        mes = _int(row.get("mes"))
        ventas = _int(row.get("cantidad_ventas"))
        compras = _int(row.get("cantidad_compras"))
        mov_fiscales = _int(row.get("cantidad_movimientos_fiscales"))
        total = _int(row.get("cantidad_total"))

        return (
            f"{anio}-{mes:02d} · {_periodo_largo(anio, mes)} "
            f"· Ventas: {ventas} · Compras: {compras} "
            f"· Mov. fiscales: {mov_fiscales} · Total: {total}"
        )

    seleccionado = st.selectbox(
        "Período IVA",
        opciones,
        format_func=_label,
        key=f"{key_prefix}_periodo",
    )

    row = periodos.loc[seleccionado]

    return int(row["anio"]), int(row["mes"])


def _mostrar_alertas(alertas):
    if not alertas:
        st.success("No se detectaron alertas de control para el período.")
        return

    for alerta in alertas:
        nivel = str(alerta.get("nivel", "INFO")).upper()
        titulo = str(alerta.get("titulo", "Alerta"))
        detalle = str(alerta.get("detalle", ""))

        mensaje = f"**{titulo}**\n\n{detalle}"

        if nivel == "ERROR":
            st.error(mensaje)
        elif nivel in {"ADVERTENCIA", "WARNING"}:
            st.warning(mensaje)
        else:
            st.info(mensaje)


def _mostrar_estado_saldo(posicion):
    saldo = _float(posicion.get("saldo_preliminar_periodo", 0))
    etiqueta = etiqueta_resultado_saldo(saldo)

    if saldo > 0.05:
        st.warning(f"{etiqueta}: **{formato_moneda(saldo)}**")
    elif saldo < -0.05:
        st.success(f"{etiqueta}: **{formato_moneda(abs(saldo))}**")
    else:
        st.info(f"{etiqueta}: **{formato_moneda(saldo)}**")


def _mostrar_metricas_posicion(posicion):
    st.markdown("#### Resumen mensual")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "IVA Débito Fiscal",
            formato_moneda(posicion.get("iva_debito_fiscal", 0)),
            help="IVA generado por ventas más débitos fiscales adicionales confirmados.",
        )

    with col2:
        st.metric(
            "Crédito fiscal computable",
            formato_moneda(posicion.get("credito_fiscal_computable", 0)),
            help="IVA computable de compras más crédito fiscal adicional confirmado.",
        )

    with col3:
        st.metric(
            "Saldo técnico IVA",
            formato_moneda(posicion.get("saldo_tecnico_iva", 0)),
            help="IVA débito fiscal menos crédito fiscal computable.",
        )

    col4, col5, col6 = st.columns(3)

    with col4:
        st.metric(
            "Percepciones IVA sufridas",
            formato_moneda(posicion.get("percepciones_iva_sufridas", 0)),
            help="Percepciones de IVA de compras y movimientos fiscales confirmados.",
        )

    with col5:
        st.metric(
            "Retenciones IVA sufridas",
            formato_moneda(posicion.get("retenciones_iva_sufridas", 0)),
            help="Retenciones IVA adicionales cargadas como movimientos fiscales.",
        )

    with col6:
        st.metric(
            "Saldo preliminar período",
            formato_moneda(posicion.get("saldo_preliminar_periodo", 0)),
            help="Saldo técnico menos percepciones, retenciones, saldos aplicables y pagos a cuenta.",
        )

    _mostrar_estado_saldo(posicion)


def _mostrar_composicion(posicion):
    st.markdown("#### Composición de la posición")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("##### Ventas")
        st.write(f"**Neto ventas:** {formato_moneda(posicion.get('neto_ventas', 0))}")
        st.write(
            f"**IVA débito ventas:** "
            f"{formato_moneda(posicion.get('iva_debito_fiscal_ventas', 0))}"
        )
        st.write(f"**Total ventas:** {formato_moneda(posicion.get('total_ventas', 0))}")
        st.write(f"**Cantidad comprobantes:** {_int(posicion.get('cantidad_ventas', 0))}")

    with col2:
        st.markdown("##### Compras")
        st.write(f"**Neto compras:** {formato_moneda(posicion.get('neto_compras', 0))}")
        st.write(f"**IVA total compras:** {formato_moneda(posicion.get('iva_total_compras', 0))}")
        st.write(
            f"**Crédito fiscal compras:** "
            f"{formato_moneda(posicion.get('credito_fiscal_computable_compras', 0))}"
        )
        st.write(
            f"**IVA no computable compras:** "
            f"{formato_moneda(posicion.get('iva_no_computable_compras', 0))}"
        )
        st.write(
            f"**Percepciones IVA compras:** "
            f"{formato_moneda(posicion.get('percepciones_iva_compras', 0))}"
        )
        st.write(
            f"**Percepciones IIBB compras informativas:** "
            f"{formato_moneda(posicion.get('percepciones_iibb_compras_informativas', 0))}"
        )
        st.write(f"**Total compras:** {formato_moneda(posicion.get('total_compras', 0))}")
        st.write(f"**Cantidad comprobantes:** {_int(posicion.get('cantidad_compras', 0))}")

    with col3:
        st.markdown("##### Movimientos fiscales")
        st.write(
            f"**IVA débito adicional:** "
            f"{formato_moneda(posicion.get('iva_debito_adicional', 0))}"
        )
        st.write(
            f"**Crédito fiscal adicional:** "
            f"{formato_moneda(posicion.get('credito_fiscal_computable_adicional', 0))}"
        )
        st.write(
            f"**Percepciones IVA adicionales:** "
            f"{formato_moneda(posicion.get('percepciones_iva_adicionales', 0))}"
        )
        st.write(
            f"**Retenciones IVA sufridas:** "
            f"{formato_moneda(posicion.get('retenciones_iva_sufridas', 0))}"
        )
        st.write(
            f"**Saldo técnico anterior aplicado:** "
            f"{formato_moneda(posicion.get('saldo_tecnico_anterior', 0))}"
        )
        st.write(
            f"**Saldo libre disponibilidad aplicado:** "
            f"{formato_moneda(posicion.get('saldo_libre_disponibilidad', 0))}"
        )
        st.write(f"**Pago a cuenta:** {formato_moneda(posicion.get('pago_a_cuenta', 0))}")
        st.write(
            f"**Cantidad movimientos:** "
            f"{_int(posicion.get('cantidad_movimientos_fiscales', 0))}"
        )


def _mostrar_resumen_origenes(resumen_origenes):
    st.markdown("#### Resumen por origen fiscal")

    st.caption(
        "VENTAS y COMPRAS se alimentan desde los módulos operativos. "
        "MOVIMIENTOS_FISCALES registra conceptos adicionales confirmados del período."
    )

    df_ui = _preparar_df_ui(resumen_origenes)
    _mostrar_dataframe(df_ui, altura=260)


def _mostrar_exportacion_excel(empresa_id, anio, mes):
    st.markdown("#### Papel de trabajo Excel")

    st.caption(
        "El archivo exporta Posición IVA, resumen por origen, Libro IVA Ventas, "
        "Libro IVA Compras, movimientos fiscales adicionales y alertas de control. "
        "No es todavía TXT Portal IVA."
    )

    try:
        excel = generar_papel_trabajo_excel_iva(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )

        nombre = nombre_archivo_papel_trabajo_iva(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )

        _descargar_excel(
            data=excel,
            file_name=nombre,
            label="Descargar papel de trabajo IVA Excel",
        )

    except Exception as e:
        st.error(f"No se pudo generar el Excel de IVA: {e}")


def _mostrar_detalle_ventas(detalle_ventas, key_prefix="ventas"):
    st.markdown("#### Detalle Libro IVA Ventas")

    if detalle_ventas is None or detalle_ventas.empty:
        st.info("No hay comprobantes de ventas para el período seleccionado.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar en ventas",
            placeholder="Cliente, CUIT, tipo, número, archivo...",
            key=f"{key_prefix}_buscar",
        )

    with col2:
        mostrar_columnas_tecnicas = st.checkbox(
            "Mostrar columnas técnicas",
            value=False,
            key=f"{key_prefix}_tecnicas",
        )

    df = detalle_ventas.copy()
    df = _aplicar_busqueda(df, busqueda)

    columnas_base = [
        "fecha",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "neto_ventas",
        "iva_debito_fiscal",
        "total_ventas",
        "archivo",
    ]

    columnas_tecnicas = [
        "origen",
        "id",
        "anio",
        "mes",
        "neto_original",
        "iva_original",
        "total_original",
        "signo_fiscal",
    ]

    columnas = columnas_base + columnas_tecnicas if mostrar_columnas_tecnicas else columnas_base
    columnas = [col for col in columnas if col in df.columns]

    st.caption(f"Comprobantes visibles: {len(df)}")

    df_ui = _preparar_df_ui(df[columnas])
    _mostrar_dataframe(df_ui, altura=460)


def _mostrar_detalle_compras(detalle_compras, key_prefix="compras"):
    st.markdown("#### Detalle Libro IVA Compras")

    if detalle_compras is None or detalle_compras.empty:
        st.info("No hay comprobantes de compras para el período seleccionado.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar en compras",
            placeholder="Proveedor, CUIT, categoría, tipo, número, archivo...",
            key=f"{key_prefix}_buscar",
        )

    with col2:
        mostrar_columnas_tecnicas = st.checkbox(
            "Mostrar columnas técnicas",
            value=False,
            key=f"{key_prefix}_tecnicas",
        )

    df = detalle_compras.copy()
    df = _aplicar_busqueda(df, busqueda)

    columnas_base = [
        "fecha",
        "codigo",
        "tipo",
        "punto_venta",
        "numero",
        "proveedor",
        "cuit",
        "categoria_compra",
        "neto_compras",
        "iva_total_compras",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepciones_iva",
        "percepciones_iibb_informativas",
        "total_compras",
        "archivo",
    ]

    columnas_tecnicas = [
        "origen",
        "id",
        "anio",
        "mes",
        "neto_original",
        "iva_original",
        "iva_total_original",
        "credito_fiscal_computable_original",
        "iva_no_computable_original",
        "percepcion_iva_original",
        "percepcion_iibb_original",
        "total_original",
        "signo_fiscal",
    ]

    columnas = columnas_base + columnas_tecnicas if mostrar_columnas_tecnicas else columnas_base
    columnas = [col for col in columnas if col in df.columns]

    st.caption(f"Comprobantes visibles: {len(df)}")

    df_ui = _preparar_df_ui(df[columnas])
    _mostrar_dataframe(df_ui, altura=460)


def _mostrar_resumen_periodos(empresa_id):
    st.markdown("#### Resumen de posiciones disponibles")

    try:
        resumen = obtener_resumen_posiciones_iva(empresa_id=empresa_id)
    except Exception as e:
        st.error(f"No se pudo calcular el resumen de períodos: {e}")
        return

    if resumen.empty:
        st.info("Todavía no hay períodos con datos suficientes para mostrar resumen.")
        return

    columnas = [
        "periodo",
        "neto_ventas",
        "iva_debito_fiscal",
        "total_ventas",
        "neto_compras",
        "iva_total_compras",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepciones_iva",
        "percepciones_iibb_informativas",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
        "retenciones_iva_sufridas",
        "saldo_tecnico_iva",
        "saldo_preliminar_periodo",
        "cantidad_ventas",
        "cantidad_compras",
        "cantidad_movimientos_fiscales",
    ]

    columnas = [col for col in columnas if col in resumen.columns]

    df_ui = _preparar_df_ui(resumen[columnas])
    _mostrar_dataframe(df_ui, altura=360)


# ======================================================
# MOVIMIENTOS FISCALES UI
# ======================================================

def _campos_por_tipo_concepto(tipo_concepto):
    tipo = str(tipo_concepto or "").upper()

    campos = {
        "neto_gravado": False,
        "iva_debito": False,
        "credito_fiscal_computable": False,
        "iva_no_computable": False,
        "percepcion_iva": False,
        "retencion_iva": False,
        "percepcion_iibb_informativa": False,
        "saldo_tecnico_anterior": False,
        "saldo_libre_disponibilidad": False,
        "pago_a_cuenta": False,
        "otros_tributos": True,
        "total": True,
    }

    if tipo == "IVA_DEBITO":
        campos.update({
            "neto_gravado": True,
            "iva_debito": True,
        })

    elif tipo == "IVA_CREDITO":
        campos.update({
            "neto_gravado": True,
            "credito_fiscal_computable": True,
            "iva_no_computable": True,
        })

    elif tipo == "IVA_NO_COMPUTABLE":
        campos.update({
            "neto_gravado": True,
            "iva_no_computable": True,
        })

    elif tipo == "PERCEPCION_IVA":
        campos.update({
            "percepcion_iva": True,
        })

    elif tipo == "RETENCION_IVA":
        campos.update({
            "retencion_iva": True,
        })

    elif tipo == "PERCEPCION_IIBB_INFORMATIVA":
        campos.update({
            "percepcion_iibb_informativa": True,
        })

    elif tipo == "SALDO_TECNICO_ANTERIOR":
        campos.update({
            "saldo_tecnico_anterior": True,
        })

    elif tipo == "SALDO_LIBRE_DISPONIBILIDAD":
        campos.update({
            "saldo_libre_disponibilidad": True,
        })

    elif tipo == "PAGO_A_CUENTA":
        campos.update({
            "pago_a_cuenta": True,
        })

    elif tipo == "AJUSTE_SALDO":
        campos.update({
            "iva_debito": True,
            "credito_fiscal_computable": True,
            "percepcion_iva": True,
            "retencion_iva": True,
            "saldo_tecnico_anterior": True,
            "saldo_libre_disponibilidad": True,
            "pago_a_cuenta": True,
        })

    else:
        campos = {clave: True for clave in campos}

    return campos


def _number_input_importe(label, key, visible=True, help_text=None):
    if not visible:
        return 0.0

    return float(st.number_input(
        label,
        value=0.0,
        step=100.0,
        format="%.2f",
        key=key,
        help=help_text,
    ))


def _mostrar_formulario_movimiento_fiscal(empresa_id, anio, mes):
    st.markdown("#### Cargar movimiento fiscal adicional")

    st.info(
        "Usá esta carga para conceptos fiscales que no vienen de Ventas/Compras. "
        "Ejemplo: IVA por comisión bancaria, percepción IVA bancaria, retención IVA sufrida, "
        "saldo técnico anterior o pago a cuenta. No reemplaza ni duplica comprobantes de compras."
    )

    with st.form("form_iva_movimiento_fiscal", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            fecha = st.date_input(
                "Fecha",
                key="iva_mov_fecha",
                help="Fecha del concepto fiscal. El período se toma de la selección superior.",
            )

        with col2:
            origenes = opciones_origenes()
            origen_default = origenes.index("MANUAL") if "MANUAL" in origenes else 0
            origen = st.selectbox(
                "Origen",
                origenes,
                index=origen_default,
                key="iva_mov_origen",
            )

        with col3:
            tipos = opciones_tipos_concepto()
            tipo_default = tipos.index("IVA_CREDITO") if "IVA_CREDITO" in tipos else 0
            tipo_concepto = st.selectbox(
                "Tipo de concepto",
                tipos,
                index=tipo_default,
                key="iva_mov_tipo",
            )

        descripcion = st.text_input(
            "Descripción obligatoria",
            placeholder="Ej.: Comisión bancaria diciembre con IVA / Percepción IVA banco",
            key="iva_mov_descripcion",
        )

        col4, col5, col6 = st.columns(3)

        with col4:
            contraparte = st.text_input(
                "Contraparte",
                placeholder="Banco / agente / proveedor / descripción",
                key="iva_mov_contraparte",
            )

        with col5:
            cuit = st.text_input(
                "CUIT",
                placeholder="Opcional",
                key="iva_mov_cuit",
            )

        with col6:
            estado = st.selectbox(
                "Estado inicial",
                [ESTADO_CONFIRMADO, ESTADO_BORRADOR],
                key="iva_mov_estado",
                help="Solo CONFIRMADO impacta la posición IVA.",
            )

        with st.expander("Datos del comprobante o referencia", expanded=False):
            c1, c2, c3, c4 = st.columns(4)

            with c1:
                comprobante_codigo = st.text_input("Código", key="iva_mov_codigo")

            with c2:
                comprobante_tipo = st.text_input("Tipo", key="iva_mov_comp_tipo")

            with c3:
                punto_venta = st.text_input("Punto venta", key="iva_mov_pv")

            with c4:
                numero = st.text_input("Número", key="iva_mov_numero")

        campos = _campos_por_tipo_concepto(tipo_concepto)

        st.markdown("##### Importes fiscales")

        c7, c8, c9 = st.columns(3)

        with c7:
            neto_gravado = _number_input_importe(
                "Neto gravado",
                "iva_mov_neto",
                campos["neto_gravado"],
            )
            iva_debito = _number_input_importe(
                "IVA débito",
                "iva_mov_iva_debito",
                campos["iva_debito"],
            )
            credito_fiscal_computable = _number_input_importe(
                "Crédito fiscal computable",
                "iva_mov_credito",
                campos["credito_fiscal_computable"],
            )
            iva_no_computable = _number_input_importe(
                "IVA no computable",
                "iva_mov_no_comp",
                campos["iva_no_computable"],
            )

        with c8:
            percepcion_iva = _number_input_importe(
                "Percepción IVA",
                "iva_mov_perc_iva",
                campos["percepcion_iva"],
            )
            retencion_iva = _number_input_importe(
                "Retención IVA",
                "iva_mov_ret_iva",
                campos["retencion_iva"],
            )
            percepcion_iibb_informativa = _number_input_importe(
                "Percepción IIBB informativa",
                "iva_mov_perc_iibb",
                campos["percepcion_iibb_informativa"],
            )
            otros_tributos = _number_input_importe(
                "Otros tributos",
                "iva_mov_otros_tributos",
                campos["otros_tributos"],
            )

        with c9:
            saldo_tecnico_anterior = _number_input_importe(
                "Saldo técnico anterior aplicado",
                "iva_mov_saldo_tecnico_ant",
                campos["saldo_tecnico_anterior"],
                help_text="Cargar positivo si reduce el saldo del período.",
            )
            saldo_libre_disponibilidad = _number_input_importe(
                "Saldo libre disponibilidad aplicado",
                "iva_mov_sld",
                campos["saldo_libre_disponibilidad"],
                help_text="Cargar positivo si se aplica contra IVA.",
            )
            pago_a_cuenta = _number_input_importe(
                "Pago a cuenta",
                "iva_mov_pago_cuenta",
                campos["pago_a_cuenta"],
                help_text="Cargar positivo si reduce el saldo del período.",
            )
            total = _number_input_importe(
                "Total / importe de referencia",
                "iva_mov_total",
                campos["total"],
            )

        observacion = st.text_area(
            "Observación",
            placeholder="Detalle interno para auditoría fiscal.",
            key="iva_mov_observacion",
        )

        movimiento_preview = {
            "tipo_concepto": tipo_concepto,
            "iva_debito": iva_debito,
            "credito_fiscal_computable": credito_fiscal_computable,
            "iva_no_computable": iva_no_computable,
            "percepcion_iva": percepcion_iva,
            "retencion_iva": retencion_iva,
            "saldo_tecnico_anterior": saldo_tecnico_anterior,
            "saldo_libre_disponibilidad": saldo_libre_disponibilidad,
            "pago_a_cuenta": pago_a_cuenta,
        }

        alertas = validar_movimiento_fiscal_dict(movimiento_preview)

        if alertas:
            st.markdown("##### Controles previos")
            _mostrar_alertas(alertas)

        guardar = st.form_submit_button("Guardar movimiento fiscal")

        if guardar:
            try:
                registrar_movimiento_fiscal(
                    empresa_id=empresa_id,
                    anio=anio,
                    mes=mes,
                    fecha=fecha,
                    origen=origen,
                    tipo_concepto=tipo_concepto,
                    descripcion=descripcion,
                    contraparte=contraparte,
                    cuit=cuit,
                    comprobante_codigo=comprobante_codigo,
                    comprobante_tipo=comprobante_tipo,
                    punto_venta=punto_venta,
                    numero=numero,
                    neto_gravado=neto_gravado,
                    iva_debito=iva_debito,
                    credito_fiscal_computable=credito_fiscal_computable,
                    iva_no_computable=iva_no_computable,
                    percepcion_iva=percepcion_iva,
                    retencion_iva=retencion_iva,
                    percepcion_iibb_informativa=percepcion_iibb_informativa,
                    saldo_tecnico_anterior=saldo_tecnico_anterior,
                    saldo_libre_disponibilidad=saldo_libre_disponibilidad,
                    pago_a_cuenta=pago_a_cuenta,
                    otros_tributos=otros_tributos,
                    total=total,
                    estado=estado,
                    observacion=observacion,
                    usuario=_obtener_usuario_actual(),
                )

                st.success(
                    "Movimiento fiscal registrado correctamente. "
                    "Si quedó CONFIRMADO, ya impacta la posición IVA del período."
                )
                st.rerun()

            except Exception as e:
                st.error(f"No se pudo guardar el movimiento fiscal: {e}")



def _valor_bool_fiscal(valor, default=False):
    """Convierte flags de base/SQLite a booleano sin romper valores vacíos."""
    if valor is None:
        return default

    try:
        if pd.isna(valor):
            return default
    except Exception:
        pass

    if isinstance(valor, bool):
        return valor

    texto = str(valor).strip().upper()

    if texto in {"1", "TRUE", "T", "SI", "SÍ", "YES", "Y"}:
        return True

    if texto in {"0", "FALSE", "F", "NO", "N"}:
        return False

    return default


def _obtener_flag_inclusion_movimiento(row):
    """
    Determina si un movimiento confirmado impacta en la posición IVA.
    Si la columna todavía no existe en alguna base vieja, conserva compatibilidad:
    un movimiento CONFIRMADO se considera incluido, como en la etapa anterior.
    """
    for columna in [
        "incluido_en_posicion",
        "incluido_en_posicion_actual",
        "incluido_posicion",
    ]:
        try:
            if columna in row.index:
                return _valor_bool_fiscal(row.get(columna), default=False)
        except Exception:
            pass

    return str(row.get("estado", "")).upper() == ESTADO_CONFIRMADO


def _decision_movimiento_fiscal(row):
    estado = str(row.get("estado", "")).strip().upper()

    if estado == ESTADO_ANULADO:
        return "Anulado por error"

    if estado == ESTADO_BORRADOR:
        return "Pendiente de revisión"

    if estado == ESTADO_CONFIRMADO:
        if _obtener_flag_inclusion_movimiento(row):
            return "Tomado en IVA del período"
        return "No tomado este mes"

    return "Sin decisión"


def _preparar_movimientos_fiscales_con_decision(df):
    if df is None or df.empty:
        return pd.DataFrame()

    preparado = df.copy()
    preparado["decision_periodo"] = preparado.apply(_decision_movimiento_fiscal, axis=1)

    for columna in [
        "neto_gravado",
        "iva_debito",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepcion_iva",
        "retencion_iva",
        "percepcion_iibb_informativa",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
        "otros_tributos",
        "total",
    ]:
        if columna in preparado.columns:
            preparado[columna] = pd.to_numeric(preparado[columna], errors="coerce").fillna(0.0)

    return preparado


def _resumen_movimientos_fiscales_por_concepto(df):
    df = _preparar_movimientos_fiscales_con_decision(df)

    if df.empty:
        return pd.DataFrame()

    columnas_sumables = [
        "neto_gravado",
        "iva_debito",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepcion_iva",
        "retencion_iva",
        "percepcion_iibb_informativa",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
        "otros_tributos",
        "total",
    ]
    columnas_sumables = [col for col in columnas_sumables if col in df.columns]

    agrupado = (
        df.groupby(["tipo_concepto", "decision_periodo"], dropna=False, as_index=False)
        .agg(
            movimientos=("id", "count") if "id" in df.columns else ("tipo_concepto", "count"),
            **{col: (col, "sum") for col in columnas_sumables},
        )
    )

    agrupado = agrupado.sort_values(
        by=["decision_periodo", "tipo_concepto"],
        ascending=[True, True],
    )

    return agrupado



def _importe_relevante_para_iva(df):
    """
    Importe operativo para decidir IVA.
    Excluye Percepción IIBB informativa y otros tributos para no mezclar controles con cómputo IVA.
    """
    if df is None or df.empty:
        return 0.0

    columnas = [
        "iva_debito",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepcion_iva",
        "retencion_iva",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
    ]

    total = 0.0
    for columna in columnas:
        if columna in df.columns:
            total += float(pd.to_numeric(df[columna], errors="coerce").fillna(0.0).sum())

    return round(total, 2)


def _mostrar_tablero_decisiones_movimientos(df):
    df = _preparar_movimientos_fiscales_con_decision(df)

    if df.empty:
        st.info("No hay movimientos fiscales adicionales cargados para este período.")
        return

    tomado = df[df["decision_periodo"] == "Tomado en IVA del período"].copy()
    no_tomado = df[df["decision_periodo"] == "No tomado este mes"].copy()
    borrador = df[df["decision_periodo"] == "Pendiente de revisión"].copy()
    anulado = df[df["decision_periodo"] == "Anulado por error"].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Tomado en IVA del período",
        formato_moneda(_importe_relevante_para_iva(tomado)),
        help="Importes que impactan la posición IVA del mes.",
    )
    c2.metric(
        "Pendiente / no tomado",
        formato_moneda(_importe_relevante_para_iva(pd.concat([no_tomado, borrador], ignore_index=True))),
        help="Importes que no impactan este mes porque quedaron pendientes o no tomados.",
    )
    c3.metric(
        "Anulado",
        formato_moneda(_importe_relevante_para_iva(anulado)),
        help="Importes anulados. No impactan IVA.",
    )

    st.caption(
        "Vista simple: tomado impacta IVA; pendiente/no tomado no impacta; anulado queda fuera. "
        "Los estados técnicos quedan ocultos en el detalle."
    )


def _mostrar_resumen_agregado_movimientos_fiscales(df, titulo="Resumen mensual por concepto"):
    resumen = _resumen_movimientos_fiscales_por_concepto(df)

    if resumen.empty:
        st.info("No hay movimientos fiscales adicionales para resumir.")
        return

    st.markdown(f"#### {titulo}")
    st.caption(
        "Importes agrupados. Para decidir el IVA mirá principalmente Crédito fiscal, Percepción IVA y Retención IVA. "
        "IIBB y otros tributos quedan como información de control."
    )

    columnas = [
        "tipo_concepto",
        "decision_periodo",
        "movimientos",
        "credito_fiscal_computable",
        "percepcion_iva",
        "retencion_iva",
        "iva_debito",
        "iva_no_computable",
        "saldo_tecnico_anterior",
        "saldo_libre_disponibilidad",
        "pago_a_cuenta",
    ]
    columnas = [col for col in columnas if col in resumen.columns]

    df_ui = _preparar_df_ui(resumen[columnas])
    df_ui = df_ui.rename(columns={
        "decision_periodo": "Decisión",
        "tipo_concepto": "Concepto",
        "movimientos": "Movimientos",
    })
    _mostrar_dataframe(df_ui, altura=260)


def _mostrar_listado_movimientos_fiscales(empresa_id, anio, mes, key_prefix="movs"):
    try:
        df = listar_movimientos_fiscales(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
            incluir_anulados=False,
        )
    except Exception as e:
        st.error(f"No se pudieron listar movimientos fiscales: {e}")
        return

    if df.empty:
        st.info("No hay movimientos fiscales adicionales cargados para este período.")
        return

    df = _preparar_movimientos_fiscales_con_decision(df)
    df_operativo, df_informativo = _separar_movimientos_operativos_e_informativos(df)

    if df_operativo.empty:
        st.info(
            "No hay movimientos fiscales que impacten IVA para este período. "
            "Si existen IIBB, Ley 25.413 u otros conceptos, quedan abajo como control informativo."
        )
    else:
        _mostrar_tablero_decisiones_movimientos(df_operativo)
        _mostrar_resumen_agregado_movimientos_fiscales(
            df_operativo,
            titulo="Resumen IVA por concepto y decisión",
        )

    with st.expander("Ver movimientos IVA línea por línea", expanded=False):
        if df_operativo.empty:
            st.info("No hay líneas operativas de IVA para mostrar.")
        else:
            col1, col2 = st.columns([2, 1])

            with col1:
                busqueda = st.text_input(
                    "Buscar movimientos IVA",
                    placeholder="Descripción, origen, tipo, contraparte, CUIT...",
                    key=f"{key_prefix}_buscar",
                )

            with col2:
                decisiones = ["TODAS"] + sorted(df_operativo["decision_periodo"].dropna().unique().tolist())
                decision_filtro = st.selectbox(
                    "Decisión",
                    decisiones,
                    key=f"{key_prefix}_decision_filtro",
                )

            df_filtrado = _aplicar_busqueda(df_operativo, busqueda)

            if decision_filtro != "TODAS" and "decision_periodo" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["decision_periodo"] == decision_filtro].copy()

            columnas = [
                "fecha",
                "decision_periodo",
                "origen",
                "tipo_concepto",
                "descripcion",
                "credito_fiscal_computable",
                "percepcion_iva",
                "retencion_iva",
                "iva_no_computable",
                "total",
            ]
            columnas = [col for col in columnas if col in df_filtrado.columns]

            st.caption(f"Movimientos IVA visibles: {len(df_filtrado)}")
            df_ui = _preparar_df_ui(df_filtrado[columnas])
            df_ui = df_ui.rename(columns={"decision_periodo": "Decisión"})
            _mostrar_dataframe(df_ui, altura=420)

    with st.expander("Ver conceptos informativos / control fiscal", expanded=False):
        if df_informativo.empty:
            st.info("No hay conceptos informativos fuera del IVA en este período.")
        else:
            st.caption(
                "Estos conceptos no integran la decisión mensual de IVA. "
                "Sirven para control contable/impositivo: IIBB, Ley 25.413 y otros tributos."
            )
            resumen_info = _resumen_movimientos_fiscales_por_concepto(df_informativo)
            if not resumen_info.empty:
                columnas_resumen = [
                    "tipo_concepto",
                    "decision_periodo",
                    "movimientos",
                    "percepcion_iibb_informativa",
                    "otros_tributos",
                    "total",
                ]
                columnas_resumen = [col for col in columnas_resumen if col in resumen_info.columns]
                df_resumen_ui = _preparar_df_ui(resumen_info[columnas_resumen])
                df_resumen_ui = df_resumen_ui.rename(columns={
                    "tipo_concepto": "Concepto",
                    "decision_periodo": "Decisión",
                })
                _mostrar_dataframe(df_resumen_ui, altura=220)

            with st.expander("Detalle informativo línea por línea", expanded=False):
                columnas_info = [
                    "fecha",
                    "decision_periodo",
                    "origen",
                    "tipo_concepto",
                    "descripcion",
                    "percepcion_iibb_informativa",
                    "otros_tributos",
                    "total",
                ]
                columnas_info = [col for col in columnas_info if col in df_informativo.columns]
                df_info_ui = _preparar_df_ui(df_informativo[columnas_info])
                df_info_ui = df_info_ui.rename(columns={"decision_periodo": "Decisión"})
                _mostrar_dataframe(df_info_ui, altura=320)

    with st.expander("Corrección puntual / auditoría", expanded=False):
        st.warning(
            "Usá esta sección solo para corregir un movimiento puntual. "
            "La decisión normal del banco se hace en Banco/Caja > Control fiscal bancario."
        )

        ids_disponibles = df["id"].tolist() if "id" in df.columns else []

        if not ids_disponibles:
            st.info("No hay identificadores de movimientos disponibles para operar.")
            return

        movimiento_id = st.selectbox(
            "Movimiento fiscal",
            ids_disponibles,
            format_func=lambda x: _label_movimiento(df, x),
            key=f"{key_prefix}_movimiento_id",
        )

        movimiento = df[df["id"] == movimiento_id].iloc[0].to_dict()
        estado_actual = str(movimiento.get("estado", "")).upper()
        decision_actual = movimiento.get("decision_periodo", "Sin decisión")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Estado técnico", estado_actual or "—")
        c2.metric("Decisión", decision_actual)
        c3.metric("Tipo", str(movimiento.get("tipo_concepto", "—")))
        c4.metric("Importe IVA", formato_moneda(_importe_relevante_para_iva(pd.DataFrame([movimiento]))))

        st.write(f"**Descripción:** {movimiento.get('descripcion', '')}")

        col_confirmar, col_anular = st.columns(2)

        with col_confirmar:
            if estado_actual == ESTADO_BORRADOR:
                st.info("Está pendiente. Podés confirmarlo si corresponde tomarlo según su configuración fiscal.")
                if _boton_accion(
                    "Confirmar movimiento pendiente",
                    key=f"{key_prefix}_confirmar",
                    tipo="primary",
                ):
                    try:
                        confirmar_movimiento_fiscal(
                            movimiento_id=movimiento_id,
                            usuario=_obtener_usuario_actual(),
                        )
                        st.success("Movimiento fiscal confirmado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo confirmar el movimiento: {e}")
            else:
                st.caption("Solo los movimientos pendientes se confirman desde esta sección.")

        with col_anular:
            if estado_actual != ESTADO_ANULADO:
                motivo = st.text_input(
                    "Motivo de anulación",
                    key=f"{key_prefix}_motivo_anulacion",
                    placeholder="Obligatorio para anular",
                )

                if _boton_accion(
                    "Anular por error",
                    key=f"{key_prefix}_anular",
                    tipo="secondary",
                ):
                    try:
                        anular_movimiento_fiscal(
                            movimiento_id=movimiento_id,
                            motivo=motivo,
                            usuario=_obtener_usuario_actual(),
                        )
                        st.success("Movimiento fiscal anulado correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo anular el movimiento: {e}")
            else:
                st.caption("El movimiento seleccionado ya está anulado.")

        with st.expander("Eventos del movimiento seleccionado", expanded=False):
            try:
                eventos = listar_eventos_movimiento(movimiento_id)
                _mostrar_dataframe(_preparar_df_ui(eventos), altura=260)
            except Exception as e:
                st.error(f"No se pudieron leer eventos: {e}")


def _label_movimiento(df, movimiento_id):
    try:
        row = df[df["id"] == movimiento_id].iloc[0]
        return (
            f"#{row.get('id')} · {row.get('fecha')} · {row.get('estado')} · "
            f"{row.get('origen')} · {row.get('tipo_concepto')} · {row.get('descripcion')}"
        )
    except Exception:
        return f"Movimiento {movimiento_id}"


def _mostrar_detalle_movimientos_fiscales(detalle_movimientos_fiscales, key_prefix="det_mov_fiscales"):
    st.markdown("#### Movimientos fiscales adicionales")

    if detalle_movimientos_fiscales is None or detalle_movimientos_fiscales.empty:
        st.info("No hay movimientos fiscales adicionales para el período seleccionado.")
        return

    df_base = _preparar_movimientos_fiscales_con_decision(detalle_movimientos_fiscales.copy())
    df_operativo, df_informativo = _separar_movimientos_operativos_e_informativos(df_base)

    if df_operativo.empty:
        st.info("No hay movimientos adicionales que impacten IVA para este período.")
    else:
        _mostrar_tablero_decisiones_movimientos(df_operativo)
        _mostrar_resumen_agregado_movimientos_fiscales(
            df_operativo,
            titulo="Resumen IVA por concepto y decisión",
        )

    with st.expander("Ver detalle IVA línea por línea", expanded=False):
        if df_operativo.empty:
            st.info("No hay detalle operativo de IVA.")
        else:
            col1, col2 = st.columns([2, 1])

            with col1:
                busqueda = st.text_input(
                    "Buscar en movimientos IVA",
                    placeholder="Descripción, origen, tipo, contraparte, CUIT...",
                    key=f"{key_prefix}_buscar",
                )

            with col2:
                mostrar_tecnicas = st.checkbox(
                    "Mostrar columnas técnicas",
                    value=False,
                    key=f"{key_prefix}_tecnicas",
                )

            df = _aplicar_busqueda(df_operativo, busqueda)

            columnas_base = [
                "fecha",
                "estado",
                "decision_periodo",
                "origen",
                "tipo_concepto",
                "descripcion",
                "contraparte",
                "cuit",
                "credito_fiscal_computable",
                "iva_no_computable",
                "percepcion_iva",
                "retencion_iva",
                "total",
            ]

            columnas_tecnicas = [
                "id",
                "empresa_id",
                "anio",
                "mes",
                "periodo",
                "neto_gravado",
                "iva_debito",
                "saldo_tecnico_anterior",
                "saldo_libre_disponibilidad",
                "pago_a_cuenta",
                "observacion",
                "usuario",
                "fecha_carga",
                "fecha_confirmacion",
            ]

            columnas = columnas_base + columnas_tecnicas if mostrar_tecnicas else columnas_base
            columnas = [col for col in columnas if col in df.columns]

            st.caption(f"Movimientos IVA visibles: {len(df)}")

            df_ui = _preparar_df_ui(df[columnas])
            df_ui = df_ui.rename(columns={"decision_periodo": "Decisión del período"})
            _mostrar_dataframe(df_ui, altura=420)

    with st.expander("Ver conceptos informativos / control fiscal", expanded=False):
        if df_informativo.empty:
            st.info("No hay conceptos informativos fuera del IVA en este período.")
        else:
            st.caption(
                "IIBB, Ley 25.413 y otros tributos no integran la decisión de IVA, "
                "pero quedan trazados para control y papel de trabajo."
            )
            columnas = [
                "fecha",
                "estado",
                "decision_periodo",
                "origen",
                "tipo_concepto",
                "descripcion",
                "percepcion_iibb_informativa",
                "otros_tributos",
                "total",
            ]
            columnas = [col for col in columnas if col in df_informativo.columns]
            df_ui = _preparar_df_ui(df_informativo[columnas])
            df_ui = df_ui.rename(columns={"decision_periodo": "Decisión del período"})
            _mostrar_dataframe(df_ui, altura=320)



# ======================================================
# PANTALLAS
# ======================================================

def _pantalla_posicion_iva(empresa_id, periodos):
    st.subheader("Posición mensual de IVA")

    st.info(
        "Esta etapa calcula la posición mensual desde Ventas, Compras y movimientos fiscales "
        "adicionales confirmados. Banco fiscal automático se incorporará luego desde Banco/Conciliación."
    )

    anio, mes = _selector_periodo(periodos, "iva_posicion")

    st.markdown(f"### {_periodo_largo(anio, mes)}")

    try:
        resultado = calcular_posicion_iva_periodo(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )
    except Exception as e:
        st.error(f"No se pudo calcular la posición IVA del período: {e}")
        return

    posicion = resultado["posicion"]
    detalle_ventas = resultado["detalle_ventas"]
    detalle_compras = resultado["detalle_compras"]
    detalle_movimientos_fiscales = resultado.get("detalle_movimientos_fiscales", pd.DataFrame())
    resumen_origenes = resultado["resumen_origenes"]
    resumen_movimientos_fiscales_origen = resultado.get(
        "resumen_movimientos_fiscales_origen",
        pd.DataFrame(),
    )
    alertas = resultado["alertas"]

    _mostrar_metricas_posicion(posicion)

    st.divider()

    _mostrar_composicion(posicion)

    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        _mostrar_resumen_origenes(resumen_origenes)

    with col2:
        st.markdown("#### Alertas de control")
        _mostrar_alertas(alertas)

    if resumen_movimientos_fiscales_origen is not None and not resumen_movimientos_fiscales_origen.empty:
        st.divider()
        st.markdown("#### Resumen de movimientos fiscales por origen/tipo")
        _mostrar_dataframe(_preparar_df_ui(resumen_movimientos_fiscales_origen), altura=260)

    st.divider()

    _mostrar_exportacion_excel(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )

    st.divider()

    with st.expander("Ver detalle de ventas del período", expanded=False):
        _mostrar_detalle_ventas(detalle_ventas, key_prefix="posicion_ventas")

    with st.expander("Ver detalle de compras del período", expanded=False):
        _mostrar_detalle_compras(detalle_compras, key_prefix="posicion_compras")

    with st.expander("Ver movimientos fiscales adicionales del período", expanded=False):
        _mostrar_detalle_movimientos_fiscales(
            detalle_movimientos_fiscales,
            key_prefix="posicion_mov_fiscales",
        )


def _pantalla_libro_iva_ventas(empresa_id, periodos):
    st.subheader("Libro IVA Ventas")

    st.caption(
        "Vista de control de comprobantes de ventas que alimentan el IVA débito fiscal. "
        "La normalización de notas de crédito se aplica solo para cálculo y visualización fiscal."
    )

    anio, mes = _selector_periodo(periodos, "iva_libro_ventas")

    try:
        resultado = calcular_posicion_iva_periodo(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )
    except Exception as e:
        st.error(f"No se pudo obtener el Libro IVA Ventas: {e}")
        return

    posicion = resultado["posicion"]
    detalle_ventas = resultado["detalle_ventas"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Neto ventas", formato_moneda(posicion.get("neto_ventas", 0)))

    with col2:
        st.metric(
            "IVA débito ventas",
            formato_moneda(posicion.get("iva_debito_fiscal_ventas", 0)),
        )

    with col3:
        st.metric("Total ventas", formato_moneda(posicion.get("total_ventas", 0)))

    _mostrar_detalle_ventas(detalle_ventas, key_prefix="libro_ventas")


def _pantalla_libro_iva_compras(empresa_id, periodos):
    st.subheader("Libro IVA Compras")

    st.caption(
        "Vista de control de comprobantes de compras que alimentan el crédito fiscal, "
        "IVA no computable y percepciones. Las percepciones IIBB se muestran solo como informativas para IVA."
    )

    anio, mes = _selector_periodo(periodos, "iva_libro_compras")

    try:
        resultado = calcular_posicion_iva_periodo(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )
    except Exception as e:
        st.error(f"No se pudo obtener el Libro IVA Compras: {e}")
        return

    posicion = resultado["posicion"]
    detalle_compras = resultado["detalle_compras"]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("IVA total compras", formato_moneda(posicion.get("iva_total_compras", 0)))

    with col2:
        st.metric(
            "Crédito fiscal compras",
            formato_moneda(posicion.get("credito_fiscal_computable_compras", 0)),
        )

    with col3:
        st.metric(
            "IVA no computable compras",
            formato_moneda(posicion.get("iva_no_computable_compras", 0)),
        )

    with col4:
        st.metric(
            "Percepciones IVA compras",
            formato_moneda(posicion.get("percepciones_iva_compras", 0)),
        )

    _mostrar_detalle_compras(detalle_compras, key_prefix="libro_compras")



def _pantalla_movimientos_fiscales(empresa_id, periodos):
    st.subheader("Movimientos fiscales adicionales")

    st.info(
        "Vista simple: acá se ve qué importes adicionales entran al IVA del período y qué queda pendiente. "
        "La decisión principal de los importes bancarios se toma desde Banco/Caja > Control fiscal bancario."
    )

    try:
        periodos_movimientos = obtener_periodos_disponibles_movimientos_fiscales_iva(
            empresa_id=empresa_id,
        )
    except Exception:
        periodos_movimientos = pd.DataFrame()

    if periodos_movimientos.empty:
        st.info(
            "No hay períodos con movimientos fiscales adicionales de IVA. "
            "Los meses que solo tienen Ventas o Compras se revisan desde Posición IVA, Libro Ventas o Libro Compras."
        )
        anio, mes = _selector_periodo(periodos_movimientos, "iva_movimientos")
    else:
        anio, mes = _selector_periodo(periodos_movimientos, "iva_movimientos")

    st.markdown(f"### {_periodo_largo(anio, mes)}")

    tab_resumen, tab_alta = st.tabs([
        "Resumen del período",
        "Cargar movimiento manual",
    ])

    with tab_resumen:
        _mostrar_listado_movimientos_fiscales(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
            key_prefix="mov_fiscales_listado",
        )

    with tab_alta:
        _mostrar_formulario_movimiento_fiscal(
            empresa_id=empresa_id,
            anio=anio,
            mes=mes,
        )

def _pantalla_papel_trabajo(empresa_id, periodos):
    st.subheader("Papel de trabajo / Exportación")

    st.warning(
        "Esta etapa genera papel de trabajo Excel. "
        "Todavía no genera TXT Portal IVA ni presentación automática."
    )

    st.markdown(
        """
        El Excel incluye:

        - Posición IVA mensual.
        - Resumen por origen fiscal.
        - Libro IVA Ventas.
        - Libro IVA Compras.
        - Movimientos fiscales adicionales.
        - Alertas de control.

        En próximas etapas se podrá incorporar:

        - Origen fiscal BANCO automático desde extractos/conciliación.
        - Liquidaciones de tarjetas/acreditadoras.
        - Exportación Portal IVA / Libro IVA Digital.
        """
    )

    anio, mes = _selector_periodo(periodos, "iva_exportacion")

    _mostrar_exportacion_excel(
        empresa_id=empresa_id,
        anio=anio,
        mes=mes,
    )


def _pantalla_resumen_periodos(empresa_id):
    st.subheader("Resumen mensual IVA")

    st.caption(
        "Resumen de todos los períodos detectados en Ventas, Compras y movimientos fiscales confirmados. "
        "Sirve para revisar rápidamente meses con saldo a ingresar, saldo a favor o datos incompletos."
    )

    _mostrar_resumen_periodos(empresa_id)


# ======================================================
# ENTRADA PRINCIPAL
# ======================================================

def mostrar_iva():
    empresa_id = _obtener_empresa_id_actual()
    nombre_empresa = _obtener_nombre_empresa_actual()

    st.subheader("IVA PRO — Posición mensual")
    st.caption(f"Empresa: {nombre_empresa} · ID interno: {empresa_id}")

    try:
        periodos = obtener_periodos_disponibles_iva(empresa_id=empresa_id)
    except Exception as e:
        st.error(f"No se pudieron obtener los períodos disponibles de IVA: {e}")
        periodos = pd.DataFrame()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Posición IVA",
        "Libro IVA Ventas",
        "Libro IVA Compras",
        "Movimientos fiscales",
        "Resumen mensual",
        "Papel de trabajo",
    ])

    with tab1:
        _pantalla_posicion_iva(
            empresa_id=empresa_id,
            periodos=periodos,
        )

    with tab2:
        _pantalla_libro_iva_ventas(
            empresa_id=empresa_id,
            periodos=periodos,
        )

    with tab3:
        _pantalla_libro_iva_compras(
            empresa_id=empresa_id,
            periodos=periodos,
        )

    with tab4:
        _pantalla_movimientos_fiscales(
            empresa_id=empresa_id,
            periodos=periodos,
        )

    with tab5:
        _pantalla_resumen_periodos(
            empresa_id=empresa_id,
        )

    with tab6:
        _pantalla_papel_trabajo(
            empresa_id=empresa_id,
            periodos=periodos,
        )


# Alias de compatibilidad por si main.py llama con otro nombre
def mostrar_modulo_iva():
    mostrar_iva()