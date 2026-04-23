import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_monto(valor):
    if pd.isna(valor): return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento de Ventas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        df = pd.read_csv(archivo, encoding='latin-1', sep=None, engine='python')
        st.dataframe(df.head(5))

        if st.button("🚀 Procesar Contabilidad"):
            for _, fila in df.iterrows():
                fecha = fila.get('Fecha de Emisión') or fila.iloc[0]
                total = limpiar_monto(fila.get('Importe Total') or fila.iloc[15])
                neto = limpiar_monto(fila.get('Importe Neto Gravado') or fila.iloc[11])
                iva = limpiar_monto(fila.get('Importe IVA') or fila.iloc[13])
                receptor = fila.get('Denominación del Receptor') or fila.iloc[7]

                glosa = f"Venta s/Fac. ARCA - {receptor}"
                # Asiento automático
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)", (fecha, "Caja/Clientes", total, 0, glosa))
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)", (fecha, "Ventas Gravadas", 0, neto, glosa))
                if iva > 0:
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, ?, ?)", (fecha, "IVA Débito Fiscal", 0, iva, glosa))
            st.success("Asientos generados correctamente.")