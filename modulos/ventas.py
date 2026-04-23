import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_ventas():
    st.header("📊 Importación de Ventas ARCA")
    archivo = st.file_uploader("Subir CSV de Mis Comprobantes Emitidos", type=["csv"])
    
    if archivo:
        try:
            # ARCA usa ';' o ',' según el reporte. Probamos ';' primero.
            df = pd.read_csv(archivo, sep=';', encoding='latin1')
            if 'Fecha' not in df.columns and 'Fecha de Emisión' not in df.columns:
                archivo.seek(0)
                df = pd.read_csv(archivo, sep=',', encoding='latin1')
        except:
            st.error("Error al leer el archivo. Verifique el formato CSV.")
            return

        st.dataframe(df.head())

        if st.button("Procesar y Generar Asientos"):
            col_f = 'Fecha de Emisión' if 'Fecha de Emisión' in df.columns else 'Fecha'
            col_rec = 'Denominación Receptor'
            col_cuit = 'Nro. Doc. Receptor'
            col_neto = 'Imp. Neto Gravado Total' if 'Imp. Neto Gravado Total' in df.columns else 'Neto Gravado Total'
            col_iva = 'Total IVA'
            col_total = 'Imp. Total' if 'Imp. Total' in df.columns else 'Total'

            for _, fila in df.iterrows():
                ejecutar_query("""
                    INSERT INTO ventas (fecha, receptor, cuit_receptor, neto, iva, total)
                    VALUES (?,?,?,?,?,?)""", 
                    (fila[col_f], fila[col_rec], fila[col_cuit], fila[col_neto], fila[col_iva], fila[col_total]))
                
                # ASIENTO AUTOMÁTICO
                # Debe: Deudores por Ventas (Cta: 1121010000)
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                              (fila[col_f], "1121010000", fila[col_total], 0, f"Venta: {fila[col_rec]}"))
                # Haber: Ventas Gravadas (Cta: 4111000000)
                ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                              (fila[col_f], "4111000000", 0, fila[col_neto], f"Neto Venta"))
                # Haber: IVA Débito Fiscal (Cta: 2121010000)
                if fila[col_iva] > 0:
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)",
                                  (fila[col_f], "2121010000", 0, fila[col_iva], f"IVA Débito Fiscal"))
            
            st.success("¡Importación finalizada y asientos generados en el Diario!")