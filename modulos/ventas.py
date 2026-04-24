import streamlit as st
import pandas as pd

from database import ejecutar_query, archivo_ya_cargado
from services.ventas_service import procesar_csv_ventas

from core.fechas import ordenar_dataframe_por_fecha, fecha_para_ordenar, formatear_fecha
from core.exportadores import exportar_excel
from core.ui import preparar_vista
from core.numeros import moneda


def mostrar_ventas():
    st.title("📤 Ventas PRO V5")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Cargar CSV",
        "Libro IVA Ventas",
        "Resumen / Estadísticas",
        "Cuenta corriente clientes"
    ])

    with tab1:
        cargar_csv_ventas()

    with tab2:
        mostrar_libro_iva_ventas()

    with tab3:
        mostrar_resumen_ventas()

    with tab4:
        mostrar_cuenta_corriente_clientes()


def cargar_csv_ventas():
    st.info(
        "Carga CSV ARCA/AFIP, genera asientos contables, guarda Libro IVA Ventas "
        "y actualiza cuenta corriente de clientes."
    )

    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])

    if not archivo:
        return

    if archivo_ya_cargado(archivo.name):
        st.error("Ese archivo ya fue cargado anteriormente.")
        return

    try:
        df = pd.read_csv(
            archivo,
            sep=None,
            engine="python",
            encoding="latin-1",
            dtype=str
        )

        df = ordenar_dataframe_por_fecha(df, columna_indice=0)

        st.subheader("Vista previa")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)

        st.caption(f"Registros detectados: {len(df)}")

        if not st.button("Procesar Ventas"):
            return

        resultado = procesar_csv_ventas(archivo.name, df)

        st.success("Proceso finalizado")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Procesados", resultado["procesados"])
            st.metric("Facturas", resultado["facturas"])

        with col2:
            st.metric("Notas de Crédito", resultado["notas_credito"])
            st.metric("Notas de Débito", resultado["notas_debito"])

        with col3:
            st.metric("Errores", resultado["errores"])
            st.metric("Duplicados", resultado["duplicados"])

        st.divider()

        st.subheader("Detalle de auditoría")
        st.write(f"Errores matemáticos: {resultado['errores_matematicos']}")
        st.write(f"Códigos inexistentes: {resultado['errores_codigo']}")
        st.write(f"Duplicados detectados: {resultado['duplicados']}")
        st.write(f"Ajustes técnicos de centavos sobre neto: {resultado['ajustes_centavos']}")

        if resultado["errores"] > 0:
            st.warning("Se detectaron errores. Revisar Estado de Cargas / Auditoría.")

    except Exception as e:
        st.error(f"No se pudo leer el archivo: {str(e)}")


