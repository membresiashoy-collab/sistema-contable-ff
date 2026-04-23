import streamlit as st
import database

def mostrar_reportes():
    st.title("📖 Libro Diario Unificado")
    
    if st.button("🗑️ Limpiar Base de Datos"):
        database.ejecutar_query("DELETE FROM libro_diario")
        st.rerun()

    df = database.ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)
    
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("El libro diario está vacío.")