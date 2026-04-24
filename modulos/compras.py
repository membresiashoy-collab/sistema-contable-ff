import streamlit as st
import pandas as pd
from datetime import date

from database import ejecutar_query, archivo_ya_cargado
from services.compras_service import (
    procesar_csv_compras_arca,
    procesar_compra_manual,
    es_csv_arca_compras,
    asegurar_columnas_compras_v2
)

from core.fechas import ordenar_dataframe_por_fecha, fecha_para_ordenar, formatear_fecha
from core.exportadores import exportar_excel
from core.ui import preparar_vista
from core.numeros import moneda


# ======================================================
# CONSULTAS AUXILIARES
# ======================================================

def obtener_categorias_activas():
    return ejecutar_query("""
        SELECT 
            categoria,
            cuenta_codigo,
            cuenta_nombre,
            cuenta_proveedor_codigo,
            cuenta_proveedor_nombre,
            tipo_categoria
        FROM categorias_compra
        WHERE activo = 1
        ORDER BY categoria
    """, fetch=True)


def obtener_tipos_comprobantes():
    return ejecutar_query("""
        SELECT codigo, descripcion, signo
        FROM tipos_comprobantes
        ORDER BY codigo
    """, fetch=True)


def mostrar_resumen_resultado(resultado):
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


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_compras():
    asegurar_columnas_compras_v2()

    st.title("📥 Compras PRO V2")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Cargar CSV ARCA",
        "Carga Manual",
        "Libro IVA Compras",
        "Resumen / Estadísticas",
        "Cuenta corriente proveedores"
    ])

    with tab1:
        cargar_csv_compras_arca()

    with tab2:
        cargar_compra_manual()

    with tab3:
        mostrar_libro_iva_compras()

    with tab4:
        mostrar_resumen_compras()

    with tab5:
        mostrar_cuenta_corriente_proveedores()


# ======================================================
# TAB 1 - CSV ARCA
# ======================================================

def cargar_csv_compras_arca():
    st.info(
        "Este módulo procesa CSV ARCA/AFIP Compras, usando categoría contable, "
        "crédito fiscal computable, percepciones, impuestos internos y otros tributos."
    )

    df_categorias = obtener_categorias_activas()

    if df_categorias.empty:
        st.error(
            "Primero cargá las Categorías de Compra desde Configuración. "
            "Sin categoría no se puede determinar la cuenta contable principal."
        )
        return

    archivo = st.file_uploader("Subir CSV Compras ARCA/AFIP", type=["csv"])

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

        try:
            df = ordenar_dataframe_por_fecha(df, columna_indice=0)
        except Exception:
            pass

        st.subheader("Vista previa")
        st.dataframe(preparar_vista(df.head(20)), use_container_width=True)
        st.caption(f"Registros detectados: {len(df)}")

        if es_csv_arca_compras(df):
            st.success("Formato detectado: CSV ARCA/AFIP Compras.")
        else:
            st.error(
                "El archivo no parece tener el formato ARCA/AFIP Compras esperado. "
                "Revisá que tenga columnas como Fecha de Emisión, Tipo de Comprobante, "
                "Punto de Venta, Número de Comprobante, Importe Total."
            )
            return

        st.divider()

        st.subheader("Clasificación contable de la carga")

        categoria = st.selectbox(
            "Seleccionar categoría contable para estas compras",
            df_categorias["categoria"].tolist()
        )

        fila_categoria = df_categorias[df_categorias["categoria"] == categoria].iloc[0]

        col1, col2 = st.columns(2)

        with col1:
            st.write("Cuenta principal:")
            st.write(f"**{fila_categoria['cuenta_codigo']} - {fila_categoria['cuenta_nombre']}**")

        with col2:
            st.write("Cuenta proveedor / acreedor:")
            st.write(f"**{fila_categoria['cuenta_proveedor_codigo']} - {fila_categoria['cuenta_proveedor_nombre']}**")

        st.warning(
            "La categoría seleccionada se aplicará a todos los comprobantes del archivo. "
            "Si el archivo mezcla compras de bienes, servicios y bienes de uso, conviene separarlo "
            "o cargar esos casos manualmente."
        )

        if not st.button("Procesar Compras ARCA"):
            return

        resultado = procesar_csv_compras_arca(
            archivo.name,
            df,
            categoria
        )

        mostrar_resumen_resultado(resultado)

    except Exception as e:
        st.error(f"No se pudo leer o procesar el archivo: {str(e)}")


