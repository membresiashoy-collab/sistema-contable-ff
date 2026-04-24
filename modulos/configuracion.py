import streamlit as st
from database import ejecutar_query


def mostrar_configuracion():
    st.title("⚙️ Configuración")

    st.subheader("Tipos de Comprobantes")

    df = ejecutar_query("""
        SELECT *
        FROM tipos_comprobantes
        ORDER BY codigo
    """, fetch=True)

    if df.empty:
        st.info("Sin datos cargados.")
    else:
        st.dataframe(df, use_container_width=True)

    st.divider()

    st.subheader("Plan de Cuentas")

    df2 = ejecutar_query("""
        SELECT *
        FROM plan_cuentas
        ORDER BY codigo
    """, fetch=True)

    if df2.empty:
        st.info("Sin plan cargado.")
    else:
        st.dataframe(df2, use_container_width=True)