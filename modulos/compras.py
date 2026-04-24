import streamlit as st
import pandas as pd

from database import ejecutar_query, archivo_ya_cargado
from services.compras_service import procesar_csv_compras

from core.fechas import ordenar_dataframe_por_fecha, fecha_para_ordenar, formatear_fecha
from core.exportadores import exportar_excel
from core.ui import preparar_vista
from core.numeros import moneda


def normalizar_columna(nombre):
    return str(nombre).lower().strip()


def buscar_columna(columnas, palabras_clave, indice_defecto=0):
    columnas_norm = [normalizar_columna(c) for c in columnas]

    for palabra in palabras_clave:
        palabra = palabra.lower()

        for i, col in enumerate(columnas_norm):
            if palabra in col:
                return columnas[i]

    if len(columnas) > indice_defecto:
        return columnas[indice_defecto]

    return columnas[0]


def indice_columna(opciones, valor):
    try:
        return opciones.index(valor)
    except Exception:
        return 0


def mostrar_ventas_mensaje_columnas():
    st.warning(
        "Como los CSV de compras pueden variar según el origen, "
        "este módulo permite mapear manualmente las columnas antes de procesar."
    )


def mostrar_compras():
    st.title("📥 Compras PRO V1")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Cargar CSV",
        "Libro IVA Compras",
        "Resumen / Estadísticas",
        "Cuenta corriente proveedores"
    ])

    with tab1:
        cargar_csv_compras()

    with tab2:
        mostrar_libro_iva_compras()

    with tab3:
        mostrar_resumen_compras()

    with tab4:
        mostrar_cuenta_corriente_proveedores()


def cargar_csv_compras():
    st.info(
        "Carga CSV de compras, genera asientos contables, guarda Libro IVA Compras "
        "y actualiza cuenta corriente de proveedores."
    )

    archivo = st.file_uploader("Subir CSV Compras", type=["csv"])

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

        st.divider()

        st.subheader("Mapeo de columnas")
        mostrar_ventas_mensaje_columnas()

        columnas = df.columns.tolist()
        columnas_opcionales = ["No usar"] + columnas

        col1, col2, col3 = st.columns(3)

        with col1:
            fecha_col = st.selectbox(
                "Fecha",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["fecha"], 0)
                )
            )

            codigo_col = st.selectbox(
                "Código comprobante",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["tipo", "código", "codigo", "comprobante"], 1)
                )
            )

            punto_venta_col = st.selectbox(
                "Punto de venta",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["punto", "pto"], 2)
                )
            )

        with col2:
            numero_desde_col = st.selectbox(
                "Número desde / comprobante",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["número desde", "numero desde", "nro desde", "comprobante"], 3)
                )
            )

            numero_hasta_col = st.selectbox(
                "Número hasta",
                columnas_opcionales,
                index=indice_columna(
                    columnas_opcionales,
                    buscar_columna(columnas_opcionales, ["número hasta", "numero hasta", "nro hasta"], 0)
                )
            )

            cuit_col = st.selectbox(
                "CUIT proveedor",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["cuit", "documento", "doc"], 7 if len(columnas) > 7 else 0)
                )
            )

        with col3:
            proveedor_col = st.selectbox(
                "Proveedor / Razón social",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["denominación", "denominacion", "razón", "razon", "proveedor", "nombre"], 8 if len(columnas) > 8 else 0)
                )
            )

            neto_col = st.selectbox(
                "Neto gravado",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["neto gravado", "neto"], 22 if len(columnas) > 22 else 0)
                )
            )

            iva_col = st.selectbox(
                "IVA",
                columnas,
                index=indice_columna(
                    columnas,
                    buscar_columna(columnas, ["iva"], 26 if len(columnas) > 26 else 0)
                )
            )

        total_col = st.selectbox(
            "Total comprobante",
            columnas,
            index=indice_columna(
                columnas,
                buscar_columna(columnas, ["importe total", "total"], 27 if len(columnas) > 27 else 0)
            )
        )

        columnas_mapeadas = {
            "fecha": fecha_col,
            "codigo": codigo_col,
            "punto_venta": punto_venta_col,
            "numero_desde": numero_desde_col,
            "numero_hasta": numero_hasta_col,
            "cuit": cuit_col,
            "proveedor": proveedor_col,
            "neto": neto_col,
            "iva": iva_col,
            "total": total_col
        }

        st.divider()

        if not st.button("Procesar Compras"):
            return

        resultado = procesar_csv_compras(archivo.name, df, columnas_mapeadas)

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


