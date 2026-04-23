import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_monto(valor):
    """Convierte formatos '1.234,56' a '1234.56'"""
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesar Ventas ARCA")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # Leemos ignorando los nombres de las columnas para evitar errores de tildes
            df = pd.read_csv(archivo, sep=';', encoding='latin-1', quotechar='"')
            
            st.write("### 🔍 Datos detectados (Vista por índices):")
            st.dataframe(df.head(3))

            if st.button("🚀 Generar Contabilidad Real"):
                count = 0
                for _, fila in df.iterrows():
                    # Usamos iloc para llamar por NÚMERO de columna, evitando el error de nombre
                    fecha = fila.iloc[0]      # Columna 0: Fecha de Emisión
                    receptor = fila.iloc[8]   # Columna 8: Denominación Receptor
                    neto = limpiar_monto(fila.iloc[22])  # Columna 22: Imp. Neto Gravado Total
                    iva = limpiar_monto(fila.iloc[26])   # Columna 26: Total IVA
                    total = limpiar_monto(fila.iloc[27])  # Columna 27: Imp. Total

                    glosa = f"Venta s/Fac. - {receptor}"
                    
                    # Inserción en Libro Diario (Partida Doble)
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Caja/Clientes", total, 0, glosa))
                    
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Ventas Gravadas", 0, neto, glosa))
                    
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                       (str(fecha), "IVA Débito Fiscal", 0, iva, glosa))
                    count += 1
                
                st.success(f"✅ ¡Proceso Exitoso! Se generaron {count} asientos con importes reales.")
        except Exception as e:
            st.error(f"Error al procesar: {e}")