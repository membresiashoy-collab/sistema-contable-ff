import streamlit as st
import pandas as pd
import database

def mostrar_compras():
    st.title("📥 Módulo de Compras")
    archivo = st.file_uploader("Subir CSV de Compras Portal IVA", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='utf-8')
        
        df.columns = [c.strip().replace('"', '') for c in df.columns]
        st.dataframe(df[['Fecha de Emisión', 'Tipo de Comprobante', 'Denominación Vendedor', 'Importe Total']].head())

        if st.button("🚀 Procesar Compras"):
            asiento = database.obtener_proximo_asiento()
            cont = 0
            for _, r in df.iterrows():
                try:
                    fecha = r['Fecha de Emisión']
                    prov = str(r['Denominación Vendedor']).replace('"', '')
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    tipo = str(r['Tipo de Comprobante'])
                    
                    # Lógica de ARCA: Nota de Crédito invierte el sentido (es un "menor gasto")
                    mult = -1 if "Nota de Crédito" in tipo else 1
                    glosa = f"{tipo}: {prov}"

                    # Asiento Dinámico
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "COMPRAS", neto * mult, 0, glosa))
                    
                    if iva != 0: # CORRECCIÓN 1: Omitir si IVA es 0
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                       (asiento, fecha, "IVA CREDITO FISCAL", iva * mult, 0, glosa))
                    
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "PROVEEDORES", 0, tot * mult, glosa))
                    asiento += 1
                    cont += 1
                except: continue
            st.success(f"Procesadas {cont} compras.")