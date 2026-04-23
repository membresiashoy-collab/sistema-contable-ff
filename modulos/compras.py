import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Carga de Compras")
    archivo = st.file_uploader("CSV de Compras", type=["csv"])
    if archivo:
        # Formato específico Portal IVA
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        df.columns = [c.strip('"') for c in df.columns]
        
        if st.button("Procesar Compras"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    f, prov = r['Fecha de Emisión'], r['Denominación Vendedor']
                    tot, iva = float(r['Importe Total']), float(r['Total IVA'])
                    neto = tot - iva
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, f, "COMPRAS", neto, 0, f"Compra {prov}"))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, f, "IVA CREDITO FISCAL", iva, 0, f"Compra {prov}"))
                    asiento += 1
                except: continue
            st.success("Compras cargadas.")