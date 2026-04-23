import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_ventas():
    st.title("📂 Procesar Ventas ARCA (CSV)")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # Leemos el CSV. ARCA suele usar coma o punto y coma.
            df = pd.read_csv(archivo, encoding='latin-1', sep=None, engine='python')
            
            st.write("### Vista previa del CSV:")
            st.dataframe(df.head(3))

            # Limpiamos los nombres de las columnas (quita espacios raros)
            df.columns = df.columns.str.strip()

            # Mapeo de columnas para CSV de ARCA
            # Intentamos buscar por nombre, si no, usamos posición
            for index, fila in df.iterrows():
                # Buscamos columnas comunes en el CSV de ARCA
                fecha = fila.get('Fecha') or fila.iloc[0]
                tipo = fila.get('Tipo') or fila.iloc[1]
                receptor = fila.get('Nombre o Razón Social Receptor') or fila.iloc[3]
                cuit = fila.get('CUIT Receptor') or fila.iloc[4]
                neto = fila.get('Importe Neto Gravado') or fila.iloc[11]
                iva = fila.get('Importe IVA') or fila.iloc[13]
                total = fila.get('Importe Total') or fila.iloc[15]

                query = """
                INSERT INTO ventas (fecha, tipo_comprobante, receptor, cuit_receptor, neto, iva, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                ejecutar_query(query, (str(fecha), str(tipo), str(receptor), str(cuit), 
                                      float(neto), float(iva), float(total)))
            
            st.success(f"✅ ¡Éxito! Se cargaron {len(df)} registros del CSV.")
            
        except Exception as e:
            st.error(f"Hubo un problema al leer el CSV: {e}")
            st.info("Asegúrate de que el archivo sea el CSV descargado directamente de ARCA.")