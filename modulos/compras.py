import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Carga de Compras (Portal IVA)")
    archivo = st.file_uploader("Subir CSV Compras Recibidas", type=["csv"])

    if archivo:
        if database.archivo_ya_cargado(archivo.name):
            st.error("Archivo ya cargado anteriormente.")
            return

        # Lector específico para tu archivo
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        if st.button("🚀 Grabar Asientos de Compras"):
            proximo = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    f, t, prov = r['Fecha de Emisión'], r['Tipo de Comprobante'], r['Denominación Vendedor']
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{t}: {prov}"

                    if database.es_comprobante_reverso(t):
                        # NC Compras: Proveedor (D) a Compra (H) e IVA (H)
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "PROVEEDORES", tot, 0, glosa, "COMPRAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "COMPRAS", 0, neto, glosa, "COMPRAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "IVA CREDITO FISCAL", 0, iva, glosa, "COMPRAS"))
                    else:
                        # Factura Compras: Compra (D) e IVA (D) a Proveedor (H)
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "COMPRAS", neto, 0, glosa, "COMPRAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "IVA CREDITO FISCAL", iva, 0, glosa, "COMPRAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "PROVEEDORES", 0, tot, glosa, "COMPRAS"))
                    proximo += 1
                except: continue
            database.registrar_archivo(archivo.name)
            st.success("Compras procesadas con éxito.")