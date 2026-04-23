import streamlit as st
import database

def mostrar_reportes():
    st.title("📖 Libro Diario Unificado")
    
    if st.button("🗑️ Limpiar Todo el Diario"):
        database.ejecutar_query("DELETE FROM libro_diario")
        st.success("Diario vaciado.")

    df = database.ejecutar_query("SELECT id_asiento as 'Asiento', fecha as 'Fecha', cuenta as 'Cuenta', debe as 'Debe', haber as 'Haber', glosa as 'Detalle' FROM libro_diario ORDER BY id_asiento ASC", fetch=True)
    
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay asientos registrados aún.")