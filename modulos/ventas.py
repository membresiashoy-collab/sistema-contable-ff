import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Registro de Ventas (Portal IVA)")
    archivo = st.file_uploader("Subir CSV de Ventas Emitidas", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='utf-8')
            
        df.columns = [c.strip().replace('"', '') for c in df.columns]
        st.dataframe(df.head())

        if st.button("🚀 Procesar Ventas y Generar Asientos"):
            asiento = database.obtener_proximo_asiento()
            cont = 0
            for _, r in df.iterrows():
                try:
                    fecha = r.get('Fecha de Emisión', r.get('Fecha'))
                    cliente = r.get('Denominación Receptor', 'Consumidor Final')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    # Intentar obtener IVA de columna o calcularlo
                    iva = float(str(r.get('Total IVA', r.get('Importe IVA 21%', tot*0.21/1.21))).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"Venta: {cliente}"

                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "DEUDORES POR VENTAS", tot, 0, glosa))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "VENTAS", 0, neto, glosa))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "IVA DEBITO FISCAL", 0, iva, glosa))
                    asiento += 1
                    cont += 1
                except:
                    continue
            st.success(f"Se cargaron {cont} asientos de ventas correctamente.")