import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Panel de Control y Configuración")

    # --- NUEVA SECCIÓN: ESTADO DE DOCUMENTOS CARGADOS ---
    st.header("📊 Estado de los Documentos")
    col_a, col_b = st.columns(2)

    # Verificar Plan de Cuentas
    res_plan = ejecutar_query("SELECT COUNT(*) as cant FROM plan_cuentas", fetch=True)
    cant_plan = res_plan.iloc[0]['cant']
    with col_a:
        if cant_plan > 0:
            st.success(f"✅ Plan de Cuentas: {cant_plan} cuentas cargadas.")
            if st.checkbox("Ver detalle del Plan"):
                df_p = ejecutar_query("SELECT * FROM plan_cuentas", fetch=True)
                st.dataframe(df_p, height=200)
        else:
            st.error("❌ Plan de Cuentas: No cargado.")

    # Verificar Tabla de Comprobantes
    res_tipos = ejecutar_query("SELECT COUNT(*) as cant FROM tipos_comprobantes", fetch=True)
    cant_tipos = res_tipos.iloc[0]['cant']
    with col_b:
        if cant_tipos > 0:
            st.success(f"✅ Tabla ARCA: {cant_tipos} comprobantes configurados.")
            if st.checkbox("Ver detalle de Comprobantes"):
                df_t = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
                st.dataframe(df_t, height=200)
        else:
            st.error("❌ Tabla ARCA: No cargada.")

    st.divider()

    # --- SECCIÓN DE CARGA / ACTUALIZACIÓN ---
    st.header("📥 Cargar o Actualizar Documentos")

    # 1. Plan de Cuentas
    with st.expander("Subir Plan de Cuentas"):
        archivo_plan = st.file_uploader("CSV del Plan de Cuentas", type=["csv"], key="u_plan")
        if archivo_plan:
            if st.button("Actualizar Plan de Cuentas"):
                try:
                    df = pd.read_csv(archivo_plan, sep=None, engine='python', encoding='latin-1')
                    ejecutar_query("DELETE FROM plan_cuentas")
                    for _, fila in df.iterrows():
                        ejecutar_query("INSERT INTO plan_cuentas VALUES (?, ?)", 
                                       (str(fila.iloc[0]), str(fila.iloc[1]).upper().strip()))
                    st.rerun() # Refresca para mostrar el cambio arriba
                except Exception as e:
                    st.error(f"Error: {e}")

    # 2. Tabla de Comprobantes
    with st.expander("Subir TABLACOMPROBANTES.csv"):
        archivo_tipos = st.file_uploader("Archivo de códigos ARCA", type=["csv"], key="u_tipos")
        if archivo_tipos:
            if st.button("Actualizar Lógica de Comprobantes"):
                try:
                    # Ajustado a tu archivo específico con separador ';'
                    df_tipos = pd.read_csv(archivo_tipos, sep=';', encoding='latin-1')
                    ejecutar_query("DELETE FROM tipos_comprobantes")
                    for _, fila in df_tipos.iterrows():
                        cod = int(fila['Código'])
                        desc = str(fila['Descripción']).upper().strip()
                        signo = -1 if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc else 1
                        ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (cod, desc, signo))
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")