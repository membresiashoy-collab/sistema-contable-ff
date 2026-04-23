import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Carga de Ventas")
    
    if st.button("🗑️ Limpiar Ventas"):
        database.borrar_datos_modulo("VENTAS")
        st.rerun()

    archivo = st.file_uploader("Subir CSV de Ventas AFIP", type=["csv"])
    if archivo:
        try:
            # Leemos ignorando errores de caracteres extraños
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            
            # Limpiamos los títulos de las columnas de caracteres basura
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Buscamos columnas por aproximación (si contiene la palabra, la usa)
            c_fecha = next((c for c in df.columns if "FECHA" in c), None)
            c_tipo = next((c for c in df.columns if "TIPO DE COMPROBANTE" in c), None)
            c_total = next((c for c in df.columns if "IMP. TOTAL" in c or "TOTAL" in c), None)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Generar Asientos"):
                asiento = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f, t = r[c_fecha], str(r[c_tipo])
                        tot = float(str(r[c_total]).replace(',', '.'))
                        iva = float(str(r[c_iva]).replace(',', '.')) if pd.notnull(r[c_iva]) else 0
                        neto = tot - iva
                        
                        if database.es_reverso(t):
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "VENTAS", neto, 0, f"NC: {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "IVA DEBITO FISCAL", iva, 0, f"NC: {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "DEUDORES POR VENTAS", 0, tot, f"NC: {t}", "VENTAS"))
                        else:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "DEUDORES POR VENTAS", tot, 0, f"Fact: {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "VENTAS", 0, neto, f"Fact: {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (asiento, f, "IVA DEBITO FISCAL", 0, iva, f"Fact: {t}", "VENTAS"))
                        asiento += 1
                    except: continue
                st.success("¡Ventas procesadas!")
        except Exception as e:
            st.error(f"Error: {e}")