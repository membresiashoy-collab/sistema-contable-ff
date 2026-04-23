import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_configuracion():
    st.header("⚙️ Configuración del Sistema")

    # Intentar leer datos de la base de datos
    try:
        df_p = ejecutar_query("SELECT * FROM plan_cuentas", fetch=True)
        df_t = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        df_p = pd.DataFrame()
        df_t = pd.DataFrame()

    # Visualización de lo cargado
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📖 Plan de Cuentas")
        if not df_p.empty:
            st.success(f"Cargadas: {len(df_p)} cuentas")
            st.dataframe(df_p, use_container_width=True, height=200)
        else:
            st.info("Plan de cuentas vacío.")

    with col2:
        st.subheader("📋 Tabla ARCA")
        if not df_t.empty:
            st.success(f"Configurados: {len(df_t)} códigos")
            st.dataframe(df_t, use_container_width=True, height=200)
        else:
            st.info("Tabla de comprobantes vacía.")

    st.divider()

    # Formularios de carga
    st.subheader("📥 Cargar Archivos")
    
    file_p = st.file_uploader("Subir Plan (CSV)", type=["csv"], key="u_p")
    if file_p and st.button("Guardar Plan"):
        df = pd.read_csv(file_p, sep=None, engine='python', encoding='latin-1')
        ejecutar_query("DELETE FROM plan_cuentas")
        for _, fila in df.iterrows():
            ejecutar_query("INSERT INTO plan_cuentas VALUES (?, ?)", (str(fila.iloc[0]), str(fila.iloc[1]).upper().strip()))
        st.success("Plan guardado.")
        st.rerun()

    file_t = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"], key="u_t")
    if file_t and st.button("Guardar Comprobantes"):
        # Usamos ';' porque es el separador de TU archivo
        df = pd.read_csv(file_t, sep=';', encoding='latin-1')
        ejecutar_query("DELETE FROM tipos_comprobantes")
        for _, fila in df.iterrows():
            desc = str(fila['Descripción']).upper()
            signo = -1 if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc else 1
            ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (int(fila['Código']), desc, signo))
        st.success("Comprobantes guardados.")
        st.rerun()