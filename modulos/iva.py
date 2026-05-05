import pandas as pd
import streamlit as st

from services.iva_service import (
    calcular_posicion_iva_periodo,
    etiqueta_resultado_saldo,
    formato_moneda,
    generar_papel_trabajo_excel_iva,
    nombre_archivo_papel_trabajo_iva,
    obtener_periodos_disponibles_iva,
    obtener_resumen_posiciones_iva,
)


# ======================================================
# MÓDULO IVA PRO
# Etapa 1: Posición mensual
# ======================================================
#
# Criterio:
# - No modifica Ventas.
# - No modifica Compras.
# - No modifica Banco/Caja.
# - No modifica Cobranzas/Pagos.
# - No modifica Conciliación.
# - Lee información fiscal ya persistida y arma papel de trabajo mensual.
#
# Nota de diseño:
# En esta etapa, la posición IVA se calcula con origen VENTAS + COMPRAS.
# El origen BANCO queda previsto para una próxima etapa, para gastos bancarios,
# comisiones, percepciones bancarias y otros conceptos fiscales sin duplicar
# movimientos financieros como compras manuales.


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
        "iva_debito_fiscal",
        "total_ventas",
        "neto_compras",
        "iva_total_compras",
        "credito_fiscal_computable",
        "iva_no_computable",
        "percepciones_iva",
        "percepciones_iibb_informativas",
        "total_compras",
        "saldo_tecnico_iva",
        "percepciones_iva_sufridas",
        "saldo_preliminar_periodo",
        "neto",
        "iva_debito",
        "iva_credito",
        "percepcion_iva",
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
        "estado": "Estado",
        "id": "ID",
        "fecha": "Fecha",
        "codigo": "Código",
        "tipo": "Tipo",
        "punto_venta": "Punto venta",
        "numero": "Número",
        "cliente": "Cliente",
        "proveedor": "Proveedor",
        "cuit": "CUIT",
        "categoria_compra": "Categoría compra",
        "archivo": "Archivo",

        "neto_ventas": "Neto ventas",
        "iva_debito_fiscal": "IVA débito fiscal",
        "total_ventas": "Total ventas",

        "neto_compras": "Neto compras",
        "iva_total_compras": "IVA total compras",
        "credito_fiscal_computable": "Crédito fiscal computable",
        "iva_no_computable": "IVA no computable",
        "percepciones_iva": "Percepciones IVA",
        "percepciones_iibb_informativas": "Percepciones IIBB informativas",
        "total_compras": "Total compras",

        "saldo_tecnico_iva": "Saldo técnico IVA",
        "percepciones_iva_sufridas": "Percepciones IVA sufridas",
        "saldo_preliminar_periodo": "Saldo preliminar período",

        "cantidad_ventas": "Cant. ventas",
        "cantidad_compras": "Cant. compras",
        "cantidad_total": "Cant. total",

        "neto": "Neto",
        "iva_debito": "IVA débito",
        "iva_credito": "IVA crédito",
        "percepcion_iva": "Percepción IVA",
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
            "No se detectaron períodos con movimientos en Ventas o Compras. "
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
        total = _int(row.get("cantidad_total"))

        return (
            f"{anio}-{mes:02d} · {_periodo_largo(anio, mes)} "
            f"· Ventas: {ventas} · Compras: {compras} · Total: {total}"
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
            help="IVA generado por ventas del período.",
        )

    with col2:
        st.metric(
            "Crédito fiscal computable",
            formato_moneda(posicion.get("credito_fiscal_computable", 0)),
            help="IVA computable de compras según clasificación fiscal.",
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
            help="Percepciones de IVA informadas en compras. Se descuentan del saldo preliminar.",
        )

    with col5:
        st.metric(
            "Saldo preliminar período",
            formato_moneda(posicion.get("saldo_preliminar_periodo", 0)),
            help="Saldo técnico menos percepciones IVA sufridas.",
        )

    with col6:
        st.metric(
            "Percepciones IIBB informativas",
            formato_moneda(posicion.get("percepciones_iibb_informativas", 0)),
            help="Se muestran para control, pero no reducen la posición de IVA.",
        )

    _mostrar_estado_saldo(posicion)


