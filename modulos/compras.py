import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Registro de Compras")
    archivo = st.file_uploader("Subir CSV Portal IVA (Compras)", type=["csv"])
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            if st.button("🚀 Procesar Asientos Contables"):
                nro = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f, t = r['FECHA DE EMISIÓN'], str(r['TIPO DE COMPROBANTE'])
                        prov = r['DENOMINACIÓN VENDEDOR']
                        tot = float(str(r['IMPORTE TOTAL']).replace(',', '.'))
                        iva = float(str(r.get('TOTAL IVA', 0)).replace(',', '.'))
                        neto = tot - iva
                        
                        if database.es_comprobante_reverso(t):
                            # NC Compra: Proveedor al DEBE, Compra/IVA al HABER
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "PROVEEDORES", tot, 0, f"NC: {prov}", "COMPRAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "COMPRAS", 0, neto, f"NC: {prov}", "COMPRAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA CREDITO FISCAL", 0, iva, f"NC: {prov}", "COMPRAS"))
                        else:
                            # Factura Compra: Compra/IVA al DEBE, Proveedor al HABER
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "COMPRAS", neto, 0, f"Fact: {prov}", "COMPRAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA CREDITO FISCAL", iva, 0, f"Fact: {prov}", "COMPRAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "PROVEEDORES", 0, tot, f"Fact: {prov}", "COMPRAS"))
                        nro += 1
                    except: continue
                st.success("Asientos de compras generados.")
        except Exception as e:
            st.error(f"Error: {e}")