def mostrar_libro_iva_ventas():
    st.subheader("📘 Libro IVA Ventas")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            numero,
            cliente,
            cuit,
            neto,
            iva,
            total,
            archivo
        FROM ventas_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay ventas cargadas.")
        return

    df["fecha_orden"] = df["fecha"].apply(fecha_para_ordenar)
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    df = df.sort_values(
        by=["anio", "mes", "fecha_orden", "numero"],
        ascending=True
    )

    col1, col2, col3 = st.columns(3)

    anios = ["Todos"] + sorted(df["anio"].dropna().unique().tolist())
    meses = ["Todos"] + sorted(df["mes"].dropna().unique().tolist())
    clientes = ["Todos"] + sorted(df["cliente"].dropna().unique().tolist())

    with col1:
        anio = st.selectbox("Año", anios)

    with col2:
        mes = st.selectbox("Mes", meses)

    with col3:
        cliente = st.selectbox("Cliente", clientes)

    if anio != "Todos":
        df = df[df["anio"] == anio]

    if mes != "Todos":
        df = df[df["mes"] == mes]

    if cliente != "Todos":
        df = df[df["cliente"] == cliente]

    df_vista = df.drop(columns=["fecha_orden"])
    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    c1, c2, c3 = st.columns(3)

    c1.metric("Neto", moneda(df["neto"].sum()))
    c2.metric("IVA Débito Fiscal", moneda(df["iva"].sum()))
    c3.metric("Total", moneda(df["total"].sum()))

    excel = exportar_excel({
        "Libro IVA Ventas": df_vista
    })

    st.download_button(
        "Descargar Libro IVA Ventas Excel",
        data=excel,
        file_name="libro_iva_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_resumen_ventas():
    st.subheader("📊 Resumen / Estadísticas de Ventas")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            cliente,
            cuit,
            neto,
            iva,
            total,
            archivo
        FROM ventas_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay ventas cargadas.")
        return

    df["fecha"] = df["fecha"].apply(formatear_fecha)

    resumen_mensual = df.groupby(["anio", "mes"], as_index=False).agg({
        "neto": "sum",
        "iva": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_mensual = resumen_mensual.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    resumen_tipo = df.groupby(["tipo"], as_index=False).agg({
        "neto": "sum",
        "iva": "sum",
        "total": "sum",
        "cliente": "count"
    })

    resumen_tipo = resumen_tipo.rename(columns={
        "cliente": "cantidad"
    })

    ranking_clientes = df.groupby(["cliente", "cuit"], as_index=False).agg({
        "total": "sum",
        "tipo": "count"
    })

    ranking_clientes = ranking_clientes.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    ranking_clientes = ranking_clientes.sort_values(by="total", ascending=False)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Neto", moneda(df["neto"].sum()))
    col2.metric("IVA Débito", moneda(df["iva"].sum()))
    col3.metric("Total Facturado", moneda(df["total"].sum()))
    col4.metric("Comprobantes", len(df))

    st.divider()

    st.subheader("Resumen mensual")
    st.dataframe(preparar_vista(resumen_mensual), use_container_width=True)

    st.subheader("Resumen por tipo de comprobante")
    st.dataframe(preparar_vista(resumen_tipo), use_container_width=True)

    st.subheader("Ranking de clientes")
    st.dataframe(preparar_vista(ranking_clientes), use_container_width=True)

    excel = exportar_excel({
        "Resumen Mensual": resumen_mensual,
        "Resumen Tipo": resumen_tipo,
        "Ranking Clientes": ranking_clientes
    })

    st.download_button(
        "Descargar Estadísticas Excel",
        data=excel,
        file_name="estadisticas_ventas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_cuenta_corriente_clientes():
    st.subheader("💰 Cuenta corriente de clientes")

    df = ejecutar_query("""
        SELECT 
            id,
            fecha,
            cliente,
            cuit,
            tipo,
            numero,
            debe,
            haber,
            origen,
            archivo
        FROM cuenta_corriente_clientes
        ORDER BY cliente, fecha, id
    """, fetch=True)

    if df.empty:
        st.info("No hay movimientos de cuenta corriente.")
        return

    df["fecha_orden"] = df["fecha"].apply(fecha_para_ordenar)
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    resumen = df.groupby(["cliente", "cuit"], as_index=False).agg({
        "debe": "sum",
        "haber": "sum"
    })

    resumen["saldo"] = resumen["debe"] - resumen["haber"]
    resumen = resumen.sort_values(by="saldo", ascending=False)

    st.subheader("Resumen de deuda por cliente")
    st.dataframe(preparar_vista(resumen), use_container_width=True)

    cliente = st.selectbox(
        "Ver detalle de cliente",
        ["Todos"] + sorted(df["cliente"].dropna().unique().tolist())
    )

    if cliente != "Todos":
        df = df[df["cliente"] == cliente]

    df = df.copy()
    df = df.sort_values(by=["cliente", "fecha_orden", "id"])

    df["saldo_acumulado"] = (
        df.groupby("cliente")["debe"].cumsum()
        - df.groupby("cliente")["haber"].cumsum()
    )

    df_vista = df.drop(columns=["fecha_orden"])

    st.subheader("Detalle de movimientos")
    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    excel = exportar_excel({
        "Resumen Cta Cte": resumen,
        "Detalle Cta Cte": df_vista
    })

    st.download_button(
        "Descargar Cuenta Corriente Excel",
        data=excel,
        file_name="cuenta_corriente_clientes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )