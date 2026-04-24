import streamlit as st
import pandas as pd
from database import ejecutar_query, eliminar_todo_diario


def formatear_fecha(fecha):
    try:
        fecha_convertida = pd.to_datetime(fecha, dayfirst=True, errors="coerce")

        if pd.isna(fecha_convertida):
            return fecha

        return fecha_convertida.strftime("%d/%m/%Y")

    except Exception:
        return fecha


def mostrar_diario():
    st.title("📓 Libro Diario")

    df = ejecutar_query("""
        SELECT 
            id,
            id_asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            origen,
            archivo
        FROM libro_diario
    """, fetch=True)

    if df.empty:
        st.info("Sin movimientos.")
        return

    df["fecha_orden"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    st.subheader("Filtros")

    origenes = ["Todos"] + sorted(df["origen"].dropna().unique().tolist())

    origen_seleccionado = st.selectbox(
        "Filtrar por origen",
        origenes
    )

    if origen_seleccionado != "Todos":
        df = df[df["origen"] == origen_seleccionado]

    archivos = ["Todos"] + sorted(df["archivo"].dropna().unique().tolist())

    archivo_seleccionado = st.selectbox(
        "Filtrar por archivo",
        archivos
    )

    if archivo_seleccionado != "Todos":
        df = df[df["archivo"] == archivo_seleccionado]

    df = df.sort_values(
        by=["fecha_orden", "id_asiento", "id"],
        ascending=True
    )

    df_vista = df[[
        "id_asiento",
        "fecha",
        "cuenta",
        "debe",
        "haber",
        "glosa",
        "origen",
        "archivo"
    ]].copy()

    df_vista.index = range(1, len(df_vista) + 1)
    df_vista.index.name = "N°"

    st.subheader("Movimientos contables")
    st.dataframe(df_vista, use_container_width=True)

    st.divider()

    c1, c2, c3 = st.columns(3)

    c1.metric("Total Debe", f"$ {df_vista['debe'].sum():,.2f}")
    c2.metric("Total Haber", f"$ {df_vista['haber'].sum():,.2f}")
    c3.metric("Diferencia", f"$ {(df_vista['debe'].sum() - df_vista['haber'].sum()):,.2f}")

    st.divider()

    st.subheader("Resumen por origen")

    resumen = df_vista.groupby("origen")[["debe", "haber"]].sum().reset_index()
    resumen["diferencia"] = resumen["debe"] - resumen["haber"]

    st.dataframe(resumen, use_container_width=True)

    st.divider()

    if "confirmar_limpiar_diario" not in st.session_state:
        st.session_state["confirmar_limpiar_diario"] = False

    if st.button("🧹 Limpiar Libro Diario"):
        st.session_state["confirmar_limpiar_diario"] = True

    if st.session_state["confirmar_limpiar_diario"]:
        st.warning("¿Confirmás eliminar todos los movimientos del Libro Diario?")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sí, limpiar libro diario"):
                eliminar_todo_diario()
                st.success("Libro Diario limpiado.")
                st.session_state["confirmar_limpiar_diario"] = False
                st.rerun()

        with col2:
            if st.button("Cancelar"):
                st.session_state["confirmar_limpiar_diario"] = False
                st.rerun()