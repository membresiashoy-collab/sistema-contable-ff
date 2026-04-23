import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Configuración Maestra")
    
    # --- SECCIÓN 1: PLAN DE CUENTAS ---
    st.subheader("1. Plan de Cuentas")
    archivo_plan = st.file_uploader("Subir Plan de Cuentas (CSV)", type=["csv"], key="plan")
    if archivo_plan:
        if st.button("Guardar Plan"):
            try:
                df = pd.read_csv(archivo_plan, sep=None, engine='python', encoding='latin-1')
                ejecutar_query("DELETE FROM plan_cuentas")
                for _, fila in df.iterrows():
                    cod = str(fila.iloc[0])
                    nom = str(fila.iloc[1]).upper().strip()
                    ejecutar_query("INSERT INTO plan_cuentas VALUES (?, ?)", (cod, nom))
                st.success("✅ Plan de Cuentas guardado.")
            except Exception as e:
                st.error(f"Error al leer el plan: {e}")

    st.divider()

    # --- SECCIÓN 2: TABLA DE COMPROBANTES (ARCA) ---
    st.subheader("2. Tabla de Comprobantes (ARCA)")
    archivo_tipos = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"], key="tipos")
    
    if archivo_tipos:
        try:
            # Leemos el archivo usando el separador detectado en tu CSV (punto y coma)
            df_tipos = pd.read_csv(archivo_tipos, sep=';', encoding='latin-1')
            
            st.write("### ✅ Vista previa de Comprobantes:")
            st.dataframe(df_tipos.head())
            
            if st.button("Confirmar y Cargar Lógica Contable"):
                ejecutar_query("DELETE FROM tipos_comprobantes")
                count = 0
                for _, fila in df_tipos.iterrows():
                    # Usamos los nombres de columna exactos de tu archivo: 'Código' y 'Descripción'
                    cod = int(fila['Código'])
                    desc = str(fila['Descripción']).upper().strip()
                    
                    # Lógica de Signo: Notas de Crédito invierten el asiento (-1)
                    if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc:
                        signo = -1
                    else:
                        signo = 1
                        
                    ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (cod, desc, signo))
                    count += 1
                st.success(f"✅ Se cargaron {count} comprobantes con su lógica de suma/resta.")
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")