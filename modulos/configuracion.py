import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Configuración Maestra")
    
    # --- SECCIÓN PLAN DE CUENTAS ---
    st.subheader("1. Plan de Cuentas")
    archivo_plan = st.file_uploader("Subir Plan de Cuentas", type=["csv"], key="plan")
    if archivo_plan:
        if st.button("Guardar Plan"):
            df = pd.read_csv(archivo_plan, sep=None, engine='python', encoding='latin-1')
            ejecutar_query("DELETE FROM plan_cuentas")
            for _, fila in df.iterrows():
                ejecutar_query("INSERT INTO plan_cuentas VALUES (?, ?)", (str(fila.iloc[0]), str(fila.iloc[1]).upper().strip()))
            st.success("Plan guardado.")

    st.divider()

    # --- SECCIÓN TABLA DE COMPROBANTES ---
    st.subheader("2. Tabla de Comprobantes (ARCA)")
    archivo_tipos = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"], key="tipos")
    
    if archivo_tipos:
        # Saltamos las 2 filas de encabezado del archivo
        df_tipos = pd.read_csv(archivo_tipos, skiprows=2, sep=',', encoding='utf-8')
        st.dataframe(df_tipos.head())
        
        if st.button("Cargar Lógica de Comprobantes"):
            ejecutar_query("DELETE FROM tipos_comprobantes")
            for _, fila in df_tipos.iterrows():
                cod = int(fila['Código'])
                desc = str(fila['Descripción']).upper()
                # Lógica: Si es Nota de Crédito, el signo es -1
                signo = -1 if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc else 1
                ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (cod, desc, signo))
            st.success("Lógica de comprobantes cargada exitosamente.")