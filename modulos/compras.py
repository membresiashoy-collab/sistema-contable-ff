import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Registro de Compras (Portal IVA)")
    archivo = st.file_uploader("Subir CSV de Compras Recibidas", type=["csv"])

    if archivo:
        # Intentar leer con latin-1 que es el estándar de AFIP para evitar el UnicodeDecodeError
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except UnicodeDecodeError:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        
        # Limpiar nombres de columnas (quitar comillas y espacios)
        df.columns = [c.strip().replace('"', '') for c in df.columns]

        st.subheader("Vista previa de comprobantes")
        st.dataframe(df[['Fecha de Emisión', 'Denominación Vendedor', 'Importe Total', 'Total IVA']].head())

        if st.button("🚀 Procesar Compras y Generar Asientos"):
            asiento = database.obtener_proximo_asiento()
            cont = 0
            for _, r in df.iterrows():
                try:
                    fecha = r['Fecha de Emisión']
                    prov = str(r['Denominación Vendedor']).replace('"', '')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r['Total IVA']).replace(',', '.'))
                    neto = tot - iva
                    glosa = f"Compra: {prov}"

                    # Asiento contable
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "COMPRAS", neto, 0, glosa))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "IVA CREDITO FISCAL", iva, 0, glosa))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "PROVEEDORES", 0, tot, glosa))
                    asiento += 1
                    cont += 1
                except Exception as e:
                    continue
            st.success(f"Se cargaron {cont} asientos de compras correctamente.")