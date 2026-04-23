import streamlit as st
import database
import pandas as pd

def mostrar_diario():
    st.title("📓 Libro Diario Unificado")
    
    filtro = st.radio("Filtrar origen:", ["Todos", "VENTAS", "COMPRAS"], horizontal=True)
    
    query = "SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario"
    if filtro != "Todos":
        query += f" WHERE origen = '{filtro}'"
    query += " ORDER BY id_asiento ASC"
    
    df = database.ejecutar_query(query, fetch=True)
    
    if df.empty:
        st.warning("El Libro Diario está vacío. Cargue datos en Ventas o Compras.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)