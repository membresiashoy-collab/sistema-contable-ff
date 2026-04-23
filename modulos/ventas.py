import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Carga de Ventas (ARCA)")
    archivo = st.file_uploader("Subir CSV Ventas Emitidas", type=["csv"])

    if archivo:
        if database.archivo_ya_cargado(archivo.name):
            st.warning(f"El archivo '{archivo.name}' ya fue procesado.")
            if not st.checkbox("Procesar de nuevo"): return

        # Intento de lectura robusto para Ventas
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            archivo.seek(0)
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='utf-8')
        
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        if st.button("🚀 Grabar Asientos de Ventas"):
            proximo = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    f = r.get('Fecha de Emisión', r.get('Fecha'))
                    t = r.get('Tipo de Comprobante', 'Factura')
                    cli = r.get('Denominación Receptor', 'C. Final')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{t}: {cli}"

                    if database.es_comprobante_reverso(t):
                        # NC Ventas: Venta (D) e IVA (D) a Deudores (H)
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "VENTAS", neto, 0, glosa, "VENTAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                    else:
                        # Factura Ventas: Deudores (D) a Venta (H) e IVA (H)
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "VENTAS", 0, neto, glosa, "VENTAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (proximo, f, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                    proximo += 1
                except: continue
            database.registrar_archivo(archivo.name)
            st.success("Ventas procesadas con éxito.")