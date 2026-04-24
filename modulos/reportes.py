import streamlit as st
from database import ejecutar_query, eliminar_todo_diario


def mostrar_diario():
    st.title("📓 Libro Diario")

    df = ejecutar_query("""
        SELECT id_asiento, fecha, cuenta, debe, haber, glosa
        FROM libro_diario
        ORDER BY id_asiento, id
    """, fetch=True)

    if df.empty:
        st.info("Sin movimientos.")
        return

    st.dataframe(df, use_container_width=True)

    st.divider()

    c1, c2 = st.columns(2)

    c1.metric("Total Debe", f"$ {df['debe'].sum():,.2f}")
    c2.metric("Total Haber", f"$ {df['haber'].sum():,.2f}")

    st.divider()

    if st.button("🧹 LIMPIAR LIBRO DIARIO"):
        eliminar_todo_diario()
        st.success("Libro Diario limpiado.")
        st.rerun()