import streamlit as st
import database

def mostrar_reportes():
    st.title("📖 Libro Diario Unificado")
    
    # Intentamos traer los datos directamente
    try:
        df = database.ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)
        
        if not df.empty:
            # Renombramos columnas para que se vea profesional
            df.columns = ['Asiento', 'Fecha', 'Cuenta', 'Debe', 'Haber', 'Detalle']
            
            # Mostramos la tabla
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Totales para verificar balance
            total_debe = df['Debe'].sum()
            total_haber = df['Haber'].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("Total Debe", f"$ {total_debe:,.2f}")
            c2.metric("Total Haber", f"$ {total_haber:,.2f}")
            
            if round(total_debe, 2) != round(total_haber, 2):
                st.error("⚠️ El Libro Diario no balancea.")
        else:
            st.warning("No se encontraron asientos en la base de datos. Asegúrate de procesar las ventas primero.")
            
    except Exception as e:
        st.error(f"Error al leer el Libro Diario: {e}")