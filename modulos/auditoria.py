import streamlit as st
from core.database import ejecutar_query, limpiar_historial


def mostrar_estado():
    st.title("📋 Estado de Cargas")

    df = ejecutar_query("""
        SELECT *
        FROM historial_cargas
        ORDER BY id DESC
    """, fetch=True)

    if df.empty:
        st.info("Sin registros.")
        return

    st.dataframe(df, use_container_width=True)

    st.metric("Total cargas", len(df))

    st.divider()

    if st.button("🧹 LIMPIAR HISTORIAL", type="primary"):
        limpiar_historial()
        st.success("Historial eliminado correctamente.")
        st.rerun()