# ======================================================
# TAB 2 - CARGA MANUAL
# ======================================================

def cargar_compra_manual():
    st.info(
        "Carga manual de comprobantes de compra. Útil para casos puntuales, "
        "bienes de uso, servicios específicos o comprobantes no incluidos en CSV."
    )

    df_categorias = obtener_categorias_activas()

    if df_categorias.empty:
        st.error("Primero cargá las Categorías de Compra desde Configuración.")
        return

    df_tipos = obtener_tipos_comprobantes()

    if df_tipos.empty:
        st.error("Primero cargá los Tipos de Comprobantes desde Configuración.")
        return

    with st.form("form_compra_manual"):
        st.subheader("Datos del comprobante")

        col1, col2, col3 = st.columns(3)

        with col1:
            fecha = st.date_input("Fecha de emisión", value=date.today())

        with col2:
            opciones_tipo = [
                f"{row['codigo']} - {row['descripcion']}"
                for _, row in df_tipos.iterrows()
            ]
            tipo_sel = st.selectbox("Tipo de comprobante", opciones_tipo)

        with col3:
            categoria = st.selectbox(
                "Categoría contable",
                df_categorias["categoria"].tolist()
            )

        codigo = tipo_sel.split(" - ")[0].strip()

        col1, col2, col3 = st.columns(3)

        with col1:
            punto_venta = st.text_input("Punto de venta", value="1")

        with col2:
            numero_comprobante = st.text_input("Número de comprobante")

        with col3:
            moneda_original = st.text_input("Moneda", value="PES")

        col1, col2, col3 = st.columns(3)

        with col1:
            cuit = st.text_input("CUIT proveedor")

        with col2:
            proveedor = st.text_input("Proveedor / Razón social")

        with col3:
            tipo_cambio = st.number_input("Tipo de cambio", min_value=0.0, value=1.0, step=0.01)

        st.divider()

        st.subheader("Importes fiscales")

        col1, col2, col3 = st.columns(3)

        with col1:
            total_neto_gravado = st.number_input("Total Neto Gravado", value=0.0, step=0.01)
            importe_no_gravado = st.number_input("Importe No Gravado", value=0.0, step=0.01)
            importe_exento = st.number_input("Importe Exento", value=0.0, step=0.01)

        with col2:
            iva_total = st.number_input("Total IVA facturado", value=0.0, step=0.01)
            credito_fiscal = st.number_input("Crédito Fiscal Computable", value=0.0, step=0.01)
            percepcion_iva = st.number_input("Percepción IVA", value=0.0, step=0.01)

        with col3:
            percepcion_iibb = st.number_input("Percepción IIBB", value=0.0, step=0.01)
            percepcion_otros = st.number_input("Percepción otros imp. nacionales", value=0.0, step=0.01)
            impuestos_municipales = st.number_input("Impuestos municipales", value=0.0, step=0.01)

        col1, col2, col3 = st.columns(3)

        with col1:
            impuestos_internos = st.number_input("Impuestos internos", value=0.0, step=0.01)

        with col2:
            otros_tributos = st.number_input("Otros tributos", value=0.0, step=0.01)

        with col3:
            total = st.number_input("Importe Total", value=0.0, step=0.01)

        total_sugerido = (
            total_neto_gravado
            + importe_no_gravado
            + importe_exento
            + iva_total
            + percepcion_iva
            + percepcion_iibb
            + percepcion_otros
            + impuestos_municipales
            + impuestos_internos
            + otros_tributos
        )

        st.caption(f"Total sugerido según componentes: {moneda(total_sugerido)}")

        guardar = st.form_submit_button("Guardar compra manual")

        if guardar:
            if numero_comprobante == "" or proveedor == "":
                st.warning("Completá número de comprobante y proveedor.")
            elif total <= 0:
                st.warning("El total debe ser mayor a cero.")
            else:
                datos = {
                    "fecha": fecha.strftime("%Y-%m-%d"),
                    "codigo": codigo,
                    "punto_venta": punto_venta,
                    "numero_comprobante": numero_comprobante,
                    "cuit": cuit,
                    "proveedor": proveedor,
                    "categoria_compra": categoria,
                    "total_neto_gravado": total_neto_gravado,
                    "importe_no_gravado": importe_no_gravado,
                    "importe_exento": importe_exento,
                    "iva_total": iva_total,
                    "credito_fiscal_computable": credito_fiscal,
                    "percepcion_iva": percepcion_iva,
                    "percepcion_iibb": percepcion_iibb,
                    "percepcion_otros_imp_nac": percepcion_otros,
                    "impuestos_municipales": impuestos_municipales,
                    "impuestos_internos": impuestos_internos,
                    "otros_tributos": otros_tributos,
                    "total": total,
                    "moneda": moneda_original,
                    "tipo_cambio": tipo_cambio
                }

                resultado = procesar_compra_manual(datos)
                mostrar_resumen_resultado(resultado)


