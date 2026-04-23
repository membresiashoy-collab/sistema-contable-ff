import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Registro de Ventas")
    archivo = st.file_uploader("Subir CSV de Ventas (Portal IVA)", type=["csv"])

    if archivo:
        if database.archivo_ya_existe(archivo.name):
            st.warning(f"⚠️ El archivo '{archivo.name}' ya fue procesado anteriormente.")
            if not st.checkbox("Procesar de todos modos"): return

        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='utf-8')
        
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        if st.button("🚀 Procesar Ventas"):
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
                        # REVERSO NC: Venta al Debe, Deudor al Haber
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "VENTAS", neto, 0, glosa, "VENTAS"))
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                    else:
                        # NORMAL FACTURA: Deudor al Debe, Venta al Haber
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "VENTAS", 0, neto, glosa, "VENTAS"))
                        if iva > 0:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                    asiento += 1
                except: continue
            database.registrar_archivo(archivo.name)
            st.success("Ventas procesadas y registradas.")