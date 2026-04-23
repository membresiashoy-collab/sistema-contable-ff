import streamlit as st
import pandas as pd
import sys
import os

# Fix de rutas para encontrar database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, obtener_proximo_asiento

def mostrar_compras():
    st.title("📥 Registro de Compras (Portal IVA)")
    
    archivo = st.file_uploader("Subir CSV de Compras", type=["csv"])

    if archivo:
        # Configuración para el formato de ARCA/AFIP
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        df.columns = [c.strip('"') for c in df.columns]

        st.subheader("Vista previa de importación")
        st.dataframe(df[['Fecha de Emisión', 'Denominación Vendedor', 'Importe Total', 'Total IVA']].head())

        if st.button("🚀 Procesar y Generar Asientos"):
            asiento_actual = obtener_proximo_asiento()
            
            for _, r in df.iterrows():
                fecha = r['Fecha de Emisión']
                proveedor = str(r['Denominación Vendedor']).strip('"')
                total = float(r['Importe Total'])
                iva = float(r['Total IVA'])
                neto = total - iva
                glosa = f"Compra: {proveedor}"

                # Asiento Contable
                # DEBE: COMPRAS (Neto)
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                               (asiento_actual, fecha, "COMPRAS", neto, 0, glosa))
                # DEBE: IVA CREDITO FISCAL
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                               (asiento_actual, fecha, "IVA CREDITO FISCAL", iva, 0, glosa))
                # HABER: PROVEEDORES (Total)
                ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                               (asiento_actual, fecha, "PROVEEDORES", 0, total, glosa))
                
                asiento_actual += 1
            
            st.success("Procesamiento completado. Los asientos fueron cargados al Diario.")