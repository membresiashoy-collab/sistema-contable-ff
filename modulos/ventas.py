import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_ventas():
    st.title("📂 Procesar Ventas ARCA")
    archivo = st.file_uploader("Subir TXT de ARCA", type=["txt"])
    
    if archivo:
        # Leemos el archivo saltando posibles filas vacías
        df = pd.read_csv(archivo, sep='\t', encoding='latin-1')
        
        st.write("### Vista previa de los datos detectados:")
        st.dataframe(df.head(3)) # Esto nos sirve para ver si leyó bien

        # Buscamos las columnas por posición en lugar de por nombre exacto
        # (ARCA suele usar: 0=Fecha, 1=Tipo, 3=Receptor, 4=CUIT, 11=Neto, 13=IVA, 15=Total)
        try:
            for index, fila in df.iterrows():
                # Usamos .iloc para entrar por número de columna y evitar el KeyError
                fecha = fila.iloc[0]
                tipo = fila.iloc[1]
                receptor = fila.iloc[3]
                cuit = fila.iloc[4]
                neto = fila.iloc[11]
                iva = fila.iloc[13]
                total = fila.iloc[15]

                query = """
                INSERT INTO ventas (fecha, tipo_comprobante, receptor, cuit_receptor, neto, iva, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                ejecutar_query(query, (str(fecha), str(tipo), str(receptor), str(cuit), float(neto), float(iva), float(total)))
            
            st.success(f"✅ Se procesaron {len(df)} comprobantes correctamente.")
            
        except Exception as e:
            st.error(f"Error al leer las columnas: {e}")
            st.info("Asegurate de que el TXT sea el de 'Ventas' exportado de ARCA.")