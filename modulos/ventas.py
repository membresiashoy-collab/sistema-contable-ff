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
    st.title("📂 Procesamiento Blindado de Ventas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        try:
            # Leemos el archivo. El delimitador ';' es correcto según tu análisis.
            df = pd.read_csv(archivo, sep=';', encoding='latin-1')
            
            st.info("Archivo cargado. Procesando por índices de columna para evitar errores de tildes.")

            if st.button("🚀 Generar Contabilidad Real"):
                count = 0
                for _, fila in df.iterrows():
                    # USAMOS .iloc PARA IR A LA POSICIÓN FIJA (según tu lista):
                    # 0: Fecha, 8: Receptor, 22: Neto, 26: IVA, 27: Total
                    fecha    = fila.iloc[0] 
                    receptor = fila.iloc[8]
                    neto     = limpiar_monto(fila.iloc[22])
                    iva      = limpiar_monto(fila.iloc[26])
                    total    = limpiar_monto(fila.iloc[27])

                    glosa = f"Venta s/Fac. - {receptor}"
                    
                    # Registro Contable (Partida Doble)
                    # 1. Al Debe: Caja/Clientes
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Caja/Clientes", total, 0, glosa))
                    
                    # 2. Al Haber: Ventas e IVA
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (str(fecha), "Ventas Gravadas", 0, neto, glosa))
                    
                    if iva > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                       (str(fecha), "IVA Débito Fiscal", 0, iva, glosa))
                    count += 1
                
                st.success(f"✅ ¡Éxito Total! Se procesaron {count} facturas con sus importes reales.")
        except Exception as e:
            st.error(f"Error técnico: {e}")