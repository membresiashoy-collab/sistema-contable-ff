import streamlit as st
import pandas as pd
from core.database import ejecutar_query, eliminar_todo_diario


def mostrar_diario():
    st.title("📓 Libro Diario")

    df = ejecutar_query("""
    SELECT id_asiento, fecha, cuenta, debe, haber, glosa
    FROM libro_diario
    ORDER BY id_asiento, id
    """, fetch=True)

    if df.empty:
        st.info("No hay movimientos cargados.")
        return

    st.dataframe(df, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        st.metric("Total Debe", f"$ {df['debe'].sum():,.2f}")

    with c2:
        st.metric("Total Haber", f"$ {df['haber'].sum():,.2f}")

    if st.button("🗑 Vaciar Libro Diario"):
        eliminar_todo_diario()
        st.success("Datos eliminados.")
        st.rerun()