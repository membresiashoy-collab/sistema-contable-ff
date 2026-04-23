import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Compras (Portal IVA ARCA)")
    archivo = st.file_uploader("Subir CSV de Compras", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        if st.button("🚀 Procesar según Tabla de Comprobantes"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    fecha, tipo, prov = r['Fecha de Emisión'], r['Tipo de Comprobante'], r['Denominación Vendedor']
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{tipo}: {prov}"

                    if database.es_comprobante_reverso(tipo):
                        # REVERSO: Nota de Crédito Compras
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "PROVEEDORES", tot, 0, glosa))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "COMPRAS", 0, neto, glosa))
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "IVA CREDITO FISCAL", 0, iva, glosa))
                    else:
                        # NORMAL: Factura Compras
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "COMPRAS", neto, 0, glosa))
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "IVA CREDITO FISCAL", iva, 0, glosa))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "PROVEEDORES", 0, tot, glosa))
                    asiento += 1
                except: continue
            st.success("Compras procesadas correctamente.")