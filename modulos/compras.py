import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Registro de Compras (Portal IVA)")
    archivo = st.file_uploader("Subir CSV de Compras Recibidas", type=["csv"])

    if archivo:
        # Configuración para tu archivo: separador ';' y decimal ','
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        df.columns = [c.strip('"') for c in df.columns]

        st.dataframe(df[['Fecha de Emisión', 'Denominación Vendedor', 'Importe Total', 'Total IVA']].head())

        if st.button("🚀 Procesar Compras y Generar Asientos"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    fecha = r['Fecha de Emisión']
                    prov = str(r['Denominación Vendedor']).replace('"', '')
                    total = float(r['Importe Total'])
                    iva = float(r['Total IVA'])
                    neto = total - iva
                    glosa = f"Compra: {prov}"

                    # DEBE: Compras (Neto)
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "COMPRAS", neto, 0, glosa))
                    # DEBE: IVA Crédito Fiscal
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "IVA CREDITO FISCAL", iva, 0, glosa))
                    # HABER: Proveedores (Total)
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "PROVEEDORES", 0, total, glosa))
                    asiento += 1
                except:
                    continue
            st.success("Compras procesadas correctamente.")