def mostrar_libro_iva_compras():
    st.subheader("📘 Libro IVA Compras")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            numero,
            proveedor,
            cuit,
            neto,
            iva,
            total,
            archivo
        FROM compras_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay compras cargadas.")
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
    proveedores = ["Todos"] + sorted(df["proveedor"].dropna().unique().tolist())

    with col1:
        anio = st.selectbox("Año", anios)

    with col2:
        mes = st.selectbox("Mes", meses)

    with col3:
        proveedor = st.selectbox("Proveedor", proveedores)

    if anio != "Todos":
        df = df[df["anio"] == anio]

    if mes != "Todos":
        df = df[df["mes"] == mes]

    if proveedor != "Todos":
        df = df[df["proveedor"] == proveedor]

    df_vista = df.drop(columns=["fecha_orden"])
    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    c1, c2, c3 = st.columns(3)

    c1.metric("Neto", moneda(df["neto"].sum()))
    c2.metric("IVA Crédito Fiscal", moneda(df["iva"].sum()))
    c3.metric("Total", moneda(df["total"].sum()))

    excel = exportar_excel({
        "Libro IVA Compras": df_vista
    })

    st.download_button(
        "Descargar Libro IVA Compras Excel",
        data=excel,
        file_name="libro_iva_compras.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_resumen_compras():
    st.subheader("📊 Resumen / Estadísticas de Compras")

    df = ejecutar_query("""
        SELECT 
            fecha,
            anio,
            mes,
            tipo,
            proveedor,
            cuit,
            neto,
            iva,
            total,
            archivo
        FROM compras_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay compras cargadas.")
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
        "proveedor": "count"
    })

    resumen_tipo = resumen_tipo.rename(columns={
        "proveedor": "cantidad"
    })

    ranking_proveedores = df.groupby(["proveedor", "cuit"], as_index=False).agg({
        "total": "sum",
        "tipo": "count"
    })

    ranking_proveedores = ranking_proveedores.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    ranking_proveedores = ranking_proveedores.sort_values(by="total", ascending=False)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Neto", moneda(df["neto"].sum()))
    col2.metric("IVA Crédito", moneda(df["iva"].sum()))
    col3.metric("Total Compras", moneda(df["total"].sum()))
    col4.metric("Comprobantes", len(df))

    st.divider()

    st.subheader("Resumen mensual")
    st.dataframe(preparar_vista(resumen_mensual), use_container_width=True)

    st.subheader("Resumen por tipo de comprobante")
    st.dataframe(preparar_vista(resumen_tipo), use_container_width=True)

    st.subheader("Ranking de proveedores")
    st.dataframe(preparar_vista(ranking_proveedores), use_container_width=True)

    excel = exportar_excel({
        "Resumen Mensual": resumen_mensual,
        "Resumen Tipo": resumen_tipo,
        "Ranking Proveedores": ranking_proveedores
    })

    st.download_button(
        "Descargar Estadísticas Compras Excel",
        data=excel,
        file_name="estadisticas_compras.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def mostrar_cuenta_corriente_proveedores():
    st.subheader("💰 Cuenta corriente de proveedores")

    df = ejecutar_query("""
        SELECT 
            id,
            fecha,
            proveedor,
            cuit,
            tipo,
            numero,
            debe,
            haber,
            origen,
            archivo
        FROM cuenta_corriente_proveedores
        ORDER BY proveedor, fecha, id
    """, fetch=True)

    if df.empty:
        st.info("No hay movimientos de cuenta corriente de proveedores.")
        return

    df["fecha_orden"] = df["fecha"].apply(fecha_para_ordenar)
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    resumen = df.groupby(["proveedor", "cuit"], as_index=False).agg({
        "debe": "sum",
        "haber": "sum"
    })

    resumen["saldo"] = resumen["haber"] - resumen["debe"]
    resumen = resumen.sort_values(by="saldo", ascending=False)

    st.subheader("Resumen de deuda con proveedores")
    st.dataframe(preparar_vista(resumen), use_container_width=True)

    proveedor = st.selectbox(
        "Ver detalle de proveedor",
        ["Todos"] + sorted(df["proveedor"].dropna().unique().tolist())
    )

    if proveedor != "Todos":
        df = df[df["proveedor"] == proveedor]

    df = df.copy()
    df = df.sort_values(by=["proveedor", "fecha_orden", "id"])

    df["saldo_acumulado"] = (
        df.groupby("proveedor")["haber"].cumsum()
        - df.groupby("proveedor")["debe"].cumsum()
    )

    df_vista = df.drop(columns=["fecha_orden"])

    st.subheader("Detalle de movimientos")
    st.dataframe(preparar_vista(df_vista), use_container_width=True)

    excel = exportar_excel({
        "Resumen Cta Cte": resumen,
        "Detalle Cta Cte": df_vista
    })

    st.download_button(
        "Descargar Cuenta Corriente Proveedores Excel",
        data=excel,
        file_name="cuenta_corriente_proveedores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )