import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Carga de Compras")
    archivo = st.file_uploader("Subir CSV Compras", type=["csv"])

    if archivo:
        if database.archivo_procesado(archivo.name):
            st.warning("⚠️ Archivo ya procesado.")
            if not st.checkbox("Re-procesar"): return

        # Lector para Compras (Punto y Coma)
        df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        if st.button("Procesar Compras"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    fecha, tipo, prov = r['Fecha de Emisión'], r['Tipo de Comprobante'], r['Denominación Vendedor']
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{tipo}: {prov}"

                    if database.es_comprobante_reverso(tipo):
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "PROVEEDORES", tot, 0, glosa, "COMPRAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "COMPRAS", 0, neto, glosa, "COMPRAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "IVA CREDITO FISCAL", 0, iva, glosa, "COMPRAS"))
                    else:
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "COMPRAS", neto, 0, glosa, "COMPRAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "IVA CREDITO FISCAL", iva, 0, glosa, "COMPRAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "PROVEEDORES", 0, tot, glosa, "COMPRAS"))
                    asiento += 1
                except: continue
            database.registrar_archivo(archivo.name)
            st.success("✅ Compras registradas.")