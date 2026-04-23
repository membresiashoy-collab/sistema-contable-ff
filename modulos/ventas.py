import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Carga de Ventas")
    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])

    if archivo:
        if database.archivo_procesado(archivo.name):
            st.warning("⚠️ Este archivo ya fue cargado.")
            if not st.checkbox("Ignorar aviso y cargar igual"): return

        # Lector flexible para Ventas (suele ser Coma)
        try:
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='latin-1')
            if len(df.columns) < 5: raise Exception("Cambio de separador")
        except:
            archivo.seek(0)
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        
        df.columns = [c.strip().replace('"', '') for c in df.columns]
        st.write("Columnas detectadas:", list(df.columns))

        if st.button("Procesar Ventas"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                try:
                    fecha = r.get('Fecha de Emisión', r.get('Fecha'))
                    tipo = str(r.get('Tipo de Comprobante', 'Factura'))
                    cliente = r.get('Denominación Receptor', 'C. Final')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', r.get('Importe IVA 21%', 0))).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"{tipo}: {cliente}"

                    # Lógica de Reverso
                    if database.es_comprobante_reverso(tipo):
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "VENTAS", neto, 0, glosa, "VENTAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                    else:
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "VENTAS", 0, neto, glosa, "VENTAS"))
                        if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, fecha, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                    asiento += 1
                except: continue
            database.registrar_archivo(archivo.name)
            st.success("✅ Ventas registradas.")