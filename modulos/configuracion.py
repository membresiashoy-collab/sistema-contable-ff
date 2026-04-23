import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Panel de Control y Configuración")

    # --- VERIFICACIÓN DE DATOS ---
    try:
        df_p = ejecutar_query("SELECT * FROM plan_cuentas", fetch=True)
        df_t = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
    except:
        df_p = pd.DataFrame()
        df_t = pd.DataFrame()

    st.header("📊 Estado de los Documentos")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📖 Plan de Cuentas")
        if not df_p.empty:
            st.success(f"Cargadas: {len(df_p)} cuentas")
            st.dataframe(df_p, use_container_width=True, height=200)
        else:
            st.warning("No hay Plan de Cuentas en la base de datos.")

    with col2:
        st.subheader("📋 Tabla ARCA")
        if not df_t.empty:
            st.success(f"Configurados: {len(df_t)} tipos")
            st.dataframe(df_t, use_container_width=True, height=200)
        else:
            st.warning("No hay Tabla de Comprobantes cargada.")

    st.divider()
    
    # --- FORMULARIOS DE CARGA (Se mantienen igual) ---
    with st.expander("📥 Subir / Actualizar Archivos"):
        f_plan = st.file_uploader("Archivo Plan de Cuentas", type=["csv"], key="plan_up")
        if f_plan and st.button("Guardar Plan"):
            df = pd.read_csv(f_plan, sep=None, engine='python', encoding='latin-1')
            ejecutar_query("DELETE FROM plan_cuentas")
            for _, fila in df.iterrows():
                ejecutar_query("INSERT INTO plan_cuentas VALUES (?, ?)", (str(fila.iloc[0]), str(fila.iloc[1]).upper().strip()))
            st.success("Plan guardado correctamente")
            st.rerun()

        f_tipos = st.file_uploader("Archivo TABLACOMPROBANTES.csv", type=["csv"], key="tipos_up")
        if f_tipos and st.button("Guardar Comprobantes"):
            df = pd.read_csv(f_tipos, sep=';', encoding='latin-1')
            ejecutar_query("DELETE FROM tipos_comprobantes")
            for _, fila in df.iterrows():
                signo = -1 if "NOTA DE CREDITO" in str(fila['Descripción']).upper() else 1
                ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (int(fila['Código']), str(fila['Descripción']).upper(), signo))
            st.success("Tabla ARCA guardada")
            st.rerun()