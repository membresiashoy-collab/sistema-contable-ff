import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_num(valor):
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento Inteligente de Ventas")
    archivo = st.file_uploader("Subir CSV de ARCA", type=["csv"])
    
    if archivo:
        # Cargamos el archivo con separador punto y coma
        df = pd.read_csv(archivo, sep=';', encoding='latin-1')
        
        # Mapa automático: buscamos la columna que CONTENGA la palabra clave
        cols = {
            "fecha": [c for c in df.columns if 'Fecha' in c][0],
            "receptor": [c for c in df.columns if 'Receptor' in c and 'Denom' in c][0],
            "neto": [c for c in df.columns if 'Neto Gravado Total' in c][0],
            "iva": [c for c in df.columns if 'Total IVA' in c][0],
            "total": [c for c in df.columns if 'Imp. Total' in c][0]
        }
        
        st.write("✅ Columnas detectadas correctamente.")
        st.dataframe(df.head(3))

        if st.button("🚀 Generar Asientos Contables"):
            for _, fila in df.iterrows():
                # Extraemos datos usando el mapa inteligente
                f, r = fila[cols["fecha"]], fila[cols["receptor"]]
                n, i, t = limpiar_num(fila[cols["neto"]]), limpiar_num(fila[cols["iva"]]), limpiar_num(fila[cols["total"]])

                glosa = f"Venta s/Fac. ARCA - {r}"
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "Caja/Clientes", t, 0, glosa))
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "Ventas Gravadas", 0, n, glosa))
                if i > 0:
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "IVA Débito Fiscal", 0, i, glosa))
            st.success("¡Asientos generados con éxito!")