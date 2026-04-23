import streamlit as st
import pandas as pd
# IMPORTANTE: No usamos 'from database', usamos la ruta completa desde la raíz
import database 

def mostrar_ventas():
    st.title("📤 Registro de Ventas")
    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])
    
    if archivo:
        df = pd.read_csv(archivo, sep=';', decimal=',')
        if st.button("Procesar Ventas"):
            asiento = database.obtener_proximo_asiento()
            # Lógica de carga aquí...
            st.success("Ventas procesadas")