# ======================================================
# TAB 3 - LIBRO IVA COMPRAS
# ======================================================

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
            categoria_compra,
            cuenta_principal_nombre,
            neto,
            importe_no_gravado,
            importe_exento,
            iva_total,
            credito_fiscal_computable,
            iva_no_computable,
            percepcion_iva,
            percepcion_iibb,
            percepcion_otros_imp_nac,
            impuestos_municipales,
            impuestos_internos,
            otros_tributos,
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

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Neto Gravado", moneda(df["neto"].sum()))
    c2.metric("IVA Total", moneda(df["iva_total"].sum()))
    c3.metric("Crédito Fiscal Computable", moneda(df["credito_fiscal_computable"].sum()))
    c4.metric("Total Compras", moneda(df["total"].sum()))

    excel = exportar_excel({
        "Libro IVA Compras": df_vista
    })

    st.download_button(
        "Descargar Libro IVA Compras Excel",
        data=excel,
        file_name="libro_iva_compras.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# TAB 4 - RESUMEN
# ======================================================

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
            categoria_compra,
            neto,
            iva_total,
            credito_fiscal_computable,
            total
        FROM compras_comprobantes
    """, fetch=True)

    if df.empty:
        st.info("No hay compras cargadas.")
        return

    resumen_mensual = df.groupby(["anio", "mes"], as_index=False).agg({
        "neto": "sum",
        "iva_total": "sum",
        "credito_fiscal_computable": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_mensual = resumen_mensual.rename(columns={
        "tipo": "cantidad_comprobantes"
    })

    resumen_categoria = df.groupby(["categoria_compra"], as_index=False).agg({
        "neto": "sum",
        "iva_total": "sum",
        "credito_fiscal_computable": "sum",
        "total": "sum",
        "tipo": "count"
    })

    resumen_categoria = resumen_categoria.rename(columns={
        "tipo": "cantidad"
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
    col2.metric("IVA Total", moneda(df["iva_total"].sum()))
    col3.metric("Crédito Fiscal Computable", moneda(df["credito_fiscal_computable"].sum()))
    col4.metric("Total Compras", moneda(df["total"].sum()))

    st.divider()

    st.subheader("Resumen mensual")
    st.dataframe(preparar_vista(resumen_mensual), use_container_width=True)

    st.subheader("Resumen por categoría")
    st.dataframe(preparar_vista(resumen_categoria), use_container_width=True)

    st.subheader("Ranking de proveedores")
    st.dataframe(preparar_vista(ranking_proveedores), use_container_width=True)

    excel = exportar_excel({
        "Resumen Mensual": resumen_mensual,
        "Resumen Categoria": resumen_categoria,
        "Ranking Proveedores": ranking_proveedores
    })

    st.download_button(
        "Descargar Estadísticas Compras Excel",
        data=excel,
        file_name="estadisticas_compras.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ======================================================
# TAB 5 - CUENTA CORRIENTE PROVEEDORES
# ======================================================

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