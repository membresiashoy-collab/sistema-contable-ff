import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_configuracion():
    st.title("⚙️ Configuración Maestra")
    
    # --- SECCIÓN 1: PLAN DE CUENTAS ---
    st.subheader("1. Plan de Cuentas")
    archivo_plan = st.file_uploader("Subir Plan de Cuentas (CSV)", type=["csv"], key="plan")
    if archivo_plan:
        if st.button("Guardar Plan"):
            try:
                # Usamos latin-1 que es más tolerante a caracteres de Excel
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
    st.write("Suba el archivo 'TABLACOMPROBANTES.xls - Tipo de comprobantes.csv'")
    
    archivo_tipos = st.file_uploader("Subir CSV de Comprobantes", type=["csv"], key="tipos")
    
    if archivo_tipos:
        try:
            # SOLUCIÓN AL ERROR: Usamos encoding 'latin-1' para evitar el UnicodeDecodeError
            # Saltamos las 2 filas de encabezado que tiene tu archivo
            df_tipos = pd.read_csv(archivo_tipos, skiprows=2, sep=',', encoding='latin-1')
            
            st.write("Vista previa de la tabla cargada:")
            st.dataframe(df_tipos.head())
            
            if st.button("Cargar Lógica de Comprobantes"):
                ejecutar_query("DELETE FROM tipos_comprobantes")
                count = 0
                for _, fila in df_tipos.iterrows():
                    # Verificamos que la fila tenga datos válidos
                    if pd.notna(fila['Código']) and pd.notna(fila['Descripción']):
                        cod = int(float(fila['Código']))
                        desc = str(fila['Descripción']).upper().strip()
                        
                        # Lógica de Signo: Notas de Crédito restan (-1), lo demás suma (+1)
                        # Buscamos la palabra sin tildes por seguridad
                        if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc:
                            signo = -1
                        else:
                            signo = 1
                            
                        ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (cod, desc, signo))
                        count += 1
                st.success(f"✅ Se cargaron {count} tipos de comprobantes con su lógica contable.")
        except Exception as e:
            st.error(f"Error técnico al procesar comprobantes: {e}")
            st.info("Sugerencia: Intente guardar el archivo CSV con codificación Latin-1 o Excel CSV.")