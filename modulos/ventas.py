import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Carga de Ventas")
    
    if st.button("🗑️ Limpiar Ventas"):
        database.borrar_datos_modulo("VENTAS")
        st.rerun()

    archivo = st.file_uploader("Subir CSV", type=["csv"])
    if archivo:
        try:
            # Leemos con encoding latin-1 para capturar caracteres AFIP
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            
            # Limpiamos los nombres de las columnas de cualquier basura de encoding
            df.columns = [c.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip().upper() for c in df.columns]
            
            # Mapeo manual para asegurar que no falle por una tilde
            col_fecha = next((c for c in df.columns if "FECHA" in c), None)
            col_tipo = next((c for c in df.columns if "TIPO DE COMPROBANTE" in c), None)
            col_total = next((c for c in df.columns if "IMP. TOTAL" in c or "TOTAL" in c), None)
            col_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 Procesar"):
                nro = database.proximo_asiento()
                for _, r in df.iterrows():
                    try:
                        f = r[col_fecha]
                        t = str(r[col_tipo])
                        tot = float(str(r[col_total]).replace(',', '.'))
                        iva = float(str(r[col_iva]).replace(',', '.')) if pd.notnull(r[col_iva]) else 0
                        neto = tot - iva
                        
                        # Lógica contable de reverso según tabla_comprobantes
                        if database.es_reverso(t):
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "VENTAS", neto, 0, f"NC: {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA DEBITO FISCAL", iva, 0, f"NC: {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "DEUDORES POR VENTAS", 0, tot, f"NC: {t}", "VENTAS"))
                        else:
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "DEUDORES POR VENTAS", tot, 0, f"Fact: {t}", "VENTAS"))
                            database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "VENTAS", 0, neto, f"Fact: {t}", "VENTAS"))
                            if iva > 0: database.ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)", (nro, f, "IVA DEBITO FISCAL", 0, iva, f"Fact: {t}", "VENTAS"))
                        nro += 1
                    except: continue
                st.success("Asientos generados.")
        except Exception as e:
            st.error(f"Error: {e}")