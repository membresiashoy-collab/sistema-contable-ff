import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    if st.button("🗑️ Limpiar Datos de Ventas"):
        database.limpiar_modulo("VENTAS")
        st.success("Módulo de ventas reseteado.")
        st.rerun()

    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='latin-1')
            if len(df.columns) < 5: raise Exception()
        except:
            archivo.seek(0)
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')

        df.columns = [c.strip().replace('"', '') for c in df.columns]
        
        if st.button("🚀 Procesar Asientos"):
            asiento_nro = database.obtener_proximo_asiento()
            cont = 0
            for _, r in df.iterrows():
                try:
                    f = r.get('Fecha de Emisión', r.get('Fecha'))
                    t = str(r.get('Tipo de Comprobante', 'Factura'))
                    cli = r.get('Denominación Receptor', 'C. Final')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{t}: {cli}"

                    if database.es_reverso(t):
                        # Nota de Crédito: Reversa el ingreso
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "VENTAS", neto, 0, glosa, "VENTAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                    else:
                        # Factura: Asiento Normal
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "VENTAS", 0, neto, glosa, "VENTAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento_nro, f, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                    asiento_nro += 1
                    cont += 1
                except: continue
            st.success(f"Se generaron {cont} asientos en el Libro Diario.")