def _mostrar_composicion(posicion):
    st.markdown("#### Composición de la posición")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Ventas")
        st.write(f"**Neto ventas:** {formato_moneda(posicion.get('neto_ventas', 0))}")
        st.write(f"**IVA débito fiscal:** {formato_moneda(posicion.get('iva_debito_fiscal', 0))}")
        st.write(f"**Total ventas:** {formato_moneda(posicion.get('total_ventas', 0))}")
        st.write(f"**Cantidad comprobantes:** {_int(posicion.get('cantidad_ventas', 0))}")

    with col2:
        st.markdown("##### Compras")
        st.write(f"**Neto compras:** {formato_moneda(posicion.get('neto_compras', 0))}")
        st.write(f"**IVA total compras:** {formato_moneda(posicion.get('iva_total_compras', 0))}")
        st.write(
            f"**Crédito fiscal computable:** "
            f"{formato_moneda(posicion.get('credito_fiscal_computable', 0))}"
        )
        st.write(f"**IVA no computable:** {formato_moneda(posicion.get('iva_no_computable', 0))}")
        st.write(f"**Percepciones IVA:** {formato_moneda(posicion.get('percepciones_iva', 0))}")
        st.write(
            f"**Percepciones IIBB informativas:** "
            f"{formato_moneda(posicion.get('percepciones_iibb_informativas', 0))}"
        )
        st.write(f"**Total compras:** {formato_moneda(posicion.get('total_compras', 0))}")
        st.write(f"**Cantidad comprobantes:** {_int(posicion.get('cantidad_compras', 0))}")


def _mostrar_resumen_origenes(resumen_origenes):
    st.markdown("#### Resumen por origen fiscal")

    st.caption(
        "En esta etapa se calculan los orígenes VENTAS y COMPRAS. "
        "BANCO y AJUSTE_MANUAL quedan visibles como preparación técnica para próximas etapas."
    )

    df_ui = _preparar_df_ui(resumen_origenes)
    _mostrar_dataframe(df_ui, altura=260)


def _mostrar_exportacion_excel(empresa_id, anio, mes):
    st.markdown("#### Papel de trabajo Excel")

    st.caption(
        "El archivo exporta Posición IVA, resumen por origen, Libro IVA Ventas, "
        "Libro IVA Compras y alertas de control. No es todavía TXT Portal IVA."
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
        "saldo_tecnico_iva",
        "saldo_preliminar_periodo",
        "cantidad_ventas",
        "cantidad_compras",
    ]

    columnas = [col for col in columnas if col in resumen.columns]

    df_ui = _preparar_df_ui(resumen[columnas])
    _mostrar_dataframe(df_ui, altura=360)


# ======================================================
# PANTALLAS
# ======================================================

def _pantalla_posicion_iva(empresa_id, periodos):
    st.subheader("Posición mensual de IVA")

    st.info(
        "Esta etapa calcula la posición mensual desde Ventas y Compras registradas. "
        "Los gastos bancarios con IVA, comisiones y percepciones bancarias se incorporarán "
        "luego como origen fiscal BANCO, sin duplicar el extracto como compra manual."
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
    resumen_origenes = resultado["resumen_origenes"]
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
        st.metric("IVA débito fiscal", formato_moneda(posicion.get("iva_debito_fiscal", 0)))

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
            "Crédito fiscal computable",
            formato_moneda(posicion.get("credito_fiscal_computable", 0)),
        )

    with col3:
        st.metric("IVA no computable", formato_moneda(posicion.get("iva_no_computable", 0)))

    with col4:
        st.metric("Percepciones IVA", formato_moneda(posicion.get("percepciones_iva", 0)))

    _mostrar_detalle_compras(detalle_compras, key_prefix="libro_compras")


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
        - Alertas de control.

        En próximas etapas se podrá incorporar:

        - Origen fiscal BANCO para comisiones, gastos bancarios y percepciones.
        - Ajustes manuales controlados.
        - Saldos a favor anteriores.
        - Retenciones sufridas.
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
        "Resumen de todos los períodos detectados en Ventas y Compras. "
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Posición IVA",
        "Libro IVA Ventas",
        "Libro IVA Compras",
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
        _pantalla_resumen_periodos(
            empresa_id=empresa_id,
        )

    with tab5:
        _pantalla_papel_trabajo(
            empresa_id=empresa_id,
            periodos=periodos,
        )


# Alias de compatibilidad por si main.py llama con otro nombre
def mostrar_modulo_iva():
    mostrar_iva()