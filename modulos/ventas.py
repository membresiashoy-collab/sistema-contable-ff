import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_arca(valor):
    if pd.isna(valor) or valor == "": return 0.0
    # Quitamos puntos de miles y cambiamos coma por punto
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesar Ventas ARCA")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        # Forzamos el separador ';' detectado en tu archivo
        df = pd.read_csv(archivo, sep=';', encoding='latin-1')
        st.dataframe(df.head(3))

        if st.button("🚀 Generar Contabilidad Real"):
            for _, fila in df.iterrows():
                fecha = fila['Fecha de Emisión']
                # Limpieza de importes según tu archivo
                neto = limpiar_arca(fila['Imp. Neto Gravado Total'])
                iva = limpiar_arca(fila['Total IVA'])
                total = limpiar_arca(fila['Imp. Total'])
                receptor = fila['Denominación Receptor']

                glosa = f"Venta s/Fac. - {receptor}"
                
                # Asiento de Partida Doble
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                               (fecha, "Caja/Clientes", total, 0, glosa))
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                               (fecha, "Ventas Gravadas", 0, neto, glosa))
                if iva > 0:
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                   (fecha, "IVA Débito Fiscal", 0, iva, glosa))
            
            st.success("✅ Asientos generados con importes reales.")