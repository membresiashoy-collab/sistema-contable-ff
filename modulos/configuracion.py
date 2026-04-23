import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Configuración del Sistema")
    
    st.subheader("📥 Cargar Plan de Cuentas Maestro")
    st.markdown("""
    Sube aquí el archivo CSV de tu Plan de Cuentas. 
    El sistema usará estos nombres para validar los asientos contables.
    """)
    
    archivo_plan = st.file_uploader("Subir CSV de Plan de Cuentas", type=["csv"])
    
    if archivo_plan:
        try:
            # Leemos el plan con detección automática de separador
            df_plan = pd.read_csv(archivo_plan, sep=None, engine='python', encoding='latin-1')
            df_plan.columns = df_plan.columns.str.strip().str.upper()
            
            st.write("### Vista previa del Plan detectado:")
            st.dataframe(df_plan.head())
            
            if st.button("Confirmar y Guardar Plan de Cuentas"):
                ejecutar_query("DELETE FROM plan_cuentas")
                for _, fila in df_plan.iterrows():
                    # Mapeo: Asumimos columna 0 es Código y columna 1 es Nombre
                    cod = str(fila.iloc[0])
                    nom = str(fila.iloc[1]).upper().strip()
                    ejecutar_query("INSERT INTO plan_cuentas (codigo, nombre) VALUES (?, ?)", (cod, nom))
                st.success("✅ Plan de Cuentas guardado. Los nombres de este archivo ahora validan los asientos.")
        except Exception as e:
            st.error(f"Error al cargar el plan: {e}")

    st.divider()
    st.subheader("🗑️ Mantenimiento")
    if st.button("Borrar todos los Asientos del Diario"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Libro Diario reseteado.")