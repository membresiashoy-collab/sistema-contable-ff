import streamlit as st
from core.database import ejecutar_query


def mostrar_estado():
    st.title("📋 Estado de Cargas")

    df = ejecutar_query("""
    SELECT fecha_carga,
           modulo,
           nombre_archivo,
           registros_procesados
    FROM historial_cargas
    ORDER BY id DESC
    """, fetch=True)

    if df.empty:
        st.info("Sin historial.")
    else:
        st.dataframe(df, use_container_width=True)

        st.metric(
            "Archivos Procesados",
            len(df)
        )