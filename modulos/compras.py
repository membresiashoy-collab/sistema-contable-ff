import streamlit as st
import pandas as pd
import sys
import os

# Fix de importación: sube un nivel para encontrar database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, obtener_proximo_asiento

def mostrar_compras():
    st.title("📥 Módulo de Compras")
    archivo = st.file_uploader("Subir CSV de Portal IVA", type=["csv"])

    if archivo:
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        df.columns = [c.strip('"') for c in df.columns]

        if st.button("🚀 Cargar a Libro Diario"):
            asiento = obtener_proximo_asiento()
            for _, r in df.iterrows():
                total = float(r['Importe Total'])
                iva = float(r['Total IVA'])
                neto = total - iva
                prov = str(r['Denominación Vendedor']).replace('"', '')
                fecha = r['Fecha de Emisión']

                # Asiento Triple
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "COMPRAS", neto, 0, f"Compra: {prov}"))
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "IVA CREDITO FISCAL", iva, 0, f"Compra: {prov}"))
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "PROVEEDORES", 0, total, f"Compra: {prov}"))
                asiento += 1
            st.success("Asientos generados correctamente.")