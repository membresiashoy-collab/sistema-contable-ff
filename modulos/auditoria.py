import streamlit as st
from database import ejecutar_query

def mostrar_estado():
    st.title("📊 Estado de Cargas")
    historial = ejecutar_query("SELECT strftime('%m/%d/%Y %H:%M', fecha_carga) as Fecha, modulo, nombre_archivo, registros_procesados FROM historial_cargas ORDER BY id DESC", fetch=True)
    
    if not historial.empty:
        st.table(historial)
    else:
        st.info("No hay archivos cargados aún.")