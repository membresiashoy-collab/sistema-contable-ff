import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    archivo = st.file_uploader("Subir CSV de Ventas Portal IVA", type=["csv"])

    if archivo:
        try:
            df = pd.read_csv(archivo, sep=';', decimal=',', encoding='latin-1')
        except:
            df = pd.read_csv(archivo, sep=',', decimal='.', encoding='utf-8')
            
        df.columns = [c.strip().replace('"', '') for c in df.columns]
        
        if st.button("🚀 Procesar Ventas"):
            asiento = database.obtener_proximo_asiento()
            cont = 0
            for _, r in df.iterrows():
                try:
                    fecha = r.get('Fecha de Emisión', r.get('Fecha'))
                    cliente = r.get('Denominación Receptor', 'Consumidor Final')
                    tipo = str(r.get('Tipo de Comprobante', 'Factura'))
                    tot = float(str(r['Importe Total']).replace(',', '.'))
                    iva = float(str(r.get('Total IVA', 0)).replace(',', '.'))
                    neto = tot - iva
                    
                    # Lógica ARCA: Nota de Crédito en ventas resta el ingreso
                    mult = -1 if "Nota de Crédito" in tipo else 1
                    glosa = f"{tipo}: {cliente}"

                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "DEUDORES POR VENTAS", tot * mult, 0, glosa))
                    database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                   (asiento, fecha, "VENTAS", 0, neto * mult, glosa))
                    
                    if iva != 0:
                        database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)",
                                       (asiento, fecha, "IVA DEBITO FISCAL", 0, iva * mult, glosa))
                    asiento += 1
                    cont += 1
                except: continue
            st.success(f"Procesadas {cont} ventas.")