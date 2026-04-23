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
            # LEER ARCHIVO COMO TEXTO PRIMERO PARA LIMPIARLO
            raw_data = archivo_tipos.read().decode('latin-1')
            lineas = raw_data.splitlines()
            
            # Buscamos la línea donde realmente empiezan los datos (Código, Descripción)
            # Según tu archivo, los datos reales empiezan después de las primeras líneas de encabezado
            datos_limpios = []
            for linea in lineas:
                if "Código" in linea or "Codigo" in linea:
                    continue # Saltamos la cabecera de texto
                # Solo procesamos líneas que tengan el formato esperado (Número, Texto)
                partes = linea.split(',')
                if len(partes) >= 2 and partes[0].replace('.','').isdigit():
                    datos_limpios.append(linea)

            # Reconstruimos el DataFrame solo con las líneas de datos puras
            df_tipos = pd.read_csv(io.StringIO('\n'.join(datos_limpios)), 
                                   names=['Código', 'Descripción'], 
                                   header=None)
            
            st.write("Vista previa de la tabla procesada:")
            st.dataframe(df_tipos.head())
            
            if st.button("Cargar Lógica de Comprobantes"):
                ejecutar_query("DELETE FROM tipos_comprobantes")
                count = 0
                for _, fila in df_tipos.iterrows():
                    cod = int(float(fila['Código']))
                    desc = str(fila['Descripción']).upper().strip()
                    
                    # Lógica de Signo: Notas de Crédito invierten el asiento (-1)
                    signo = -1 if "NOTA DE CREDITO" in desc or "NOTA DE CRÉDITO" in desc else 1
                    
                    ejecutar_query("INSERT INTO tipos_comprobantes VALUES (?, ?, ?)", (cod, desc, signo))
                    count += 1
                st.success(f"✅ Se cargaron {count} tipos de comprobantes correctamente.")
        except Exception as e:
            st.error(f"Error al procesar: {e}")