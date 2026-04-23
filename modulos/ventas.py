import streamlit as st
import pandas as pd
import database 

def mostrar_ventas():
    st.title("📤 Carga de Ventas")
    archivo = st.file_uploader("CSV de Ventas", type=["csv"])
    if archivo:
        df = pd.read_csv(archivo) # Ajustar separador si es necesario
        st.dataframe(df.head())
        if st.button("Procesar Ventas"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    fecha, total, cliente = r['Fecha'], float(r['Importe Total']), r['Denominación Receptor']
                    iva = total * 0.21 / 1.21 # Ejemplo genérico
                    neto = total - iva
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "DEUDORES", total, 0, f"Venta {cliente}"))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", 0, iva, f"Venta {cliente}"))
                    asiento += 1
                except: continue
            st.success("Ventas cargadas.")