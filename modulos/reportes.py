import streamlit as st
import database

def mostrar_reportes():
    st.title("📖 Libro Diario Unificado")
    
    # Consulta de todos los asientos guardados
    df = database.ejecutar_query("""
        SELECT id_asiento as 'Asiento', 
               fecha as 'Fecha', 
               cuenta as 'Cuenta', 
               debe as 'Debe', 
               haber as 'Haber', 
               glosa as 'Detalle' 
        FROM libro_diario 
        ORDER BY id_asiento ASC
    """, fetch=True)
    
    if not df.empty:
        # Visualización profesional de la tabla
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Opcional: Sumas de verificación para asegurar que el libro balancea
        col1, col2 = st.columns(2)
        col1.metric("Total Debe", f"$ {df['Debe'].sum():,.2f}")
        col2.metric("Total Haber", f"$ {df['Haber'].sum():,.2f}")
    else:
        st.info("No hay asientos contables registrados.")