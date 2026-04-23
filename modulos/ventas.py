import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Ventas (Portal IVA ARCA)")
    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='utf-8')
        
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        if st.button("🚀 Procesar según Tabla de Comprobantes"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    fecha = r.get('Fecha de Emisión', r.get('Fecha'))
                    tipo = r.get('Tipo de Comprobante', 'Factura')
                    cliente = r.get('Denominación Receptor', 'C. Final')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{tipo}: {cliente}"

                    if database.es_comprobante_reverso(tipo):
                        # REVERSO: Nota de Crédito Ventas
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "VENTAS", neto, 0, glosa))
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", iva, 0, glosa))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "DEUDORES POR VENTAS", 0, tot, glosa))
                    else:
                        # NORMAL: Factura Ventas
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "DEUDORES POR VENTAS", tot, 0, glosa))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "VENTAS", 0, neto, glosa))
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", 0, iva, glosa))
                    asiento += 1
                except: continue
            st.success("Ventas procesadas correctamente.")