import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Panel de Control y Configuración")

    # --- SECCIÓN 1: ESTADO DE DOCUMENTOS CARGADOS ---
    st.header("📊 Estado de los Documentos")
    col_a, col_b = st.columns(2)

    # Verificación del Plan de Cuentas
    try:
        res_plan = ejecutar_query("SELECT COUNT(*) as cant FROM plan_cuentas", fetch=True)
        cant_plan = res_plan.iloc[0]['cant'] if not res_plan.empty else 0
    except:
        cant_plan = 0

    with col_a:
        if cant_plan > 0:
            st.success(f"✅ Plan de Cuentas: {cant_plan} cuentas cargadas.")
            if st.checkbox("Ver detalle del Plan", key="view_pdc"):
                df_p = ejecutar_query("SELECT * FROM plan_cuentas", fetch=True)
                st.dataframe(df_p, use_container_width=True, height=250)
        else:
            st.error("❌ Plan de Cuentas: No detectado.")

    # Verificación de Tabla de Comprobantes
    try:
        res_tipos = ejecutar_query("SELECT COUNT(*) as cant FROM tipos_comprobantes", fetch=True)
        cant_tipos = res_tipos.iloc[0]['cant'] if not res_tipos.empty else 0
    except:
        cant_tipos = 0

    with col_b:
        if cant_tipos > 0:
            st.success(f"✅ Tabla ARCA: {cant_tipos} códigos configurados.")
            if st.checkbox("Ver detalle de Comprobantes", key="view_tipos"):
                df_t = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
                st.dataframe(df_t, use_container_width=True, height=250)
        else:
            st.error("❌ Tabla ARCA: No detectada.")

    st.divider()

    # --- SECCIÓN 2: CARGA / ACTUALIZACIÓN ---
    st.header("📥 Cargar o Actualizar")

    # Plan de Cuentas
    with st.expander("Subir Plan de Cuentas"):
        archivo_plan = st.file_uploader("CSV del Plan de Cuentas", type=["csv"], key="u_plan")
        if archivo_plan:
            if st.button("Confirmar Actualización de Plan"):
                df = pd.read_csv(archivo_plan, sep=None, engine='python', encoding='latin-1')
                ejecutar_query("DELETE FROM plan_cuentas")
                for _, fila in df.iterrows():
                    ejecutar_query("INSERT INTO plan_cuentas VALUES (?, ?)", 
                                   (str(fila.iloc[0]), str(fila.iloc[1]).upper().strip()))
                st.success("Plan actualizado. Refresque la página.")
                st.balloons()

    # Tabla de Comprobantes
    with st.expander("Subir TABLACOMPROBANTES.csv"):
        archivo_tipos = st.file_uploader("Archivo de códigos ARCA", type=["csv"], key="u_tipos")
        if archivo_tipos:
            if st.button("Confirmar Actualización de Comprobantes"):
                # Forzamos el separador ';' que tiene tu archivo
                df_tipos = pd.read_csv(archivo_tipos, sep=';', encoding='latin-1')
                ejecutar_query("DELETE FROM tipos_comprobantes")
                for _, fila in df_tipos.iterrows():
                    cod = int(fila['Código'])
                    desc = str(fila['Descripción']).upper().strip()
                    signo = -1 if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc else 1
                    ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (cod, desc, signo))
                st.success("Lógica ARCA actualizada.")
                st.balloons()