import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Configuración del Sistema")
    
    st.subheader("📥 Cargar Plan de Cuentas Maestro")
    archivo_plan = st.file_uploader("Subir CSV de Plan de Cuentas", type=["csv"])
    
    if archivo_plan:
        try:
            # Leemos el plan (usando separador automático)
            df_plan = pd.read_csv(archivo_plan, sep=None, engine='python', encoding='latin-1')
            df_plan.columns = df_plan.columns.str.strip().str.upper()
            
            st.write("### Vista previa del Plan de Cuentas:")
            st.dataframe(df_plan.head())
            
            if st.button("Confirmar y Guardar Plan"):
                ejecutar_query("DELETE FROM plan_cuentas")
                for _, fila in df_plan.iterrows():
                    # Mapeo: 1ra col Codigo, 2da col Nombre
                    cod = str(fila.iloc[0])
                    nom = str(fila.iloc[1]).upper().strip()
                    ejecutar_query("INSERT INTO plan_cuentas (codigo, nombre) VALUES (?, ?)", (cod, nom))
                st.success("✅ Plan de Cuentas guardado. Ahora manda sobre los asientos.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    if st.button("🗑️ Vaciar Libro Diario"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Diario reseteado.")