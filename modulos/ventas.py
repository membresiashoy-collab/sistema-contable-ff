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
            # Leemos el archivo con separador punto y coma y codificación latina
            df = pd.read_csv(archivo, sep=';', encoding='latin-1')
            
            # --- LIMPIEZA TOTAL DE COLUMNAS ---
            # Eliminamos comillas, espacios y posibles errores de codificación en los nombres
            df.columns = df.columns.str.replace('"', '').str.strip()
            
            st.write("### 🔍 Vista previa de columnas detectadas:")
            st.write(list(df.columns)) # Esto ayuda a verificar que los nombres estén limpios

            if st.button("🚀 Generar Contabilidad Real"):
                count = 0
                for _, fila in df.iterrows():
                    # Usamos los nombres exactos que vimos en tu archivo
                    fecha = fila['Fecha de Emisión']
                    neto = limpiar_monto(fila['Imp. Neto Gravado Total'])
                    iva = limpiar_monto(fila['Total IVA'])
                    total = limpiar_monto(fila['Imp. Total'])
                    receptor = fila['Denominación Receptor']

                    glosa = f"Venta s/Fac. - {receptor}"
                    
                    # Asiento de Partida Doble
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Caja/Clientes", total, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Ventas Gravadas", 0, neto, glosa))
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                       (str(fecha), "IVA Débito Fiscal", 0, iva, glosa))
                    count += 1
                
                st.success(f"✅ ¡Éxito! Se procesaron {count} facturas con importes reales.")
        except Exception as e:
            st.error(f"Error al procesar: {e}")