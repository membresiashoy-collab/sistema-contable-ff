import streamlit as st
import pandas as pd
import database # Importación absoluta desde la raíz

def mostrar_ventas():
    st.title("📤 Registro de Ventas (Portal IVA)")
    archivo = st.file_uploader("Subir CSV de Ventas", type=["csv"])

    if archivo:
        # AFIP Ventas suele usar ',' como separador
        df = pd.read_csv(archivo)
        st.dataframe(df.head())

        if st.button("🚀 Procesar Ventas y Generar Asientos"):
            asiento = database.obtener_proximo_asiento()
            for _, r in df.iterrows():
                # Ajustar nombres de columnas según tu CSV de ventas habitual
                try:
                    fecha = r['Fecha']
                    cliente = r['Denominación Receptor']
                    total = float(r['Importe Total'])
                    iva = float(r['Importe IVA 21%']) + float(r.get('Importe IVA 10,5%', 0))
                    neto = total - iva
                    
                    # DEBE: Deudores por Ventas (Total)
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "DEUDORES POR VENTAS", total, 0, f"Venta: {cliente}"))
                    # HABER: Ventas (Neto)
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "VENTAS", 0, neto, f"Venta: {cliente}"))
                    # HABER: IVA Débito Fiscal
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "IVA DEBITO FISCAL", 0, iva, f"Venta: {cliente}"))
                    asiento += 1
                except:
                    continue
            st.success("Ventas procesadas correctamente.")