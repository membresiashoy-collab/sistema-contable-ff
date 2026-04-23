import streamlit as st
import pandas as pd
import database
import re

def limpiar_nombre_columna(col):
    # Elimina caracteres no deseados y normaliza
    col = col.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')
    col = re.sub(r'[^a-zA-Z0-9\s%]', '', col)
    return col.strip().upper()

def mostrar_ventas():
    st.title("📤 Importación de Ventas")
    
    if st.button("🗑️ Vaciar Ventas"):
        database.borrar_datos_modulo("VENTAS")
        st.rerun()

    archivo = st.file_uploader("Subir CSV Ventas", type=["csv"])
    if archivo:
        try:
            # Leemos ignorando errores de codificación iniciales
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            # Aplicamos limpieza profunda a los títulos de las columnas
            df.columns = [limpiar_nombre_columna(c) for c in df.columns]
            
            st.write("Columnas procesadas correctamente:", list(df.columns))

            if st.button("🚀 Generar Asientos"):
                asiento = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        # Buscamos columnas por palabras clave para evitar fallos de tildes
                        f = r.filter(like='FECHA').iloc[0]
                        t = str(r.filter(like='TIPO DE COMPROBANTE').iloc[0])
                        tot = float(str(r.filter(like='TOTAL').iloc[-1]).replace(',', '.'))
                        iva = float(str(r.filter(like='TOTAL IVA').iloc[0]).replace(',', '.'))
                        neto = tot - iva
                        
                        glosa = f"Venta: {t}"
                        
                        if database.es_reverso(t):
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "VENTAS", neto, 0, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "IVA DEBITO FISCAL", iva, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "DEUDORES POR VENTAS", 0, tot, glosa, "VENTAS"))
                        else:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "DEUDORES POR VENTAS", tot, 0, glosa, "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "VENTAS", 0, neto, glosa, "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "IVA DEBITO FISCAL", 0, iva, glosa, "VENTAS"))
                        asiento += 1
                    except: continue
                st.success("Asientos de Ventas procesados.")
        except Exception as e:
            st.error(f"Error técnico: {e}")